from __future__ import annotations

import base64
import json
import os
import uuid
from typing import Any, Dict, Mapping, Tuple, cast

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.db import models
from django.utils import timezone

from core.backends.base import BackendConfig


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("utf-8")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s.encode("utf-8"))


def _aesgcm_encrypt(key: bytes, plaintext: bytes, aad: bytes) -> Tuple[bytes, bytes]:
    """Encrypt plaintext with AES-GCM.

    Args:
        key: AES-GCM key bytes.
        plaintext: Bytes to encrypt.
        aad: Additional authenticated data.

    Returns:
        Tuple of (nonce, ciphertext).
    """
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext, aad)
    return nonce, ct


def _aesgcm_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    """Decrypt AES-GCM ciphertext.

    Args:
        key: AES-GCM key bytes.
        nonce: Nonce used during encryption.
        ciphertext: Ciphertext (includes auth tag).
        aad: Additional authenticated data.

    Returns:
        Decrypted plaintext bytes.
    """
    return AESGCM(key).decrypt(nonce, ciphertext, aad)


class VaultItemKind(models.TextChoices):
    AWS_S3 = "aws_s3", "AWS S3 Credentials"
    GDRIVE_OAUTH2 = "gdrive_oauth2", "Google Drive (OAuth 2.0)"
    DROPBOX_OAUTH2 = "dropbox_oauth2", "Dropbox (OAuth 2.0)"


class VaultItem(models.Model):
    """Encrypted record scoped to a tenant identifier."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope = models.CharField(max_length=120)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=32, choices=VaultItemKind.choices)

    wrapped_dek = models.TextField()
    payload_nonce = models.CharField(max_length=32)
    payload_ciphertext = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    rotated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["scope", "kind"])]
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "name"], name="uniq_vaultitem_scope_name"
            ),
        ]

    def _payload_aad(self) -> bytes:
        """Return AAD used for payload encryption."""
        return f"vault:payload:{self.scope}:{self.kind}:{self.id}".encode("utf-8")

    def _dek_aad(self) -> bytes:
        """Return AAD used for DEK wrapping."""
        return f"vault:dek:{self.scope}:{self.kind}".encode("utf-8")

    @staticmethod
    def _wrap_dek(*, kek: bytes, dek: bytes, aad: bytes) -> str:
        """Wrap a DEK with the KEK."""
        nonce, ct = _aesgcm_encrypt(kek, dek, aad)
        return f"{_b64e(nonce)}.{_b64e(ct)}"

    @staticmethod
    def _unwrap_dek(*, kek: bytes, wrapped: str, aad: bytes) -> bytes:
        """Unwrap a DEK using the KEK."""
        nonce_b64, ct_b64 = wrapped.split(".", 1)
        return _aesgcm_decrypt(kek, _b64d(nonce_b64), _b64d(ct_b64), aad)

    def set_payload(
        self, *, settings_obj: Mapping[str, Any], secrets_obj: Mapping[str, Any]
    ) -> None:
        """Encrypt and store settings and secrets.

        Args:
            settings_obj: Non-secret configuration for the item.
            secrets_obj: Secret material for the item.
        """
        if self.id is None:
            super().save(force_insert=True)

        dek = os.urandom(32)
        self.wrapped_dek = self._wrap_dek(
            kek=settings.VAULT_MASTER_KEY,
            dek=dek,
            aad=self._dek_aad(),
        )

        payload = {
            "settings": dict(settings_obj),
            "secrets": dict(secrets_obj),
        }
        plaintext = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
        nonce, ct = _aesgcm_encrypt(dek, plaintext, self._payload_aad())
        self.payload_nonce = _b64e(nonce)
        self.payload_ciphertext = _b64e(ct)
        self.rotated_at = timezone.now()

    def get_payload(self) -> Dict[str, Any]:
        """Decrypt and return payload.

        Returns:
            Payload dict containing settings and secrets.
        """
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
        return cast(Dict[str, Any], json.loads(plaintext.decode("utf-8")))

    def to_backend_config(self) -> BackendConfig:
        """Build backend config from payload.

        Returns:
            BackendConfig derived from settings and secrets.
        """
        payload = self.get_payload()
        settings_obj = payload.get("settings", {})
        secrets_obj = payload.get("secrets", {})

        if not isinstance(settings_obj, Mapping):
            settings_obj = {}
        if not isinstance(secrets_obj, Mapping):
            secrets_obj = {}

        return BackendConfig(
            kind=self.kind,
            settings=cast(Mapping[str, Any], settings_obj),
            secrets=cast(Mapping[str, Any], secrets_obj),
        )

    def rotate(self) -> None:
        """Re-encrypt payload with a new DEK."""
        payload = self.get_payload()
        self.set_payload(
            settings_obj=cast(Mapping[str, Any], payload.get("settings", {})),
            secrets_obj=cast(Mapping[str, Any], payload.get("secrets", {})),
        )
        self.save(
            update_fields=[
                "wrapped_dek",
                "payload_nonce",
                "payload_ciphertext",
                "rotated_at",
                "updated_at",
            ]
        )
