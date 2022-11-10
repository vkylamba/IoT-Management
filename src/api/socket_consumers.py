import json
import logging
import re
from datetime import datetime

from asgiref.sync import async_to_sync, sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from device.clickhouse_models import (DerivedData, MeterData,
                                      create_model_instance)
from device.models import Device, Meter, RawData
from device_schemas.device_types import IOT_GW_DEVICES
from device_schemas.schema import validate_data_schema
from django.conf import settings

logger = logging.getLogger('django')
# logger = logging.getLogger('application')

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
            if key in AVAILABLE_METER_DATA_FIELDS.keys() and isinstance(val, AVAILABLE_METER_DATA_FIELDS[key]):
                meter_data[key] = val
            else:
                extra_data["key"] = val

    if data_arrival_time is None:
        data_arrival_time = datetime.utcnow()

    meter_data['data_arrival_time'] = data_arrival_time
    meter_data['meter'] = meter

    if extra_data:
        meter_data[EXTRA_METER_DATA_FIELD] = json.dumps(extra_data)
    return meter_data


def process_raw_data(device, message_data):
    data_arrival_time = datetime.utcnow()
    last_raw_data = get_latest_raw_data(device)
    raw_data = RawData(
        device=device,
        data_arrival_time=data_arrival_time,
        data=message_data
    )
    raw_data.save()

    config_data = message_data.get("config", {})
    dev_type = config_data.get("devType", "")

    if dev_type in IOT_GW_DEVICES:
        configured_schema_type = device.other_data.get("data_schema_type")
        if configured_schema_type is None:
            configured_schema_type = dev_type

        validated_data = validate_data_schema(configured_schema_type, message_data, last_raw_data)
        if validated_data is not None:
            message_data = validated_data

    meters_and_data = []
    for meter_name in message_data:
        if 'meter' not in meter_name:
            continue
        if all(value == None for value in message_data.get(meter_name, {}).values()):
            continue
        meters = Meter.objects.filter(
            name=meter_name,
            device=device
        )
        if meters.count() == 0:
            meter = create_model_instance(Meter, {
                "name": meter_name,
                "device": device
            })
        else:
            meter = meters[0]
        try:
            meter_data = filter_meter_data(message_data, meter, data_arrival_time)
            data_obj = create_model_instance(
                MeterData,
                meter_data
            )
            meters_and_data.append({
                "meter": meter,
                "data": meter_data
            })
        except TypeError as e:
            logger.exception(e)

# @database_sync_to_async
def process_device_message_sync(message):
    device = None
    resp = "Error processing message"
    time_to_sync = False
    utc_timestamp = int(datetime.utcnow().timestamp())

    if "HEARTBEAT" in message:
        logger.debug("heartbeat message received.")
        resp = f"HEARTBEAT_ACK [{utc_timestamp}]"
        message_mac = re.sub(r"HEARTBEAT\s\[\d+\]\s", '', message)
        device_mac = message_mac.strip('[]')
        device_id = message.replace(f" {message_mac}", "").strip(f"HEARTBEAT []")
        if device_id != '0':
            device = Device.objects.filter(
                id=device_id
            ).first()
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

                other_data["last_heartbeat_time"] = datetime.utcnow().strftime(settings.TIME_FORMAT_STRING)
                if time_to_sync:
                    other_data["last_data_sync_time"] = other_data["last_heartbeat_time"]
                device.other_data = other_data
                device.save()
            elif device_mac:
                # Create new device
                device = Device.objects.filter(
                    mac=device_mac
                ).first()
                if not device:
                    device = Device(
                        mac=device_mac,
                        other_data={
                            "last_heartbeat_time": datetime.utcnow().strftime(settings.TIME_FORMAT_STRING)
                        }
                    )
                    device.save()
    else:
        try:
            message_data = json.loads(message)
            logger.debug("Data received: ", message)
        except Exception as e:
            logger.error(f"Error parsing data as json. Data is {message}, error: {e}")
            message_data = {}

        config_data = message_data.get("config", {})
        device_mac = config_data.get("mac")

        device = None
        if device_mac is not None:
            device = Device.objects.filter(
                mac=device_mac
            ).first()
            if not device:
                logger.info(f"New device detected with mac: {device_mac}")
                device = Device(
                    mac=device_mac,
                    alias="new device",
                    other_data=config_data
                )
                time_to_sync = True
                device.save()

            logger.info(f"Device mac: {device_mac}")

            process_raw_data(device, message_data)
            resp = "OK"

        if device is not None and device.id != config_data.get('devId'):
            resp = "CONFIG[2] {%s}" % device.id

    if device is not None:
        command = device.get_command()
        if command is not None:
            command.status = 'E'
            command.command_read_time = datetime.utcnow()
            command.save()
            resp = f"{command.command}{command.param}"
        elif time_to_sync:
            resp = "SYNC [0] {0}"
    
    return resp


class InputDataConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.client = self.scope['client']
        self.room_name = '_'.join([str(x) for x in self.client])
        self.room_group_name = 'device_%s' % self.room_name
        logger.debug(f"Connection request from client: {self.room_group_name}")

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
    
    async def disconnect(self, close_code):
        # Leave room group
        logger.info(f"Disconnecting from {self.room_group_name}")
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        logger.info(f"Data received from {self.room_group_name}: {text_data}")
        resp = await sync_to_async(self.device_message)({"message": text_data})
        await self.send(text_data=resp)

    def device_message(self, event):
        message = event['message']
        logger.info(f"processing device message {message}")

        resp = "Exception processing data"
        try:
            resp = process_device_message_sync(message)
        except Exception as ex:
            logger.exception(f"Exception processing data: {message}")
            logger.exception(ex)

        logger.info(f"Sending to {self.room_group_name}: {resp}")
        return resp
