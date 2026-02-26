from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from connections.models import Connection, ConnectionKind
from connections.service import load_s3_credentials

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
