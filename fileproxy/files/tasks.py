from __future__ import annotations

import logging
from pathlib import Path

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from .services import get_backend_for_connection

logger = logging.getLogger(__name__)

User = get_user_model()


@shared_task(bind=True, max_retries=3, name="files.upload_to_backend")
def upload_to_backend(self, upload_id: str) -> None:
    from .models import PendingUpload

    try:
        pending = PendingUpload.objects.get(id=upload_id)
    except PendingUpload.DoesNotExist:
        logger.warning("upload_to_backend: PendingUpload %s not found", upload_id)
        return

    if pending.status not in (PendingUpload.Status.PENDING, PendingUpload.Status.UPLOADING):
        logger.info(
            "upload_to_backend: skipping %s (status=%s)", upload_id, pending.status
        )
        return

    if pending.status == PendingUpload.Status.PENDING:
        # First attempt: CAS PENDING → UPLOADING so only one worker proceeds.
        updated = PendingUpload.objects.filter(
            id=upload_id, status=PendingUpload.Status.PENDING
        ).update(status=PendingUpload.Status.UPLOADING)
        if not updated:
            # Another worker claimed it between the get() and now.
            logger.info("upload_to_backend: could not claim %s, skipping", upload_id)
            return
    elif self.request.retries == 0:
        # UPLOADING but this is not a retry → another task owns this record.
        logger.info("upload_to_backend: %s already claimed by another worker, skipping", upload_id)
        return
    # Else: UPLOADING and self.request.retries > 0 → we own it from a previous attempt.

    temp_path = Path(pending.temp_file_path)

    if not temp_path.exists():
        logger.error(
            "upload_to_backend: temp file missing for %s: %s", upload_id, temp_path
        )
        pending.status = PendingUpload.Status.FAILED
        pending.error_message = f"Temp file not found: {temp_path}"
        pending.save(update_fields=["status", "error_message"])
        return

    try:
        user = User.objects.get(id=pending.user_id)
        backend = get_backend_for_connection(user=user, connection_name=pending.connection_name)
        with open(temp_path, "rb") as f:
            backend.write_stream(pending.path, f)
    except FileNotFoundError:
        logger.error(
            "upload_to_backend: temp file vanished mid-upload for %s", upload_id
        )
        pending.status = PendingUpload.Status.FAILED
        pending.error_message = "Temp file disappeared during upload"
        pending.save(update_fields=["status", "error_message"])
        return
    except Exception as exc:
        retries = self.request.retries
        logger.warning(
            "upload_to_backend: attempt %d failed for %s: %s", retries + 1, upload_id, exc
        )
        PendingUpload.objects.filter(id=upload_id).update(retry_count=retries + 1)
        if retries < self.max_retries:
            raise self.retry(exc=exc, countdown=4**retries)
        # Max retries reached — mark failed, keep temp file for inspection.
        pending.refresh_from_db()
        pending.status = PendingUpload.Status.FAILED
        pending.error_message = str(exc)
        pending.save(update_fields=["status", "error_message"])
        return

    # Success
    try:
        temp_path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not delete temp file: %s", temp_path)

    pending.status = PendingUpload.Status.DONE
    pending.completed_at = timezone.now()
    pending.save(update_fields=["status", "completed_at"])
    logger.info("upload_to_backend: completed %s (%s bytes)", upload_id, pending.expected_size)
