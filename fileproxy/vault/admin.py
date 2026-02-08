from __future__ import annotations

from django.contrib import admin

from .models import VaultItem


@admin.register(VaultItem)
class VaultItemAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "kind", "scope", "created_at", "updated_at", "rotated_at")
    list_filter = ("kind", "created_at", "updated_at", "rotated_at")
    search_fields = ("name", "scope")
    readonly_fields = (
        "scope",
        "kind",
        "wrapped_dek",
        "payload_nonce",
        "payload_ciphertext",
        "created_at",
        "updated_at",
        "rotated_at",
    )
