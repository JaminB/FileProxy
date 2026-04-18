from __future__ import annotations

import asyncio
import base64
import urllib.parse

from asgiref.sync import sync_to_async

from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from connections.models import Connection
from core.backends.base import (
    BackendConnectionError,
    BackendDeleteError,
    BackendEnumerateError,
    BackendReadError,
    BackendTestError,
    BackendWriteError,
)
from subscription.service import SubscriptionLimitExceeded, check_limit

from .. import write_cache
from ..serializers import (
    ConnectionMetaSerializer,
    EnumeratePageSerializer,
    EnumerateQuerySerializer,
    ReadFileQuerySerializer,
    WriteFileSerializer,
)
from ..services import (
    ConnectionNotFound,
    connections_for_user,
    get_backend_for_connection,
    user_scope,
)
from .parsers import OctetStreamParser, _ByteCountingStream


class FilesViewSet(viewsets.ViewSet):
    """
    Backend-agnostic file API.

    - GET    /api/v1/files/                              -> list connections for current user
    - POST   /api/v1/files/{connection_name}/health/     -> backend connectivity test
    - GET    /api/v1/files/{connection_name}/objects/    -> enumerate backend
    - GET    /api/v1/files/{connection_name}/path/       -> read file
    - POST   /api/v1/files/{connection_name}/path/       -> write file
    - DELETE /api/v1/files/{connection_name}/path/       -> delete file
    - GET    /api/v1/files/{connection_name}/path/stream/ -> streaming binary download
    """

    lookup_field = "connection_name"
    lookup_url_kwarg = "connection_name"
    lookup_value_regex = r"[^/]+"

    def _backend(self, request, connection_name: str):
        return get_backend_for_connection(user=request.user, connection_name=connection_name)

    def _record_event(
        self,
        request,
        connection_name: str,
        operation: str,
        object_path: str = "",
        ok: bool = True,
        bytes_transferred: int = 0,
    ) -> None:
        from usage.service import record_event

        scope = f"user:{request.user.id}"
        try:
            kind = Connection.objects.only("kind").get(scope=scope, name=connection_name).kind
        except Exception:  # noqa: BLE001
            kind = ""
        record_event(
            scope=scope,
            connection_name=connection_name,
            connection_kind=kind,
            operation=operation,
            object_path=object_path,
            ok=ok,
            bytes_transferred=bytes_transferred,
        )

    async def _async_tracked_stream(self, request, connection_name: str, chunks_iter, path: str):
        """Async generator that pulls chunks from a sync backend iterator.

        Each call to next() runs in the thread pool via asyncio.to_thread(), freeing
        the event loop to serve other requests between chunks.  This allows a single
        UvicornWorker process to handle many concurrent file transfers without blocking.
        """
        ok = False
        total_bytes = 0
        _done = object()
        try:
            while True:
                chunk = await asyncio.to_thread(next, chunks_iter, _done)
                if chunk is _done:
                    break
                if chunk:
                    total_bytes += len(chunk)
                yield chunk
            ok = True
        except GeneratorExit:
            ok = True  # Client disconnected; count bytes already sent
            raise
        finally:
            await sync_to_async(self._record_event)(
                request,
                connection_name,
                "read",
                object_path=path,
                ok=ok,
                bytes_transferred=total_bytes,
            )

    def _error(self, e: Exception) -> Response:
        if isinstance(e, ValidationError):
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(e, ConnectionNotFound):
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)

        if isinstance(e, SubscriptionLimitExceeded):
            return Response({"detail": str(e)}, status=status.HTTP_402_PAYMENT_REQUIRED)

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
        items = connections_for_user(request.user).only(
            "id", "name", "kind", "created_at", "updated_at", "rotated_at"
        )
        return Response(ConnectionMetaSerializer(items, many=True).data)

    @action(detail=True, methods=["post"], url_path="health")
    def health(self, request, connection_name: str = ""):
        try:
            backend = self._backend(request, connection_name)
            backend.test()
            return Response({"detail": "Connection OK."})
        except Exception as e:  # noqa: BLE001
            return self._error(e)

    @action(detail=True, methods=["get"], url_path="objects")
    def objects(self, request, connection_name: str = ""):
        ok = False
        try:
            check_limit(request.user, "enumerate")
            backend = self._backend(request, connection_name)
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
            self._record_event(request, connection_name, "enumerate", ok=ok)

    @action(
        detail=True,
        methods=["get", "post", "delete"],
        url_path="path",
        parser_classes=[JSONParser, MultiPartParser, OctetStreamParser],
    )
    def path(self, request, connection_name: str = ""):
        if request.method in ("GET", "HEAD"):
            return self._path_read(request, connection_name)
        elif request.method == "POST":
            return self._path_write(request, connection_name)
        elif request.method == "DELETE":
            return self._path_delete(request, connection_name)
        else:
            return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def _path_read(self, request, connection_name: str):
        """GET /api/v1/files/{connection_name}/path/?path=..."""
        path = ""
        try:
            check_limit(request.user, "read")
            backend = self._backend(request, connection_name)

            q = ReadFileQuerySerializer(data=request.query_params)
            q.is_valid(raise_exception=True)
            path = q.validated_data["path"]

            # read_stream() initiates the backend request and returns an iterator.
            # Connection-time errors (auth, not-found) are raised here so they can
            # be converted to proper HTTP error responses before headers are sent.
            chunks = backend.read_stream(path)

            async def _content():
                _done = object()
                async for chunk in self._async_tracked_stream(
                    request, connection_name, iter(chunks), path
                ):
                    if chunk:
                        await sync_to_async(check_limit)(
                            request.user, "read", bytes_count=len(chunk)
                        )
                    yield chunk

            return StreamingHttpResponse(_content(), content_type="application/octet-stream")
        except Exception as e:  # noqa: BLE001
            self._record_event(request, connection_name, "read", object_path=path, ok=False)
            return self._error(e)

    def _path_write(self, request, connection_name: str):
        """POST /api/v1/files/{connection_name}/path/"""
        ok = False
        path = ""
        bytes_written = 0
        threshold = settings.WRITE_CACHE_THRESHOLD_BYTES
        try:
            backend = self._backend(request, connection_name)
            content_type = request.content_type or ""

            if "multipart/form-data" in content_type:
                path = (request.data.get("path") or "").strip()
                file_obj = request.FILES.get("file")
                if not path:
                    raise ValidationError({"path": "This field is required."})
                if not file_obj:
                    raise ValidationError({"file": "This field is required."})
                bytes_written = file_obj.size or 0
                check_limit(request.user, "write", bytes_count=bytes_written)
                if bytes_written >= threshold:
                    write_cache.enqueue_upload(
                        user=request.user,
                        connection_name=connection_name,
                        path=path,
                        stream=file_obj,
                        size=bytes_written,
                    )
                    ok = True
                    return Response(
                        {"status": "pending", "path": path},
                        status=status.HTTP_202_ACCEPTED,
                    )
                backend.write_stream(path, file_obj)
                ok = True
                return Response({"detail": "OK", "path": path})

            elif "application/octet-stream" in content_type:
                path = (request.query_params.get("path") or "").strip()
                if not path:
                    raise ValidationError({"path": "This query parameter is required."})

                raw_content_length = request.META.get("CONTENT_LENGTH")
                if raw_content_length is None:
                    return Response({"detail": "Content-Length header is required."}, status=411)
                try:
                    content_length = int(raw_content_length)
                except (ValueError, TypeError):
                    content_length = 0

                check_limit(request.user, "write", bytes_count=content_length)

                if content_length >= threshold:
                    write_cache.enqueue_upload(
                        user=request.user,
                        connection_name=connection_name,
                        path=path,
                        stream=request.stream,
                        size=content_length,
                    )
                    bytes_written = content_length
                    ok = True
                    return Response(
                        {"status": "pending", "path": path},
                        status=status.HTTP_202_ACCEPTED,
                    )

                counting_stream = _ByteCountingStream(request.stream)
                backend.write_stream(path, counting_stream)
                bytes_written = counting_stream.bytes_read

                # Post-write check on actual bytes (catches inaccurate Content-Length)
                if bytes_written != content_length:
                    check_limit(request.user, "write", bytes_count=bytes_written)

                ok = True
                return Response({"detail": "OK", "path": path})

            else:  # application/json (default)
                s = WriteFileSerializer(data=request.data)
                s.is_valid(raise_exception=True)
                path = s.validated_data["path"]
                raw = base64.b64decode(s.validated_data["data_base64"])
                bytes_written = len(raw)
                check_limit(request.user, "write", bytes_count=bytes_written)
                if bytes_written >= threshold:
                    write_cache.enqueue_upload(
                        user=request.user,
                        connection_name=connection_name,
                        path=path,
                        data=raw,
                        size=bytes_written,
                    )
                    ok = True
                    return Response(
                        {"status": "pending", "path": path},
                        status=status.HTTP_202_ACCEPTED,
                    )
                backend.write(path, raw)
                ok = True
                return Response({"detail": "OK", "path": path})

        except Exception as e:  # noqa: BLE001
            return self._error(e)
        finally:
            self._record_event(
                request,
                connection_name,
                "write",
                object_path=path,
                ok=ok,
                bytes_transferred=bytes_written,
            )

    def _path_delete(self, request: Request, connection_name: str):
        """DELETE /api/v1/files/{connection_name}/path/?path=..."""
        ok = False
        path = ""
        try:
            check_limit(request.user, "delete")
            backend = self._backend(request, connection_name)

            q = ReadFileQuerySerializer(data=request.query_params)
            q.is_valid(raise_exception=True)
            path = q.validated_data["path"]

            backend.delete(path)
            ok = True
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:  # noqa: BLE001
            return self._error(e)
        finally:
            self._record_event(request, connection_name, "delete", object_path=path, ok=ok)

    @action(detail=True, methods=["get"], url_path="path/stream")
    def path_stream(self, request, connection_name: str = ""):
        """GET /api/v1/files/{connection_name}/path/stream/?path=... — binary streaming download."""
        path = ""
        try:
            check_limit(request.user, "read")
            backend = self._backend(request, connection_name)
            q = ReadFileQuerySerializer(data=request.query_params)
            q.is_valid(raise_exception=True)
            path = q.validated_data["path"]
            filename = path.rsplit("/", 1)[-1] or "download"
            ascii_filename = filename.encode("ascii", errors="replace").decode("ascii")
            encoded_filename = urllib.parse.quote(filename, safe="")

            chunks = backend.read_stream(path)

            async def _content():
                async for chunk in self._async_tracked_stream(
                    request, connection_name, iter(chunks), path
                ):
                    if chunk:
                        await sync_to_async(check_limit)(
                            request.user, "read", bytes_count=len(chunk)
                        )
                    yield chunk

            resp = StreamingHttpResponse(_content(), content_type="application/octet-stream")
            resp["Content-Disposition"] = (
                f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{encoded_filename}"
            )
            return resp
        except Exception as e:  # noqa: BLE001
            self._record_event(request, connection_name, "read", object_path=path, ok=False)
            return self._error(e)

    @action(detail=True, methods=["get"], url_path="pending")
    def pending_uploads(self, request: Request, connection_name: str = ""):
        """GET /api/v1/files/{connection_name}/pending/ — active pending uploads."""
        from ..models import PendingUpload

        if not Connection.objects.filter(
            scope=user_scope(request.user), name=connection_name
        ).exists():
            return self._error(ConnectionNotFound(f"Connection not found: {connection_name}"))

        qs = PendingUpload.objects.filter(
            user_id=request.user.id,
            connection_name=connection_name,
            status__in=[
                PendingUpload.Status.PENDING,
                PendingUpload.Status.UPLOADING,
                PendingUpload.Status.FAILED,
            ],
        ).order_by("created_at")
        data = [
            {
                "id": str(p.id),
                "path": p.path,
                "expected_size": p.expected_size,
                "status": p.status,
                "created_at": p.created_at.isoformat(),
            }
            for p in qs
        ]
        return Response(data)
