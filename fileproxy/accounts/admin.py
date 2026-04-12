from django.contrib import admin

from .models import APIKey, UserProfile


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "created_at", "last_used_at"]
    readonly_fields = ["id", "created_at", "last_used_at"]


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "status", "signup_source", "status_updated_at"]
    list_filter = ["status", "signup_source"]
    search_fields = ["user__username", "user__email"]
    readonly_fields = ["status_updated_at"]
