from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from ..models import VaultItem
from ..schemas import S3StaticCredentials
from ..service import create_s3_credentials, load_s3_credentials

User = get_user_model()


class VaultTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u1", password="pw")
        self.scope = f"user:{self.user.id}"

    def test_round_trip_encrypt_decrypt(self):
        creds = S3StaticCredentials(
            access_key_id="AKIA1234567890ABCDE",
            secret_access_key="supersecretsecretsecretsecretsecret",
            session_token=None,
        )

        settings_obj = {"user_id": self.user.id}
        secrets_obj = {
            "access_key_id": creds.access_key_id,
            "secret_access_key": creds.secret_access_key,
            "session_token": creds.session_token,
        }

        item = create_s3_credentials(
            scope=self.scope,
            name="prod",
            settings_obj=settings_obj,
            secrets_obj=secrets_obj,
        )

        loaded = load_s3_credentials(item=item)
        self.assertEqual(loaded.access_key_id, creds.access_key_id)
        self.assertEqual(loaded.secret_access_key, creds.secret_access_key)
        self.assertEqual(loaded.session_token, creds.session_token)

    def test_db_does_not_store_plaintext(self):
        creds = S3StaticCredentials(
            access_key_id="AKIAZZZZZZZZZZZZZZZZ",
            secret_access_key="plaintext-should-not-appear-anywhere",
            session_token=None,
        )

        item = create_s3_credentials(
            scope=self.scope,
            name="test",
            settings_obj={"user_id": self.user.id},
            secrets_obj={
                "access_key_id": creds.access_key_id,
                "secret_access_key": creds.secret_access_key,
                "session_token": creds.session_token,
            },
        )

        item_db = VaultItem.objects.get(id=item.id)
        combined = (
            f"{item_db.wrapped_dek}{item_db.payload_nonce}{item_db.payload_ciphertext}"
        )
        self.assertNotIn(creds.access_key_id, combined)
        self.assertNotIn(creds.secret_access_key, combined)

    def test_rotate_changes_ciphertext(self):
        creds = S3StaticCredentials(
            access_key_id="AKIAROTATE123456789",
            secret_access_key="rotate-me-please-rotate-me-please-rotate",
            session_token=None,
        )

        item = create_s3_credentials(
            scope=self.scope,
            name="rotate",
            settings_obj={"user_id": self.user.id},
            secrets_obj={
                "access_key_id": creds.access_key_id,
                "secret_access_key": creds.secret_access_key,
                "session_token": creds.session_token,
            },
        )

        before = (item.wrapped_dek, item.payload_nonce, item.payload_ciphertext)
        item.rotate()
        item.refresh_from_db()
        after = (item.wrapped_dek, item.payload_nonce, item.payload_ciphertext)

        self.assertNotEqual(before, after)

        loaded = load_s3_credentials(item=item)
        self.assertEqual(loaded.access_key_id, creds.access_key_id)
        self.assertEqual(loaded.secret_access_key, creds.secret_access_key)

    def test_aad_prevents_swapping_between_scopes(self):
        user2 = User.objects.create_user(username="u2", password="pw")
        scope2 = f"user:{user2.id}"

        creds1 = S3StaticCredentials(
            access_key_id="AKIAUSERONE123456789",
            secret_access_key="secret-one-secret-one-secret-one-secret",
            session_token=None,
        )
        creds2 = S3StaticCredentials(
            access_key_id="AKIAUSERTWO123456789",
            secret_access_key="secret-two-secret-two-secret-two-secret",
            session_token=None,
        )

        item1 = create_s3_credentials(
            scope=self.scope,
            name="one",
            settings_obj={"user_id": self.user.id},
            secrets_obj={
                "access_key_id": creds1.access_key_id,
                "secret_access_key": creds1.secret_access_key,
                "session_token": creds1.session_token,
            },
        )
        item2 = create_s3_credentials(
            scope=scope2,
            name="two",
            settings_obj={"user_id": user2.id},
            secrets_obj={
                "access_key_id": creds2.access_key_id,
                "secret_access_key": creds2.secret_access_key,
                "session_token": creds2.session_token,
            },
        )

        VaultItem.objects.filter(id=item1.id).update(
            wrapped_dek=item2.wrapped_dek,
            payload_nonce=item2.payload_nonce,
            payload_ciphertext=item2.payload_ciphertext,
        )
        item1.refresh_from_db()

        with self.assertRaises(Exception):
            _ = item1.get_payload()

    def test_aad_prevents_swapping_between_ids_in_same_scope(self):
        creds1 = S3StaticCredentials(
            access_key_id="AKIAIDONE1234567890",
            secret_access_key="secret-id-one-secret-id-one-secret-id",
            session_token=None,
        )
        creds2 = S3StaticCredentials(
            access_key_id="AKIAIDTWO1234567890",
            secret_access_key="secret-id-two-secret-id-two-secret-id",
            session_token=None,
        )

        item1 = create_s3_credentials(
            scope=self.scope,
            name="id-one",
            settings_obj={"user_id": self.user.id},
            secrets_obj={
                "access_key_id": creds1.access_key_id,
                "secret_access_key": creds1.secret_access_key,
                "session_token": creds1.session_token,
            },
        )
        item2 = create_s3_credentials(
            scope=self.scope,
            name="id-two",
            settings_obj={"user_id": self.user.id},
            secrets_obj={
                "access_key_id": creds2.access_key_id,
                "secret_access_key": creds2.secret_access_key,
                "session_token": creds2.session_token,
            },
        )

        VaultItem.objects.filter(id=item1.id).update(
            wrapped_dek=item2.wrapped_dek,
            payload_nonce=item2.payload_nonce,
            payload_ciphertext=item2.payload_ciphertext,
        )
        item1.refresh_from_db()

        with self.assertRaises(Exception):
            _ = item1.get_payload()
