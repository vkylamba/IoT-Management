import json
import logging
import re
from datetime import datetime

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from device.models import Device
from device_schemas.device_types import IOT_GW_DEVICES
from django.conf import settings
from api.utils import process_raw_data


logger = logging.getLogger('application')

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
            resp = f"CONFIG[2] {device.numeric_id}"

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
