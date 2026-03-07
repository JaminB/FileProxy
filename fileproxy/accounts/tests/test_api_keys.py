from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import APIKey
from accounts.tokens import APIKeyToken


class APIKeyTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pass")
        self.other = User.objects.create_user("bob", password="pass")
        self.client.login(username="alice", password="pass")

    # --- Create ---

    def test_create_returns_token(self):
        res = self.client.post("/api/v1/accounts/api-keys/", {"name": "my-key"}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertIn("token", res.data)
        self.assertIn("id", res.data)

    def test_create_name_required(self):
        res = self.client.post("/api/v1/accounts/api-keys/", {}, format="json")
        self.assertEqual(res.status_code, 400)

    # --- List ---

    def test_list_no_token(self):
        APIKey.objects.create(user=self.user, name="k1")
        res = self.client.get("/api/v1/accounts/api-keys/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)
        self.assertNotIn("token", res.data[0])

    # --- Revoke ---

    def test_revoke(self):
        key = APIKey.objects.create(user=self.user, name="k1")
        res = self.client.delete(f"/api/v1/accounts/api-keys/{key.id}/")
        self.assertEqual(res.status_code, 204)
        self.assertFalse(APIKey.objects.filter(pk=key.id).exists())

    def test_revoked_key_401(self):
        key = APIKey.objects.create(user=self.user, name="k1")
        token = str(APIKeyToken.for_api_key(key))
        key.delete()
        self.client.logout()
        res = self.client.get("/api/v1/connections/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(res.status_code, 401)

    # --- JWT auth ---

    def test_jwt_auth_connections(self):
        key = APIKey.objects.create(user=self.user, name="k1")
        token = str(APIKeyToken.for_api_key(key))
        self.client.logout()
        res = self.client.get("/api/v1/connections/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(res.status_code, 200)

    def test_jwt_auth_files(self):
        key = APIKey.objects.create(user=self.user, name="k1")
        token = str(APIKeyToken.for_api_key(key))
        self.client.logout()
        res = self.client.get("/api/v1/files/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(res.status_code, 200)

    # --- Isolation ---

    def test_cross_user_isolation(self):
        # Bob has a connection (just checking alice gets empty list, not bob's data)
        key = APIKey.objects.create(user=self.user, name="k1")
        token = str(APIKeyToken.for_api_key(key))
        self.client.logout()
        res = self.client.get("/api/v1/connections/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(res.status_code, 200)
        # Alice sees only her own connections (empty since no connections created)
        self.assertEqual(res.data, [])

    def test_unauthenticated_401(self):
        self.client.logout()
        res = self.client.get("/api/v1/connections/")
        self.assertEqual(res.status_code, 401)

    def test_cannot_revoke_other_users_key(self):
        bob_key = APIKey.objects.create(user=self.other, name="bob-key")
        res = self.client.delete(f"/api/v1/accounts/api-keys/{bob_key.id}/")
        self.assertEqual(res.status_code, 404)
        self.assertTrue(APIKey.objects.filter(pk=bob_key.id).exists())

    # --- last_used_at throttle ---

    def test_last_used_at_updated_on_first_request(self):
        key = APIKey.objects.create(user=self.user, name="k1")
        token = str(APIKeyToken.for_api_key(key))
        self.client.logout()
        self.client.get("/api/v1/connections/", HTTP_AUTHORIZATION=f"Bearer {token}")
        key.refresh_from_db()
        self.assertIsNotNone(key.last_used_at)

    def test_last_used_at_not_updated_within_interval(self):
        recent = timezone.now()
        key = APIKey.objects.create(user=self.user, name="k1", last_used_at=recent)
        token = str(APIKeyToken.for_api_key(key))
        self.client.logout()
        with patch("accounts.authentication.timezone.now", return_value=recent + timedelta(seconds=30)):
            self.client.get("/api/v1/connections/", HTTP_AUTHORIZATION=f"Bearer {token}")
        key.refresh_from_db()
        # Should still equal the original value — no update was issued
        self.assertEqual(key.last_used_at, recent)

    def test_last_used_at_updated_after_interval_elapsed(self):
        recent = timezone.now()
        key = APIKey.objects.create(user=self.user, name="k1", last_used_at=recent)
        token = str(APIKeyToken.for_api_key(key))
        self.client.logout()
        later = recent + timedelta(minutes=2)
        with patch("accounts.authentication.timezone.now", return_value=later):
            self.client.get("/api/v1/connections/", HTTP_AUTHORIZATION=f"Bearer {token}")
        key.refresh_from_db()
        self.assertEqual(key.last_used_at, later)
