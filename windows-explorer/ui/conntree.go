//go:build windows

package ui

import (
	"strings"

	"github.com/lxn/walk"

	"github.com/fileproxy/windows-explorer/client"
)

// ConnTreeModel implements walk.TreeModel for the left-pane connection tree.
// Top-level items are connections; child items are virtual folders discovered
// by enumerating objects and grouping by path separators.
type ConnTreeModel struct {
	walk.TreeModelBase
	api   *client.Client
	mw    *walk.MainWindow // set after window creation; used for Synchronize in async loads
	roots []*ConnTreeItem
}

func newConnTreeModel(api *client.Client) *ConnTreeModel {
	return &ConnTreeModel{api: api}
}

func (m *ConnTreeModel) LazyPopulation() bool       { return true }
func (m *ConnTreeModel) RootCount() int             { return len(m.roots) }
func (m *ConnTreeModel) RootAt(i int) walk.TreeItem { return m.roots[i] }

// fetchConnections does the network call and returns tree items.
// Safe to call off the UI thread — does not touch walk.
func (m *ConnTreeModel) fetchConnections() ([]*ConnTreeItem, error) {
	conns, err := m.api.ListConnections()
	if err != nil {
		return nil, err
	}
	items := make([]*ConnTreeItem, len(conns))
	for i, c := range conns {
		items[i] = &ConnTreeItem{
			model:  m,
			parent: nil,
			conn:   c.Name,
			prefix: "",
			name:   c.Name,
		}
	}
	return items, nil
}

// applyConnections sets the root items and notifies the TreeView.
// Must be called on the UI thread (inside mw.Synchronize).
func (m *ConnTreeModel) applyConnections(items []*ConnTreeItem) {
	m.roots = items
	m.PublishItemsReset(nil)
}

// ConnTreeItem is a node in the connection tree (either a connection root or a virtual folder).
type ConnTreeItem struct {
	model    *ConnTreeModel
	parent   *ConnTreeItem
	conn     string // owning connection name
	prefix   string // full path prefix for this node (e.g. "folder/sub/")
	name     string // display name
	children []*ConnTreeItem
	loaded   bool
	loading  bool // async load in progress
}

func (it *ConnTreeItem) Text() string { return it.name }

func (it *ConnTreeItem) Parent() walk.TreeItem {
	if it.parent == nil {
		return nil
	}
	return it.parent
}

// ChildCount returns the number of children, kicking off an async load if needed.
// Returns 0 while loading — walk must not try to insert children until the load
// completes and PublishItemsReset fires on the UI thread.
func (it *ConnTreeItem) ChildCount() int {
	if !it.loaded && !it.loading {
		it.loading = true
		conn := it.conn
		prefix := it.prefix
		go func() {
			objects, err := it.model.api.Enumerate(conn, prefix)
			it.model.mw.Synchronize(func() {
				if err == nil {
					it.buildChildren(objects)
					it.loaded = true
				}
				// On error, keep loaded=false so the next expand triggers a retry.
				it.loading = false
				it.model.PublishItemsReset(it)
			})
		}()
	}
	if !it.loaded {
		return 0
	}
	return len(it.children)
}

func (it *ConnTreeItem) ChildAt(i int) walk.TreeItem {
	if i < len(it.children) {
		return it.children[i]
	}
	return nil
}

// HasChild implements walk.HasChilder.
// Returns true until the item is loaded (so the expand arrow appears), then
// returns the accurate value so empty connections don't show a stale arrow.
func (it *ConnTreeItem) HasChild() bool {
	if !it.loaded {
		return true
	}
	return len(it.children) > 0
}

// buildChildren constructs the virtual folder children from a flat object list.
// Must be called on the UI thread (inside mw.Synchronize).
func (it *ConnTreeItem) buildChildren(objects []client.Object) {
	seen := map[string]bool{}
	var children []*ConnTreeItem
	for _, obj := range objects {
		rel := strings.TrimPrefix(obj.Path, it.prefix)
		rel = strings.TrimPrefix(rel, "/")
		idx := strings.Index(rel, "/")
		if idx == -1 {
			continue // file, not a folder
		}
		folderName := rel[:idx]
		childPrefix := it.prefix + folderName + "/"
		if seen[childPrefix] {
			continue
		}
		seen[childPrefix] = true
		children = append(children, &ConnTreeItem{
			model:  it.model,
			parent: it,
			conn:   it.conn,
			prefix: childPrefix,
			name:   folderName,
		})
	}
	it.children = children
}
