from __future__ import annotations

from dataclasses import dataclass
from typing import Any, BinaryIO, Iterator, Optional

import boto3
from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

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
class S3Object:
    """S3 object metadata."""

    name: str
    path: str
    size: int | None


class S3Backend(Backend):
    """AWS S3 backend."""

    def __init__(self, config: BackendConfig):
        """Initialize S3 backend."""
        super().__init__(config)

        self._bucket = self._require_setting_str("bucket")

        self._client = boto3.client(
            "s3",
            aws_access_key_id=self._require_secret_str("access_key_id"),
            aws_secret_access_key=self._require_secret_str("secret_access_key"),
            aws_session_token=self._optional_secret_str("session_token"),
        )

    def test(self) -> None:
        """Validate S3 connectivity and credentials by performing a full R/W/L/D cycle.

        Raises:
            BackendTestError: If any step fails. Error messages explicitly name the failing action.
        """
        import uuid

        test_key = f"fileproxy-test/{uuid.uuid4().hex}.txt"
        test_bytes = f"fileproxy connectivity test {test_key}".encode("utf-8")

        wrote = False
        deleted = False

        def _err(
            action: str, *, code: str | None = None, extra: str | None = None
        ) -> BackendTestError:
            parts = [f"S3 test failed at {action}:"]
            if extra:
                parts.append(extra)
            parts.append(f"bucket={self._bucket}")
            if action != "head_bucket":
                parts.append(f"key={test_key}")
            if code:
                parts.append(f"code={code}")
            return BackendTestError(" ".join(parts))

        def _client_error_code(e: ClientError) -> str | None:
            return (e.response.get("Error") or {}).get("Code")

        try:
            # 1) Bucket access
            try:
                self._client.head_bucket(Bucket=self._bucket)
            except NoCredentialsError as e:
                raise _err("head_bucket", extra="missing AWS credentials") from e
            except ClientError as e:
                raise _err("head_bucket", code=_client_error_code(e)) from e
            except BotoCoreError as e:
                raise _err("head_bucket", extra="connectivity error") from e

            # 2) Write
            try:
                self._client.put_object(Bucket=self._bucket, Key=test_key, Body=test_bytes)
                wrote = True
            except NoCredentialsError as e:
                raise _err("write", extra="missing AWS credentials") from e
            except ClientError as e:
                raise _err("write", code=_client_error_code(e)) from e
            except BotoCoreError as e:
                raise _err("write", extra="connectivity error") from e

            # 3) Read + validate
            try:
                resp = self._client.get_object(Bucket=self._bucket, Key=test_key)
                got = resp["Body"].read()
                if got != test_bytes:
                    raise _err("read", extra="content mismatch")
            except NoCredentialsError as e:
                raise _err("read", extra="missing AWS credentials") from e
            except ClientError as e:
                raise _err("read", code=_client_error_code(e)) from e
            except BotoCoreError as e:
                raise _err("read", extra="connectivity error") from e

            # 4) List + confirm presence
            try:
                found = False
                paginator = self._client.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=self._bucket, Prefix=test_key):
                    for obj in page.get("Contents", []) or []:
                        if obj.get("Key") == test_key:
                            found = True
                            break
                    if found:
                        break

                if not found:
                    raise _err("list", extra="test key not found in listing")
            except NoCredentialsError as e:
                raise _err("list", extra="missing AWS credentials") from e
            except ClientError as e:
                raise _err("list", code=_client_error_code(e)) from e
            except BotoCoreError as e:
                raise _err("list", extra="connectivity error") from e

            # 5) Delete
            try:
                self._client.delete_object(Bucket=self._bucket, Key=test_key)
                deleted = True
            except NoCredentialsError as e:
                raise _err("delete", extra="missing AWS credentials") from e
            except ClientError as e:
                raise _err("delete", code=_client_error_code(e)) from e
            except BotoCoreError as e:
                raise _err("delete", extra="connectivity error") from e

            # 6) Verify deletion
            try:
                self._client.head_object(Bucket=self._bucket, Key=test_key)
                raise _err("delete_verification", extra="key still exists after delete")
            except ClientError as e:
                code = _client_error_code(e)
                if code not in ("404", "NotFound", "NoSuchKey"):
                    raise _err(
                        "delete_verification",
                        code=code,
                        extra="unexpected head_object error",
                    ) from e
            except BotoCoreError as e:
                raise _err("delete_verification", extra="connectivity error") from e

        finally:
            # Best-effort cleanup if we wrote but didn't successfully delete.
            if wrote and not deleted:
                try:
                    self._client.delete_object(Bucket=self._bucket, Key=test_key)
                except Exception as e:  # noqa: BLE001
                    raise BackendTestError(
                        f"S3 test cleanup failed: bucket={self._bucket} key={test_key}"
                    ) from e

    def enumerate_page(
        self,
        *,
        prefix: str | None = None,
        cursor: str | None = None,
        page_size: int = 1000,
    ) -> EnumeratePage:
        """Return one page of S3 objects."""
        kwargs: dict[str, Any] = {"Bucket": self._bucket, "MaxKeys": page_size}
        if prefix:
            kwargs["Prefix"] = prefix
        if cursor:
            kwargs["ContinuationToken"] = cursor

        try:
            resp = self._client.list_objects_v2(**kwargs)
        except NoCredentialsError as e:
            raise BackendEnumerateError("S3 enumerate failed: missing AWS credentials") from e
        except ClientError as e:
            code = (e.response.get("Error") or {}).get("Code")
            raise BackendEnumerateError(f"S3 enumerate failed (code={code})") from e
        except BotoCoreError as e:
            raise BackendEnumerateError("S3 enumerate failed: connectivity error") from e

        objects: list[S3Object] = []
        for obj in resp.get("Contents", []) or []:
            key = obj.get("Key") or ""
            size = obj.get("Size")
            objects.append(
                S3Object(
                    name=key.rsplit("/", 1)[-1],
                    path=key,
                    size=int(size) if size is not None else None,
                )
            )

        return EnumeratePage(
            objects=objects,
            next_cursor=resp.get("NextContinuationToken") or None,
        )

    def read(self, path: str) -> bytes:
        """Read an object from S3."""
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=path)
            return resp["Body"].read()
        except NoCredentialsError as e:
            raise BackendReadError(f"S3 read failed (path={path}): missing AWS credentials") from e
        except ClientError as e:
            code = (e.response.get("Error") or {}).get("Code")
            raise BackendReadError(f"S3 read failed (path={path}) (code={code})") from e
        except BotoCoreError as e:
            raise BackendReadError(f"S3 read failed (path={path}): connectivity error") from e

    def write(self, path: str, data: bytes) -> None:
        """Write an object to S3."""
        try:
            self._client.put_object(Bucket=self._bucket, Key=path, Body=data)
        except NoCredentialsError as e:
            raise BackendWriteError(
                f"S3 write failed (path={path}): missing AWS credentials"
            ) from e
        except ClientError as e:
            code = (e.response.get("Error") or {}).get("Code")
            raise BackendWriteError(f"S3 write failed (path={path}) (code={code})") from e
        except BotoCoreError as e:
            raise BackendWriteError(f"S3 write failed (path={path}): connectivity error") from e

    def delete(self, path: str) -> None:
        """Delete an object from S3."""
        try:
            self._client.delete_object(Bucket=self._bucket, Key=path)
        except NoCredentialsError as e:
            raise BackendDeleteError(
                f"S3 delete failed (path={path}): missing AWS credentials"
            ) from e
        except ClientError as e:
            code = (e.response.get("Error") or {}).get("Code")
            raise BackendDeleteError(f"S3 delete failed (path={path}) (code={code})") from e
        except BotoCoreError as e:
            raise BackendDeleteError(f"S3 delete failed (path={path}): connectivity error") from e

    def read_stream(self, path: str) -> Iterator[bytes]:
        """Stream object bytes from S3 in 8 MB chunks."""
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=path)
        except NoCredentialsError as e:
            raise BackendReadError(f"S3 read failed (path={path}): missing AWS credentials") from e
        except ClientError as e:
            code = (e.response.get("Error") or {}).get("Code")
            raise BackendReadError(f"S3 read failed (path={path}) (code={code})") from e
        except BotoCoreError as e:
            raise BackendReadError(f"S3 read failed (path={path}): connectivity error") from e
        return resp["Body"].iter_chunks(chunk_size=8 * 1024 * 1024)

    def write_stream(self, path: str, stream: BinaryIO) -> None:
        """Upload a file-like object to S3 using multipart for files >= 8 MB."""
        from boto3.s3.transfer import TransferConfig

        config = TransferConfig(
            multipart_threshold=8 * 1024 * 1024,
            multipart_chunksize=8 * 1024 * 1024,
        )
        try:
            self._client.upload_fileobj(stream, self._bucket, path, Config=config)
        except (S3UploadFailedError, NoCredentialsError) as e:
            raise BackendWriteError(f"S3 write_stream failed (path={path}): {e}") from e
        except ClientError as e:
            code = (e.response.get("Error") or {}).get("Code")
            raise BackendWriteError(f"S3 write_stream failed (path={path}) (code={code})") from e
        except BotoCoreError as e:
            raise BackendWriteError(
                f"S3 write_stream failed (path={path}): connectivity error"
            ) from e

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

    def _optional_secret_str(self, key: str) -> Optional[str]:
        val = self.config.secrets.get(key)
        if val is None:
            return None
        if not isinstance(val, str):
            raise BackendError(f"Invalid secret type for {key}")
        val = val.strip()
        return val if val else None
