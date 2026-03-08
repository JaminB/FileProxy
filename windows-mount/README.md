# FileProxy Windows Mount

Mount FileProxy connections as a Windows drive letter in Explorer.

The binary starts a local WebDAV server backed by the FileProxy REST API, then maps
a drive letter using the Windows WebClient service (`net use`). No additional
software or runtimes are required — it is a single static `.exe`.

---

## Prerequisites

- **Go 1.21+** (for building only — the compiled binary has no runtime dependency)
- **Windows 7 or later** (amd64 or 386)
- **WebClient service** must be running on your machine:
  ```
  sc query WebClient
  ```
  If it shows `STOPPED`, start it:
  ```
  sc start WebClient
  ```
  The service is enabled by default on Windows 7–11 but may be disabled on some
  enterprise configurations.

---

## Build

From the `windows-mount/` directory:

```bash
# Fetch dependencies
go mod download

# 64-bit (Windows 7+, recommended)
GOOS=windows GOARCH=amd64 go build -ldflags="-s -w" -o dist/fileproxy-mount-amd64.exe .

# 32-bit (Windows XP+)
GOOS=windows GOARCH=386 go build -ldflags="-s -w" -o dist/fileproxy-mount-386.exe .
```

`-ldflags="-s -w"` strips debug info for a smaller binary.

---

## First-time setup: create an API key

1. Start FileProxy: `cd fileproxy && python manage.py runserver`
2. Log in at `http://localhost:8000`
3. Go to your profile (top-right corner) → **API Keys** → **Create API key**
4. Copy the token — you will only see it once

---

## Usage

```
fileproxy-mount-amd64.exe mount [flags]
```

| Flag | Default | Description |
|---|---|---|
| `--server-url` | *(required first time)* | FileProxy server base URL, e.g. `http://localhost:8000` |
| `--api-key` | *(prompted if omitted)* | JWT API key created in the web UI |
| `--port` | `6789` | Local port for the WebDAV server |
| `--drive` | `F` | Drive letter to map (without colon) |

### Example

```powershell
.\fileproxy-mount-amd64.exe mount `
  --server-url http://localhost:8000 `
  --api-key eyJhbGciOi... `
  --drive F `
  --port 6789
```

On the first successful connection, `--server-url` and `--api-key` are saved to
`%APPDATA%\FileProxyMount\config.json`. Subsequent runs can omit both flags.

Press **Ctrl+C** to unmount the drive and exit cleanly.

---

## Path structure

```
F:\                        ← root: one subdirectory per connection
F:\my-s3-bucket\           ← connection "my-s3-bucket"
F:\my-s3-bucket\docs\      ← virtual folder (prefix "docs/")
F:\my-s3-bucket\docs\report.pdf   ← object "docs/report.pdf"
```

Virtual folders are derived by splitting object keys on `/`. The backend itself
stores flat paths (e.g. S3 keys like `docs/report.pdf`).

---

## How it works

1. The binary authenticates to FileProxy using your JWT API key.
2. It starts an HTTP WebDAV server on `localhost:<port>`.
3. WebDAV requests are translated to FileProxy REST API calls:
   - Directory listing → `GET /api/v1/files/<conn>/objects/?prefix=...`
   - File read → `GET /api/v1/files/<conn>/read/?path=...`
   - File write → `POST /api/v1/files/<conn>/write/?path=...`
   - File delete → `DELETE /api/v1/files/<conn>/object/?path=...`
4. `net use <drive>: http://localhost:<port>` maps the drive.
   Windows WebClient handles HTTP WebDAV on `localhost` without requiring HTTPS.
5. On Ctrl+C, `net use <drive>: /delete` unmounts the drive.

---

## Troubleshooting

**"System error 67: The network name cannot be found"**
The WebClient service is not running. Start it:
```
sc start WebClient
```

**"System error 85: The local device name is already in use"**
The drive letter is already mapped. Use a different `--drive` letter, or run:
```
net use F: /delete /y
```

**Port already in use**
Change the port with `--port 7890` (or any free port).

**HTTPS requirement**
Windows WebDAV over plain HTTP only works for `localhost`. If FileProxy runs on
a remote host, run this binary on your local machine and point `--server-url` at
the remote server (the binary proxies all calls through its local WebDAV server).
If the remote server uses HTTPS, it works without any special configuration.

**Large files**
File contents are read entirely into memory before being served to Windows
(the FileProxy API returns base64-encoded JSON). For very large files, this may
cause high memory usage. A streaming download endpoint is a planned improvement.
