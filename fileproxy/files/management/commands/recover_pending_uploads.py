from __future__ import annotations

from django.core.management.base import BaseCommand

from files.models import PendingUpload
from files.tasks import upload_to_backend


class Command(BaseCommand):
    help = "Re-dispatch any pending or uploading PendingUpload records to Celery."

    def handle(self, *args, **options) -> None:
        stuck = PendingUpload.objects.filter(
            status__in=[PendingUpload.Status.PENDING, PendingUpload.Status.UPLOADING]
        )
        count = stuck.count()
        if count == 0:
            self.stdout.write("No pending uploads to recover.")
            return

        # Reset uploading → pending so the task's CAS can claim them.
        stuck.filter(status=PendingUpload.Status.UPLOADING).update(
            status=PendingUpload.Status.PENDING
        )

        for record in stuck:
            upload_to_backend.delay(str(record.id))
            self.stdout.write(f"Re-dispatched {record.id} ({record.connection_name}/{record.path})")

        self.stdout.write(self.style.SUCCESS(f"Recovered {count} pending upload(s)."))
