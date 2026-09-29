import json
import logging
from datetime import datetime

from api.utils import DEVICE_MONTHLY_REPORT_QUEUE_KEY
from api.viewsets.device_details_views import _generate_device_monthly_report_job
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django_redis import get_redis_connection

logger = logging.getLogger('django')


class Command(BaseCommand):
    help = 'Processes queued monthly report generation jobs.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--poll-timeout',
            type=int,
            default=5,
            help='Seconds to wait for a queued job before checking again.',
        )

    def handle(self, *args, **options):
        poll_timeout = max(1, int(options.get('poll_timeout') or 5))
        redis_connection = get_redis_connection('default')

        self.stdout.write(self.style.SUCCESS('Monthly report queue worker started'))
        try:
            while True:
                entry = redis_connection.blpop(DEVICE_MONTHLY_REPORT_QUEUE_KEY, timeout=poll_timeout)
                if entry is None:
                    continue

                _, raw_payload = entry
                if isinstance(raw_payload, bytes):
                    raw_payload = raw_payload.decode('utf-8')

                try:
                    payload = json.loads(raw_payload)
                except Exception as exc:
                    logger.exception('Dropping invalid monthly report job payload: %s', exc)
                    continue
                logger.info('Processing monthly report job: %s', payload)
                self._process_job(payload)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Monthly report queue worker stopped'))

    def _process_job(self, payload):
        close_old_connections()

        job_id = payload.get('job_id')
        device_id = payload.get('device_id')
        report_month = payload.get('report_month')
        force_refresh = bool(payload.get('force_refresh', False))

        if not job_id or not device_id or not report_month:
            logger.warning('Skipping invalid monthly report job payload: %s', payload)
            return

        try:
            _generate_device_monthly_report_job(job_id, device_id, report_month, force_refresh)
        except Exception as exc:
            logger.exception('Monthly report job failed for device %s: %s', device_id, exc)
        finally:
            close_old_connections()
