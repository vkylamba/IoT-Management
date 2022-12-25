import os
import uuid

from django.db import models

from .device import DeviceType


def get_firmware_path(instance, filename):
    return os.path.join('device_firmware', str(instance.pk), filename)


class DeviceFirmware(models.Model):
    """
        model to store device firmware.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device_type = models.ForeignKey(DeviceType, blank=True, null=True, on_delete=models.CASCADE)
    document = models.FileField(
        upload_to=get_firmware_path,
        blank=True,
        null=True,
    )
    group_name = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )
    version = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )
    description = models.CharField(
        max_length=1024,
        blank=True,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = "device"
        verbose_name = "Device Firmware"
        verbose_name_plural = "Device Firmware"

    def __str__(self):
        owner = ''
        if self.device_type is not None:
            owner += self.device_type.name
        if self.group_name is not None:
            owner += ' ' + self.group_name
        return f"{owner} - {self.version}"
