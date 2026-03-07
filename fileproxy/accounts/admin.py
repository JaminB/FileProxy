from django.contrib import admin

from .models import APIKey


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "created_at", "last_used_at"]
    readonly_fields = ["id", "created_at", "last_used_at"]
