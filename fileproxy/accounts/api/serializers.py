from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from ..models import APIKey, UserProfile


class APIKeyListSerializer(serializers.ModelSerializer):
    class Meta:
        model = APIKey
        fields = ["id", "name", "created_at", "last_used_at"]


class APIKeyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ["status", "signup_source", "status_updated_at", "review_note"]


class UserListSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)
    plan_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "is_staff",
            "is_active",
            "date_joined",
            "last_login",
            "profile",
            "plan_name",
        ]

    def get_plan_name(self, user):
        try:
            sub = user.subscription
            if sub.plan:
                return sub.plan.name
        except ObjectDoesNotExist:
            pass
        return None


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "is_staff"]
