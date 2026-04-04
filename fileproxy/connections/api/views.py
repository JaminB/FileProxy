from __future__ import annotations

import secrets as secrets_mod

from django.conf import settings as django_settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.backends.base import BackendConnectionError
from core.backends.factory import backend_from_config

from ..models import Connection, ConnectionKind
from ..tasks import refresh_oauth2_connection
from .serializers import (
    AzureBlobCreateSerializer,
    ConnectionListSerializer,
    ConnectionRenameSerializer,
    DropboxCreateSerializer,
    GDriveCreateSerializer,
    S3CredentialsCreateSerializer,
)


def _get_or_404(queryset, **kwargs):
    """Like get_object_or_404, but also catches ValidationError for invalid PK types."""
    try:
        return get_object_or_404(queryset, **kwargs)
    except (DjangoValidationError, ValueError, TypeError):
        raise Http404


def _default_scope_from_request(request) -> str:
    user = getattr(request, "user", None)
    user_id = getattr(user, "id", None)
    if user_id is None:
        raise ValueError("Authenticated user is required.")
    return f"user:{user_id}"


class ConnectionViewSet(viewsets.ModelViewSet):
    """Connection API (metadata only)."""

    def get_queryset(self):
        scope = _default_scope_from_request(self.request)
        return Connection.objects.filter(scope=scope).order_by("kind", "name")

    def get_serializer_class(self):
        return ConnectionListSerializer

    def create(self, request, *args, **kwargs):
        """Direct POST to the list endpoint is not supported; use /s3/, /gdrive/, etc."""
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        serializer = ConnectionListSerializer(qs, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        """GET /api/v1/connections/{id}/ (metadata only)."""
        item = _get_or_404(self.get_queryset(), pk=kwargs["pk"])
        return Response(ConnectionListSerializer(item).data)

    def destroy(self, request, *args, **kwargs):
        item = _get_or_404(self.get_queryset(), pk=kwargs["pk"])
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="s3")
    def create_s3(self, request):
        serializer = S3CredentialsCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(ConnectionListSerializer(item).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses={
            200: inline_serializer("OAuthInitiate", fields={"auth_url": drf_serializers.URLField()})
        }
    )
    @action(detail=False, methods=["post"], url_path="gdrive")
    def gdrive_create(self, request):
        client_id = django_settings.GOOGLE_CLIENT_ID
        client_secret = django_settings.GOOGLE_CLIENT_SECRET
        if not client_id or not client_secret:
            return Response(
                {"detail": "Google Drive is not configured on this server."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = GDriveCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        state = secrets_mod.token_urlsafe(32)
        request.session["gdrive_oauth_pending"] = {
            "name": serializer.validated_data["name"],
            "state": state,
            "scope": _default_scope_from_request(request),
        }

        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        flow.redirect_uri = request.build_absolute_uri("/connections/oauth/gdrive/callback/")
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            state=state,
        )
        return Response({"auth_url": auth_url})

    @extend_schema(
        responses={
            200: inline_serializer(
                "OAuthInitiateDropbox", fields={"auth_url": drf_serializers.URLField()}
            )
        }
    )
    @action(detail=False, methods=["post"], url_path="dropbox")
    def dropbox_create(self, request):
        app_key = django_settings.DROPBOX_APP_KEY
        app_secret = django_settings.DROPBOX_APP_SECRET
        if not app_key or not app_secret:
            return Response(
                {"detail": "Dropbox is not configured on this server."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = DropboxCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        state = secrets_mod.token_urlsafe(32)
        redirect_uri = request.build_absolute_uri("/connections/oauth/dropbox/callback/")
        request.session["dropbox_oauth_pending"] = {
            "name": serializer.validated_data["name"],
            "state": state,
            "scope": _default_scope_from_request(request),
            "redirect_uri": redirect_uri,
        }

        import dropbox as dbx_sdk

        csrf_session = {}
        flow = dbx_sdk.DropboxOAuth2Flow(
            consumer_key=app_key,
            redirect_uri=redirect_uri,
            session=csrf_session,
            csrf_token_session_key="csrf_token",
            consumer_secret=app_secret,
            token_access_type="offline",
            scope=[
                "account_info.read",
                "files.content.read",
                "files.content.write",
                "files.metadata.read",
                "files.metadata.write",
            ],
        )
        auth_url = flow.start()
        request.session["dropbox_oauth_pending"]["csrf_token"] = csrf_session.get("csrf_token")
        return Response({"auth_url": auth_url})

    @action(detail=False, methods=["post"], url_path="azure")
    def create_azure(self, request):
        serializer = AzureBlobCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(ConnectionListSerializer(item).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def rotate(self, request, pk=None):
        item = _get_or_404(self.get_queryset(), pk=pk)
        item.rotate()
        return Response(ConnectionListSerializer(item).data)

    @action(detail=True, methods=["post"])
    def rename(self, request, pk=None):
        item = _get_or_404(self.get_queryset(), pk=pk)
        serializer = ConnectionRenameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item.name = serializer.validated_data["name"]
        item.save(update_fields=["name", "updated_at"])
        return Response(ConnectionListSerializer(item).data)

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """POST /api/v1/connections/{id}/test/"""
        item = _get_or_404(self.get_queryset(), pk=pk)

        backend = backend_from_config(item.to_backend_config())
        try:
            backend.test()
        except BackendConnectionError as e:
            return Response({"detail": str(e), "ok": False}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "Connection OK.", "ok": True})

    _OAUTH2_KINDS = {ConnectionKind.GDRIVE_OAUTH2, ConnectionKind.DROPBOX_OAUTH2}

    @action(detail=True, methods=["post"])
    def refresh(self, request, pk=None):
        """POST /api/v1/connections/{id}/refresh/ — enqueue an immediate credential refresh."""
        item = _get_or_404(self.get_queryset(), pk=pk)
        if item.kind not in self._OAUTH2_KINDS:
            return Response(
                {"detail": "Credential refresh is only available for OAuth2 connections."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        refresh_oauth2_connection.delay(str(item.id))
        return Response({"detail": "Credential refresh enqueued."}, status=status.HTTP_202_ACCEPTED)
