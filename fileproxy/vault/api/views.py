from __future__ import annotations

import secrets as secrets_mod

from django.conf import settings as django_settings
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.backends.base import BackendConnectionError
from core.backends.factory import backend_from_config

from ..models import VaultItem
from .serializers import (DropboxCreateSerializer, GDriveCreateSerializer,
                          S3CredentialsCreateSerializer, VaultItemListSerializer,
                          VaultItemRenameSerializer)


def _default_scope_from_request(request) -> str:
    user = getattr(request, "user", None)
    user_id = getattr(user, "id", None)
    if user_id is None:
        raise ValueError("Authenticated user is required.")
    return f"user:{user_id}"


class VaultItemViewSet(viewsets.ModelViewSet):
    """Vault item API (metadata only)."""

    def get_queryset(self):
        scope = _default_scope_from_request(self.request)
        return VaultItem.objects.filter(scope=scope).order_by("kind", "name")

    def get_serializer_class(self):
        return VaultItemListSerializer

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        serializer = VaultItemListSerializer(qs, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        """GET /api/v1/vault-items/{id}/ (metadata only)."""
        item = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])
        return Response(VaultItemListSerializer(item).data)

    def destroy(self, request, *args, **kwargs):
        item = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="s3")
    def create_s3(self, request):
        serializer = S3CredentialsCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(
            VaultItemListSerializer(item).data, status=status.HTTP_201_CREATED
        )

    @action(detail=False, methods=["post"], url_path="gdrive")
    def gdrive_create(self, request):
        client_id = django_settings.GOOGLE_CLIENT_ID
        client_secret = django_settings.GOOGLE_CLIENT_SECRET
        if not client_id or not client_secret:
            return Response(
                {"detail": "Google Drive is not configured on this server."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
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
            {"web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }},
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        flow.redirect_uri = request.build_absolute_uri("/vault/oauth/gdrive/callback/")
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            state=state,
        )
        return Response({"auth_url": auth_url})

    @action(detail=False, methods=["post"], url_path="dropbox")
    def dropbox_create(self, request):
        app_key = django_settings.DROPBOX_APP_KEY
        app_secret = django_settings.DROPBOX_APP_SECRET
        if not app_key or not app_secret:
            return Response(
                {"detail": "Dropbox is not configured on this server."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = DropboxCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        state = secrets_mod.token_urlsafe(32)
        redirect_uri = request.build_absolute_uri("/vault/oauth/dropbox/callback/")
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
            scope=["account_info.read", "files.content.read", "files.content.write",
                   "files.metadata.read", "files.metadata.write"],
        )
        auth_url = flow.start()
        request.session["dropbox_oauth_pending"]["csrf_token"] = csrf_session.get("csrf_token")
        return Response({"auth_url": auth_url})

    @action(detail=True, methods=["post"])
    def rotate(self, request, pk=None):
        item = get_object_or_404(self.get_queryset(), pk=pk)
        item.rotate()
        return Response(VaultItemListSerializer(item).data)

    @action(detail=True, methods=["post"])
    def rename(self, request, pk=None):
        item = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = VaultItemRenameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item.name = serializer.validated_data["name"]
        item.save(update_fields=["name", "updated_at"])
        return Response(VaultItemListSerializer(item).data)

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """POST /api/v1/vault-items/{id}/test/"""
        item = get_object_or_404(self.get_queryset(), pk=pk)

        backend = backend_from_config(item.to_backend_config())
        try:
            backend.test()
        except BackendConnectionError as e:
            return Response(
                {"detail": str(e), "ok": False}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response({"detail": "Connection OK.", "ok": True})
