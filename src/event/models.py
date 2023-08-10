import logging
import uuid

from device.models import Command, DevCommand, Device
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule
from utils.time_and_space import is_number

User = get_user_model()
logger = logging.getLogger('django')

# Create your models here.

event_triggering = (
    ('Data', 'Data triggered event.'),
    ('Time', 'Time triggered event.'),
)


class EventType(models.Model):
    """
        Event Type model.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, help_text="Event type name")
    description = models.TextField(help_text='Description')
    trigger_type = models.CharField(max_length=20, choices=event_triggering)
    equation = models.TextField(max_length=255, help_text='Trigger equation', null=True, blank=True)

    class Meta:
        verbose_name_plural = 'Event types'

    def __str__(self):
        return self.name


class DeviceEvent(models.Model):
    """
        Device events model
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    typ = models.ForeignKey(EventType, on_delete=models.CASCADE)
    device = models.ForeignKey(Device, related_name='events', blank=True, null=True, on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='events', blank=True, null=True, on_delete=models.CASCADE)
    equation_threshold = models.CharField(max_length=255, help_text='Threshold value for the event equations', null=True, blank=True)
    schedule = models.ForeignKey(CrontabSchedule, null=True, blank=True, on_delete=models.CASCADE)
    last_trigger_time = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name_plural = 'Device events'

    def __str__(self):
        return "{dev} - {typ}".format(dev=self.device.ip_address if self.device else self.user.user.username, typ=self.typ.name)

    def eval_equation(self, data=None):
        event_typ = self.typ
        equation = event_typ.equation
        if equation == "":
            return True
        data_members = [attr for attr in dir(data) if not callable(attr) and not attr.startswith("__")]
        logger.info("Equation is {}".format(equation))
        time_now = timezone.now()
        for data_member in data_members:
            if data_member in equation:
                data_member_val = eval('data.{attr}'.format(attr=data_member))
                equation = equation.replace("{}_val".format(data_member), str(data_member_val))

        logger.info("Transformed Equation is {}".format(equation))
        result = eval(equation)
        logger.info("Result of the equation is {}".format(result))

        result_is_number, result = is_number(result)
        threshold_is_number, threshold = is_number(self.equation_threshold)
        if result_is_number and threshold_is_number:
            if result - threshold > 0:
                return True
        elif threshold is None:
            return True
        elif result is not None:
            target_type = type(result)
            logger.critical("data type of result {} is {}".format(result, target_type))
            # Convert the threshold into data type of result
            threshold = target_type(threshold)
            if result == threshold:
                return True
        return False

class Action(models.Model):
    """
        Action model
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    device_event = models.ForeignKey(DeviceEvent, on_delete=models.CASCADE)
    device_command = models.ForeignKey(DevCommand, blank=True, null=True, on_delete=models.CASCADE)

    task = models.CharField(
        max_length=200,
        blank=True, null=True,
        verbose_name='Task Name',
        help_text=('The Name of the Celery Task that Should be Run.  '
                    '(Example: "proj.tasks.import_contacts")'),
    )
    
    args = models.JSONField(
        blank=True, null=True,
        verbose_name=('Positional Arguments'),
        help_text=(
            'JSON encoded positional arguments '
            '(Example: ["arg1", "arg2"])'),
    )
    kwargs = models.JSONField(
        blank=True, null=True,
        verbose_name=('Keyword Arguments'),
        help_text=(
            'JSON encoded keyword arguments '
            '(Example: {"argument": "value"})'),
    )
    
    class Meta:
        verbose_name_plural = 'Actions'

    def __str__(self):
        return "{name} - {dev_event}".format(name=self.name, dev_event=self.device_event)

class EventHistory(models.Model):
    """
        Event history model.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device_event = models.ForeignKey(DeviceEvent, on_delete=models.CASCADE)
    trigger_time = models.DateTimeField(auto_now_add=True)
    
    action = models.ForeignKey(Action, blank=True, null=True, on_delete=models.CASCADE)
    result = models.JSONField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = 'Events history'

    def __str__(self):
        return "{dev} - {typ} - {time}".format(
            dev=self.device_event.device.ip_address,
            typ=self.device_event.typ.name,
            time=self.trigger_time.strftime("%d-%m-%Y %H:%M:%S")
        )
