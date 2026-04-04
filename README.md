# FileProxy

FileProxy is a Django web app that stores cloud storage credentials encrypted in a vault and exposes a unified REST API and browser UI for file operations across multiple backends. Users connect their S3 buckets, Google Drive, Dropbox accounts, or Azure Blob Storage containers once; FileProxy handles all authentication and proxies file operations through a single consistent API with usage tracking and per-operation subscription limits.

---

## Features

- **Multi-backend support** — Amazon S3, Google Drive, Dropbox, Azure Blob Storage
- **Encrypted credential vault** — AES-GCM envelope encryption with per-item key rotation
- **Unified file API** — enumerate, read, write, delete, and streaming download across all backends
- **Usage event tracking** — per-connection analytics dashboard with operation history
- **Subscription tiers** — per-operation and data-transfer limits enforced at the API layer
- **OpenAPI / Swagger UI** — auto-generated at `/api/docs/`
- **Light / Dark theme toggle**

---

## Architecture

```
fileproxy/
├── core/backends/       # Backend abstraction layer (ABC + concrete implementations)
├── connections/         # Encrypted credential store (models, API, UI)
├── files/               # File operation API (backend-agnostic)
├── usage/               # Event recording and analytics
├── subscription/        # Tiered plans and limit enforcement
├── accounts/            # User registration/auth views
├── api/                 # Root API URL aggregator (/api/v1/)
└── config/              # Django settings, root URLconf
```

### Backend abstraction

The `Backend` ABC in `core/backends/base.py` defines the interface all backends must implement:

| Method | Description |
|---|---|
| `test()` | Verify connectivity and credentials |
| `enumerate_page(prefix, cursor, page_size)` | List objects at a prefix with cursor-based pagination |
| `read(path)` | Read an object and return bytes |
| `read_stream(path)` | Read an object as a chunk iterator for streaming |
| `write(path, data)` | Write bytes to an object path |
| `write_stream(path, file_obj)` | Write a file-like object to a path |
| `delete(path)` | Delete an object |

### Supported backends

| Kind | Auth | Key credentials |
|---|---|---|
| `aws_s3` | Static credentials | `access_key_id`, `secret_access_key`, `bucket`, `region` |
| `gdrive_oauth2` | OAuth2 (offline) | `refresh_token`; settings: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| `dropbox_oauth2` | OAuth2 (offline) | `refresh_token`; settings: `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET` |
| `azure_blob` | Service Principal | `tenant_id`, `client_id`, `client_secret`, `account_name`, `container_name` |

### Credential encryption

Credentials are stored using envelope encryption. Each connection has a unique Data Encryption Key (DEK) encrypted by a master Key Encryption Key (KEK) derived from `FILEPROXY_VAULT_MASTER_KEY`. AES-GCM authenticated data (AAD) binds each ciphertext to its `scope:kind:id`, preventing cross-item ciphertext swapping. The DEK is rotated independently per connection via the `rotate` action without re-entering credentials.

---

## Local Development Setup

### Prerequisites

- Python 3.13
- [Poetry](https://python-poetry.org/)
- Node 20+ and npm

### Install

```bash
git clone <repo>
cd FileProxy

# Python dependencies
cd fileproxy
poetry install --no-root

# Node dependencies (for TypeScript build and linting)
npm install
```

### Environment

Create `fileproxy/.env`:

```dotenv
FILEPROXY_VAULT_MASTER_KEY=<32-byte key encoded as URL-safe base64>

# Optional — required only for the respective backends
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=

DROPBOX_APP_KEY=
DROPBOX_APP_SECRET=

# Feature flags
SUBSCRIPTIONS_ENABLED=true
```

Generate the vault master key:

```bash
python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

### Database setup

```bash
cd fileproxy
poetry run python manage.py migrate
poetry run python manage.py createsuperuser
```

### Run

```bash
cd fileproxy
poetry run python manage.py runserver
```

### TypeScript

The compiled JS is committed to the repository. You only need to rebuild if you modify TypeScript source files:

```bash
cd fileproxy
npm run ts:build   # Compile once
npm run ts:watch   # Watch mode
```

---

## URL Structure

### UI routes

| Path | Purpose |
|---|---|
| `/` | Home dashboard |
| `/connections/` | Connection management |
| `/files/` | File browser |
| `/usage/` | Usage analytics overview |
| `/subscription/` | Subscription plan management |
| `/api/docs/` | Swagger UI |
| `/admin/` | Django admin |

### API endpoints

All endpoints are under `/api/v1/` and require session or basic authentication.

**Connections**

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/connections/` | List all connections |
| POST | `/api/v1/connections/` | Create a connection (generic) |
| GET | `/api/v1/connections/{id}/` | Retrieve a connection |
| PUT/PATCH | `/api/v1/connections/{id}/` | Update a connection |
| DELETE | `/api/v1/connections/{id}/` | Delete a connection |
| POST | `/api/v1/connections/{id}/rotate/` | Rotate the DEK (re-encrypts with new key) |
| POST | `/api/v1/connections/{id}/rename/` | Rename a connection |
| POST | `/api/v1/connections/{id}/test/` | Test backend connectivity |
| POST | `/api/v1/connections/s3/` | Create an S3 connection |
| POST | `/api/v1/connections/gdrive/initiate/` | Begin Google Drive OAuth2 flow |
| POST | `/api/v1/connections/dropbox/initiate/` | Begin Dropbox OAuth2 flow |
| POST | `/api/v1/connections/azure/` | Create an Azure Blob connection |

See `/api/docs/` for full request/response schemas.

**Files**

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/files/` | List connections available for file operations |
| POST | `/api/v1/files/{name}/health/` | Test backend connectivity |
| GET | `/api/v1/files/{name}/objects/` | Enumerate objects (`prefix`, `cursor`, `page_size` params) |
| GET | `/api/v1/files/{name}/path/?path=…` | Read object (streaming) |
| POST | `/api/v1/files/{name}/path/` | Write object — JSON (`path` + `data_base64`), multipart, or `application/octet-stream` |
| DELETE | `/api/v1/files/{name}/path/?path=…` | Delete object → 204 |
| GET | `/api/v1/files/{name}/path/stream/?path=…` | Streaming binary download |
| GET | `/api/v1/files/{name}/pending/` | List pending (in-progress) uploads |

**Usage**

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/usage/summary/` | Aggregate totals across all connections |
| GET | `/api/v1/usage/by-connection/` | Per-connection operation breakdown |
| GET | `/api/v1/usage/timeline/` | Time-series operation counts |

**Subscription**

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/subscription/plans/` | List available plans |
| GET | `/api/v1/subscription/my/` | Current user's active subscription |
| POST | `/api/v1/subscription/my/switch/` | Switch to a different plan |
| POST | `/api/v1/subscription/my/cancel/` | Cancel subscription |
| GET | `/api/v1/subscription/my/usage/` | Usage counts against current plan limits |
| GET | `/api/v1/subscription/my/plans/` | Plans available to switch to |

---

## Running Tests

```bash
cd fileproxy
poetry run python manage.py test                     # All apps
poetry run python manage.py test connections
poetry run python manage.py test files
poetry run python manage.py test usage
poetry run python manage.py test subscription
```

---

## TypeScript

```bash
cd fileproxy
npm run ts:build       # Compile once
npm run ts:watch       # Watch mode
npm run format         # Prettier
npm run lint:security  # ESLint security scan
```

---

## CI/CD

The GitHub Actions pipeline runs on every push (except to `main`) and on pull requests.

**Job dependency graph:**

```
format ──┬──> lint
         ├──> test ──> fuzz
         └──> security
```

| Job | Tool | Description |
|---|---|---|
| `format` | ruff, Prettier | Auto-formats Python and TypeScript; commits fixes back to the branch |
| `lint` | ruff check | Lints Python (import order, style) after formatting |
| `test` | Django test runner | Runs the full test suite against a generated vault key |
| `security` | Bandit, ESLint | Static security analysis for Python and TypeScript |
| `fuzz` | Schemathesis | Spins up a live dev server and fuzz-tests all OpenAPI endpoints for server errors and schema conformance |

---

## Adding a New Backend

1. Create `core/backends/<name>.py` — implement the `Backend` ABC (`test`, `enumerate_page`, `read`, `write`, `delete`)
2. Add a new `ConnectionKind` choice in `connections/models.py`
3. `python manage.py makemigrations connections && python manage.py migrate`
4. Add a credentials dataclass in `connections/schemas.py` with `to_payload` / `from_payload`
5. Add `create_*` and `load_*` functions in `connections/service.py`
6. Add a `*CreateSerializer` (or `*InitiateSerializer` for OAuth) in `connections/api/serializers.py`
7. Add a `*_create` (or `*_initiate`) action on `ConnectionViewSet` in `connections/api/views.py`
8. Add a form view (and OAuth callback view if applicable) in `connections/ui/views.py`
9. Register routes in `connections/ui/urls.py`
10. Register the backend class in `core/backends/factory.py`'s `_KIND_TO_BACKEND` dict
11. Add any required env vars in `config/settings.py` (use `default=""` so the app starts without them)
12. Create `connections/templates/connections_ui/new_<name>.html`
13. Create `static/ts/connections/forms/<name>.ts`, then `npm run ts:build`
14. Verify the connection card in `new_credentials.html` links to `/connections/new/<name>/`

---

## License

TBD
