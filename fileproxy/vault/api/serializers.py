from __future__ import annotations

from rest_framework import serializers

from vault.models import VaultItem, VaultItemKind
from vault.schemas import S3StaticCredentials
from vault.service import create_s3_credentials


class VaultItemListSerializer(serializers.ModelSerializer):
    class Meta:
        model = VaultItem
        fields = ["id", "name", "kind", "created_at", "updated_at", "rotated_at"]


class S3CredentialsCreateSerializer(serializers.Serializer):
    """
    Input-only serializer for creating S3 credentials.
    Never returns secrets.
    """

    name = serializers.CharField(max_length=120)
    access_key_id = serializers.CharField(max_length=128, trim_whitespace=True)
    secret_access_key = serializers.CharField(max_length=256, trim_whitespace=True)
    session_token = serializers.CharField(
        max_length=2048, required=False, allow_null=True, allow_blank=True, trim_whitespace=True
    )

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
        # normalize session token
        st = attrs.get("session_token")
        if st is not None:
            st = st.strip()
            attrs["session_token"] = st if st else None
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        creds = S3StaticCredentials(
            access_key_id=validated_data["access_key_id"],
            secret_access_key=validated_data["secret_access_key"],
            session_token=validated_data.get("session_token"),
        )
        item = create_s3_credentials(
            user=request.user,
            name=validated_data["name"],
            creds=creds,
        )
        return item


class VaultItemRenameSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)