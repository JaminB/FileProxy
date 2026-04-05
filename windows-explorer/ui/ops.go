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
// Immutable fields (ID, Kind, Conn, Path, Name) may be read freely after Add().
// All mutable fields are protected by mu; use the provided methods to mutate them.
type Op struct {
	// Immutable after Add() — safe to read without a lock.
	ID   string
	Kind OpKind
	Conn string
	Path string
	Name string

	mu         sync.Mutex
	status     OpStatus
	errMsg     string
	doneAt     time.Time
	pendingID  string
	totalBytes int64
	doneBytes  atomic.Int64
}

// AddDone atomically increments the bytes-done counter.
func (o *Op) AddDone(n int64) { o.doneBytes.Add(n) }

// Activate transitions the op to the active (in-progress) state.
func (o *Op) Activate() {
	o.mu.Lock()
	defer o.mu.Unlock()
	o.status = OpActive
}

// SetQueued transitions the op to the server-queued (pending) state and resets
// the progress counter so the bar does not misleadingly show 100%.
func (o *Op) SetQueued() {
	o.mu.Lock()
	defer o.mu.Unlock()
	o.status = OpPending
	o.doneBytes.Store(0)
}

// Complete marks the op as successfully finished.
func (o *Op) Complete() {
	o.mu.Lock()
	defer o.mu.Unlock()
	o.status = OpDone
	o.doneAt = time.Now()
}

// Fail marks the op as failed with a human-readable message.
func (o *Op) Fail(msg string) {
	o.mu.Lock()
	defer o.mu.Unlock()
	o.status = OpFailed
	o.errMsg = msg
	o.doneAt = time.Now()
}

// view returns an immutable snapshot of the op's current state.
func (o *Op) view() OpView {
	o.mu.Lock()
	defer o.mu.Unlock()
	return OpView{
		ID:         o.ID,
		Kind:       o.Kind,
		Name:       o.Name,
		Status:     o.status,
		ErrMsg:     o.errMsg,
		DoneAt:     o.doneAt,
		TotalBytes: o.totalBytes,
		DoneBytes:  o.doneBytes.Load(),
	}
}

// OpView is an immutable snapshot of Op state used by the UI renderer.
type OpView struct {
	ID         string
	Kind       OpKind
	Name       string
	Status     OpStatus
	ErrMsg     string
	DoneAt     time.Time
	TotalBytes int64
	DoneBytes  int64
}

// Percent returns the completion percentage (0–100).
func (v OpView) Percent() int {
	if v.TotalBytes <= 0 {
		return 0
	}
	p := int(v.DoneBytes * 100 / v.TotalBytes)
	if p > 100 {
		p = 100
	}
	return p
}

// StatusLabel returns a short human-readable status string.
func (v OpView) StatusLabel() string {
	switch v.Status {
	case OpPending:
		return "pending"
	case OpActive:
		if v.TotalBytes > 0 {
			return fmt.Sprintf("%d%%", v.Percent())
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

// Active returns snapshots of all ops that should appear in the transfers panel.
func (s *OpsStore) Active() []OpView {
	s.mu.RLock()
	defer s.mu.RUnlock()
	now := time.Now()
	var result []OpView
	for _, op := range s.ops {
		v := op.view()
		if (v.Status == OpDone || v.Status == OpFailed) && now.Sub(v.DoneAt) > 4*time.Second {
			continue
		}
		result = append(result, v)
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
		v := op.view()
		if (v.Status == OpDone || v.Status == OpFailed) && now.Sub(v.DoneAt) > 5*time.Second {
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
		op.mu.Lock()
		if op.status == OpDone || op.status == OpFailed {
			op.mu.Unlock()
			continue
		}
		if p, ok := byPath[op.Path]; ok {
			op.pendingID = p.ID
			op.totalBytes = p.ExpectedSize
			switch p.Status {
			case "uploading":
				op.status = OpActive
			case "pending":
				op.status = OpPending
			case "failed":
				op.status = OpFailed
				op.errMsg = "upload failed on server"
				op.doneAt = time.Now()
			}
		} else {
			// No longer in the pending list — server-side upload completed.
			op.status = OpDone
			op.doneBytes.Store(op.totalBytes)
			op.doneAt = time.Now()
		}
		op.mu.Unlock()
	}
}
