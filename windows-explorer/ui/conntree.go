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

// load fetches the connection list and populates the root items.
func (m *ConnTreeModel) load() error {
	conns, err := m.api.ListConnections()
	if err != nil {
		return err
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
	m.roots = items
	m.PublishItemsReset(nil)
	return nil
}

// connLoadingItem is a read-only placeholder shown while children load.
type connLoadingItem struct{}

func (l *connLoadingItem) Text() string              { return "Loading..." }
func (l *connLoadingItem) Parent() walk.TreeItem     { return nil }
func (l *connLoadingItem) ChildCount() int           { return 0 }
func (l *connLoadingItem) ChildAt(i int) walk.TreeItem { return nil }

var loadingPlaceholder walk.TreeItem = &connLoadingItem{}

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
// Called on the UI thread; shows a "Loading..." placeholder while the load is in progress.
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
				}
				it.loaded = true
				it.loading = false
				it.model.PublishItemsReset(it)
			})
		}()
	}
	if !it.loaded {
		return 1 // show "Loading..." placeholder
	}
	return len(it.children)
}

func (it *ConnTreeItem) ChildAt(i int) walk.TreeItem {
	if !it.loaded {
		return loadingPlaceholder
	}
	if i < len(it.children) {
		return it.children[i]
	}
	return nil
}

// HasChild implements walk.HasChilder — always returns true so the tree
// shows an expand arrow before we know the actual child count.
func (it *ConnTreeItem) HasChild() bool { return true }

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
