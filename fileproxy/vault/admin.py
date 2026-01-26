from django.contrib import admin
from .models import VaultItem


@admin.register(VaultItem)
class VaultItemAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "name", "kind", "created_at", "rotated_at")
    list_filter = ("kind",)
    search_fields = ("name", "user__username", "user__email")

    readonly_fields = (
        "user",
        "name",
        "kind",
        "wrapped_dek",
        "payload_nonce",
        "payload_ciphertext",
        "created_at",
        "updated_at",
        "rotated_at",
    )

    def has_add_permission(self, request):
        # Create via app/API, not admin, to reduce accidental secret exposure.
        return False

    def has_change_permission(self, request, obj=None):
        return False