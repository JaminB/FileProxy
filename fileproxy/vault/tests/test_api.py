from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

User = get_user_model()


class VaultApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u1", password="pw")
        self.client.login(username="u1", password="pw")

    def test_create_s3_and_list_does_not_return_secrets(self):
        resp = self.client.post(
            "/api/v1/vault-items/s3/",
            {
                "name": "prod",
                "access_key_id": "AKIA1234567890ABCDE",
                "secret_access_key": "supersecretsecretsecretsecretsecret",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertIn("id", resp.data)
        self.assertNotIn("access_key_id", resp.data)
        self.assertNotIn("secret_access_key", resp.data)

        resp2 = self.client.get("/api/v1/vault-items/")
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(len(resp2.data), 1)
        self.assertNotIn("access_key_id", resp2.data[0])
        self.assertNotIn("secret_access_key", resp2.data[0])