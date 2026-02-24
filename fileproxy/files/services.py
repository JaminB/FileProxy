from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet

from core.backends.base import Backend
from core.backends.factory import backend_from_config
from vault.models import VaultItem


class FilesError(RuntimeError):
    pass


class VaultItemNotFound(FilesError):
    pass


def user_scope(user: AbstractBaseUser) -> str:
    return f"user:{user.id}"


def vault_items_for_user(user: AbstractBaseUser) -> QuerySet[VaultItem]:
    return VaultItem.objects.filter(scope=user_scope(user)).order_by("name")


def get_backend_for_user_vault_item(*, user: AbstractBaseUser, vault_item_name: str) -> Backend:
    name = (vault_item_name or "").strip()
    if not name:
        raise VaultItemNotFound("Missing vault item name")

    try:
        item = VaultItem.objects.get(scope=user_scope(user), name=name)
    except ObjectDoesNotExist as e:
        raise VaultItemNotFound(f"Vault item not found: {name}") from e

    return backend_from_config(item.to_backend_config())
