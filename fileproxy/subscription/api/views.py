from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import SubscriptionPlan, UserSubscription
from ..service import (
    cancel_subscription,
    create_plan,
    delete_plan,
    get_cycle_usage,
    get_or_create_subscription,
    set_default_plan,
    switch_plan,
)
from .serializers import (
    CycleUsageSerializer,
    SubscriptionPlanCreateSerializer,
    SubscriptionPlanSerializer,
    UserSubscriptionSerializer,
)


def _get_or_404(queryset_or_model, **kwargs):
    """Like get_object_or_404, but also catches ValidationError for invalid PK types."""
    try:
        return get_object_or_404(queryset_or_model, **kwargs)
    except (DjangoValidationError, ValueError, TypeError):
        raise Http404


class SubscriptionPlanViewSet(viewsets.GenericViewSet):
    """Staff-only plan management."""

    permission_classes = [IsAdminUser]
    serializer_class = SubscriptionPlanSerializer

    def get_queryset(self):
        return SubscriptionPlan.objects.all()

    def list(self, request):
        """GET /api/v1/subscription/plans/"""
        plans = self.get_queryset()
        return Response(SubscriptionPlanSerializer(plans, many=True).data)

    def create(self, request):
        """POST /api/v1/subscription/plans/"""
        s = SubscriptionPlanCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        plan = create_plan(
            name=d["name"],
            is_default=d.get("is_default", False),
            enumerate_limit=d.get("enumerate_limit"),
            read_limit=d.get("read_limit"),
            write_limit=d.get("write_limit"),
            delete_limit=d.get("delete_limit"),
            read_transfer_limit_bytes=d.get("read_transfer_limit_bytes"),
            write_transfer_limit_bytes=d.get("write_transfer_limit_bytes"),
        )
        return Response(SubscriptionPlanSerializer(plan).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        """GET /api/v1/subscription/plans/{id}/"""
        plan = _get_or_404(self.get_queryset(), pk=pk)
        return Response(SubscriptionPlanSerializer(plan).data)

    def destroy(self, request, pk=None):
        """DELETE /api/v1/subscription/plans/{id}/"""
        plan = _get_or_404(self.get_queryset(), pk=pk)
        delete_plan(plan)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="set-default")
    def set_default(self, request, pk=None):
        """POST /api/v1/subscription/plans/{id}/set-default/"""
        plan = _get_or_404(self.get_queryset(), pk=pk)
        set_default_plan(plan)
        return Response(SubscriptionPlanSerializer(plan).data)

    @action(detail=True, methods=["get"])
    def subscribers(self, request, pk=None):
        """GET /api/v1/subscription/plans/{id}/subscribers/"""
        plan = _get_or_404(self.get_queryset(), pk=pk)
        subs_qs = UserSubscription.objects.filter(plan=plan).select_related("user")

        try:
            limit = max(1, min(1000, int(request.query_params.get("limit", 100))))
        except (TypeError, ValueError):
            limit = 100
        try:
            offset = max(0, int(request.query_params.get("offset", 0)))
        except (TypeError, ValueError):
            offset = 0

        subs = subs_qs[offset : offset + limit]
        return Response(UserSubscriptionSerializer(subs, many=True).data)


class MySubscriptionView(APIView):
    """Authenticated-user subscription management."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """GET /api/v1/subscription/my/"""
        sub = get_or_create_subscription(request.user)
        return Response(UserSubscriptionSerializer(sub).data)


class MySubscriptionSwitchView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """POST /api/v1/subscription/my/switch/"""
        plan_id = request.data.get("plan_id")
        if not plan_id:
            return Response({"detail": "plan_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        plan = _get_or_404(SubscriptionPlan, pk=plan_id, expires_at__isnull=True)
        sub = switch_plan(request.user, plan)
        return Response(UserSubscriptionSerializer(sub).data)


class MySubscriptionCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """POST /api/v1/subscription/my/cancel/"""
        sub = cancel_subscription(request.user)
        return Response(UserSubscriptionSerializer(sub).data)


class MySubscriptionUsageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """GET /api/v1/subscription/my/usage/"""
        sub = get_or_create_subscription(request.user)
        usage = get_cycle_usage(sub)
        plan = sub.get_effective_plan()
        data = {**usage, "plan": plan}
        return Response(CycleUsageSerializer(data).data)


class MyAvailablePlansView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """GET /api/v1/subscription/my/plans/"""
        plans = SubscriptionPlan.objects.filter(expires_at__isnull=True).order_by("name")
        return Response(SubscriptionPlanSerializer(plans, many=True).data)
