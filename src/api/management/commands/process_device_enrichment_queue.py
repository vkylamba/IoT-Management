import json
import logging
from datetime import datetime

from api.utils import DEVICE_ENRICHMENT_QUEUE_KEY
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django_redis import get_redis_connection

from device.models import Device, Meter
from utils import detect_and_save_meter_loads

logger = logging.getLogger('django')


class Command(BaseCommand):
    help = 'Processes queued device enrichment jobs.'

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

        self.stdout.write(self.style.SUCCESS('Device enrichment queue worker started'))
        try:
            while True:
                entry = redis_connection.blpop(DEVICE_ENRICHMENT_QUEUE_KEY, timeout=poll_timeout)
                if entry is None:
                    continue

                _, raw_payload = entry
                if isinstance(raw_payload, bytes):
                    raw_payload = raw_payload.decode('utf-8')

                try:
                    payload = json.loads(raw_payload)
                except Exception as exc:
                    logger.exception('Dropping invalid enrichment job payload: %s', exc)
                    continue

                self._process_job(payload)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Device enrichment queue worker stopped'))

    def _process_job(self, payload):
        close_old_connections()

        device_id = payload.get('device_id')
        device = Device.objects.filter(pk=device_id).first()
        if device is None:
            logger.warning('Skipping enrichment job for missing device %s', device_id)
            return

        meter_entries = payload.get('meters') or []
        meter_ids = [entry.get('meter_id') for entry in meter_entries if entry.get('meter_id')]
        meters_by_id = {
            str(meter.pk): meter
            for meter in Meter.objects.filter(pk__in=meter_ids)
        }

        meters_and_data = []
        for meter_entry in meter_entries:
            meter = meters_by_id.get(str(meter_entry.get('meter_id')))
            if meter is None:
                continue

            meter_data = dict(meter_entry.get('data') or {})
            meter_data['meter'] = meter
            meters_and_data.append({
                'meter': meter,
                'data': meter_data,
            })

        if not meters_and_data:
            logger.debug('Skipping empty enrichment job for device %s', device_id)
            return

        data_arrival_time_raw = payload.get('data_arrival_time')
        data_arrival_time = None
        if data_arrival_time_raw:
            try:
                data_arrival_time = datetime.fromisoformat(data_arrival_time_raw)
            except Exception:
                data_arrival_time = None

        try:
            detect_and_save_meter_loads(device, meters_and_data, data_arrival_time)
        except Exception as exc:
            logger.exception('Enrichment job failed for device %s: %s', device_id, exc)
        finally:
            close_old_connections()