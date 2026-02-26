from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from ..models import OperationKind, UsageEvent
from .serializers import ByConnectionSerializer, SummarySerializer, TimelineSerializer


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
                "connection",
                str,
                OpenApiParameter.QUERY,
                description="Filter by connection name",
                required=False,
            ),
        ],
        responses=SummarySerializer,
    )
    def summary(self, request):
        """Total file operation counts by kind, with optional ?days= and ?connection= filters."""
        try:
            days = max(1, min(3650, int(request.query_params.get("days", 30))))
        except (TypeError, ValueError):
            days = 30

        scope = _user_scope(request)
        since = timezone.now() - timedelta(days=days)
        qs = UsageEvent.objects.filter(scope=scope, occurred_at__gte=since)

        vault = request.query_params.get("connection", "").strip()
        if vault:
            qs = qs.filter(connection_name=vault)

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
        responses={"200": ByConnectionSerializer(many=True)},
    )
    def by_connection(self, request):
        """Per-connection operation breakdown."""
        try:
            days = max(1, min(3650, int(request.query_params.get("days", 30))))
        except (TypeError, ValueError):
            days = 30

        scope = _user_scope(request)
        since = timezone.now() - timedelta(days=days)
        qs = UsageEvent.objects.filter(scope=scope, occurred_at__gte=since)

        non_test_ops = [op for op in OperationKind.values if op != "test"]
        annotations = {op: Count("id", filter=Q(operation=op)) for op in non_test_ops}
        rows = (
            qs.values("connection_name", "connection_kind")
            .annotate(**annotations)
            .order_by("connection_name")
        )

        result = []
        for row in rows:
            ops = {op: row[op] for op in non_test_ops}
            result.append(
                {
                    "name": row["connection_name"],
                    "kind": row["connection_kind"],
                    "total": sum(ops.values()),
                    **ops,
                }
            )

        result.sort(key=lambda x: x["total"], reverse=True)
        return Response(result)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "connection",
                str,
                OpenApiParameter.QUERY,
                description="Connection name (required)",
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
        """Time-series event counts per operation for a connection."""
        vault = request.query_params.get("connection", "").strip()
        if not vault:
            return Response(
                {"detail": "connection parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            days = max(1, min(3650, int(request.query_params.get("days", 30))))
        except (TypeError, ValueError):
            days = 30

        scope = _user_scope(request)
        today = timezone.now().date()
        # days=7 → start_date = today-6, giving exactly 7 dates: [today-6 .. today]
        start_date = today - timedelta(days=days - 1)
        since = timezone.make_aware(
            timezone.datetime.combine(start_date, timezone.datetime.min.time())
        )

        rows = (
            UsageEvent.objects.filter(scope=scope, connection_name=vault, occurred_at__gte=since)
            .annotate(date=TruncDate("occurred_at"))
            .values("date", "operation")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        date_list = [str(start_date + timedelta(days=i)) for i in range(days)]

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
            {"connection_name": vault, "days": days, "dates": date_list, "series": series}
        )
