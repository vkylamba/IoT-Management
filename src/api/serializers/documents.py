from rest_framework import serializers
from device.models import AssetDocument

class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetDocument
        fields = '__all__'