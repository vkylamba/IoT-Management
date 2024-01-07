import importlib
from decimal import Decimal

from device.models import DevCommand, Device, DeviceType, Operator
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from event.models import Action, DeviceEvent, EventType


class Command(BaseCommand):

    """
        Command to check the device events and execute the actions.
    """

    help = 'Command to check the device events and execute the actions.'

    @transaction.atomic
    def handle(self, *args, **kwargs):

        time_now = timezone.now()
        
        actions = Action.objects.filter(
            device_event__typ__trigger_type='Time',
            active=True
        )
        for action in actions:
            if not action.device_event.active:
                continue
            last_trigger_time = action.device_event.last_trigger_time
            if last_trigger_time is None or (action.device_event.schedule is not None and action.device_event.schedule.schedule.is_due(last_trigger_time).is_due):
                if action.task:
                    temp_list = action.task.split('.')
                    import_module = '.'.join(temp_list[:-1])
                    func_name = temp_list[-1]
                    task_module = importlib.import_module(import_module)
                    task = getattr(task_module, func_name, False)
                    if task:
                        if action.args:
                            if action.kwargs:
                                task(action.id, *action.args, **action.kwargs)
                            else:
                                task(action.id, *action.args)
                        elif action.kwargs:
                            task(action.id, **action.kwargs)
                        else:
                            task(action.id)

                action.device_event.last_trigger_time = time_now
                action.device_event.save()
