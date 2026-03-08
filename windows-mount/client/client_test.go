package client_test

import (
	"encoding/base64"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/fileproxy/windows-mount/client"
)

func TestNew_stripsTrailingSlash(t *testing.T) {
	c := client.New("http://example.com/", "key")
	if strings.HasSuffix(c.BaseURL, "/") {
		t.Errorf("BaseURL should not have trailing slash, got %q", c.BaseURL)
	}
}

func TestNew_preservesURLWithoutSlash(t *testing.T) {
	c := client.New("http://example.com", "key")
	if c.BaseURL != "http://example.com" {
		t.Errorf("unexpected BaseURL: %q", c.BaseURL)
	}
}

func TestListConnections_happyPath(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/files/" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		if r.Header.Get("Authorization") != "Bearer testkey" {
			t.Errorf("unexpected auth header: %q", r.Header.Get("Authorization"))
		}
		json.NewEncoder(w).Encode([]client.Connection{
			{Name: "conn1", Kind: "aws_s3"},
			{Name: "conn2", Kind: "gdrive_oauth2"},
		})
	}))
	defer srv.Close()

	c := client.New(srv.URL, "testkey")
	conns, err := c.ListConnections()
	if err != nil {
		t.Fatal(err)
	}
	if len(conns) != 2 {
		t.Fatalf("expected 2 connections, got %d", len(conns))
	}
	if conns[0].Name != "conn1" || conns[0].Kind != "aws_s3" {
		t.Errorf("unexpected conn[0]: %+v", conns[0])
	}
	if conns[1].Name != "conn2" || conns[1].Kind != "gdrive_oauth2" {
		t.Errorf("unexpected conn[1]: %+v", conns[1])
	}
}

func TestListConnections_httpError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
	}))
	defer srv.Close()

	c := client.New(srv.URL, "badkey")
	_, err := c.ListConnections()
	if err == nil {
		t.Fatal("expected error on 401, got nil")
	}
}

func TestEnumerate_singlePage(t *testing.T) {
	size := int64(42)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]interface{}{
			"objects": []client.Object{
				{Path: "file1.txt", Size: &size},
				{Path: "file2.txt", Size: &size},
			},
			"next_cursor": "",
		})
	}))
	defer srv.Close()

	c := client.New(srv.URL, "key")
	objs, err := c.Enumerate("myconn", "")
	if err != nil {
		t.Fatal(err)
	}
	if len(objs) != 2 {
		t.Fatalf("expected 2 objects, got %d", len(objs))
	}
	if objs[0].Path != "file1.txt" || objs[1].Path != "file2.txt" {
		t.Errorf("unexpected paths: %v", objs)
	}
}

func TestEnumerate_multiPage(t *testing.T) {
	callCount := 0
	size := int64(10)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		cursor := r.URL.Query().Get("cursor")
		if cursor == "" {
			json.NewEncoder(w).Encode(map[string]interface{}{
				"objects":     []client.Object{{Path: "file1.txt", Size: &size}},
				"next_cursor": "page2",
			})
		} else {
			json.NewEncoder(w).Encode(map[string]interface{}{
				"objects":     []client.Object{{Path: "file2.txt", Size: &size}},
				"next_cursor": "",
			})
		}
	}))
	defer srv.Close()

	c := client.New(srv.URL, "key")
	objs, err := c.Enumerate("myconn", "")
	if err != nil {
		t.Fatal(err)
	}
	if len(objs) != 2 {
		t.Fatalf("expected 2 objects across pages, got %d", len(objs))
	}
	if callCount != 2 {
		t.Errorf("expected 2 page fetches, got %d", callCount)
	}
}

func TestEnumerate_prefixPassedThrough(t *testing.T) {
	var gotPrefix string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPrefix = r.URL.Query().Get("prefix")
		json.NewEncoder(w).Encode(map[string]interface{}{"objects": nil, "next_cursor": ""})
	}))
	defer srv.Close()

	c := client.New(srv.URL, "key")
	c.Enumerate("myconn", "subdir/")
	if gotPrefix != "subdir/" {
		t.Errorf("expected prefix %q, got %q", "subdir/", gotPrefix)
	}
}

func TestEnumerateStream_deliversAllObjects(t *testing.T) {
	size := int64(5)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cursor := r.URL.Query().Get("cursor")
		if cursor == "" {
			json.NewEncoder(w).Encode(map[string]interface{}{
				"objects":     []client.Object{{Path: "a.txt", Size: &size}, {Path: "b.txt", Size: &size}},
				"next_cursor": "next",
			})
		} else {
			json.NewEncoder(w).Encode(map[string]interface{}{
				"objects":     []client.Object{{Path: "c.txt", Size: &size}},
				"next_cursor": "",
			})
		}
	}))
	defer srv.Close()

	c := client.New(srv.URL, "key")
	objCh, errCh := c.EnumerateStream("myconn", "")

	var objs []client.Object
	for obj := range objCh {
		objs = append(objs, obj)
	}
	if err := <-errCh; err != nil {
		t.Fatal(err)
	}
	if len(objs) != 3 {
		t.Fatalf("expected 3 objects, got %d", len(objs))
	}
}

func TestEnumerateStream_errorPropagatesViaErrCh(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "server error", http.StatusInternalServerError)
	}))
	defer srv.Close()

	c := client.New(srv.URL, "key")
	objCh, errCh := c.EnumerateStream("myconn", "")

	for range objCh {
	} // drain
	if err := <-errCh; err == nil {
		t.Fatal("expected error from errCh, got nil")
	}
}

func TestRead_base64RoundTrip(t *testing.T) {
	want := []byte("hello world\x00binary")
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]string{
			"data_base64": base64.StdEncoding.EncodeToString(want),
		})
	}))
	defer srv.Close()

	c := client.New(srv.URL, "key")
	got, err := c.Read("myconn", "path/to/file.txt")
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != string(want) {
		t.Errorf("expected %q, got %q", want, got)
	}
}

func TestRead_httpError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "not found", http.StatusNotFound)
	}))
	defer srv.Close()

	c := client.New(srv.URL, "key")
	_, err := c.Read("myconn", "missing.txt")
	if err == nil {
		t.Fatal("expected error on 404, got nil")
	}
}

func TestRead_malformedJSON(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("not-json"))
	}))
	defer srv.Close()

	c := client.New(srv.URL, "key")
	_, err := c.Read("myconn", "file.txt")
	if err == nil {
		t.Fatal("expected error on malformed JSON, got nil")
	}
}

func TestWrite_correctAuthAndPayload(t *testing.T) {
	payload := []byte("binary\x00data\xff")
	var gotBody []byte
	var gotAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		gotBody, _ = io.ReadAll(r.Body)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	c := client.New(srv.URL, "myapikey")
	err := c.Write("myconn", "path/file.bin", payload)
	if err != nil {
		t.Fatal(err)
	}

	if gotAuth != "Bearer myapikey" {
		t.Errorf("unexpected auth header: %q", gotAuth)
	}

	var body struct {
		DataBase64 string `json:"data_base64"`
	}
	if err := json.Unmarshal(gotBody, &body); err != nil {
		t.Fatalf("body not valid JSON: %v\nbody: %s", err, gotBody)
	}
	decoded, err := base64.StdEncoding.DecodeString(body.DataBase64)
	if err != nil {
		t.Fatalf("data_base64 not valid base64: %v", err)
	}
	if string(decoded) != string(payload) {
		t.Errorf("payload mismatch: got %q, want %q", decoded, payload)
	}
}

func TestDelete_correctMethodAndPath(t *testing.T) {
	var gotMethod, gotPath string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotPath = r.URL.Path
		w.WriteHeader(http.StatusNoContent)
	}))
	defer srv.Close()

	c := client.New(srv.URL, "key")
	err := c.Delete("myconn", "some/file.txt")
	if err != nil {
		t.Fatal(err)
	}

	if gotMethod != "DELETE" {
		t.Errorf("expected DELETE method, got %s", gotMethod)
	}
	if !strings.Contains(gotPath, "myconn") {
		t.Errorf("path should contain conn name, got %q", gotPath)
	}
}
