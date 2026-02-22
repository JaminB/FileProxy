from __future__ import annotations

import io
import uuid
from dataclasses import dataclass
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaInMemoryUpload, MediaIoBaseDownload, MediaIoBaseUpload
import google.auth.exceptions
import google.oauth2.credentials

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
class GDriveObject:
    name: str
    path: str
    size: int | None


class GDriveBackend(Backend):
    """Google Drive backend using OAuth2 user credentials."""

    _FOLDER_MIME = "application/vnd.google-apps.folder"

    def __init__(self, config: BackendConfig):
        super().__init__(config)

        creds = google.oauth2.credentials.Credentials(
            token=None,
            refresh_token=self._require_secret("refresh_token"),
            client_id=self._require_secret("client_id"),
            client_secret=self._require_secret("client_secret"),
            token_uri="https://oauth2.googleapis.com/token",
        )
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_secret(self, key: str) -> str:
        val = self.config.secrets.get(key)
        if not isinstance(val, str) or not val.strip():
            raise BackendError(f"Missing required secret: {key}")
        return val.strip()

    def _find_child(self, parent_id: str, name: str, *, mime_type: str | None = None) -> str | None:
        """Return the Drive file ID of a direct child by name, or None if not found."""
        q = f"'{parent_id}' in parents and name = {_q(name)} and trashed = false"
        if mime_type:
            q += f" and mimeType = '{mime_type}'"
        resp = (
            self._service.files()
            .list(q=q, fields="files(id)", pageSize=1)
            .execute()
        )
        files = resp.get("files", [])
        return files[0]["id"] if files else None

    def _resolve_folder(self, folder_path: str) -> str | None:
        """Walk folder_path (slash-separated) from root; return final folder ID or None."""
        if not folder_path:
            return "root"
        current_id = "root"
        for part in folder_path.strip("/").split("/"):
            if not part:
                continue
            child_id = self._find_child(current_id, part, mime_type=self._FOLDER_MIME)
            if child_id is None:
                return None
            current_id = child_id
        return current_id

    def _get_or_create_folder(self, folder_path: str) -> str:
        """Resolve or create all folders in folder_path, returning the final folder ID."""
        if not folder_path:
            return "root"
        current_id = "root"
        for part in folder_path.strip("/").split("/"):
            if not part:
                continue
            child_id = self._find_child(current_id, part, mime_type=self._FOLDER_MIME)
            if child_id is None:
                meta = {
                    "name": part,
                    "mimeType": self._FOLDER_MIME,
                    "parents": [current_id],
                }
                result = self._service.files().create(body=meta, fields="id").execute()
                child_id = result["id"]
            current_id = child_id
        return current_id

    def _split_path(self, path: str) -> tuple[str, str]:
        """Split path into (folder_path, filename)."""
        if "/" not in path:
            return "", path
        folder_path, filename = path.rsplit("/", 1)
        return folder_path, filename

    # ------------------------------------------------------------------
    # Backend interface
    # ------------------------------------------------------------------

    def enumerate_page(
        self,
        *,
        prefix: str | None = None,
        cursor: str | None = None,
        page_size: int = 1000,
    ) -> EnumeratePage:
        try:
            if prefix:
                folder_id = self._resolve_folder(prefix.rstrip("/"))
            else:
                folder_id = "root"

            if folder_id is None:
                return EnumeratePage(objects=[], next_cursor=None)

            q = f"'{folder_id}' in parents and trashed = false"
            kwargs: dict[str, Any] = {
                "q": q,
                "fields": "nextPageToken, files(id, name, mimeType, size)",
                "pageSize": min(page_size, 1000),
            }
            if cursor:
                kwargs["pageToken"] = cursor

            resp = self._service.files().list(**kwargs).execute()
        except HttpError as e:
            raise BackendEnumerateError(f"GDrive enumerate failed: {e}") from e
        except google.auth.exceptions.RefreshError as e:
            raise BackendEnumerateError(f"GDrive auth refresh failed: {e}") from e

        base_prefix = (prefix or "").rstrip("/")
        if base_prefix:
            base_prefix += "/"

        objects: list[GDriveObject] = []
        for f in resp.get("files", []):
            name = f.get("name", "")
            is_folder = f.get("mimeType") == self._FOLDER_MIME
            size_raw = f.get("size")
            size = int(size_raw) if size_raw is not None else None
            if is_folder:
                obj_path = f"{base_prefix}{name}/"
                size = None
            else:
                obj_path = f"{base_prefix}{name}"
            objects.append(GDriveObject(name=name, path=obj_path, size=size))

        return EnumeratePage(
            objects=objects,
            next_cursor=resp.get("nextPageToken") or None,
        )

    def read(self, path: str) -> bytes:
        folder_path, filename = self._split_path(path)
        try:
            folder_id = self._resolve_folder(folder_path)
            if folder_id is None:
                raise BackendReadError(f"GDrive read failed: folder not found (path={path})")

            file_id = self._find_child(folder_id, filename)
            if file_id is None:
                raise BackendReadError(f"GDrive read failed: file not found (path={path})")

            request = self._service.files().get_media(fileId=file_id)
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return buf.getvalue()
        except BackendReadError:
            raise
        except HttpError as e:
            raise BackendReadError(f"GDrive read failed (path={path}): {e}") from e
        except google.auth.exceptions.RefreshError as e:
            raise BackendReadError(f"GDrive auth refresh failed: {e}") from e

    def write(self, path: str, data: bytes) -> None:
        folder_path, filename = self._split_path(path)
        try:
            folder_id = self._get_or_create_folder(folder_path)
            existing_id = self._find_child(folder_id, filename)
            media = MediaInMemoryUpload(data, resumable=False)

            if existing_id:
                self._service.files().update(
                    fileId=existing_id,
                    media_body=media,
                ).execute()
            else:
                meta = {"name": filename, "parents": [folder_id]}
                self._service.files().create(
                    body=meta,
                    media_body=media,
                    fields="id",
                ).execute()
        except HttpError as e:
            raise BackendWriteError(f"GDrive write failed (path={path}): {e}") from e
        except google.auth.exceptions.RefreshError as e:
            raise BackendWriteError(f"GDrive auth refresh failed: {e}") from e

    def read_stream(self, path: str):
        folder_path, filename = self._split_path(path)
        try:
            folder_id = self._resolve_folder(folder_path)
            if folder_id is None:
                raise BackendReadError(f"GDrive read_stream failed: folder not found (path={path})")

            file_id = self._find_child(folder_id, filename)
            if file_id is None:
                raise BackendReadError(f"GDrive read_stream failed: file not found (path={path})")

            request = self._service.files().get_media(fileId=file_id)
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request, chunksize=8 * 1024 * 1024)
            done = False
            while not done:
                _, done = downloader.next_chunk()
                chunk = buf.getvalue()
                buf.seek(0)
                buf.truncate(0)
                yield chunk
        except BackendReadError:
            raise
        except HttpError as e:
            raise BackendReadError(f"GDrive read_stream failed (path={path}): {e}") from e
        except google.auth.exceptions.RefreshError as e:
            raise BackendReadError(f"GDrive auth refresh failed: {e}") from e

    def write_stream(self, path: str, stream) -> None:
        folder_path, filename = self._split_path(path)
        try:
            folder_id = self._get_or_create_folder(folder_path)
            existing_id = self._find_child(folder_id, filename)
            media = MediaIoBaseUpload(
                stream,
                mimetype="application/octet-stream",
                chunksize=8 * 1024 * 1024,
                resumable=True,
            )

            if existing_id:
                self._service.files().update(
                    fileId=existing_id,
                    media_body=media,
                ).execute()
            else:
                meta = {"name": filename, "parents": [folder_id]}
                self._service.files().create(
                    body=meta,
                    media_body=media,
                    fields="id",
                ).execute()
        except HttpError as e:
            raise BackendWriteError(f"GDrive write_stream failed (path={path}): {e}") from e
        except google.auth.exceptions.RefreshError as e:
            raise BackendWriteError(f"GDrive auth refresh failed: {e}") from e

    def delete(self, path: str) -> None:
        folder_path, filename = self._split_path(path)
        try:
            folder_id = self._resolve_folder(folder_path)
            if folder_id is None:
                raise BackendDeleteError(f"GDrive delete failed: folder not found (path={path})")

            file_id = self._find_child(folder_id, filename)
            if file_id is None:
                raise BackendDeleteError(f"GDrive delete failed: file not found (path={path})")

            self._service.files().delete(fileId=file_id).execute()
        except BackendDeleteError:
            raise
        except HttpError as e:
            raise BackendDeleteError(f"GDrive delete failed (path={path}): {e}") from e
        except google.auth.exceptions.RefreshError as e:
            raise BackendDeleteError(f"GDrive auth refresh failed: {e}") from e

    def test(self) -> None:
        test_name = f"fileproxy-test-{uuid.uuid4().hex}.txt"
        test_data = f"fileproxy connectivity test {test_name}".encode("utf-8")
        file_id: str | None = None

        try:
            # 1) Verify auth
            try:
                self._service.about().get(fields="user").execute()
            except google.auth.exceptions.RefreshError as e:
                raise BackendTestError(f"GDrive test failed at auth: token refresh error: {e}") from e
            except HttpError as e:
                raise BackendTestError(f"GDrive test failed at auth: {e}") from e

            # 2) Write test file to Drive root
            try:
                media = MediaInMemoryUpload(test_data, resumable=False)
                meta = {"name": test_name, "parents": ["root"]}
                result = self._service.files().create(
                    body=meta, media_body=media, fields="id"
                ).execute()
                file_id = result["id"]
            except HttpError as e:
                raise BackendTestError(f"GDrive test failed at write: {e}") from e

            # 3) Read back and verify content
            try:
                request = self._service.files().get_media(fileId=file_id)
                buf = io.BytesIO()
                downloader = MediaIoBaseDownload(buf, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                got = buf.getvalue()
                if got != test_data:
                    raise BackendTestError("GDrive test failed at read: content mismatch")
            except BackendTestError:
                raise
            except HttpError as e:
                raise BackendTestError(f"GDrive test failed at read: {e}") from e

            # 4) Delete
            try:
                self._service.files().delete(fileId=file_id).execute()
                file_id = None
            except HttpError as e:
                raise BackendTestError(f"GDrive test failed at delete: {e}") from e

            # 5) Verify gone (expect 404)
            try:
                self._service.files().get(fileId=result["id"], fields="id").execute()
                raise BackendTestError("GDrive test failed at delete_verification: file still exists")
            except HttpError as e:
                if e.resp.status != 404:
                    raise BackendTestError(
                        f"GDrive test failed at delete_verification: unexpected error: {e}"
                    ) from e
        finally:
            if file_id is not None:
                try:
                    self._service.files().delete(fileId=file_id).execute()
                except Exception:
                    pass


def _q(value: str) -> str:
    """Escape a string for use in Drive API query expressions."""
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"
