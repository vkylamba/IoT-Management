from datetime import datetime, time, timedelta
from uuid import UUID

import pytz
from api.utils import replay_stored_raw_data
from device.models import Device, User
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone


class Command(BaseCommand):
    help = 'Reprocess status calculations from stored raw data for a device and time range.'

    def add_arguments(self, parser):
        parser.add_argument('device_id', type=str)

        range_group = parser.add_mutually_exclusive_group(required=True)
        range_group.add_argument(
            '--day',
            type=str,
            help='Device-local day to rebuild in YYYY-MM-DD format.',
        )
        range_group.add_argument(
            '--start',
            type=str,
            help='UTC or ISO timestamp marking the start of the rebuild window.',
        )

        parser.add_argument(
            '--end',
            type=str,
            help='UTC or ISO timestamp marking the end of the rebuild window. Required with --start.',
        )
        parser.add_argument(
            '--user-id',
            type=str,
            help='Optional user id for user-scoped status types. Defaults to device.device_type.user when available.',
        )
        parser.add_argument(
            '--keep-existing-statuses',
            action='store_true',
            help='Append rebuilt statuses without deleting existing status rows in the replay window.',
        )

    def handle(self, *args, **options):
        device = self._get_device(options['device_id'])
        user = self._get_user(device, options.get('user_id'))
        start_time, end_time = self._resolve_time_window(
            device,
            day=options.get('day'),
            start=options.get('start'),
            end=options.get('end'),
        )

        result = replay_stored_raw_data(
            device=device,
            start_time=start_time,
            end_time=end_time,
            user=user,
            clear_existing_statuses=not options.get('keep_existing_statuses', False),
        )

        self.stdout.write(
            self.style.SUCCESS(
                'Reprocessed statuses for device {device} from {start} to {end}. '
                'Warm-up start: {warmup}. Raw rows visited: {processed}. '
                'Rows in requested window: {replayed}. Skipped status raws: {skipped}. '
                'Deleted existing statuses: {deleted}. User context: {user}.'.format(
                    device=device.id,
                    start=result['start_time'].isoformat(),
                    end=result['end_time'].isoformat(),
                    warmup=result['replay_start_time'].isoformat(),
                    processed=result['processed_raw_count'],
                    replayed=result['replayed_raw_count'],
                    skipped=result['skipped_status_raw_count'],
                    deleted=result['deleted_status_count'],
                    user=user.id if user is not None else 'none',
                )
            )
        )

    def _get_device(self, device_id):
        device_query = Q(ip_address=device_id) | Q(alias=device_id)

        try:
            UUID(str(device_id))
        except (TypeError, ValueError):
            pass
        else:
            device_query = Q(pk=device_id) | device_query

        device = Device.objects.filter(device_query).first()
        if device is None:
            raise CommandError(f'Device not found: {device_id}')
        return device

    def _get_user(self, device, user_id):
        if user_id:
            user = User.objects.filter(pk=user_id).first()
            if user is None:
                raise CommandError(f'User not found: {user_id}')
            return user

        device_type = getattr(device, 'device_type', None)
        return getattr(device_type, 'user', None)

    def _resolve_time_window(self, device, day=None, start=None, end=None):
        if day:
            if end:
                raise CommandError('--end cannot be used with --day')

            try:
                requested_day = datetime.strptime(day, '%Y-%m-%d').date()
            except ValueError as exc:
                raise CommandError('Invalid --day value. Use YYYY-MM-DD.') from exc

            device_timezone = device.get_timezone() or timezone.get_current_timezone()
            start_local = datetime.combine(requested_day, time.min)
            start_local = timezone.make_aware(start_local, device_timezone)
            end_local = start_local + timedelta(days=1)
            return start_local.astimezone(pytz.utc), end_local.astimezone(pytz.utc)

        if not start or not end:
            raise CommandError('--start and --end must be provided together when --day is not used')

        start_time = self._parse_datetime(start, '--start')
        end_time = self._parse_datetime(end, '--end')
        if start_time >= end_time:
            raise CommandError('--end must be later than --start')
        return start_time, end_time

    def _parse_datetime(self, value, label):
        normalized_value = value.replace('Z', '+00:00')

        try:
            parsed_value = datetime.fromisoformat(normalized_value)
        except ValueError as exc:
            raise CommandError(f'Invalid {label} value: {value}') from exc

        if timezone.is_naive(parsed_value):
            parsed_value = timezone.make_aware(
                parsed_value,
                timezone.get_current_timezone(),
            )

        return parsed_value.astimezone(pytz.utc)