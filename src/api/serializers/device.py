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
            'user',
            'device',
            'device_type',
            'target_type',
            'update_trigger',
            'schedule',
            'last_trigger_time',
            'translation_schema',
            'created_at',
            'active',
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data['device']:
            data['device'] = str(instance.device) if instance.device is not None else None
            data['device_type'] = str(instance.device_type.code) if instance.device_type is not None else None
        return data
