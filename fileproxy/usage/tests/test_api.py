from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from usage.models import UsageEvent

User = get_user_model()


def _make_event(scope, name, kind, operation, days_ago=0):
    """Create a UsageEvent, backdating occurred_at by days_ago days."""
    event = UsageEvent(
        scope=scope,
        connection_name=name,
        connection_kind=kind,
        operation=operation,
    )
    event.save()
    if days_ago:
        UsageEvent.objects.filter(pk=event.pk).update(
            occurred_at=timezone.now() - timedelta(days=days_ago)
        )
    return event


class UsageSummaryApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u1", password="pw")
        self.client.login(username="u1", password="pw")
        self.scope = f"user:{self.user.id}"

    def test_summary_returns_expected_structure(self):
        _make_event(self.scope, "my-vault", "s3", "read")
        _make_event(self.scope, "my-vault", "s3", "write")
        resp = self.client.get("/api/v1/usage/summary/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("days", resp.data)
        self.assertIn("total", resp.data)
        self.assertIn("ops", resp.data)
        self.assertNotIn("test", resp.data["ops"])

    def test_summary_default_days_is_30(self):
        resp = self.client.get("/api/v1/usage/summary/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["days"], 30)

    def test_summary_days_filter_excludes_old_events(self):
        _make_event(self.scope, "my-vault", "s3", "read")
        _make_event(self.scope, "my-vault", "s3", "read", days_ago=40)
        resp = self.client.get("/api/v1/usage/summary/?days=30")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["ops"]["read"], 1)

    def test_summary_vault_filter(self):
        _make_event(self.scope, "vault-a", "s3", "read")
        _make_event(self.scope, "vault-b", "s3", "write")
        resp = self.client.get("/api/v1/usage/summary/?connection=vault-a")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["ops"]["read"], 1)
        self.assertEqual(resp.data["ops"]["write"], 0)

    def test_summary_excludes_test_operations(self):
        _make_event(self.scope, "my-vault", "s3", "test")
        _make_event(self.scope, "my-vault", "s3", "read")
        resp = self.client.get("/api/v1/usage/summary/")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("test", resp.data["ops"])
        self.assertEqual(resp.data["total"], 1)

    def test_summary_requires_authentication(self):
        self.client.logout()
        resp = self.client.get("/api/v1/usage/summary/")
        self.assertIn(resp.status_code, [401, 403])


class UsageByConnectionApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u2", password="pw")
        self.client.login(username="u2", password="pw")
        self.scope = f"user:{self.user.id}"

    def test_by_connection_returns_list(self):
        _make_event(self.scope, "vault-a", "s3", "read")
        _make_event(self.scope, "vault-b", "s3", "write")
        resp = self.client.get("/api/v1/usage/by-connection/")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.data, list)
        self.assertEqual(len(resp.data), 2)

    def test_by_connection_item_structure(self):
        _make_event(self.scope, "vault-a", "s3", "read")
        resp = self.client.get("/api/v1/usage/by-connection/")
        self.assertEqual(resp.status_code, 200)
        item = resp.data[0]
        self.assertIn("name", item)
        self.assertIn("kind", item)
        self.assertIn("total", item)
        self.assertIn("read", item)
        self.assertIn("write", item)
        self.assertIn("enumerate", item)
        self.assertIn("delete", item)
        self.assertNotIn("test", item)

    def test_by_connection_days_filter(self):
        _make_event(self.scope, "vault-a", "s3", "read")
        _make_event(self.scope, "vault-a", "s3", "read", days_ago=40)
        resp = self.client.get("/api/v1/usage/by-connection/?days=30")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["read"], 1)

    def test_by_connection_sorted_by_total_descending(self):
        _make_event(self.scope, "vault-b", "s3", "read")
        _make_event(self.scope, "vault-a", "s3", "read")
        _make_event(self.scope, "vault-a", "s3", "write")
        resp = self.client.get("/api/v1/usage/by-connection/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data[0]["name"], "vault-a")
        self.assertEqual(resp.data[0]["total"], 2)

    def test_by_connection_excludes_test_operations(self):
        _make_event(self.scope, "vault-a", "s3", "test")
        _make_event(self.scope, "vault-a", "s3", "read")
        resp = self.client.get("/api/v1/usage/by-connection/")
        self.assertEqual(resp.status_code, 200)
        item = resp.data[0]
        self.assertNotIn("test", item)
        self.assertEqual(item["total"], 1)


class UsageTimelineApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u3", password="pw")
        self.client.login(username="u3", password="pw")
        self.scope = f"user:{self.user.id}"

    def test_timeline_requires_vault_param(self):
        resp = self.client.get("/api/v1/usage/timeline/")
        self.assertEqual(resp.status_code, 400)

    def test_timeline_returns_expected_structure(self):
        _make_event(self.scope, "my-vault", "s3", "read")
        resp = self.client.get("/api/v1/usage/timeline/?connection=my-vault")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("connection_name", resp.data)
        self.assertIn("days", resp.data)
        self.assertIn("dates", resp.data)
        self.assertIn("series", resp.data)

    def test_timeline_dates_length_matches_days(self):
        for days in [7, 30, 90]:
            resp = self.client.get(f"/api/v1/usage/timeline/?connection=my-vault&days={days}")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(len(resp.data["dates"]), days)

    def test_timeline_series_length_matches_dates(self):
        resp = self.client.get("/api/v1/usage/timeline/?connection=my-vault&days=7")
        self.assertEqual(resp.status_code, 200)
        date_count = len(resp.data["dates"])
        for op, counts in resp.data["series"].items():
            self.assertEqual(len(counts), date_count, f"series[{op!r}] length mismatch")

    def test_timeline_last_date_is_today(self):
        resp = self.client.get("/api/v1/usage/timeline/?connection=my-vault&days=7")
        self.assertEqual(resp.status_code, 200)
        today_str = str(timezone.now().date())
        self.assertEqual(resp.data["dates"][-1], today_str)

    def test_timeline_first_date_is_days_minus_1_ago(self):
        days = 7
        resp = self.client.get(f"/api/v1/usage/timeline/?connection=my-vault&days={days}")
        self.assertEqual(resp.status_code, 200)
        expected_start = str(timezone.now().date() - timedelta(days=days - 1))
        self.assertEqual(resp.data["dates"][0], expected_start)

    def test_timeline_event_counted_on_correct_date(self):
        _make_event(self.scope, "my-vault", "s3", "read", days_ago=2)
        resp = self.client.get("/api/v1/usage/timeline/?connection=my-vault&days=7")
        self.assertEqual(resp.status_code, 200)
        expected_date = str(timezone.now().date() - timedelta(days=2))
        idx = resp.data["dates"].index(expected_date)
        self.assertEqual(resp.data["series"]["read"][idx], 1)

    def test_timeline_old_events_excluded(self):
        _make_event(self.scope, "my-vault", "s3", "read", days_ago=40)
        resp = self.client.get("/api/v1/usage/timeline/?connection=my-vault&days=7")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(sum(resp.data["series"]["read"]), 0)

    def test_timeline_default_days_is_30(self):
        resp = self.client.get("/api/v1/usage/timeline/?connection=my-vault")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["days"], 30)
        self.assertEqual(len(resp.data["dates"]), 30)
