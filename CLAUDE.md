# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All Django commands run from the `fileproxy/` directory (where `manage.py` lives).

```bash
# Run development server
cd fileproxy && python manage.py runserver

# Apply migrations
cd fileproxy && python manage.py migrate

# Create a migration
cd fileproxy && python manage.py makemigrations

# Run all tests
cd fileproxy && python manage.py test

# Run tests for a specific app
cd fileproxy && python manage.py test vault
cd fileproxy && python manage.py test files

# Run a single test
cd fileproxy && python manage.py test vault.tests.test_vault.VaultTests.test_round_trip_encrypt_decrypt

# TypeScript build (from fileproxy/)
cd fileproxy && npm run ts:build

# TypeScript watch mode
cd fileproxy && npm run ts:watch
```

## Environment

The app requires a `.env` file at `fileproxy/.env` (loaded by `settings.py`):

```
FILEPROXY_VAULT_MASTER_KEY=<32-byte key encoded as URL-safe base64>
```

Generate a key with: `python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`

## Architecture

FileProxy is a Django app that proxies file operations to external storage backends (currently S3 only), with credentials stored encrypted in a local database.

### Apps and layers

**`core/backends/`** — Backend abstraction layer
- `base.py`: `Backend` ABC defining `test()`, `enumerate()`, `read()`, `write()`, `delete()`. Also defines `BackendConfig` and typed exceptions (`BackendTestError`, `BackendReadError`, etc.)
- `s3.py`: `S3Backend` — concrete S3 implementation using boto3
- `factory.py`: `backend_from_config(config)` — maps `BackendConfig.kind` string to a backend class

**`vault/`** — Encrypted credential store
- `models.py`: `VaultItem` stores credentials using envelope encryption (AES-GCM). Each item has a Data Encryption Key (DEK) wrapped by a master Key Encryption Key (KEK) from `VAULT_MASTER_KEY`. AAD binds ciphertext to `scope:kind:id`, preventing cross-item ciphertext swapping.
- `service.py`: `create_s3_credentials()` and `load_s3_credentials()` — service functions for vault operations
- `schemas.py`: `S3StaticCredentials` dataclass
- `api/`: DRF viewset at `/api/v1/vault-items/` — CRUD + `rotate`, `rename`, `test` actions. Never returns secrets in responses.
- `ui/`: Django template views at `/vault/`

**`files/`** — File operation API (backend-agnostic)
- `services.py`: `get_backend_for_user_vault_item()` — resolves a vault item name to a `Backend` instance for a user. `user_scope(user)` returns `"user:{id}"`.
- `api/views.py`: `FilesViewSet` at `/api/v1/files/{vault_item_name}/` — exposes `test`, `objects`, `read`, `write`, `delete_object` actions. Data transferred as base64.
- `ui/`: Simple browser view at `/files/`

**`api/`** — Root API URL aggregator (`/api/v1/`) — includes vault and files routers.

**`config/`** — Django project config: settings, URL root, env helpers.

### URL structure

| Path | Purpose |
|---|---|
| `/api/v1/vault-items/` | Credential management (no secrets in responses) |
| `/api/v1/files/{name}/objects/` | Enumerate backend objects |
| `/api/v1/files/{name}/read/` | Read object (returns base64) |
| `/api/v1/files/{name}/write/` | Write object (accepts base64) |
| `/api/v1/files/{name}/test/` | Backend connectivity test |
| `/api/docs/` | Swagger UI (drf-spectacular) |
| `/vault/` | Vault management UI |
| `/files/` | File browser UI |

### Frontend

TypeScript source lives in `fileproxy/static/ts/` and compiles to `fileproxy/static/js/`. The TS is organized by feature: `vault/forms/`, `vault/tables/`, `vault/item/`, `files/`, and shared `utils/` (api, dom, cookies).

### Adding a new backend

1. Create a new class in `core/backends/` inheriting from `Backend`
2. Add a new `VaultItemKind` choice in `vault/models.py`
3. Register in `core/backends/factory.py`'s `_KIND_TO_BACKEND` dict
4. Add a corresponding serializer action in `vault/api/views.py` and `vault/api/serializers.py`