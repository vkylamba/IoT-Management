from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from pymongo import MongoClient

from device.models import DeviceFirmware, Meter, RawData, UserDeviceType, StatusType
from device.models.device import *

User = get_user_model()

class OperatorAdmin(admin.ModelAdmin):
    ordering = ('name',)
    list_display = ('name', 'contact_number', 'avatar')
    list_filter = ('name',)


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
    return deleted


def delete_device_types(modeladmin, request, queryset):

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
    return deleted

class DeviceAdmin(admin.ModelAdmin):
    ordering = ('ip_address',)
    list_display = ('id', 'ip_address', 'mac', 'Type', 'operator')
    list_filter = ('ip_address', 'alias', 'id', 'mac')
    actions = [delete_devices]

    def Type(self, obj):

        return ", ".join(tpe.name for tpe in obj.types.all())

class DeviceTypeAdmin(admin.ModelAdmin):
    ordering = ('name',)
    list_display = ('id', 'name')
    list_filter = ('name', )
    actions = [delete_device_types]


class RawDataAdmin(admin.ModelAdmin):
    ordering = ('-data_arrival_time',)
    list_display = ('id', 'device', 'channel', 'data_type', 'data_arrival_time')
    list_filter = ('device__ip_address', 'device__alias', 'data_type', 'channel')

class CommandAdmin(admin.ModelAdmin):
    ordering = ('-command_in_time',)
    list_display = ('Device', 'status', 'command_in_time',
                    'command_read_time', 'command', 'param')
    list_filter = ('device__ip_address', 'device__alias', 'command', 'param')

    def Device(self, obj):

        return obj.device

class DeviceStatusAdmin(admin.ModelAdmin):
    ordering = ('-created_at',)
    list_display = ('id', 'name', 'device', 'created_at')
    list_filter = ('device__ip_address', 'name')


class MeterAdmin(admin.ModelAdmin):
    ordering = ('device__ip_address',)
    list_display = ('id', 'name', 'meter_type', 'Device')
    list_filter = ('device__ip_address', 'name', 'meter_type')

    def Device(self, obj):
        return obj.device


class DevicePropertyAdmin(admin.ModelAdmin):
    ordering = ('device__ip_address',)
    list_display = ('id', 'name', 'value', 'Device')
    list_filter = ('device__ip_address', 'name')

    def Device(self, obj):
        return obj.device


class DeviceEquipmentAdmin(admin.ModelAdmin):
    ordering = ('device__ip_address',)
    list_display = ('id', 'Device', 'meter_id', 'Equipment')
    list_filter = ('device__ip_address', 'equipment__name')

    def Device(self, obj):
        return obj.device

    def Equipment(self, obj):
        return obj.equipment


admin.site.register(DeviceType, DeviceTypeAdmin)
admin.site.register(Operator, OperatorAdmin)
admin.site.register(Device, DeviceAdmin)
admin.site.register(RawData, RawDataAdmin)
admin.site.register(Equipment)
admin.site.register(DeviceEquipment, DeviceEquipmentAdmin)
admin.site.register(DeviceProperty, DevicePropertyAdmin)
admin.site.register(User)
admin.site.register(DeviceStatus, DeviceStatusAdmin)
admin.site.register(Document)
admin.site.register(Meter, MeterAdmin)
admin.site.register(Command, CommandAdmin)
admin.site.register(DevCommand)
admin.site.register(Permission)
admin.site.register(DeviceFirmware)
admin.site.register(Subnet)


admin.site.register(UserDeviceType)
admin.site.register(StatusType)