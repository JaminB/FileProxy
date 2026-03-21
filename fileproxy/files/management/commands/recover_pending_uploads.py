from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

from files.models import PendingUpload
from files.tasks import upload_to_backend

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Re-dispatch any pending or uploading PendingUpload records to Celery."

    def handle(self, *args, **options) -> None:
        stuck_qs = PendingUpload.objects.filter(
            status__in=(PendingUpload.Status.PENDING, PendingUpload.Status.UPLOADING)
        )
        # Reset any mid-flight records to PENDING so the task's CAS can reclaim them.
        stuck_qs.filter(status=PendingUpload.Status.UPLOADING).update(
            status=PendingUpload.Status.PENDING
        )
        records = list(stuck_qs)
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
