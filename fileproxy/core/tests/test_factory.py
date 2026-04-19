from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from core.backends.azure_blob import AzureBlobBackend
from core.backends.base import BackendConfig, BackendError
from core.backends.dropbox import DropboxBackend
from core.backends.factory import backend_from_config
from core.backends.gdrive import GDriveBackend
from core.backends.s3 import S3Backend


def _config(kind: str, settings=None, secrets=None) -> BackendConfig:
    return BackendConfig(kind=kind, settings=settings or {}, secrets=secrets or {})


class BackendFromConfigTests(SimpleTestCase):
    def test_s3_returns_s3_backend(self):
        with patch.object(S3Backend, "__init__", return_value=None):
            backend = backend_from_config(_config("aws_s3"))
        self.assertIsInstance(backend, S3Backend)

    def test_gdrive_returns_gdrive_backend(self):
        with patch.object(GDriveBackend, "__init__", return_value=None):
            backend = backend_from_config(_config("gdrive_oauth2"))
        self.assertIsInstance(backend, GDriveBackend)

    def test_dropbox_returns_dropbox_backend(self):
        with patch.object(DropboxBackend, "__init__", return_value=None):
            backend = backend_from_config(_config("dropbox_oauth2"))
        self.assertIsInstance(backend, DropboxBackend)

    def test_azure_returns_azure_backend(self):
        with patch.object(AzureBlobBackend, "__init__", return_value=None):
            backend = backend_from_config(_config("azure_blob"))
        self.assertIsInstance(backend, AzureBlobBackend)

    def test_unsupported_kind_raises_backend_error(self):
        with self.assertRaises(BackendError):
            backend_from_config(_config("unknown_kind"))
