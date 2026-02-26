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
        "read_transfer_mb",
        "write_transfer_mb",
        "expires_at",
        "created_at",
    ]
    list_filter = ["is_default"]

    @admin.display(description="Read transfer (MB)")
    def read_transfer_mb(self, obj):
        if obj.read_transfer_limit_bytes is None:
            return "Unlimited"
        return f"{obj.read_transfer_limit_bytes / 1_048_576:.1f} MB"

    @admin.display(description="Write transfer (MB)")
    def write_transfer_mb(self, obj):
        if obj.write_transfer_limit_bytes is None:
            return "Unlimited"
        return f"{obj.write_transfer_limit_bytes / 1_048_576:.1f} MB"


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ["user", "plan", "status", "cycle_started_at", "cycle_ends_at", "created_at"]
    list_filter = ["status"]
    raw_id_fields = ["user"]
