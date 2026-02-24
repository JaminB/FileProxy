from __future__ import annotations

from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from ..models import OperationKind, UsageEvent
from .serializers import ByVaultItemSerializer, SummarySerializer, TimelineSerializer


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
            ),
            OpenApiParameter(
                "vault",
                str,
                OpenApiParameter.QUERY,
                description="Filter by vault item name",
                required=False,
            ),
        ],
        responses=SummarySerializer,
    )
    def summary(self, request):
        """Total file operation counts by kind, with optional ?days= and ?vault= filters."""
        try:
            days = max(1, int(request.query_params.get("days", 30)))
        except (TypeError, ValueError):
            days = 30

        scope = _user_scope(request)
        since = timezone.now() - timedelta(days=days)
        qs = UsageEvent.objects.filter(scope=scope, occurred_at__gte=since)

        vault = request.query_params.get("vault", "").strip()
        if vault:
            qs = qs.filter(vault_item_name=vault)

        ops = {
            kind: qs.filter(operation=kind).count()
            for kind in OperationKind.values
            if kind != "test"
        }
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

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "vault",
                str,
                OpenApiParameter.QUERY,
                description="Vault item name (required)",
                required=True,
            ),
            OpenApiParameter(
                "days",
                int,
                OpenApiParameter.QUERY,
                description="Number of days to look back (default: 30)",
                required=False,
            ),
        ],
        responses=TimelineSerializer,
    )
    def timeline(self, request):
        """Time-series event counts per operation for a vault item."""
        vault = request.query_params.get("vault", "").strip()
        if not vault:
            return Response(
                {"detail": "vault parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            days = max(1, int(request.query_params.get("days", 30)))
        except (TypeError, ValueError):
            days = 30

        scope = _user_scope(request)
        since = timezone.now() - timedelta(days=days)

        rows = (
            UsageEvent.objects.filter(
                scope=scope, vault_item_name=vault, occurred_at__gte=since
            )
            .annotate(date=TruncDate("occurred_at"))
            .values("date", "operation")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        today = timezone.now().date()
        date_list = []
        d = since.date()
        while d <= today:
            date_list.append(str(d))
            d += timedelta(days=1)

        ops = ["enumerate", "read", "write", "delete"]
        series: dict[str, list[int]] = {op: [0] * len(date_list) for op in ops}
        date_index = {date_str: i for i, date_str in enumerate(date_list)}

        for row in rows:
            op = row["operation"]
            if op in series:
                idx = date_index.get(str(row["date"]))
                if idx is not None:
                    series[op][idx] += row["count"]

        return Response(
            {"vault_item_name": vault, "days": days, "dates": date_list, "series": series}
        )
