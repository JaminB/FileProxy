"""
Tests for the write cache: async upload path (view routing, enqueue_upload helper,
upload_to_backend Celery task, recover_pending_uploads management command).
"""

from __future__ import annotations

import base64
import io
import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from files.models import PendingUpload
from files.tasks import upload_to_backend
from rest_framework.test import APITestCase

from .test_api import _VAULT_ITEM_PAYLOAD, _BaseFilesTest, _make_fake_s3_client, _start_patches

User = get_user_model()

# Threshold low enough for small test payloads to hit the async path.
_SMALL_THRESHOLD = 10  # bytes
_LARGE_PAYLOAD = b"x" * 20  # 20 bytes > threshold
_SMALL_PAYLOAD = b"hi"  # 2 bytes < threshold


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


# ---------------------------------------------------------------------------
# View routing tests: JSON content-type
# ---------------------------------------------------------------------------


@override_settings(WRITE_CACHE_THRESHOLD_BYTES=_SMALL_THRESHOLD)
class WriteCacheJsonViewTests(_BaseFilesTest):
    """JSON (base64) write endpoint routes to async/sync based on payload size."""

    @patch("files.write_cache.upload_to_backend")
    def test_large_json_returns_202(self, mock_task):
        mock_task.delay.return_value = MagicMock(id="fake-task-id")
        with tempfile.TemporaryDirectory() as tmp:
            with self.settings(WRITE_CACHE_DIR=tmp):
                resp = self.client.post(
                    f"/api/v1/files/{self.vault_item_name}/write/",
                    {"path": "a/large.bin", "data_base64": _b64(_LARGE_PAYLOAD)},
                    format="json",
                )
        self.assertEqual(resp.status_code, 202, resp.text)
        self.assertEqual(resp.data["status"], "pending")
        self.assertIn("path", resp.data)
        mock_task.delay.assert_called_once()

    @patch("files.write_cache.upload_to_backend")
    def test_large_json_creates_pending_upload_record(self, mock_task):
        mock_task.delay.return_value = MagicMock(id="fake-task-id")
        path = "a/large.bin"
        with tempfile.TemporaryDirectory() as tmp:
            with self.settings(WRITE_CACHE_DIR=tmp):
                self.client.post(
                    f"/api/v1/files/{self.vault_item_name}/write/",
                    {"path": path, "data_base64": _b64(_LARGE_PAYLOAD)},
                    format="json",
                )
        self.assertEqual(PendingUpload.objects.count(), 1)
        pending = PendingUpload.objects.get()
        self.assertEqual(pending.status, PendingUpload.Status.PENDING)
        self.assertEqual(pending.connection_name, self.vault_item_name)
        self.assertEqual(pending.path, path)
        self.assertEqual(pending.expected_size, len(_LARGE_PAYLOAD))
        self.assertEqual(pending.user_id, self.user.id)

    @patch("files.write_cache.upload_to_backend")
    def test_large_json_writes_temp_file(self, mock_task):
        mock_task.delay.return_value = MagicMock(id="fake-task-id")
        with tempfile.TemporaryDirectory() as tmp:
            with self.settings(WRITE_CACHE_DIR=tmp):
                self.client.post(
                    f"/api/v1/files/{self.vault_item_name}/write/",
                    {"path": "a/large.bin", "data_base64": _b64(_LARGE_PAYLOAD)},
                    format="json",
                )
            pending = PendingUpload.objects.get()
            self.assertTrue(Path(pending.temp_file_path).exists())
            self.assertEqual(Path(pending.temp_file_path).read_bytes(), _LARGE_PAYLOAD)

    @patch("files.write_cache.upload_to_backend")
    def test_large_json_does_not_write_placeholder_to_backend(self, mock_task):
        """Async path must not touch the backend until the task completes.

        Writing a 0-byte placeholder at enqueue time would permanently destroy any
        pre-existing file at that path if the task ultimately fails or is cancelled.
        """
        mock_task.delay.return_value = MagicMock(id="fake-task-id")
        path = "a/placeholder.bin"
        with tempfile.TemporaryDirectory() as tmp:
            with self.settings(WRITE_CACHE_DIR=tmp):
                resp = self.client.post(
                    f"/api/v1/files/{self.vault_item_name}/write/",
                    {"path": path, "data_base64": _b64(_LARGE_PAYLOAD)},
                    format="json",
                )
        self.assertEqual(resp.status_code, 202)
        stored = self._fake_s3._buckets[self.bucket].get(path)
        self.assertIsNone(stored, "Enqueue must not write a backend placeholder")

    def test_small_json_returns_200(self):
        resp = self.client.post(
            f"/api/v1/files/{self.vault_item_name}/write/",
            {"path": "a/small.txt", "data_base64": _b64(_SMALL_PAYLOAD)},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.data["detail"], "OK")
        self.assertEqual(PendingUpload.objects.count(), 0)


# ---------------------------------------------------------------------------
# View routing tests: multipart content-type
# ---------------------------------------------------------------------------


@override_settings(WRITE_CACHE_THRESHOLD_BYTES=_SMALL_THRESHOLD)
class WriteCacheMultipartViewTests(_BaseFilesTest):
    """Multipart write endpoint routes to async/sync based on file size."""

    @patch("files.write_cache.upload_to_backend")
    def test_large_multipart_returns_202(self, mock_task):
        mock_task.delay.return_value = MagicMock(id="fake-task-id")
        with tempfile.TemporaryDirectory() as tmp:
            with self.settings(WRITE_CACHE_DIR=tmp):
                resp = self.client.post(
                    f"/api/v1/files/{self.vault_item_name}/write/",
                    {"path": "b/large.bin", "file": io.BytesIO(_LARGE_PAYLOAD)},
                    format="multipart",
                )
        self.assertEqual(resp.status_code, 202, resp.text)
        self.assertEqual(resp.data["status"], "pending")
        mock_task.delay.assert_called_once()

    @patch("files.write_cache.upload_to_backend")
    def test_large_multipart_creates_pending_upload_record(self, mock_task):
        mock_task.delay.return_value = MagicMock(id="fake-task-id")
        path = "b/large.bin"
        with tempfile.TemporaryDirectory() as tmp:
            with self.settings(WRITE_CACHE_DIR=tmp):
                self.client.post(
                    f"/api/v1/files/{self.vault_item_name}/write/",
                    {"path": path, "file": io.BytesIO(_LARGE_PAYLOAD)},
                    format="multipart",
                )
        self.assertEqual(PendingUpload.objects.count(), 1)
        pending = PendingUpload.objects.get()
        self.assertEqual(pending.status, PendingUpload.Status.PENDING)
        self.assertEqual(pending.expected_size, len(_LARGE_PAYLOAD))

    def test_small_multipart_returns_200(self):
        resp = self.client.post(
            f"/api/v1/files/{self.vault_item_name}/write/",
            {"path": "b/small.txt", "file": io.BytesIO(_SMALL_PAYLOAD)},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(PendingUpload.objects.count(), 0)


# ---------------------------------------------------------------------------
# View routing tests: octet-stream content-type
# ---------------------------------------------------------------------------


@override_settings(WRITE_CACHE_THRESHOLD_BYTES=_SMALL_THRESHOLD)
class WriteCacheOctetStreamViewTests(_BaseFilesTest):
    """Octet-stream write endpoint routes to async/sync based on Content-Length."""

    @patch("files.write_cache.upload_to_backend")
    def test_large_octet_stream_returns_202(self, mock_task):
        mock_task.delay.return_value = MagicMock(id="fake-task-id")
        with tempfile.TemporaryDirectory() as tmp:
            with self.settings(WRITE_CACHE_DIR=tmp):
                resp = self.client.post(
                    f"/api/v1/files/{self.vault_item_name}/write/?path=c/large.bin",
                    data=_LARGE_PAYLOAD,
                    content_type="application/octet-stream",
                    HTTP_CONTENT_LENGTH=str(len(_LARGE_PAYLOAD)),
                )
        self.assertEqual(resp.status_code, 202, resp.text)
        self.assertEqual(resp.data["status"], "pending")
        mock_task.delay.assert_called_once()

    @patch("files.write_cache.upload_to_backend")
    def test_large_octet_stream_creates_pending_upload_record(self, mock_task):
        mock_task.delay.return_value = MagicMock(id="fake-task-id")
        path = "c/large.bin"
        with tempfile.TemporaryDirectory() as tmp:
            with self.settings(WRITE_CACHE_DIR=tmp):
                self.client.post(
                    f"/api/v1/files/{self.vault_item_name}/write/?path={path}",
                    data=_LARGE_PAYLOAD,
                    content_type="application/octet-stream",
                    HTTP_CONTENT_LENGTH=str(len(_LARGE_PAYLOAD)),
                )
        self.assertEqual(PendingUpload.objects.count(), 1)
        pending = PendingUpload.objects.get()
        self.assertEqual(pending.status, PendingUpload.Status.PENDING)
        self.assertEqual(pending.expected_size, len(_LARGE_PAYLOAD))

    def test_small_octet_stream_returns_200(self):
        resp = self.client.post(
            f"/api/v1/files/{self.vault_item_name}/write/?path=c/small.bin",
            data=_SMALL_PAYLOAD,
            content_type="application/octet-stream",
            HTTP_CONTENT_LENGTH=str(len(_SMALL_PAYLOAD)),
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(PendingUpload.objects.count(), 0)


# ---------------------------------------------------------------------------
# Duplicate upload cancellation
# ---------------------------------------------------------------------------


@override_settings(WRITE_CACHE_THRESHOLD_BYTES=_SMALL_THRESHOLD)
class WriteCacheDuplicateCancellationTests(_BaseFilesTest):
    """Re-uploading the same path cancels any earlier pending uploads."""

    @patch("files.write_cache.upload_to_backend")
    def test_second_upload_cancels_first(self, mock_task):
        mock_task.delay.return_value = MagicMock(id="fake-task-id")
        path = "dup/file.bin"
        with tempfile.TemporaryDirectory() as tmp:
            with self.settings(WRITE_CACHE_DIR=tmp):
                self.client.post(
                    f"/api/v1/files/{self.vault_item_name}/write/",
                    {"path": path, "data_base64": _b64(_LARGE_PAYLOAD)},
                    format="json",
                )
                first_id = PendingUpload.objects.get().id

                self.client.post(
                    f"/api/v1/files/{self.vault_item_name}/write/",
                    {"path": path, "data_base64": _b64(_LARGE_PAYLOAD)},
                    format="json",
                )

        uploads = list(PendingUpload.objects.order_by("created_at"))
        self.assertEqual(len(uploads), 2)
        cancelled = next(u for u in uploads if u.id == first_id)
        active = next(u for u in uploads if u.id != first_id)
        self.assertEqual(cancelled.status, PendingUpload.Status.CANCELLED)
        self.assertEqual(active.status, PendingUpload.Status.PENDING)

    @patch("files.write_cache.upload_to_backend")
    def test_second_upload_deletes_first_temp_file(self, mock_task):
        mock_task.delay.return_value = MagicMock(id="fake-task-id")
        path = "dup/tempfile.bin"
        with tempfile.TemporaryDirectory() as tmp:
            with self.settings(WRITE_CACHE_DIR=tmp):
                self.client.post(
                    f"/api/v1/files/{self.vault_item_name}/write/",
                    {"path": path, "data_base64": _b64(_LARGE_PAYLOAD)},
                    format="json",
                )
                first_temp = Path(PendingUpload.objects.get().temp_file_path)
                self.assertTrue(first_temp.exists(), "First temp file should exist")

                self.client.post(
                    f"/api/v1/files/{self.vault_item_name}/write/",
                    {"path": path, "data_base64": _b64(_LARGE_PAYLOAD)},
                    format="json",
                )
            self.assertFalse(first_temp.exists(), "First temp file should be deleted")

    @patch("files.write_cache.upload_to_backend")
    def test_second_upload_not_preempted_when_first_is_fresh_uploading(self, mock_task):
        """If the first record is actively UPLOADING (fresh claimed_at), the second upload
        returns the existing record without dispatching a new task or cancelling the first.

        This prevents a race where the first task's write_stream finishes after the second
        task's and overwrites newer backend content.
        """
        mock_task.delay.return_value = MagicMock(id="fake-task-id")
        path = "dup/in_flight.bin"
        with tempfile.TemporaryDirectory() as tmp:
            with self.settings(WRITE_CACHE_DIR=tmp):
                # Enqueue the first upload.
                self.client.post(
                    f"/api/v1/files/{self.vault_item_name}/write/",
                    {"path": path, "data_base64": _b64(_LARGE_PAYLOAD)},
                    format="json",
                )
                first = PendingUpload.objects.get()
                # Simulate a worker claiming it.
                PendingUpload.objects.filter(id=first.id).update(
                    status=PendingUpload.Status.UPLOADING,
                    claimed_at=timezone.now(),
                )

                # Second upload for the same path while the first is actively UPLOADING.
                resp = self.client.post(
                    f"/api/v1/files/{self.vault_item_name}/write/",
                    {"path": path, "data_base64": _b64(_LARGE_PAYLOAD)},
                    format="json",
                )

        self.assertEqual(resp.status_code, 202)
        # Only one record; it is still UPLOADING (not cancelled or replaced).
        self.assertEqual(PendingUpload.objects.count(), 1)
        first.refresh_from_db()
        self.assertEqual(first.status, PendingUpload.Status.UPLOADING)
        # No second task dispatched.
        mock_task.delay.assert_called_once()


# ---------------------------------------------------------------------------
# Celery task: upload_to_backend
# ---------------------------------------------------------------------------


class UploadToBackendTaskTests(APITestCase):
    """Tests for the upload_to_backend Celery task (run directly, no broker)."""

    bucket = "task-test-bucket"
    connection_name = "prod"

    def setUp(self):
        self.user = User.objects.create_user(username="taskuser", password="pw")
        self.client.login(username="taskuser", password="pw")

        self._fake_s3 = _make_fake_s3_client(self.bucket)
        self._patchers = _start_patches(self._fake_s3)
        self.assertTrue(self._patchers, "No patches applied")

        resp = self.client.post(
            "/api/v1/connections/s3/",
            {**_VAULT_ITEM_PAYLOAD, "name": self.connection_name, "bucket": self.bucket},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.text)

    def tearDown(self):
        for p in reversed(self._patchers):
            p.stop()

    def _make_temp_file(self, data: bytes) -> str:
        fd, path = tempfile.mkstemp(prefix="fp_task_test_")
        os.close(fd)
        Path(path).write_bytes(data)
        return path

    def _create_pending(self, data: bytes = b"task payload", path: str = "task/file.txt"):
        temp_path = self._make_temp_file(data)
        return PendingUpload.objects.create(
            user_id=self.user.id,
            connection_name=self.connection_name,
            path=path,
            temp_file_path=temp_path,
            expected_size=len(data),
        )

    def test_task_uploads_file_and_marks_done(self):
        data = b"hello from task"
        pending = self._create_pending(data=data, path="task/upload.txt")

        upload_to_backend.apply(args=(str(pending.id),))

        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingUpload.Status.DONE)
        self.assertIsNotNone(pending.completed_at)
        self.assertFalse(Path(pending.temp_file_path).exists())
        stored = self._fake_s3._buckets[self.bucket].get("task/upload.txt")
        self.assertEqual(stored, data)

    def test_task_done_does_not_overwrite_cancellation(self):
        """If the upload is cancelled mid-flight, the task's DONE save is skipped."""
        data = b"cancelled payload"
        pending = self._create_pending(data=data, path="task/cancelled.txt")
        temp_path = pending.temp_file_path

        # Simulate cancellation happening between write_stream and the DONE update.
        def _cancel_mid_flight(path, stream):
            PendingUpload.objects.filter(id=pending.id).update(
                status=PendingUpload.Status.CANCELLED
            )

        with patch("files.tasks.get_backend_for_connection") as mock_backend_fn:
            mock_backend = MagicMock()
            mock_backend.write_stream.side_effect = _cancel_mid_flight
            mock_backend_fn.return_value = mock_backend
            upload_to_backend.apply(args=(str(pending.id),))

        pending.refresh_from_db()
        # Status must still be CANCELLED, not DONE.
        self.assertEqual(pending.status, PendingUpload.Status.CANCELLED)
        # Cleanup temp file (task deletes it before the conditional update).
        if Path(temp_path).exists():
            os.unlink(temp_path)

    def test_task_skips_already_cancelled(self):
        pending = self._create_pending()
        pending.status = PendingUpload.Status.CANCELLED
        pending.save()

        upload_to_backend.apply(args=(str(pending.id),))

        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingUpload.Status.CANCELLED)

    def test_task_skips_already_done(self):
        pending = self._create_pending()
        pending.status = PendingUpload.Status.DONE
        pending.completed_at = timezone.now()
        pending.save()

        upload_to_backend.apply(args=(str(pending.id),))

        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingUpload.Status.DONE)

    def test_task_fails_immediately_if_temp_file_missing(self):
        pending = self._create_pending()
        os.unlink(pending.temp_file_path)

        upload_to_backend.apply(args=(str(pending.id),))

        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingUpload.Status.FAILED)
        self.assertIn("not found", pending.error_message.lower())

    def test_task_nonexistent_upload_id_does_not_raise(self):
        """Task should log and return gracefully for unknown IDs."""
        result = upload_to_backend.apply(args=(str(uuid.uuid4()),))
        self.assertIsNone(result.result)

    def test_task_fails_immediately_on_missing_user(self):
        """User.DoesNotExist is a permanent error — task marks FAILED without retrying."""
        pending = self._create_pending(path="task/no_user.txt")
        # Use a user_id that doesn't exist.
        PendingUpload.objects.filter(id=pending.id).update(user_id=999999)

        with patch("files.tasks.get_backend_for_connection") as mock_fn:
            upload_to_backend.apply(args=(str(pending.id),))
            mock_fn.assert_not_called()

        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingUpload.Status.FAILED)

    def test_task_marks_failed_after_max_retries(self):
        """When max retries are exhausted via apply(), status is set to FAILED."""
        pending = self._create_pending(path="task/fail.txt")
        temp_path = pending.temp_file_path

        with patch("files.tasks.get_backend_for_connection") as mock_backend_fn:
            mock_backend = MagicMock()
            mock_backend.write_stream.side_effect = RuntimeError("backend down")
            mock_backend_fn.return_value = mock_backend
            upload_to_backend.apply(args=(str(pending.id),))

        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingUpload.Status.FAILED)
        self.assertIn("backend down", pending.error_message)
        self.assertTrue(Path(temp_path).exists())
        os.unlink(temp_path)

    def test_task_skips_uploading_with_fresh_claim(self):
        """UPLOADING + retries=0 + fresh claimed_at → another task owns it, skip."""
        pending = self._create_pending()
        pending.status = PendingUpload.Status.UPLOADING
        pending.claimed_at = timezone.now()
        pending.save()

        with patch("files.tasks.get_backend_for_connection") as mock_fn:
            upload_to_backend.apply(args=(str(pending.id),))
            mock_fn.assert_not_called()

        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingUpload.Status.UPLOADING)

    def test_task_reclaims_uploading_with_stale_claim(self):
        """UPLOADING + retries=0 + stale claimed_at → worker died, re-claim and proceed."""
        from datetime import timedelta

        data = b"stale claim payload"
        pending = self._create_pending(data=data, path="task/stale.txt")
        PendingUpload.objects.filter(id=pending.id).update(
            status=PendingUpload.Status.UPLOADING,
            claimed_at=timezone.now() - timedelta(minutes=15),
        )
        pending.refresh_from_db()

        upload_to_backend.apply(args=(str(pending.id),))

        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingUpload.Status.DONE)


# ---------------------------------------------------------------------------
# recover_pending_uploads management command
# ---------------------------------------------------------------------------


class RecoverPendingUploadsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="recover_user", password="pw")

    def _create_pending(self, status=PendingUpload.Status.PENDING, path="recover/file.txt"):
        return PendingUpload.objects.create(
            user_id=self.user.id,
            connection_name="myconn",
            path=path,
            temp_file_path="/tmp/fake_temp",  # nosec B108
            expected_size=100,
            status=status,
        )

    def test_no_pending_records_produces_no_dispatches(self):
        _patch = "files.management.commands.recover_pending_uploads.upload_to_backend"
        with patch(_patch) as mock_task:
            call_command("recover_pending_uploads", verbosity=0)
        mock_task.delay.assert_not_called()

    @patch("files.management.commands.recover_pending_uploads.upload_to_backend")
    def test_pending_records_are_dispatched(self, mock_task):
        mock_task.delay.return_value = MagicMock(id="fake-id")
        p1 = self._create_pending(status=PendingUpload.Status.PENDING, path="r/a.txt")
        p2 = self._create_pending(status=PendingUpload.Status.PENDING, path="r/b.txt")

        call_command("recover_pending_uploads", verbosity=0)

        self.assertEqual(mock_task.delay.call_count, 2)
        dispatched_ids = {str(c.args[0]) for c in mock_task.delay.call_args_list}
        self.assertIn(str(p1.id), dispatched_ids)
        self.assertIn(str(p2.id), dispatched_ids)

    @patch("files.management.commands.recover_pending_uploads.upload_to_backend")
    def test_fresh_uploading_records_are_not_touched(self, mock_task):
        # UPLOADING with a fresh claimed_at → another worker is active; leave it alone.
        p = self._create_pending(status=PendingUpload.Status.UPLOADING)
        PendingUpload.objects.filter(id=p.id).update(claimed_at=timezone.now())

        call_command("recover_pending_uploads", verbosity=0)

        p.refresh_from_db()
        self.assertEqual(p.status, PendingUpload.Status.UPLOADING)
        mock_task.delay.assert_not_called()

    @patch("files.management.commands.recover_pending_uploads.upload_to_backend")
    def test_stale_uploading_records_reset_and_dispatched(self, mock_task):
        # UPLOADING with a stale claimed_at (worker died) → reset to PENDING + dispatch.
        from datetime import timedelta

        mock_task.delay.return_value = MagicMock(id="fake-id")
        p = self._create_pending(status=PendingUpload.Status.UPLOADING)
        PendingUpload.objects.filter(id=p.id).update(
            claimed_at=timezone.now() - timedelta(minutes=15)
        )

        call_command("recover_pending_uploads", verbosity=0)

        p.refresh_from_db()
        self.assertEqual(p.status, PendingUpload.Status.PENDING)
        mock_task.delay.assert_called_once_with(str(p.id))

    @patch("files.management.commands.recover_pending_uploads.upload_to_backend")
    def test_uploading_with_null_claimed_at_reset_and_dispatched(self, mock_task):
        # UPLOADING with no claimed_at (legacy or enqueue failure) → reset + dispatch.
        mock_task.delay.return_value = MagicMock(id="fake-id")
        p = self._create_pending(status=PendingUpload.Status.UPLOADING)
        # claimed_at is None by default.

        call_command("recover_pending_uploads", verbosity=0)

        p.refresh_from_db()
        self.assertEqual(p.status, PendingUpload.Status.PENDING)
        mock_task.delay.assert_called_once_with(str(p.id))

    @patch("files.management.commands.recover_pending_uploads.upload_to_backend")
    def test_done_and_failed_records_are_not_dispatched(self, mock_task):
        mock_task.delay.return_value = MagicMock(id="fake-id")
        self._create_pending(status=PendingUpload.Status.DONE, path="r/done.txt")
        self._create_pending(status=PendingUpload.Status.FAILED, path="r/failed.txt")
        self._create_pending(status=PendingUpload.Status.CANCELLED, path="r/cancelled.txt")

        call_command("recover_pending_uploads", verbosity=0)

        mock_task.delay.assert_not_called()


# ---------------------------------------------------------------------------
# PendingUpload model
# ---------------------------------------------------------------------------


class PendingUploadModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="model_user", password="pw")

    def test_default_status_is_pending(self):
        p = PendingUpload.objects.create(
            user_id=self.user.id,
            connection_name="conn",
            path="model/file.txt",
            temp_file_path="/tmp/x",  # nosec B108
            expected_size=42,
        )
        self.assertEqual(p.status, PendingUpload.Status.PENDING)

    def test_uuid_primary_key_auto_generated(self):
        p = PendingUpload.objects.create(
            user_id=self.user.id,
            connection_name="conn",
            path="model/file2.txt",
            temp_file_path="/tmp/y",  # nosec B108
            expected_size=1,
        )
        self.assertIsNotNone(p.id)
        self.assertEqual(len(str(p.id)), 36)  # UUID4 string length

    def test_str_contains_key_fields(self):
        p = PendingUpload.objects.create(
            user_id=self.user.id,
            connection_name="myconn",
            path="model/file3.txt",
            temp_file_path="/tmp/z",  # nosec B108
            expected_size=1,
        )
        s = str(p)
        self.assertIn("myconn", s)
        self.assertIn("pending", s)
