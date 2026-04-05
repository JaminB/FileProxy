//go:build windows

package ui

import (
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/lxn/walk"

	"github.com/fileproxy/windows-explorer/client"
)

// FileEntry is one row in the file list table.
type FileEntry struct {
	IsFolder     bool
	Name         string // display name (just the filename or folder name)
	FullPath     string // full path for API calls
	Size         *int64
	LastModified *time.Time
}

// FileTableModel implements walk.TableModel and walk.Sorter for the right-pane file list.
type FileTableModel struct {
	walk.TableModelBase
	walk.SorterBase
	entries []*FileEntry
}

func newFileTableModel() *FileTableModel {
	return &FileTableModel{}
}

func (m *FileTableModel) RowCount() int { return len(m.entries) }

func (m *FileTableModel) Value(row, col int) interface{} {
	if row < 0 || row >= len(m.entries) {
		return ""
	}
	e := m.entries[row]
	switch col {
	case 0: // Name
		if e.IsFolder {
			return "\U0001F4C1 " + e.Name
		}
		return "\U0001F4C4 " + e.Name
	case 1: // Size
		if e.IsFolder || e.Size == nil {
			return ""
		}
		return formatSize(*e.Size)
	case 2: // Modified
		if e.LastModified == nil {
			return ""
		}
		return e.LastModified.Format("2006-01-02 15:04")
	}
	return ""
}

// Sort implements walk.Sorter so column header clicks sort the table.
func (m *FileTableModel) Sort(col int, order walk.SortOrder) error {
	m.sortEntries(col, order)
	m.PublishRowsReset()
	return m.SorterBase.Sort(col, order)
}

func (m *FileTableModel) sortEntries(col int, order walk.SortOrder) {
	asc := order == walk.SortAscending
	sort.SliceStable(m.entries, func(i, j int) bool {
		a, b := m.entries[i], m.entries[j]
		// Folders always come first regardless of sort column.
		if a.IsFolder != b.IsFolder {
			return a.IsFolder
		}
		var less bool
		switch col {
		case 1: // Size
			sa, sb := int64(0), int64(0)
			if a.Size != nil {
				sa = *a.Size
			}
			if b.Size != nil {
				sb = *b.Size
			}
			less = sa < sb
		case 2: // Modified
			ta := time.Time{}
			tb := time.Time{}
			if a.LastModified != nil {
				ta = *a.LastModified
			}
			if b.LastModified != nil {
				tb = *b.LastModified
			}
			less = ta.Before(tb)
		default: // Name
			less = strings.ToLower(a.Name) < strings.ToLower(b.Name)
		}
		if asc {
			return less
		}
		return !less
	})
}

// EntryAt returns the entry at the given row, or nil.
func (m *FileTableModel) EntryAt(row int) *FileEntry {
	if row < 0 || row >= len(m.entries) {
		return nil
	}
	return m.entries[row]
}

// Reload rebuilds the entry list from all objects returned for conn/prefix.
func (m *FileTableModel) Reload(objects []client.Object, prefix string) {
	seen := map[string]bool{}
	var folders, files []*FileEntry

	for _, obj := range objects {
		rel := strings.TrimPrefix(obj.Path, prefix)
		rel = strings.TrimPrefix(rel, "/")
		if rel == "" {
			continue
		}
		idx := strings.Index(rel, "/")
		if idx == -1 {
			// Direct file at this level
			var lm *time.Time
			if obj.LastModified != nil {
				t, err := time.Parse(time.RFC3339Nano, *obj.LastModified)
				if err == nil {
					lm = &t
				}
			}
			files = append(files, &FileEntry{
				IsFolder:     false,
				Name:         rel,
				FullPath:     obj.Path,
				Size:         obj.Size,
				LastModified: lm,
			})
		} else {
			// Virtual folder from first path component
			folderName := rel[:idx]
			folderPath := prefix + folderName + "/"
			if !seen[folderPath] {
				seen[folderPath] = true
				folders = append(folders, &FileEntry{
					IsFolder: true,
					Name:     folderName,
					FullPath: folderPath,
				})
			}
		}
	}

	sort.Slice(folders, func(i, j int) bool {
		return strings.ToLower(folders[i].Name) < strings.ToLower(folders[j].Name)
	})
	sort.Slice(files, func(i, j int) bool {
		return strings.ToLower(files[i].Name) < strings.ToLower(files[j].Name)
	})

	m.entries = append(folders, files...)
	m.PublishRowsReset()
}

func formatSize(n int64) string {
	switch {
	case n < 1024:
		return fmt.Sprintf("%d B", n)
	case n < 1024*1024:
		return fmt.Sprintf("%.1f KB", float64(n)/1024)
	case n < 1024*1024*1024:
		return fmt.Sprintf("%.1f MB", float64(n)/(1024*1024))
	default:
		return fmt.Sprintf("%.2f GB", float64(n)/(1024*1024*1024))
	}
}
