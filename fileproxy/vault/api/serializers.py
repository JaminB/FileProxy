from __future__ import annotations

import re

from rest_framework import serializers

from ..models import VaultItem
from ..schemas import S3StaticCredentials
from ..service import create_azure_blob_credentials, create_s3_credentials


class VaultItemListSerializer(serializers.ModelSerializer):
    bucket = serializers.SerializerMethodField()
    account_name = serializers.SerializerMethodField()
    container_name = serializers.SerializerMethodField()

    class Meta:
        model = VaultItem
        fields = [
            "id",
            "name",
            "kind",
            "bucket",
            "account_name",
            "container_name",
            "created_at",
            "updated_at",
            "rotated_at",
        ]

    def get_bucket(self, obj: VaultItem) -> str | None:
        payload = obj.get_payload()
        settings = payload.get("settings", {})
        return settings.get("bucket")

    def get_account_name(self, obj: VaultItem) -> str | None:
        payload = obj.get_payload()
        settings = payload.get("settings", {})
        return settings.get("account_name")

    def get_container_name(self, obj: VaultItem) -> str | None:
        payload = obj.get_payload()
        settings = payload.get("settings", {})
        return settings.get("container_name")


class S3CredentialsCreateSerializer(serializers.Serializer):
    """Create S3 credentials without returning secrets."""

    name = serializers.CharField(max_length=120)
    bucket = serializers.CharField(max_length=63, trim_whitespace=True)

    access_key_id = serializers.CharField(max_length=128, trim_whitespace=True)
    secret_access_key = serializers.CharField(max_length=256, trim_whitespace=True)
    session_token = serializers.CharField(
        max_length=2048,
        required=False,
        allow_null=True,
        allow_blank=True,
        trim_whitespace=True,
    )

    def validate_bucket(self, v: str) -> str:
        v = v.strip()
        if not v:
            raise serializers.ValidationError("bucket is required")
        return v

    def validate_access_key_id(self, v: str) -> str:
        v = v.strip()
        if len(v) < 16:
            raise serializers.ValidationError("access_key_id is too short")
        return v

    def validate_secret_access_key(self, v: str) -> str:
        v = v.strip()
        if len(v) < 30:
            raise serializers.ValidationError("secret_access_key is too short")
        return v

    def validate(self, attrs):
        st = attrs.get("session_token")
        if st is not None:
            st = st.strip()
            attrs["session_token"] = st if st else None
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        scope = f"user:{request.user.id}"

        creds = S3StaticCredentials(
            access_key_id=validated_data["access_key_id"],
            secret_access_key=validated_data["secret_access_key"],
            session_token=validated_data.get("session_token"),
        )

        settings_obj = {
            "bucket": validated_data["bucket"],
            "user_id": request.user.id,
        }
        secrets_obj = {
            "access_key_id": creds.access_key_id,
            "secret_access_key": creds.secret_access_key,
            "session_token": creds.session_token,
        }

        return create_s3_credentials(
            scope=scope,
            name=validated_data["name"],
            settings_obj=settings_obj,
            secrets_obj=secrets_obj,
        )


class GDriveCreateSerializer(serializers.Serializer):
    """Validates the pre-OAuth form fields."""

    name = serializers.CharField(max_length=120)


class DropboxCreateSerializer(serializers.Serializer):
    """Validates the pre-OAuth form fields for Dropbox."""

    name = serializers.CharField(max_length=120)


class AzureBlobCreateSerializer(serializers.Serializer):
    """Create Azure Blob Storage credentials without returning secrets."""

    name = serializers.CharField(max_length=120)
    account_name = serializers.CharField(max_length=24, trim_whitespace=True)
    container_name = serializers.CharField(max_length=63, trim_whitespace=True)
    tenant_id = serializers.CharField(max_length=256, trim_whitespace=True)
    client_id = serializers.CharField(max_length=256, trim_whitespace=True)
    client_secret = serializers.CharField(max_length=512, trim_whitespace=True)

    def validate_account_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Account name cannot be empty.")
        if not re.fullmatch(r"[a-z0-9]{3,24}", value):
            raise serializers.ValidationError(
                "Account name must be 3–24 characters and may only contain"
                " lowercase letters and numbers."
            )
        return value

    def validate_container_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Container name cannot be empty.")
        return value

    def create(self, validated_data):
        request = self.context["request"]
        scope = f"user:{request.user.id}"

        settings_obj = {
            "user_id": request.user.id,
            "account_name": validated_data["account_name"],
            "container_name": validated_data["container_name"],
        }
        secrets_obj = {
            "tenant_id": validated_data["tenant_id"],
            "client_id": validated_data["client_id"],
            "client_secret": validated_data["client_secret"],
        }

        return create_azure_blob_credentials(
            scope=scope,
            name=validated_data["name"],
            settings_obj=settings_obj,
            secrets_obj=secrets_obj,
        )


class VaultItemRenameSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
