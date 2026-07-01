from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission as AuthPermission
from django.contrib.admin.sites import NotRegistered
from pymongo import MongoClient
from typing import Any

from device.models import DeviceFirmware, Meter, RawData, UserDeviceType, StatusType, DeviceConfig
from device.models.device import *
from iot_server.admin_utils import DjongoSafeModelAdmin

User = get_user_model()


class DisableAdminLogMixin:
    def log_addition(self, request, object, message) -> Any:
        return None

    def log_change(self, request, object, message) -> Any:
        return None

    def log_deletion(self, request, object, object_repr) -> Any:
        return None


class SafeDeviceAdminMixin(DisableAdminLogMixin, DjongoSafeModelAdmin):
    pass

def delete_devices(modeladmin, request, queryset):

    db_config = settings.DATABASES['default']
    
    if db_config.get('ENGINE') != 'djongo':
        raise Exception('Not mongodb!')
    
    db_name = db_config.get('NAME')
    db_host = db_config.get('CLIENT', {}).get('host')

    deleted = 0
    if db_name and db_host:
        client = MongoClient(db_host)
        db = client[db_name]
        db_table_name = queryset.model._meta.db_table
        db_table = db[db_table_name]
        for obj in queryset:
            result = db_table.delete_many({'id': obj.id})
            deleted += result.deleted_count
    modeladmin.message_user(request, f'Deleted {deleted} device records.')
    return None


class DocumentInline(admin.TabularInline):
    model = AssetDocument
    extra = 0
    can_delete = False

class MeterInline(admin.TabularInline):
    model = Meter
    extra = 0
    can_delete = False

class DeviceEquipmentInline(admin.TabularInline):
    model = DeviceEquipment
    extra = 0
    can_delete = False

class DevicePropertyInline(admin.TabularInline):
    model = DeviceProperty
    extra = 0
    can_delete = False

class DeviceConfigInline(admin.TabularInline):
    model = DeviceConfig
    extra = 0
    can_delete = False

class DeviceAdmin(SafeDeviceAdminMixin):
    ordering = ('ip_address',)
    list_display = ('id', 'ip_address', 'alias', 'mac', 'device_type', 'active', 'created_at')
    list_filter = ('ip_address', 'alias', 'id', 'mac', 'active', 'created_at')
    search_fields = ('ip_address', 'alias', 'mac')
    actions = [delete_devices]
    inlines = [DocumentInline, MeterInline, DeviceEquipmentInline, DevicePropertyInline, DeviceConfigInline]

class RawDataAdmin(SafeDeviceAdminMixin):
    ordering = ('-data_arrival_time',)
    list_display = ('id', 'device', 'channel', 'data_type', 'data_arrival_time')
    list_filter = ('device__ip_address', 'device__alias', 'data_type', 'channel')

class CommandAdmin(SafeDeviceAdminMixin):
    ordering = ('-command_in_time',)
    list_display = ('Device', 'status', 'command_in_time',
                    'command_read_time', 'command', 'param')
    list_filter = ('device__ip_address', 'device__alias', 'command', 'param')

    def Device(self, obj):

        return obj.device

class AssetStatusAdmin(SafeDeviceAdminMixin):
    ordering = ('-created_at',)
    list_display = ('id', 'name', 'device', 'asset', 'created_at')
    list_filter = ('device__ip_address', 'asset__name', 'name')


class MeterAdmin(SafeDeviceAdminMixin):
    ordering = ('device__ip_address',)
    list_display = ('id', 'name', 'meter_type', 'Device')
    list_filter = ('device__ip_address', 'name', 'meter_type')

    def Device(self, obj):
        return obj.device


class DevicePropertyAdmin(SafeDeviceAdminMixin):
    ordering = ('device__ip_address',)
    list_display = ('id', 'name', 'value', 'Device')
    list_filter = ('device__ip_address', 'name')

    def Device(self, obj):
        return obj.device


class DeviceEquipmentAdmin(SafeDeviceAdminMixin):
    ordering = ('device__ip_address',)
    list_display = ('id', 'Device', 'meter_id', 'Equipment')
    list_filter = ('device__ip_address', 'equipment__name')

    def Device(self, obj):
        return obj.device.ip_address
    
    def Equipment(self, obj):
        return obj.equipment.name


class StatusTypeAdmin(SafeDeviceAdminMixin):
    ordering = ('name',)
    list_display = ('id', 'name', 'target_type', 'user', 'device', 'device_type', 'update_trigger')
    list_filter = ('name', 'target_type', 'user', 'device', 'device_type', 'update_trigger')


class UserDeviceTypeAdmin(SafeDeviceAdminMixin):
    ordering = ('name',)
    list_display = ('id', 'name', 'code', 'user', 'identifier_field')
    list_filter = ('name', 'code', 'user', 'identifier_field')
    


class DeviceConfigAdmin(SafeDeviceAdminMixin):
    ordering = ('updated_at',)
    list_display = ('id', 'device', 'group_name', 'version', 'active', 'created_at', 'updated_at')
    list_filter = ('device', 'group_name', 'active')


admin.site.register(Device, DeviceAdmin)
admin.site.register(RawData, RawDataAdmin)
admin.site.register(Equipment, DjongoSafeModelAdmin)
admin.site.register(DeviceEquipment, DeviceEquipmentAdmin)
admin.site.register(DeviceProperty, DevicePropertyAdmin)


class UserAdmin(SafeDeviceAdminMixin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser')
    list_filter = ('is_staff', 'is_superuser', 'is_active')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    filter_horizontal = ('permissions', 'groups', 'user_permissions')


admin.site.register(User, UserAdmin)
admin.site.register(AssetStatus, AssetStatusAdmin)
admin.site.register(AssetDocument, DjongoSafeModelAdmin)
admin.site.register(Meter, MeterAdmin)
admin.site.register(Command, CommandAdmin)
admin.site.register(Permission, DjongoSafeModelAdmin)
admin.site.register(DeviceFirmware, DjongoSafeModelAdmin)
admin.site.register(Subnet, DjongoSafeModelAdmin)


admin.site.register(DeviceConfig, DeviceConfigAdmin)
admin.site.register(UserDeviceType, UserDeviceTypeAdmin)
admin.site.register(StatusType, StatusTypeAdmin)

for auth_model in (Group, AuthPermission):
    try:
        admin.site.unregister(auth_model)
    except NotRegistered:
        continue
    admin.site.register(auth_model, DjongoSafeModelAdmin)