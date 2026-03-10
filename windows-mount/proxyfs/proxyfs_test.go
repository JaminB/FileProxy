package proxyfs

import (
	"errors"
	"io"
	"os"
	"testing"
	"time"

	"github.com/fileproxy/windows-mount/client"
)

// mockClient implements APIClient for unit tests.
type mockClient struct {
	conns         []client.Connection
	listErr       error
	objects       map[string][]client.Object // key: "conn:prefix"
	readData      map[string][]byte          // key: "conn:path"
	readErr       error
	writeErr      error
	deleteErr     error
	writeCalls    []writeCall
	downloadCalls int
}

type writeCall struct{ conn, path string; data []byte }

func (m *mockClient) ListConnections() ([]client.Connection, error) {
	return m.conns, m.listErr
}

func (m *mockClient) Enumerate(conn, prefix string) ([]client.Object, error) {
	key := conn + ":" + prefix
	return m.objects[key], nil
}

func (m *mockClient) EnumerateStream(conn, prefix string) (<-chan client.Object, <-chan error) {
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

func (m *mockClient) Download(conn, path string) ([]byte, error) {
	m.downloadCalls++
	if m.readErr != nil {
		return nil, m.readErr
	}
	key := conn + ":" + path
	if data, ok := m.readData[key]; ok {
		return data, nil
	}
	return nil, errors.New("not found")
}

func (m *mockClient) WriteStream(conn, path string, r io.Reader) error {
	data, err := io.ReadAll(r)
	if err != nil {
		return err
	}
	m.writeCalls = append(m.writeCalls, writeCall{conn, path, data})
	return m.writeErr
}

func (m *mockClient) Delete(conn, path string) error {
	return m.deleteErr
}

// --- parseName tests ---

func TestParseName_root(t *testing.T) {
	conn, path := parseName("")
	if conn != "" || path != "" {
		t.Errorf("expected empty, got conn=%q path=%q", conn, path)
	}
}

func TestParseName_leadingSlashRoot(t *testing.T) {
	conn, path := parseName("/")
	if conn != "" || path != "" {
		t.Errorf("expected empty, got conn=%q path=%q", conn, path)
	}
}

func TestParseName_connOnly(t *testing.T) {
	conn, path := parseName("myconn")
	if conn != "myconn" || path != "" {
		t.Errorf("got conn=%q path=%q", conn, path)
	}
}

func TestParseName_connOnlyWithLeadingSlash(t *testing.T) {
	conn, path := parseName("/myconn")
	if conn != "myconn" || path != "" {
		t.Errorf("got conn=%q path=%q", conn, path)
	}
}

func TestParseName_connAndPath(t *testing.T) {
	conn, path := parseName("/myconn/dir/file.txt")
	if conn != "myconn" || path != "dir/file.txt" {
		t.Errorf("got conn=%q path=%q", conn, path)
	}
}

func TestParseName_noLeadingSlash(t *testing.T) {
	conn, path := parseName("myconn/dir/file.txt")
	if conn != "myconn" || path != "dir/file.txt" {
		t.Errorf("got conn=%q path=%q", conn, path)
	}
}

// --- lastName tests ---

func TestLastName_noSlash(t *testing.T) {
	if got := lastName("file.txt"); got != "file.txt" {
		t.Errorf("got %q", got)
	}
}

func TestLastName_withSlash(t *testing.T) {
	if got := lastName("dir/file.txt"); got != "file.txt" {
		t.Errorf("got %q", got)
	}
}

func TestLastName_trailingSlash(t *testing.T) {
	if got := lastName("dir/sub/"); got != "sub" {
		t.Errorf("got %q", got)
	}
}

func TestLastName_nested(t *testing.T) {
	if got := lastName("a/b/c/d"); got != "d" {
		t.Errorf("got %q", got)
	}
}

// --- Stat tests ---

func TestStat_root(t *testing.T) {
	mc := &mockClient{}
	fs := NewFromAPIClient(mc)
	fi, err := fs.Stat("")
	if err != nil {
		t.Fatal(err)
	}
	if !fi.IsDir() {
		t.Error("root should be a directory")
	}
}

func TestStat_connectionRoot_exists(t *testing.T) {
	mc := &mockClient{
		conns: []client.Connection{{Name: "myconn", Kind: "aws_s3"}},
	}
	fs := NewFromAPIClient(mc)
	fi, err := fs.Stat("/myconn")
	if err != nil {
		t.Fatal(err)
	}
	if !fi.IsDir() {
		t.Error("connection root should be a directory")
	}
	if fi.Name() != "myconn" {
		t.Errorf("expected name %q, got %q", "myconn", fi.Name())
	}
}

func TestStat_connectionRoot_missing(t *testing.T) {
	mc := &mockClient{
		conns: []client.Connection{{Name: "other", Kind: "aws_s3"}},
	}
	fs := NewFromAPIClient(mc)
	_, err := fs.Stat("/missing")
	if !errors.Is(err, os.ErrNotExist) {
		t.Errorf("expected ErrNotExist, got %v", err)
	}
}

func TestStat_file_found(t *testing.T) {
	size := int64(100)
	mc := &mockClient{
		conns: []client.Connection{{Name: "myconn", Kind: "aws_s3"}},
		objects: map[string][]client.Object{
			"myconn:": {{Path: "file.txt", Size: &size}},
		},
	}
	fs := NewFromAPIClient(mc)
	fi, err := fs.Stat("/myconn/file.txt")
	if err != nil {
		t.Fatal(err)
	}
	if fi.IsDir() {
		t.Error("file should not be a directory")
	}
	if fi.Size() != 100 {
		t.Errorf("expected size 100, got %d", fi.Size())
	}
}

func TestStat_file_missingReturnsErrNotExist(t *testing.T) {
	mc := &mockClient{
		conns:   []client.Connection{{Name: "myconn", Kind: "aws_s3"}},
		objects: map[string][]client.Object{"myconn:": {}},
	}
	fs := NewFromAPIClient(mc)
	_, err := fs.Stat("/myconn/missing.txt")
	if !errors.Is(err, os.ErrNotExist) {
		t.Errorf("expected ErrNotExist, got %v", err)
	}
}

func TestStat_dirInferredFromChildren(t *testing.T) {
	size := int64(10)
	mc := &mockClient{
		conns: []client.Connection{{Name: "myconn", Kind: "aws_s3"}},
		objects: map[string][]client.Object{
			// Stat("/myconn/subdir") enumerates with parentPrefix=""
			"myconn:": {{Path: "subdir/file.txt", Size: &size}},
		},
	}
	fs := NewFromAPIClient(mc)
	fi, err := fs.Stat("/myconn/subdir")
	if err != nil {
		t.Fatal(err)
	}
	if !fi.IsDir() {
		t.Error("expected directory inferred from children")
	}
}

// --- OpenFile tests ---

func TestOpenFile_rootListsConnections(t *testing.T) {
	mc := &mockClient{
		conns: []client.Connection{
			{Name: "conn1", Kind: "aws_s3"},
			{Name: "conn2", Kind: "gdrive_oauth2"},
		},
	}
	fs := NewFromAPIClient(mc)
	f, err := fs.OpenFile("", os.O_RDONLY, 0)
	if err != nil {
		t.Fatal(err)
	}
	infos, err := f.Readdir(0)
	if err != nil && err != io.EOF {
		t.Fatal(err)
	}
	if len(infos) != 2 {
		t.Fatalf("expected 2 entries, got %d", len(infos))
	}
}

func TestOpenFile_connNotFound(t *testing.T) {
	mc := &mockClient{conns: []client.Connection{{Name: "other", Kind: "aws_s3"}}}
	fs := NewFromAPIClient(mc)
	_, err := fs.OpenFile("/missing", os.O_RDONLY, 0)
	if !errors.Is(err, os.ErrNotExist) {
		t.Errorf("expected ErrNotExist, got %v", err)
	}
}

func TestOpenFile_writeFlagReturnsWriteFile(t *testing.T) {
	mc := &mockClient{conns: []client.Connection{{Name: "myconn", Kind: "aws_s3"}}}
	fs := NewFromAPIClient(mc)
	f, err := fs.OpenFile("/myconn/new.txt", os.O_WRONLY|os.O_CREATE, 0666)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := f.(*writeFile); !ok {
		t.Errorf("expected *writeFile, got %T", f)
	}
}

func TestOpenFile_readExistingFile(t *testing.T) {
	size := int64(5)
	mc := &mockClient{
		conns:   []client.Connection{{Name: "myconn", Kind: "aws_s3"}},
		objects: map[string][]client.Object{"myconn:": {{Path: "readme.txt", Size: &size}}},
		readData: map[string][]byte{"myconn:readme.txt": []byte("hello")},
	}
	fs := NewFromAPIClient(mc)
	f, err := fs.OpenFile("/myconn/readme.txt", os.O_RDONLY, 0)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := f.(*readFile); !ok {
		t.Errorf("expected *readFile, got %T", f)
	}
}

func TestOpenFile_dirPathReturnsStreamingDirFile(t *testing.T) {
	size := int64(1)
	mc := &mockClient{
		conns: []client.Connection{{Name: "myconn", Kind: "aws_s3"}},
		// Enumerate parent prefix "" to determine subdir is a dir
		objects: map[string][]client.Object{
			"myconn:": {{Path: "subdir/file.txt", Size: &size}},
			// openDirStream uses prefix "subdir/"
			"myconn:subdir/": {{Path: "subdir/file.txt", Size: &size}},
		},
	}
	fs := NewFromAPIClient(mc)
	f, err := fs.OpenFile("/myconn/subdir", os.O_RDONLY, 0)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := f.(*streamingDirFile); !ok {
		t.Errorf("expected *streamingDirFile, got %T", f)
	}
}

// --- Remove tests ---

func TestRemove_connOnly_returnsPermission(t *testing.T) {
	mc := &mockClient{}
	fs := NewFromAPIClient(mc)
	err := fs.Remove("/myconn")
	if !errors.Is(err, os.ErrPermission) {
		t.Errorf("expected ErrPermission, got %v", err)
	}
}

func TestRemove_root_returnsPermission(t *testing.T) {
	mc := &mockClient{}
	fs := NewFromAPIClient(mc)
	err := fs.Remove("")
	if !errors.Is(err, os.ErrPermission) {
		t.Errorf("expected ErrPermission, got %v", err)
	}
}

func TestRemove_validPath_delegatesToDelete(t *testing.T) {
	mc := &mockClient{}
	fs := NewFromAPIClient(mc)
	err := fs.Remove("/myconn/file.txt")
	if err != nil {
		t.Fatal(err)
	}
}

// --- RemoveAll tests ---

func TestRemoveAll_delegatesToRemove(t *testing.T) {
	mc := &mockClient{}
	fs := NewFromAPIClient(mc)
	// conn-only should return ErrPermission (same as Remove)
	err := fs.RemoveAll("/myconn")
	if !errors.Is(err, os.ErrPermission) {
		t.Errorf("expected ErrPermission, got %v", err)
	}
}

// --- Rename tests ---

func TestRename_missingConnReturnsPermission(t *testing.T) {
	mc := &mockClient{}
	fs := NewFromAPIClient(mc)
	err := fs.Rename("/myconn", "/other")
	if !errors.Is(err, os.ErrPermission) {
		t.Errorf("expected ErrPermission, got %v", err)
	}
}

func TestRename_happyPath_readWriteDelete(t *testing.T) {
	mc := &mockClient{
		readData: map[string][]byte{"src:old.txt": []byte("data")},
	}
	fs := NewFromAPIClient(mc)
	err := fs.Rename("/src/old.txt", "/dst/new.txt")
	if err != nil {
		t.Fatal(err)
	}
	// Should have called Write with the data
	if len(mc.writeCalls) != 1 {
		t.Fatalf("expected 1 write call, got %d", len(mc.writeCalls))
	}
	if mc.writeCalls[0].conn != "dst" || mc.writeCalls[0].path != "new.txt" {
		t.Errorf("unexpected write: %+v", mc.writeCalls[0])
	}
	if string(mc.writeCalls[0].data) != "data" {
		t.Errorf("unexpected write data: %q", mc.writeCalls[0].data)
	}
}

// --- Mkdir tests ---

func TestMkdir_connOnly_returnsExist(t *testing.T) {
	mc := &mockClient{}
	fs := NewFromAPIClient(mc)
	err := fs.Mkdir("/myconn", 0755)
	if !errors.Is(err, os.ErrExist) {
		t.Errorf("expected ErrExist, got %v", err)
	}
}

func TestMkdir_path_writesKeepSentinel(t *testing.T) {
	mc := &mockClient{}
	fs := NewFromAPIClient(mc)
	err := fs.Mkdir("/myconn/newdir", 0755)
	if err != nil {
		t.Fatal(err)
	}
	if len(mc.writeCalls) != 1 {
		t.Fatalf("expected 1 write call, got %d", len(mc.writeCalls))
	}
	if mc.writeCalls[0].path != "newdir/.keep" {
		t.Errorf("expected .keep sentinel, got path %q", mc.writeCalls[0].path)
	}
}

// --- connections cache tests ---

func TestConnections_TTLCaching(t *testing.T) {
	mc := &mockClient{conns: []client.Connection{{Name: "c1", Kind: "aws_s3"}}}
	fs := NewFromAPIClient(mc)

	// First call fetches from API
	c1, err := fs.connections()
	if err != nil || len(c1) != 1 {
		t.Fatalf("first call: err=%v len=%d", err, len(c1))
	}

	// Add a second connection to the mock but cache should still return 1
	mc.conns = append(mc.conns, client.Connection{Name: "c2", Kind: "aws_s3"})
	c2, err := fs.connections()
	if err != nil || len(c2) != 1 {
		t.Errorf("second call within TTL: expected cached 1 conn, got err=%v len=%d", err, len(c2))
	}
}

func TestConnections_TTLExpiry(t *testing.T) {
	mc := &mockClient{conns: []client.Connection{{Name: "c1", Kind: "aws_s3"}}}
	fs := NewFromAPIClient(mc)

	// Manually expire the TTL
	fs.connTTL = time.Now().Add(-1 * time.Second)
	mc.conns = append(mc.conns, client.Connection{Name: "c2", Kind: "aws_s3"})

	c, err := fs.connections()
	if err != nil || len(c) != 2 {
		t.Errorf("after TTL expiry: expected 2 conns, got err=%v len=%d", err, len(c))
	}
}

// --- dirFile tests ---

func TestDirFile_Readdir_countZeroReturnsAll(t *testing.T) {
	infos := []os.FileInfo{
		dirInfoFi("a"), dirInfoFi("b"), dirInfoFi("c"),
	}
	d := &dirFile{info: dirInfoFi("root"), children: infos}
	result, err := d.Readdir(0)
	if err != nil {
		t.Fatal(err)
	}
	if len(result) != 3 {
		t.Errorf("expected 3, got %d", len(result))
	}
}

func TestDirFile_Readdir_countPages(t *testing.T) {
	infos := []os.FileInfo{dirInfoFi("a"), dirInfoFi("b"), dirInfoFi("c")}
	d := &dirFile{info: dirInfoFi("root"), children: infos}

	r1, _ := d.Readdir(2)
	if len(r1) != 2 {
		t.Errorf("expected 2, got %d", len(r1))
	}
	r2, _ := d.Readdir(2)
	if len(r2) != 1 {
		t.Errorf("expected 1, got %d", len(r2))
	}
	_, err := d.Readdir(1)
	if err != io.EOF {
		t.Errorf("expected io.EOF, got %v", err)
	}
}

func TestDirFile_Readdirnames(t *testing.T) {
	infos := []os.FileInfo{dirInfoFi("foo"), dirInfoFi("bar")}
	d := &dirFile{info: dirInfoFi("root"), children: infos}
	names, err := d.Readdirnames(0)
	if err != nil {
		t.Fatal(err)
	}
	if len(names) != 2 || names[0] != "foo" || names[1] != "bar" {
		t.Errorf("unexpected names: %v", names)
	}
}

// --- readFile tests ---

func TestReadFile_Read_lazyLoadsAndCaches(t *testing.T) {
	mc := &mockClient{readData: map[string][]byte{"myconn:file.txt": []byte("hello")}}
	rf := &readFile{client: mc, conn: "myconn", path: "file.txt", info: &fileInfo{name: "file.txt"}}

	buf := make([]byte, 10)
	n, err := rf.Read(buf)
	if err != nil && err != io.EOF {
		t.Fatal(err)
	}
	if string(buf[:n]) != "hello" {
		t.Errorf("expected %q, got %q", "hello", buf[:n])
	}
	// Data should be cached; second read from beginning via seek
	rf.reader.Seek(0, io.SeekStart)
	n2, _ := rf.Read(buf)
	if string(buf[:n2]) != "hello" {
		t.Errorf("second read mismatch: got %q", buf[:n2])
	}
}

func TestReadFile_Read_errorPropagates(t *testing.T) {
	mc := &mockClient{readErr: errors.New("read failed")}
	rf := &readFile{client: mc, conn: "c", path: "f", info: &fileInfo{name: "f"}}
	_, err := rf.Read(make([]byte, 10))
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestReadFile_ReadAt(t *testing.T) {
	mc := &mockClient{readData: map[string][]byte{"c:f": []byte("hello world")}}
	rf := &readFile{client: mc, conn: "c", path: "f", info: &fileInfo{name: "f"}}
	buf := make([]byte, 5)
	n, err := rf.ReadAt(buf, 6)
	if err != nil && err != io.EOF {
		t.Fatal(err)
	}
	if string(buf[:n]) != "world" {
		t.Errorf("expected %q, got %q", "world", buf[:n])
	}
}

func TestReadFile_Seek(t *testing.T) {
	mc := &mockClient{readData: map[string][]byte{"c:f": []byte("abcde")}}
	rf := &readFile{client: mc, conn: "c", path: "f", info: &fileInfo{name: "f"}}
	pos, err := rf.Seek(2, io.SeekStart)
	if err != nil {
		t.Fatal(err)
	}
	if pos != 2 {
		t.Errorf("expected pos 2, got %d", pos)
	}
	buf := make([]byte, 3)
	n, _ := rf.Read(buf)
	if string(buf[:n]) != "cde" {
		t.Errorf("expected %q, got %q", "cde", buf[:n])
	}
}

// --- writeFile tests ---

func TestWriteFile_Write_buffersAndUploadsOnClose(t *testing.T) {
	mc := &mockClient{conns: []client.Connection{{Name: "myconn", Kind: "aws_s3"}}}
	fs := NewFromAPIClient(mc)
	f, err := fs.OpenFile("/myconn/out.txt", os.O_WRONLY|os.O_CREATE, 0666)
	if err != nil {
		t.Fatal(err)
	}
	f.Write([]byte("hello "))
	f.WriteString("world")

	if len(mc.writeCalls) != 0 {
		t.Error("expected no writes before Close")
	}
	if err := f.Close(); err != nil {
		t.Fatal(err)
	}
	if len(mc.writeCalls) != 1 {
		t.Fatalf("expected 1 write on Close, got %d", len(mc.writeCalls))
	}
	if string(mc.writeCalls[0].data) != "hello world" {
		t.Errorf("unexpected data: %q", mc.writeCalls[0].data)
	}
}

// --- streamingDirFile tests ---

func TestStreamingDirFile_Readdir_deduplication(t *testing.T) {
	size := int64(1)
	objCh := make(chan client.Object, 10)
	errCh := make(chan error, 1)
	objCh <- client.Object{Path: "dir/file1.txt", Size: &size}
	objCh <- client.Object{Path: "dir/file2.txt", Size: &size}
	objCh <- client.Object{Path: "file3.txt", Size: &size}
	close(objCh)
	close(errCh)

	d := &streamingDirFile{
		info:   dirInfoFi("root"),
		objCh:  objCh,
		errCh:  errCh,
		prefix: "",
		seen:   map[string]bool{},
	}

	infos, err := d.Readdir(0)
	if err != nil {
		t.Fatal(err)
	}
	// "dir" appears twice but should be deduplicated; "file3.txt" is separate
	if len(infos) != 2 {
		t.Errorf("expected 2 unique entries, got %d: %v", len(infos), infos)
	}
}

func TestStreamingDirFile_Readdir_mixedFilesAndDirs(t *testing.T) {
	size := int64(42)
	objCh := make(chan client.Object, 10)
	errCh := make(chan error, 1)
	objCh <- client.Object{Path: "sub/", Size: nil}     // dir
	objCh <- client.Object{Path: "readme.txt", Size: &size} // file
	close(objCh)
	close(errCh)

	d := &streamingDirFile{
		info:   dirInfoFi("root"),
		objCh:  objCh,
		errCh:  errCh,
		prefix: "",
		seen:   map[string]bool{},
	}

	infos, _ := d.Readdir(0)
	if len(infos) != 2 {
		t.Fatalf("expected 2 entries, got %d", len(infos))
	}
}

func TestStreamingDirFile_Readdir_countPositivePagesResults(t *testing.T) {
	size := int64(1)
	objCh := make(chan client.Object, 10)
	errCh := make(chan error, 1)
	for i := 0; i < 5; i++ {
		path := string(rune('a'+i)) + ".txt"
		objCh <- client.Object{Path: path, Size: &size}
	}
	close(objCh)
	close(errCh)

	d := &streamingDirFile{
		info:   dirInfoFi("root"),
		objCh:  objCh,
		errCh:  errCh,
		prefix: "",
		seen:   map[string]bool{},
	}

	// First batch of 2
	batch1, err := d.Readdir(2)
	if err != nil {
		t.Fatal(err)
	}
	if len(batch1) != 2 {
		t.Errorf("expected 2, got %d", len(batch1))
	}

	// Second batch of 2
	batch2, err := d.Readdir(2)
	if err != nil {
		t.Fatal(err)
	}
	if len(batch2) != 2 {
		t.Errorf("expected 2, got %d", len(batch2))
	}

	// Third batch: only 1 left
	batch3, err := d.Readdir(2)
	if err != nil {
		t.Fatal(err)
	}
	if len(batch3) != 1 {
		t.Errorf("expected 1, got %d", len(batch3))
	}

	// EOF
	_, err = d.Readdir(2)
	if err != io.EOF {
		t.Errorf("expected io.EOF, got %v", err)
	}
}

func TestStreamingDirFile_Readdirnames(t *testing.T) {
	size := int64(1)
	objCh := make(chan client.Object, 10)
	errCh := make(chan error, 1)
	objCh <- client.Object{Path: "foo.txt", Size: &size}
	objCh <- client.Object{Path: "bar.txt", Size: &size}
	close(objCh)
	close(errCh)

	d := &streamingDirFile{
		info:   dirInfoFi("root"),
		objCh:  objCh,
		errCh:  errCh,
		prefix: "",
		seen:   map[string]bool{},
	}

	names, err := d.Readdirnames(0)
	if err != nil {
		t.Fatal(err)
	}
	if len(names) != 2 {
		t.Errorf("expected 2 names, got %d", len(names))
	}
}

func TestStreamingDirFile_Readdir_errorSurfaced(t *testing.T) {
	objCh := make(chan client.Object)
	errCh := make(chan error, 1)
	errCh <- errors.New("stream error")
	close(objCh)

	d := &streamingDirFile{
		info:   dirInfoFi("root"),
		objCh:  objCh,
		errCh:  errCh,
		prefix: "",
		seen:   map[string]bool{},
	}

	_, err := d.Readdir(0)
	if err == nil || err == io.EOF {
		t.Errorf("expected stream error, got %v", err)
	}
}

// --- OpenFile Stat size test ---

func TestOpenFile_statReturnsSizeBeforeDownload(t *testing.T) {
	size := int64(1234)
	mc := &mockClient{
		conns:   []client.Connection{{Name: "myconn", Kind: "aws_s3"}},
		objects: map[string][]client.Object{"myconn:": {{Path: "big.bin", Size: &size}}},
	}
	fs := NewFromAPIClient(mc)
	f, err := fs.OpenFile("/myconn/big.bin", os.O_RDONLY, 0)
	if err != nil {
		t.Fatal(err)
	}
	fi, err := f.Stat()
	if err != nil {
		t.Fatal(err)
	}
	if fi.Size() != size {
		t.Errorf("expected size %d before download, got %d", size, fi.Size())
	}
	if mc.downloadCalls > 0 {
		t.Error("Stat() should not trigger Download()")
	}
}

