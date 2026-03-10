package main

import (
	"os"
	"syscall"
	"unsafe"

	"github.com/fileproxy/windows-mount/cmd"
	"github.com/fileproxy/windows-mount/gui"
	"github.com/fileproxy/windows-mount/mountsvc"
	"github.com/fileproxy/windows-mount/winmount"
)

var (
	kernel32       = syscall.NewLazyDLL("kernel32.dll")
	freeConsole    = kernel32.NewProc("FreeConsole")
	user32         = syscall.NewLazyDLL("user32.dll")
	procMsgBox     = user32.NewProc("MessageBoxW")
)

func showMessageBox(title, text string, isError bool) {
	t, _ := syscall.UTF16PtrFromString(title)
	m, _ := syscall.UTF16PtrFromString(text)
	var flags uintptr = 0x00000040 // MB_ICONINFORMATION
	if isError {
		flags = 0x00000010 // MB_ICONERROR
	}
	procMsgBox.Call(0, uintptr(unsafe.Pointer(m)), uintptr(unsafe.Pointer(t)), flags)
}

func main() {
	// Elevated helper: re-launched by the GUI's "Allow Large Files" button.
	// Runs as Administrator to patch the WebClient registry key, then exits.
	if len(os.Args) == 2 && os.Args[1] == "--set-webdav-limit" {
		freeConsole.Call()
		err := winmount.SetFileSizeLimit(0xFFFFFFFF)
		if err == nil {
			err = winmount.RestartWebClient()
		}
		if err != nil {
			showMessageBox("FileProxy Mount", "Could not raise WebDAV file size limit:\n\n"+err.Error(), true)
		} else {
			showMessageBox("FileProxy Mount", "WebDAV file size limit raised to 4 GB.\n\nRemount the drive for the change to take effect.", false)
		}
		return
	}

	if len(os.Args) == 1 {
		// Launched without arguments (e.g. double-clicked from Explorer).
		// Release the console Windows auto-creates so no terminal flickers
		// behind the GUI window.
		freeConsole.Call()

		savedURL, savedKey := mountsvc.LoadAuthConfig()
		cfg := mountsvc.Config{
			ServerURL: savedURL,
			APIKey:    savedKey,
			Drive:     "F",
			Port:      6789,
		}
		gui.Run(cfg, false)
		return
	}

	// Launched with arguments — standard CLI mode via cobra.
	cmd.Execute()
}
