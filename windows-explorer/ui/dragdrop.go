//go:build windows

package ui

// OLE drag-and-drop support.
//
// Drop IN  — IDropTarget registered on the TableView.
//            Files dragged from Windows Explorer are uploaded to the current
//            connection and prefix.
//
// Drag OUT — IDataObject + IDropSource exposed when the user drags a row out
//            of the TableView.  The remote file is downloaded to a temp
//            directory at drop time (inside IDataObject::GetData) so the drag
//            cursor responds instantly; only a brief UI freeze occurs when the
//            user releases the mouse over a target.

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"time"
	"unsafe"

	"github.com/lxn/walk"
	"github.com/lxn/win"
)

// ── Constants ─────────────────────────────────────────────────────────────────

const (
	dropEffectNone = uint32(0)
	dropEffectCopy = uint32(1)

	dvaspectContent = uint32(1)
	tymedHGlobal    = uint32(1)
	cfHDrop         = uint16(15)

	gmemZeroed = uintptr(0x0040) // GMEM_FIXED | GMEM_ZEROINIT

	dragDropSDrop   = uintptr(0x00040100)
	dragDropSCancel = uintptr(0x00040101)
	dragDropSUseDefaultCursors = uintptr(0x00040102)

	eNotImpl     = uintptr(0x80004001)
	eNoInterface = uintptr(0x80004002)
	eFail        = uintptr(0x80004005)
	dvEFormatEtc = uintptr(0x80040064)

	sOK = uintptr(0)

	// Drag threshold: squared pixel distance before a mouse-move is a drag.
	dragThreshSq = int32(5 * 5)
)

// ── DLL / proc references ─────────────────────────────────────────────────────
// shell32 and kernel32 are declared in mainwindow.go (same package).

var (
	ole32dll = syscall.NewLazyDLL("ole32.dll")

	procOleInitialize    = ole32dll.NewProc("OleInitialize")
	procOleUninitialize  = ole32dll.NewProc("OleUninitialize")
	procRegisterDragDrop = ole32dll.NewProc("RegisterDragDrop")
	procRevokeDragDrop   = ole32dll.NewProc("RevokeDragDrop")
	procReleaseStgMedium = ole32dll.NewProc("ReleaseStgMedium")
	procDoDragDrop       = ole32dll.NewProc("DoDragDrop")

	procDragQueryFileW = shell32.NewProc("DragQueryFileW")
	procGlobalAlloc    = kernel32.NewProc("GlobalAlloc")
	procGlobalFree     = kernel32.NewProc("GlobalFree")
)

// ── COM structures (x64 ABI) ──────────────────────────────────────────────────

// formatETC mirrors Windows FORMATETC.
// cfFormat(2) + pad(6) = aligns ptd to offset 8.
type formatETC struct {
	cfFormat uint16
	_        [6]byte
	ptd      uintptr // offset 8
	dwAspect uint32  // offset 16
	lindex   int32   // offset 20
	tymed    uint32  // offset 24
	// Go adds 4-byte trailing pad → 32 bytes total, matches Windows.
}

// stgMedium mirrors Windows STGMEDIUM (hGlobal union member).
// tymed(4) + pad(4) = aligns hGlobal to offset 8.
type stgMedium struct {
	tymed          uint32
	_              uint32
	hGlobal        uintptr // offset 8
	pUnkForRelease uintptr // offset 16
}

// ═══════════════════════════════════════════════════════════════════════════════
// DROP IN — IDropTarget
// ═══════════════════════════════════════════════════════════════════════════════

type iDropTargetVtbl struct {
	queryInterface, addRef, release          uintptr
	dragEnter, dragOver, dragLeave, dropFile uintptr
}

// fileDropTarget is a COM IDropTarget.  vtbl MUST be the first field.
type fileDropTarget struct {
	vtbl *iDropTargetVtbl
	app  *App
}

// dropTargetVtbl is shared across all fileDropTarget instances.
var dropTargetVtbl = &iDropTargetVtbl{
	queryInterface: syscall.NewCallback(dtQI),
	addRef:         syscall.NewCallback(dtAddRef),
	release:        syscall.NewCallback(dtRelease),
	dragEnter:      syscall.NewCallback(dtDragEnter),
	dragOver:       syscall.NewCallback(dtDragOver),
	dragLeave:      syscall.NewCallback(dtDragLeave),
	dropFile:       syscall.NewCallback(dtDrop),
}

func newFileDropTarget(app *App) *fileDropTarget {
	return &fileDropTarget{vtbl: dropTargetVtbl, app: app}
}

// IUnknown

func dtQI(_ *fileDropTarget, _, ppvObj uintptr) uintptr {
	*(*uintptr)(unsafe.Pointer(ppvObj)) = 0
	return eNoInterface
}
func dtAddRef(_ *fileDropTarget) uintptr  { return 1 }
func dtRelease(_ *fileDropTarget) uintptr { return 1 }

// IDropTarget::DragEnter(pDataObj, grfKeyState, pt[packed], pdwEffect)
func dtDragEnter(this *fileDropTarget, _, _, _, pdwEffect uintptr) uintptr {
	this.app.connMu.RLock()
	conn := this.app.conn
	this.app.connMu.RUnlock()
	effect := dropEffectNone
	if conn != "" {
		effect = dropEffectCopy
	}
	if pdwEffect != 0 {
		*(*uint32)(unsafe.Pointer(pdwEffect)) = effect
	}
	return sOK
}

// IDropTarget::DragOver(grfKeyState, pt[packed], pdwEffect)
func dtDragOver(this *fileDropTarget, _, _, pdwEffect uintptr) uintptr {
	this.app.connMu.RLock()
	conn := this.app.conn
	this.app.connMu.RUnlock()
	effect := dropEffectNone
	if conn != "" {
		effect = dropEffectCopy
	}
	if pdwEffect != 0 {
		*(*uint32)(unsafe.Pointer(pdwEffect)) = effect
	}
	return sOK
}

// IDropTarget::DragLeave()
func dtDragLeave(_ *fileDropTarget) uintptr { return sOK }

// IDropTarget::Drop(pDataObj, grfKeyState, pt[packed], pdwEffect)
func dtDrop(this *fileDropTarget, pDataObj, _, _, pdwEffect uintptr) uintptr {
	this.app.connMu.RLock()
	conn := this.app.conn
	this.app.connMu.RUnlock()
	if conn == "" {
		if pdwEffect != 0 {
			*(*uint32)(unsafe.Pointer(pdwEffect)) = dropEffectNone
		}
		return sOK
	}
	if pdwEffect != 0 {
		*(*uint32)(unsafe.Pointer(pdwEffect)) = dropEffectCopy
	}

	// Call IDataObject::GetData (vtable slot 3) to get CF_HDROP.
	fmtetc := formatETC{cfFormat: uint16(cfHDrop), dwAspect: dvaspectContent, lindex: -1, tymed: tymedHGlobal}
	var stg stgMedium
	vtblPtr := *(*uintptr)(unsafe.Pointer(pDataObj))
	ptrSize := unsafe.Sizeof(uintptr(0))
	getDataFn := *(*uintptr)(unsafe.Pointer(vtblPtr + 3*ptrSize))
	hr, _, _ := syscall.SyscallN(getDataFn,
		pDataObj,
		uintptr(unsafe.Pointer(&fmtetc)),
		uintptr(unsafe.Pointer(&stg)),
	)
	if hr != 0 {
		return sOK
	}
	defer procReleaseStgMedium.Call(uintptr(unsafe.Pointer(&stg)))

	hdrop := stg.hGlobal
	nFiles, _, _ := procDragQueryFileW.Call(hdrop, 0xFFFFFFFF, 0, 0)
	if nFiles == 0 {
		return sOK
	}

	paths := make([]string, 0, nFiles)
	for i := uintptr(0); i < nFiles; i++ {
		size, _, _ := procDragQueryFileW.Call(hdrop, i, 0, 0)
		buf := make([]uint16, size+1)
		procDragQueryFileW.Call(hdrop, i, uintptr(unsafe.Pointer(&buf[0])), size+1)
		paths = append(paths, syscall.UTF16ToString(buf))
	}

	this.app.uploadPaths(paths)
	return sOK
}

// OleInit initialises OLE on the current (UI) thread.
func OleInit() { procOleInitialize.Call(0) }

// OleShutdown releases OLE on the current (UI) thread.
func OleShutdown() { procOleUninitialize.Call() }

// RegisterDropTarget registers dt as IDropTarget for hwnd and returns a revoke
// func that must be called before the window is destroyed.
func RegisterDropTarget(hwnd win.HWND, dt *fileDropTarget) func() {
	procRegisterDragDrop.Call(uintptr(hwnd), uintptr(unsafe.Pointer(dt)))
	return func() { procRevokeDragDrop.Call(uintptr(hwnd)) }
}

// ═══════════════════════════════════════════════════════════════════════════════
// DRAG OUT — IDropSource + IDataObject
// ═══════════════════════════════════════════════════════════════════════════════

// ── IDropSource ───────────────────────────────────────────────────────────────

type iDropSourceVtbl struct {
	queryInterface, addRef, release  uintptr
	queryContinueDrag, giveFeedback  uintptr
}

type dropSource struct{ vtbl *iDropSourceVtbl }

var dropSourceVtbl = &iDropSourceVtbl{
	queryInterface:    syscall.NewCallback(dsQI),
	addRef:            syscall.NewCallback(dsAddRef),
	release:           syscall.NewCallback(dsRelease),
	queryContinueDrag: syscall.NewCallback(dsQueryContinueDrag),
	giveFeedback:      syscall.NewCallback(dsGiveFeedback),
}

// sharedDropSource is stateless; one instance suffices.
var sharedDropSource = &dropSource{vtbl: dropSourceVtbl}

func dsQI(_ *dropSource, _, ppvObj uintptr) uintptr {
	*(*uintptr)(unsafe.Pointer(ppvObj)) = 0
	return eNoInterface
}
func dsAddRef(_ *dropSource) uintptr  { return 1 }
func dsRelease(_ *dropSource) uintptr { return 1 }

// IDropSource::QueryContinueDrag(fEscapePressed, grfKeyState)
func dsQueryContinueDrag(_ *dropSource, fEscapePressed, grfKeyState uintptr) uintptr {
	if fEscapePressed != 0 {
		return dragDropSCancel
	}
	if grfKeyState&1 == 0 { // MK_LBUTTON released → commit the drop
		return dragDropSDrop
	}
	return sOK
}

// IDropSource::GiveFeedback(dwEffect)
func dsGiveFeedback(_ *dropSource, _ uintptr) uintptr {
	return dragDropSUseDefaultCursors
}

// ── IDataObject ───────────────────────────────────────────────────────────────

type iDataObjectVtbl struct {
	queryInterface, addRef, release                 uintptr
	getData, getDataHere, queryGetData              uintptr
	getCanonicalFormatEtc, setData, enumFormatEtc   uintptr
	dAdvise, dUnadvise, enumDAdvise                 uintptr
}

// fileDataObject provides CF_HDROP for a single remote file.
// The download is deferred to GetData (called at actual drop time).
type fileDataObject struct {
	vtbl    *iDataObjectVtbl // must be first — COM convention
	app     *App
	conn    string
	entry   *FileEntry
	tmpPath string // cached local path after first download; "" until then
}

// E_NOTIMPL stubs of varying arity (syscall.NewCallback requires exact arity).
func doNotImpl1(_, _ uintptr) uintptr                        { return eNotImpl }
func doNotImpl2(_, _, _ uintptr) uintptr                     { return eNotImpl }
func doNotImpl3(_, _, _, _ uintptr) uintptr                  { return eNotImpl }
func doNotImpl4(_, _, _, _, _ uintptr) uintptr               { return eNotImpl }

var dataObjectVtbl = &iDataObjectVtbl{
	queryInterface:        syscall.NewCallback(doQI),
	addRef:                syscall.NewCallback(doAddRef),
	release:               syscall.NewCallback(doRelease),
	getData:               syscall.NewCallback(doGetData),
	getDataHere:           syscall.NewCallback(doNotImpl2),     // (this, FORMATETC*, STGMEDIUM*)
	queryGetData:          syscall.NewCallback(doQueryGetData), // (this, FORMATETC*)
	getCanonicalFormatEtc: syscall.NewCallback(doNotImpl2),     // (this, FORMATETC*, FORMATETC*)
	setData:               syscall.NewCallback(doNotImpl3),     // (this, FORMATETC*, STGMEDIUM*, BOOL)
	enumFormatEtc:         syscall.NewCallback(doNotImpl2),     // (this, DWORD, IEnumFORMATETC**)
	dAdvise:               syscall.NewCallback(doNotImpl4),     // (this, FORMATETC*, DWORD, IAdviseSink*, DWORD*)
	dUnadvise:             syscall.NewCallback(doNotImpl1),     // (this, DWORD)
	enumDAdvise:           syscall.NewCallback(doNotImpl1),     // (this, IEnumSTATDATA**)
}

func newFileDataObject(app *App, conn string, entry *FileEntry) *fileDataObject {
	return &fileDataObject{vtbl: dataObjectVtbl, app: app, conn: conn, entry: entry}
}

func doQI(_ *fileDataObject, _, ppvObj uintptr) uintptr {
	*(*uintptr)(unsafe.Pointer(ppvObj)) = 0
	return eNoInterface
}
func doAddRef(_ *fileDataObject) uintptr  { return 1 }
func doRelease(_ *fileDataObject) uintptr { return 1 }

// IDataObject::QueryGetData(FORMATETC*)
func doQueryGetData(_ *fileDataObject, pfmtetc uintptr) uintptr {
	fmtetc := (*formatETC)(unsafe.Pointer(pfmtetc))
	if fmtetc.cfFormat == uint16(cfHDrop) {
		return sOK
	}
	return dvEFormatEtc
}

// IDataObject::GetData(FORMATETC*, STGMEDIUM*)
// Called by the drop target at drop time.  Downloads the file lazily on the
// first call, then returns a fresh HGLOBAL on every call.  A fresh HGLOBAL is
// required because the drop target takes ownership of the medium and frees it
// via ReleaseStgMedium after each call — reusing the same handle would be a
// use-after-free.
func doGetData(this *fileDataObject, pfmtetc, pstgmed uintptr) uintptr {
	fmtetc := (*formatETC)(unsafe.Pointer(pfmtetc))
	if fmtetc.cfFormat != uint16(cfHDrop) {
		return dvEFormatEtc
	}
	// Download once; cache the local path so subsequent GetData calls skip the
	// network round-trip but still produce independent HGLOBALs.
	if this.tmpPath == "" {
		path, err := this.app.downloadToTempFile(this.conn, this.entry)
		if err != nil {
			return eFail
		}
		this.tmpPath = path
	}
	hdrop := createHDROP(this.tmpPath)
	if hdrop == 0 {
		return eFail
	}
	stg := (*stgMedium)(unsafe.Pointer(pstgmed))
	stg.tymed = tymedHGlobal
	stg.hGlobal = hdrop
	stg.pUnkForRelease = 0
	return sOK
}

// ── HDROP builder ─────────────────────────────────────────────────────────────

// createHDROP allocates a zeroed GMEM_FIXED block containing a DROPFILES
// struct for a single local file.  The drop target frees it via
// ReleaseStgMedium / GlobalFree.
func createHDROP(path string) uintptr {
	// DROPFILES layout (x64): pFiles(4)+pt.x(4)+pt.y(4)+fNC(4)+fWide(4) = 20 bytes
	const headerSize = uintptr(20)

	pathW := syscall.StringToUTF16(path) // NUL-terminated
	pathW = append(pathW, 0)             // double-NUL required by HDROP
	pathBytes := uintptr(len(pathW)) * 2 // UTF-16LE

	hGlobal, _, _ := procGlobalAlloc.Call(gmemZeroed, headerSize+pathBytes)
	if hGlobal == 0 {
		return 0
	}
	// Set pFiles (offset 0) and fWide (offset 16); other fields stay zero.
	*(*uint32)(unsafe.Pointer(hGlobal))          = uint32(headerSize)
	*(*uint32)(unsafe.Pointer(hGlobal + 16))     = 1 // fWide = TRUE
	dst := unsafe.Slice((*uint16)(unsafe.Pointer(hGlobal+headerSize)), len(pathW))
	copy(dst, pathW)
	return hGlobal
}

// downloadToTempFile downloads a remote file to the OS temp dir and returns
// the local path.  The caller is responsible for creating an HDROP from that
// path.  Blocks the calling goroutine while downloading.
func (app *App) downloadToTempFile(conn string, entry *FileEntry) (string, error) {
	tmpDir := filepath.Join(os.TempDir(), "fileproxy-explorer", conn)
	if err := os.MkdirAll(tmpDir, 0700); err != nil {
		return "", err
	}
	// Use a unique suffix to avoid collisions when the same file is dragged out
	// multiple times while a previous copy is still open in another application.
	ext := filepath.Ext(entry.Name)
	base := strings.TrimSuffix(entry.Name, ext)
	tmpPath := filepath.Join(tmpDir, fmt.Sprintf("%s-%d%s", base, time.Now().UnixNano(), ext))

	app.setStatus("Preparing "+entry.Name+"...", "")
	body, _, err := app.api.Download(conn, entry.FullPath)
	if err != nil {
		app.setStatus("Error: "+err.Error(), "")
		return "", err
	}
	defer body.Close()

	f, err := os.Create(tmpPath)
	if err != nil {
		return "", err
	}
	defer f.Close()
	if _, err = io.Copy(f, body); err != nil {
		return "", err
	}
	app.setStatus("Ready", "")
	return tmpPath, nil
}

// ── Drag-out detection ────────────────────────────────────────────────────────

// dragOutState tracks the pending drag gesture from the TableView.
var dragOutState struct {
	pressing bool
	startX   int32
	startY   int32
}

// attachDragOut wires mouse events on the TableView to start DoDragDrop when
// the user drags a selected file row out of the window.
func (app *App) attachDragOut() {
	app.tableView.MouseDown().Attach(func(x, y int, button walk.MouseButton) {
		if button&walk.LeftButton != 0 {
			dragOutState.pressing = true
			dragOutState.startX = int32(x)
			dragOutState.startY = int32(y)
		}
	})

	app.tableView.MouseUp().Attach(func(_ int, _ int, button walk.MouseButton) {
		if button&walk.LeftButton != 0 {
			dragOutState.pressing = false
		}
	})

	app.tableView.MouseMove().Attach(func(x, y int, button walk.MouseButton) {
		if !dragOutState.pressing || button&walk.LeftButton == 0 {
			dragOutState.pressing = false
			return
		}
		dx := int32(x) - dragOutState.startX
		dy := int32(y) - dragOutState.startY
		if dx*dx+dy*dy < dragThreshSq {
			return
		}
		dragOutState.pressing = false

		idx := app.tableView.CurrentIndex()
		entry := app.tableModel.EntryAt(idx)
		if entry == nil || entry.IsFolder {
			return
		}
		app.connMu.RLock()
		conn := app.conn
		app.connMu.RUnlock()
		if conn == "" {
			return
		}

		app.startFileDragDrop(conn, entry)
	})
}

// startFileDragDrop initiates an OLE drag-and-drop for a single remote file.
// The file is downloaded lazily inside IDataObject::GetData when the user
// actually drops it.  Must be called on the UI thread.
func (app *App) startFileDragDrop(conn string, entry *FileEntry) {
	dataObj := newFileDataObject(app, conn, entry)
	var effect uint32
	procDoDragDrop.Call(
		uintptr(unsafe.Pointer(dataObj)),
		uintptr(unsafe.Pointer(sharedDropSource)),
		uintptr(dropEffectCopy),
		uintptr(unsafe.Pointer(&effect)),
	)
	// Prevent the GC from collecting dataObj before DoDragDrop returns.
	// The pointer was passed as uintptr so the GC cannot see the live reference.
	runtime.KeepAlive(dataObj)
}

// ── uploadPaths ───────────────────────────────────────────────────────────────

// uploadPaths expands directories recursively, then uploads every file to the
// current connection/prefix.  Safe to call from any thread (including the UI
// thread inside an OLE drop callback).
func (app *App) uploadPaths(paths []string) {
	app.connMu.RLock()
	conn := app.conn
	prefix := app.prefix
	app.connMu.RUnlock()

	if conn == "" {
		// Use a goroutine so mw.Synchronize doesn't deadlock when called from
		// the UI thread (e.g. inside IDropTarget::Drop).
		go func() {
			app.mw.Synchronize(func() {
				walk.MsgBox(app.mw, "Upload",
					"Select a connection first.",
					walk.MsgBoxIconWarning|walk.MsgBoxOK)
			})
		}()
		return
	}

	type uploadItem struct {
		localPath  string
		remotePath string
		size       int64
	}

	// Expand the drop list: files are used as-is; directories are walked
	// recursively and their contents uploaded under <prefix><folderName>/...
	var items []uploadItem
	for _, localPath := range paths {
		fi, err := os.Stat(localPath)
		if err != nil {
			continue
		}
		if !fi.IsDir() {
			items = append(items, uploadItem{
				localPath:  localPath,
				remotePath: prefix + filepath.Base(localPath),
				size:       fi.Size(),
			})
			continue
		}
		// Directory: walk and collect files preserving relative structure.
		folderName := filepath.Base(localPath)
		_ = filepath.Walk(localPath, func(p string, info os.FileInfo, err error) error {
			if err != nil || info.IsDir() {
				return nil
			}
			rel, relErr := filepath.Rel(localPath, p)
			if relErr != nil {
				return nil
			}
			remotePath := prefix + folderName + "/" + filepath.ToSlash(rel)
			items = append(items, uploadItem{localPath: p, remotePath: remotePath, size: info.Size()})
			return nil
		})
	}

	for _, item := range items {
		item := item
		op := &Op{
			ID:   nextOpID("ul"),
			Kind: OpUpload,
			Conn: conn,
			Path: item.remotePath,
			Name: filepath.Base(item.localPath),
		}
		op.totalBytes = item.size
		op.status = OpPending
		app.ops.Add(op)

		go func() {
			f, openErr := os.Open(item.localPath)
			if openErr != nil {
				op.Fail(openErr.Error())
				return
			}
			defer f.Close()

			op.Activate()
			queued, upErr := app.api.Upload(op.Conn, op.Path, &progressReader{r: f, op: op}, item.size)
			if upErr != nil {
				op.Fail(upErr.Error())
				return
			}
			if queued {
				op.SetQueued()
			} else {
				op.Complete()
				app.scheduleReload()
			}
		}()
	}
}
