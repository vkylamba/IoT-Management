import uuid

from django.db import models


class UserDeviceType(models.Model):
    """
        To store user specific device type details.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=255,
        help_text='Type name'
    )
    code = models.CharField(
        max_length=255,
        help_text='Type code'
    )
    user = models.ForeignKey('User', blank=True, null=True, on_delete=models.DO_NOTHING)
    identifier_field = models.CharField(
        max_length=50,
        help_text='Field in the data schema to identify the device to which the data belongs to'
    )
    details = models.TextField(blank=True, null=True)
    data_schema = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)
    
    class Meta:
        app_label = "device"
        verbose_name = "User Device Type"
        verbose_name_plural = "User Device Types"

    def __str__(self):
        return f"{self.code}-{self.user}"


class StatusType(models.Model):
    """
        model to store status types.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, help_text='Type name')
    code = models.CharField(max_length=255, help_text='Type code')
    user = models.ForeignKey('User', blank=True, null=True, on_delete=models.DO_NOTHING)
    device = models.ForeignKey('Device', blank=True, null=True, on_delete=models.DO_NOTHING)
    device_type = models.ForeignKey('UserDeviceType', blank=True, null=True, on_delete=models.DO_NOTHING)
    translation_schema = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)

    class Meta:
        app_label = "device"
        verbose_name = "Status Type"
        verbose_name_plural = "Status Types"

    def __str__(self):
        return f"{self.name} - {self.active}"
