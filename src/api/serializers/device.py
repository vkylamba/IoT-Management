from rest_framework import serializers
from device.models import UserDeviceType, StatusType


class UserDeviceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserDeviceType
        fields = (
            'id',
            'name',
            'code',
            'identifier_field',
            'details',
            'data_schema',
            'created_at',
            'active',
        )

class StatusTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatusType
        fields = (
            'id',
            'name',
            'code',
            'translation_schema',
            'created_at',
            'active',
        )
