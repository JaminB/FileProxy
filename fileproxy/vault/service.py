from __future__ import annotations

from typing import Any, Dict, Mapping, cast

from django.db import transaction

from .models import VaultItem, VaultItemKind
from .schemas import DropboxOAuth2Credentials, GoogleDriveOAuth2Credentials, S3StaticCredentials


@transaction.atomic
def create_s3_credentials(
    *,
    scope: str,
    name: str,
    settings_obj: Mapping[str, Any],
    secrets_obj: Mapping[str, Any],
) -> VaultItem:
    item = VaultItem(scope=scope, name=name, kind=VaultItemKind.AWS_S3)
    item.save(force_insert=True)  # ensures id exists for AAD binding
    item.set_payload(settings_obj=settings_obj, secrets_obj=secrets_obj)
    item.save()
    return item


@transaction.atomic
def create_gdrive_oauth2_credentials(
    *,
    scope: str,
    name: str,
    secrets_obj: Mapping[str, Any],
) -> VaultItem:
    item = VaultItem(scope=scope, name=name, kind=VaultItemKind.GDRIVE_OAUTH2)
    item.save(force_insert=True)
    item.set_payload(settings_obj={}, secrets_obj=secrets_obj)
    item.save()
    return item


def load_s3_credentials(*, item: VaultItem) -> S3StaticCredentials:
    if item.kind != VaultItemKind.AWS_S3:
        raise ValueError("VaultItem is not AWS S3 credentials")

    payload = item.get_payload()
    secrets = payload.get("secrets", {})

    if not isinstance(secrets, Mapping):
        raise ValueError("VaultItem secrets payload is invalid")

    return S3StaticCredentials(
        access_key_id=cast(str, secrets.get("access_key_id")),
        secret_access_key=cast(str, secrets.get("secret_access_key")),
        session_token=cast(str | None, secrets.get("session_token")),
    )


@transaction.atomic
def create_dropbox_oauth2_credentials(
    *,
    scope: str,
    name: str,
    secrets_obj: Mapping[str, Any],
) -> VaultItem:
    item = VaultItem(scope=scope, name=name, kind=VaultItemKind.DROPBOX_OAUTH2)
    item.save(force_insert=True)
    item.set_payload(settings_obj={}, secrets_obj=secrets_obj)
    item.save()
    return item


def load_dropbox_oauth2_credentials(*, item: VaultItem) -> DropboxOAuth2Credentials:
    if item.kind != VaultItemKind.DROPBOX_OAUTH2:
        raise ValueError("VaultItem is not Dropbox OAuth2 credentials")
    payload = item.get_payload()
    secrets = payload.get("secrets", {})
    if not isinstance(secrets, Mapping):
        raise ValueError("VaultItem secrets payload is invalid")
    return DropboxOAuth2Credentials.from_payload(cast(Dict[str, Any], secrets))


def load_gdrive_oauth2_credentials(*, item: VaultItem) -> GoogleDriveOAuth2Credentials:
    if item.kind != VaultItemKind.GDRIVE_OAUTH2:
        raise ValueError("VaultItem is not Google Drive OAuth2 credentials")
    payload = item.get_payload()
    secrets = payload.get("secrets", {})
    if not isinstance(secrets, Mapping):
        raise ValueError("VaultItem secrets payload is invalid")
    return GoogleDriveOAuth2Credentials.from_payload(cast(Dict[str, Any], secrets))
