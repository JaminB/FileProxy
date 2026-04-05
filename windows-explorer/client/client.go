// Package client calls the FileProxy REST API.
package client

import (
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/url"
	"strings"
)

// Connection represents a FileProxy connection (storage backend).
type Connection struct {
	Name string `json:"name"`
	Kind string `json:"kind"`
}

// Object represents a file object returned by the enumerate endpoint.
type Object struct {
	Name         string  `json:"name"`
	Path         string  `json:"path"`
	Size         *int64  `json:"size"`
	LastModified *string `json:"last_modified"`
}

// EnumeratePage is one page of results from the objects endpoint.
type EnumeratePage struct {
	Objects    []Object `json:"objects"`
	NextCursor string   `json:"next_cursor"`
}

// PendingUpload is an in-flight or queued upload from the pending/ endpoint.
type PendingUpload struct {
	ID           string `json:"id"`
	Path         string `json:"path"`
	ExpectedSize int64  `json:"expected_size"`
	Status       string `json:"status"` // "pending", "uploading", "failed"
}

// Client calls the FileProxy REST API with Bearer token auth.
type Client struct {
	BaseURL string
	APIKey  string
	http    *http.Client
}

// New creates a new Client.
func New(baseURL, apiKey string) *Client {
	return &Client{
		BaseURL: strings.TrimRight(baseURL, "/"),
		APIKey:  apiKey,
		http:    &http.Client{},
	}
}

func (c *Client) newRequest(method, path string, body io.Reader) (*http.Request, error) {
	req, err := http.NewRequest(method, c.BaseURL+path, body)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+c.APIKey)
	return req, nil
}

func (c *Client) do(req *http.Request) (*http.Response, error) {
	resp, err := c.http.Do(req) //#nosec G107 -- BaseURL is user-configured, not attacker-controlled
	if err != nil {
		return nil, err
	}
	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	return resp, nil
}

// ListConnections returns all connections visible to the authenticated user.
func (c *Client) ListConnections() ([]Connection, error) {
	req, err := c.newRequest("GET", "/api/v1/files/", nil)
	if err != nil {
		return nil, err
	}
	resp, err := c.do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var result []Connection
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decoding connections: %w", err)
	}
	return result, nil
}

// EnumeratePage fetches one page of objects for conn at prefix.
func (c *Client) EnumeratePage(conn, prefix, cursor string) (EnumeratePage, error) {
	q := url.Values{}
	q.Set("page_size", "1000")
	if prefix != "" {
		q.Set("prefix", prefix)
	}
	if cursor != "" {
		q.Set("cursor", cursor)
	}
	p := fmt.Sprintf("/api/v1/files/%s/objects/?%s", url.PathEscape(conn), q.Encode())
	req, err := c.newRequest("GET", p, nil)
	if err != nil {
		return EnumeratePage{}, err
	}
	resp, err := c.do(req)
	if err != nil {
		return EnumeratePage{}, err
	}
	defer resp.Body.Close()
	var page EnumeratePage
	if err := json.NewDecoder(resp.Body).Decode(&page); err != nil {
		return EnumeratePage{}, fmt.Errorf("decoding objects: %w", err)
	}
	return page, nil
}

// Enumerate fetches all objects under prefix (handles pagination automatically).
func (c *Client) Enumerate(conn, prefix string) ([]Object, error) {
	var all []Object
	cursor := ""
	for {
		page, err := c.EnumeratePage(conn, prefix, cursor)
		if err != nil {
			return nil, err
		}
		all = append(all, page.Objects...)
		if page.NextCursor == "" {
			break
		}
		cursor = page.NextCursor
	}
	return all, nil
}

// Download opens a streaming download for path in conn.
// Returns the response body and Content-Length (-1 if unknown).
// The caller must close the returned ReadCloser.
func (c *Client) Download(conn, path string) (io.ReadCloser, int64, error) {
	q := url.Values{"path": {path}}
	endpoint := fmt.Sprintf("/api/v1/files/%s/path/?%s", url.PathEscape(conn), q.Encode())
	req, err := c.newRequest("GET", endpoint, nil)
	if err != nil {
		return nil, -1, err
	}
	resp, err := c.do(req)
	if err != nil {
		return nil, -1, err
	}
	return resp.Body, resp.ContentLength, nil
}

// Upload uploads r to path in conn using multipart/form-data.
// size is used to update progress; pass -1 if unknown.
// Returns queued=true when the server accepted it asynchronously (HTTP 202).
func (c *Client) Upload(conn, path string, r io.Reader) (queued bool, err error) {
	endpoint := fmt.Sprintf("/api/v1/files/%s/path/", url.PathEscape(conn))
	filename := path
	if idx := strings.LastIndex(path, "/"); idx >= 0 {
		filename = path[idx+1:]
	}

	pr, pw := io.Pipe()
	mw := multipart.NewWriter(pw)
	go func() {
		var werr error
		defer func() { pw.CloseWithError(werr) }()
		if werr = mw.WriteField("path", path); werr != nil {
			return
		}
		part, perr := mw.CreateFormFile("file", filename)
		if perr != nil {
			werr = perr
			return
		}
		if _, werr = io.Copy(part, r); werr != nil {
			return
		}
		werr = mw.Close()
	}()

	req, reqErr := c.newRequest("POST", endpoint, pr)
	if reqErr != nil {
		pr.CloseWithError(reqErr)
		return false, reqErr
	}
	req.Header.Set("Content-Type", mw.FormDataContentType())

	resp, doErr := c.http.Do(req) //#nosec G107
	if doErr != nil {
		return false, doErr
	}
	defer resp.Body.Close()

	if resp.StatusCode == 202 {
		return true, nil
	}
	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		return false, fmt.Errorf("HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	return false, nil
}

// Delete removes path from conn.
func (c *Client) Delete(conn, path string) error {
	q := url.Values{"path": {path}}
	endpoint := fmt.Sprintf("/api/v1/files/%s/path/?%s", url.PathEscape(conn), q.Encode())
	req, err := c.newRequest("DELETE", endpoint, nil)
	if err != nil {
		return err
	}
	resp, err := c.do(req)
	if err != nil {
		return err
	}
	resp.Body.Close()
	return nil
}

// PendingUploads returns all in-progress or queued uploads for conn.
func (c *Client) PendingUploads(conn string) ([]PendingUpload, error) {
	endpoint := fmt.Sprintf("/api/v1/files/%s/pending/", url.PathEscape(conn))
	req, err := c.newRequest("GET", endpoint, nil)
	if err != nil {
		return nil, err
	}
	resp, err := c.do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var result []PendingUpload
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decoding pending uploads: %w", err)
	}
	return result, nil
}
