from device.clickhouse_models import MeterData
from device.models import Meter
from django.conf import settings
from rest_framework import serializers


class MeterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Meter
        fields = '__all__'


class MeterDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeterData
        fields = '__all__'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data['data_arrival_time']:
            data['data_arrival_time'] = instance.data_arrival_time.strftime(settings.TIME_FORMAT_STRING)
        return data
