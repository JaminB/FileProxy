from django.contrib import admin

from .models import SubscriptionPlan, UserSubscription


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "is_default",
        "enumerate_limit",
        "read_limit",
        "write_limit",
        "delete_limit",
        "expires_at",
        "created_at",
    ]
    list_filter = ["is_default"]


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ["user", "plan", "status", "cycle_started_at", "cycle_ends_at", "created_at"]
    list_filter = ["status"]
    raw_id_fields = ["user"]
