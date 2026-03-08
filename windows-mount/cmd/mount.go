package cmd

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/fileproxy/windows-mount/mountsvc"
	"github.com/spf13/cobra"
	"golang.org/x/term"
)

var (
	flagServerURL string
	flagAPIKey    string
	flagPort      int
	flagDrive     string
)

var mountCmd = &cobra.Command{
	Use:   "mount",
	Short: "Mount FileProxy connections as a Windows drive letter via WebDAV",
	RunE:  runMount,
}

func init() {
	mountCmd.Flags().StringVar(&flagServerURL, "server-url", "", "FileProxy server URL (e.g. http://localhost:8000)")
	mountCmd.Flags().StringVar(&flagAPIKey, "api-key", "", "JWT API key (prompted if omitted)")
	mountCmd.Flags().IntVar(&flagPort, "port", 6789, "Local WebDAV port")
	mountCmd.Flags().StringVar(&flagDrive, "drive", "F", "Drive letter to map")
	rootCmd.AddCommand(mountCmd)
}

func runMount(cmd *cobra.Command, args []string) error {
	savedURL, savedKey := mountsvc.LoadAuthConfig()

	serverURL := flagServerURL
	if serverURL == "" {
		serverURL = savedURL
	}
	if serverURL == "" {
		return fmt.Errorf("--server-url is required")
	}

	apiKey := flagAPIKey
	if apiKey == "" {
		apiKey = savedKey
	}
	if apiKey == "" {
		fmt.Print("Enter API key: ")
		raw, err := term.ReadPassword(int(syscall.Stdin))
		if err != nil {
			return fmt.Errorf("reading API key: %w", err)
		}
		fmt.Println()
		apiKey = string(raw)
	}
	if apiKey == "" {
		return fmt.Errorf("API key is required")
	}

	cfg := mountsvc.Config{
		ServerURL: serverURL,
		APIKey:    apiKey,
		Drive:     flagDrive,
		Port:      flagPort,
	}

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	return mountsvc.Start(ctx, cfg, os.Stderr, nil)
}
