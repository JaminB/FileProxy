from __future__ import annotations

import base64

from django.http import StreamingHttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from .parsers import OctetStreamParser

from core.backends.base import (BackendConnectionError, BackendDeleteError,
                                BackendEnumerateError, BackendReadError,
                                BackendTestError, BackendWriteError)
from vault.models import VaultItem

from ..serializers import (BackendObjectSerializer, DeleteFileSerializer,
                           EnumeratePageSerializer, EnumerateQuerySerializer,
                           ReadFileQuerySerializer, VaultItemMetaSerializer,
                           WriteFileSerializer)
from ..services import (VaultItemNotFound, get_backend_for_user_vault_item,
                        vault_items_for_user)


class FilesViewSet(viewsets.ViewSet):
    """
    Backend-agnostic file API.

    - GET  /api/v1/files/                         -> list vault items for current user (metadata only)
    - POST /api/v1/files/{vault_item_name}/test/   -> backend connectivity test
    - GET  /api/v1/files/{vault_item_name}/objects -> enumerate backend
    - GET  /api/v1/files/{vault_item_name}/read    -> read object
    - POST /api/v1/files/{vault_item_name}/write   -> write object
    - POST /api/v1/files/{vault_item_name}/delete  -> delete object
    """

    lookup_field = "vault_item_name"
    lookup_url_kwarg = "vault_item_name"
    lookup_value_regex = r"[^/]+"

    def _backend(self, request, vault_item_name: str):
        return get_backend_for_user_vault_item(
            user=request.user, vault_item_name=vault_item_name
        )

    def _record_event(
        self,
        request,
        vault_item_name: str,
        operation: str,
        object_path: str = "",
        ok: bool = True,
    ) -> None:
        from usage.service import record_event

        scope = f"user:{request.user.id}"
        try:
            kind = VaultItem.objects.only("kind").get(
                scope=scope, name=vault_item_name
            ).kind
        except Exception:  # noqa: BLE001
            kind = ""
        record_event(
            scope=scope,
            vault_item_name=vault_item_name,
            vault_item_kind=kind,
            operation=operation,
            object_path=object_path,
            ok=ok,
        )

    def _error(self, e: Exception) -> Response:
        if isinstance(e, ValidationError):
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(e, VaultItemNotFound):
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)

        if isinstance(e, (BackendTestError, BackendConnectionError)):
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(
            e,
            (
                BackendEnumerateError,
                BackendReadError,
                BackendWriteError,
                BackendDeleteError,
            ),
        ):
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"detail": "Unexpected error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    def list(self, request):
        """GET /api/v1/files/"""
        items = vault_items_for_user(request.user).only(
            "id", "name", "kind", "created_at", "updated_at", "rotated_at"
        )
        return Response(VaultItemMetaSerializer(items, many=True).data)

    @action(detail=True, methods=["post"])
    def test(self, request, vault_item_name: str = ""):
        ok = False
        try:
            backend = self._backend(request, vault_item_name)
            backend.test()
            ok = True
            return Response({"detail": "Connection OK."})
        except Exception as e:  # noqa: BLE001
            return self._error(e)
        finally:
            self._record_event(request, vault_item_name, "test", ok=ok)

    @action(detail=True, methods=["get"], url_path="objects")
    def objects(self, request, vault_item_name: str = ""):
        ok = False
        try:
            backend = self._backend(request, vault_item_name)
            q = EnumerateQuerySerializer(data=request.query_params)
            q.is_valid(raise_exception=True)
            page = backend.enumerate_page(
                prefix=q.validated_data.get("prefix") or None,
                cursor=q.validated_data.get("cursor") or None,
                page_size=q.validated_data["page_size"],
            )
            ok = True
            return Response(EnumeratePageSerializer(page).data)
        except Exception as e:  # noqa: BLE001
            return self._error(e)
        finally:
            self._record_event(request, vault_item_name, "enumerate", ok=ok)

    @action(detail=True, methods=["get"], url_path="read")
    def read(self, request, vault_item_name: str = ""):
        ok = False
        path = ""
        try:
            backend = self._backend(request, vault_item_name)

            q = ReadFileQuerySerializer(data=request.query_params)
            q.is_valid(raise_exception=True)
            path = q.validated_data["path"]

            data = backend.read(path)
            ok = True
            return Response(
                {"path": path, "data_base64": base64.b64encode(data).decode("ascii")}
            )
        except Exception as e:  # noqa: BLE001
            return self._error(e)
        finally:
            self._record_event(request, vault_item_name, "read", object_path=path, ok=ok)

    @action(detail=True, methods=["post"], url_path="write",
            parser_classes=[JSONParser, MultiPartParser, OctetStreamParser])
    def write(self, request, vault_item_name: str = ""):
        ok = False
        path = ""
        try:
            backend = self._backend(request, vault_item_name)
            content_type = request.content_type or ""

            if "multipart/form-data" in content_type:
                path = (request.data.get("path") or "").strip()
                file_obj = request.FILES.get("file")
                if not path:
                    raise ValidationError({"path": "This field is required."})
                if not file_obj:
                    raise ValidationError({"file": "This field is required."})
                backend.write_stream(path, file_obj)
                ok = True
                return Response({"detail": "OK", "path": path})

            elif "application/octet-stream" in content_type:
                path = (request.query_params.get("path") or "").strip()
                if not path:
                    raise ValidationError({"path": "This query parameter is required."})
                raw = request.data  # bytes from OctetStreamParser

            else:  # application/json (default)
                s = WriteFileSerializer(data=request.data)
                s.is_valid(raise_exception=True)
                path = s.validated_data["path"]
                raw = base64.b64decode(s.validated_data["data_base64"])

            backend.write(path, raw)
            ok = True
            return Response({"detail": "OK", "path": path})
        except Exception as e:  # noqa: BLE001
            return self._error(e)
        finally:
            self._record_event(request, vault_item_name, "write", object_path=path, ok=ok)

    @action(detail=True, methods=["delete"], url_path="object")
    def delete_object(self, request: Request, vault_item_name: str = ""):
        """DELETE /api/v1/files/{vault_item_name}/object/?path=..."""
        ok = False
        path = ""
        try:
            backend = self._backend(request, vault_item_name)

            q = ReadFileQuerySerializer(data=request.query_params)
            q.is_valid(raise_exception=True)
            path = q.validated_data["path"]

            backend.delete(path)
            ok = True
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:  # noqa: BLE001
            return self._error(e)
        finally:
            self._record_event(request, vault_item_name, "delete", object_path=path, ok=ok)

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, vault_item_name: str = ""):
        """GET /api/v1/files/{vault_item_name}/download/?path=... — binary streaming download."""
        try:
            backend = self._backend(request, vault_item_name)
            q = ReadFileQuerySerializer(data=request.query_params)
            q.is_valid(raise_exception=True)
            path = q.validated_data["path"]
            filename = path.rsplit("/", 1)[-1] or "download"

            chunks = backend.read_stream(path)
            resp = StreamingHttpResponse(chunks, content_type="application/octet-stream")
            resp["Content-Disposition"] = f'attachment; filename="{filename}"'
            return resp
        except Exception as e:  # noqa: BLE001
            return self._error(e)
