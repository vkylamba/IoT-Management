import uuid

from django.db import models
from django_celery_beat.models import CrontabSchedule


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


STATUS_TARGET_TYPES = (
    ('meter', 'meter'),
    ('user', 'user'),
    ('alarm', 'alarm'),
    ('device', 'device'),
    ('report', 'report'),
)

STATUS_UPDATE_TRIGGER = (
    ('data', 'Data'),
    ('schedule', 'Schedule'),
    ('data/schedule', 'Data and Schedule'),
)
class StatusType(models.Model):
    """
        model to store status types.
    """
    STATUS_TARGET_METER = 'meter'
    STATUS_TARGET_USER = 'user'
    STATUS_TARGET_ALARM = 'alarm'
    STATUS_TARGET_DEVICE = 'device'
    STATUS_TARGET_REPORT = 'report'

    STATUS_UPDATE_TRIGGER_DATA = 'data'
    STATUS_UPDATE_TRIGGER_SCHEDULE = 'schedule'
    STATUS_UPDATE_TRIGGER_ANY = 'any'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, help_text='Type name')
    user = models.ForeignKey('User', blank=True, null=True, on_delete=models.DO_NOTHING)
    device = models.ForeignKey('Device', blank=True, null=True, on_delete=models.DO_NOTHING)
    device_type = models.ForeignKey('UserDeviceType', blank=True, null=True, on_delete=models.DO_NOTHING)
    target_type = models.CharField(max_length=255, choices=STATUS_TARGET_TYPES, help_text='Resulting status type')
    update_trigger = models.CharField(max_length=255, choices=STATUS_UPDATE_TRIGGER, help_text='Status update trigger')
    schedule = models.ForeignKey(CrontabSchedule, null=True, blank=True, on_delete=models.CASCADE)
    last_trigger_time = models.DateTimeField(null=True, blank=True)
    translation_schema = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)

    class Meta:
        app_label = "device"
        verbose_name = "Status Type"
        verbose_name_plural = "Status Types"

    def __str__(self):
        return f"{self.name} - {self.active}"
