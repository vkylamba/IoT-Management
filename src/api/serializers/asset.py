from rest_framework import serializers

from asset.models import Asset, AssetAttribute, AssetBindingAgent, AssetType


class AssetTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetType
        fields = (
            'id',
            'owner',
            'name',
            'slug',
            'category',
            'description',
            'schema',
            'is_system',
            'active',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'owner', 'is_system', 'created_at', 'updated_at')


class AssetAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetAttribute
        fields = (
            'id',
            'asset',
            'key',
            'label',
            'value_type',
            'unit',
            'static_value',
            'source_type',
            'source_field',
            'source_template',
            'config',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


class AssetSerializer(serializers.ModelSerializer):
    attributes = AssetAttributeSerializer(many=True, read_only=True)

    class Meta:
        model = Asset
        fields = (
            'id',
            'owner',
            'asset_type',
            'parent',
            'code',
            'name',
            'description',
            'location',
            'boundary_geojson',
            'address',
            'metadata',
            'active',
            'created_at',
            'updated_at',
            'attributes',
        )
        read_only_fields = ('id', 'owner', 'created_at', 'updated_at', 'attributes')


class AssetBindingAgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetBindingAgent
        fields = (
            'id',
            'owner',
            'asset',
            'name',
            'devices',
            'sync_mode',
            'attribute_mapping_template',
            'active',
            'last_synced_at',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'owner', 'last_synced_at', 'created_at', 'updated_at')
