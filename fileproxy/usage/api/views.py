from __future__ import annotations

from datetime import timedelta

from django.db.models import Count
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from vault.models import VaultItem

from ..models import OperationKind, UsageEvent
from .serializers import ByVaultItemSerializer, SummarySerializer, VaultMetricsSerializer


def _user_scope(request) -> str:
    return f"user:{request.user.id}"


class UsageViewSet(ViewSet):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "days",
                int,
                OpenApiParameter.QUERY,
                description="Number of days to look back (default: 30)",
                required=False,
            )
        ],
        responses=SummarySerializer,
    )
    def summary(self, request):
        """Total file operation counts by kind, with optional ?days= filter."""
        try:
            days = max(1, int(request.query_params.get("days", 30)))
        except (TypeError, ValueError):
            days = 30

        scope = _user_scope(request)
        since = timezone.now() - timedelta(days=days)
        qs = UsageEvent.objects.filter(scope=scope, occurred_at__gte=since)

        ops = {kind: qs.filter(operation=kind).count() for kind in OperationKind.values}
        return Response({"days": days, "total": sum(ops.values()), "ops": ops})

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "days",
                int,
                OpenApiParameter.QUERY,
                description="Number of days to look back (default: 30)",
                required=False,
            )
        ],
        responses={"200": ByVaultItemSerializer(many=True)},
    )
    def by_vault(self, request):
        """Per-vault-item operation breakdown."""
        try:
            days = max(1, int(request.query_params.get("days", 30)))
        except (TypeError, ValueError):
            days = 30

        scope = _user_scope(request)
        since = timezone.now() - timedelta(days=days)
        qs = UsageEvent.objects.filter(scope=scope, occurred_at__gte=since)

        pairs = (
            qs.values("vault_item_name", "vault_item_kind")
            .distinct()
            .order_by("vault_item_name")
        )

        result = []
        for pair in pairs:
            name = pair["vault_item_name"]
            kind = pair["vault_item_kind"]
            item_qs = qs.filter(vault_item_name=name)
            ops = {
                op: item_qs.filter(operation=op).count()
                for op in OperationKind.values
                if op != "test"
            }
            result.append({"name": name, "kind": kind, "total": sum(ops.values()), **ops})

        result.sort(key=lambda x: x["total"], reverse=True)
        return Response(result)

    @extend_schema(responses=VaultMetricsSerializer)
    def vault_metrics(self, request):
        """Vault item counts by kind and recently added items."""
        scope = _user_scope(request)
        qs = VaultItem.objects.filter(scope=scope)

        total = qs.count()
        by_kind = {
            row["kind"]: row["count"]
            for row in qs.values("kind").annotate(count=Count("id"))
        }
        recent = [
            {"name": r["name"], "kind": r["kind"], "created_at": r["created_at"]}
            for r in qs.order_by("-created_at").values("name", "kind", "created_at")[:5]
        ]

        return Response({"total": total, "by_kind": by_kind, "recent": recent})
