from django.contrib import admin

from asset.models import Asset, AssetAttribute, AssetBindingAgent, AssetType


@admin.register(AssetType)
class AssetTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'category', 'is_system', 'active', 'created_at')
    list_filter = ('category', 'is_system', 'active')
    search_fields = ('name', 'slug')


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('name', 'asset_type', 'owner', 'parent', 'active', 'created_at')
    list_filter = ('active', 'asset_type')
    search_fields = ('name', 'code')


@admin.register(AssetAttribute)
class AssetAttributeAdmin(admin.ModelAdmin):
    list_display = ('asset', 'key', 'value_type', 'unit', 'source_type', 'source_field', 'updated_at')
    list_filter = ('value_type', 'source_type')
    search_fields = ('asset__name', 'key', 'label')


@admin.register(AssetBindingAgent)
class AssetBindingAgentAdmin(admin.ModelAdmin):
    list_display = ('name', 'asset', 'sync_mode', 'active', 'last_synced_at')
    list_filter = ('sync_mode', 'active')
    filter_horizontal = ('devices',)
    search_fields = ('name', 'asset__name')
