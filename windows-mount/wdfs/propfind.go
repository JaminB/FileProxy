package wdfs

import (
	"fmt"
	"net/http"
	"net/url"
	"os"
	"path"
	"strings"
	"time"
)

// PropfindHandler handles WebDAV PROPFIND requests with streaming XML output.
// It writes and flushes each batch of directory entries as they arrive from the
// API, so Windows Explorer starts rendering files before enumeration finishes.
type PropfindHandler struct {
	fs *FS
}

func NewPropfindHandler(fs *FS) *PropfindHandler {
	return &PropfindHandler{fs: fs}
}

func (h *PropfindHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	name := path.Clean(r.URL.Path)
	if name == "." {
		name = "/"
	}

	depth := r.Header.Get("Depth")
	if depth == "" {
		depth = "infinity"
	}
	// Treat infinity as 1 to avoid recursive explosion.
	if depth == "infinity" {
		depth = "1"
	}

	fi, err := h.fs.Stat(ctx, name)
	if os.IsNotExist(err) {
		http.Error(w, "Not Found", http.StatusNotFound)
		return
	}
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "text/xml; charset=utf-8")
	w.WriteHeader(207)

	flusher, canFlush := w.(http.Flusher)

	fmt.Fprint(w, `<?xml version="1.0" encoding="UTF-8"?>`+"\n")
	fmt.Fprint(w, `<D:multistatus xmlns:D="DAV:">`+"\n")

	// Write the requested resource itself.
	writeDAVResponse(w, name, fi)

	if canFlush {
		flusher.Flush()
	}

	if depth == "0" || !fi.IsDir() {
		fmt.Fprint(w, `</D:multistatus>`)
		if canFlush {
			flusher.Flush()
		}
		return
	}

	// Stream children in batches, flushing after each so the client sees
	// entries progressively rather than waiting for full enumeration.
	f, err := h.fs.OpenFile(ctx, name, os.O_RDONLY, 0)
	if err != nil {
		fmt.Fprintf(os.Stderr, "  [propfind] OpenFile(%q): %v\n", name, err)
		fmt.Fprint(w, `</D:multistatus>`)
		if canFlush {
			flusher.Flush()
		}
		return
	}
	defer f.Close()

	const batchSize = 20
	total := 0
	for {
		children, err := f.Readdir(batchSize)
		for _, child := range children {
			childPath := path.Join(name, child.Name())
			writeDAVResponse(w, childPath, child)
			total++
		}
		if len(children) > 0 && canFlush {
			flusher.Flush()
			fmt.Fprintf(os.Stderr, "  [propfind] flushed %d entries for %q\n", total, name)
		}
		if err != nil || len(children) < batchSize {
			break
		}
	}

	fmt.Fprint(w, `</D:multistatus>`)
	if canFlush {
		flusher.Flush()
	}
	fmt.Fprintf(os.Stderr, "  [propfind] done %q — %d total entries\n", name, total)
}

// writeDAVResponse writes a single <D:response> element for the given path and FileInfo.
func writeDAVResponse(w http.ResponseWriter, name string, fi os.FileInfo) {
	href := davHref(name, fi.IsDir())

	modTime := fi.ModTime()
	if modTime.IsZero() {
		modTime = time.Unix(0, 0)
	}

	fmt.Fprintf(w, "<D:response>\n")
	fmt.Fprintf(w, "  <D:href>%s</D:href>\n", xmlEscape(href)) // #nosec G705 -- href is URL-encoded then XML-escaped
	fmt.Fprintf(w, "  <D:propstat>\n")
	fmt.Fprintf(w, "    <D:prop>\n")

	if fi.IsDir() {
		fmt.Fprintf(w, "      <D:resourcetype><D:collection/></D:resourcetype>\n")
	} else {
		fmt.Fprintf(w, "      <D:resourcetype/>\n")
		fmt.Fprintf(w, "      <D:getcontentlength>%d</D:getcontentlength>\n", fi.Size()) // #nosec G705 -- integer format verb, no injection possible
		fmt.Fprintf(w, "      <D:getcontenttype>application/octet-stream</D:getcontenttype>\n")
	}

	fmt.Fprintf(w, "      <D:displayname>%s</D:displayname>\n", xmlEscape(fi.Name())) // #nosec G705 -- value is XML-escaped
	fmt.Fprintf(w, "      <D:getlastmodified>%s</D:getlastmodified>\n", // #nosec G705 -- formatted time literal, no injection possible
		modTime.UTC().Format(http.TimeFormat))
	fmt.Fprintf(w, "      <D:creationdate>%s</D:creationdate>\n", // #nosec G705 -- formatted time literal, no injection possible
		modTime.UTC().Format(time.RFC3339))

	fmt.Fprintf(w, "    </D:prop>\n")
	fmt.Fprintf(w, "    <D:status>HTTP/1.1 200 OK</D:status>\n")
	fmt.Fprintf(w, "  </D:propstat>\n")
	fmt.Fprintf(w, "</D:response>\n")
}

// davHref returns the URL-encoded href for a WebDAV response entry.
func davHref(p string, isDir bool) string {
	segments := strings.Split(p, "/")
	for i, s := range segments {
		segments[i] = url.PathEscape(s)
	}
	encoded := strings.Join(segments, "/")
	if isDir && !strings.HasSuffix(encoded, "/") {
		encoded += "/"
	}
	return encoded
}

func xmlEscape(s string) string {
	s = strings.ReplaceAll(s, "&", "&amp;")
	s = strings.ReplaceAll(s, "<", "&lt;")
	s = strings.ReplaceAll(s, ">", "&gt;")
	s = strings.ReplaceAll(s, `"`, "&quot;")
	return s
}
