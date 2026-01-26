# FileProxy

FileProxy exposes a folder in object storage as a simple, authenticated HTTP API.

It provides a thin read/write proxy over storage systems like S3, allowing applications to interact with files over HTTP without embedding storage SDKs, credentials, or custom glue code.

This is not a sync tool, workflow engine, or file manager.
It is a controlled access layer.

---

## What FileProxy Is For

FileProxy is useful when you need to:

- Read and write files over HTTP
- Avoid distributing cloud storage credentials
- Expose storage-backed artifacts to internal or external services
- Decouple application logic from storage APIs

Common use cases:
- Internal tools exchanging CSVs, reports, or build artifacts
- Data pipelines publishing intermediate outputs
- SaaS products exposing generated files to customers
- Simple integrations that need file access but not full SDKs

---

## What FileProxy Is Not

FileProxy intentionally does **not** provide:

- File synchronization
- Transformations or processing
- Webhooks or workflows
- UI-based file browsing
- Complex permission hierarchies

If you need those, this is the wrong tool.

---

## Core Concepts

### Storage Source
A connected storage backend (e.g. an S3 bucket and prefix).

### Path
A logical file path rooted at the configured storage prefix.

Example:
```
/reports/2026/january.csv
```

### Token
An API token used to authenticate requests.

---

## API Overview

All requests are authenticated using a bearer token.

```
Authorization: Bearer <token>
```

### List Files

Returns files and folders at a given path.

```
GET /v1/files?path=/reports
```

Example response:
```json
[
  {
    "name": "january.csv",
    "size": 18342,
    "updated_at": "2026-01-12T18:22:10Z"
  },
  {
    "name": "february.csv",
    "size": 19401,
    "updated_at": "2026-02-12T18:21:44Z"
  }
]
```

---

### Read File

Streams the contents of a file.

```
GET /v1/file?path=/reports/january.csv
```

The response body contains the raw file bytes.

---

### Write File

Creates or overwrites a file at the given path.

```
PUT /v1/file?path=/reports/january.csv
Content-Type: text/csv
```

Request body:
```
<raw file contents>
```

Notes:
- Writes are atomic at the object level
- Existing files are overwritten by default
- Directories are created implicitly

---

### Delete File

Deletes a file at the given path.

```
DELETE /v1/file?path=/reports/january.csv
```

---

## Authentication & Access

- Each FileProxy instance issues one or more API tokens
- Tokens are scoped to a single storage source
- All requests are authenticated
- FileProxy never exposes underlying storage credentials

---

## Supported Backends

Initial support:
- Amazon S3 (bucket + prefix)

Planned:
- Google Drive
- Dropbox

---

## Operational Guarantees

- Read-after-write consistency per request
- No background sync or caching assumptions
- Requests are stateless
- Storage is the source of truth

---

## Pricing Model

FileProxy is billed per connected storage source on a monthly subscription.

Pricing includes:
- API access
- Authenticated read/write operations
- Basic rate limiting
- Operational monitoring

---

## Design Philosophy

FileProxy is intentionally minimal.

- Small surface area
- Predictable behavior
- No hidden automation
- Easy to reason about in production

If you can explain your use case without a diagram, FileProxy is probably a good fit.

---

## License

TBD
