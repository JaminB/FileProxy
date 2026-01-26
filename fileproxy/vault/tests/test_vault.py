from django.contrib.auth import get_user_model
from django.test import TestCase

from ..models import VaultItem, VaultItemKind
from ..schemas import S3StaticCredentials
from ..service import create_s3_credentials, load_s3_credentials

User = get_user_model()


class VaultTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u1", password="pw")

    def test_round_trip_encrypt_decrypt(self):
        creds = S3StaticCredentials(
            access_key_id="AKIA1234567890ABCDE",
            secret_access_key="supersecretsecretsecretsecretsecret",
            session_token=None,
        )
        item = create_s3_credentials(user=self.user, name="prod", creds=creds)

        loaded = load_s3_credentials(item=item)
        self.assertEqual(loaded.access_key_id, creds.access_key_id)
        self.assertEqual(loaded.secret_access_key, creds.secret_access_key)
        self.assertEqual(loaded.session_token, creds.session_token)

    def test_db_does_not_store_plaintext(self):
        creds = S3StaticCredentials(
            access_key_id="AKIAZZZZZZZZZZZZZZZZ",
            secret_access_key="plaintext-should-not-appear-anywhere",
        )
        item = create_s3_credentials(user=self.user, name="test", creds=creds)

        # Pull raw fields and ensure they do not contain plaintext.
        item_db = VaultItem.objects.get(id=item.id)
        combined = f"{item_db.wrapped_dek}{item_db.payload_nonce}{item_db.payload_ciphertext}"
        self.assertNotIn(creds.access_key_id, combined)
        self.assertNotIn(creds.secret_access_key, combined)

    def test_rotate_changes_ciphertext(self):
        creds = S3StaticCredentials(
            access_key_id="AKIAROTATE123456789",
            secret_access_key="rotate-me-please-rotate-me-please-rotate",
        )
        item = create_s3_credentials(user=self.user, name="rotate", creds=creds)

        before = (item.wrapped_dek, item.payload_nonce, item.payload_ciphertext)
        item.rotate()
        item.refresh_from_db()
        after = (item.wrapped_dek, item.payload_nonce, item.payload_ciphertext)

        self.assertNotEqual(before, after)

        # Still decrypts correctly after rotation.
        loaded = load_s3_credentials(item=item)
        self.assertEqual(loaded.access_key_id, creds.access_key_id)
        self.assertEqual(loaded.secret_access_key, creds.secret_access_key)

    def test_aad_prevents_swapping_between_users(self):
        # Create a second user and vault item.
        user2 = User.objects.create_user(username="u2", password="pw")
        creds1 = S3StaticCredentials(
            access_key_id="AKIAUSERONE123456789",
            secret_access_key="secret-one-secret-one-secret-one-secret",
        )
        creds2 = S3StaticCredentials(
            access_key_id="AKIAUSERTWO123456789",
            secret_access_key="secret-two-secret-two-secret-two-secret",
        )
        item1 = create_s3_credentials(user=self.user, name="one", creds=creds1)
        item2 = create_s3_credentials(user=user2, name="two", creds=creds2)

        # Attempt ciphertext swap (simulate DB tampering): move payload fields of item2 into item1.
        VaultItem.objects.filter(id=item1.id).update(
            wrapped_dek=item2.wrapped_dek,
            payload_nonce=item2.payload_nonce,
            payload_ciphertext=item2.payload_ciphertext,
        )
        item1.refresh_from_db()

        # Decryption should fail because AAD is bound to (user_id, kind, id).
        with self.assertRaises(Exception):
            _ = item1.get_payload()