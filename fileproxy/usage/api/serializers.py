from rest_framework import serializers


class OperationCountsSerializer(serializers.Serializer):
    enumerate = serializers.IntegerField()
    read = serializers.IntegerField()
    write = serializers.IntegerField()
    delete = serializers.IntegerField()


class SummarySerializer(serializers.Serializer):
    days = serializers.IntegerField()
    total = serializers.IntegerField()
    ops = OperationCountsSerializer()


class ByConnectionSerializer(serializers.Serializer):
    name = serializers.CharField()
    kind = serializers.CharField()
    enumerate = serializers.IntegerField()
    read = serializers.IntegerField()
    write = serializers.IntegerField()
    delete = serializers.IntegerField()
    total = serializers.IntegerField()


class TimelineSerializer(serializers.Serializer):
    connection_name = serializers.CharField()
    days = serializers.IntegerField()
    dates = serializers.ListField(child=serializers.CharField())
    series = serializers.DictField(child=serializers.ListField(child=serializers.IntegerField()))
