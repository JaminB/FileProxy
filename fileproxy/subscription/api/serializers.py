from __future__ import annotations

from rest_framework import serializers

from ..models import SubscriptionPlan, UserSubscription


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = [
            "id",
            "name",
            "is_default",
            "enumerate_limit",
            "read_limit",
            "write_limit",
            "delete_limit",
            "read_transfer_limit_bytes",
            "write_transfer_limit_bytes",
            "expires_at",
            "created_at",
        ]
        read_only_fields = fields


class SubscriptionPlanCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    is_default = serializers.BooleanField(default=False)
    enumerate_limit = serializers.IntegerField(min_value=0, allow_null=True, required=False)
    read_limit = serializers.IntegerField(min_value=0, allow_null=True, required=False)
    write_limit = serializers.IntegerField(min_value=0, allow_null=True, required=False)
    delete_limit = serializers.IntegerField(min_value=0, allow_null=True, required=False)
    read_transfer_limit_bytes = serializers.IntegerField(
        min_value=0, allow_null=True, required=False
    )
    write_transfer_limit_bytes = serializers.IntegerField(
        min_value=0, allow_null=True, required=False
    )


class UserSubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    effective_plan = serializers.SerializerMethodField()
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = UserSubscription
        fields = [
            "id",
            "username",
            "email",
            "plan",
            "effective_plan",
            "status",
            "cycle_started_at",
            "cycle_ends_at",
            "cancels_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_effective_plan(self, obj):
        plan = obj.get_effective_plan()
        if plan is None:
            return None
        return SubscriptionPlanSerializer(plan).data


class CycleUsageSerializer(serializers.Serializer):
    enumerate = serializers.IntegerField()
    read = serializers.IntegerField()
    write = serializers.IntegerField()
    delete = serializers.IntegerField()
    read_bytes = serializers.IntegerField()
    write_bytes = serializers.IntegerField()
    plan = SubscriptionPlanSerializer(allow_null=True)
