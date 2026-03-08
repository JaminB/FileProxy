// Package wdfs adapts proxyfs.FileProxyFS (afero.Fs) to webdav.FileSystem,
// with structured verbose logging at every filesystem operation so failures
// can be diagnosed from the terminal output alone.
package wdfs

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"

	fpfs "github.com/fileproxy/windows-mount/proxyfs"
	"golang.org/x/net/webdav"
)

// FS wraps a FileProxyFS as a webdav.FileSystem with verbose logging.
type FS struct {
	inner *fpfs.FileProxyFS
}

func New(fs *fpfs.FileProxyFS) *FS { return &FS{inner: fs} }

func (w *FS) Mkdir(ctx context.Context, name string, perm os.FileMode) error {
	err := w.inner.Mkdir(name, perm)
	if err != nil {
		fmt.Fprintf(os.Stderr, "  [fs] Mkdir(%q) ERROR: %v\n", name, err)
	} else {
		fmt.Fprintf(os.Stderr, "  [fs] Mkdir(%q) OK\n", name)
	}
	return err
}

func (w *FS) OpenFile(ctx context.Context, name string, flag int, perm os.FileMode) (webdav.File, error) {
	f, err := w.inner.OpenFile(name, flag, perm)
	if err != nil {
		fmt.Fprintf(os.Stderr, "  [fs] OpenFile(%q, flag=%d) ERROR: %v\n", name, flag, err)
		return nil, err
	}
	fi, _ := f.Stat()
	isDir := fi != nil && fi.IsDir()
	fmt.Fprintf(os.Stderr, "  [fs] OpenFile(%q, flag=%d) OK isDir=%v\n", name, flag, isDir)
	return &loggingFile{File: f.(webdav.File), name: name}, nil
}

func (w *FS) RemoveAll(ctx context.Context, name string) error {
	err := w.inner.RemoveAll(name)
	if err != nil {
		fmt.Fprintf(os.Stderr, "  [fs] RemoveAll(%q) ERROR: %v\n", name, err)
	} else {
		fmt.Fprintf(os.Stderr, "  [fs] RemoveAll(%q) OK\n", name)
	}
	return err
}

func (w *FS) Rename(ctx context.Context, oldName, newName string) error {
	err := w.inner.Rename(oldName, newName)
	if err != nil {
		fmt.Fprintf(os.Stderr, "  [fs] Rename(%q → %q) ERROR: %v\n", oldName, newName, err)
	} else {
		fmt.Fprintf(os.Stderr, "  [fs] Rename(%q → %q) OK\n", oldName, newName)
	}
	return err
}

func (w *FS) Stat(ctx context.Context, name string) (os.FileInfo, error) {
	fi, err := w.inner.Stat(name)
	if err != nil {
		fmt.Fprintf(os.Stderr, "  [fs] Stat(%q) ERROR: %v\n", name, err)
	} else {
		fmt.Fprintf(os.Stderr, "  [fs] Stat(%q) OK name=%q size=%d isDir=%v\n",
			name, fi.Name(), fi.Size(), fi.IsDir())
	}
	return fi, err
}

var _ webdav.FileSystem = (*FS)(nil)

// loggingFile wraps a webdav.File and logs Readdir and Read calls.
type loggingFile struct {
	webdav.File
	name string
}

func (f *loggingFile) Readdir(count int) ([]os.FileInfo, error) {
	infos, err := f.File.Readdir(count)
	if err != nil {
		fmt.Fprintf(os.Stderr, "  [fs] Readdir(%q, count=%d) ERROR: %v\n", f.name, count, err)
	} else {
		names := make([]string, len(infos))
		for i, fi := range infos {
			if fi.IsDir() {
				names[i] = fi.Name() + "/"
			} else {
				names[i] = fi.Name()
			}
		}
		fmt.Fprintf(os.Stderr, "  [fs] Readdir(%q) → %d entries: %v\n", f.name, len(infos), names)
	}
	return infos, err
}

func (f *loggingFile) Read(p []byte) (int, error) {
	n, err := f.File.Read(p)
	if err != nil && !errors.Is(err, io.EOF) {
		fmt.Fprintf(os.Stderr, "  [fs] Read(%q, buf=%d) n=%d ERROR: %v\n", f.name, len(p), n, err)
	} else {
		fmt.Fprintf(os.Stderr, "  [fs] Read(%q, buf=%d) n=%d\n", f.name, len(p), n)
	}
	return n, err
}
