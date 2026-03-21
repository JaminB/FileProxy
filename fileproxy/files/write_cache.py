from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from typing import IO
from uuid import UUID, uuid4

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone

from .models import PendingUpload
from .tasks import upload_to_backend

logger = logging.getLogger(__name__)


def _temp_dir() -> Path:
    d = Path(settings.WRITE_CACHE_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_bytes_to_temp(data: bytes, upload_id: UUID) -> Path:
    path = _temp_dir() / str(upload_id)
    path.write_bytes(data)
    return path


def _write_stream_to_temp(stream: IO[bytes], upload_id: UUID) -> Path:
    path = _temp_dir() / str(upload_id)
    with path.open("wb") as f:
        for chunk in iter(lambda: stream.read(65536), b""):
            f.write(chunk)
    return path


def _cancel_stale_uploads(user_id: int, connection_name: str, path: str) -> None:
    """Cancel PENDING and stale UPLOADING records for the same (user, connection, path).

    Fresh UPLOADING records (``claimed_at`` within the last 10 minutes) are left alone;
    ``enqueue_upload`` returns early in that case before this function is called.
    """
    stale_cutoff = timezone.now() - timedelta(minutes=10)
    stale = (
        PendingUpload.objects.filter(
            user_id=user_id,
            connection_name=connection_name,
            path=path,
            status__in=(PendingUpload.Status.PENDING, PendingUpload.Status.UPLOADING),
        )
        # Exclude fresh UPLOADING records (a live worker owns them).
        .exclude(
            status=PendingUpload.Status.UPLOADING,
            claimed_at__isnull=False,
            claimed_at__gte=stale_cutoff,
        )
    )
    for record in stale:
        try:
            temp = Path(record.temp_file_path)
            if temp.exists():
                temp.unlink()
        except OSError:
            logger.warning("Could not delete stale temp file: %s", record.temp_file_path)
        record.status = PendingUpload.Status.CANCELLED
        record.save(update_fields=["status"])


def enqueue_upload(
    *,
    user: AbstractBaseUser,
    connection_name: str,
    path: str,
    backend,
    data: bytes | None = None,
    stream: IO[bytes] | None = None,
    size: int,
) -> PendingUpload:
    """
    Buffer a file locally and dispatch a Celery task to upload it to the backend.

    Exactly one of ``data`` (bytes) or ``stream`` (file-like) must be provided.
    Creates a 0-byte placeholder in the backend immediately, then returns a
    ``PendingUpload`` record after dispatching the background task.
    """
    if (data is None) == (stream is None):
        raise ValueError("Provide exactly one of data or stream")

    user_id = user.id
    _stale_cutoff = timezone.now() - timedelta(minutes=10)

    # If a fresh UPLOADING record exists for this (user, connection, path), don't preempt
    # it: the in-flight write_stream call could finish after any new task's and overwrite
    # newer content.  Return the existing record so the caller gets a 202 with the same path.
    fresh = PendingUpload.objects.filter(
        user_id=user_id,
        connection_name=connection_name,
        path=path,
        status=PendingUpload.Status.UPLOADING,
        claimed_at__isnull=False,
        claimed_at__gte=_stale_cutoff,
    ).first()
    if fresh:
        logger.info(
            "enqueue_upload: fresh UPLOADING record exists for %s/%s, returning it",
            connection_name,
            path,
        )
        return fresh

    upload_id = uuid4()

    _cancel_stale_uploads(user_id, connection_name, path)

    if data is not None:
        temp_path = _write_bytes_to_temp(data, upload_id)
    else:
        temp_path = _write_stream_to_temp(stream, upload_id)

    pending = None
    try:
        pending = PendingUpload.objects.create(
            id=upload_id,
            user_id=user_id,
            connection_name=connection_name,
            path=path,
            temp_file_path=str(temp_path),
            expected_size=size,
        )
        result = upload_to_backend.delay(str(upload_id))
        pending.celery_task_id = result.id
        pending.save(update_fields=["celery_task_id"])
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not delete temp file after enqueue failure: %s", temp_path)
        if pending is not None:
            try:
                pending.delete()
            except Exception:
                logger.warning(
                    "Could not delete PendingUpload %s after dispatch failure", upload_id
                )
        raise

    return pending
