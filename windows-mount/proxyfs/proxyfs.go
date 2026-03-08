package proxyfs

import (
	"bytes"
	"errors"
	"io"
	"io/fs"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/fileproxy/windows-mount/client"
	"github.com/spf13/afero"
)

// APIClient is the minimal interface that FileProxyFS requires from the REST
// client. *client.FileProxyClient satisfies it automatically.
type APIClient interface {
	ListConnections() ([]client.Connection, error)
	Enumerate(conn, prefix string) ([]client.Object, error)
	EnumerateStream(conn, prefix string) (<-chan client.Object, <-chan error)
	Read(conn, path string) ([]byte, error)
	Write(conn, path string, data []byte) error
	Delete(conn, path string) error
}

// FileProxyFS implements afero.Fs backed by the FileProxy REST API.
type FileProxyFS struct {
	client APIClient

	connMu  sync.RWMutex
	connTTL time.Time
	conns   []client.Connection
}

func New(c *client.FileProxyClient) *FileProxyFS {
	return &FileProxyFS{client: c}
}

// NewFromAPIClient creates a FileProxyFS backed by any APIClient implementation.
// Useful for testing with a mock client.
func NewFromAPIClient(c APIClient) *FileProxyFS {
	return &FileProxyFS{client: c}
}

func (f *FileProxyFS) Name() string { return "FileProxyFS" }

func (f *FileProxyFS) connections() ([]client.Connection, error) {
	f.connMu.Lock()
	defer f.connMu.Unlock()
	if time.Now().Before(f.connTTL) {
		return f.conns, nil
	}
	conns, err := f.client.ListConnections()
	if err != nil {
		return nil, err
	}
	f.conns = conns
	f.connTTL = time.Now().Add(30 * time.Second)
	return conns, nil
}

func (f *FileProxyFS) connectionExists(name string) (bool, error) {
	conns, err := f.connections()
	if err != nil {
		return false, err
	}
	for _, c := range conns {
		if c.Name == name {
			return true, nil
		}
	}
	return false, nil
}

// parseName splits "/conn/path/to/file" into ("conn", "path/to/file").
func parseName(name string) (conn, path string) {
	name = strings.TrimPrefix(name, "/")
	if name == "" {
		return "", ""
	}
	parts := strings.SplitN(name, "/", 2)
	if len(parts) == 1 {
		return parts[0], ""
	}
	return parts[0], parts[1]
}

func lastName(p string) string {
	p = strings.TrimRight(p, "/")
	idx := strings.LastIndex(p, "/")
	if idx < 0 {
		return p
	}
	return p[idx+1:]
}

func dirInfoFi(name string) os.FileInfo {
	return &fileInfo{name: name, isDir: true}
}

// Stat returns FileInfo for the given path.
func (f *FileProxyFS) Stat(name string) (os.FileInfo, error) {
	conn, path := parseName(name)
	if conn == "" {
		return dirInfoFi(""), nil
	}
	exists, err := f.connectionExists(conn)
	if err != nil {
		return nil, err
	}
	if !exists {
		return nil, os.ErrNotExist
	}
	if path == "" {
		return dirInfoFi(conn), nil
	}

	// Enumerate the parent directory and look for the entry by name.
	// Never use the full path as the prefix — backends treat it as a folder name.
	idx := strings.LastIndex(path, "/")
	var parentPrefix, entryName string
	if idx < 0 {
		parentPrefix = ""
		entryName = path
	} else {
		parentPrefix = path[:idx+1]
		entryName = path[idx+1:]
	}

	objs, err := f.client.Enumerate(conn, parentPrefix)
	if err != nil {
		return nil, err
	}
	for _, o := range objs {
		rel := strings.TrimPrefix(o.Path, parentPrefix)
		first := strings.SplitN(rel, "/", 2)[0]
		if first != entryName {
			continue
		}
		if strings.Contains(rel, "/") {
			return dirInfoFi(entryName), nil
		}
		size := int64(0)
		if o.Size != nil {
			size = *o.Size
		}
		return &fileInfo{name: entryName, size: size}, nil
	}
	return nil, os.ErrNotExist
}

// Open opens name for reading.
func (f *FileProxyFS) Open(name string) (afero.File, error) {
	return f.OpenFile(name, os.O_RDONLY, 0)
}

// Create creates or truncates a file for writing.
func (f *FileProxyFS) Create(name string) (afero.File, error) {
	return f.OpenFile(name, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0666)
}

// OpenFile opens name with the given flags.
func (f *FileProxyFS) OpenFile(name string, flag int, perm os.FileMode) (afero.File, error) {
	conn, path := parseName(name)

	// Root: list all connections as directories.
	if conn == "" {
		conns, err := f.connections()
		if err != nil {
			return nil, err
		}
		infos := make([]os.FileInfo, len(conns))
		for i, c := range conns {
			infos[i] = dirInfoFi(c.Name)
		}
		return &dirFile{info: dirInfoFi(""), children: infos}, nil
	}

	exists, err := f.connectionExists(conn)
	if err != nil {
		return nil, err
	}
	if !exists {
		return nil, os.ErrNotExist
	}

	// Write / create.
	if flag&(os.O_WRONLY|os.O_RDWR|os.O_CREATE) != 0 {
		return &writeFile{
			client: f.client,
			conn:   conn,
			path:   path,
			info:   &fileInfo{name: lastName(path)},
			buf:    &bytes.Buffer{},
		}, nil
	}

	// Connection root directory.
	if path == "" {
		return f.openDirStream(conn, "")
	}

	// Determine file vs directory using parent prefix.
	idx := strings.LastIndex(path, "/")
	var parentPrefix, entryName string
	if idx < 0 {
		parentPrefix = ""
		entryName = path
	} else {
		parentPrefix = path[:idx+1]
		entryName = path[idx+1:]
	}

	objs, err := f.client.Enumerate(conn, parentPrefix)
	if err != nil {
		return nil, err
	}
	for _, o := range objs {
		rel := strings.TrimPrefix(o.Path, parentPrefix)
		first := strings.SplitN(rel, "/", 2)[0]
		if first != entryName {
			continue
		}
		if strings.Contains(rel, "/") {
			return f.openDirStream(conn, path+"/")
		}
		return &readFile{
			client: f.client,
			conn:   conn,
			path:   path,
			info:   &fileInfo{name: entryName},
		}, nil
	}
	return nil, os.ErrNotExist
}

// openDirStream returns a streamingDirFile that yields entries as the API
// delivers them page by page. Callers see the first results immediately
// without waiting for full enumeration.
func (f *FileProxyFS) openDirStream(conn, prefix string) (afero.File, error) {
	name := lastName(strings.TrimRight(prefix, "/"))
	if name == "" {
		name = conn
	}
	objCh, errCh := f.client.EnumerateStream(conn, prefix)
	return &streamingDirFile{
		info:   dirInfoFi(name),
		objCh:  objCh,
		errCh:  errCh,
		prefix: prefix,
		seen:   map[string]bool{},
	}, nil
}

func (f *FileProxyFS) Remove(name string) error {
	conn, path := parseName(name)
	if conn == "" || path == "" {
		return os.ErrPermission
	}
	return f.client.Delete(conn, path)
}

func (f *FileProxyFS) RemoveAll(path string) error { return f.Remove(path) }

func (f *FileProxyFS) Rename(oldname, newname string) error {
	oldConn, oldPath := parseName(oldname)
	newConn, newPath := parseName(newname)
	if oldConn == "" || oldPath == "" || newConn == "" || newPath == "" {
		return os.ErrPermission
	}
	data, err := f.client.Read(oldConn, oldPath)
	if err != nil {
		return err
	}
	if err := f.client.Write(newConn, newPath, data); err != nil {
		return err
	}
	return f.client.Delete(oldConn, oldPath)
}

func (f *FileProxyFS) Mkdir(name string, perm os.FileMode) error {
	conn, path := parseName(name)
	if conn == "" {
		return os.ErrPermission
	}
	if path == "" {
		return os.ErrExist
	}
	return f.client.Write(conn, strings.TrimRight(path, "/")+"/.keep", []byte{})
}

func (f *FileProxyFS) MkdirAll(path string, perm os.FileMode) error {
	return f.Mkdir(path, perm)
}

func (f *FileProxyFS) Chmod(name string, mode os.FileMode) error    { return nil }
func (f *FileProxyFS) Chown(name string, uid, gid int) error         { return nil }
func (f *FileProxyFS) Chtimes(name string, a, m time.Time) error     { return nil }

// --- fileInfo ---

type fileInfo struct {
	name  string
	size  int64
	isDir bool
}

func (fi *fileInfo) Name() string      { return fi.name }
func (fi *fileInfo) Size() int64       { return fi.size }
func (fi *fileInfo) Mode() os.FileMode {
	if fi.isDir {
		return os.ModeDir | 0755
	}
	return 0644
}
func (fi *fileInfo) ModTime() time.Time { return time.Time{} }
func (fi *fileInfo) IsDir() bool        { return fi.isDir }
func (fi *fileInfo) Sys() interface{}   { return nil }

// --- dirFile ---

type dirFile struct {
	info     os.FileInfo
	children []os.FileInfo
	pos      int
}

func (d *dirFile) Name() string                               { return d.info.Name() }
func (d *dirFile) Close() error                               { return nil }
func (d *dirFile) Stat() (os.FileInfo, error)                 { return d.info, nil }
func (d *dirFile) Sync() error                                { return nil }
func (d *dirFile) Truncate(int64) error                       { return errors.New("is a directory") }
func (d *dirFile) Read([]byte) (int, error)                   { return 0, errors.New("is a directory") }
func (d *dirFile) ReadAt([]byte, int64) (int, error)          { return 0, errors.New("is a directory") }
func (d *dirFile) Seek(int64, int) (int64, error)             { return 0, errors.New("is a directory") }
func (d *dirFile) Write([]byte) (int, error)                  { return 0, errors.New("is a directory") }
func (d *dirFile) WriteString(string) (int, error)            { return 0, errors.New("is a directory") }
func (d *dirFile) WriteAt([]byte, int64) (int, error)         { return 0, errors.New("is a directory") }

func (d *dirFile) Readdir(count int) ([]os.FileInfo, error) {
	if count <= 0 {
		result := d.children[d.pos:]
		d.pos = len(d.children)
		return result, nil
	}
	if d.pos >= len(d.children) {
		return nil, io.EOF
	}
	end := d.pos + count
	if end > len(d.children) {
		end = len(d.children)
	}
	result := d.children[d.pos:end]
	d.pos = end
	return result, nil
}

func (d *dirFile) Readdirnames(n int) ([]string, error) {
	infos, err := d.Readdir(n)
	names := make([]string, len(infos))
	for i, fi := range infos {
		names[i] = fi.Name()
	}
	return names, err
}

// --- readFile ---

type readFile struct {
	client APIClient
	conn   string
	path   string
	info   *fileInfo

	once   sync.Once
	data   []byte
	err    error
	reader *bytes.Reader
}

func (h *readFile) load() {
	h.once.Do(func() {
		h.data, h.err = h.client.Read(h.conn, h.path)
		if h.err == nil {
			h.info.size = int64(len(h.data))
			h.reader = bytes.NewReader(h.data)
		}
	})
}

func (h *readFile) Name() string                              { return h.info.Name() }
func (h *readFile) Close() error                              { return nil }
func (h *readFile) Stat() (os.FileInfo, error)                { return h.info, nil }
func (h *readFile) Sync() error                               { return nil }
func (h *readFile) Truncate(int64) error                      { return errors.New("read-only") }
func (h *readFile) Write([]byte) (int, error)                 { return 0, errors.New("read-only") }
func (h *readFile) WriteAt([]byte, int64) (int, error)        { return 0, errors.New("read-only") }
func (h *readFile) WriteString(string) (int, error)           { return 0, errors.New("read-only") }
func (h *readFile) Readdir(int) ([]os.FileInfo, error)        { return nil, errors.New("not a dir") }
func (h *readFile) Readdirnames(int) ([]string, error)        { return nil, errors.New("not a dir") }

func (h *readFile) Read(p []byte) (int, error) {
	h.load()
	if h.err != nil {
		return 0, h.err
	}
	return h.reader.Read(p)
}

func (h *readFile) ReadAt(p []byte, off int64) (int, error) {
	h.load()
	if h.err != nil {
		return 0, h.err
	}
	return h.reader.ReadAt(p, off)
}

func (h *readFile) Seek(off int64, whence int) (int64, error) {
	h.load()
	if h.err != nil {
		return 0, h.err
	}
	return h.reader.Seek(off, whence)
}

// --- writeFile ---

type writeFile struct {
	client APIClient
	conn   string
	path   string
	info   *fileInfo
	buf    *bytes.Buffer
}

func (w *writeFile) Name() string                              { return w.info.Name() }
func (w *writeFile) Stat() (os.FileInfo, error)                { return w.info, nil }
func (w *writeFile) Sync() error                               { return nil }
func (w *writeFile) Truncate(int64) error                      { w.buf.Reset(); return nil }
func (w *writeFile) Read([]byte) (int, error)                  { return 0, errors.New("write-only") }
func (w *writeFile) ReadAt([]byte, int64) (int, error)         { return 0, errors.New("write-only") }
func (w *writeFile) Seek(int64, int) (int64, error)            { return 0, errors.New("write-only") }
func (w *writeFile) Readdir(int) ([]os.FileInfo, error)        { return nil, errors.New("not a dir") }
func (w *writeFile) Readdirnames(int) ([]string, error)        { return nil, errors.New("not a dir") }
func (w *writeFile) WriteString(s string) (int, error)         { return w.buf.WriteString(s) }
func (w *writeFile) Write(p []byte) (int, error)               { return w.buf.Write(p) }
func (w *writeFile) WriteAt(p []byte, off int64) (int, error)  { return w.buf.Write(p) }

func (w *writeFile) Close() error {
	return w.client.Write(w.conn, w.path, w.buf.Bytes())
}

// --- streamingDirFile ---
// Yields directory entries as the API delivers them page by page.
// Readdir(N) blocks only until N unique entries are available, allowing the
// caller to flush partial results to the client without waiting for the full
// enumeration to finish.

type streamingDirFile struct {
	info    os.FileInfo
	objCh   <-chan client.Object
	errCh   <-chan error
	prefix  string
	seen    map[string]bool
	pending []os.FileInfo
	done    bool
	err     error // first error received from errCh, if any
}

// fill reads the next object from the channel and, if it produces a new unique
// entry, appends it to pending. Skips duplicate path components.
func (d *streamingDirFile) fill() {
	for {
		obj, ok := <-d.objCh
		if !ok {
			select {
			case err := <-d.errCh:
				d.err = err
			default:
			}
			d.done = true
			return
		}
		rel := strings.TrimPrefix(obj.Path, d.prefix)
		if rel == "" {
			continue
		}
		parts := strings.SplitN(rel, "/", 2)
		entry := parts[0]
		if d.seen[entry] {
			continue
		}
		d.seen[entry] = true
		var fi os.FileInfo
		if len(parts) > 1 {
			fi = dirInfoFi(entry)
		} else {
			size := int64(0)
			if obj.Size != nil {
				size = *obj.Size
			}
			fi = &fileInfo{name: entry, size: size}
		}
		d.pending = append(d.pending, fi)
		return
	}
}

func (d *streamingDirFile) Readdir(count int) ([]os.FileInfo, error) {
	if count <= 0 {
		// Drain everything.
		for !d.done {
			d.fill()
		}
		result := d.pending
		d.pending = nil
		if len(result) == 0 {
			if d.err != nil {
				return nil, d.err
			}
			return nil, io.EOF
		}
		return result, nil
	}
	// Fill up to count entries.
	for len(d.pending) < count && !d.done {
		d.fill()
	}
	if len(d.pending) == 0 {
		if d.err != nil {
			return nil, d.err
		}
		return nil, io.EOF
	}
	n := count
	if n > len(d.pending) {
		n = len(d.pending)
	}
	result := d.pending[:n]
	d.pending = d.pending[n:]
	return result, nil
}

func (d *streamingDirFile) Readdirnames(n int) ([]string, error) {
	infos, err := d.Readdir(n)
	names := make([]string, len(infos))
	for i, fi := range infos {
		names[i] = fi.Name()
	}
	return names, err
}

func (d *streamingDirFile) Name() string                               { return d.info.Name() }
func (d *streamingDirFile) Stat() (os.FileInfo, error)                 { return d.info, nil }
func (d *streamingDirFile) Close() error                               { return nil }
func (d *streamingDirFile) Sync() error                                { return nil }
func (d *streamingDirFile) Truncate(int64) error                       { return errors.New("is a directory") }
func (d *streamingDirFile) Read([]byte) (int, error)                   { return 0, errors.New("is a directory") }
func (d *streamingDirFile) ReadAt([]byte, int64) (int, error)          { return 0, errors.New("is a directory") }
func (d *streamingDirFile) Seek(int64, int) (int64, error)             { return 0, errors.New("is a directory") }
func (d *streamingDirFile) Write([]byte) (int, error)                  { return 0, errors.New("is a directory") }
func (d *streamingDirFile) WriteAt([]byte, int64) (int, error)         { return 0, errors.New("is a directory") }
func (d *streamingDirFile) WriteString(string) (int, error)            { return 0, errors.New("is a directory") }

// Compile-time interface checks.
var _ afero.Fs = (*FileProxyFS)(nil)
var _ afero.File = (*dirFile)(nil)
var _ afero.File = (*readFile)(nil)
var _ afero.File = (*writeFile)(nil)
var _ afero.File = (*streamingDirFile)(nil)
var _ fs.FileInfo = (*fileInfo)(nil)
