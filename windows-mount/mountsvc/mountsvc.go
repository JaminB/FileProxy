// Package mountsvc contains the core WebDAV mount logic shared by the CLI
// and GUI frontends.
package mountsvc

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"

	"github.com/fileproxy/windows-mount/client"
	fpfs "github.com/fileproxy/windows-mount/proxyfs"
	"github.com/fileproxy/windows-mount/wdfs"
	"github.com/fileproxy/windows-mount/winmount"
	"golang.org/x/net/webdav"
)

// Config holds the parameters for a mount session.
type Config struct {
	ServerURL string
	APIKey    string
	Drive     string
	Port      int
}

// Start connects to FileProxy, starts the local WebDAV server, mounts the
// drive, and blocks until ctx is cancelled or a fatal error occurs.
// All status and error messages are written to log.
// onMounted is called synchronously in the same goroutine that invoked Start,
// after the drive is successfully mounted. Callers that need to update UI state
// should wrap it in their own synchronization (e.g. mw.Synchronize).
func Start(ctx context.Context, cfg Config, log io.Writer, onMounted func()) error {
	c := client.New(cfg.ServerURL, cfg.APIKey)

	fmt.Fprintf(log, "Connecting to %s ...\n", cfg.ServerURL)
	connections, err := c.ListConnections()
	if err != nil {
		return fmt.Errorf("connecting to FileProxy: %w", err)
	}
	fmt.Fprintf(log, "Found %d connection(s):\n", len(connections))
	for _, conn := range connections {
		fmt.Fprintf(log, "  • %s (%s)\n", conn.Name, conn.Kind)
	}

	SaveAuthConfig(cfg.ServerURL, cfg.APIKey)

	filesystem := wdfs.New(fpfs.New(c))
	davHandler := &webdav.Handler{
		FileSystem: filesystem,
		LockSystem: webdav.NewMemLS(),
		Logger: func(r *http.Request, err error) {
			if err != nil {
				fmt.Fprintf(log, "[webdav] %s %s: %v\n", r.Method, r.URL.Path, err)
			}
		},
	}

	port, ln, err := bindPort(cfg.Port)
	if err != nil {
		return fmt.Errorf("WebDAV server error: %w", err)
	}
	if port != cfg.Port {
		fmt.Fprintf(log, "Port %d in use, using port %d instead.\n", cfg.Port, port)
	}

	srv := &http.Server{
		Handler: newRouter(wdfs.NewPropfindHandler(filesystem), davHandler),
	}

	srvErr := make(chan error, 1)
	go func() {
		if err := srv.Serve(ln); err != nil && err != http.ErrServerClosed {
			srvErr <- err
		}
	}()

	fmt.Fprintf(log, "Mounting drive %s: ...\n", cfg.Drive)
	if err := winmount.Mount(cfg.Drive, port); err != nil {
		srv.Close()
		return fmt.Errorf("mount failed: %w\n\nEnsure the WebClient service is running:\n  sc start WebClient", err)
	}
	fmt.Fprintf(log, "Drive %s: mounted — open Explorer to browse.\n", cfg.Drive)

	if onMounted != nil {
		onMounted()
	}

	select {
	case <-ctx.Done():
	case err := <-srvErr:
		winmount.Unmount(cfg.Drive)
		return fmt.Errorf("WebDAV server error: %w", err)
	}

	fmt.Fprintf(log, "Unmounting drive %s: ...\n", cfg.Drive)
	if err := winmount.Unmount(cfg.Drive); err != nil {
		fmt.Fprintf(log, "Warning: unmount failed: %v\n", err)
	}
	srv.Shutdown(context.Background())
	fmt.Fprintf(log, "Done.\n")
	return nil
}

// bindPort tries to listen on the requested port. If that port is already in
// use it walks up by 1 until it finds a free port (up to +99). Returns the
// actual port and the already-listening net.Listener.
func bindPort(port int) (int, net.Listener, error) {
	if port < 1 || port > 65535 {
		return 0, nil, fmt.Errorf("invalid port %d: must be between 1 and 65535", port)
	}
	maxPort := port + 99
	if maxPort > 65535 {
		maxPort = 65535
	}
	for p := port; p <= maxPort; p++ {
		ln, err := net.Listen("tcp", fmt.Sprintf("localhost:%d", p))
		if err == nil {
			return p, ln, nil
		}
	}
	return 0, nil, fmt.Errorf("no free port found in range %d–%d; another instance may still be running", port, maxPort)
}

// --- HTTP routing ---

type router struct{ propfind, dav http.Handler }

func (r *router) ServeHTTP(w http.ResponseWriter, req *http.Request) {
	w.Header().Set("MS-Author-Via", "DAV")
	if req.Method == "PROPFIND" {
		r.propfind.ServeHTTP(w, req)
	} else {
		r.dav.ServeHTTP(w, req)
	}
}

func newRouter(propfind, dav http.Handler) *router {
	return &router{propfind: propfind, dav: dav}
}

// --- Config persistence ---

type authConfig struct {
	ServerURL string `json:"server_url"`
	APIKey    string `json:"api_key"`
}

func ConfigPath() string {
	appdata := os.Getenv("APPDATA")
	if appdata == "" {
		appdata = "."
	}
	return filepath.Join(appdata, "FileProxyMount", "config.json")
}

// LoadAuthConfig returns the saved server URL and API key, if any.
func LoadAuthConfig() (serverURL, apiKey string) {
	data, err := os.ReadFile(ConfigPath())
	if err != nil {
		return "", ""
	}
	var cfg authConfig
	_ = json.Unmarshal(data, &cfg)
	return cfg.ServerURL, cfg.APIKey
}

// SaveAuthConfig persists the server URL and API key for future sessions.
func SaveAuthConfig(serverURL, apiKey string) {
	path := ConfigPath()
	_ = os.MkdirAll(filepath.Dir(path), 0700)
	data, _ := json.MarshalIndent(authConfig{ServerURL: serverURL, APIKey: apiKey}, "", "  ")
	_ = os.WriteFile(path, data, 0600)
}
