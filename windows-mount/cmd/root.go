package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

var rootCmd = &cobra.Command{
	Use:   "fileproxy-mount",
	Short: "Mount FileProxy connections as a Windows drive letter via WebDAV",
	Long: `fileproxy-mount starts a local WebDAV server backed by the FileProxy REST API
and maps it to a Windows drive letter so you can browse connections in Explorer.`,
}

func Execute() {
	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
