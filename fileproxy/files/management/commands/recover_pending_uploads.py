from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from files.models import PendingUpload
from files.tasks import upload_to_backend

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Re-dispatch PENDING PendingUpload records to Celery. "
        "UPLOADING records are left alone to avoid duplicate uploads in multi-instance deployments."
    )

    _stale_timeout = timedelta(minutes=10)

    def handle(self, *args, **options) -> None:
        # Reset UPLOADING records whose claimed_at is missing or older than the
        # stale timeout — these belong to workers that have died. Records with a
        # fresh claimed_at are left alone (another instance is actively uploading).
        stale_cutoff = timezone.now() - self._stale_timeout
        stale_qs = PendingUpload.objects.filter(
            status=PendingUpload.Status.UPLOADING
        ).filter(Q(claimed_at__isnull=True) | Q(claimed_at__lt=stale_cutoff))
        reset_count = stale_qs.update(status=PendingUpload.Status.PENDING)
        if reset_count:
            self.stdout.write(f"Reset {reset_count} stale UPLOADING record(s) to PENDING.")

        records = list(PendingUpload.objects.filter(status=PendingUpload.Status.PENDING))
        if not records:
            self.stdout.write("No pending uploads to recover.")
            return

        dispatched = 0
        for record in records:
            try:
                upload_to_backend.delay(str(record.id))
                self.stdout.write(
                    f"Re-dispatched {record.id} ({record.connection_name}/{record.path})"
                )
                dispatched += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not dispatch %s: %s", record.id, exc)
                self.stderr.write(f"Warning: could not dispatch {record.id}: {exc}")

        self.stdout.write(
            self.style.SUCCESS(f"Recovered {dispatched}/{len(records)} pending upload(s).")
        )
