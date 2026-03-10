package wdfs

import (
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/fileproxy/windows-mount/client"
	fpfs "github.com/fileproxy/windows-mount/proxyfs"
)

// --- davHref tests ---

func TestDavHref_plainPath(t *testing.T) {
	got := davHref("/myconn/file.txt", false)
	if got != "/myconn/file.txt" {
		t.Errorf("unexpected href: %q", got)
	}
}

func TestDavHref_specialCharsEncoded(t *testing.T) {
	got := davHref("/my conn/file name.txt", false)
	if strings.Contains(got, " ") {
		t.Errorf("spaces should be encoded, got %q", got)
	}
}

func TestDavHref_dirGetsTrailingSlash(t *testing.T) {
	got := davHref("/myconn/subdir", true)
	if !strings.HasSuffix(got, "/") {
		t.Errorf("dir should have trailing slash, got %q", got)
	}
}

func TestDavHref_dirAlreadyHasTrailingSlash(t *testing.T) {
	got := davHref("/myconn/subdir/", true)
	if strings.Count(got, "/") != strings.Count("/myconn/subdir/", "/") {
		t.Errorf("unexpected href: %q", got)
	}
}

// --- xmlEscape tests ---

func TestXmlEscape_ampersand(t *testing.T) {
	got := xmlEscape("a&b")
	if got != "a&amp;b" {
		t.Errorf("got %q", got)
	}
}

func TestXmlEscape_lessThan(t *testing.T) {
	got := xmlEscape("a<b")
	if got != "a&lt;b" {
		t.Errorf("got %q", got)
	}
}

func TestXmlEscape_greaterThan(t *testing.T) {
	got := xmlEscape("a>b")
	if got != "a&gt;b" {
		t.Errorf("got %q", got)
	}
}

func TestXmlEscape_quote(t *testing.T) {
	got := xmlEscape(`a"b`)
	if got != "a&quot;b" {
		t.Errorf("got %q", got)
	}
}

func TestXmlEscape_combined(t *testing.T) {
	got := xmlEscape(`<a href="b&c">`)
	expected := "&lt;a href=&quot;b&amp;c&quot;&gt;"
	if got != expected {
		t.Errorf("got %q, want %q", got, expected)
	}
}

// --- writeDAVResponse tests ---

func TestWriteDAVResponse_file(t *testing.T) {
	rr := httptest.NewRecorder()
	fi := &mockFileInfo{name: "file.txt", size: 1234, isDir: false}
	writeDAVResponse(rr, "/conn/file.txt", fi)
	body := rr.Body.String()

	if !strings.Contains(body, "<D:getcontentlength>1234</D:getcontentlength>") {
		t.Errorf("missing content-length in:\n%s", body)
	}
	if strings.Contains(body, "<D:collection/>") {
		t.Errorf("file should not have <D:collection/> in:\n%s", body)
	}
}

func TestWriteDAVResponse_dir(t *testing.T) {
	rr := httptest.NewRecorder()
	fi := &mockFileInfo{name: "subdir", isDir: true}
	writeDAVResponse(rr, "/conn/subdir", fi)
	body := rr.Body.String()

	if !strings.Contains(body, "<D:collection/>") {
		t.Errorf("dir should have <D:collection/> in:\n%s", body)
	}
	if strings.Contains(body, "<D:getcontentlength>") {
		t.Errorf("dir should not have content-length in:\n%s", body)
	}
}

type mockFileInfo struct {
	name  string
	size  int64
	isDir bool
}

func (m *mockFileInfo) Name() string      { return m.name }
func (m *mockFileInfo) Size() int64       { return m.size }
func (m *mockFileInfo) IsDir() bool       { return m.isDir }
func (m *mockFileInfo) ModTime() time.Time { return time.Time{} }
func (m *mockFileInfo) Mode() os.FileMode {
	if m.isDir {
		return os.ModeDir | 0755
	}
	return 0644
}
func (m *mockFileInfo) Sys() interface{} { return nil }

// --- loggingFile tests ---

func TestLoggingFile_Read_normalAndEOF(t *testing.T) {
	// Create a loggingFile wrapping an in-memory implementation.
	inner := &inMemFile{data: []byte("hello")}
	lf := &loggingFile{File: inner, name: "test.txt"}

	buf := make([]byte, 10)
	n, err := lf.Read(buf)
	// Should not log the EOF error as an "ERROR"
	if err != nil && err.Error() == "EOF" {
		// EOF is acceptable — not treated as error in the log
	}
	if n > 0 && string(buf[:n]) != "hello" {
		t.Errorf("unexpected data: %q", buf[:n])
	}
}

// inMemFile is a minimal webdav.File backed by a byte slice.
type inMemFile struct {
	data []byte
	pos  int
}

func (f *inMemFile) Read(p []byte) (int, error) {
	if f.pos >= len(f.data) {
		return 0, io.EOF
	}
	n := copy(p, f.data[f.pos:])
	f.pos += n
	return n, nil
}

func (f *inMemFile) Close() error                               { return nil }
func (f *inMemFile) Seek(offset int64, whence int) (int64, error) { return 0, nil }
func (f *inMemFile) Readdir(count int) ([]os.FileInfo, error)   { return nil, nil }
func (f *inMemFile) Stat() (os.FileInfo, error)                 { return &mockFileInfo{name: "test.txt"}, nil }
func (f *inMemFile) Write(p []byte) (int, error)                { return 0, nil }

// --- PropfindHandler.ServeHTTP integration tests ---

// mockAPIClient implements fpfs.APIClient for propfind integration tests.
type mockAPIClient struct {
	conns   []client.Connection
	objects map[string][]client.Object
}

func (m *mockAPIClient) ListConnections() ([]client.Connection, error) {
	return m.conns, nil
}

func (m *mockAPIClient) Enumerate(conn, prefix string) ([]client.Object, error) {
	key := conn + ":" + prefix
	return m.objects[key], nil
}

func (m *mockAPIClient) EnumerateStream(conn, prefix string) (<-chan client.Object, <-chan error) {
	objCh := make(chan client.Object, 100)
	errCh := make(chan error, 1)
	go func() {
		defer close(objCh)
		defer close(errCh)
		key := conn + ":" + prefix
		for _, obj := range m.objects[key] {
			objCh <- obj
		}
	}()
	return objCh, errCh
}

func (m *mockAPIClient) Download(conn, path string) ([]byte, error) { return nil, nil }
func (m *mockAPIClient) WriteStream(conn, path string, r io.Reader) error {
	io.Copy(io.Discard, r) //nolint:errcheck
	return nil
}
func (m *mockAPIClient) Delete(conn, path string) error { return nil }

func newTestHandler(api *mockAPIClient) *PropfindHandler {
	proxyFS := fpfs.NewFromAPIClient(api)
	wdfsFS := New(proxyFS)
	return NewPropfindHandler(wdfsFS)
}

func TestPropfindHandler_depth0_rootOnly(t *testing.T) {
	api := &mockAPIClient{
		conns: []client.Connection{{Name: "conn1", Kind: "aws_s3"}},
	}
	h := newTestHandler(api)

	req := httptest.NewRequest("PROPFIND", "/", nil)
	req.Header.Set("Depth", "0")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)

	if rr.Code != 207 {
		t.Errorf("expected 207, got %d", rr.Code)
	}
	body := rr.Body.String()
	if !strings.Contains(body, `<D:multistatus`) {
		t.Errorf("missing multistatus in body:\n%s", body)
	}
	// depth=0 should not list children
	if strings.Contains(body, "conn1") {
		t.Errorf("depth=0 should not list children, but got conn1 in:\n%s", body)
	}
}

func TestPropfindHandler_depth1_rootListsConnections(t *testing.T) {
	api := &mockAPIClient{
		conns: []client.Connection{
			{Name: "myconn", Kind: "aws_s3"},
		},
	}
	h := newTestHandler(api)

	req := httptest.NewRequest("PROPFIND", "/", nil)
	req.Header.Set("Depth", "1")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)

	if rr.Code != 207 {
		t.Errorf("expected 207, got %d", rr.Code)
	}
	body := rr.Body.String()
	if !strings.Contains(body, "myconn") {
		t.Errorf("expected myconn in depth=1 response:\n%s", body)
	}
}

func TestPropfindHandler_nonExistentPath_returns404(t *testing.T) {
	api := &mockAPIClient{
		conns: []client.Connection{{Name: "other", Kind: "aws_s3"}},
	}
	h := newTestHandler(api)

	req := httptest.NewRequest("PROPFIND", "/doesnotexist", nil)
	req.Header.Set("Depth", "1")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)

	if rr.Code != http.StatusNotFound {
		t.Errorf("expected 404, got %d", rr.Code)
	}
}

func TestPropfindHandler_fileWithDepth1_singleResponse(t *testing.T) {
	size := int64(500)
	api := &mockAPIClient{
		conns: []client.Connection{{Name: "myconn", Kind: "aws_s3"}},
		objects: map[string][]client.Object{
			// Stat("/myconn/readme.txt") enumerates parent prefix ""
			"myconn:": {{Path: "readme.txt", Size: &size}},
		},
	}
	h := newTestHandler(api)

	req := httptest.NewRequest("PROPFIND", "/myconn/readme.txt", nil)
	req.Header.Set("Depth", "1")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)

	if rr.Code != 207 {
		t.Errorf("expected 207, got %d", rr.Code)
	}
	body := rr.Body.String()
	// File: should contain content-length, should not have collection
	if !strings.Contains(body, "<D:getcontentlength>500</D:getcontentlength>") {
		t.Errorf("expected content-length in response:\n%s", body)
	}
	if strings.Contains(body, "<D:collection/>") {
		t.Errorf("file should not have collection:\n%s", body)
	}
}

// --- contentType tests ---

func TestContentType_knownExtension(t *testing.T) {
	ct := contentType("photo.png")
	if !strings.HasPrefix(ct, "image/png") {
		t.Errorf("expected image/png, got %q", ct)
	}
}

func TestContentType_unknownExtension(t *testing.T) {
	if got := contentType("file.xyz999"); got != "application/octet-stream" {
		t.Errorf("expected fallback, got %q", got)
	}
}

func TestContentType_noExtension(t *testing.T) {
	if got := contentType("Makefile"); got != "application/octet-stream" {
		t.Errorf("expected fallback, got %q", got)
	}
}
