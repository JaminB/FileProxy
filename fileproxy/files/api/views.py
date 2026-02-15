from __future__ import annotations

import base64

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.backends.base import (
    BackendConnectionError,
    BackendDeleteError,
    BackendEnumerateError,
    BackendReadError,
    BackendTestError,
    BackendWriteError,
)

from files.serializers import (
    BackendObjectSerializer,
    DeleteFileSerializer,
    EnumerateQuerySerializer,
    ReadFileQuerySerializer,
    WriteFileSerializer,
)
from files.services import VaultItemNotFound, get_backend_for_user_vault_item


class FilesViewSet(viewsets.ViewSet):
    """
    Backend-agnostic file API.

    URL is keyed by vault item *name* so end users never need to know backend types.
    """

    permission_classes = [IsAuthenticated]
    lookup_field = "vault_item_name"
    lookup_url_kwarg = "vault_item_name"

    def _backend(self, request, vault_item_name: str):
        return get_backend_for_user_vault_item(user=request.user, vault_item_name=vault_item_name)

    def _error(self, e: Exception) -> Response:
        if isinstance(e, VaultItemNotFound):
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)

        if isinstance(e, (BackendTestError, BackendConnectionError)):
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(e, (BackendEnumerateError, BackendReadError, BackendWriteError, BackendDeleteError)):
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Fallback
        return Response({"detail": "Unexpected error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=["post"])
    def test(self, request, vault_item_name: str = ""):
        """POST /api/v1/files/{vault_item_name}/test/"""
        try:
            backend = self._backend(request, vault_item_name)
            backend.test()
            return Response({"detail": "Connection OK."})
        except Exception as e:  # noqa: BLE001
            return self._error(e)

    @action(detail=True, methods=["get"], url_path="objects")
    def objects(self, request, vault_item_name: str = ""):
        """GET /api/v1/files/{vault_item_name}/objects/?prefix=..."""
        try:
            backend = self._backend(request, vault_item_name)

            q = EnumerateQuerySerializer(data=request.query_params)
            q.is_valid(raise_exception=True)
            prefix = q.validated_data.get("prefix") or None

            objs = list(backend.enumerate(prefix=prefix))
            return Response(BackendObjectSerializer(objs, many=True).data)
        except Exception as e:  # noqa: BLE001
            return self._error(e)

    @action(detail=True, methods=["get"], url_path="read")
    def read(self, request, vault_item_name: str = ""):
        """GET /api/v1/files/{vault_item_name}/read/?path=..."""
        try:
            backend = self._backend(request, vault_item_name)

            q = ReadFileQuerySerializer(data=request.query_params)
            q.is_valid(raise_exception=True)
            path = q.validated_data["path"]

            data = backend.read(path)
            return Response({"path": path, "data_base64": base64.b64encode(data).decode("ascii")})
        except Exception as e:  # noqa: BLE001
            return self._error(e)

    @action(detail=True, methods=["post"], url_path="write")
    def write(self, request, vault_item_name: str = ""):
        """POST /api/v1/files/{vault_item_name}/write/"""
        try:
            backend = self._backend(request, vault_item_name)

            s = WriteFileSerializer(data=request.data)
            s.is_valid(raise_exception=True)

            path = s.validated_data["path"]
            raw = base64.b64decode(s.validated_data["data_base64"])

            backend.write(path, raw)
            return Response({"detail": "OK", "path": path})
        except Exception as e:  # noqa: BLE001
            return self._error(e)

    @action(detail=True, methods=["post"], url_path="delete")
    def delete(self, request, vault_item_name: str = ""):
        """POST /api/v1/files/{vault_item_name}/delete/"""
        try:
            backend = self._backend(request, vault_item_name)

            s = DeleteFileSerializer(data=request.data)
            s.is_valid(raise_exception=True)

            path = s.validated_data["path"]
            backend.delete(path)
            return Response({"detail": "OK", "path": path})
        except Exception as e:  # noqa: BLE001
            return self._error(e)
