from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, BinaryIO, Iterator

from azure.core.exceptions import AzureError, HttpResponseError, ResourceNotFoundError
from azure.identity import ClientSecretCredential
from azure.storage.blob import BlobServiceClient

from .base import (Backend, BackendConfig, BackendDeleteError,
                   BackendEnumerateError, BackendError, BackendReadError,
                   BackendTestError, BackendWriteError, EnumeratePage)


@dataclass(frozen=True, slots=True)
class AzureBlobObject:
    """Azure Blob object metadata."""

    name: str
    path: str
    size: int | None


class AzureBlobBackend(Backend):
    """Azure Blob Storage backend using Service Principal authentication."""

    def __init__(self, config: BackendConfig):
        super().__init__(config)

        account_name = self._require_setting_str("account_name")
        container_name = self._require_setting_str("container_name")

        credential = ClientSecretCredential(
            tenant_id=self._require_secret_str("tenant_id"),
            client_id=self._require_secret_str("client_id"),
            client_secret=self._require_secret_str("client_secret"),
        )
        self._container_client = BlobServiceClient(
            f"https://{account_name}.blob.core.windows.net", credential=credential
        ).get_container_client(container_name)
        self._account_name = account_name
        self._container_name = container_name

    def test(self) -> None:
        """Validate Azure Blob connectivity and credentials by performing a full R/W/L/D cycle.

        Raises:
            BackendTestError: If any step fails.
        """
        test_key = f"fileproxy-test/{uuid.uuid4().hex}.txt"
        test_bytes = f"fileproxy connectivity test {test_key}".encode("utf-8")

        wrote = False
        deleted = False

        def _err(action: str, *, extra: str | None = None) -> BackendTestError:
            parts = [f"Azure Blob test failed at {action}:"]
            if extra:
                parts.append(extra)
            parts.append(f"account={self._account_name}")
            parts.append(f"container={self._container_name}")
            if action not in ("get_container_properties",):
                parts.append(f"blob={test_key}")
            return BackendTestError(" ".join(parts))

        try:
            # 1) Container access
            try:
                self._container_client.get_container_properties()
            except ResourceNotFoundError as e:
                raise _err("get_container_properties", extra="container not found") from e
            except HttpResponseError as e:
                raise _err("get_container_properties", extra=str(e.error_code or e)) from e
            except AzureError as e:
                raise _err("get_container_properties", extra=str(e)) from e

            # 2) Write
            try:
                self._container_client.upload_blob(test_key, test_bytes, overwrite=True)
                wrote = True
            except HttpResponseError as e:
                raise _err("write", extra=str(e.error_code or e)) from e
            except AzureError as e:
                raise _err("write", extra=str(e)) from e

            # 3) Read + validate
            try:
                got = self._container_client.download_blob(test_key).readall()
                if got != test_bytes:
                    raise _err("read", extra="content mismatch")
            except ResourceNotFoundError as e:
                raise _err("read", extra="blob not found") from e
            except HttpResponseError as e:
                raise _err("read", extra=str(e.error_code or e)) from e
            except AzureError as e:
                raise _err("read", extra=str(e)) from e

            # 4) List + confirm presence
            try:
                found = any(
                    b.name == test_key
                    for b in self._container_client.list_blobs(name_starts_with=test_key)
                )
                if not found:
                    raise _err("list", extra="test blob not found in listing")
            except BackendTestError:
                raise
            except HttpResponseError as e:
                raise _err("list", extra=str(e.error_code or e)) from e
            except AzureError as e:
                raise _err("list", extra=str(e)) from e

            # 5) Delete
            try:
                self._container_client.delete_blob(test_key)
                deleted = True
            except ResourceNotFoundError as e:
                raise _err("delete", extra="blob not found") from e
            except HttpResponseError as e:
                raise _err("delete", extra=str(e.error_code or e)) from e
            except AzureError as e:
                raise _err("delete", extra=str(e)) from e

        finally:
            if wrote and not deleted:
                try:
                    self._container_client.delete_blob(test_key)
                except Exception as e:  # noqa: BLE001
                    raise BackendTestError(
                        f"Azure Blob test cleanup failed: "
                        f"account={self._account_name} container={self._container_name} blob={test_key}"
                    ) from e

    def enumerate_page(
        self,
        *,
        prefix: str | None = None,
        cursor: str | None = None,
        page_size: int = 1000,
    ) -> EnumeratePage:
        """Return one page of Azure Blob objects."""
        try:
            pages = self._container_client.list_blobs(
                name_starts_with=prefix, results_per_page=page_size
            ).by_page(continuation_token=cursor or None)
            page = next(pages)
        except StopIteration:
            return EnumeratePage(objects=[], next_cursor=None)
        except HttpResponseError as e:
            raise BackendEnumerateError(
                f"Azure Blob enumerate failed: {e.error_code or e}"
            ) from e
        except AzureError as e:
            raise BackendEnumerateError(f"Azure Blob enumerate failed: {e}") from e

        objects: list[AzureBlobObject] = []
        for blob in page:
            name = blob.name or ""
            size = blob.size
            objects.append(AzureBlobObject(
                name=name.rsplit("/", 1)[-1],
                path=name,
                size=int(size) if size is not None else None,
            ))

        return EnumeratePage(
            objects=objects,
            next_cursor=pages.continuation_token or None,
        )

    def read(self, path: str) -> bytes:
        """Read a blob from Azure Blob Storage."""
        try:
            return self._container_client.download_blob(path).readall()
        except ResourceNotFoundError as e:
            raise BackendReadError(f"Azure Blob read failed (path={path}): blob not found") from e
        except HttpResponseError as e:
            raise BackendReadError(
                f"Azure Blob read failed (path={path}): {e.error_code or e}"
            ) from e
        except AzureError as e:
            raise BackendReadError(f"Azure Blob read failed (path={path}): {e}") from e

    def write(self, path: str, data: bytes) -> None:
        """Write a blob to Azure Blob Storage."""
        try:
            self._container_client.upload_blob(path, data, overwrite=True)
        except HttpResponseError as e:
            raise BackendWriteError(
                f"Azure Blob write failed (path={path}): {e.error_code or e}"
            ) from e
        except AzureError as e:
            raise BackendWriteError(f"Azure Blob write failed (path={path}): {e}") from e

    def delete(self, path: str) -> None:
        """Delete a blob from Azure Blob Storage."""
        try:
            self._container_client.delete_blob(path)
        except ResourceNotFoundError as e:
            raise BackendDeleteError(
                f"Azure Blob delete failed (path={path}): blob not found"
            ) from e
        except HttpResponseError as e:
            raise BackendDeleteError(
                f"Azure Blob delete failed (path={path}): {e.error_code or e}"
            ) from e
        except AzureError as e:
            raise BackendDeleteError(f"Azure Blob delete failed (path={path}): {e}") from e

    def read_stream(self, path: str) -> Iterator[bytes]:
        """Stream blob bytes in chunks."""
        try:
            downloader = self._container_client.download_blob(path)
        except ResourceNotFoundError as e:
            raise BackendReadError(f"Azure Blob read failed (path={path}): blob not found") from e
        except HttpResponseError as e:
            raise BackendReadError(
                f"Azure Blob read failed (path={path}): {e.error_code or e}"
            ) from e
        except AzureError as e:
            raise BackendReadError(f"Azure Blob read failed (path={path}): {e}") from e
        yield from downloader.chunks()

    def write_stream(self, path: str, stream: BinaryIO) -> None:
        """Upload a file-like stream to Azure Blob Storage."""
        try:
            self._container_client.upload_blob(path, stream, overwrite=True)
        except HttpResponseError as e:
            raise BackendWriteError(
                f"Azure Blob write_stream failed (path={path}): {e.error_code or e}"
            ) from e
        except AzureError as e:
            raise BackendWriteError(f"Azure Blob write_stream failed (path={path}): {e}") from e

    def _require_setting_str(self, key: str) -> str:
        val = self.config.settings.get(key)
        if not isinstance(val, str) or not val.strip():
            raise BackendError(f"Missing required setting: {key}")
        return val.strip()

    def _require_secret_str(self, key: str) -> str:
        val = self.config.secrets.get(key)
        if not isinstance(val, str) or not val.strip():
            raise BackendError(f"Missing required secret: {key}")
        return val.strip()
