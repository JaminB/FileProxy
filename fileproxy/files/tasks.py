from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from .models import PendingUpload
from .services import ConnectionNotFound, get_backend_for_connection

logger = logging.getLogger(__name__)

User = get_user_model()


def _fail(pending: PendingUpload, message: str) -> None:
    """Conditionally mark a PendingUpload FAILED only if it is still UPLOADING."""
    updated = PendingUpload.objects.filter(
        id=pending.id, status=PendingUpload.Status.UPLOADING
    ).update(status=PendingUpload.Status.FAILED, error_message=message)
    if updated:
        logger.error("upload_to_backend: failed %s — %s", pending.id, message)
    else:
        logger.info(
            "upload_to_backend: skipped final FAILED save for %s (status changed)", pending.id
        )


@shared_task(bind=True, max_retries=3, name="files.upload_to_backend")
def upload_to_backend(self, upload_id: str) -> None:
    try:
        pending = PendingUpload.objects.get(id=upload_id)
    except PendingUpload.DoesNotExist:
        logger.warning("upload_to_backend: PendingUpload %s not found", upload_id)
        return

    if pending.status not in (PendingUpload.Status.PENDING, PendingUpload.Status.UPLOADING):
        logger.info("upload_to_backend: skipping %s (status=%s)", upload_id, pending.status)
        return

    _stale_cutoff = timezone.now() - timedelta(minutes=10)

    if pending.status == PendingUpload.Status.PENDING:
        # First attempt: CAS PENDING → UPLOADING and stamp claimed_at.
        updated = PendingUpload.objects.filter(
            id=upload_id, status=PendingUpload.Status.PENDING
        ).update(status=PendingUpload.Status.UPLOADING, claimed_at=timezone.now())
        if not updated:
            # Another worker claimed it between the get() and now.
            logger.info("upload_to_backend: could not claim %s, skipping", upload_id)
            return
    elif self.request.retries == 0:
        # UPLOADING on first delivery. Check if the existing claim is still fresh.
        if pending.claimed_at is not None and pending.claimed_at >= _stale_cutoff:
            # Fresh claim — another worker is likely active; skip.
            logger.info(
                "upload_to_backend: %s has a fresh claim (%s), skipping",
                upload_id,
                pending.claimed_at,
            )
            return
        # Stale or missing claim — re-claim atomically via CAS so only one worker proceeds.
        logger.info("upload_to_backend: re-claiming stale record %s", upload_id)
        updated = (
            PendingUpload.objects.filter(id=upload_id, status=PendingUpload.Status.UPLOADING)
            .filter(Q(claimed_at__isnull=True) | Q(claimed_at__lt=_stale_cutoff))
            .update(claimed_at=timezone.now())
        )
        if not updated:
            # Another worker won the re-claim race.
            logger.info(
                "upload_to_backend: could not re-claim %s (already claimed), skipping", upload_id
            )
            return
    # Else: UPLOADING and retries > 0 → we own it from a previous backend-failure retry.

    temp_path = Path(pending.temp_file_path)

    if not temp_path.exists():
        _fail(pending, f"Temp file not found: {temp_path}")
        return

    try:
        user = User.objects.get(id=pending.user_id)
        backend = get_backend_for_connection(user=user, connection_name=pending.connection_name)
    except (User.DoesNotExist, ConnectionNotFound) as exc:
        # Permanent errors — retrying won't help.
        _fail(pending, str(exc))
        return

    # Re-check status right before the backend write. A concurrent enqueue_upload
    # for the same (user, connection, path) may have cancelled this record after
    # we claimed it (PENDING → UPLOADING) but before we started uploading.
    current_status = (
        PendingUpload.objects.filter(id=pending.id).values_list("status", flat=True).first()
    )
    if current_status != PendingUpload.Status.UPLOADING:
        logger.info(
            "upload_to_backend: aborting %s before backend write (status=%s)",
            upload_id,
            current_status,
        )
        return

    try:
        with temp_path.open("rb") as f:
            backend.write_stream(pending.path, f)
    except FileNotFoundError:
        _fail(pending, "Temp file disappeared during upload")
        return
    except Exception as exc:
        retries = self.request.retries
        logger.warning(
            "upload_to_backend: attempt %d failed for %s: %s", retries + 1, upload_id, exc
        )
        PendingUpload.objects.filter(id=upload_id).update(retry_count=retries + 1)
        if retries < self.max_retries:
            raise self.retry(exc=exc, countdown=4**retries)
        # Max retries reached — keep temp file for inspection.
        _fail(pending, str(exc))
        return

    # Success — only transition from UPLOADING to avoid overwriting a concurrent cancellation.
    try:
        temp_path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not delete temp file: %s", temp_path)

    updated = PendingUpload.objects.filter(
        id=pending.id, status=PendingUpload.Status.UPLOADING
    ).update(status=PendingUpload.Status.DONE, completed_at=timezone.now())
    if updated:
        logger.info("upload_to_backend: completed %s (%s bytes)", upload_id, pending.expected_size)
    else:
        logger.info("upload_to_backend: skipped final DONE save for %s (status changed)", upload_id)
