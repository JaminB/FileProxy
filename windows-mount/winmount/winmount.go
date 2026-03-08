package winmount

import (
	"fmt"
	"os/exec"
	"strings"
)

// Mount maps drive letter to the local WebDAV server using net use.
func Mount(drive string, port int) error {
	drive = strings.TrimSuffix(strings.ToUpper(drive), ":")
	url := fmt.Sprintf("http://localhost:%d", port)
	cmd := exec.Command("net", "use", drive+":", url, "/persistent:no") //nolint:gosec // G204: drive is user-supplied input, not attacker-controlled
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("%w\n%s", err, strings.TrimSpace(string(out)))
	}
	return nil
}

// Unmount removes the drive mapping.
func Unmount(drive string) error {
	drive = strings.TrimSuffix(strings.ToUpper(drive), ":")
	cmd := exec.Command("net", "use", drive+":", "/delete", "/y") //nolint:gosec // G204: drive is user-supplied input, not attacker-controlled
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("%w\n%s", err, strings.TrimSpace(string(out)))
	}
	return nil
}
