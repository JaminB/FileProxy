from __future__ import annotations

import base64
import io
from typing import Any
from unittest.mock import patch

from botocore.exceptions import ClientError
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from core.backends.base import BackendTestError

User = get_user_model()


class _FakeStreamingBody:
    """Minimal stand-in for boto3's StreamingBody that supports both read() and iter_chunks()."""

    def __init__(self, data: bytes):
        self._stream = io.BytesIO(data)

    def read(self) -> bytes:
        return self._stream.read()

    def iter_chunks(self, chunk_size: int = 1024 * 1024):
        while True:
            chunk = self._stream.read(chunk_size)
            if not chunk:
                break
            yield chunk


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
        return {"Body": _FakeStreamingBody(self._buckets[Bucket][Key])}

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

    def upload_fileobj(self, fileobj, bucket: str, key: str, Config=None):
        if bucket not in self._buckets:
            raise self._client_error("404", "NoSuchBucket")
        self._buckets[bucket][key] = fileobj.read()

    def list_objects_v2(self, *, Bucket, Prefix="", MaxKeys=1000, ContinuationToken=None):
        if Bucket not in self._buckets:
            raise self._client_error("NoSuchBucket", "The bucket does not exist")
        prefix = Prefix or ""
        all_keys = sorted(k for k in self._buckets[Bucket] if k.startswith(prefix))
        start = 0
        if ContinuationToken:
            try:
                start = all_keys.index(ContinuationToken) + 1
            except ValueError:
                # Simulate S3 behavior: invalid continuation tokens result in an error
                raise self._client_error(
                    "InvalidArgument", "Invalid or unknown continuation token"
                )
        page_keys = all_keys[start: start + MaxKeys]
        result = {}
        if page_keys:
            result["Contents"] = [
                {"Key": k, "Size": len(self._buckets[Bucket][k])} for k in page_keys
            ]
        if page_keys and start + MaxKeys < len(all_keys):
            result["NextContinuationToken"] = page_keys[-1]
            result["IsTruncated"] = True
        else:
            result["IsTruncated"] = False
        return result

    def get_paginator(self, operation_name: str):
        if operation_name != "list_objects_v2":
            raise ValueError(f"Unsupported paginator op: {operation_name}")
        return _FakePaginator(self)


def _make_fake_s3_client(bucket: str) -> _FakeS3Client:
    return _FakeS3Client(existing_buckets=[bucket])


def _start_patches(fake_s3: _FakeS3Client) -> list:
    patchers = []
    for target in ("core.backends.s3.boto3.client", "core.backends.s3.client"):
        try:
            p = patch(target, return_value=fake_s3)
            p.start()
            patchers.append(p)
        except Exception:
            pass
    return patchers


_VAULT_ITEM_PAYLOAD = {
    "name": "prod",
    "bucket": "fileproxy-test-bucket",
    "access_key_id": "AKIA1234567890ABCDE",
    "secret_access_key": "supersecretsecretsecretsecretsecret",
    "session_token": "",
}


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
        paths = {o["path"] for o in resp.data["objects"]}
        self.assertIn(path, paths)

        # objects (prefix filters)
        resp = self.client.get(
            f"/api/v1/files/{self.vault_item_name}/objects/", {"prefix": "folder/"}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual({o["path"] for o in resp.data["objects"]}, {path})

        # delete
        resp = self.client.delete(
            f"/api/v1/files/{self.vault_item_name}/object/?path={path}"
        )
        self.assertEqual(resp.status_code, 204, resp.text if hasattr(resp, "text") else "")

        # objects after delete
        resp = self.client.get(f"/api/v1/files/{self.vault_item_name}/objects/")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertNotIn(path, {o["path"] for o in resp.data["objects"]})

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


class _BaseFilesTest(APITestCase):
    """Shared setUp/tearDown for files API tests."""

    vault_item_name = "prod"
    bucket = "fileproxy-test-bucket"

    def setUp(self):
        self.user = User.objects.create_user(username="u1", password="pw")
        self.client.login(username="u1", password="pw")
        self._fake_s3 = _make_fake_s3_client(self.bucket)
        self._patchers = _start_patches(self._fake_s3)
        self.assertTrue(self._patchers, "No patches applied; check import style")
        resp = self.client.post(
            "/api/v1/vault-items/s3/",
            {**_VAULT_ITEM_PAYLOAD, "name": self.vault_item_name, "bucket": self.bucket},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.text)

    def tearDown(self):
        for p in reversed(self._patchers):
            p.stop()

    def _write(self, path: str, data: bytes = b"test data") -> None:
        resp = self.client.post(
            f"/api/v1/files/{self.vault_item_name}/write/",
            {"path": path, "data_base64": base64.b64encode(data).decode("ascii")},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.text)


class FilesListTests(APITestCase):
    bucket = "fileproxy-test-bucket"

    def setUp(self):
        self.user = User.objects.create_user(username="u1", password="pw")
        self.client.login(username="u1", password="pw")
        self._fake_s3 = _make_fake_s3_client(self.bucket)
        self._patchers = _start_patches(self._fake_s3)
        self.assertTrue(self._patchers, "No patches applied; check import style")
        resp = self.client.post(
            "/api/v1/vault-items/s3/",
            {**_VAULT_ITEM_PAYLOAD, "bucket": self.bucket},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.text)

    def tearDown(self):
        for p in reversed(self._patchers):
            p.stop()

    def test_list_returns_vault_items(self):
        resp = self.client.get("/api/v1/files/")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(len(resp.data), 1)
        item = resp.data[0]
        self.assertEqual(item["name"], _VAULT_ITEM_PAYLOAD["name"])
        self.assertEqual(item["kind"], "aws_s3")
        for field in ("id", "created_at", "updated_at", "rotated_at"):
            self.assertIn(field, item)
        # Secrets must not appear
        self.assertNotIn("access_key_id", item)
        self.assertNotIn("secret_access_key", item)

    def test_list_is_scoped_to_user(self):
        # Second user with their own vault item
        user2 = User.objects.create_user(username="u2", password="pw")
        client2 = self.client_class()
        client2.login(username="u2", password="pw")

        bucket2 = "user2-bucket"
        fake2 = _make_fake_s3_client(bucket2)
        patchers2 = _start_patches(fake2)
        try:
            resp = client2.post(
                "/api/v1/vault-items/s3/",
                {
                    **_VAULT_ITEM_PAYLOAD,
                    "name": "user2item",
                    "bucket": bucket2,
                },
                format="json",
            )
            self.assertEqual(resp.status_code, 201, resp.text)

            # u1 only sees their item
            resp1 = self.client.get("/api/v1/files/")
            self.assertEqual(resp1.status_code, 200)
            names1 = {i["name"] for i in resp1.data}
            self.assertIn(_VAULT_ITEM_PAYLOAD["name"], names1)
            self.assertNotIn("user2item", names1)

            # u2 only sees their item
            resp2 = client2.get("/api/v1/files/")
            self.assertEqual(resp2.status_code, 200)
            names2 = {i["name"] for i in resp2.data}
            self.assertIn("user2item", names2)
            self.assertNotIn(_VAULT_ITEM_PAYLOAD["name"], names2)
        finally:
            for p in reversed(patchers2):
                p.stop()

    def test_list_unauthenticated_returns_401(self):
        self.client.logout()
        resp = self.client.get("/api/v1/files/")
        self.assertIn(resp.status_code, (401, 403))


class FilesObjectsTests(_BaseFilesTest):
    def test_objects_empty_prefix_returns_all(self):
        self._write("a/one.txt", b"data1")
        self._write("b/two.txt", b"data2")

        resp = self.client.get(f"/api/v1/files/{self.vault_item_name}/objects/")
        self.assertEqual(resp.status_code, 200, resp.text)
        paths = {o["path"] for o in resp.data["objects"]}
        self.assertIn("a/one.txt", paths)
        self.assertIn("b/two.txt", paths)

    def test_objects_prefix_filters_results(self):
        self._write("a/one.txt", b"data1")
        self._write("b/two.txt", b"data2")

        resp = self.client.get(
            f"/api/v1/files/{self.vault_item_name}/objects/", {"prefix": "a/"}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        paths = {o["path"] for o in resp.data["objects"]}
        self.assertIn("a/one.txt", paths)
        self.assertNotIn("b/two.txt", paths)

    def test_objects_unknown_vault_item_returns_404(self):
        resp = self.client.get("/api/v1/files/no-such-item/objects/")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("detail", resp.data)


class FilesReadTests(_BaseFilesTest):
    def test_read_returns_base64_data(self):
        payload = b"read me back"
        path = "read/test.bin"
        self._write(path, payload)

        resp = self.client.get(
            f"/api/v1/files/{self.vault_item_name}/read/", {"path": path}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.data["path"], path)
        self.assertEqual(base64.b64decode(resp.data["data_base64"]), payload)

    def test_read_missing_path_param_returns_400(self):
        resp = self.client.get(f"/api/v1/files/{self.vault_item_name}/read/")
        self.assertEqual(resp.status_code, 400)

    def test_read_nonexistent_path_returns_400(self):
        resp = self.client.get(
            f"/api/v1/files/{self.vault_item_name}/read/",
            {"path": "does/not/exist.txt"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_read_unknown_vault_item_returns_404(self):
        resp = self.client.get(
            "/api/v1/files/no-such-item/read/", {"path": "anything.txt"}
        )
        self.assertEqual(resp.status_code, 404)
        self.assertIn("detail", resp.data)


class FilesWriteTests(_BaseFilesTest):
    def test_write_creates_object(self):
        path = "write/new.txt"
        data = b"brand new content"
        payload_b64 = base64.b64encode(data).decode("ascii")

        resp = self.client.post(
            f"/api/v1/files/{self.vault_item_name}/write/",
            {"path": path, "data_base64": payload_b64},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.data["path"], path)

        # Confirm object is enumerable
        resp = self.client.get(f"/api/v1/files/{self.vault_item_name}/objects/")
        self.assertEqual(resp.status_code, 200)
        paths = {o["path"] for o in resp.data["objects"]}
        self.assertIn(path, paths)

    def test_write_missing_path_returns_400(self):
        resp = self.client.post(
            f"/api/v1/files/{self.vault_item_name}/write/",
            {"data_base64": base64.b64encode(b"data").decode()},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_write_missing_data_base64_returns_400(self):
        resp = self.client.post(
            f"/api/v1/files/{self.vault_item_name}/write/",
            {"path": "some/path.txt"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_write_unknown_vault_item_returns_404(self):
        resp = self.client.post(
            "/api/v1/files/no-such-item/write/",
            {"path": "p.txt", "data_base64": base64.b64encode(b"x").decode()},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)
        self.assertIn("detail", resp.data)


class FilesWriteMultipartTests(_BaseFilesTest):
    def test_write_multipart_creates_object(self):
        path = "upload/multi.txt"
        data = b"multipart content"

        resp = self.client.post(
            f"/api/v1/files/{self.vault_item_name}/write/",
            {"path": path, "file": io.BytesIO(data)},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.data["path"], path)

        resp = self.client.get(f"/api/v1/files/{self.vault_item_name}/objects/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(path, {o["path"] for o in resp.data["objects"]})

    def test_write_multipart_missing_path_returns_400(self):
        resp = self.client.post(
            f"/api/v1/files/{self.vault_item_name}/write/",
            {"file": io.BytesIO(b"data")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400)

    def test_write_multipart_missing_file_returns_400(self):
        resp = self.client.post(
            f"/api/v1/files/{self.vault_item_name}/write/",
            {"path": "some/path.txt"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400)


class FilesWriteOctetStreamTests(_BaseFilesTest):
    def test_write_octet_stream_creates_object(self):
        path = "upload/binary.bin"
        data = b"\x00\x01\x02\x03binary data"

        resp = self.client.post(
            f"/api/v1/files/{self.vault_item_name}/write/?path={path}",
            data=data,
            content_type="application/octet-stream",
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.data["path"], path)

        resp = self.client.get(f"/api/v1/files/{self.vault_item_name}/objects/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(path, {o["path"] for o in resp.data["objects"]})

    def test_write_octet_stream_missing_path_returns_400(self):
        resp = self.client.post(
            f"/api/v1/files/{self.vault_item_name}/write/",
            data=b"some data",
            content_type="application/octet-stream",
        )
        self.assertEqual(resp.status_code, 400)


class FilesDeleteTests(_BaseFilesTest):
    def test_delete_removes_object(self):
        path = "to/delete.txt"
        self._write(path, b"goodbye")

        # Confirm it exists
        resp = self.client.get(f"/api/v1/files/{self.vault_item_name}/objects/")
        self.assertIn(path, {o["path"] for o in resp.data["objects"]})

        # Delete
        resp = self.client.delete(
            f"/api/v1/files/{self.vault_item_name}/object/?path={path}"
        )
        self.assertEqual(resp.status_code, 204)

        # Confirm it is gone
        resp = self.client.get(f"/api/v1/files/{self.vault_item_name}/objects/")
        self.assertNotIn(path, {o["path"] for o in resp.data["objects"]})

    def test_delete_missing_path_returns_400(self):
        resp = self.client.delete(f"/api/v1/files/{self.vault_item_name}/object/")
        self.assertEqual(resp.status_code, 400)

    def test_delete_unknown_vault_item_returns_404(self):
        resp = self.client.delete("/api/v1/files/no-such-item/object/?path=anything.txt")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("detail", resp.data)


class FilesTestEndpointTests(_BaseFilesTest):
    def test_test_success(self):
        resp = self.client.post(
            f"/api/v1/files/{self.vault_item_name}/test/", format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.data["detail"], "Connection OK.")

    def test_test_unknown_vault_item_returns_404(self):
        resp = self.client.post("/api/v1/files/no-such-item/test/", format="json")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("detail", resp.data)

    def test_test_backend_connection_failure_returns_400(self):
        # Make head_bucket raise to simulate a connection failure.
        # BackendTestError is raised by S3Backend.test() when the bucket check fails.
        original_head_bucket = self._fake_s3.head_bucket

        def _failing_head_bucket(**kwargs):
            from botocore.exceptions import ClientError
            raise ClientError(
                {"Error": {"Code": "403", "Message": "Access Denied"}}, "HeadBucket"
            )

        self._fake_s3.head_bucket = _failing_head_bucket
        try:
            resp = self.client.post(
                f"/api/v1/files/{self.vault_item_name}/test/", format="json"
            )
            self.assertEqual(resp.status_code, 400)
            self.assertIn("detail", resp.data)
        finally:
            self._fake_s3.head_bucket = original_head_bucket


class FilesDownloadTests(_BaseFilesTest):
    def test_download_returns_binary_response(self):
        payload = b"\x00\x01\x02binary content\xff"
        path = "dl/test.bin"
        self._write(path, payload)

        resp = self.client.get(
            f"/api/v1/files/{self.vault_item_name}/download/", {"path": path}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/octet-stream", resp.get("Content-Type", ""))
        self.assertIn("attachment", resp.get("Content-Disposition", ""))
        self.assertEqual(b"".join(resp.streaming_content), payload)

    def test_download_missing_path_returns_400(self):
        resp = self.client.get(f"/api/v1/files/{self.vault_item_name}/download/")
        self.assertEqual(resp.status_code, 400)

    def test_download_nonexistent_path_returns_400(self):
        resp = self.client.get(
            f"/api/v1/files/{self.vault_item_name}/download/",
            {"path": "does/not/exist.bin"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_download_unknown_vault_item_returns_404(self):
        resp = self.client.get(
            "/api/v1/files/no-such-item/download/", {"path": "anything.bin"}
        )
        self.assertEqual(resp.status_code, 404)
        self.assertIn("detail", resp.data)


class FilesObjectsPaginationTests(_BaseFilesTest):
    def test_page_size_limits_results(self):
        for i in range(5):
            self._write(f"file{i:02d}.txt", b"x")

        resp = self.client.get(
            f"/api/v1/files/{self.vault_item_name}/objects/", {"page_size": 2}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertIn("objects", resp.data)
        self.assertIn("next_cursor", resp.data)
        self.assertEqual(len(resp.data["objects"]), 2)
        self.assertIsNotNone(resp.data["next_cursor"])

    def test_cursor_advances_page(self):
        for i in range(4):
            self._write(f"pg{i:02d}.txt", b"x")

        resp1 = self.client.get(
            f"/api/v1/files/{self.vault_item_name}/objects/", {"page_size": 2}
        )
        self.assertEqual(resp1.status_code, 200)
        cursor = resp1.data["next_cursor"]
        self.assertIsNotNone(cursor)

        resp2 = self.client.get(
            f"/api/v1/files/{self.vault_item_name}/objects/",
            {"page_size": 2, "cursor": cursor},
        )
        self.assertEqual(resp2.status_code, 200)
        paths1 = {o["path"] for o in resp1.data["objects"]}
        paths2 = {o["path"] for o in resp2.data["objects"]}
        self.assertFalse(paths1 & paths2, "Pages should not overlap")

    def test_last_page_has_null_next_cursor(self):
        self._write("only.txt", b"x")

        resp = self.client.get(
            f"/api/v1/files/{self.vault_item_name}/objects/", {"page_size": 1000}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.data["next_cursor"])

    def test_invalid_page_size_returns_400(self):
        resp = self.client.get(
            f"/api/v1/files/{self.vault_item_name}/objects/", {"page_size": 0}
        )
        self.assertEqual(resp.status_code, 400)

    def test_response_always_has_both_keys(self):
        resp = self.client.get(f"/api/v1/files/{self.vault_item_name}/objects/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("objects", resp.data)
        self.assertIn("next_cursor", resp.data)


class FilesWriteStreamTests(_BaseFilesTest):
    def test_write_stream_via_multipart_roundtrip(self):
        """Large binary data written via multipart (write_stream) round-trips cleanly."""
        path = "stream/large.bin"
        # 1 MB of repeating bytes — exercises the upload_fileobj path
        data = bytes(range(256)) * (1024 * 4)

        resp = self.client.post(
            f"/api/v1/files/{self.vault_item_name}/write/",
            {"path": path, "file": io.BytesIO(data)},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.data["path"], path)

        # Confirm it lands correctly via the read endpoint
        resp = self.client.get(
            f"/api/v1/files/{self.vault_item_name}/read/", {"path": path}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(base64.b64decode(resp.data["data_base64"]), data)
