from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from connections.models import Connection, ConnectionKind
from connections.service import create_gdrive_oauth2_credentials, load_s3_credentials

User = get_user_model()


class ConnectionApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u1", password="pw")
        self.client.login(username="u1", password="pw")
        self.scope = f"user:{self.user.id}"

        # Required by S3 backend config (settings.bucket)
        self.bucket = "fileproxy-test-bucket"

    def test_create_s3_and_list_does_not_return_secrets(self):
        resp = self.client.post(
            "/api/v1/connections/s3/",
            {
                "name": "prod",
                "bucket": self.bucket,
                "access_key_id": "AKIA1234567890ABCDE",
                "secret_access_key": "supersecretsecretsecretsecretsecret",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertIn("id", resp.data)
        self.assertNotIn("access_key_id", resp.data)
        self.assertNotIn("secret_access_key", resp.data)

        resp2 = self.client.get("/api/v1/connections/")
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(len(resp2.data), 1)
        self.assertNotIn("access_key_id", resp2.data[0])
        self.assertNotIn("secret_access_key", resp2.data[0])

    def test_created_item_is_scoped_and_secrets_roundtrip(self):
        resp = self.client.post(
            "/api/v1/connections/s3/",
            {
                "name": "prod",
                "bucket": self.bucket,
                "access_key_id": "AKIA1234567890ABCDE",
                "secret_access_key": "supersecretsecretsecretsecretsecret",
                "session_token": "",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        item_id = resp.data["id"]

        item = Connection.objects.get(id=item_id)
        self.assertEqual(item.scope, self.scope)
        self.assertEqual(item.kind, ConnectionKind.AWS_S3)

        creds = load_s3_credentials(item=item)
        self.assertEqual(creds.access_key_id, "AKIA1234567890ABCDE")
        self.assertEqual(creds.secret_access_key, "supersecretsecretsecretsecretsecret")
        self.assertIsNone(creds.session_token)


class RefreshActionTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u2", password="pw")
        self.client.login(username="u2", password="pw")
        self.scope = f"user:{self.user.id}"

    def _create_s3(self):
        resp = self.client.post(
            "/api/v1/connections/s3/",
            {
                "name": "s3conn",
                "bucket": "bucket",
                "access_key_id": "AKIA1234567890ABCDE",
                "secret_access_key": "supersecretsecretsecretsecretsecret",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        return resp.data["id"]

    def _create_gdrive(self):
        conn = create_gdrive_oauth2_credentials(
            scope=self.scope,
            name="gdrive-conn",
            secrets_obj={"refresh_token": "fake-refresh-token"},
        )
        return str(conn.id)

    @patch("connections.api.views.refresh_oauth2_connection")
    def test_refresh_oauth2_returns_202_and_enqueues_task(self, mock_task):
        conn_id = self._create_gdrive()
        resp = self.client.post(f"/api/v1/connections/{conn_id}/refresh/")
        self.assertEqual(resp.status_code, 202)
        mock_task.delay.assert_called_once_with(conn_id)

    @patch("connections.api.views.refresh_oauth2_connection")
    def test_refresh_non_oauth2_returns_400(self, mock_task):
        conn_id = self._create_s3()
        resp = self.client.post(f"/api/v1/connections/{conn_id}/refresh/")
        self.assertEqual(resp.status_code, 400)
        mock_task.delay.assert_not_called()

    @patch("connections.api.views.refresh_oauth2_connection")
    def test_refresh_another_users_connection_returns_404(self, mock_task):
        conn_id = self._create_gdrive()
        # Create a second user and log in as them
        User.objects.create_user(username="u3", password="pw")
        self.client.login(username="u3", password="pw")
        resp = self.client.post(f"/api/v1/connections/{conn_id}/refresh/")
        self.assertEqual(resp.status_code, 404)
        mock_task.delay.assert_not_called()
