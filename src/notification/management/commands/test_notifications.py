from django.core.management.base import BaseCommand

from api.models import ClientDevice
import sys


class Command(BaseCommand):

    """
        Command to load initial data into database.
    """

    help = 'Sends push notification to devices.'

    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument('message', nargs='+', type=str)

        # Named (optional) arguments
        parser.add_argument(
            '--user',
            default='',
            help='username',
        )

    def handle(self, *args, **options):

        username = options.get('user', None)
        message = options.get('message')

        if not message:
            sys.exit("Message not provided.")

        message = {
            "subject": "Test message",
            "message": message,
        }

        if username:
            devices = ClientDevice.objects.filter(user__username=username)
        else:
            devices = ClientDevice.objects.all()
        for device in devices:
            device.send(data=message)
