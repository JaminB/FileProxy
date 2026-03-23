from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO, Iterator

import dropbox
import dropbox.exceptions
import dropbox.files
from django.conf import settings as django_settings

from .base import (
    Backend,
    BackendConfig,
    BackendDeleteError,
    BackendEnumerateError,
    BackendError,
    BackendReadError,
    BackendTestError,
    BackendWriteError,
    EnumeratePage,
)


@dataclass(frozen=True, slots=True)
class DropboxObject:
    name: str
    path: str
    size: int | None
    last_modified: datetime | None


def _ensure_abs(path: str) -> str:
    """Ensure path starts with '/'."""
    if not path.startswith("/"):
        return "/" + path
    return path


class DropboxBackend(Backend):
    """Dropbox backend using OAuth2 refresh token credentials."""

    def __init__(self, config: BackendConfig):
        super().__init__(config)
        self._dbx = dropbox.Dropbox(
            oauth2_refresh_token=self._require_secret("refresh_token"),
            app_key=django_settings.DROPBOX_APP_KEY,
            app_secret=django_settings.DROPBOX_APP_SECRET,
        )

    def _require_secret(self, key: str) -> str:
        val = self.config.secrets.get(key)
        if not isinstance(val, str) or not val.strip():
            raise BackendError(f"Missing required secret: {key}")
        return val.strip()

    def test(self) -> None:
        test_name = f"/fileproxy-test-{uuid.uuid4().hex}.txt"
        test_data = f"fileproxy connectivity test {test_name}".encode("utf-8")

        try:
            # 1) Write test file (implicitly verifies auth and write access)
            try:
                self._dbx.files_upload(test_data, test_name)
            except dropbox.exceptions.AuthError as e:
                raise BackendTestError(f"Dropbox test failed at auth: {e}") from e
            except dropbox.exceptions.ApiError as e:
                raise BackendTestError(f"Dropbox test failed at write: {e}") from e

            # 2) Read back and verify
            try:
                _, resp = self._dbx.files_download(test_name)
                got = resp.content
                if got != test_data:
                    raise BackendTestError("Dropbox test failed at read: content mismatch")
            except BackendTestError:
                raise
            except dropbox.exceptions.AuthError as e:
                raise BackendTestError(f"Dropbox test failed at auth: {e}") from e
            except dropbox.exceptions.ApiError as e:
                raise BackendTestError(f"Dropbox test failed at read: {e}") from e

            # 3) Delete
            try:
                self._dbx.files_delete_v2(test_name)
            except dropbox.exceptions.ApiError as e:
                raise BackendTestError(f"Dropbox test failed at delete: {e}") from e

        except BackendTestError:
            raise
        except Exception as e:
            raise BackendTestError(f"Dropbox test failed: {e}") from e

    def enumerate_page(
        self,
        *,
        prefix: str | None = None,
        cursor: str | None = None,
        page_size: int = 1000,
    ) -> EnumeratePage:
        try:
            if cursor:
                result = self._dbx.files_list_folder_continue(cursor)
            else:
                folder_path = _ensure_abs(prefix.rstrip("/") if prefix else "")
                if folder_path == "/":
                    folder_path = ""
                result = self._dbx.files_list_folder(
                    folder_path,
                    limit=min(page_size, 2000),
                )
        except dropbox.exceptions.ApiError as e:
            raise BackendEnumerateError(f"Dropbox enumerate failed: {e}") from e
        except dropbox.exceptions.AuthError as e:
            raise BackendEnumerateError(f"Dropbox auth failed: {e}") from e

        base_prefix = (prefix or "").rstrip("/")
        if base_prefix:
            base_prefix += "/"

        objects: list[DropboxObject] = []
        for entry in result.entries:
            if isinstance(entry, dropbox.files.FileMetadata):
                obj_path = f"{base_prefix}{entry.name}"
                objects.append(
                    DropboxObject(
                        name=entry.name,
                        path=obj_path,
                        size=entry.size,
                        last_modified=entry.server_modified,
                    )
                )
            elif isinstance(entry, dropbox.files.FolderMetadata):
                obj_path = f"{base_prefix}{entry.name}/"
                objects.append(
                    DropboxObject(name=entry.name, path=obj_path, size=None, last_modified=None)
                )

        next_cursor = result.cursor if result.has_more else None
        return EnumeratePage(objects=objects, next_cursor=next_cursor)

    def read(self, path: str) -> bytes:
        abs_path = _ensure_abs(path)
        try:
            _, resp = self._dbx.files_download(abs_path)
            return resp.content
        except dropbox.exceptions.ApiError as e:
            raise BackendReadError(f"Dropbox read failed (path={path}): {e}") from e
        except dropbox.exceptions.AuthError as e:
            raise BackendReadError(f"Dropbox auth failed: {e}") from e

    def write(self, path: str, data: bytes) -> None:
        abs_path = _ensure_abs(path)
        try:
            self._dbx.files_upload(
                data,
                abs_path,
                mode=dropbox.files.WriteMode.overwrite,
            )
        except dropbox.exceptions.ApiError as e:
            raise BackendWriteError(f"Dropbox write failed (path={path}): {e}") from e
        except dropbox.exceptions.AuthError as e:
            raise BackendWriteError(f"Dropbox auth failed: {e}") from e

    def read_stream(self, path: str) -> Iterator[bytes]:
        abs_path = _ensure_abs(path)
        try:
            _, resp = self._dbx.files_download(abs_path)
        except dropbox.exceptions.ApiError as e:
            raise BackendReadError(f"Dropbox read_stream failed (path={path}): {e}") from e
        except dropbox.exceptions.AuthError as e:
            raise BackendReadError(f"Dropbox auth failed: {e}") from e
        return resp.iter_content(chunk_size=8 * 1024 * 1024)

    def write_stream(self, path: str, stream: BinaryIO) -> None:
        abs_path = _ensure_abs(path)
        chunk_size = 8 * 1024 * 1024
        try:
            first_chunk = stream.read(chunk_size)
            if len(first_chunk) < chunk_size:
                # Small file — use simple upload
                self._dbx.files_upload(
                    first_chunk,
                    abs_path,
                    mode=dropbox.files.WriteMode.overwrite,
                )
                return

            # Large file — use upload session
            result = self._dbx.files_upload_session_start(first_chunk)
            session_id = result.session_id
            offset = len(first_chunk)

            while True:
                chunk = stream.read(chunk_size)
                cursor = dropbox.files.UploadSessionCursor(session_id=session_id, offset=offset)
                if len(chunk) < chunk_size:
                    # Last chunk (possibly empty)
                    commit = dropbox.files.CommitInfo(
                        path=abs_path,
                        mode=dropbox.files.WriteMode.overwrite,
                    )
                    self._dbx.files_upload_session_finish(chunk, cursor, commit)
                    return
                self._dbx.files_upload_session_append_v2(chunk, cursor)
                offset += len(chunk)
        except dropbox.exceptions.ApiError as e:
            raise BackendWriteError(f"Dropbox write_stream failed (path={path}): {e}") from e
        except dropbox.exceptions.AuthError as e:
            raise BackendWriteError(f"Dropbox auth failed: {e}") from e

    def delete(self, path: str) -> None:
        abs_path = _ensure_abs(path)
        try:
            self._dbx.files_delete_v2(abs_path)
        except dropbox.exceptions.ApiError as e:
            raise BackendDeleteError(f"Dropbox delete failed (path={path}): {e}") from e
        except dropbox.exceptions.AuthError as e:
            raise BackendDeleteError(f"Dropbox auth failed: {e}") from e
