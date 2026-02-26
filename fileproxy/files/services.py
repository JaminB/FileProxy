from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet

from connections.models import Connection
from core.backends.base import Backend
from core.backends.factory import backend_from_config


class FilesError(RuntimeError):
    pass


class ConnectionNotFound(FilesError):
    pass


def user_scope(user: AbstractBaseUser) -> str:
    return f"user:{user.id}"


def connections_for_user(user: AbstractBaseUser) -> QuerySet[Connection]:
    return Connection.objects.filter(scope=user_scope(user)).order_by("name")


def get_backend_for_connection(*, user: AbstractBaseUser, connection_name: str) -> Backend:
    name = (connection_name or "").strip()
    if not name:
        raise ConnectionNotFound("Missing connection name")

    try:
        item = Connection.objects.get(scope=user_scope(user), name=name)
    except ObjectDoesNotExist as e:
        raise ConnectionNotFound(f"Connection not found: {name}") from e

    return backend_from_config(item.to_backend_config())
