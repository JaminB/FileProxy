from __future__ import annotations

from typing import Any, Dict, Mapping, cast

from django.db import transaction

from .models import Connection, ConnectionKind
from .schemas import (AzureBlobCredentials, DropboxOAuth2Credentials,
                      GoogleDriveOAuth2Credentials, S3StaticCredentials)


@transaction.atomic
def create_s3_credentials(
    *,
    scope: str,
    name: str,
    settings_obj: Mapping[str, Any],
    secrets_obj: Mapping[str, Any],
) -> Connection:
    item = Connection(scope=scope, name=name, kind=ConnectionKind.AWS_S3)
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
) -> Connection:
    item = Connection(scope=scope, name=name, kind=ConnectionKind.GDRIVE_OAUTH2)
    item.save(force_insert=True)
    item.set_payload(settings_obj={}, secrets_obj=secrets_obj)
    item.save()
    return item


def load_s3_credentials(*, item: Connection) -> S3StaticCredentials:
    if item.kind != ConnectionKind.AWS_S3:
        raise ValueError("Connection is not AWS S3 credentials")

    payload = item.get_payload()
    secrets = payload.get("secrets", {})

    if not isinstance(secrets, Mapping):
        raise ValueError("Connection secrets payload is invalid")

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
) -> Connection:
    item = Connection(scope=scope, name=name, kind=ConnectionKind.DROPBOX_OAUTH2)
    item.save(force_insert=True)
    item.set_payload(settings_obj={}, secrets_obj=secrets_obj)
    item.save()
    return item


def load_dropbox_oauth2_credentials(*, item: Connection) -> DropboxOAuth2Credentials:
    if item.kind != ConnectionKind.DROPBOX_OAUTH2:
        raise ValueError("Connection is not Dropbox OAuth2 credentials")
    payload = item.get_payload()
    secrets = payload.get("secrets", {})
    if not isinstance(secrets, Mapping):
        raise ValueError("Connection secrets payload is invalid")
    return DropboxOAuth2Credentials.from_payload(cast(Dict[str, Any], secrets))


@transaction.atomic
def create_azure_blob_credentials(
    *,
    scope: str,
    name: str,
    settings_obj: Mapping[str, Any],
    secrets_obj: Mapping[str, Any],
) -> Connection:
    item = Connection(scope=scope, name=name, kind=ConnectionKind.AZURE_BLOB)
    item.save(force_insert=True)
    item.set_payload(settings_obj=settings_obj, secrets_obj=secrets_obj)
    item.save()
    return item


def load_azure_blob_credentials(*, item: Connection) -> AzureBlobCredentials:
    if item.kind != ConnectionKind.AZURE_BLOB:
        raise ValueError("Connection is not Azure Blob credentials")
    payload = item.get_payload()
    secrets = payload.get("secrets", {})
    if not isinstance(secrets, Mapping):
        raise ValueError("Connection secrets payload is invalid")
    return AzureBlobCredentials.from_payload(cast(Dict[str, Any], secrets))


def load_gdrive_oauth2_credentials(*, item: Connection) -> GoogleDriveOAuth2Credentials:
    if item.kind != ConnectionKind.GDRIVE_OAUTH2:
        raise ValueError("Connection is not Google Drive OAuth2 credentials")
    payload = item.get_payload()
    secrets = payload.get("secrets", {})
    if not isinstance(secrets, Mapping):
        raise ValueError("Connection secrets payload is invalid")
    return GoogleDriveOAuth2Credentials.from_payload(cast(Dict[str, Any], secrets))
