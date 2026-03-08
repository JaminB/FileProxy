package client

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
)

// Connection represents a FileProxy connection.
type Connection struct {
	Name string `json:"name"`
	Kind string `json:"kind"`
}

// Object represents a file object returned by the enumerate endpoint.
type Object struct {
	Path string `json:"path"`
	Size *int64 `json:"size"`
}

// FileProxyClient calls the FileProxy REST API.
type FileProxyClient struct {
	BaseURL string
	APIKey  string
	http    *http.Client
}

// New creates a new FileProxyClient.
func New(baseURL, apiKey string) *FileProxyClient {
	return &FileProxyClient{
		BaseURL: strings.TrimRight(baseURL, "/"),
		APIKey:  apiKey,
		http:    &http.Client{},
	}
}

func (c *FileProxyClient) newRequest(method, path string, body io.Reader) (*http.Request, error) {
	req, err := http.NewRequest(method, c.BaseURL+path, body)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+c.APIKey)
	return req, nil
}

func (c *FileProxyClient) do(req *http.Request) (*http.Response, error) {
	resp, err := c.http.Do(req) // #nosec G704 -- BaseURL is user-configured (desktop client), not attacker-controlled
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
func (c *FileProxyClient) ListConnections() ([]Connection, error) {
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

type enumeratePage struct {
	Objects    []Object `json:"objects"`
	NextCursor string   `json:"next_cursor"`
}

func (c *FileProxyClient) fetchPage(conn, prefix, cursor string) (enumeratePage, error) {
	q := url.Values{}
	if prefix != "" {
		q.Set("prefix", prefix)
	}
	if cursor != "" {
		q.Set("cursor", cursor)
	}
	p := fmt.Sprintf("/api/v1/files/%s/objects/", url.PathEscape(conn))
	if len(q) > 0 {
		p += "?" + q.Encode()
	}
	req, err := c.newRequest("GET", p, nil)
	if err != nil {
		return enumeratePage{}, err
	}
	resp, err := c.do(req)
	if err != nil {
		return enumeratePage{}, err
	}
	defer resp.Body.Close()
	var page enumeratePage
	if err := json.NewDecoder(resp.Body).Decode(&page); err != nil {
		return enumeratePage{}, fmt.Errorf("decoding objects: %w", err)
	}
	return page, nil
}

// Enumerate fetches all objects for conn with the given prefix (handles pagination).
func (c *FileProxyClient) Enumerate(conn, prefix string) ([]Object, error) {
	var all []Object
	cursor := ""
	for {
		page, err := c.fetchPage(conn, prefix, cursor)
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

// EnumerateStream fetches objects page by page in a goroutine, sending each
// object to the returned channel as it arrives. Errors are sent to errCh.
// Both channels are closed when done.
func (c *FileProxyClient) EnumerateStream(conn, prefix string) (<-chan Object, <-chan error) {
	objCh := make(chan Object, 100)
	errCh := make(chan error, 1)
	go func() {
		defer close(objCh)
		defer close(errCh)
		cursor := ""
		for {
			page, err := c.fetchPage(conn, prefix, cursor)
			if err != nil {
				errCh <- err
				return
			}
			for _, obj := range page.Objects {
				objCh <- obj
			}
			if page.NextCursor == "" {
				return
			}
			cursor = page.NextCursor
		}
	}()
	return objCh, errCh
}

// Read fetches object data for the given path in conn.
func (c *FileProxyClient) Read(conn, path string) ([]byte, error) {
	q := url.Values{"path": {path}}
	endpoint := fmt.Sprintf("/api/v1/files/%s/read/?%s", url.PathEscape(conn), q.Encode())
	req, err := c.newRequest("GET", endpoint, nil)
	if err != nil {
		return nil, err
	}
	resp, err := c.do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var result struct {
		DataBase64 string `json:"data_base64"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decoding read response: %w", err)
	}
	data, err := base64.StdEncoding.DecodeString(result.DataBase64)
	if err != nil {
		return nil, fmt.Errorf("decoding base64: %w", err)
	}
	return data, nil
}

// Write uploads data to the given path in conn.
func (c *FileProxyClient) Write(conn, path string, data []byte) error {
	q := url.Values{"path": {path}}
	endpoint := fmt.Sprintf("/api/v1/files/%s/write/?%s", url.PathEscape(conn), q.Encode())
	body, err := json.Marshal(struct {
		DataBase64 string `json:"data_base64"`
	}{DataBase64: base64.StdEncoding.EncodeToString(data)})
	if err != nil {
		return err
	}
	req, err := c.newRequest("POST", endpoint, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.do(req)
	if err != nil {
		return err
	}
	resp.Body.Close()
	return nil
}

// Delete removes the object at path in conn.
func (c *FileProxyClient) Delete(conn, path string) error {
	q := url.Values{"path": {path}}
	endpoint := fmt.Sprintf("/api/v1/files/%s/object/?%s", url.PathEscape(conn), q.Encode())
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
