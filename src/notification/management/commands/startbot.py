import logging

from django.core.management.base import BaseCommand
from utils.telegram_bot.bot import start_bot, stop_bot

logger = logging.getLogger('django')
class Command(BaseCommand):

    """
        Command to start telegram bot.
    """

    help = 'Starts the telegram bot.'

    def handle(self, *args, **options):
        try:
            start_bot()
        except Exception as ex:
            logger.exception(ex)
            stop_bot()
