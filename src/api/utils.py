
import logging
import re
from copy import deepcopy
from datetime import datetime

import pytz
import simplejson as json
from device.clickhouse_models import MeterData, create_model_instance
from device.models import (Device, DeviceStatus, Meter, RawData, StatusType,
                           User, UserDeviceType)
from device_schemas.device_types import IOT_GW_DEVICES
from device_schemas.schema import (extract_data, translate_data_from_schema,
                                   validate_data_schema, validate_schema)
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.db.utils import DatabaseError
from django.utils import timezone
from event.models import DeviceEvent, EventHistory, EventType
from notification.models import Notification

from utils import detect_and_save_meter_loads
from device.log_handler import set_device_for_logger
from utils.weather import get_weather_data_cached

logger = logging.getLogger('device')

AVAILABLE_METER_DATA_FIELDS = {
        "voltage": float,
        "current": float,
        "power": float,
        "frequency": float,
        "energy": float,
        "runtime": int,
        "humidity": float,
        "temperature": float,
        "latitude": float,
        "longitude": float,
        "state": int,
        "cpu_temperature": float,
}

EXTRA_METER_DATA_FIELD = "more_data"

ALARM_TYPE_IDS_CACHE_KEY = 'alarm_eval:type_ids:v1'
ALARM_EVENT_TYPE_CACHE_KEY_PREFIX = 'alarm_eval:event_type:'
ALARM_TYPE_IDS_CACHE_TIMEOUT_SECONDS = 120
ALARM_EVENT_TYPE_CACHE_TIMEOUT_SECONDS = 300


def create_device_status_with_timestamp(
    *,
    name,
    device,
    user,
    status_data,
    created_at,
):
    status = DeviceStatus(
        name=name,
        device=device,
        user=user if user is not None and user.is_authenticated else None,
        status=status_data,
        created_at=created_at,
        updated_at=created_at,
    )

    created_at_field = status._meta.get_field('created_at')
    updated_at_field = status._meta.get_field('updated_at')
    original_created_auto_now_add = created_at_field.auto_now_add
    original_updated_auto_now_add = updated_at_field.auto_now_add

    try:
        created_at_field.auto_now_add = False
        updated_at_field.auto_now_add = False
        status.save(force_insert=True)
    finally:
        created_at_field.auto_now_add = original_created_auto_now_add
        updated_at_field.auto_now_add = original_updated_auto_now_add

    return status


def generate_device_alias(dev_identifier_field, dev_id):
    dev_identifier_fields = dev_identifier_field.split('.')
    dev_identifier_field = dev_identifier_fields[-1]
    dev_identifier_fields = re.split(' |,|-|_', dev_identifier_field.lower())
    names_to_skip = [
        '#', 'id'
    ]
    alias = ''
    for field_name in dev_identifier_fields:
        if field_name not in names_to_skip:
            if alias != '':
                alias += '-'
            alias += field_name.upper()
    return alias + '-' + str(dev_id)


def assign_ip_address_to_existing_user_devices(user: User, user_device_type: UserDeviceType):
    subnet = user.subnet_mask
    dev_identifier = user_device_type.identifier_field
    dev_identifier = generate_device_alias(dev_identifier, '')
    subnet = subnet.split('/')
    if len(subnet) > 1:
        subnet_1 = subnet[0].strip()
        subnet_1 = '.'.join(subnet_1.split('.')[:-1])
        subnet_start = User.address_string_to_numeric(subnet[0].strip())
        subnet_end = subnet_start + int(subnet[1].strip())
        # Now figure out the devices which belongs to this user
        max_address = subnet_start
        devices_with_ip_address = Device.objects.filter(
            alias__istartswith=dev_identifier,
            ip_address__istartswith=subnet_1
        )
        for device in devices_with_ip_address:
            dev_address = device.ip_address
            if dev_address is None or device.active is False:
                continue
            dev_address = User.address_string_to_numeric(dev_address)
            if subnet_start <= dev_address and dev_address < subnet_end:
                if max_address is None or dev_address > max_address:
                    max_address = dev_address
        devices_without_ip_address = Device.objects.filter(
            alias__istartswith=dev_identifier,
            ip_address__isnull=True
        )
        for device in devices_without_ip_address:
            max_address += 1
            device.ip_address = User.address_numeric_to_string(max_address)
        
        Device.objects.bulk_update(devices_without_ip_address, ['ip_address'])


def merge_device_other_data(device: Device, updates: dict):
    latest_device = Device.objects.filter(pk=device.pk).first()
    other_data = dict((latest_device.other_data if latest_device else device.other_data) or {})
    other_data.update(updates)
    device.other_data = other_data
    device.save()
    return other_data


def get_or_create_user_device(user: User, data: json) -> Device:
    user_dev_types = UserDeviceType.objects.filter(
        user=user
    )
    device = None
    user_devices, next_address = user.device_list(return_objects=True, return_next_address=True)

    for user_dev_type in user_dev_types:
        dev_identifier_field = user_dev_type.identifier_field
        if user_dev_type.data_schema is not None:
            schema_valid = validate_schema(user_dev_type.data_schema, data)
            if schema_valid:
                dev_id = extract_data(dev_identifier_field, data)
                if dev_id:
                    dev_id_str = str(dev_id)
                    dev = [d for d in user_devices if str(d.numeric_id) == dev_id_str or d.ip_address == dev_id_str]
                    if len(dev) == 0:
                        device = Device(
                            alias=generate_device_alias(dev_identifier_field, dev_id),
                            device_type=user_dev_type,
                            ip_address=next_address,
                        )
                        if isinstance(dev_id, int):
                            device.numeric_id = dev_id
                        device.save()
                        break
                    else:
                        device = dev[0]
                        device.device_type = user_dev_type
                        device.save()
                        break
    return device

def get_latest_raw_data(device):
    try:
        raw_data = RawData.objects.filter(
            device=device
        ).order_by(
            '-data_arrival_time'
        )[0]
        return json.loads(raw_data.data)
    except Exception as ex:
        return None


def get_local_day_start_utc(device, reference_time=None):
    if reference_time is None:
        local_now = device.get_local_time()
    else:
        if timezone.is_naive(reference_time):
            reference_time = timezone.make_aware(
                reference_time,
                timezone.get_current_timezone(),
            )

        device_timezone = device.get_timezone()
        if device_timezone is not None and reference_time.tzinfo is not None:
            local_now = reference_time.astimezone(device_timezone)
        else:
            local_now = reference_time

    local_day_start = local_now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    if local_day_start.tzinfo is None:
        return local_day_start
    return local_day_start.astimezone(pytz.utc)


def _normalize_raw_snapshot(raw_snapshot):
    if raw_snapshot is None:
        return None
    if hasattr(raw_snapshot, 'data'):
        return raw_snapshot.data
    if isinstance(raw_snapshot, dict):
        wrapper_keys = {'data', 'data_arrival_time', 'data_type', 'channel'}
        if 'data' in raw_snapshot and set(raw_snapshot.keys()).issubset(wrapper_keys):
            return raw_snapshot.get('data')
        return raw_snapshot
    return None


def _merge_raw_snapshot(base_snapshot, incoming_snapshot, overwrite=True):
    base_snapshot = dict(base_snapshot or {})
    incoming_snapshot = _normalize_raw_snapshot(incoming_snapshot) or {}

    for key, value in incoming_snapshot.items():
        existing_value = base_snapshot.get(key)
        if isinstance(existing_value, dict) and isinstance(value, dict):
            base_snapshot[key] = _merge_raw_snapshot(
                existing_value,
                value,
                overwrite=overwrite,
            )
        elif key not in base_snapshot or overwrite:
            base_snapshot[key] = value

    return base_snapshot


def _get_status_queryset_for_day(user, device, day_start_utc, as_of_time=None):
    if user is not None and user.is_authenticated:
        statuses = DeviceStatus.objects.filter(
            Q(user=user) | Q(device=device)
        )
    else:
        statuses = DeviceStatus.objects.filter(device=device)

    statuses = statuses.filter(created_at__gte=day_start_utc)
    if as_of_time is not None:
        statuses = statuses.filter(created_at__lte=as_of_time)
    return statuses.order_by('created_at')


def build_status_processing_context(user, device, last_raw_data, as_of_time=None):
    day_start_utc = get_local_day_start_utc(device, reference_time=as_of_time)

    statuses_today = _get_status_queryset_for_day(
        user,
        device,
        day_start_utc,
        as_of_time=as_of_time,
    )
    raw_data_today = RawData.objects.filter(
        device=device,
        data_type='meters-data',
        data_arrival_time__gte=day_start_utc
    )
    if as_of_time is not None:
        raw_data_today = raw_data_today.filter(data_arrival_time__lte=as_of_time)
    raw_data_today = raw_data_today.order_by('data_arrival_time')

    raw_data_first = {}
    raw_data_last = {}
    for raw_data_point in raw_data_today:
        raw_data_first = _merge_raw_snapshot(
            raw_data_first,
            raw_data_point,
            overwrite=False,
        )
        raw_data_last = _merge_raw_snapshot(
            raw_data_last,
            raw_data_point,
            overwrite=True,
        )

    raw_data_last = _merge_raw_snapshot(raw_data_last, last_raw_data, overwrite=True)

    if not raw_data_first and raw_data_last:
        raw_data_first = dict(raw_data_last)

    status_first = {}
    status_last = {}
    last_status_models_by_target = {}

    for st_dt in statuses_today:
        if st_dt.name not in status_first:
            status_first[st_dt.name] = st_dt.status
        status_last[st_dt.name] = st_dt.status
        last_status_models_by_target[st_dt.name] = st_dt

    if raw_data_first:
        status_first['raw'] = raw_data_first
    if raw_data_last:
        status_last['raw'] = raw_data_last

    existing_statuses = {
        'firstToday': status_first,
        'lastToday': status_last
    }
    return {
        'existing_statuses': existing_statuses,
        'last_status_models_by_target': last_status_models_by_target,
        'current_raw_data': dict(status_last.get('raw', {}) or {}),
        'day_start_utc': day_start_utc,
    }


def merge_raw_into_status_context(status_processing_context, raw_snapshot):
    if status_processing_context is None:
        return None

    normalized_snapshot = _normalize_raw_snapshot(raw_snapshot) or {}
    existing_statuses = status_processing_context.setdefault(
        'existing_statuses',
        {'firstToday': {}, 'lastToday': {}},
    )
    first_today = existing_statuses.setdefault('firstToday', {})
    last_today = existing_statuses.setdefault('lastToday', {})

    first_today['raw'] = _merge_raw_snapshot(
        first_today.get('raw'),
        normalized_snapshot,
        overwrite=False,
    )
    last_today['raw'] = _merge_raw_snapshot(
        last_today.get('raw'),
        normalized_snapshot,
        overwrite=True,
    )
    status_processing_context['current_raw_data'] = dict(last_today.get('raw', {}) or {})
    return status_processing_context['current_raw_data']


def record_status_in_context(status_processing_context, target_type, status_model):
    if status_processing_context is None or status_model is None:
        return

    existing_statuses = status_processing_context.setdefault(
        'existing_statuses',
        {'firstToday': {}, 'lastToday': {}},
    )
    first_today = existing_statuses.setdefault('firstToday', {})
    last_today = existing_statuses.setdefault('lastToday', {})

    if target_type not in first_today:
        first_today[target_type] = deepcopy(status_model.status)
    last_today[target_type] = deepcopy(status_model.status)
    status_processing_context.setdefault('last_status_models_by_target', {})[
        target_type
    ] = status_model


def get_existing_status_data_for_today(user, device, last_raw_data, as_of_time=None):

    status_processing_context = build_status_processing_context(
        user,
        device,
        last_raw_data,
        as_of_time=as_of_time,
    )
    return status_processing_context['existing_statuses']


def get_status_types_for_device(user, device):
    if user is not None and user.is_authenticated:
        return StatusType.objects.filter(
            Q(user=user) | Q(device_type=device.type) | Q(device=device)
        )
    if device.type is not None:
        return StatusType.objects.filter(
            Q(device_type=device.type) | Q(device=device)
        )
    return StatusType.objects.filter(
        device=device
    )



def filter_meter_data(data, meter, data_arrival_time):
    meter_name = meter.name
    meter_data = {}
    extra_data = {}
    for key, val in data.get(meter_name, {}).items():
        if val is not None:
            if key in AVAILABLE_METER_DATA_FIELDS.keys(): # and isinstance(val, AVAILABLE_METER_DATA_FIELDS[key]):
                meter_data[key] = val
            else:
                extra_data[key] = val

    if data_arrival_time is None:
        data_arrival_time = timezone.now()

    meter_data['data_arrival_time'] = data_arrival_time
    meter_data['meter'] = meter

    if extra_data:
        meter_data[EXTRA_METER_DATA_FIELD] = json.dumps(extra_data)
    return meter_data


def _extract_alarm_status_value(status_dict, status_key):
    if status_dict is None or not isinstance(status_dict, dict):
        return None

    current_value = status_dict
    for key in str(status_key).split('.'):
        if not isinstance(current_value, dict):
            return None
        current_value = current_value.get(key)

    return current_value


def _is_numeric_alarm_value(value):
    if value is None:
        return False, None
    try:
        return True, float(value)
    except (TypeError, ValueError):
        return False, None


def _is_alarm_match(current_value, operator, target_value):
    if current_value is None:
        return False

    operator = operator or EventType.ALARM_OPERATOR_EQ
    current_is_number, current_numeric = _is_numeric_alarm_value(current_value)
    target_is_number, target_numeric = _is_numeric_alarm_value(target_value)

    if operator in {
        EventType.ALARM_OPERATOR_GT,
        EventType.ALARM_OPERATOR_GTE,
        EventType.ALARM_OPERATOR_LT,
        EventType.ALARM_OPERATOR_LTE,
    }:
        if not current_is_number or not target_is_number:
            return False
        if operator == EventType.ALARM_OPERATOR_GT:
            return current_numeric > target_numeric
        if operator == EventType.ALARM_OPERATOR_GTE:
            return current_numeric >= target_numeric
        if operator == EventType.ALARM_OPERATOR_LT:
            return current_numeric < target_numeric
        return current_numeric <= target_numeric

    if operator == EventType.ALARM_OPERATOR_CONTAINS:
        return str(target_value).lower() in str(current_value).lower()

    if current_is_number and target_is_number:
        if operator == EventType.ALARM_OPERATOR_NEQ:
            return current_numeric != target_numeric
        return current_numeric == target_numeric

    if operator == EventType.ALARM_OPERATOR_NEQ:
        return str(current_value) != str(target_value)
    return str(current_value) == str(target_value)


def _get_cached_alarm_type_ids():
    alarm_type_ids = cache.get(ALARM_TYPE_IDS_CACHE_KEY)
    if alarm_type_ids is not None:
        return alarm_type_ids

    try:
        alarm_type_ids = list(
            EventType.objects.filter(
                status_key__isnull=False,
                operator__isnull=False,
                target_value__isnull=False,
            ).values_list('id', flat=True)
        )
    except DatabaseError:
        try:
            event_types = EventType.objects.all().only('id', 'status_key', 'operator', 'target_value')
            alarm_type_ids = [
                event_type.id
                for event_type in event_types
                if event_type.status_key not in [None, '']
                and event_type.operator not in [None, '']
                and event_type.target_value not in [None, '']
            ]
        except Exception:
            logger.exception('Failed to resolve cached alarm event type ids.')
            alarm_type_ids = []

    cache.set(
        ALARM_TYPE_IDS_CACHE_KEY,
        alarm_type_ids,
        ALARM_TYPE_IDS_CACHE_TIMEOUT_SECONDS,
    )
    return alarm_type_ids


def _get_cached_event_type_alarm_rules(event_type_ids):
    if len(event_type_ids) == 0:
        return {}

    cache_keys = {
        event_type_id: f'{ALARM_EVENT_TYPE_CACHE_KEY_PREFIX}{event_type_id}'
        for event_type_id in event_type_ids
    }
    cached_items = cache.get_many(list(cache_keys.values()))

    event_types_map = {}
    missing_ids = []
    for event_type_id in event_type_ids:
        cached_value = cached_items.get(cache_keys[event_type_id])
        if cached_value is None:
            missing_ids.append(event_type_id)
            continue
        event_types_map[event_type_id] = cached_value

    if len(missing_ids) > 0:
        try:
            fetched_event_types = EventType.objects.filter(id__in=missing_ids)
        except DatabaseError:
            missing_ids_set = set(missing_ids)
            fetched_event_types = [
                event_type
                for event_type in EventType.objects.all().only('id', 'name', 'status_key', 'operator', 'target_value')
                if event_type.id in missing_ids_set
            ]
        cache_updates = {}
        for event_type in fetched_event_types:
            serialized_alarm_type = {
                'id': event_type.id,
                'name': event_type.name,
                'status_key': event_type.status_key,
                'operator': event_type.operator,
                'target_value': event_type.target_value,
            }
            event_types_map[event_type.id] = serialized_alarm_type
            cache_updates[cache_keys[event_type.id]] = serialized_alarm_type

        if cache_updates:
            cache.set_many(cache_updates, ALARM_EVENT_TYPE_CACHE_TIMEOUT_SECONDS)

    return event_types_map


def invalidate_alarm_evaluation_cache(event_type_ids=None):
    cache.delete(ALARM_TYPE_IDS_CACHE_KEY)
    if not event_type_ids:
        return

    cache.delete_many([
        f'{ALARM_EVENT_TYPE_CACHE_KEY_PREFIX}{event_type_id}'
        for event_type_id in event_type_ids
        if event_type_id is not None
    ])


def evaluate_device_status_alarms(device, status_snapshot, trigger_time=None):
    if status_snapshot is None or not isinstance(status_snapshot, dict):
        return

    alarm_type_ids = _get_cached_alarm_type_ids()
    if len(alarm_type_ids) == 0:
        return

    device_id = getattr(device, 'id', None)
    if device_id is None:
        return

    try:
        alarms = list(DeviceEvent.objects.all())
    except Exception:
        logger.exception('Failed to query device events for alarm evaluation.')
        return

    alarm_type_ids_set = set(alarm_type_ids)
    alarms = [
        alarm
        for alarm in alarms
        if getattr(alarm, 'device_id', None) == device_id
        and alarm.active is True
        and alarm.typ_id in alarm_type_ids_set
    ]
    alarms = sorted(
        alarms,
        key=lambda alarm: alarm.created_at or timezone.now(),
        reverse=True,
    )
    if len(alarms) == 0:
        return

    event_type_ids = [alarm.typ_id for alarm in alarms if alarm.typ_id is not None]
    event_types_map = _get_cached_event_type_alarm_rules(event_type_ids)
    evaluated_at = trigger_time or timezone.now()

    for alarm in alarms:
        event_type = event_types_map.get(alarm.typ_id)
        if event_type is None:
            continue

        status_key = event_type.get('status_key')
        operator = event_type.get('operator')
        target_value = event_type.get('target_value')

        current_value = _extract_alarm_status_value(status_snapshot, status_key)
        is_match = _is_alarm_match(current_value, operator, target_value)

        if is_match and not alarm.last_evaluation_match:
            message = f"{status_key} {operator} {target_value} (current: {current_value})"
            channels = [
                action.get('channel')
                for action in (alarm.actions_config or [])
                if action.get('channel')
            ]

            EventHistory.objects.create(
                device_event=alarm,
                result={
                    'status_key': status_key,
                    'operator': operator,
                    'target_value': target_value,
                    'status_value': str(current_value) if current_value is not None else None,
                    'status_snapshot': status_snapshot,
                    'message': message,
                    'channels': channels,
                }
            )

            for action in alarm.actions_config or []:
                method = action.get('method')
                if method is None:
                    continue

                template = None
                template_id = action.get('template_id')
                if template_id:
                    template = Notification.objects.filter(id=template_id).first()

                Notification.objects.create(
                    name=f"Alarm: {event_type.get('name')}",
                    user=alarm.user,
                    method=method,
                    title=(template.title if template else f"Device alarm for {device.ip_address}"),
                    text=(template.text if template else message),
                    emails=action.get('emails') or (template.emails if template else None),
                    data={
                        'device': device.ip_address,
                        'event_id': str(alarm.id),
                        'status_key': status_key,
                        'operator': operator,
                        'target_value': target_value,
                        'status_value': str(current_value) if current_value is not None else None,
                        'triggered_at': evaluated_at.strftime(settings.TIME_FORMAT_STRING),
                    },
                )

            alarm.last_trigger_time = evaluated_at

        alarm.last_evaluation_match = is_match
        alarm.save(update_fields=['last_trigger_time', 'last_evaluation_match'])


def process_raw_data(device, message_data, channel='unknown', data_type='unknown', user=None):
    config_data = message_data.get("config", {})
    dev_type_name = config_data.get("devType")
    dev_type = None
    set_device_for_logger(logger, device.ip_address)
    if dev_type_name is None:
        try:
            dev_type = device.device_type
            dev_type_name = device.device_type.code if device.device_type is not None else None
        except Exception as ex:
            logger.warning(ex)

    if dev_type is None:
        dev_types = [x.name for x in device.types.all()]
        dev_type_name = dev_types[-1] if len(dev_types) > 0 else None
    logger.info(f"Data from device type {dev_type_name}: {message_data}")

    # Save the raw data
    data_arrival_time = message_data.get("last_update_time")
    time_utc = message_data.get("timeUTC")
    if data_arrival_time is not None:
        data_arrival_time = datetime.strptime(
            data_arrival_time,
            "%Y-%m-%dT%H:%M:%S%z"
        )
        data_arrival_time = data_arrival_time.astimezone(pytz.utc)
    elif time_utc is not None:
        data_arrival_time = datetime.strptime(
            time_utc,
            "%Y-%m-%d %H:%M:%S"
        )
        data_arrival_time = data_arrival_time.astimezone(pytz.utc)
    else:
        data_arrival_time = timezone.now()

    # Remove apiKey from the raw data if exists
    if "apiKey" in message_data:
        message_data.pop("apiKey")

    raw_data = RawData(
        device=device,
        channel=channel,
        data_type=data_type,
        data_arrival_time=data_arrival_time,
        data=message_data
    )
    raw_data.save()

    other_data = merge_device_other_data(device, {
        "last_data_sync_time": data_arrival_time.strftime(settings.TIME_FORMAT_STRING)
    })

    if data_type == 'status':
        logger.info("Status data received, skipping meter data processing.")
        return ""

    last_raw_data = get_latest_raw_data(device)

    meters_and_data = []
    dev_meters_list = Meter.objects.filter(
        device=device
    )
    dev_meters = {}
    for dev_meter in dev_meters_list:
        dev_meters[dev_meter.name] = dev_meter

    meters_names_found = []
    for meter_name in message_data:
        if 'meter' not in meter_name:
            logger.warning(f"Skipping meter {meter_name}.")
            continue

        meters_names_found.append(meter_name)

        if all(value == None for value in message_data.get(meter_name, {}).values()):
            continue
        
        if dev_meters.get(meter_name) is None:
            meter = Meter(
                name=meter_name,
                device=device
            )
            meter.save()
        else:
            meter = dev_meters[meter_name]
        try:
            meter_data = filter_meter_data(message_data, meter, data_arrival_time)
            create_model_instance(
                MeterData,
                meter_data
            )
            meters_and_data.append({
                "meter": meter,
                "data": meter_data
            })
        except TypeError as e:
            logger.exception(e)

    weather_and_loads_data = {}
    if other_data.get("device_load_detection_on", False):
        # Skip if only status meter data is there
        if not(len(meters_names_found) == 1 and meters_names_found[0] == "status_meter"):
            try:
                weather_and_loads_data = detect_and_save_meter_loads(
                    device,
                    meters_and_data,
                    data_arrival_time
                )
                logger.info(f"Weather and loads data detected for device {device.ip_address}: {weather_and_loads_data}")
            except Exception as ex:
                logger.exception("Load detection error: %s", ex)

    try:
        update_user_and_device_statuses(user, device, raw_data, last_raw_data, weather_and_loads_data)
    except Exception as ex:
        logger.exception(ex)

    return ""


def update_user_and_device_statuses(
    user,
    device,
    raw_data,
    last_raw_data,
    weather_and_loads_data=None,
    status_created_at=None,
    status_types=None,
    status_processing_context=None,
    min_status_interval_minutes=10,
    enforce_min_status_interval=False,
):
    set_device_for_logger(logger, device.ip_address or str(device.id))

    # get status types, which should be updated
    if status_types is None:
        status_types = get_status_types_for_device(user, device)
    if status_types is None:
        logger.info(f"No status linked to device. {device}")
        return None

    if status_created_at is None:
        status_created_at = timezone.now()
    elif timezone.is_naive(status_created_at):
        status_created_at = timezone.make_aware(
            status_created_at,
            timezone.get_current_timezone(),
        )

    if min_status_interval_minutes is None:
        min_status_interval_minutes = 10
    min_status_interval_seconds = max(0, int(min_status_interval_minutes)) * 60

    if isinstance(raw_data, RawData):
        normalized_raw_data = raw_data.data
    else:
        normalized_raw_data = raw_data

    if status_processing_context is None:
        status_processing_context = build_status_processing_context(
            user,
            device,
            last_raw_data,
            as_of_time=status_created_at,
        )
    else:
        merge_raw_into_status_context(status_processing_context, normalized_raw_data)

    existing_statuses = status_processing_context.get('existing_statuses', {})
    current_raw_data = (
        status_processing_context.get('current_raw_data')
        or normalized_raw_data
        or {}
    )
    last_status_models_by_target = status_processing_context.setdefault(
        'last_status_models_by_target',
        {},
    )
    calculated_alarm_status_data = {}

    for status_type in status_types:
        schema = status_type.translation_schema
        if schema is not None:
            if isinstance(schema, list) and status_type.target_type != StatusType.STATUS_TARGET_METER:
                for x in schema:
                    x["target"] = status_type.target_type
                    x["name"] = status_type.name
                    # x["type"] = status_type.target_type
            elif isinstance(schema, dict):
                schema["target"] = status_type.target_type
                schema["name"] = status_type.name
                # schema["type"] = status_type.target_type

            validated_data = translate_data_from_schema(
                schema,
                current_raw_data,
                existing_statuses,
                weather_and_loads_data or {},
            )
            if validated_data is None:
                logger.warning(f"Invalid data! for status {status_type.name}. Data: {current_raw_data}")
                return "Invalid data! Data doesn't match the schema configured for the device/user."

            logger.info(f"Validated data for schema {status_type.name} is: {validated_data}")
            validated_status_data = validated_data.get(status_type.name, {})
            if isinstance(validated_status_data, dict):
                calculated_alarm_status_data.update(validated_status_data)
            if any(validated_status_data):
                # create a new status if last once was created at least 10 minutes ago
                last_status = last_status_models_by_target.get(status_type.target_type)
                create_new = True
                time_now = status_created_at
                if last_status is not None:
                    last_status_creation_time = last_status.created_at
                    if (time_now - last_status_creation_time).total_seconds() <= min_status_interval_seconds:
                        create_new = False
                else:
                    create_new = True
                if not create_new and last_status is not None and not enforce_min_status_interval:
                    # Create copies of the dicts and remove energy field for comparison
                    last_validated_data = last_status.status.copy() if isinstance(last_status.status, dict) else {}
                    current_validated_data = validated_data.copy() if isinstance(validated_data, dict) else {}
                    
                    # Remove energy field from both for comparison (handles both flat and nested dicts)
                    # Remove top-level energy field
                    last_validated_data.pop('energy', None)
                    current_validated_data.pop('energy', None)
                    
                    # Remove energy from nested dicts
                    # for key in list(last_validated_data.keys()):
                    #     if isinstance(last_validated_data[key], dict):
                    #         last_validated_data[key] = {k: v for k, v in last_validated_data[key].items() if k != 'energy'}
                    
                    # for key in list(current_validated_data.keys()):
                    #     if isinstance(current_validated_data[key], dict):
                    #         current_validated_data[key] = {k: v for k, v in current_validated_data[key].items() if k != 'energy'}

                    data_changed = last_validated_data != current_validated_data
                    if data_changed:
                        create_new = True
                        logger.debug(f"Status data changed for {status_type.target_type}, creating new status entry")
                elif not create_new:
                    create_new = True
                        
                if create_new:
                    status = create_device_status_with_timestamp(
                        name=status_type.target_type,
                        device=device,
                        user=user,
                        status_data=validated_data,
                        created_at=time_now,
                    )
                    record_status_in_context(
                        status_processing_context,
                        status_type.target_type,
                        status,
                    )
                if status_type.target_type == StatusType.STATUS_TARGET_DEVICE:
                    other_data = device.other_data
                    if other_data is None:
                        other_data = validated_status_data
                    else:
                        other_data.update(validated_status_data)
                    device.save()
                
                if status_type.target_type == StatusType.STATUS_TARGET_USER:
                    if user is not None and user.is_authenticated:
                        other_data = user.other_data
                        if other_data is None:
                            other_data = validated_status_data
                        else:
                            other_data.update(validated_status_data)
                        user.save()
                
                if status_type.target_type == StatusType.STATUS_TARGET_METER:
                    pass
                    # ToDo: Save meter data here

    if any(calculated_alarm_status_data):
        evaluate_device_status_alarms(
            device=device,
            status_snapshot=calculated_alarm_status_data,
            trigger_time=status_created_at,
        )


def replay_stored_raw_data(
    device,
    start_time,
    end_time,
    user=None,
    clear_existing_statuses=True,
    replay_status_interval_minutes=10,
    replay_target_types=None,
    progress_callback=None,
):
    replay_start_time = get_local_day_start_utc(device, reference_time=start_time)
    status_types = list(get_status_types_for_device(user, device) or [])
    if replay_target_types:
        allowed_target_types = set(replay_target_types)
        status_types = [
            status_type
            for status_type in status_types
            if status_type.target_type in allowed_target_types
        ]
    status_processing_context = {
        'existing_statuses': {'firstToday': {}, 'lastToday': {}},
        'last_status_models_by_target': {},
        'current_raw_data': {},
        'day_start_utc': replay_start_time,
    }
    raw_data_queryset = RawData.objects.filter(
        device=device,
        data_arrival_time__gte=replay_start_time,
        data_arrival_time__lt=end_time,
    ).order_by('data_arrival_time', 'id')
    total_raw_count = raw_data_queryset.count()

    deleted_status_count = 0
    if clear_existing_statuses:
        deleted_status_count, _ = DeviceStatus.objects.filter(
            device=device,
            created_at__gte=replay_start_time,
            created_at__lt=end_time,
        ).delete()

    processed_raw_count = 0
    replayed_raw_count = 0
    skipped_status_raw_count = 0

    def emit_progress(phase='replaying', force=False, raw_entry=None):
        if not callable(progress_callback):
            return

        if not force and processed_raw_count > 0 and processed_raw_count % 25 != 0:
            return

        if total_raw_count > 0:
            progress_percent = min(99, int((processed_raw_count / total_raw_count) * 100))
        else:
            progress_percent = 99

        progress_callback({
            'phase': phase,
            'processed_raw_count': processed_raw_count,
            'replayed_raw_count': replayed_raw_count,
            'skipped_status_raw_count': skipped_status_raw_count,
            'deleted_status_count': deleted_status_count,
            'total_raw_count': total_raw_count,
            'current_raw_time': (
                raw_entry.data_arrival_time.isoformat()
                if raw_entry is not None and raw_entry.data_arrival_time is not None
                else None
            ),
            'progress_percent': progress_percent,
        })

    emit_progress(phase='starting', force=True)

    for raw_entry in raw_data_queryset.iterator():
        processed_raw_count += 1

        if raw_entry.data_type == 'status':
            skipped_status_raw_count += 1
            continue

        stored_weather_data = get_weather_data_cached(
            device,
            use_cache=False,
            reference_time=raw_entry.data_arrival_time,
            allow_fetch=False,
            store_in_raw_data=False,
        )
        replay_context_data = {}
        if stored_weather_data:
            replay_context_data['weather'] = stored_weather_data

        update_user_and_device_statuses(
            user,
            device,
            raw_entry,
            raw_entry.data,
            replay_context_data,
            status_created_at=raw_entry.data_arrival_time,
            status_types=status_types,
            status_processing_context=status_processing_context,
            min_status_interval_minutes=replay_status_interval_minutes,
            enforce_min_status_interval=True,
        )

        if raw_entry.data_arrival_time >= start_time:
            replayed_raw_count += 1

        emit_progress(raw_entry=raw_entry)

    emit_progress(phase='completed', force=True)

    return {
        'processed_raw_count': processed_raw_count,
        'replayed_raw_count': replayed_raw_count,
        'skipped_status_raw_count': skipped_status_raw_count,
        'deleted_status_count': deleted_status_count,
        'total_raw_count': total_raw_count,
        'replay_status_interval_minutes': replay_status_interval_minutes,
        'replay_target_types': list(replay_target_types or []),
        'replay_start_time': replay_start_time,
        'start_time': start_time,
        'end_time': end_time,
    }
