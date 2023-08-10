import logging
from datetime import datetime

import pytz
import simplejson as json
from dashboard.data_scripts.data_update_signal_receiver import \
    update_device_info_on_meter_data_update
from device.clickhouse_models import MeterData, create_model_instance
from device.models import Meter, RawData
from device_schemas.device_types import IOT_GW_DEVICES
from device_schemas.schema import validate_data_schema
from django.conf import settings

from utils import detect_and_save_meter_loads

logger = logging.getLogger('django')

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
        data_arrival_time = datetime.utcnow()

    meter_data['data_arrival_time'] = data_arrival_time
    meter_data['meter'] = meter

    if extra_data:
        meter_data[EXTRA_METER_DATA_FIELD] = json.dumps(extra_data)
    return meter_data


def process_raw_data(device, message_data, channel='unknown', data_type='unknown'):
    config_data = message_data.get("config", {})
    dev_type = config_data.get("devType")

    if dev_type is None:
        dev_types = [x.name for x in device.types.all()]
        dev_type = dev_types[-1] if len(dev_types) > 0 else None
    logger.info(f"Data from {dev_type} device: {message_data}")

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
        data_arrival_time = datetime.utcnow()

    raw_data = RawData(
        device=device,
        channel=channel,
        data_type=data_type,
        data_arrival_time=data_arrival_time,
        data=message_data
    )
    raw_data.save()

    other_data = device.other_data
    if other_data is None:
        other_data = {}

    other_data["last_data_sync_time"] = data_arrival_time.strftime(settings.TIME_FORMAT_STRING)
    device.other_data = other_data
    device.save()

    if dev_type in IOT_GW_DEVICES:
        configured_schema_type = other_data.get("data_schema_type")
        if configured_schema_type is None:
            configured_schema_type = dev_type
        last_raw_data = get_latest_raw_data(device)
        validated_data = validate_data_schema(configured_schema_type, message_data, last_raw_data)
        if validated_data is None:
            logger.error(f"Invalid data! for schema {dev_type}. Data: {message_data}")
            return "Invalid data! Data doesn't match the schema configured for the device."

        logger.info(f"Validated data for schema {dev_type} is: {validated_data}")
        message_data = validated_data

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

    # Skip if only status meter data is there
    if len(meters_names_found) == 1 and meters_names_found[0] == "status_meter":
        return ""

    load_data = None
    if other_data.get("device_load_detection_on", False):
        load_data = detect_and_save_meter_loads(
            device,
            meters_and_data,
            data_arrival_time
        )
    update_device_info_on_meter_data_update(device, meters_and_data, load_data, data_arrival_time)

    return ""
