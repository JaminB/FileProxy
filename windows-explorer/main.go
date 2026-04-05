//go:build windows

package main

import (
	"github.com/fileproxy/windows-explorer/client"
	"github.com/fileproxy/windows-explorer/config"
	"github.com/fileproxy/windows-explorer/ui"
)

func main() {
	// Detach from the Windows console before showing any UI, so there is no
	// terminal window flicker when the .exe is double-clicked from Explorer.
	// ui.FreeConsole() // disabled for debug build

	cfg := config.Load()

	// If no credentials saved yet, show the settings dialog before the main window.
	if cfg.ServerURL == "" || cfg.APIKey == "" {
		newCfg, ok := ui.ShowSettingsDialog(nil, cfg)
		if !ok {
			return // User cancelled — exit.
		}
		cfg = newCfg
		config.Save(cfg)
	}

	api := client.New(cfg.ServerURL, cfg.APIKey)
	ui.Run(api, cfg)
}
