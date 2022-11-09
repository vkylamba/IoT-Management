from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from django.utils import timezone

from device.models import (
    DeviceType,
    Operator,
    Device,
    DevCommand,
)

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

DeviceCommands = (
    ('0', 'No Command'),
    ('1', 'Send Data'),
    ('2', 'Turn On'),
    ('3', 'Turn Off'),
    ('4', 'Set Operator'),
    ('5', 'Set Data APN'),
    ('6', 'Set Data Username'),
    ('7', 'Set Data Password'),
    ('8', 'Set Data Server'),
    ('9', 'Set Data Path'),
    ('10', 'Tell Location'),
    ('11', 'Set Time'),
    ('12', 'Set Data Frequency')
)


class Command(BaseCommand):

    """
        Command to load commands data into database.
    """

    help = 'Loads initial data set into database.'

    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument('device_ip', nargs='+', type=str)

    @transaction.atomic
    def handle(self, *args, **kwargs):

        device_ip = kwargs.get('device_ip')[0]

        for each_command in DeviceCommands:
            command, created = DevCommand.objects.get_or_create(
                command_name=each_command[1]
            )
            if created:
                command.command_code = each_command[0]
                command.save()

        device = self.create_sample_device(device_ip)
        self.create_event_types()
        self.attach_events_to_device(device)

        # template_contexts = self.create_template_context()
        # self.create_notifications(template_contexts)
        # self.attach_actions_to_events(device)

    def create_sample_device(self, device_ip):
        """
            Method to load sample events for a device.
        """
        # Check if the device exists
        device, created = Device.objects.get_or_create(ip_address=device_ip)
        if created:
            device.save()
            # Create a device type
            device_type = DeviceType(
                name='Sample Device Type',
                details="Sample Device"
            )
            device_type.save()
            device.types.add(device_type)
            device.installation_date = timezone.now().date()

            # Create an operator
            operator = Operator(
                name=device_ip + " operator",
                address="Address",
                pin_code="00000",
                contact_number="0000000000"
            )
            operator.save()
            device.operator = operator

            print("Created device {}".format(device.ip_address))
            device.save()
            

            for each_command in DevCommand.objects.all():
                device.commands.add(each_command)

        return device

    def create_event_types(self):
        """
            Method to create sample event types.
            Events are: Overload, Scheduled alarm, Daily Report,
        """
        events = [
            {
                "name": "Overload",
                "description": "Event fires on overload. The threshold is defined separately for each device.",
                "type": "Data",
                "equation": "power_val/1000"
            },
            {
                "name": "Daily Report",
                "description": "Event fires on scheduled time. It can generate a report for each device.",
                "type": "Time",
                "equation": None
            },
            {
                "name": "No Data Check",
                "description": "Event fires on the scheduled time, and checks for data availability. Time is defined for each device.",
                "type": "Time",
                "equation": "(time_now - data.data_arrival_time).days"
            },
            {
                "name": "Scheduled alarm",
                "description": "Event fires on the scheduled time. Time is defined for each device.",
                "type": "Time",
                "equation": None
            },
            {
                "name": "Forward data",
                "description": "Event fires whenever a new data point arrives. It forwards the data to another server.",
                "type": "Data",
                "equation": '"device_val"'
            },
        ]
        for event in events:
            event_type, created = EventType.objects.get_or_create(
                name=event.get('name')
            )
            if created:
                event_type.description = event.get('description')
                event_type.trigger_type = event.get('type')
                event_type.equation = event.get('equation')
                event_type.save()
            print("Cretaed event type {}".format(event_type.name))

    def attach_events_to_device(self, device):
        """
            Method to attach events to device.
        """
        schedule_event1 = CrontabSchedule(
            minute=1,
            hour=7,
        )
        schedule_event1.save()
        schedule_event2 = CrontabSchedule(
            minute=1,
            hour='*',
        )
        schedule_event2.save()

        events = {
            "Overload": {
                "equation_threshold": '100.0',
                "schedule": None
            },
            "Daily Report": {
                "equation_threshold": None,
                "schedule": schedule_event1
            },
            "Scheduled alarm": {
                "equation_threshold": None,
                "schedule": schedule_event2
            },
            "No Data Check": {
                "equation_threshold": '2.0',
                "schedule": schedule_event2
            },
            "Forward data": {
                "equation_threshold": '0.0.0.11',
                "schedule": None
            },
            "Forward data to Emon": {
                "equation_threshold": '0.0.0.11',
                "schedule": None
            }
        }

        event_types = EventType.objects.all()
        for event_type in event_types:
            if event_type.name in events:
                threshold = events[event_type.name].get("equation_threshold")
                if event_type.name in events:
                    device_event = DeviceEvent(
                        typ=event_type,
                        device=device,
                        equation_threshold=threshold,
                    )
                    schedule=events[event_type.name].get("schedule")
                    device_event.schedule = schedule
                    device_event.save()
                print("Attached event {} to device {}".format(event_type.name, device.ip_address))
