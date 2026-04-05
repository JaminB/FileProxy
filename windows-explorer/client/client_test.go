package client_test

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/fileproxy/windows-explorer/client"
)

func newClient(srv *httptest.Server) *client.Client {
	return client.New(srv.URL, "test-key")
}

// TestEnumeratePagination verifies that Enumerate follows NextCursor across pages.
func TestEnumeratePagination(t *testing.T) {
	page := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer test-key" {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		var resp client.EnumeratePage
		if page == 0 {
			resp = client.EnumeratePage{
				Objects:    []client.Object{{Name: "a.txt", Path: "prefix/a.txt"}},
				NextCursor: "cursor-1",
			}
		} else {
			resp = client.EnumeratePage{
				Objects: []client.Object{{Name: "b.txt", Path: "prefix/b.txt"}},
			}
		}
		page++
		json.NewEncoder(w).Encode(resp) //nolint:errcheck
	}))
	defer srv.Close()

	objs, err := newClient(srv).Enumerate("my-conn", "prefix/")
	if err != nil {
		t.Fatalf("Enumerate: %v", err)
	}
	if len(objs) != 2 {
		t.Fatalf("expected 2 objects across 2 pages, got %d", len(objs))
	}
	if objs[0].Name != "a.txt" || objs[1].Name != "b.txt" {
		t.Errorf("unexpected object names: %v", objs)
	}
}

// TestUploadQueued verifies that a 202 response sets queued=true.
func TestUploadQueued(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusAccepted)
	}))
	defer srv.Close()

	queued, err := newClient(srv).Upload("my-conn", "folder/file.txt", strings.NewReader("hello"), -1)
	if err != nil {
		t.Fatalf("Upload: %v", err)
	}
	if !queued {
		t.Error("expected queued=true for HTTP 202")
	}
}

// TestUploadImmediate verifies that a 200 response sets queued=false.
func TestUploadImmediate(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	queued, err := newClient(srv).Upload("my-conn", "file.txt", strings.NewReader("hello"), -1)
	if err != nil {
		t.Fatalf("Upload: %v", err)
	}
	if queued {
		t.Error("expected queued=false for HTTP 200")
	}
}

// TestDoErrorResponse verifies that HTTP 4xx responses are returned as errors.
func TestDoErrorResponse(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "not found", http.StatusNotFound)
	}))
	defer srv.Close()

	_, err := newClient(srv).ListConnections()
	if err == nil {
		t.Fatal("expected error for HTTP 404")
	}
	if !strings.Contains(err.Error(), "404") {
		t.Errorf("expected '404' in error, got: %v", err)
	}
}

// TestUploadMultipart verifies that the file field is present in the request body.
func TestUploadMultipart(t *testing.T) {
	var gotContentType string
	var gotBody []byte
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotContentType = r.Header.Get("Content-Type")
		gotBody, _ = io.ReadAll(r.Body)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	_, err := newClient(srv).Upload("conn", "dir/hello.txt", strings.NewReader("world"), -1)
	if err != nil {
		t.Fatalf("Upload: %v", err)
	}
	if gotContentType != "application/octet-stream" {
		t.Errorf("expected application/octet-stream content-type, got: %s", gotContentType)
	}
	if !strings.Contains(string(gotBody), "world") {
		t.Error("expected file content in request body")
	}
}
