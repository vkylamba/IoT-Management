from django.contrib import admin
from django.contrib.auth.models import Permission
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from device.models import *

User = get_user_model()
admin.site.register(DeviceType)


class OperatorAdmin(admin.ModelAdmin):

    list_display = ('name', 'contact_number', 'avatar')


admin.site.register(Operator, OperatorAdmin)


class DeviceAdmin(admin.ModelAdmin):

    list_display = ('ip_address', 'Type', 'operator')

    def Type(self, obj):

        return ", ".join(tpe.name for tpe in obj.types.all())


admin.site.register(Device, DeviceAdmin)
admin.site.register(Equipment)
admin.site.register(DeviceEquipment)
admin.site.register(DeviceProperty)
admin.site.register(User)
admin.site.register(DeviceStatus)
admin.site.register(Document)

class CommandAdmin(admin.ModelAdmin):

    list_display = ('Device', 'status', 'command_in_time',
                    'command_read_time', 'command', 'param')

    def Device(self, obj):

        return obj.device


admin.site.register(Command, CommandAdmin)


admin.site.register(DevCommand)
admin.site.register(Permission)
