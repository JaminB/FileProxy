// Package gui provides the native Windows GUI for FileProxy Mount.
// It uses the walk library which wraps Win32 controls directly — no browser,
// no embedded runtime, no third-party renderer.
package gui

import (
	"context"
	"fmt"
	"strings"
	"sync"

	"github.com/fileproxy/windows-mount/mountsvc"
	"github.com/lxn/walk"
	. "github.com/lxn/walk/declarative" //nolint:revive // dot-import required by walk declarative API
)

// Run opens the main window. cfg pre-fills the form; if autoStart is true the
// mount begins immediately (used when CLI args were supplied).
func Run(cfg mountsvc.Config, autoStart bool) {
	var (
		mw           *walk.MainWindow
		urlEdit      *walk.LineEdit
		keyEdit      *walk.LineEdit
		driveCombo   *walk.ComboBox
		portEdit     *walk.LineEdit
		logEdit      *walk.TextEdit
		actionBtn    *walk.PushButton
		statusBar    *walk.StatusBarItem
		ni           *walk.NotifyIcon
	)

	drives := availableDrives()
	driveIdx := driveIndex(drives, cfg.Drive)

	lw := &logWriter{}

	var (
		cancelMount context.CancelFunc
		mountMu     sync.Mutex
		mounted     bool
	)

	setMounted := func(m bool, drive string) {
		mountMu.Lock()
		mounted = m
		mountMu.Unlock()
		if m {
			actionBtn.SetText("Unmount")
			urlEdit.SetEnabled(false)
			keyEdit.SetEnabled(false)
			driveCombo.SetEnabled(false)
			portEdit.SetEnabled(false)
			statusBar.SetText(fmt.Sprintf("Drive %s: mounted", drive))
			if ni != nil {
				ni.SetToolTip(fmt.Sprintf("FileProxy Mount — %s: mounted", drive))
				ni.ShowInfo("FileProxy Mount", fmt.Sprintf("Drive %s: is now mounted.", drive))
				mw.SetVisible(false)
			}
		} else {
			actionBtn.SetText("Mount Drive")
			urlEdit.SetEnabled(true)
			keyEdit.SetEnabled(true)
			driveCombo.SetEnabled(true)
			portEdit.SetEnabled(true)
			statusBar.SetText("Not connected")
			if ni != nil {
				ni.SetToolTip("FileProxy Mount")
			}
		}
	}

	doMount := func() {
		mountMu.Lock()
		defer mountMu.Unlock()

		if mounted {
			if cancelMount != nil {
				cancelMount()
			}
			return
		}

		serverURL := strings.TrimSpace(urlEdit.Text())
		apiKey := strings.TrimSpace(keyEdit.Text())
		drive := drives[driveCombo.CurrentIndex()]
		port := 6789
		if portText := strings.TrimSpace(portEdit.Text()); portText != "" {
			var parsedPort int
			if n, err := fmt.Sscanf(portText, "%d", &parsedPort); n != 1 || err != nil || parsedPort < 1 || parsedPort > 65535 {
				walk.MsgBox(mw, "Invalid Port", "Port must be a number between 1 and 65535.", walk.MsgBoxIconWarning|walk.MsgBoxOK)
				return
			}
			port = parsedPort
		}

		if serverURL == "" {
			walk.MsgBox(mw, "Required", "Server URL cannot be empty.", walk.MsgBoxIconWarning|walk.MsgBoxOK)
			return
		}
		if apiKey == "" {
			walk.MsgBox(mw, "Required", "API Key cannot be empty.", walk.MsgBoxIconWarning|walk.MsgBoxOK)
			return
		}

		mcfg := mountsvc.Config{
			ServerURL: serverURL,
			APIKey:    apiKey,
			Drive:     drive,
			Port:      port,
		}

		lw.reset(logEdit)
		logEdit.SetText("")
		statusBar.SetText("Connecting...")

		ctx, cancel := context.WithCancel(context.Background())
		cancelMount = cancel

		go func() {
			err := mountsvc.Start(ctx, mcfg, lw, func() {
				mw.Synchronize(func() { setMounted(true, drive) })
			})
			mw.Synchronize(func() {
				mountMu.Lock()
				cancelMount = nil
				mountMu.Unlock()
				setMounted(false, drive)
				if err != nil && err != context.Canceled {
					statusBar.SetText("Error — see log")
					walk.MsgBox(mw, "Mount Error", err.Error(), walk.MsgBoxIconError|walk.MsgBoxOK)
				}
			})
		}()
	}

	urlDefault := cfg.ServerURL
	if urlDefault == "" {
		urlDefault = "http://localhost:8000"
	}

	err := MainWindow{
		AssignTo: &mw,
		Title:    "FileProxy Mount",
		Icon:     walk.IconApplication(),
		MinSize:  Size{Width: 500, Height: 520},
		Size:     Size{Width: 520, Height: 540},
		Font:     Font{Family: "Segoe UI", PointSize: 9},
		Layout:   VBox{Margins: Margins{Left: 14, Top: 14, Right: 14, Bottom: 14}, Spacing: 10},
		StatusBarItems: []StatusBarItem{
			{AssignTo: &statusBar, Text: "Not connected", Width: 400},
		},
		Children: []Widget{

			// ── Connection ────────────────────────────────────────────────
			GroupBox{
				Title:  "FileProxy Server",
				Layout: Grid{Columns: 2, Spacing: 8, Margins: Margins{Left: 8, Top: 8, Right: 8, Bottom: 8}},
				Children: []Widget{
					Label{Text: "Server URL:", TextAlignment: AlignFar},
					LineEdit{
						AssignTo: &urlEdit,
						Text:     urlDefault,
					},
					Label{Text: "API Key:", TextAlignment: AlignFar},
					LineEdit{
						AssignTo:     &keyEdit,
						PasswordMode: true,
						Text:         cfg.APIKey,
					},
				},
			},

			// ── Drive options ─────────────────────────────────────────────
			GroupBox{
				Title:  "Drive Options",
				Layout: Grid{Columns: 4, Spacing: 8, Margins: Margins{Left: 8, Top: 8, Right: 8, Bottom: 8}},
				Children: []Widget{
					Label{Text: "Drive Letter:", TextAlignment: AlignFar},
					ComboBox{
						AssignTo:     &driveCombo,
						Model:        drives,
						CurrentIndex: driveIdx,
						MaxSize:      Size{Width: 56},
					},
					Label{Text: "WebDAV Port:", TextAlignment: AlignFar},
					LineEdit{
						AssignTo: &portEdit,
						Text:     fmt.Sprintf("%d", cfg.Port),
						MaxSize:  Size{Width: 72},
					},
				},
			},

			// ── Activity log ──────────────────────────────────────────────
			GroupBox{
				Title:  "Activity",
				Layout: VBox{Margins: Margins{Left: 6, Top: 6, Right: 6, Bottom: 6}},
				Children: []Widget{
					TextEdit{
						AssignTo: &logEdit,
						ReadOnly: true,
						VScroll:  true,
						MinSize:  Size{Height: 180},
						Font:     Font{Family: "Consolas", PointSize: 9},
					},
				},
			},

			// ── Action button ─────────────────────────────────────────────
			Composite{
				Layout: HBox{MarginsZero: true},
				Children: []Widget{
					HSpacer{},
					PushButton{
						AssignTo: &actionBtn,
						Text:     "Mount Drive",
						MinSize:  Size{Width: 130, Height: 32},
						OnClicked: func() {
							doMount()
						},
					},
					HSpacer{},
				},
			},
		},
	}.Create()

	if err != nil {
		walk.MsgBox(nil, "Startup Error", err.Error(), walk.MsgBoxIconError|walk.MsgBoxOK)
		return
	}

	lw.mu.Lock()
	lw.sync = mw.Synchronize
	lw.mu.Unlock()

	// ── System tray ───────────────────────────────────────────────────────
	var niErr error
	ni, niErr = walk.NewNotifyIcon(mw)
	if niErr != nil {
		// Tray unavailable (e.g. no shell) — continue without it.
		ni = nil
	} else {
		ni.SetIcon(walk.IconApplication())
		ni.SetToolTip("FileProxy Mount")
		ni.SetVisible(true)

		showAction := walk.NewAction()
		showAction.SetText("Show")
		showAction.Triggered().Attach(func() {
			mw.SetVisible(true)
			mw.BringToTop()
		})
		ni.ContextMenu().Actions().Add(showAction)

		ni.ContextMenu().Actions().Add(walk.NewSeparatorAction())

		exitAction := walk.NewAction()
		exitAction.SetText("Exit")
		exitAction.Triggered().Attach(func() {
			mountMu.Lock()
			if cancelMount != nil {
				cancelMount()
			}
			mountMu.Unlock()
			mw.Close()
		})
		ni.ContextMenu().Actions().Add(exitAction)

		ni.MouseDown().Attach(func(x, y int, button walk.MouseButton) {
			if button == walk.LeftButton {
				mw.SetVisible(true)
				mw.BringToTop()
			}
		})
	}

	// Closing the window hides to tray while mounted; exits otherwise.
	mw.Closing().Attach(func(canceled *bool, reason walk.CloseReason) {
		mountMu.Lock()
		isMounted := mounted
		mountMu.Unlock()
		if isMounted {
			mw.SetVisible(false)
			*canceled = true
		}
	})

	if autoStart {
		doMount()
	}

	mw.Run()

	// Cleanup on exit
	mountMu.Lock()
	if cancelMount != nil {
		cancelMount()
	}
	mountMu.Unlock()
	if ni != nil {
		ni.Dispose()
	}
}

// availableDrives returns the drive letters D–Z as options.
func availableDrives() []string {
	drives := make([]string, 0, 23)
	for c := 'D'; c <= 'Z'; c++ {
		drives = append(drives, string(c))
	}
	return drives
}

func driveIndex(drives []string, letter string) int {
	letter = strings.ToUpper(strings.TrimSuffix(letter, ":"))
	for i, d := range drives {
		if d == letter {
			return i
		}
	}
	// Default to F
	for i, d := range drives {
		if d == "F" {
			return i
		}
	}
	return 0
}

// logWriter is an io.Writer that appends text to a walk TextEdit, safe to
// use from any goroutine. Each Write appends only the new chunk via AppendText
// so the cost per write is O(chunk) rather than O(total log size).
type logWriter struct {
	mu   sync.Mutex
	te   *walk.TextEdit
	sync func(func())
}

func (w *logWriter) reset(te *walk.TextEdit) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.te = te
}

func (w *logWriter) Write(p []byte) (int, error) {
	w.mu.Lock()
	te := w.te
	syncFn := w.sync
	w.mu.Unlock()

	if te != nil && syncFn != nil {
		text := string(p)
		syncFn(func() {
			te.AppendText(text)
		})
	}
	return len(p), nil
}
