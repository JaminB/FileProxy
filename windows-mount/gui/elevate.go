//go:build windows

package gui

import (
	"fmt"
	"os"
	"syscall"
	"unsafe"

	"github.com/lxn/walk"
)

// bcmSetShield is the Win32 message that adds a UAC shield overlay to a button.
const bcmSetShield = 0x160C

var (
	modUser32         = syscall.NewLazyDLL("user32.dll")
	procSendMessage   = modUser32.NewProc("SendMessageW")
	modShell32        = syscall.NewLazyDLL("shell32.dll")
	procShellExecuteW = modShell32.NewProc("ShellExecuteW")
)

// setShieldIcon decorates btn with the UAC shield overlay, signalling to the
// user that clicking it will trigger an elevation prompt.
func setShieldIcon(btn *walk.PushButton) {
	procSendMessage.Call(uintptr(btn.Handle()), bcmSetShield, 0, 1)
}

// relaunchElevated re-runs the current executable with the given argument
// using the "runas" ShellExecute verb, which triggers a UAC elevation prompt.
// hwnd is used as the parent for the UAC dialog.
func relaunchElevated(hwnd uintptr, arg string) error {
	verb, _ := syscall.UTF16PtrFromString("runas")
	exe, _ := os.Executable()
	exePtr, _ := syscall.UTF16PtrFromString(exe)
	argPtr, _ := syscall.UTF16PtrFromString(arg)
	ret, _, _ := procShellExecuteW.Call(
		hwnd,
		uintptr(unsafe.Pointer(verb)),
		uintptr(unsafe.Pointer(exePtr)),
		uintptr(unsafe.Pointer(argPtr)),
		0,
		1, // SW_SHOWNORMAL
	)
	// ShellExecute returns a value > 32 on success.
	if ret <= 32 {
		return fmt.Errorf("elevation request failed (code %d)", ret)
	}
	return nil
}
