package winmount

import (
	"fmt"
	"os/exec"
	"strings"
)

// validateDrive returns an error if drive is not exactly one ASCII letter A–Z.
func validateDrive(drive string) error {
	if len(drive) != 1 || drive[0] < 'A' || drive[0] > 'Z' {
		return fmt.Errorf("invalid drive letter %q: must be a single letter A–Z", drive)
	}
	return nil
}

// Mount maps drive letter to the local WebDAV server using net use.
func Mount(drive string, port int) error {
	drive = strings.TrimSuffix(strings.ToUpper(drive), ":")
	if err := validateDrive(drive); err != nil {
		return err
	}
	url := fmt.Sprintf("http://localhost:%d", port)
	cmd := exec.Command("net", "use", drive+":", url, "/persistent:no") // #nosec G204 -- drive validated to single A-Z letter above
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("%w\n%s", err, strings.TrimSpace(string(out)))
	}
	return nil
}

// Unmount removes the drive mapping.
func Unmount(drive string) error {
	drive = strings.TrimSuffix(strings.ToUpper(drive), ":")
	if err := validateDrive(drive); err != nil {
		return err
	}
	cmd := exec.Command("net", "use", drive+":", "/delete", "/y") // #nosec G204 -- drive validated to single A-Z letter above
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("%w\n%s", err, strings.TrimSpace(string(out)))
	}
	return nil
}
