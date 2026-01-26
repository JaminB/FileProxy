from django.db import transaction

from .models import VaultItem, VaultItemKind
from .schemas import S3StaticCredentials


@transaction.atomic
def create_s3_credentials(*, user, name: str, creds: S3StaticCredentials) -> VaultItem:
    item = VaultItem(user=user, name=name, kind=VaultItemKind.AWS_S3)
    item.save(force_insert=True)  # ensures id exists for AAD binding
    item.set_payload(creds.to_payload())
    item.save()
    return item


def load_s3_credentials(*, item: VaultItem) -> S3StaticCredentials:
    if item.kind != VaultItemKind.AWS_S3:
        raise ValueError("VaultItem is not AWS S3 credentials")
    return S3StaticCredentials.from_payload(item.get_payload())