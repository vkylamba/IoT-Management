import json
import logging

from api.utils import DEVICE_MONTHLY_REPORT_QUEUE_KEY
from api.viewsets.device_details_views import _update_monthly_report_job_status
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone
from django_redis import get_redis_connection
from utils.solar.monthly_report_job import generate_device_monthly_report_job

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
        parser.add_argument(
            '--purge',
            action='store_true',
            help='Delete all queued monthly report jobs and exit without starting the worker loop.',
        )

    def handle(self, *args, **options):
        poll_timeout = max(1, int(options.get('poll_timeout') or 5))
        redis_connection = get_redis_connection('default')

        if options.get('purge'):
            deleted = redis_connection.delete(DEVICE_MONTHLY_REPORT_QUEUE_KEY)
            self.stdout.write(self.style.SUCCESS(f'Monthly report queue purged. Removed {deleted} item(s).'))
            return

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
            _update_monthly_report_job_status(job_id, {
                'status': 'running',
                'message': 'Monthly report generation queued.',
                'month': report_month,
                'progress_percent': 0,
            })

            result = generate_device_monthly_report_job(
                device_pk=device_id,
                report_month=report_month,
                force_refresh=force_refresh,
                progress_callback=lambda progress_patch: _update_monthly_report_job_status(
                    job_id,
                    {
                        'status': 'running',
                        **progress_patch,
                    },
                ),
            )

            device = result['device']
            report_path = result['report_path']
            report_url = f"{settings.MEDIA_URL}device-reports/{report_path.parent.name}/{report_path.name}"

            if result['cached'] and not force_refresh:
                _update_monthly_report_job_status(job_id, {
                    'status': 'completed',
                    'message': 'Monthly report already cached.',
                    'month': report_month,
                    'device_id': str(device.pk),
                    'device_identifier': device.ip_address or device.alias or str(device.id),
                    'progress_percent': 100,
                    'cached': True,
                    'generated': False,
                    'url': report_url,
                    'daily_reports_generated': 0,
                    'missing_days': [],
                    'finished_at': timezone.now().isoformat(),
                })
                return

            _update_monthly_report_job_status(job_id, {
                'status': 'completed',
                'message': 'Monthly report generated successfully.',
                'month': report_month,
                'device_id': str(device.pk),
                'device_identifier': device.ip_address or device.alias or str(device.id),
                'cached': False,
                'generated': True,
                'progress_percent': 100,
                'url': report_url,
                'daily_reports_generated': result['daily_reports_generated'],
                'missing_days': result['missing_days'],
                'records_collected': result['records_collected'],
                'finished_at': timezone.now().isoformat(),
            })
        except Exception as exc:
            logger.exception('Monthly report job failed for device %s: %s', device_id, exc)
            _update_monthly_report_job_status(job_id, {
                'status': 'failed',
                'message': str(exc),
                'error': str(exc),
                'progress_percent': 100,
                'finished_at': timezone.now().isoformat(),
            })
        finally:
            close_old_connections()
