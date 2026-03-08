package main

import (
	"os"
	"syscall"

	"github.com/fileproxy/windows-mount/cmd"
	"github.com/fileproxy/windows-mount/gui"
	"github.com/fileproxy/windows-mount/mountsvc"
)

var (
	kernel32    = syscall.NewLazyDLL("kernel32.dll")
	freeConsole = kernel32.NewProc("FreeConsole")
)

func main() {
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
