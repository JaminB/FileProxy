from __future__ import annotations

from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, render

from accounts.models import UserProfile
from accounts.ui.views import _require_staff
from subscription.models import SubscriptionPlan


def _pending_count() -> int:
    return UserProfile.objects.filter(status=UserProfile.STATUS_PENDING).count()


def dashboard(request):
    denied = _require_staff(request)
    if denied:
        return denied

    stats = {
        "total": User.objects.count(),
        "pending": UserProfile.objects.filter(
            status=UserProfile.STATUS_PENDING
        ).count(),
        "active": UserProfile.objects.filter(status=UserProfile.STATUS_ACTIVE).count(),
        "suspended": UserProfile.objects.filter(
            status=UserProfile.STATUS_SUSPENDED
        ).count(),
        "beta": UserProfile.objects.filter(
            signup_source=UserProfile.SOURCE_BETA
        ).count(),
    }
    return render(
        request,
        "admin_panel/dashboard.html",
        {"stats": stats, "pending_count": stats["pending"]},
    )


def users(request):
    denied = _require_staff(request)
    if denied:
        return denied
    plans = SubscriptionPlan.objects.filter(expires_at__isnull=True).order_by("name")
    return render(
        request,
        "admin_panel/users.html",
        {"plans": plans, "pending_count": _pending_count()},
    )


def user_detail(request, user_id):
    denied = _require_staff(request)
    if denied:
        return denied
    target_user = get_object_or_404(
        User.objects.select_related("profile", "subscription__plan"), pk=user_id
    )
    plans = SubscriptionPlan.objects.filter(expires_at__isnull=True).order_by("name")
    return render(
        request,
        "admin_panel/user_detail.html",
        {"target_user": target_user, "plans": plans, "pending_count": _pending_count()},
    )


def beta(request):
    denied = _require_staff(request)
    if denied:
        return denied
    plans = SubscriptionPlan.objects.filter(expires_at__isnull=True).order_by("name")
    return render(
        request,
        "admin_panel/beta.html",
        {"plans": plans, "pending_count": _pending_count()},
    )
