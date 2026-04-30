import os
import csv
import logging
import tempfile
import threading
import uuid
from collections.abc import Iterable
from datetime import datetime, time, timedelta

import pytz
import simplejson as json
from api.permissions import IsDevice, IsDeviceUser
from api.serializers import StatusTypeSerializer
from api.utils import get_existing_status_data_for_today, get_or_create_user_device, invalidate_alarm_evaluation_cache, merge_device_other_data, process_raw_data, replay_stored_raw_data
from device.clickhouse_models import DerivedData
from device.models import (Command, Device, DeviceStatus, DeviceProperty, Meter, RawData, StatusType,
                           UserDeviceType, DeviceType)
from device_schemas.schema import (get_status_expression_helper_content,
                                   translate_data_from_schema)
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.db import close_old_connections
from django.db.utils import DatabaseError
from django.db.models import Q
from django.http import HttpResponse, FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from device.models.ota import DeviceConfig
from event.models import DeviceEvent, EventHistory, EventType
from notification.models import Notification
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from utils import DataReports
from utils.weather import get_weather_data_cached
from api.viewsets.common_utils import device_admin, is_device_admin

PERMISSIONS_ADMIN = settings.PERMISSIONS_ADMIN

logger = logging.getLogger('django')

REPROCESS_JOB_STATUS_DIR = os.path.join(
    tempfile.gettempdir(),
    'iot-management-reprocess-jobs',
)
REPROCESS_JOB_STATUS_TTL_SECONDS = 6 * 60 * 60


def _serialize_reprocess_job_value(value):
    if isinstance(value, dict):
        return {
            str(key): _serialize_reprocess_job_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_serialize_reprocess_job_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _ensure_reprocess_job_status_dir():
    os.makedirs(REPROCESS_JOB_STATUS_DIR, exist_ok=True)


def _get_reprocess_job_status_path(job_id):
    _ensure_reprocess_job_status_dir()
    return os.path.join(REPROCESS_JOB_STATUS_DIR, f'{job_id}.json')


def _load_reprocess_job_status(job_id):
    status_path = _get_reprocess_job_status_path(job_id)
    if not os.path.exists(status_path):
        return None

    if timezone.now().timestamp() - os.path.getmtime(status_path) > REPROCESS_JOB_STATUS_TTL_SECONDS:
        try:
            os.remove(status_path)
        except OSError:
            logger.warning('Failed to remove expired reprocess job state: %s', status_path)
        return None

    with open(status_path, 'r', encoding='utf-8') as handle:
        return json.load(handle)


def _write_reprocess_job_status(job_id, data):
    status_path = _get_reprocess_job_status_path(job_id)
    serialized_data = _serialize_reprocess_job_value({
        **data,
        'updated_at': timezone.now().isoformat(),
    })
    temp_path = f'{status_path}.tmp'
    with open(temp_path, 'w', encoding='utf-8') as handle:
        json.dump(serialized_data, handle)
    os.replace(temp_path, status_path)
    return serialized_data


def _update_reprocess_job_status(job_id, patch):
    current_data = _load_reprocess_job_status(job_id) or {}
    current_data.update(patch)
    return _write_reprocess_job_status(job_id, current_data)


def _invalidate_device_static_data_cache(device, requested_device_id):
    for cache_key in {requested_device_id, str(device.id), device.ip_address, device.alias}:
        if cache_key:
            cache.delete(f'device_static_data_{cache_key}')


def _build_reprocess_response(
    device,
    replay_user,
    mode,
    status_interval_minutes,
    target_types,
    keep_existing_statuses,
    result,
):
    return {
        'message': f'Reprocessed statuses for {device.ip_address or device.id}.',
        'device_id': str(device.id),
        'device_identifier': device.ip_address or device.alias or str(device.id),
        'mode': mode,
        'status_interval_minutes': status_interval_minutes,
        'target_types': target_types,
        'keep_existing_statuses': keep_existing_statuses,
        'user_id': str(replay_user.id) if replay_user is not None else None,
        'processed_raw_count': result['processed_raw_count'],
        'replayed_raw_count': result['replayed_raw_count'],
        'skipped_status_raw_count': result['skipped_status_raw_count'],
        'deleted_status_count': result['deleted_status_count'],
        'total_raw_count': result.get('total_raw_count', 0),
        'replay_start_time': result['replay_start_time'].isoformat(),
        'start_time': result['start_time'].isoformat(),
        'end_time': result['end_time'].isoformat(),
    }


def _run_reprocess_job(
    job_id,
    requested_device_id,
    device_pk,
    replay_user_id,
    start_time,
    end_time,
    mode,
    status_interval_minutes,
    target_types,
    keep_existing_statuses,
):
    close_old_connections()
    try:
        device = Device.objects.filter(pk=device_pk).first()
        if device is None:
            raise ValueError('Device not found.')

        replay_user = None
        if replay_user_id is not None:
            replay_user = get_user_model().objects.filter(pk=replay_user_id).first()

        _update_reprocess_job_status(job_id, {
            'status': 'running',
            'started_at': timezone.now().isoformat(),
            'message': 'Replay started.',
            'progress_percent': 0,
        })

        def on_progress(progress):
            total_raw_count = progress.get('total_raw_count') or 0
            processed_raw_count = progress.get('processed_raw_count') or 0
            progress_message = f'Processed {processed_raw_count} of {total_raw_count} raw entries.'
            if progress.get('current_raw_time'):
                progress_message = f"{progress_message} Current raw time: {progress['current_raw_time']}"

            _update_reprocess_job_status(job_id, {
                'status': 'running',
                'message': progress_message,
                'progress_percent': progress.get('progress_percent', 0),
                'progress': progress,
            })

        result = replay_stored_raw_data(
            device=device,
            start_time=start_time,
            end_time=end_time,
            user=replay_user,
            clear_existing_statuses=not keep_existing_statuses,
            replay_status_interval_minutes=status_interval_minutes,
            replay_target_types=target_types,
            progress_callback=on_progress,
        )

        _invalidate_device_static_data_cache(device, requested_device_id)
        response_data = _build_reprocess_response(
            device=device,
            replay_user=replay_user,
            mode=mode,
            status_interval_minutes=status_interval_minutes,
            target_types=target_types,
            keep_existing_statuses=keep_existing_statuses,
            result=result,
        )
        _update_reprocess_job_status(job_id, {
            'status': 'completed',
            'message': response_data['message'],
            'progress_percent': 100,
            'progress': {
                'phase': 'completed',
                'processed_raw_count': response_data['processed_raw_count'],
                'replayed_raw_count': response_data['replayed_raw_count'],
                'skipped_status_raw_count': response_data['skipped_status_raw_count'],
                'deleted_status_count': response_data['deleted_status_count'],
                'total_raw_count': response_data['total_raw_count'],
            },
            'result': response_data,
            'finished_at': timezone.now().isoformat(),
        })
    except Exception as exc:
        logger.exception('Failed to complete replay job %s', job_id)
        _update_reprocess_job_status(job_id, {
            'status': 'failed',
            'message': 'Replay failed.',
            'error': str(exc),
            'finished_at': timezone.now().isoformat(),
        })
    finally:
        close_old_connections()

class HeartbeatViewSet(viewsets.ViewSet):
    """
        Viewset to get device heartbeat data
    """
    permission_classes = ()
    authentication_classes = ()

    def get(self, request, format=None):
        """
            Method to heartbeat data via get request.
        """
        logger.info(f"heartbeat data received: {request.query_params}")
        return Response("OK")

    def post(self, request, format=None):
        """
        Method to heartbeat data via get request.
        """
        logger.info(f"heartbeat data received: {request.data}")

        device_mac = request.data.get("mac")
        device = Device.objects.filter(
            mac=device_mac
        ).first()

        utc_timestamp = int(datetime.utcnow().timestamp())
        resp = f"HEARTBEAT_ACK [{utc_timestamp}]"
        time_to_sync = False
        try:
            if device:
                other_data = device.other_data
                if other_data is None:
                    other_data = {}

                last_datasync_time = other_data.get("last_data_sync_time")
                if last_datasync_time is None:
                    time_to_sync = True
                else:
                    last_datasync_time = datetime.strptime(last_datasync_time, settings.TIME_FORMAT_STRING)
                    time_to_sync = (datetime.utcnow() - last_datasync_time).total_seconds() >= settings.DEFAULT_SYNC_FREQUENCY_MINUTES * 60

                    merge_device_other_data(device, {
                        "last_heartbeat_time": datetime.utcnow().strftime(settings.TIME_FORMAT_STRING)
                    })
            elif device_mac:
                device = Device(
                    mac=device_mac,
                    other_data={
                        "last_heartbeat_time": datetime.utcnow().strftime(settings.TIME_FORMAT_STRING)
                    }
                )
                time_to_sync = True
                device.save()

            if time_to_sync:
                resp = "SYNC [0] {0}"
            elif device is not None:
                command = device.get_command()
                if command is not None:
                    command.status = 'E'
                    command.command_read_time = datetime.utcnow()
                    command.save()
                    resp = f"{command.command}{command.param}"

        except Exception as ex:
            logger.exception(ex)
            resp = "ERROR"
        return Response(resp)


class DataViewSet(viewsets.ViewSet):
    """
        Viewset to accept data from device.
    """
    permission_classes = (IsDevice,)
    authentication_classes = ()

    def create(self, request, format=None):
        """
            Method to accept data via post request.
        """
        device = getattr(request, 'device', None)
        user = getattr(request, 'user', None)
        data = request.data

        logger.info(f"Received data {data} from user: {user}, device: {device}")
        # if device is None, then check if it is a user
        errors = []
        if device is None and user is not None:
            device = get_or_create_user_device(user, data)
        
        if device is None:
            errors.append("Device not found!")
            return Response(status=status.HTTP_422_UNPROCESSABLE_ENTITY, data=errors)

        error = process_raw_data(device, data, channel='api', data_type='data', user=user)
        if error != "":
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                "error": error
            })

        # invalidate static data cache
        cache.delete("device_static_data_{}".format(device.ip_address))

        return Response("OK")


class DeviceDetailsViewSet(viewsets.ViewSet):
    """
    ViewSet to return device info.
    """
    permission_classes = (IsAuthenticated, IsDeviceUser)

    def _get_reprocess_interval_minutes(self, payload):
        interval_value = payload.get('status_interval_minutes', 10)
        try:
            interval_minutes = int(interval_value)
        except (TypeError, ValueError) as exc:
            raise ValueError('Status interval must be an integer between 2 and 60 minutes.') from exc

        if interval_minutes < 2 or interval_minutes > 60:
            raise ValueError('Status interval must be between 2 and 60 minutes.')

        return interval_minutes

    def _get_reprocess_target_types(self, payload):
        target_types = payload.get('target_types')
        if target_types in [None, '', []]:
            return [
                StatusType.STATUS_TARGET_DEVICE,
                StatusType.STATUS_TARGET_USER,
                StatusType.STATUS_TARGET_METER,
                StatusType.STATUS_TARGET_ALARM,
                StatusType.STATUS_TARGET_REPORT,
            ]

        if not isinstance(target_types, list):
            raise ValueError('Target types must be a list.')

        allowed_target_types = {
            StatusType.STATUS_TARGET_DEVICE,
            StatusType.STATUS_TARGET_USER,
            StatusType.STATUS_TARGET_METER,
            StatusType.STATUS_TARGET_ALARM,
            StatusType.STATUS_TARGET_REPORT,
        }
        normalized_target_types = []
        for target_type in target_types:
            if target_type not in allowed_target_types:
                raise ValueError(f'Invalid target type: {target_type}')
            if target_type not in normalized_target_types:
                normalized_target_types.append(target_type)

        if not normalized_target_types:
            raise ValueError('Choose at least one target type to reprocess.')

        return normalized_target_types

    def _parse_reprocess_datetime(self, value):
        if not value:
            return None

        normalized_value = str(value).replace('Z', '+00:00')
        parsed_value = datetime.fromisoformat(normalized_value)
        if timezone.is_naive(parsed_value):
            parsed_value = timezone.make_aware(
                parsed_value,
                timezone.get_current_timezone(),
            )
        return parsed_value.astimezone(pytz.utc)

    def _get_reprocess_window(self, device, payload):
        mode = payload.get('mode', 'day')
        if mode == 'range':
            start_time = self._parse_reprocess_datetime(payload.get('start'))
            end_time = self._parse_reprocess_datetime(payload.get('end'))
            if start_time is None or end_time is None:
                raise ValueError('Start and end are required for range reprocessing.')
            if start_time >= end_time:
                raise ValueError('End time must be later than start time.')
            return start_time, end_time, mode

        day_value = payload.get('day')
        if not day_value:
            raise ValueError('Day is required for day-based reprocessing.')

        requested_day = datetime.strptime(day_value, '%Y-%m-%d').date()
        device_timezone = device.get_timezone() or timezone.get_current_timezone()
        start_local = timezone.make_aware(
            datetime.combine(requested_day, time.min),
            device_timezone,
        )
        end_local = start_local + timedelta(days=1)
        return start_local.astimezone(pytz.utc), end_local.astimezone(pytz.utc), 'day'

    def _resolve_user_device(self, user, device_id):
        device = user.device_list(return_objects=True, device_id=device_id)
        if isinstance(device, list):
            filtered_device = [x for x in device if x.ip_address == device_id]
            if len(filtered_device) == 0:
                return None
            return filtered_device[0]
        return device

    def _get_alarm_type_ids(self):
        try:
            return list(
                EventType.objects.filter(
                    status_key__isnull=False,
                    operator__isnull=False,
                    target_value__isnull=False,
                ).values_list('id', flat=True)
            )
        except DatabaseError:
            try:
                event_types = EventType.objects.all().only('id', 'status_key', 'operator', 'target_value')
                return [
                    event_type.id
                    for event_type in event_types
                    if event_type.status_key not in [None, '']
                    and event_type.operator not in [None, '']
                    and event_type.target_value not in [None, '']
                ]
            except Exception:
                logger.exception('Failed to resolve alarm event type ids.')
                return []

    def _get_event_types_map(self, event_type_ids):
        if len(event_type_ids) == 0:
            return {}
        try:
            event_types = EventType.objects.filter(id__in=event_type_ids)
            return {event_type.id: event_type for event_type in event_types}
        except Exception:
            logger.exception('Failed to resolve event type map with id__in; falling back to in-memory filtering.')
            event_type_ids_set = set(event_type_ids)
            try:
                event_types = EventType.objects.all().only('id', 'name', 'status_key', 'operator', 'target_value')
                return {
                    event_type.id: event_type
                    for event_type in event_types
                    if event_type.id in event_type_ids_set
                }
            except Exception:
                logger.exception('Failed to resolve event type map for alarms.')
                return {}

    def _get_alarm_events_for_device(self, device, active_only=None):
        alarm_type_ids = self._get_alarm_type_ids()
        if len(alarm_type_ids) == 0:
            return [], {}

        device_id = getattr(device, 'id', None)
        if device_id is None:
            return [], {}

        try:
            alarms = list(DeviceEvent.objects.all())
        except Exception:
            logger.exception('Failed to query device events for alarm resolution.')
            return [], {}

        alarm_type_ids_set = set(alarm_type_ids)
        alarms = [
            alarm
            for alarm in alarms
            if getattr(alarm, 'device_id', None) == device_id
            and alarm.typ_id in alarm_type_ids_set
            and (active_only is not True or alarm.active is True)
        ]
        alarms = sorted(
            alarms,
            key=lambda alarm: alarm.created_at or timezone.now(),
            reverse=True,
        )

        event_type_ids = [alarm.typ_id for alarm in alarms if alarm.typ_id is not None]
        event_types_map = self._get_event_types_map(event_type_ids)
        return alarms, event_types_map

    def _get_device_alarm_by_id(self, device, alarm_id):
        device_id = getattr(device, 'id', None)
        if device_id is None:
            return None

        normalized_alarm_id = str(alarm_id)

        try:
            alarms = DeviceEvent.objects.all()
        except Exception:
            logger.exception('Failed to query device events for alarm lookup.')
            return None

        for alarm in alarms:
            if str(getattr(alarm, 'id', None)) == normalized_alarm_id and getattr(alarm, 'device_id', None) == device_id:
                return alarm
        return None

    def _serialize_status_alarm(self, device_event, event_type=None):
        event_type = event_type or EventType.objects.filter(id=device_event.typ_id).first()
        if event_type is None:
            return None

        channels = [
            action.get('channel')
            for action in (device_event.actions_config or [])
            if action.get('channel')
        ]
        channels = list(dict.fromkeys(channels))

        return {
            'id': str(device_event.id),
            'name': event_type.name,
            'status_key': event_type.status_key,
            'operator': event_type.operator,
            'target_value': event_type.target_value,
            'channels': channels,
            'active': device_event.active,
            'last_trigger_time': (
                device_event.last_trigger_time.strftime(settings.TIME_FORMAT_STRING)
                if device_event.last_trigger_time is not None
                else None
            ),
            'created_at': device_event.created_at.strftime(settings.TIME_FORMAT_STRING),
        }

    def _serialize_status_alarm_history(self, event_history, event_types_map=None):
        result = event_history.result or {}
        channels = result.get('channels') or []
        event_types_map = event_types_map or {}

        event_type = event_types_map.get(event_history.device_event.typ_id)
        if event_type is None:
            event_type = EventType.objects.filter(id=event_history.device_event.typ_id).first()

        if event_type is None:
            return None

        return {
            'id': str(event_history.id),
            'alarm_id': str(event_history.device_event.id),
            'alarm_name': event_type.name,
            'status_key': event_type.status_key,
            'operator': event_type.operator,
            'target_value': event_type.target_value,
            'status_value': result.get('status_value'),
            'triggered_at': event_history.trigger_time.strftime(settings.TIME_FORMAT_STRING),
            'channels': channels,
            'message': result.get('message'),
            'status_snapshot': result.get('status_snapshot'),
        }

    def _build_alarm_actions_config(self, payload, owner=None):
        channels = payload.get('channels', [])
        if not isinstance(channels, list):
            channels = []

        default_title = payload.get('template_title') or 'Device Alarm'
        default_text = payload.get('template_text') or '{{device}}: {{status_key}} {{operator}} {{target_value}} ({{status_value}})'

        actions = []
        for channel in channels:
            method = None
            if channel == EventType.ALARM_CHANNEL_IN_APP:
                method = Notification.PUSH_NOTIFICATION
            elif channel == EventType.ALARM_CHANNEL_TELEGRAM:
                method = Notification.TELEGRAM_BOT
            elif channel == EventType.ALARM_CHANNEL_EMAIL:
                method = Notification.EMAIL

            if method is None:
                continue

            template = Notification.objects.create(
                name=f'Alarm template: {channel}',
                user=owner,
                method=method,
                title=default_title,
                text=default_text,
                emails=(payload.get('emails') or '').strip() or None,
                data={
                    'template': True,
                    'channel': channel,
                },
            )

            actions.append({
                'channel': channel,
                'method': method,
                'template_id': str(template.id),
                'emails': (payload.get('emails') or '').strip() or None,
                'telegram_chat_ids': (payload.get('telegram_chat_ids') or '').strip() or None,
            })

        return actions

    def get_device_alarms(self, request, device_id):
        device = self._resolve_user_device(request.user, device_id)
        if device is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        alarms, event_types_map = self._get_alarm_events_for_device(device)
        serialized_alarms = []
        for alarm in alarms:
            serialized_alarm = self._serialize_status_alarm(
                alarm,
                event_type=event_types_map.get(alarm.typ_id),
            )
            if serialized_alarm is not None:
                serialized_alarms.append(serialized_alarm)
        return Response(serialized_alarms)

    def create_device_alarm(self, request, device_id):
        device = self._resolve_user_device(request.user, device_id)
        if device is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        payload = request.data or {}
        alarm_id = payload.get('id')
        alarm_type_ids = set(self._get_alarm_type_ids())

        alarm = None
        if alarm_id:
            alarm = self._get_device_alarm_by_id(device, alarm_id)
            if alarm is not None and alarm.typ_id not in alarm_type_ids:
                alarm = None
            if alarm is None:
                return Response({'error': 'Alarm not found.'}, status=status.HTTP_404_NOT_FOUND)
        else:
            alarm = DeviceEvent(device=device, user=request.user)

        status_key = (payload.get('status_key') or '').strip()
        target_value = str(payload.get('target_value') or '').strip()
        operator = (payload.get('operator') or EventType.ALARM_OPERATOR_EQ).strip()

        if status_key == '' or target_value == '':
            return Response(
                {'error': 'status_key and target_value are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        allowed_operators = {x[0] for x in EventType.ALARM_OPERATOR_CHOICES}
        if operator not in allowed_operators:
            return Response({'error': 'Invalid operator.'}, status=status.HTTP_400_BAD_REQUEST)

        if alarm.typ_id is None:
            alarm_type = EventType(
                name=(payload.get('name') or '').strip() or f'{status_key} {operator} {target_value}',
                description='Device status alarm type',
                trigger_type='Data',
                equation='status expression',
                is_alarm_type=True,
            )
        else:
            alarm_type = alarm.typ

        alarm_type.name = (payload.get('name') or '').strip() or f'{status_key} {operator} {target_value}'
        alarm_type.status_key = status_key
        alarm_type.operator = operator
        alarm_type.target_value = target_value
        alarm_type.is_alarm_type = True
        alarm_type.trigger_type = 'Data'
        alarm_type.description = 'Device status alarm type'
        alarm_type.save()

        alarm.typ = alarm_type
        alarm.actions_config = self._build_alarm_actions_config(payload, owner=request.user)
        alarm.active = bool(payload.get('active', True))
        alarm.save()

        invalidate_alarm_evaluation_cache([alarm_type.id])

        return Response(self._serialize_status_alarm(alarm, event_type=alarm_type))

    def delete_device_alarm(self, request, device_id, alarm_id):
        device = self._resolve_user_device(request.user, device_id)
        if device is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        alarm_type_ids = set(self._get_alarm_type_ids())
        alarm = self._get_device_alarm_by_id(device, alarm_id)
        if alarm is not None and alarm.typ_id not in alarm_type_ids:
            alarm = None
        if alarm is None:
            return Response({'error': 'Alarm not found.'}, status=status.HTTP_404_NOT_FOUND)

        alarm_type = alarm.typ
        alarm.delete()

        if alarm_type is not None:
            try:
                has_other_bindings = any(
                    getattr(device_event, 'typ_id', None) == alarm_type.id
                    for device_event in DeviceEvent.objects.all()
                )
            except Exception:
                logger.exception('Failed to resolve remaining bindings for alarm type %s.', alarm_type.id)
                has_other_bindings = True
            if not has_other_bindings:
                invalidate_alarm_evaluation_cache([alarm_type.id])
                alarm_type.delete()
            else:
                invalidate_alarm_evaluation_cache([alarm_type.id])

        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_device_alarm_history(self, request, device_id):
        device = self._resolve_user_device(request.user, device_id)
        if device is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        limit = request.query_params.get('limit', 100)
        try:
            limit = max(1, min(500, int(limit)))
        except (TypeError, ValueError):
            limit = 100

        alarms, event_types_map = self._get_alarm_events_for_device(device)
        alarm_event_ids = [alarm.id for alarm in alarms]
        if len(alarm_event_ids) == 0:
            return Response([])

        history = EventHistory.objects.filter(
            device_event_id__in=alarm_event_ids,
        ).order_by('-trigger_time')[:limit]

        serialized_history = []
        for item in history:
            serialized_item = self._serialize_status_alarm_history(
                item,
                event_types_map=event_types_map,
            )
            if serialized_item is not None:
                serialized_history.append(serialized_item)
        return Response(serialized_history)

    @device_admin
    def reprocess_statuses(self, request, device_id):
        payload = request.data or {}
        device, _ = is_device_admin(request.user, device_id)
        if device is None:
            return Response(
                status=status.HTTP_404_NOT_FOUND,
                data={'error': 'Device not found'}
            )

        try:
            start_time, end_time, mode = self._get_reprocess_window(device, payload)
            status_interval_minutes = self._get_reprocess_interval_minutes(payload)
            target_types = self._get_reprocess_target_types(payload)
        except ValueError as exc:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={'error': str(exc)}
            )

        replay_user = getattr(getattr(device, 'device_type', None), 'user', None) or request.user
        keep_existing_statuses = bool(payload.get('keep_existing_statuses', False))

        job_id = uuid.uuid4().hex
        queued_job = _write_reprocess_job_status(job_id, {
            'job_id': job_id,
            'status': 'queued',
            'message': 'Replay queued.',
            'progress_percent': 0,
            'device_id': str(device.id),
            'device_identifier': device.ip_address or device.alias or str(device.id),
            'mode': mode,
            'status_interval_minutes': status_interval_minutes,
            'target_types': target_types,
            'keep_existing_statuses': keep_existing_statuses,
            'user_id': str(replay_user.id) if replay_user is not None else None,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'created_at': timezone.now().isoformat(),
            'progress': {
                'phase': 'queued',
                'processed_raw_count': 0,
                'replayed_raw_count': 0,
                'skipped_status_raw_count': 0,
                'deleted_status_count': 0,
                'total_raw_count': 0,
            },
        })

        replay_thread = threading.Thread(
            target=_run_reprocess_job,
            kwargs={
                'job_id': job_id,
                'requested_device_id': device_id,
                'device_pk': device.pk,
                'replay_user_id': replay_user.id if replay_user is not None else None,
                'start_time': start_time,
                'end_time': end_time,
                'mode': mode,
                'status_interval_minutes': status_interval_minutes,
                'target_types': target_types,
                'keep_existing_statuses': keep_existing_statuses,
            },
            daemon=True,
        )
        replay_thread.start()

        return Response(queued_job, status=status.HTTP_202_ACCEPTED)

    @device_admin
    def get_reprocess_status(self, request, device_id, job_id):
        device, _ = is_device_admin(request.user, device_id)
        job_data = _load_reprocess_job_status(job_id)
        if job_data is None or device is None or job_data.get('device_id') != str(device.id):
            return Response(
                status=status.HTTP_404_NOT_FOUND,
                data={'error': 'Replay job not found.'}
            )

        return Response(job_data)

    def get_status_type_helper(self, request):
        device_id = request.query_params.get('device_id')
        latest_raw = None
        raw_data_sample = {}

        if device_id not in [None, '', 'None', 'null', 'NULL']:
            device, _ = is_device_admin(request.user, device_id)
            if device is None:
                return Response(
                    status=status.HTTP_404_NOT_FOUND,
                    data={"error": "Device not found"}
                )
            latest_raw = RawData.objects.filter(device=device).order_by('-data_arrival_time').first()
            raw_data_sample = (latest_raw.data if latest_raw is not None else {}) or {}

        helper_content = get_status_expression_helper_content(raw_data_sample)
        helper_content['device_context'] = {
            'device_id': device_id,
            'has_device_context': bool(device_id),
            'latest_raw_time': latest_raw.data_arrival_time if latest_raw is not None else None,
            'available_data_cache_keys': ['weather'],
        }

        return Response(helper_content)

    def get_status_type_preview(self, request, device_id):
        if device_id in [None, '', 'None', 'null', 'NULL']:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"error": "Invalid device_id"}
            )

        dev_user = request.user
        device, _ = is_device_admin(dev_user, device_id)
        if device is None:
            return Response(
                status=status.HTTP_404_NOT_FOUND,
                data={"error": "Device not found"}
            )

        status_type = request.data.get('status_type', {}) or {}
        schema = status_type.get('translation_schema')
        target_name = status_type.get('name')
        schema_target = status_type.get('target_type')
        data_cache = request.data.get('data_cache', {}) or {}

        if schema is None:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"error": "Missing status_type.translation_schema"}
            )

        normalized_schema = schema
        if isinstance(normalized_schema, dict):
            normalized_schema = {
                **normalized_schema,
                'name': target_name or normalized_schema.get('name'),
                'target': schema_target or normalized_schema.get('target')
            }
        elif isinstance(normalized_schema, list):
            normalized_schema = [
                {
                    **item,
                    'name': item.get('name') or target_name,
                    'target': item.get('target') or schema_target
                } if isinstance(item, dict) else item
                for item in normalized_schema
            ]

        latest_raw = RawData.objects.filter(device=device).order_by('-data_arrival_time').first()
        raw_data = (latest_raw.data if latest_raw is not None else {}) or {}
        existing_statuses = get_existing_status_data_for_today(dev_user, device, latest_raw)
        raw_data = (
            (existing_statuses.get('lastToday', {}) or {}).get('raw')
            or raw_data
            or {}
        )

        translated_preview = translate_data_from_schema(
            normalized_schema,
            raw_data,
            existing_statuses,
            data_cache,
            include_debug=True,
        )
        translated = translated_preview.get('translated_data', {})

        if not target_name and isinstance(normalized_schema, dict):
            target_name = normalized_schema.get('name')

        calculated_values = translated.get(target_name, {}) if target_name else translated
        field_details = translated_preview.get('field_details', [])
        if target_name:
            field_details = [
                field_detail
                for field_detail in field_details
                if field_detail.get('status_name') == target_name
            ]

        return Response({
            'status_type': {
                'name': target_name,
                'target_type': schema_target,
            },
            'calculated_values': calculated_values,
            'field_details': field_details,
            'debug_context': translated_preview.get('debug_context', {}),
            'raw_data_sample': raw_data,
            'data_arrival_time': latest_raw.data_arrival_time if latest_raw is not None else None,
        })

    def device_static_data(self, request, device_id):
        """
        The view should return static data of the device.
        """
        if device_id in [None, '', 'None', 'null', 'NULL']:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"error": "Invalid device_id"}
            )

        # Find out the user
        dev_user = request.user
        device, _ = is_device_admin(dev_user, device_id)

        if device is None:
            return Response(
                status=status.HTTP_404_NOT_FOUND,
                data={"error": "Device not found"}
            )

        cached_data = cache.get("device_static_data_{}".format(device_id))

        if cached_data is not None:
            return Response(json.loads(cached_data))

        latest_status = DeviceStatus.objects.filter(
            device=device,
            name=DeviceStatus.DAILY_STATUS
        ).order_by('-created_at').first()
        
        data_report = DataReports(device)
        available_device_types = UserDeviceType.objects.filter(
            user=dev_user
        ).all()
        dev_types = []
        for dev_type in available_device_types:
            dev_types.append({'value': dev_type.code, 'text': dev_type.name})

        if device.type is not None:
            available_status_types = StatusType.objects.filter(
                Q(device=device) | Q(device_type=device.type)
            ).all()
        else:
             available_status_types = StatusType.objects.filter(
                Q(device=device)
            ).all()

        status_types = []
        for status_type in available_status_types:
            if not status_type.active: continue
            status_types.append(StatusTypeSerializer(status_type).data)

        device_data = {
            'id': str(device.id),
            'numeric_id': device.numeric_id,
            'active': device.active,
            'ip_address': device.ip_address,
            'name': device.name,
            'alias': device.alias,
            'type': device.type.name if device.type is not None else None,
            'available_status_types': status_types,
            'available_device_types': dev_types,
            'installation_date': device.installation_date.strftime("%d-%b-%Y") if device.installation_date else None,
            'operator': {},
            'device_contact': device.device_contact_number,
            'avatar': device.avatar.url if device.avatar else None,
            'position': {
                'latitude': device.position.get("latitude") if device.position else None,
                'longitude': device.position.get("longitude") if device.position else None
            },
            'commands': [c.command_name for c in device.commands.all()],
            'properties': {
                **((device.other_data or {}).get('device_properties', {})),
                **{p.name: p.get_value() for p in DeviceProperty.objects.filter(device=device)},
                **((latest_status.status if latest_status else None) or {})
            },
            'address': device.address,
            'other_data': device.other_data,
            'token': device.access_token
        }

        if device.operator:
            operator_data = {
                '_id': str(device.operator.id),
                'name': device.operator.name,
                'address': device.operator.address,
                'pincode': device.operator.pin_code,
                'contact': device.operator.contact_number,
                'avatar': device.operator.avatar.url if device.operator.avatar else None
            }
            device_data['operator'] = operator_data

        available_parameters = [
            "voltage", "current", "power",
            "frequency", "temperature",
            "energy", "state", "runtime",
            "latitude", "longitude",
        ]

        derived_data = DerivedData.objects.filter(device=str(device.id))
        for derived_dt in derived_data:
            available_parameters.append(derived_dt.name)

        device_data["data_parameters"] = available_parameters

        device_data['latest_data'] = data_report.get_latest_data()
        device_data['latest_weather_data'] = get_weather_data_cached(device)
        device_data['current_load'] = data_report.get_possible_equipment_list()
        device_data['tips'] = data_report.get_energy_saving_tips(device_data['current_load'])

        device_data['status_data_today'] = data_report.get_current_day_status_data()
        device_data['loads_today'] = data_report.get_appliances_current_day()

        configured_alarms, alarm_event_types = self._get_alarm_events_for_device(device)
        serialized_alarms = []
        for alarm in configured_alarms:
            serialized_alarm = self._serialize_status_alarm(
                alarm,
                event_type=alarm_event_types.get(alarm.typ_id),
            )
            if serialized_alarm is not None:
                serialized_alarms.append(serialized_alarm)
        device_data['alarms'] = serialized_alarms

        device_data['available_meter_types'] = [x for x in Meter.__dict__ if '_METER' in x]
        device_data['meters'] = [{
            "id": str(device_meter.id),
            "name": device_meter.name,
            "meter_type": device_meter.meter_type,
        } for device_meter in device.get_meters()]
        cache.set("device_static_data_{}".format(device_id), json.dumps(device_data), 120)

        return Response(device_data)

    def update_static_data(self, request, device_id):
        data = request.data
        dev_user = request.user
        device = dev_user.device_list(return_objects=True, device_id=device_id)

        if isinstance(device, list):
            device = [
                x for x in device if x.ip_address == device_id
            ]
            if len(device) == 0:
                return Response(status=status.HTTP_404_NOT_FOUND)
            device = device[0]

        if not dev_user.has_permission(settings.PERMISSIONS_ADMIN):
            return Response(status=status.HTTP_403_FORBIDDEN)

        original_device_id = device.ip_address

        for key in data:
            val = data[key]
            if key in {'other_data', 'position'} and isinstance(val, dict):
                existing_value = getattr(device, key, None) or {}
                setattr(device, key, {**existing_value, **val})
                continue
            if key == 'properties' and isinstance(val, dict):
                # DeviceProperty model fields (string or float) — upsert as rows
                DEVICE_PROPERTY_KEYS = {'currency', 'pay_per_unit', 'total_investment', 'total_recovery_amount'}
                for prop_key, prop_val in val.items():
                    if prop_key in DEVICE_PROPERTY_KEYS:
                        val_type = DeviceProperty.STRING if prop_key == 'currency' else DeviceProperty.FLOAT
                        DeviceProperty.objects.update_or_create(
                            device=device, name=prop_key,
                            defaults={'value': str(prop_val), 'val_type': val_type}
                        )
                # Remaining keys go into other_data['device_properties']
                remaining = {k: v for k, v in val.items() if k not in DEVICE_PROPERTY_KEYS}
                if remaining:
                    existing_other_data = device.other_data or {}
                    existing_device_properties = existing_other_data.get('device_properties', {})
                    device.other_data = {
                        **existing_other_data,
                        'device_properties': {**existing_device_properties, **remaining}
                    }
                continue
            if hasattr(device, key):
                try:
                    setattr(device, key, val)
                except Exception as ex:
                    logger.warning(ex)

        if 'type' in data:
            dev_type = UserDeviceType.objects.filter(user=dev_user, code__iexact=data['type']).first()
            if dev_type:
                device.device_type = dev_type
        
        device.alias = data.get('alias', device.alias)
        device.device_contact_number = data.get('device_contact', device.device_contact_number)

        device.save()

        cache.delete("device_static_data_{}".format(original_device_id))
        cache.delete("device_static_data_{}".format(device.ip_address))

        device_meters = device.get_meters()

        for meter_data in data.get('meters', []):
            meter = device_meters.filter(id=meter_data['id'])
            if meter.count() > 0:
                meter.update(meter_type=meter_data.get('meter_type'))

        # Update status types for the device
        errors = []
        if request.user.has_permission(PERMISSIONS_ADMIN):
            if device.device_type is not None:
                device_status_types = StatusType.objects.filter(
                    Q(device=device) | Q(device_type=device.device_type)
                ).all()
            else:
                device_status_types = StatusType.objects.filter(
                    Q(device=device)
                ).all()
            # handle the status types update
            new_available_status_types = request.data.get("available_status_types")
            if isinstance(new_available_status_types, list):
                for new_available_status_type in new_available_status_types:
                    status_type_id = new_available_status_type.get("id")
                    status_type = None
                    if status_type_id is not None:
                        status_type = device_status_types.filter(
                            id=status_type_id
                        ).first()
                        if status_type is None:
                            errors.append(f"Status type with id {status_type_id} not found!")
                            continue
                    else:
                        status_type = StatusType()
                    if len(errors) == 0:
                        status_type.active = new_available_status_type.get("active", status_type.active)
                        status_type.name = new_available_status_type.get("name", status_type.name)
                        status_type.target_type = new_available_status_type.get("target_type", status_type.target_type)
                        status_type.update_trigger = new_available_status_type.get("update_trigger", status_type.update_trigger)
                        status_type.device = device
                        status_type.device_type = new_available_status_type.get("device_type", status_type.device_type)
                        status_type.translation_schema = new_available_status_type.get("translation_schema", status_type.translation_schema)
                        status_type.save()

        latest_status = DeviceStatus.objects.filter(
            device=device,
            name=DeviceStatus.DAILY_STATUS
        ).order_by('-created_at').first()

        available_device_types = UserDeviceType.objects.filter(
            user=dev_user
        ).all()
        dev_types = []
        for dev_type in available_device_types:
            dev_types.append({'value': dev_type.code, 'text': dev_type.name})
    
        if device.device_type is not None:
            available_status_types = StatusType.objects.filter(
                Q(device=device) | Q(device_type=device.device_type)
            ).all()
        else:
            available_status_types = StatusType.objects.filter(
                Q(device=device)
            ).all()

        status_types = []
        for status_type in available_status_types:
            if not status_type.active: continue
            status_types.append(StatusTypeSerializer(status_type).data)

        device_data = {
            'ip_address': device.ip_address,
            'name': device.name,
            'alias': device.alias,
            'type': device.device_type.name if device.device_type is not None else None,
            'available_status_types': status_types,
            'available_device_types': dev_types,
            'installation_date': device.installation_date.strftime("%d-%b-%Y") if device.installation_date else None,
            'device_contact': device.device_contact_number,
            'avatar': device.avatar.url if device.avatar else None,
            'position': {
                'latitude': device.position.get("latitude") if device.position else None,
                'longitude': device.position.get("longitude") if device.position else None
            },
            'commands': [c.command_name for c in device.commands.all()],
            'properties': {
                **((device.other_data or {}).get('device_properties', {})),
                **{p.name: p.get_value() for p in DeviceProperty.objects.filter(device=device)},
                **((latest_status.status if latest_status else None) or {})
            },
            'address': device.address,
            'other_data': device.other_data
        }

        device_data['meters'] = [{
            "id": str(device_meter.id),
            "name": device_meter.name,
            "meter_type": device_meter.meter_type,
        } for device_meter in device.get_meters()]

        return Response(device_data)

    def get_dynamic_data(self, request, device_id):
        dynamic_data = {}

        dev_user = request.user

        if device_id == "all":
            devices = dev_user.device_list(return_objects=True)
        else:
            devices = dev_user.device_list(return_objects=True, device_id=device_id)

        if isinstance(devices, list) and device_id != "all":
            devices = [
                x for x in devices if x.ip_address == device_id
            ]
            if len(devices) == 0:
                return Response(status=status.HTTP_404_NOT_FOUND)

        data_type = "raw"
        export_type = "json"
        data_type = request.data.get("dataType", data_type)
        export_type = request.data.get("exportType")
        start_time = request.data.get("startTime", "").strip()
        start_date = request.data.get("startDate", "").strip()
        end_time = request.data.get("endTime", "").strip()
        end_date = request.data.get("endDate", "").strip()
        if end_date == '' and end_time == '':
            end_date = start_date
            end_time = start_time
        if start_date:
            start_time = datetime.strptime(
                start_date, settings.DATE_FORMAT_STRING
            )
        else:
            start_time = datetime.strptime(
                start_time, settings.TIME_FORMAT_STRING
            )
        if end_date:
            end_time = datetime.strptime(
                end_date, settings.DATE_FORMAT_STRING
            )
        else:
            end_time = datetime.strptime(
                end_time, settings.TIME_FORMAT_STRING
            )
        selected_x_params = request.data.get("x_params")
        selected_y_params = request.data.get("y_params")
        # aggregate_data = request.GET.get('aggregate', 'yes')

        data_report = DataReports(devices, multiple=isinstance(devices, Iterable))
        data = None
        if data_type in ["raw", "raw_data"]:
            data = data_report.get_device_data(
                data_type,
                start_time,
                end_time,
                meter_type=[
                    Meter.AC_METER, Meter.INVERTER_AC_METER,
                    Meter.HOUSEHOLD_AC_METER, Meter.LOAD_AC_METER
                ]
            )
        elif export_type != "json":
            data = data_report.get_status_data([data_type], start_time, end_time)
        if export_type == "json":
            if data_type == "status":
                data = data_report.get_current_day_status_data(start_time)
            elif data_type in ["raw", "raw_data"]:
                json_data = []
                if data is not None:
                    for dt in data:
                        if isinstance(dt, dict):
                            rl_data = dt.get("status")
                            data_arrival_time = dt.get("created_at")
                            channel = "calculated"
                            data_type = dt.get("name")
                            ip_address = data_report.device.ip_address
                        else:
                            rl_data = dt.data
                            data_arrival_time = dt.data_arrival_time.strftime(settings.TIME_FORMAT_STRING)
                            channel = dt.channel
                            data_type = dt.data_type
                            ip_address = dt.device.ip_address

                        if data_arrival_time is None:
                            data_arrival_time = dt.created_at

                        json_data.append({
                            "data_arrival_time": data_arrival_time,
                            "channel": channel,
                            "data_type": data_type,
                            "ip_address": ip_address,
                            "data": rl_data
                        })
                    data = json_data
            elif data_type is not None:
                data = data_report.get_status_data([data_type], start_time, end_time)
            else:
                x_params = selected_x_params.strip()
                y_params = selected_y_params.strip().split(',')

                params_list = ["time"]
                if(x_params != '' and x_params != 'time'):
                    params_list += [x_params]
                for param in y_params:
                    params_list += [param]

                for param in params_list:
                    dynamic_data[param] = []

                for param in params_list:
                    data_list = []
                    for each_data in data:
                        if(param == "time"):
                            param = "data_arrival_time"
                        data_list.append(getattr(each_data, param, None))
                    dynamic_data[param] = data_list
                data = {"error": "success", "dynamic_data": dynamic_data}
            return Response(data)
        else:
            header = ["data_arrival_time", "device", "channel", "data_type", "data"]
            csv_data = []
            if data is not None:
                for dt in data:
                    if isinstance(dt, dict):
                        rl_data = dt.get("status")
                        data_arrival_time = dt.get("created_at")
                        channel = "calculated"
                        data_type = dt.get("name")
                        ip_address = data_report.device.ip_address
                    else:
                        rl_data = dt.data
                        data_arrival_time = dt.data_arrival_time.strftime(settings.TIME_FORMAT_STRING)
                        channel = dt.channel
                        data_type = dt.data_type
                        ip_address = dt.device.ip_address

                    if data_arrival_time is None:
                        data_arrival_time = dt.created_at

                    csv_data.append([
                        data_arrival_time,
                        channel,
                        data_type,
                        ip_address,
                        json.dumps(rl_data)
                    ])
            # Create the HttpResponse object with the appropriate CSV header.
            response = HttpResponse(
                content_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="{device_id}-{data_type}.csv"'},
            )

            writer = csv.writer(response)
            writer.writerow(header)
            writer.writerows(csv_data)

            return response

    def send_command(self, request, device_id):
        device, is_admin = is_device_admin(request.user, device_id)
        if device is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not is_admin:
            return Response(status=status.HTTP_403_FORBIDDEN)

        data = request.data
        command = data.get('command', '').strip()
        command_param = data.get("command_param")
        if command_param and isinstance(command_param, str):
            command_param = command_param.strip()

        if command != "":
            # Save the command into command model
            dev_command = device.commands.filter(command_name=command).first()
            cmd = Command(
                device=device,
                status='P',
                command_in_time=timezone.now(),
                command=dev_command.command_code if dev_command else command,
                param=command_param
            )
            cmd.save()
            cmd.send()
        return Response(status=status.HTTP_201_CREATED)

    def get_report(self, request, device_id, report_type):
        """
            This will return weekly/monthly energy consumption data by day/week.
            This will return weekly/monthly energy consumption data by appliance.
            This will return weekly/monthly energy consumption data of last 3 weeks/months.
        """

        # Findout the user
        dev_user = request.user
        device = dev_user.device_list(return_objects=True, device_id=device_id)

        if isinstance(device, list):
            device = [
                x for x in device if x.ip_address == device_id
            ]
            if len(device) == 0:
                return Response(status=status.HTTP_404_NOT_FOUND)

        report_data = None
        report_name = None

        if report_type == 'yesterday':
            report_name = DeviceStatus.LAST_DAY_REPORT

        elif report_type == 'month':
            report_name = DeviceStatus.LAST_MONTH_REPORT

        elif report_type == 'week':
            report_name = DeviceStatus.LAST_WEEK_REPORT
            
        if report_name is not None:
            report_status = DeviceStatus.objects.filter(
                device=device,
                name=report_name
            ).order_by('-created_at').first()
            if report_status:
                report_data = report_status.status

        # Get weekly/monthly energy consumption data by appliance.
        # x, consumption_data_by_appaliance = data_report.get_data_with_apaliances(
        #     start_time=start_time,
        #     end_time=end_time
        # )

        return Response(report_data)

    def remove_device(self, request, device_id):
        dev_user = request.user
        dev = get_object_or_404(Device, id=device_id)
        device = dev_user.device_list(return_objects=True, device_id=dev.ip_address)
        if isinstance(device, list):
            device = [
                x for x in device if x.ip_address == device_id
            ]
            if len(device) == 0:
                return Response(status=status.HTTP_404_NOT_FOUND)

        if not dev_user.has_permission(settings.PERMISSIONS_ADMIN):
            return Response(status=status.HTTP_403_FORBIDDEN)

        device.active = False
        device.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_logs(self, request, device_id):
        dev_user = request.user
        dev_user = request.user
        device = dev_user.device_list(return_objects=True, device_id=device_id)
        if isinstance(device, list):
            device = [
                x for x in device if x.ip_address == device_id
            ]
            if len(device) == 0:
                return Response(status=status.HTTP_404_NOT_FOUND)
        
        if device is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not dev_user.has_permission(settings.PERMISSIONS_ADMIN):
            return Response(status=status.HTTP_403_FORBIDDEN)
        
        date_str = request.query_params.get("date", None)
        format = request.query_params.get("format", None)
        if format is None:
            format = "file"
        if date_str is None:
            date_str = timezone.now().strftime("%Y-%m-%d")
        log_file = os.path.join(settings.MEDIA_ROOT, f"device-logs/device-{device.ip_address}-{date_str}.log")
        if os.path.exists(log_file):
            if format == "file":
                response = FileResponse(open(log_file, "rb"))
                return response
            else:
                logs_data = None
                with open(log_file, "r") as f:
                    logs_data = f.readlines()
                return Response(status=status.HTTP_200_OK, data={"logs": logs_data})
        return Response(status=status.HTTP_404_NOT_FOUND)

    def get_config(self, request, device_id):
        dev_user = request.user
        dev_user = request.user
        device, is_admin = is_device_admin(dev_user, device_id)
        if device is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not is_admin:
            return Response(status=status.HTTP_403_FORBIDDEN)
        
        # get the latest config data
        cfg = DeviceConfig.objects.filter(
            device=device,
        ).order_by('-created_at').first()
        if cfg is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        data = {
            "id": cfg.id,
            "data": cfg.data,
            "group_name": cfg.group_name,
            "version": cfg.version,
            "description": cfg.description,
            "active": cfg.active,
            "created_at": cfg.created_at.strftime(settings.TIME_FORMAT_STRING) if cfg.created_at is not None else None,
            "updated_at": cfg.updated_at.strftime(settings.TIME_FORMAT_STRING) if cfg.updated_at is not None else None,
        }
        return Response(data=data)

    def get_commands(self, request, device_id):
        dev_user = request.user
        dev_user = request.user
        device, is_admin = is_device_admin(dev_user, device_id)
        if device is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not is_admin:
            return Response(status=status.HTTP_403_FORBIDDEN)
        
        page_size = int(request.query_params.get("page_size", 10))
        page = int(request.query_params.get("page", 0))
        if page < 0:
            page = 0
        if page_size < 1:
            page_size = 10
        elif page_size > 100:
            page_size = 100
        commands = Command.objects.filter(
            device=device
        ).select_related('device').order_by('-command_in_time')
        total_commands = commands.count()
        commands = commands[page*page_size: (page+1)*page_size]
        commands_data = []
        for command in commands:
            commands_data.append({
                "id": command.id,
                "device_id": str(command.device.id),
                "command": command.command,
                "param": command.param,
                "response": command.response,
                "status": command.status,
                "command_in_time": command.command_in_time.strftime(settings.TIME_FORMAT_STRING) if command.command_in_time is not None else None,
                "command_read_time": command.command_read_time.strftime(settings.TIME_FORMAT_STRING) if command.command_read_time is not None else None,
                "response_time": command.response_time.strftime(settings.TIME_FORMAT_STRING) if command.response_time is not None else None,
            })
        data = {
            "total": total_commands,
            "page": page,
            "page_size": page_size,
            "commands": commands_data
        }
        return Response(data=data)
