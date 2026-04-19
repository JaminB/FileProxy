from __future__ import annotations

from django.test import SimpleTestCase

from ..schemas import (
    AzureBlobCredentials,
    DropboxOAuth2Credentials,
    GoogleDriveOAuth2Credentials,
    S3StaticCredentials,
)


class S3StaticCredentialsSchemaTests(SimpleTestCase):
    def test_roundtrip(self):
        creds = S3StaticCredentials(
            access_key_id="AKIAEXAMPLE",
            secret_access_key="supersecret",
            session_token=None,
        )
        loaded = S3StaticCredentials.from_payload(creds.to_payload())
        self.assertEqual(loaded.access_key_id, creds.access_key_id)
        self.assertEqual(loaded.secret_access_key, creds.secret_access_key)
        self.assertIsNone(loaded.session_token)

    def test_roundtrip_with_session_token(self):
        creds = S3StaticCredentials(
            access_key_id="AKIAEXAMPLE",
            secret_access_key="supersecret",
            session_token="mytoken",
        )
        loaded = S3StaticCredentials.from_payload(creds.to_payload())
        self.assertEqual(loaded.session_token, "mytoken")

    def test_session_token_defaults_to_none_when_missing(self):
        payload = {"access_key_id": "AKIA", "secret_access_key": "secret"}
        loaded = S3StaticCredentials.from_payload(payload)
        self.assertIsNone(loaded.session_token)


class GoogleDriveSchemaTests(SimpleTestCase):
    def test_roundtrip(self):
        creds = GoogleDriveOAuth2Credentials(refresh_token="gdrive-refresh-token")
        loaded = GoogleDriveOAuth2Credentials.from_payload(creds.to_payload())
        self.assertEqual(loaded.refresh_token, "gdrive-refresh-token")


class AzureBlobSchemaTests(SimpleTestCase):
    def test_roundtrip(self):
        creds = AzureBlobCredentials(
            tenant_id="tenant-123",
            client_id="client-456",
            client_secret="secret-789",
        )
        loaded = AzureBlobCredentials.from_payload(creds.to_payload())
        self.assertEqual(loaded.tenant_id, "tenant-123")
        self.assertEqual(loaded.client_id, "client-456")
        self.assertEqual(loaded.client_secret, "secret-789")


class DropboxSchemaTests(SimpleTestCase):
    def test_roundtrip(self):
        creds = DropboxOAuth2Credentials(refresh_token="dropbox-refresh-token")
        loaded = DropboxOAuth2Credentials.from_payload(creds.to_payload())
        self.assertEqual(loaded.refresh_token, "dropbox-refresh-token")
