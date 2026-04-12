import uuid

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class NotificationPreferences(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="notification_prefs")
    email_billing_alerts = models.BooleanField(default=True)
    email_product_updates = models.BooleanField(default=False)


class UserProfile(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACTIVE = "active"
    STATUS_REJECTED = "rejected"
    STATUS_SUSPENDED = "suspended"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_SUSPENDED, "Suspended"),
    ]

    SOURCE_NORMAL = "normal"
    SOURCE_BETA = "beta"
    SOURCE_CHOICES = [
        (SOURCE_NORMAL, "Normal"),
        (SOURCE_BETA, "Beta"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    signup_source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_NORMAL)
    status_updated_at = models.DateTimeField(default=timezone.now)
    review_note = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["-status_updated_at"]

    def __str__(self):
        return f"{self.user.username} ({self.status})"

    def set_status(self, status: str, note: str = ""):
        self.status = status
        self.status_updated_at = timezone.now()
        if note:
            self.review_note = note
        self.save(update_fields=["status", "status_updated_at", "review_note"])


class APIKey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
