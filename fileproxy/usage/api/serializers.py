from rest_framework import serializers


class OperationCountsSerializer(serializers.Serializer):
    test = serializers.IntegerField()
    enumerate = serializers.IntegerField()
    read = serializers.IntegerField()
    write = serializers.IntegerField()
    delete = serializers.IntegerField()


class SummarySerializer(serializers.Serializer):
    days = serializers.IntegerField()
    total = serializers.IntegerField()
    ops = OperationCountsSerializer()


class ByVaultItemSerializer(serializers.Serializer):
    name = serializers.CharField()
    kind = serializers.CharField()
    enumerate = serializers.IntegerField()
    read = serializers.IntegerField()
    write = serializers.IntegerField()
    delete = serializers.IntegerField()
    total = serializers.IntegerField()


class RecentVaultItemSerializer(serializers.Serializer):
    name = serializers.CharField()
    kind = serializers.CharField()
    created_at = serializers.DateTimeField()


class VaultMetricsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    by_kind = serializers.DictField(child=serializers.IntegerField())
    recent = RecentVaultItemSerializer(many=True)
