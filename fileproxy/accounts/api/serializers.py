from rest_framework import serializers

from ..models import APIKey


class APIKeyListSerializer(serializers.ModelSerializer):
    class Meta:
        model = APIKey
        fields = ["id", "name", "created_at", "last_used_at"]


class APIKeyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
