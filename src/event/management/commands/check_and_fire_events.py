import importlib
from decimal import Decimal

from device.models import Device
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from event.models import Action, DeviceEvent, EventType
from utils.reports.report_helpers import get_latest_report_data_for_period


REPORT_TASK_TO_PERIOD = {
    'event.tasks.daily_energy_report': 'yesterday',
    'event.tasks.weekly_energy_report': 'week',
    'event.tasks.monthly_energy_report': 'month',
}


def _should_bootstrap_report_status(action):
    period = REPORT_TASK_TO_PERIOD.get(action.task)
    if period is None:
        return False

    device_event = action.device_event
    if device_event is None or device_event.device is None:
        return False

    return get_latest_report_data_for_period(device_event.device, period) is None


class Command(BaseCommand):

    """
        Command to check the device events and execute the actions.
    """

    help = 'Command to check the device events and execute the actions.'

    @transaction.atomic
    def handle(self, *args, **kwargs):

        time_now = timezone.now()
        
        actions = Action.objects.filter(
            device_event__typ__trigger_type='Time'
        )
        for action in actions:
            if not action.active or not action.device_event.active:
                continue
            last_trigger_time = action.device_event.last_trigger_time
            should_bootstrap_report = _should_bootstrap_report_status(action)
            if last_trigger_time is None or should_bootstrap_report or (action.device_event.schedule is not None and action.device_event.schedule.schedule.is_due(last_trigger_time).is_due):
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
