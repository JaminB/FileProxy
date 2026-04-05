// Package ui provides the native Windows GUI for FileProxy Explorer.
// It uses the walk library which wraps Win32 controls directly.
package ui

import (
	"bytes"
	"context"
	"fmt"
	"image"
	_ "image/png"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"
	"unsafe"

	"github.com/lxn/walk"
	. "github.com/lxn/walk/declarative" //nolint:revive // dot-import required by walk declarative API

	"github.com/fileproxy/windows-explorer/client"
	"github.com/fileproxy/windows-explorer/config"
)

// ── Windows API ───────────────────────────────────────────────────────────────

var (
	shell32          = syscall.NewLazyDLL("shell32.dll")
	procShellExecute = shell32.NewProc("ShellExecuteW")
	kernel32         = syscall.NewLazyDLL("kernel32.dll")
	freeConsole      = kernel32.NewProc("FreeConsole")
)

func shellOpen(path string) {
	p, _ := syscall.UTF16PtrFromString(path)
	op, _ := syscall.UTF16PtrFromString("open")
	procShellExecute.Call(0, uintptr(unsafe.Pointer(op)), uintptr(unsafe.Pointer(p)), 0, 0, 1)
}

// ── Op row widgets (transfers panel) ─────────────────────────────────────────

const maxOpRows = 8

type opRow struct {
	composite *walk.Composite
	nameLabel *walk.Label
	bar       *walk.ProgressBar
	statLabel *walk.Label
	opID      string
	doneAt    time.Time
}

// ── App ───────────────────────────────────────────────────────────────────────

// App coordinates all UI state: client, current location, models, ops.
type App struct {
	api   *client.Client
	cfg   config.Config
	cfgMu sync.Mutex
	ops   OpsStore

	// conn and prefix are the current navigation location.
	// Written on the UI thread; read from background goroutines under connMu.
	connMu        sync.RWMutex
	conn          string // current connection name ("" = none)
	prefix        string // current path prefix within conn
	exitRequested bool   // set before Close() to allow real exit

	mw          *walk.MainWindow
	treeView    *walk.TreeView
	tableView   *walk.TableView
	addrEdit    *walk.LineEdit
	statusLeft  *walk.StatusBarItem
	statusRight *walk.StatusBarItem
	ni          *walk.NotifyIcon

	treeModel  *ConnTreeModel
	tableModel *FileTableModel

	opRows [maxOpRows]opRow

	loadMu sync.Mutex
	ctx    context.Context
	cancel context.CancelFunc
}

// ── Entry point ───────────────────────────────────────────────────────────────

// ShowSettingsDialog opens a modal dialog that lets the user enter the server URL
// and API key. Returns the updated config and whether the user accepted.
func ShowSettingsDialog(parent walk.Form, cfg config.Config) (config.Config, bool) {
	var dlg *walk.Dialog
	var urlEdit, keyEdit *walk.LineEdit

	cmd, err := Dialog{
		AssignTo:  &dlg,
		Title:     "FileProxy Explorer — Settings",
		MinSize:   Size{Width: 440, Height: 180},
		Layout:    VBox{Margins: Margins{Left: 14, Top: 14, Right: 14, Bottom: 14}, Spacing: 8},
		Children: []Widget{
			Label{Text: "Server URL (e.g. https://fileproxy.example.com):"},
			LineEdit{AssignTo: &urlEdit, Text: cfg.ServerURL},
			Label{Text: "API Key:"},
			LineEdit{AssignTo: &keyEdit, PasswordMode: true, Text: cfg.APIKey},
			Composite{
				Layout: HBox{MarginsZero: true},
				Children: []Widget{
					HSpacer{},
					PushButton{
						Text:    "Save",
						MinSize: Size{Width: 80},
						OnClicked: func() {
							cfg.ServerURL = strings.TrimSpace(urlEdit.Text())
							cfg.APIKey = strings.TrimSpace(keyEdit.Text())
							dlg.Accept()
						},
					},
					PushButton{
						Text:      "Cancel",
						MinSize:   Size{Width: 80},
						OnClicked: func() { dlg.Cancel() },
					},
				},
			},
		},
	}.Run(parent)

	if err != nil || cmd != walk.DlgCmdOK {
		return cfg, false
	}
	return cfg, true
}

// FreeConsole detaches from the Windows console to suppress the terminal
// that appears when the .exe is double-clicked. Call once at startup.
func FreeConsole() { freeConsole.Call() }

// Run creates and runs the main application window. Blocks until the window closes.
func Run(api *client.Client, cfg config.Config) {

	app := &App{
		api:        api,
		cfg:        cfg,
		treeModel:  newConnTreeModel(api),
		tableModel: newFileTableModel(),
	}
	app.ctx, app.cancel = context.WithCancel(context.Background())

	winIcon := loadIcon(logoLightBytes)
	trayIcon := loadIcon(logoDarkBytes)

	// Build op-row widget specs (pre-allocated, initially hidden).
	opRowWidgets := make([]Widget, maxOpRows)
	for i := range app.opRows {
		i := i
		opRowWidgets[i] = Composite{
			AssignTo: &app.opRows[i].composite,
			Visible:  false,
			Layout:   HBox{MarginsZero: true, Spacing: 6},
			Children: []Widget{
				Label{
					AssignTo: &app.opRows[i].nameLabel,
					MinSize:  Size{Width: 180},
					MaxSize:  Size{Width: 180},
				},
				ProgressBar{
					AssignTo:      &app.opRows[i].bar,
					MinSize:       Size{Width: 80},
					MaxSize:       Size{Width: 9999},
					StretchFactor: 1,
				},
				Label{
					AssignTo: &app.opRows[i].statLabel,
					MinSize:  Size{Width: 90},
				},
			},
		}
	}

	err := MainWindow{
		AssignTo: &app.mw,
		Title:    "FileProxy Explorer",
		Icon:     winIcon,
		MinSize:  Size{Width: 900, Height: 600},
		Size:     Size{Width: 1100, Height: 700},
		Font:     Font{Family: "Segoe UI", PointSize: 9},
		MenuItems: []MenuItem{
			Menu{
				Text: "&File",
				Items: []MenuItem{
					Action{Text: "&Settings...", OnTriggered: func() {
						app.cfgMu.Lock()
						oldCfg := app.cfg
						app.cfgMu.Unlock()
						newCfg, ok := ShowSettingsDialog(app.mw, oldCfg)
						if ok {
							app.cfgMu.Lock()
							app.cfg = newCfg
							app.cfgMu.Unlock()
							config.Save(newCfg)
							// Don't swap app.api — background goroutines hold references to
							// it and a concurrent pointer write would be a data race. Server
							// and API-key changes take effect on the next launch.
							if newCfg.ServerURL != oldCfg.ServerURL || newCfg.APIKey != oldCfg.APIKey {
								walk.MsgBox(app.mw, "Restart required",
									"Server URL or API key changed.\nRestart FileProxy Explorer to connect with the new settings.",
									walk.MsgBoxIconInformation|walk.MsgBoxOK)
							}
						}
					}},
					Separator{},
					Action{Text: "E&xit", OnTriggered: func() {
						app.exitRequested = true
						app.mw.Close()
					}},
				},
			},
		},
		StatusBarItems: []StatusBarItem{
			{AssignTo: &app.statusLeft, Text: "Loading...", Width: 600},
			{AssignTo: &app.statusRight, Text: "", Width: 200},
		},
		Layout: VBox{Margins: Margins{Left: 0, Top: 4, Right: 0, Bottom: 0}, Spacing: 0},
		Children: []Widget{

			// ── Toolbar ──────────────────────────────────────────────────────
			Composite{
				Layout: HBox{Margins: Margins{Left: 6, Top: 4, Right: 6, Bottom: 4}, Spacing: 4},
				Children: []Widget{
					PushButton{Text: "⬆ Up", MinSize: Size{Width: 60}, OnClicked: func() { app.doUp() }},
					PushButton{Text: "↓ Download", MinSize: Size{Width: 90}, OnClicked: func() { app.doDownload() }},
					PushButton{Text: "⬆ Upload", MinSize: Size{Width: 80}, OnClicked: func() { app.doUpload() }},
					PushButton{Text: "✕ Delete", MinSize: Size{Width: 70}, OnClicked: func() { app.doDelete() }},
					PushButton{Text: "↺ Refresh", MinSize: Size{Width: 80}, OnClicked: func() { app.doRefresh() }},
					HSpacer{},
				},
			},

			// ── Address bar ───────────────────────────────────────────────────
			Composite{
				Layout: HBox{Margins: Margins{Left: 6, Top: 2, Right: 6, Bottom: 2}, Spacing: 4},
				Children: []Widget{
					Label{Text: "Location:"},
					LineEdit{
						AssignTo: &app.addrEdit,
						Text:     "",
						OnKeyDown: func(key walk.Key) {
							if key == walk.KeyReturn {
								app.navigateToAddress()
							}
						},
					},
					PushButton{Text: "Go", MinSize: Size{Width: 40}, OnClicked: func() {
						app.navigateToAddress()
					}},
				},
			},

			// ── Main split pane ───────────────────────────────────────────────
			HSplitter{
				StretchFactor: 1,
				Children: []Widget{
					TreeView{
						AssignTo: &app.treeView,
						Model:    app.treeModel,
						MinSize:  Size{Width: 220},
						MaxSize:  Size{Width: 400},
					},
					TableView{
						AssignTo:         &app.tableView,
						Model:            app.tableModel,
						AlternatingRowBG: true,
						Columns: []TableViewColumn{
							{Title: "Name", Width: 360},
							{Title: "Size", Width: 80},
							{Title: "Modified", Width: 140},
						},
					},
				},
			},

			// ── Transfers panel ───────────────────────────────────────────────
			GroupBox{
				Title:   "Transfers",
				MaxSize: Size{Height: 200},
				Layout:  VBox{Margins: Margins{Left: 6, Top: 4, Right: 6, Bottom: 4}, Spacing: 3},
				Children: opRowWidgets,
			},
		},
	}.Create()

	if err != nil {
		walk.MsgBox(nil, "Startup Error", err.Error(), walk.MsgBoxIconError|walk.MsgBoxOK)
		return
	}

	// Wire up the main window reference for async tree loading.
	app.treeModel.mw = app.mw

	// ── TreeView selection changes navigation ─────────────────────────────────
	app.treeView.CurrentItemChanged().Attach(func() {
		item, ok := app.treeView.CurrentItem().(*ConnTreeItem)
		if !ok || item == nil {
			return
		}
		app.navigateTo(item.conn, item.prefix)
	})

	// ── TableView double-click activates folders or files ─────────────────────
	app.tableView.ItemActivated().Attach(func() {
		idx := app.tableView.CurrentIndex()
		entry := app.tableModel.EntryAt(idx)
		if entry == nil {
			return
		}
		if entry.IsFolder {
			app.navigateTo(app.conn, entry.FullPath)
		} else {
			app.openFile(entry)
		}
	})

	// ── System tray ───────────────────────────────────────────────────────────
	if ni, niErr := walk.NewNotifyIcon(app.mw); niErr == nil {
		app.ni = ni
		ni.SetIcon(trayIcon)
		ni.SetToolTip("FileProxy Explorer")
		ni.SetVisible(true)

		showAct := walk.NewAction()
		showAct.SetText("Show")
		showAct.Triggered().Attach(func() {
			app.mw.SetVisible(true)
			app.mw.BringToTop()
		})
		ni.ContextMenu().Actions().Add(showAct)
		ni.ContextMenu().Actions().Add(walk.NewSeparatorAction())

		exitAct := walk.NewAction()
		exitAct.SetText("Exit")
		exitAct.Triggered().Attach(func() {
			app.exitRequested = true
			app.mw.Close()
		})
		ni.ContextMenu().Actions().Add(exitAct)

		ni.MouseDown().Attach(func(x, y int, button walk.MouseButton) {
			if button == walk.LeftButton {
				app.mw.SetVisible(true)
				app.mw.BringToTop()
			}
		})

		app.mw.Closing().Attach(func(canceled *bool, reason walk.CloseReason) {
			if app.exitRequested {
				// Real exit requested — allow the window to close.
				return
			}
			// Otherwise minimise to tray.
			app.mw.SetVisible(false)
			*canceled = true
		})
	}

	// ── Background goroutines ─────────────────────────────────────────────────
	go app.transferRefreshLoop()
	go app.pendingPollLoop()

	// Initial connection load.
	app.reloadConnections()

	app.mw.Run()

	app.cancel()
	if app.ni != nil {
		app.ni.Dispose()
	}
}

// ── Navigation ────────────────────────────────────────────────────────────────

func (app *App) navigateTo(conn, prefix string) {
	app.connMu.Lock()
	app.conn = conn
	app.prefix = prefix
	app.connMu.Unlock()

	addr := conn
	if prefix != "" {
		addr += "/" + strings.TrimSuffix(prefix, "/")
	}
	app.mw.Synchronize(func() {
		app.addrEdit.SetText(addr)
		app.setStatus("Loading...", "")
	})
	go app.reloadFileTable()
}

func (app *App) navigateToAddress() {
	addr := strings.TrimSpace(app.addrEdit.Text())
	if addr == "" {
		return
	}
	parts := strings.SplitN(addr, "/", 2)
	conn := parts[0]
	prefix := ""
	if len(parts) == 2 && parts[1] != "" {
		prefix = parts[1] + "/"
	}
	app.navigateTo(conn, prefix)
}

func (app *App) doUp() {
	if app.conn == "" {
		return
	}
	if app.prefix == "" {
		// Already at root — do nothing.
		return
	}
	// Strip the trailing slash, then strip the last component.
	p := strings.TrimSuffix(app.prefix, "/")
	idx := strings.LastIndex(p, "/")
	newPrefix := ""
	if idx >= 0 {
		newPrefix = p[:idx+1]
	}
	app.navigateTo(app.conn, newPrefix)
}

func (app *App) doRefresh() {
	if app.conn == "" {
		app.reloadConnections()
		return
	}
	go app.reloadFileTable()
}

// ── Data loading ──────────────────────────────────────────────────────────────

func (app *App) reloadConnections() {
	app.setStatus("Loading connections...", "")
	go func() {
		if err := app.treeModel.load(); err != nil {
			app.mw.Synchronize(func() {
				app.setStatus("Error loading connections: "+err.Error(), "")
			})
			return
		}
		app.mw.Synchronize(func() {
			app.setStatus(fmt.Sprintf("%d connections", app.treeModel.RootCount()), "")
		})
	}()
}

func (app *App) reloadFileTable() {
	app.connMu.RLock()
	conn := app.conn
	prefix := app.prefix
	app.connMu.RUnlock()

	if conn == "" {
		return
	}
	app.loadMu.Lock()
	defer app.loadMu.Unlock()

	app.mw.Synchronize(func() { app.setStatus("Loading...", "") })

	objects, err := app.api.Enumerate(conn, prefix)
	if err != nil {
		app.mw.Synchronize(func() {
			app.setStatus("Error: "+err.Error(), "")
		})
		return
	}
	app.mw.Synchronize(func() {
		app.tableModel.Reload(objects, prefix)
		app.setStatus(fmt.Sprintf("%d items", app.tableModel.RowCount()), "Ready")
	})
}

// ── File operations ───────────────────────────────────────────────────────────

func (app *App) doDownload() {
	idx := app.tableView.CurrentIndex()
	entry := app.tableModel.EntryAt(idx)
	if entry == nil || entry.IsFolder {
		return
	}

	dlg := new(walk.FileDialog)
	dlg.Title = "Save As"
	dlg.Filter = "All Files (*.*)|*.*"
	dlg.FilePath = entry.Name
	ok, err := dlg.ShowSave(app.mw)
	if err != nil || !ok {
		return
	}
	savePath := dlg.FilePath

	size := int64(-1)
	if entry.Size != nil {
		size = *entry.Size
	}
	op := &Op{
		ID:   fmt.Sprintf("dl-%d", time.Now().UnixNano()),
		Kind: OpDownload,
		Conn: app.conn,
		Path: entry.FullPath,
		Name: entry.Name,
	}
	op.totalBytes = size
	op.status = OpActive
	app.ops.Add(op)

	go func() {
		body, _, dlErr := app.api.Download(op.Conn, op.Path)
		if dlErr != nil {
			op.Fail(dlErr.Error())
			app.mw.Synchronize(func() {
				walk.MsgBox(app.mw, "Download Error", dlErr.Error(), walk.MsgBoxIconError|walk.MsgBoxOK)
			})
			return
		}
		defer body.Close()

		f, createErr := os.Create(savePath)
		if createErr != nil {
			op.Fail(createErr.Error())
			return
		}
		defer f.Close()

		// Copy with progress tracking.
		buf := make([]byte, 32*1024)
		for {
			n, readErr := body.Read(buf)
			if n > 0 {
				if _, wErr := f.Write(buf[:n]); wErr != nil {
					op.Fail(wErr.Error())
					return
				}
				op.AddDone(int64(n))
			}
			if readErr == io.EOF {
				break
			}
			if readErr != nil {
				op.Fail(readErr.Error())
				return
			}
		}
		op.Complete()
	}()
}

func (app *App) openFile(entry *FileEntry) {
	// Capture conn before creating the op so the goroutine uses a stable value.
	op := &Op{
		ID:   fmt.Sprintf("open-%d", time.Now().UnixNano()),
		Kind: OpDownload,
		Conn: app.conn,
		Path: entry.FullPath,
		Name: entry.Name,
	}
	size := int64(-1)
	if entry.Size != nil {
		size = *entry.Size
	}
	op.totalBytes = size
	op.status = OpActive

	// Download to a temp location and open with default app.
	tmpDir := filepath.Join(os.TempDir(), "fileproxy-explorer", op.Conn)
	if mkErr := os.MkdirAll(tmpDir, 0700); mkErr != nil {
		return
	}
	tmpPath := filepath.Join(tmpDir, entry.Name)

	app.ops.Add(op)

	go func() {
		body, _, dlErr := app.api.Download(op.Conn, op.Path)
		if dlErr != nil {
			op.Fail(dlErr.Error())
			return
		}
		defer body.Close()

		f, createErr := os.Create(tmpPath)
		if createErr != nil {
			op.Fail(createErr.Error())
			return
		}
		defer f.Close()

		buf := make([]byte, 32*1024)
		for {
			n, readErr := body.Read(buf)
			if n > 0 {
				if _, wErr := f.Write(buf[:n]); wErr != nil {
					op.Fail(wErr.Error())
					return
				}
				op.AddDone(int64(n))
			}
			if readErr == io.EOF {
				break
			}
			if readErr != nil {
				op.Fail(readErr.Error())
				return
			}
		}
		op.Complete()
		shellOpen(tmpPath)
	}()
}

func (app *App) doUpload() {
	if app.conn == "" {
		walk.MsgBox(app.mw, "Upload", "Select a connection first.", walk.MsgBoxIconWarning|walk.MsgBoxOK)
		return
	}
	dlg := new(walk.FileDialog)
	dlg.Title = "Upload File"
	dlg.Filter = "All Files (*.*)|*.*"
	ok, err := dlg.ShowOpen(app.mw)
	if err != nil || !ok {
		return
	}
	localPath := dlg.FilePath
	filename := filepath.Base(localPath)
	remotePath := app.prefix + filename

	fi, statErr := os.Stat(localPath)
	if statErr != nil {
		return
	}
	size := fi.Size()

	op := &Op{
		ID:   fmt.Sprintf("ul-%d", time.Now().UnixNano()),
		Kind: OpUpload,
		Conn: app.conn,
		Path: remotePath,
		Name: filename,
	}
	op.totalBytes = size
	op.status = OpPending
	app.ops.Add(op)

	go func() {
		f, openErr := os.Open(localPath)
		if openErr != nil {
			op.Fail(openErr.Error())
			return
		}
		defer f.Close()

		// Wrap with counting reader to track progress.
		pr := &progressReader{r: f, op: op}
		op.Activate()

		queued, upErr := app.api.Upload(op.Conn, op.Path, pr)
		if upErr != nil {
			op.Fail(upErr.Error())
			return
		}
		if queued {
			// Server queued the upload — switch to pending state and reset
			// the progress bar so it doesn't misleadingly show 100%.
			op.SetQueued()
			// pendingPollLoop will update status as the server processes it.
		} else {
			op.Complete()
			// Reload the file list to show the new file.
			app.mw.Synchronize(func() { go app.reloadFileTable() })
		}
	}()
}

func (app *App) doDelete() {
	idx := app.tableView.CurrentIndex()
	entry := app.tableModel.EntryAt(idx)
	if entry == nil || entry.IsFolder {
		return
	}
	conn := app.conn // capture before goroutine to avoid stale read
	msg := fmt.Sprintf("Delete %q from %q?", entry.Name, conn)
	if walk.MsgBox(app.mw, "Confirm Delete", msg, walk.MsgBoxIconWarning|walk.MsgBoxYesNo) != walk.DlgCmdYes {
		return
	}
	app.setStatus("Deleting "+entry.Name+"...", "")
	go func() {
		if err := app.api.Delete(conn, entry.FullPath); err != nil {
			app.mw.Synchronize(func() {
				app.setStatus("Delete failed: "+err.Error(), "")
				walk.MsgBox(app.mw, "Delete Error", err.Error(), walk.MsgBoxIconError|walk.MsgBoxOK)
			})
			return
		}
		app.mw.Synchronize(func() {
			go app.reloadFileTable()
		})
	}()
}

// ── Transfers panel refresh ───────────────────────────────────────────────────

// transferRefreshLoop updates the transfers panel every 500 ms.
func (app *App) transferRefreshLoop() {
	tick := time.NewTicker(500 * time.Millisecond)
	defer tick.Stop()
	for {
		select {
		case <-app.ctx.Done():
			return
		case <-tick.C:
			app.ops.Prune()
			views := app.ops.Active()
			app.mw.Synchronize(func() { app.renderOpsPanel(views) })
		}
	}
}

func (app *App) renderOpsPanel(views []OpView) {
	for i := range app.opRows {
		row := &app.opRows[i]
		if i < len(views) {
			v := views[i]
			row.opID = v.ID

			// Name label — trim if too long.
			name := v.Name
			if len(name) > 28 {
				name = "..." + name[len(name)-25:]
			}
			row.nameLabel.SetText(name)

			// Progress bar
			row.bar.SetRange(0, 100)
			if v.TotalBytes > 0 {
				row.bar.SetMarqueeMode(false)
				row.bar.SetValue(v.Percent())
			} else {
				row.bar.SetMarqueeMode(v.Status == OpActive)
				row.bar.SetValue(0)
			}

			// Status label
			var stat string
			switch v.Status {
			case OpPending:
				stat = "pending"
			case OpActive:
				if v.TotalBytes > 0 {
					stat = fmt.Sprintf("%d%%", v.Percent())
				} else {
					stat = string(v.Kind)
				}
			case OpDone:
				stat = "✓ done"
			case OpFailed:
				stat = "✗ " + v.ErrMsg
				if len(stat) > 20 {
					stat = stat[:20] + "..."
				}
			}
			row.statLabel.SetText(stat)
			row.composite.SetVisible(true)
		} else {
			row.opID = ""
			row.composite.SetVisible(false)
		}
	}
}

// pendingPollLoop polls the server's pending/ endpoint every 2 seconds
// to sync server-side upload queue status.
func (app *App) pendingPollLoop() {
	tick := time.NewTicker(2 * time.Second)
	defer tick.Stop()
	for {
		select {
		case <-app.ctx.Done():
			return
		case <-tick.C:
			app.connMu.RLock()
			conn := app.conn
			app.connMu.RUnlock()
			if conn == "" {
				continue
			}
			pending, err := app.api.PendingUploads(conn)
			if err != nil {
				continue
			}
			app.ops.SyncWithPending(conn, pending)
		}
	}
}

// ── Status bar ────────────────────────────────────────────────────────────────

func (app *App) setStatus(left, right string) {
	app.statusLeft.SetText(left)
	if right != "" {
		app.statusRight.SetText(right)
	}
}

// ── Icon helpers ──────────────────────────────────────────────────────────────

func loadIcon(data []byte) *walk.Icon {
	img, _, err := image.Decode(bytes.NewReader(data))
	if err != nil {
		return walk.IconApplication()
	}
	ico, err := walk.NewIconFromImage(img)
	if err != nil {
		return walk.IconApplication()
	}
	return ico
}

// ── progressReader wraps an io.Reader and updates an Op as bytes are read ─────

type progressReader struct {
	r  io.Reader
	op *Op
}

func (pr *progressReader) Read(p []byte) (int, error) {
	n, err := pr.r.Read(p)
	if n > 0 {
		pr.op.AddDone(int64(n))
	}
	return n, err
}
