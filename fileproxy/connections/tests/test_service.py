from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from ..service import (
    create_azure_blob_credentials,
    create_dropbox_oauth2_credentials,
    create_gdrive_oauth2_credentials,
    create_s3_credentials,
    load_azure_blob_credentials,
    load_dropbox_oauth2_credentials,
    load_gdrive_oauth2_credentials,
    load_s3_credentials,
)

User = get_user_model()


class CreateLoadGDriveTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="gdrive_user", password="pw")
        self.scope = f"user:{self.user.id}"

    def test_create_and_load_roundtrip(self):
        item = create_gdrive_oauth2_credentials(
            scope=self.scope,
            name="my-drive",
            secrets_obj={"refresh_token": "gdrive-rt-abc"},
        )
        creds = load_gdrive_oauth2_credentials(item=item)
        self.assertEqual(creds.refresh_token, "gdrive-rt-abc")

    def test_load_wrong_kind_raises(self):
        item = create_s3_credentials(
            scope=self.scope,
            name="s3-conn",
            settings_obj={"user_id": self.user.id},
            secrets_obj={"access_key_id": "AKIA", "secret_access_key": "secret", "session_token": None},
        )
        with self.assertRaises(ValueError):
            load_gdrive_oauth2_credentials(item=item)


class CreateLoadDropboxTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dropbox_user", password="pw")
        self.scope = f"user:{self.user.id}"

    def test_create_and_load_roundtrip(self):
        item = create_dropbox_oauth2_credentials(
            scope=self.scope,
            name="my-dropbox",
            secrets_obj={"refresh_token": "dropbox-rt-xyz"},
        )
        creds = load_dropbox_oauth2_credentials(item=item)
        self.assertEqual(creds.refresh_token, "dropbox-rt-xyz")

    def test_load_wrong_kind_raises(self):
        item = create_s3_credentials(
            scope=self.scope,
            name="s3-conn",
            settings_obj={"user_id": self.user.id},
            secrets_obj={"access_key_id": "AKIA", "secret_access_key": "secret", "session_token": None},
        )
        with self.assertRaises(ValueError):
            load_dropbox_oauth2_credentials(item=item)


class CreateLoadAzureBlobTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="azure_user", password="pw")
        self.scope = f"user:{self.user.id}"

    def test_create_and_load_roundtrip(self):
        item = create_azure_blob_credentials(
            scope=self.scope,
            name="my-azure",
            settings_obj={"account_name": "myaccount", "container_name": "mycontainer", "user_id": self.user.id},
            secrets_obj={"tenant_id": "t-123", "client_id": "c-456", "client_secret": "s-789"},
        )
        creds = load_azure_blob_credentials(item=item)
        self.assertEqual(creds.tenant_id, "t-123")
        self.assertEqual(creds.client_id, "c-456")
        self.assertEqual(creds.client_secret, "s-789")

    def test_load_wrong_kind_raises(self):
        item = create_s3_credentials(
            scope=self.scope,
            name="s3-conn",
            settings_obj={"user_id": self.user.id},
            secrets_obj={"access_key_id": "AKIA", "secret_access_key": "secret", "session_token": None},
        )
        with self.assertRaises(ValueError):
            load_azure_blob_credentials(item=item)


class CreateLoadS3ExtraTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="s3_extra_user", password="pw")
        self.scope = f"user:{self.user.id}"

    def test_load_wrong_kind_raises(self):
        item = create_gdrive_oauth2_credentials(
            scope=self.scope,
            name="gdrive-conn",
            secrets_obj={"refresh_token": "rt"},
        )
        with self.assertRaises(ValueError):
            load_s3_credentials(item=item)
