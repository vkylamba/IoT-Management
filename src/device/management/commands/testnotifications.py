from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from django.utils import timezone

from device.models.device import (
    DeviceType,
    Operator,
    Device,
    DevCommand,
    Data
)
from django.contrib.auth.models import User

from django_celery_beat.models import CrontabSchedule
from django_celery_beat.models import (
    PeriodicTask,
)

from event.models import (
    Action,
    DeviceEvent,
    EventType
)

from notification.models import (
    TemplateContext,
    Notification,
)


class Command(BaseCommand):

    """
        Command to load commands data into database.
    """

    help = 'Test events command'

    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument('device_ip', nargs='+', type=str)
        parser.add_argument('event_type', nargs='+', type=str)

    @transaction.atomic
    def handle(self, *args, **kwargs):
        device_ip = kwargs.get('device_ip')[1]
        event_type = kwargs.get('event_type')[0]
        # Get the device
        device = Device.objects.get(ip_address=device_ip)

        if event_type == 'data':
            last_data = device.get_last_data_point()

            # Create a data object
            voltage = int(input('Enter voltage value(dV): '))
            current = int(input('Enter current value(cA): '))
            time = int(input('Enter time value(in secs): '))
            state = int(input('Enter state value: '))
            latitude = input('Enter latitude value: ')
            longitude = input('Enter longitude value: ')
            power = voltage * current
            device_data = Data(
                device=device,
                voltage=voltage,
                current=current,
                power=power,
                energy=last_data.energy + (power * time / 1000),
                runtime=last_data.runtime + time,
                state=state,
                latitude=latitude,
                longitude=longitude
            )
            device_data.save()
        elif event_type == 'time':
            # Get available events for this device
            dev_events = DeviceEvent.objects.filter(device=device)
            print("Available events for this device are: ")
            for i, dev_event in enumerate(dev_events):
                print("{}-{}".format(i, dev_event))
            selected_event = int(input("Enter event number to fire: "))
            dev_events[selected_event].trigger_events()
