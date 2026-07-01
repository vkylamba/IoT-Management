import uuid

from django.conf import settings
from django.db import models


class AssetType(models.Model):
    """
    User-defined or system-defined types for assets.
    """

    CATEGORY_FARM = 'farm'
    CATEGORY_FIELD = 'field'
    CATEGORY_ZONE = 'zone'
    CATEGORY_STORAGE = 'storage'
    CATEGORY_INFRA = 'infrastructure'
    CATEGORY_SENSOR_GROUP = 'sensor_group'
    CATEGORY_CUSTOM = 'custom'

    TYPE_CATEGORIES = (
        (CATEGORY_FARM, 'Farm'),
        (CATEGORY_FIELD, 'Field'),
        (CATEGORY_ZONE, 'Zone'),
        (CATEGORY_STORAGE, 'Storage'),
        (CATEGORY_INFRA, 'Infrastructure'),
        (CATEGORY_SENSOR_GROUP, 'Sensor Group'),
        (CATEGORY_CUSTOM, 'Custom'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='asset_types',
        help_text='If null and is_system=True, the type is globally available.'
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120)
    category = models.CharField(max_length=40, choices=TYPE_CATEGORIES, default=CATEGORY_CUSTOM)
    description = models.TextField(blank=True, null=True)
    schema = models.JSONField(blank=True, null=True, help_text='Optional JSON schema for type-level defaults/validation.')
    is_system = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'asset'
        verbose_name = 'Asset Type'
        verbose_name_plural = 'Asset Types'
        constraints = [
            models.UniqueConstraint(fields=['owner', 'slug'], name='unique_asset_type_slug_per_owner')
        ]

    def __str__(self):
        return self.name


class Asset(models.Model):
    """
    Hierarchical asset model to represent Farm -> Field -> Zone -> Sensor groups.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assets'
    )
    asset_type = models.ForeignKey(
        AssetType,
        on_delete=models.PROTECT,
        related_name='assets'
    )
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='children'
    )

    code = models.CharField(max_length=80, blank=True, null=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    # Spatial modeling support
    location = models.JSONField(blank=True, null=True, help_text='Point-like object e.g. {"lat": 0, "lng": 0}.')
    boundary_geojson = models.JSONField(blank=True, null=True, help_text='GeoJSON polygon/multipolygon for field/zone boundaries.')
    address = models.TextField(blank=True, null=True)

    metadata = models.JSONField(blank=True, null=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'asset'
        verbose_name = 'Asset'
        verbose_name_plural = 'Assets'
        constraints = [
            models.UniqueConstraint(fields=['owner', 'code'], name='unique_asset_code_per_owner')
        ]

    def __str__(self):
        return self.name


class AssetAttribute(models.Model):
    """
    Flexible attributes attached to an asset, with optional mapping to device datasets.
    """

    VALUE_STRING = 'string'
    VALUE_INT = 'int'
    VALUE_FLOAT = 'float'
    VALUE_BOOL = 'bool'
    VALUE_JSON = 'json'
    VALUE_DATE = 'date'
    VALUE_DATETIME = 'datetime'

    VALUE_TYPES = (
        (VALUE_STRING, 'String'),
        (VALUE_INT, 'Integer'),
        (VALUE_FLOAT, 'Float'),
        (VALUE_BOOL, 'Boolean'),
        (VALUE_JSON, 'JSON'),
        (VALUE_DATE, 'Date'),
        (VALUE_DATETIME, 'DateTime'),
    )

    SOURCE_STATIC = 'static'
    SOURCE_DEVICE_STATUS = 'device_status'
    SOURCE_RAW_DATA = 'raw_data'
    SOURCE_METER_DATA = 'meter_data'
    SOURCE_TEMPLATE = 'template'

    SOURCE_TYPES = (
        (SOURCE_STATIC, 'Static'),
        (SOURCE_DEVICE_STATUS, 'Device Status'),
        (SOURCE_RAW_DATA, 'Raw Data'),
        (SOURCE_METER_DATA, 'Meter Data'),
        (SOURCE_TEMPLATE, 'Template'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='attributes')

    key = models.CharField(max_length=120)
    label = models.CharField(max_length=120, blank=True, null=True)
    value_type = models.CharField(max_length=20, choices=VALUE_TYPES, default=VALUE_STRING)
    unit = models.CharField(max_length=30, blank=True, null=True)

    # One of static value or computed value via source/template.
    static_value = models.JSONField(blank=True, null=True)

    source_type = models.CharField(max_length=30, choices=SOURCE_TYPES, default=SOURCE_STATIC)
    source_field = models.CharField(max_length=120, blank=True, null=True, help_text='Field name in mapped source model/table.')
    source_template = models.TextField(
        blank=True,
        null=True,
        help_text='Template string for derived values, e.g. {{meter.power}}/{{status.current}}.'
    )

    config = models.JSONField(blank=True, null=True, help_text='Optional parser/transform configuration.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'asset'
        verbose_name = 'Asset Attribute'
        verbose_name_plural = 'Asset Attributes'
        constraints = [
            models.UniqueConstraint(fields=['asset', 'key'], name='unique_asset_attribute_key')
        ]

    def __str__(self):
        return f'{self.asset.name}::{self.key}'


class AssetBindingAgent(models.Model):
    """
    Defines how devices are bound to an asset and how attributes pull from data sources.
    """

    SYNC_ON_READ = 'on_read'
    SYNC_PERIODIC = 'periodic'
    SYNC_MANUAL = 'manual'

    SYNC_MODES = (
        (SYNC_ON_READ, 'On Read'),
        (SYNC_PERIODIC, 'Periodic'),
        (SYNC_MANUAL, 'Manual'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='asset_agents')
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='agents')
    name = models.CharField(max_length=150)

    devices = models.ManyToManyField('device.Device', related_name='asset_binding_agents', blank=True)

    sync_mode = models.CharField(max_length=20, choices=SYNC_MODES, default=SYNC_ON_READ)
    attribute_mapping_template = models.JSONField(
        blank=True,
        null=True,
        help_text='Optional mapping config linking attribute keys to device status/raw/meter paths.'
    )

    active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'asset'
        verbose_name = 'Asset Binding Agent'
        verbose_name_plural = 'Asset Binding Agents'
        constraints = [
            models.UniqueConstraint(fields=['owner', 'asset', 'name'], name='unique_asset_agent_name_per_asset_owner')
        ]

    def __str__(self):
        return f'{self.asset.name}::{self.name}'
