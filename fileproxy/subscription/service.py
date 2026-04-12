from __future__ import annotations

import calendar

from django.db import transaction
from django.utils import timezone

from files.services import user_scope
from usage.models import OperationKind


class SubscriptionLimitExceeded(Exception):
    pass


def _add_one_month(dt):
    """Add approximately one month to a datetime, preserving tzinfo."""
    month = dt.month + 1
    year = dt.year
    if month > 12:
        month = 1
        year += 1
    # Handle end-of-month edge cases
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def get_or_create_subscription(user):
    from .models import UserSubscription

    try:
        sub = UserSubscription.objects.select_related("plan").get(user=user)
    except UserSubscription.DoesNotExist:
        now = timezone.now()
        sub = UserSubscription.objects.create(
            user=user,
            plan=None,
            status=UserSubscription.STATUS_ACTIVE,
            current_period_start=now,
            current_period_end=_add_one_month(now),
        )

    advance_cycle_if_needed(sub)
    return sub


def advance_cycle_if_needed(sub) -> None:

    now = timezone.now()
    if now <= sub.current_period_end:
        return

    # Advance the cycle
    sub.current_period_start = sub.current_period_end
    sub.current_period_end = _add_one_month(sub.current_period_start)

    # If the plan is expired/soft-deleted, fall back to default
    if sub.plan and sub.plan.is_expired:
        sub.plan = None

    # If status is canceled and the cancel_at has passed, reset to active on default
    if sub.status == sub.STATUS_CANCELED and sub.cancel_at and now >= sub.cancel_at:
        sub.plan = None
        sub.status = sub.STATUS_ACTIVE
        sub.cancel_at = None

    sub.save(
        update_fields=["current_period_start", "current_period_end", "plan", "status", "cancel_at"]
    )


def get_cycle_usage(sub) -> dict:
    from usage.models import UsageEvent

    scope = user_scope(sub.user)
    events = UsageEvent.objects.filter(
        scope=scope,
        occurred_at__gte=sub.current_period_start,
        occurred_at__lt=sub.current_period_end,
        ok=True,
    )

    result = {
        "enumerate": 0,
        "read": 0,
        "write": 0,
        "delete": 0,
        "read_bytes": 0,
        "write_bytes": 0,
    }

    for event in events.values("operation", "bytes_transferred"):
        op = event["operation"]
        bt = event["bytes_transferred"] or 0
        if op == OperationKind.ENUMERATE:
            result["enumerate"] += 1
        elif op == OperationKind.READ:
            result["read"] += 1
            result["read_bytes"] += bt
        elif op == OperationKind.WRITE:
            result["write"] += 1
            result["write_bytes"] += bt
        elif op == OperationKind.DELETE:
            result["delete"] += 1

    return result


def check_limit(user, operation: str, bytes_count: int = 0) -> None:
    from django.conf import settings

    if not settings.SUBSCRIPTIONS_ENABLED:
        return

    sub = get_or_create_subscription(user)
    plan = sub.get_effective_plan()

    if plan is None:
        return

    usage = get_cycle_usage(sub)

    if operation == "enumerate":
        if plan.enumerate_limit is not None and usage["enumerate"] >= plan.enumerate_limit:
            raise SubscriptionLimitExceeded(
                f"Enumerate limit of {plan.enumerate_limit} requests/cycle exceeded."
            )
    elif operation == "read":
        if plan.read_limit is not None and usage["read"] >= plan.read_limit:
            raise SubscriptionLimitExceeded(
                f"Read limit of {plan.read_limit} requests/cycle exceeded."
            )
        if (
            plan.read_transfer_limit_bytes is not None
            and usage["read_bytes"] + bytes_count > plan.read_transfer_limit_bytes
        ):
            raise SubscriptionLimitExceeded(
                f"Read data transfer limit of {plan.read_transfer_limit_bytes}"
                " bytes/cycle exceeded."
            )
    elif operation == "write":
        if plan.write_limit is not None and usage["write"] >= plan.write_limit:
            raise SubscriptionLimitExceeded(
                f"Write limit of {plan.write_limit} requests/cycle exceeded."
            )
        if (
            plan.write_transfer_limit_bytes is not None
            and usage["write_bytes"] + bytes_count > plan.write_transfer_limit_bytes
        ):
            raise SubscriptionLimitExceeded(
                f"Write data transfer limit of {plan.write_transfer_limit_bytes}"
                " bytes/cycle exceeded."
            )
    elif operation == "delete":
        if plan.delete_limit is not None and usage["delete"] >= plan.delete_limit:
            raise SubscriptionLimitExceeded(
                f"Delete limit of {plan.delete_limit} requests/cycle exceeded."
            )


@transaction.atomic
def create_plan(
    *,
    name: str,
    is_default: bool = False,
    enumerate_limit=None,
    read_limit=None,
    write_limit=None,
    delete_limit=None,
    read_transfer_limit_bytes=None,
    write_transfer_limit_bytes=None,
):
    from .models import SubscriptionPlan

    if is_default:
        SubscriptionPlan.objects.filter(is_default=True).update(is_default=False)

    return SubscriptionPlan.objects.create(
        name=name,
        is_default=is_default,
        enumerate_limit=enumerate_limit,
        read_limit=read_limit,
        write_limit=write_limit,
        delete_limit=delete_limit,
        read_transfer_limit_bytes=read_transfer_limit_bytes,
        write_transfer_limit_bytes=write_transfer_limit_bytes,
    )


@transaction.atomic
def delete_plan(plan) -> None:
    from .models import UserSubscription

    if UserSubscription.objects.filter(plan=plan, status=UserSubscription.STATUS_ACTIVE).exists():
        plan.expires_at = timezone.now()
        plan.save(update_fields=["expires_at"])
    else:
        plan.delete()


@transaction.atomic
def set_default_plan(plan) -> None:
    from .models import SubscriptionPlan

    SubscriptionPlan.objects.filter(is_default=True).update(is_default=False)
    plan.is_default = True
    plan.save(update_fields=["is_default"])


@transaction.atomic
def switch_plan(user, plan) -> object:
    from .models import UserSubscription

    sub = get_or_create_subscription(user)
    now = timezone.now()
    sub.plan = plan
    sub.current_period_start = now
    sub.current_period_end = _add_one_month(now)
    sub.status = UserSubscription.STATUS_ACTIVE
    sub.cancel_at = None
    sub.save(
        update_fields=["plan", "current_period_start", "current_period_end", "status", "cancel_at"]
    )
    return sub


def get_or_create_beta_plan():
    from .models import SubscriptionPlan

    plan, _ = SubscriptionPlan.objects.get_or_create(
        name="beta",
        defaults={
            "enumerate_limit": 5000,
            "read_limit": 1000,
            "write_limit": 500,
            "delete_limit": 500,
            "read_transfer_limit_bytes": 1_073_741_824,  # 1 GB
            "write_transfer_limit_bytes": 1_073_741_824,  # 1 GB
        },
    )
    return plan


@transaction.atomic
def cancel_subscription(user) -> object:
    sub = get_or_create_subscription(user)
    sub.status = sub.STATUS_CANCELED
    sub.cancel_at = sub.current_period_end
    sub.cancel_at_period_end = True
    sub.save(update_fields=["status", "cancel_at", "cancel_at_period_end"])
    return sub
