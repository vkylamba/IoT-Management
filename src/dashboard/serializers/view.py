from rest_framework import serializers
from dashboard.models import View


class ViewSerializer(serializers.ModelSerializer):
    class Meta:
        model = View
        fields = (
            'id',
            'view_type',
            'user',
            'device',
            'device_type',
            'active',
            'metadata',
            'updated_at',
        )
