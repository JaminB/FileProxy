from __future__ import annotations

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import VaultItem, VaultItemKind
from .serializers import (
    S3CredentialsCreateSerializer,
    VaultItemListSerializer,
    VaultItemRenameSerializer,
)


class VaultItemViewSet(
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    VaultItem API

    - list: returns metadata only (no secrets)
    - create_s3: creates an aws_s3 vault item (input contains secrets, response does not)
    - rotate: re-encrypts payload with a new DEK
    - rename: updates display name only
    - destroy: deletes the vault item
    """

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return VaultItem.objects.filter(user=self.request.user).order_by("kind", "name")

    def get_serializer_class(self):
        # default for list
        return VaultItemListSerializer

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        serializer = VaultItemListSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="s3")
    def create_s3(self, request):
        """
        POST /api/v1/vault-items/s3

        Body:
          {
            "name": "prod-s3",
            "access_key_id": "...",
            "secret_access_key": "...",
            "session_token": "..." (optional)
          }

        Response: Vault item metadata only.
        """
        serializer = S3CredentialsCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        item = serializer.save()

        out = VaultItemListSerializer(item)
        return Response(out.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def rotate(self, request, pk=None):
        item = self.get_queryset().get(pk=pk)
        item.rotate()
        out = VaultItemListSerializer(item)
        return Response(out.data)

    @action(detail=True, methods=["post"])
    def rename(self, request, pk=None):
        item = self.get_queryset().get(pk=pk)
        serializer = VaultItemRenameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item.name = serializer.validated_data["name"]
        item.save(update_fields=["name", "updated_at"])
        out = VaultItemListSerializer(item)
        return Response(out.data)