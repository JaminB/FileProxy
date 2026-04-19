from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from usage.models import UsageEvent
from usage.service import record_event


class RecordEventTests(TestCase):
    def test_happy_path_creates_usage_event(self):
        record_event(
            scope="user:42",
            connection_name="my-s3",
            connection_kind="aws_s3",
            operation="read",
            object_path="folder/file.txt",
            ok=True,
            bytes_transferred=1024,
        )

        self.assertEqual(UsageEvent.objects.count(), 1)
        event = UsageEvent.objects.get()
        self.assertEqual(event.scope, "user:42")
        self.assertEqual(event.connection_name, "my-s3")
        self.assertEqual(event.connection_kind, "aws_s3")
        self.assertEqual(event.operation, "read")
        self.assertEqual(event.object_path, "folder/file.txt")
        self.assertTrue(event.ok)
        self.assertEqual(event.bytes_transferred, 1024)

    def test_exception_is_swallowed(self):
        with patch("usage.models.UsageEvent.objects.create", side_effect=RuntimeError("db down")):
            # Must not raise
            record_event(
                scope="user:1",
                connection_name="conn",
                connection_kind="aws_s3",
                operation="write",
            )
        self.assertEqual(UsageEvent.objects.count(), 0)
