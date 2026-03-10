//go:build windows

package winmount

import (
	"fmt"
	"os/exec"

	"golang.org/x/sys/windows/registry"
)

const webClientParamsKey = `SYSTEM\CurrentControlSet\Services\WebClient\Parameters`

// SetFileSizeLimit sets the WebClient FileSizeLimitInBytes registry value so
// that Windows allows WebDAV writes larger than the default 50 MB cap.
// Requires administrator privileges; returns a descriptive error if access is denied.
func SetFileSizeLimit(limitBytes uint32) error {
	k, err := registry.OpenKey(registry.LOCAL_MACHINE, webClientParamsKey, registry.SET_VALUE)
	if err != nil {
		return fmt.Errorf("open WebClient registry key (run as Administrator): %w", err)
	}
	defer k.Close()
	if err := k.SetDWordValue("FileSizeLimitInBytes", limitBytes); err != nil {
		return fmt.Errorf("set FileSizeLimitInBytes: %w", err)
	}
	return nil
}

// RestartWebClient stops and starts the WebClient service so that the updated
// registry value takes effect immediately. Ignores "not running" errors from stop.
func RestartWebClient() error {
	// Ignore stop errors — service may already be stopped.
	_ = exec.Command("net", "stop", "WebClient").Run()
	if err := exec.Command("net", "start", "WebClient").Run(); err != nil {
		return fmt.Errorf("start WebClient service: %w", err)
	}
	return nil
}
