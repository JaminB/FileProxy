from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


class SubscriptionPlan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    is_default = models.BooleanField(default=False)
    enumerate_limit = models.PositiveIntegerField(null=True, blank=True)
    read_limit = models.PositiveIntegerField(null=True, blank=True)
    write_limit = models.PositiveIntegerField(null=True, blank=True)
    delete_limit = models.PositiveIntegerField(null=True, blank=True)
    read_transfer_limit_bytes = models.BigIntegerField(null=True, blank=True)
    write_transfer_limit_bytes = models.BigIntegerField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Stripe pricing fields (null = free/default plan)
    stripe_product_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    stripe_price_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    price_cents = models.PositiveIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="usd")
    billing_interval = models.CharField(
        max_length=10,
        choices=[("month", "Monthly"), ("year", "Yearly")],
        null=True,
        blank=True,
    )
    billing_interval_count = models.PositiveIntegerField(default=1)
    trial_days = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_default", "expires_at"], name="sub_plan_default_exp_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    @classmethod
    def get_default(cls) -> SubscriptionPlan | None:
        return cls.objects.filter(is_default=True, expires_at__isnull=True).first()

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= timezone.now()


class UserSubscription(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_CANCELED = "canceled"
    STATUS_CHOICES = [
        ("trialing", "Trialing"),
        ("active", "Active"),
        ("past_due", "Past Due"),
        ("canceled", "Canceled"),
        ("incomplete", "Incomplete"),
        ("incomplete_expired", "Incomplete Expired"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(
        SubscriptionPlan,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="subscribers",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    cancel_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Stripe identifiers
    stripe_customer_id = models.CharField(
        max_length=255, null=True, blank=True, unique=True, db_index=True
    )
    stripe_subscription_id = models.CharField(
        max_length=255, null=True, blank=True, unique=True, db_index=True
    )
    # Trial period
    trial_start = models.DateTimeField(null=True, blank=True)
    trial_end = models.DateTimeField(null=True, blank=True)
    # Cancellation state
    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Subscription({self.user}, {self.status})"

    def get_effective_plan(self) -> SubscriptionPlan | None:
        if self.plan and not self.plan.is_expired:
            return self.plan
        return SubscriptionPlan.get_default()
