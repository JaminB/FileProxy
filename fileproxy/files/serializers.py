from __future__ import annotations

from rest_framework import serializers


class BackendObjectSerializer(serializers.Serializer):
    name = serializers.CharField()
    path = serializers.CharField()
    size = serializers.IntegerField(required=False, allow_null=True)


class EnumerateQuerySerializer(serializers.Serializer):
    prefix = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    cursor = serializers.CharField(required=False, allow_null=True)
    page_size = serializers.IntegerField(required=False, default=1000, min_value=1, max_value=1000)


class EnumeratePageSerializer(serializers.Serializer):
    objects = BackendObjectSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class ReadFileQuerySerializer(serializers.Serializer):
    path = serializers.CharField()


class WriteFileSerializer(serializers.Serializer):
    path = serializers.CharField()
    data_base64 = serializers.CharField(help_text="Base64-encoded bytes")


class DeleteFileSerializer(serializers.Serializer):
    path = serializers.CharField()


class VaultItemMetaSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    kind = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    rotated_at = serializers.DateTimeField(allow_null=True)
