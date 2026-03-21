from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

from files.models import PendingUpload
from files.tasks import upload_to_backend

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Re-dispatch PENDING PendingUpload records to Celery. "
        "UPLOADING records are left alone to avoid duplicate uploads in multi-instance deployments."
    )

    def handle(self, *args, **options) -> None:
        # Only re-dispatch PENDING records. UPLOADING records are left alone because
        # in a multi-instance deployment another worker may still be actively uploading;
        # resetting them to PENDING would cause duplicate uploads.
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
