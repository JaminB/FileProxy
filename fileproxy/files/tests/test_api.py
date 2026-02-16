from __future__ import annotations

import base64
import io
from typing import Any
from unittest.mock import patch

from botocore.exceptions import ClientError
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

User = get_user_model()


class _FakePaginator:
    def __init__(self, client: "_FakeS3Client"):
        self._client = client

    def paginate(self, **kwargs: Any):
        bucket = kwargs["Bucket"]
        prefix = kwargs.get("Prefix") or ""

        contents = []
        for key, data in self._client._buckets.get(bucket, {}).items():
            if key.startswith(prefix):
                contents.append({"Key": key, "Size": len(data)})

        # Match boto3: if no results, omit Contents entirely or use empty
        yield {"Contents": contents} if contents else {"Contents": []}


class _FakeS3Client:
    """
    Minimal fake for the boto3 S3 client methods used by S3Backend:
      - head_bucket
      - put_object
      - get_object
      - delete_object
      - head_object
      - get_paginator(list_objects_v2)
    """

    def __init__(self, *, existing_buckets: list[str] | None = None):
        self._buckets: dict[str, dict[str, bytes]] = {}
        for b in existing_buckets or []:
            self._buckets[b] = {}

    def _client_error(self, code: str, message: str = "error") -> ClientError:
        return ClientError(
            {"Error": {"Code": code, "Message": message}}, "FakeOperation"
        )

    def head_bucket(self, *, Bucket: str):
        if Bucket not in self._buckets:
            raise self._client_error("404", "NoSuchBucket")

    def put_object(self, *, Bucket: str, Key: str, Body: bytes):
        if Bucket not in self._buckets:
            raise self._client_error("404", "NoSuchBucket")
        self._buckets[Bucket][Key] = Body

    def get_object(self, *, Bucket: str, Key: str):
        if Bucket not in self._buckets:
            raise self._client_error("404", "NoSuchBucket")
        if Key not in self._buckets[Bucket]:
            raise self._client_error("NoSuchKey", "NotFound")
        return {"Body": io.BytesIO(self._buckets[Bucket][Key])}

    def delete_object(self, *, Bucket: str, Key: str):
        if Bucket not in self._buckets:
            raise self._client_error("404", "NoSuchBucket")
        self._buckets[Bucket].pop(Key, None)

    def head_object(self, *, Bucket: str, Key: str):
        if Bucket not in self._buckets:
            raise self._client_error("404", "NoSuchBucket")
        if Key not in self._buckets[Bucket]:
            raise self._client_error("404", "NotFound")
        return {"ContentLength": len(self._buckets[Bucket][Key])}

    def get_paginator(self, operation_name: str):
        if operation_name != "list_objects_v2":
            raise ValueError(f"Unsupported paginator op: {operation_name}")
        return _FakePaginator(self)


class FilesApiS3Tests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u1", password="pw")
        self.client.login(username="u1", password="pw")

        self.vault_item_name = "prod"
        self.bucket = "fileproxy-test-bucket"

        self._fake_s3 = _FakeS3Client(existing_buckets=[self.bucket])

        # Patch whatever symbol core.backends.s3 actually uses.
        self._patchers = []
        for target in ("core.backends.s3.boto3.client", "core.backends.s3.client"):
            try:
                p = patch(target, return_value=self._fake_s3)
                p.start()
                self._patchers.append(p)
            except Exception:
                # target doesn't exist in that module, ignore
                pass

        # Sanity: ensure at least one patch applied
        self.assertTrue(
            self._patchers,
            "Failed to patch core.backends.s3 boto client; check import style",
        )

        resp = self.client.post(
            "/api/v1/vault-items/s3/",
            {
                "name": self.vault_item_name,
                "bucket": self.bucket,
                "access_key_id": "AKIA1234567890ABCDE",
                "secret_access_key": "supersecretsecretsecretsecretsecret",
                "session_token": "",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.text)

    def tearDown(self):
        for p in reversed(self._patchers):
            p.stop()

    def test_write_read_objects_delete_roundtrip(self):
        path = "folder/a.txt"
        payload = b"hello files api"
        payload_b64 = base64.b64encode(payload).decode("ascii")

        # write
        resp = self.client.post(
            f"/api/v1/files/{self.vault_item_name}/write/",
            {"path": path, "data_base64": payload_b64},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.data["path"], path)

        # read
        resp = self.client.get(
            f"/api/v1/files/{self.vault_item_name}/read/", {"path": path}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.data["path"], path)
        self.assertEqual(base64.b64decode(resp.data["data_base64"]), payload)

        # objects (no prefix)
        resp = self.client.get(f"/api/v1/files/{self.vault_item_name}/objects/")
        self.assertEqual(resp.status_code, 200, resp.text)
        paths = {o["path"] for o in resp.data}
        self.assertIn(path, paths)

        # objects (prefix filters)
        resp = self.client.get(
            f"/api/v1/files/{self.vault_item_name}/objects/", {"prefix": "folder/"}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual({o["path"] for o in resp.data}, {path})

        # delete
        resp = self.client.post(
            f"/api/v1/files/{self.vault_item_name}/delete/",
            {"path": path},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        # objects after delete
        resp = self.client.get(f"/api/v1/files/{self.vault_item_name}/objects/")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertNotIn(path, {o["path"] for o in resp.data})

    def test_test_endpoint_runs_backend_healthcheck(self):
        resp = self.client.post(
            f"/api/v1/files/{self.vault_item_name}/test/", format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.data["detail"], "Connection OK.")

    def test_unknown_vault_item_name_returns_404(self):
        resp = self.client.get("/api/v1/files/does-not-exist/objects/")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("detail", resp.data)
