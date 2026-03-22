from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from files.models import PendingUpload

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = (
    PendingUpload.Status.DONE,
    PendingUpload.Status.FAILED,
    PendingUpload.Status.CANCELLED,
)


class Command(BaseCommand):
    help = (
        "Delete terminal PendingUpload records (DONE/CANCELLED/FAILED) and their temp files "
        "once they are older than --days days. Also removes orphaned temp files in "
        "WRITE_CACHE_DIR that are no longer referenced by any DB record."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--days",
            type=int,
            default=settings.WRITE_CACHE_CLEANUP_DAYS,
            help=(
                "Delete records older than this many days "
                f"(default: {settings.WRITE_CACHE_CLEANUP_DAYS})."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be deleted without actually deleting anything.",
        )

    def handle(self, *args, **options) -> None:
        days: int = options["days"]
        dry_run: bool = options["dry_run"]
        cutoff = timezone.now() - timedelta(days=days)

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — nothing will be deleted."))

        # --- 1. Delete terminal DB records (and their temp files) ---
        old_records = PendingUpload.objects.filter(
            status__in=_TERMINAL_STATUSES,
            created_at__lt=cutoff,
        )

        deleted_records = 0
        deleted_files = 0
        kept_files = 0

        for record in old_records.iterator():
            temp_path = Path(record.temp_file_path)
            if temp_path.exists():
                if record.status == PendingUpload.Status.FAILED:
                    logger.info(
                        "cleanup_pending_uploads: removing FAILED temp file %s (record %s)",
                        temp_path,
                        record.id,
                    )
                if not dry_run:
                    try:
                        temp_path.unlink(missing_ok=True)
                        deleted_files += 1
                    except OSError:
                        logger.warning("Could not delete temp file: %s", temp_path)
                        kept_files += 1
                else:
                    self.stdout.write(f"  Would delete temp file: {temp_path}")
                    deleted_files += 1
            if not dry_run:
                record.delete()
            deleted_records += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted_records} record(s) older than {days} day(s) "
                f"({deleted_files} temp file(s) removed, {kept_files} could not be removed)."
            )
        )

        # --- 2. Remove orphaned temp files (in WRITE_CACHE_DIR but not in DB) ---
        cache_dir = Path(settings.WRITE_CACHE_DIR)
        if not cache_dir.exists():
            return

        known_paths = set(PendingUpload.objects.values_list("temp_file_path", flat=True))

        orphaned = 0
        for f in cache_dir.iterdir():
            if not f.is_file():
                continue
            if str(f) not in known_paths:
                logger.info("cleanup_pending_uploads: removing orphaned temp file %s", f)
                if not dry_run:
                    try:
                        f.unlink()
                        orphaned += 1
                    except OSError:
                        logger.warning("Could not delete orphaned temp file: %s", f)
                else:
                    self.stdout.write(f"  Would delete orphaned temp file: {f}")
                    orphaned += 1

        if orphaned:
            self.stdout.write(self.style.SUCCESS(f"Removed {orphaned} orphaned temp file(s)."))
