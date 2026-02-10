from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.backends.factory import backend_from_config
from core.backends.base import BackendConnectionError

from ..models import VaultItem
from .serializers import (
    S3CredentialsCreateSerializer,
    VaultItemListSerializer,
    VaultItemRenameSerializer,
)


def _default_scope_from_request(request) -> str:
    user = getattr(request, "user", None)
    user_id = getattr(user, "id", None)
    if user_id is None:
        raise ValueError("Authenticated user is required.")
    return f"user:{user_id}"


class VaultItemViewSet(viewsets.ModelViewSet):
    """Vault item API (metadata only)."""

    permission_classes = [IsAuthenticated]

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
        item = self.get_queryset().get(pk=kwargs["pk"])
        return Response(VaultItemListSerializer(item).data)

    def destroy(self, request, *args, **kwargs):
        item = self.get_queryset().get(pk=kwargs["pk"])
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="s3")
    def create_s3(self, request):
        serializer = S3CredentialsCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(VaultItemListSerializer(item).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def rotate(self, request, pk=None):
        item = self.get_queryset().get(pk=pk)
        item.rotate()
        return Response(VaultItemListSerializer(item).data)

    @action(detail=True, methods=["post"])
    def rename(self, request, pk=None):
        item = self.get_queryset().get(pk=pk)
        serializer = VaultItemRenameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item.name = serializer.validated_data["name"]
        item.save(update_fields=["name", "updated_at"])
        return Response(VaultItemListSerializer(item).data)



    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """POST /api/v1/vault-items/{id}/test/"""
        item = self.get_queryset().get(pk=pk)

        backend = backend_from_config(item.to_backend_config())
        try:
            backend.test()
        except BackendConnectionError as e:
            return Response({"detail": str(e), "ok": False}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "Connection OK.", "ok": True})
