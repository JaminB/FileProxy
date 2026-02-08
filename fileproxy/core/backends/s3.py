from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from .base import Backend, BackendConfig, BackendConnectionError, BackendError


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
        """Validate S3 connectivity and credentials."""
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except NoCredentialsError as e:
            raise BackendConnectionError("Missing AWS credentials") from e
        except ClientError as e:
            code = (e.response.get("Error") or {}).get("Code")
            msg = f"S3 head_bucket failed (bucket={self._bucket}, code={code})"
            raise BackendConnectionError(msg) from e
        except BotoCoreError as e:
            raise BackendConnectionError("S3 connectivity check failed") from e

    def enumerate(self, *, prefix: str | None = None) -> Iterable[S3Object]:
        """List objects in the bucket."""
        paginator = self._client.get_paginator("list_objects_v2")
        kwargs: dict[str, Any] = {"Bucket": self._bucket}
        if prefix:
            kwargs["Prefix"] = prefix

        try:
            for page in paginator.paginate(**kwargs):
                for obj in page.get("Contents", []) or []:
                    key = obj.get("Key") or ""
                    size = obj.get("Size")
                    yield S3Object(
                        name=key.rsplit("/", 1)[-1],
                        path=key,
                        size=int(size) if size is not None else None,
                    )
        except (ClientError, BotoCoreError) as e:
            raise BackendError("S3 enumerate failed") from e

    def read(self, path: str) -> bytes:
        """Read an object from S3."""
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=path)
            return resp["Body"].read()
        except (ClientError, BotoCoreError) as e:
            raise BackendError(f"S3 read failed (path={path})") from e

    def write(self, path: str, data: bytes) -> None:
        """Write an object to S3."""
        try:
            self._client.put_object(Bucket=self._bucket, Key=path, Body=data)
        except (ClientError, BotoCoreError) as e:
            raise BackendError(f"S3 write failed (path={path})") from e

    def delete(self, path: str) -> None:
        """Delete an object from S3."""
        try:
            self._client.delete_object(Bucket=self._bucket, Key=path)
        except (ClientError, BotoCoreError) as e:
            raise BackendError(f"S3 delete failed (path={path})") from e

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
