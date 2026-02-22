from __future__ import annotations

from .base import Backend, BackendConfig, BackendError
from .dropbox import DropboxBackend
from .gdrive import GDriveBackend
from .s3 import S3Backend

_KIND_TO_BACKEND: dict[str, type[Backend]] = {
    "aws_s3": S3Backend,
    "gdrive_oauth2": GDriveBackend,
    "dropbox_oauth2": DropboxBackend,
}


def backend_from_config(config: BackendConfig) -> Backend:
    """Create a backend instance for a backend config.

    Args:
        config: Backend configuration and secrets.

    Returns:
        Backend instance.

    Raises:
        BackendError: If the backend kind is unsupported.
    """
    backend_cls = _KIND_TO_BACKEND.get(config.kind)
    if backend_cls is None:
        raise BackendError(f"Unsupported backend kind: {config.kind}")
    return backend_cls(config)
