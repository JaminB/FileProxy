package mountsvc

import (
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

// --- bindPort tests ---

func TestBindPort_returnsWorkingListener(t *testing.T) {
	port, ln, err := bindPort(19100)
	if err != nil {
		t.Fatal(err)
	}
	defer ln.Close()

	if port < 19100 || port > 19199 {
		t.Errorf("port %d out of expected range [19100, 19199]", port)
	}
	// Verify the listener is actually accepting connections.
	addr := ln.Addr().String()
	conn, err := net.Dial("tcp", addr)
	if err != nil {
		t.Errorf("listener not reachable: %v", err)
	} else {
		conn.Close()
	}
}

func TestBindPort_skipsInUsePort(t *testing.T) {
	// Claim a port first.
	ln0, err := net.Listen("tcp", "localhost:0")
	if err != nil {
		t.Fatal(err)
	}
	defer ln0.Close()
	occupiedPort := ln0.Addr().(*net.TCPAddr).Port

	port, ln, err := bindPort(occupiedPort)
	if err != nil {
		t.Fatal(err)
	}
	defer ln.Close()

	if port == occupiedPort {
		t.Errorf("expected to advance past occupied port %d, but got the same", occupiedPort)
	}
}

// --- router tests ---

func TestRouter_propfindRouting(t *testing.T) {
	propfindCalled := false
	davCalled := false

	ph := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { propfindCalled = true })
	dh := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { davCalled = true })

	r := newRouter(ph, dh)

	req := httptest.NewRequest("PROPFIND", "/", nil)
	rr := httptest.NewRecorder()
	r.ServeHTTP(rr, req)

	if !propfindCalled {
		t.Error("PROPFIND should route to propfind handler")
	}
	if davCalled {
		t.Error("PROPFIND should not route to dav handler")
	}
}

func TestRouter_getRoutesToDav(t *testing.T) {
	davCalled := false
	ph := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {})
	dh := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { davCalled = true })

	r := newRouter(ph, dh)

	req := httptest.NewRequest("GET", "/", nil)
	rr := httptest.NewRecorder()
	r.ServeHTTP(rr, req)

	if !davCalled {
		t.Error("GET should route to dav handler")
	}
}

func TestRouter_putRoutesToDav(t *testing.T) {
	davCalled := false
	ph := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {})
	dh := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { davCalled = true })

	r := newRouter(ph, dh)

	req := httptest.NewRequest("PUT", "/file.txt", nil)
	rr := httptest.NewRecorder()
	r.ServeHTTP(rr, req)

	if !davCalled {
		t.Error("PUT should route to dav handler")
	}
}

func TestRouter_deleteRoutesToDav(t *testing.T) {
	davCalled := false
	ph := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {})
	dh := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { davCalled = true })

	r := newRouter(ph, dh)

	req := httptest.NewRequest("DELETE", "/file.txt", nil)
	rr := httptest.NewRecorder()
	r.ServeHTTP(rr, req)

	if !davCalled {
		t.Error("DELETE should route to dav handler")
	}
}

func TestRouter_alwaysSetsDAVHeader(t *testing.T) {
	ph := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {})
	dh := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {})
	r := newRouter(ph, dh)

	for _, method := range []string{"PROPFIND", "GET", "PUT", "DELETE"} {
		req := httptest.NewRequest(method, "/", nil)
		rr := httptest.NewRecorder()
		r.ServeHTTP(rr, req)
		if rr.Header().Get("MS-Author-Via") != "DAV" {
			t.Errorf("method %s: missing MS-Author-Via header", method)
		}
	}
}

// --- ConfigPath tests ---

func TestConfigPath_usesAPPDATA(t *testing.T) {
	t.Setenv("APPDATA", "/tmp/testappdata")
	got := ConfigPath()
	expected := filepath.Join("/tmp/testappdata", "FileProxyMount", "config.json")
	if got != expected {
		t.Errorf("got %q, want %q", got, expected)
	}
}

func TestConfigPath_fallsBackToDot(t *testing.T) {
	t.Setenv("APPDATA", "")
	got := ConfigPath()
	expected := filepath.Join(".", "FileProxyMount", "config.json")
	if got != expected {
		t.Errorf("got %q, want %q", got, expected)
	}
}

// --- LoadAuthConfig / SaveAuthConfig tests ---

func TestAuthConfig_roundTrip(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("APPDATA", dir)

	SaveAuthConfig("http://example.com:8000", "my-api-key-123")

	gotURL, gotKey := LoadAuthConfig()
	if gotURL != "http://example.com:8000" {
		t.Errorf("url mismatch: got %q", gotURL)
	}
	if gotKey != "my-api-key-123" {
		t.Errorf("key mismatch: got %q", gotKey)
	}
}

func TestLoadAuthConfig_missingFile_returnsEmpty(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("APPDATA", dir)
	// No config saved.
	url, key := LoadAuthConfig()
	if url != "" || key != "" {
		t.Errorf("expected empty strings, got url=%q key=%q", url, key)
	}
}

func TestLoadAuthConfig_corruptJSON_returnsEmpty(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("APPDATA", dir)

	// Write a valid config first to create the directory, then corrupt it.
	SaveAuthConfig("http://example.com", "key")
	os.WriteFile(ConfigPath(), []byte("not-json!!!"), 0600)

	url, key := LoadAuthConfig()
	if url != "" || key != "" {
		t.Errorf("expected empty on corrupt JSON, got url=%q key=%q", url, key)
	}
}
