from django.contrib import admin
from django.contrib.auth.models import Permission
from django.contrib.auth import get_user_model

from device.models.device import *
from device.models import RawData, Meter

User = get_user_model()

class OperatorAdmin(admin.ModelAdmin):

    list_display = ('name', 'contact_number', 'avatar')


class DeviceAdmin(admin.ModelAdmin):

    list_display = ('id', 'ip_address', 'mac', 'Type', 'operator')

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
