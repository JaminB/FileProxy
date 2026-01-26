from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("utf-8")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s.encode("utf-8"))


def _aesgcm_encrypt(key: bytes, plaintext: bytes, aad: bytes) -> Tuple[bytes, bytes]:
    """
    Returns (nonce, ciphertext). AESGCM ciphertext includes the auth tag.
    """
    nonce = os.urandom(12)  # AES-GCM standard nonce size
    ct = AESGCM(key).encrypt(nonce, plaintext, aad)
    return nonce, ct


def _aesgcm_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    return AESGCM(key).decrypt(nonce, ciphertext, aad)


class VaultItemKind(models.TextChoices):
    AWS_S3 = "aws_s3", "AWS S3 Credentials"
    # Future:
    # GDRIVE = "gdrive_oauth", "Google Drive OAuth"
    # DROPBOX = "dropbox_oauth", "Dropbox OAuth"


class VaultItem(models.Model):
    """
    A single encrypted record owned by a user.

    - Payload is encrypted JSON stored as ciphertext.
    - Each record has its own DEK (data encryption key).
    - The DEK is wrapped using settings.VAULT_MASTER_KEY (KEK).
    - AAD binds ciphertext to (user_id, kind, id) to prevent swapping attacks.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="vault_items")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=32, choices=VaultItemKind.choices)

    # Wrapped DEK: "b64(nonce).b64(ciphertext)"
    wrapped_dek = models.TextField()

    # Payload ciphertext
    payload_nonce = models.CharField(max_length=32)  # b64
    payload_ciphertext = models.TextField()          # b64

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    rotated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "kind"])]
        constraints = [
            models.UniqueConstraint(fields=["user", "name"], name="uniq_vaultitem_user_name"),
        ]

    def _payload_aad(self) -> bytes:
        # Requires id. If id is None, caller should save() first.
        return f"vault:payload:{self.user_id}:{self.kind}:{self.id}".encode("utf-8")

    def _dek_aad(self) -> bytes:
        # Stable even before id exists.
        return f"vault:dek:{self.user_id}:{self.kind}".encode("utf-8")

    @staticmethod
    def _wrap_dek(*, kek: bytes, dek: bytes, aad: bytes) -> str:
        nonce, ct = _aesgcm_encrypt(kek, dek, aad)
        return f"{_b64e(nonce)}.{_b64e(ct)}"

    @staticmethod
    def _unwrap_dek(*, kek: bytes, wrapped: str, aad: bytes) -> bytes:
        nonce_b64, ct_b64 = wrapped.split(".", 1)
        return _aesgcm_decrypt(kek, _b64d(nonce_b64), _b64d(ct_b64), aad)

    def set_payload(self, payload: Dict[str, Any]) -> None:
        """
        Encrypt and store payload. Caller should call save() after.
        """
        if self.id is None:
            # We need an id for payload AAD binding to prevent row swapping.
            super().save(force_insert=True)

        dek = os.urandom(32)
        self.wrapped_dek = self._wrap_dek(
            kek=settings.VAULT_MASTER_KEY,
            dek=dek,
            aad=self._dek_aad(),
        )

        plaintext = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        nonce, ct = _aesgcm_encrypt(dek, plaintext, self._payload_aad())
        self.payload_nonce = _b64e(nonce)
        self.payload_ciphertext = _b64e(ct)
        self.rotated_at = timezone.now()

    def get_payload(self) -> Dict[str, Any]:
        dek = self._unwrap_dek(
            kek=settings.VAULT_MASTER_KEY,
            wrapped=self.wrapped_dek,
            aad=self._dek_aad(),
        )
        plaintext = _aesgcm_decrypt(
            dek,
            _b64d(self.payload_nonce),
            _b64d(self.payload_ciphertext),
            self._payload_aad(),
        )
        return json.loads(plaintext.decode("utf-8"))

    def rotate(self) -> None:
        """
        Re-encrypt payload with a new DEK.
        """
        payload = self.get_payload()
        self.set_payload(payload)
        self.save(update_fields=[
            "wrapped_dek",
            "payload_nonce",
            "payload_ciphertext",
            "rotated_at",
            "updated_at",
        ])