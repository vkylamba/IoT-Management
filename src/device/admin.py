from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from pymongo import MongoClient

from device.models import DeviceFirmware, Meter, RawData
from device.models.device import *

User = get_user_model()

class OperatorAdmin(admin.ModelAdmin):

    list_display = ('name', 'contact_number', 'avatar')


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
            result = db_table.delete_many({'alias': obj.alias})
            deleted += result.deleted_count
    return deleted

class DeviceAdmin(admin.ModelAdmin):

    list_display = ('id', 'ip_address', 'mac', 'Type', 'operator')
    actions = [delete_devices]

    def Type(self, obj):

        return ", ".join(tpe.name for tpe in obj.types.all())

class RawDataAdmin(admin.ModelAdmin):

    list_display = ('id', 'device', 'data_arrival_time')

class CommandAdmin(admin.ModelAdmin):

    list_display = ('Device', 'status', 'command_in_time',
                    'command_read_time', 'command', 'param')

    def Device(self, obj):

        return obj.device


admin.site.register(DeviceType)
admin.site.register(Operator, OperatorAdmin)
admin.site.register(Device, DeviceAdmin)
admin.site.register(RawData, RawDataAdmin)
admin.site.register(Equipment)
admin.site.register(DeviceEquipment)
admin.site.register(DeviceProperty)
admin.site.register(User)
admin.site.register(DeviceStatus)
admin.site.register(Document)
admin.site.register(Meter)
admin.site.register(Command, CommandAdmin)
admin.site.register(DevCommand)
admin.site.register(Permission)
admin.site.register(DeviceFirmware)
