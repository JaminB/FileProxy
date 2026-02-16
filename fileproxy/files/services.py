from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import AbstractBaseUser

from vault.models import VaultItem
from core.backends.factory import backend_from_config
from core.backends.base import Backend


class FilesError(RuntimeError):
    pass


class VaultItemNotFound(FilesError):
    pass


def _user_scope(user: AbstractBaseUser) -> str:
    return f"user:{user.id}"


def get_backend_for_user_vault_item(*, user: AbstractBaseUser, vault_item_name: str) -> Backend:
    name = (vault_item_name or "").strip()
    if not name:
        raise VaultItemNotFound("Missing vault item name")

    try:
        item = VaultItem.objects.get(scope=_user_scope(user), name=name)
    except ObjectDoesNotExist as e:
        raise VaultItemNotFound(f"Vault item not found: {name}") from e

    return backend_from_config(item.to_backend_config())
