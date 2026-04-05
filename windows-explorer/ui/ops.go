package ui

import (
	"fmt"
	"sync"
	"sync/atomic"
	"time"

	"github.com/fileproxy/windows-explorer/client"
)

// OpKind classifies an operation.
type OpKind string

const (
	OpUpload   OpKind = "upload"
	OpDownload OpKind = "download"
	OpDelete   OpKind = "delete"
)

// OpStatus is the lifecycle state of an operation.
type OpStatus int

const (
	OpPending OpStatus = iota
	OpActive
	OpDone
	OpFailed
)

// Op tracks a single file transfer or delete operation.
type Op struct {
	ID   string
	Kind OpKind
	Conn string
	Path string // full path within the connection
	Name string // display filename

	TotalBytes int64
	doneBytes  atomic.Int64

	Status    OpStatus
	ErrMsg    string
	DoneAt    time.Time
	PendingID string // server-side pending upload ID (set when matched)
}

// AddDone atomically increments the bytes-done counter.
func (o *Op) AddDone(n int64) { o.doneBytes.Add(n) }

// DoneBytes returns the current bytes-done counter.
func (o *Op) DoneBytes() int64 { return o.doneBytes.Load() }

// Percent returns the completion percentage (0–100).
func (o *Op) Percent() int {
	if o.TotalBytes <= 0 {
		return 0
	}
	p := int(o.doneBytes.Load() * 100 / o.TotalBytes)
	if p > 100 {
		p = 100
	}
	return p
}

// StatusLabel returns a short human-readable status string.
func (o *Op) StatusLabel() string {
	switch o.Status {
	case OpPending:
		return "pending"
	case OpActive:
		if o.TotalBytes > 0 {
			return fmt.Sprintf("%d%%", o.Percent())
		}
		return "active"
	case OpDone:
		return "done"
	case OpFailed:
		return "failed"
	default:
		return ""
	}
}

// OpsStore is a goroutine-safe list of operations.
type OpsStore struct {
	mu  sync.RWMutex
	ops []*Op
}

// Add appends an op.
func (s *OpsStore) Add(op *Op) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.ops = append(s.ops, op)
}

// Find returns the op with the given ID, or nil.
func (s *OpsStore) Find(id string) *Op {
	s.mu.RLock()
	defer s.mu.RUnlock()
	for _, op := range s.ops {
		if op.ID == id {
			return op
		}
	}
	return nil
}

// Active returns all ops that should appear in the UI (not yet pruned).
func (s *OpsStore) Active() []*Op {
	s.mu.RLock()
	defer s.mu.RUnlock()
	now := time.Now()
	var result []*Op
	for _, op := range s.ops {
		if (op.Status == OpDone || op.Status == OpFailed) && now.Sub(op.DoneAt) > 4*time.Second {
			continue
		}
		result = append(result, op)
	}
	return result
}

// Prune removes completed ops older than 5 seconds.
func (s *OpsStore) Prune() {
	s.mu.Lock()
	defer s.mu.Unlock()
	now := time.Now()
	filtered := s.ops[:0]
	for _, op := range s.ops {
		if (op.Status == OpDone || op.Status == OpFailed) && now.Sub(op.DoneAt) > 5*time.Second {
			continue
		}
		filtered = append(filtered, op)
	}
	s.ops = filtered
}

// SyncWithPending reconciles queued upload ops against the server's pending list.
func (s *OpsStore) SyncWithPending(conn string, pending []client.PendingUpload) {
	s.mu.Lock()
	defer s.mu.Unlock()

	byPath := make(map[string]client.PendingUpload, len(pending))
	for _, p := range pending {
		byPath[p.Path] = p
	}

	for _, op := range s.ops {
		if op.Kind != OpUpload || op.Conn != conn {
			continue
		}
		if op.Status == OpDone || op.Status == OpFailed {
			continue
		}
		if p, ok := byPath[op.Path]; ok {
			op.PendingID = p.ID
			op.TotalBytes = p.ExpectedSize
			switch p.Status {
			case "uploading":
				op.Status = OpActive
			case "failed":
				op.Status = OpFailed
				op.ErrMsg = "upload failed on server"
				op.DoneAt = time.Now()
			}
		} else {
			// No longer in the pending list — upload completed.
			op.Status = OpDone
			op.doneBytes.Store(op.TotalBytes)
			op.DoneAt = time.Now()
		}
	}
}
