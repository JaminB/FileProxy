from __future__ import annotations

from uuid import uuid4

from django.db import models


class PendingUpload(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        UPLOADING = "uploading"
        DONE = "done"
        FAILED = "failed"
        CANCELLED = "cancelled"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user_id = models.IntegerField(db_index=True)
    connection_name = models.CharField(max_length=255)
    path = models.CharField(max_length=4096)
    temp_file_path = models.CharField(max_length=4096)
    expected_size = models.BigIntegerField()
    celery_task_id = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["user_id", "connection_name", "path", "status"]),
        ]

    def __str__(self) -> str:
        return f"PendingUpload({self.id}, {self.connection_name}/{self.path}, {self.status})"
