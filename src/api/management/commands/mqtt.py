import json
import logging
import time

import paho.mqtt.client as mqtt
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand

from api.utils import process_raw_data
from device.models import Command as CommandsModal
from device.models import Device, DeviceType
from device_schemas.device_types import IOT_GW_DEVICES

logger = logging.getLogger('application')


ROOT_CA_FILE_PATH = "root_ca.crt"

CLIENT_SYSTEM_STATUS_TOPIC_TYPE = "status"
CLIENT_METERS_DATA_TOPIC_TYPE = "meters-data"
CLIENT_MODBUS_DATA_TOPIC_TYPE = "modbus-data"
CLIENT_UPDATE_RESP_TOPIC_TYPE = "update-response"
CLIENT_HEARTBEAT_RESP_TOPIC_TYPE = "heartbeat"
CLIENT_COMMAND_RESP_TOPIC_TYPE = "command"

MEROSS_DEVICE_DATA_TOPIC_TYPE = "publish"

CLIENT_COUNT_TOPIC = "$SYS/broker/clients/connected"


MQTT_ENABLED_DEVICE_TYPES = {
    'devices': {
        'topic_prefix': 'Devtest',
        'command_topic': 'command'
    }
}


class Command(BaseCommand):

    """
        Command to start mqtt service.
    """

    help = 'Starts the mqtt service.'

    def handle(self, *args, **options):
        while True:
            try:
                client = mqtt.Client()
                client.on_connect = self.on_connect
                client.on_message = self.on_message
                
                client.username_pw_set(settings.MQTT_USER, settings.MQTT_PASSWORD)
                client.tls_set(ROOT_CA_FILE_PATH)
                client.tls_insecure_set(False)

                client.connect(
                    host=settings.MQTT_BROKER,
                    port=int(settings.MQTT_PORT),
                    keepalive=settings.MQTT_KEEPALIVE
                )

                client.loop_start()
                
                self.check_and_send_commands(client)

                # client.loop_forever()
            except Exception as ex:
                logger.exception(ex)
            time.sleep(10)

    def on_connect(self, mqtt_client, user_data, flags, rc):
        if rc == 0:
            logger.info('MQTT connected successful')
            self.subscribe_all_topics(mqtt_client)
            # self.subscribe_active_clients_topic(mqtt_client)
        else:
            logger.info('MQTT, Bad connection. Code:', rc)

    def on_message(self, mqtt_client, user_data, msg):
        logger.info(f'Received message on topic: {msg.topic} with payload: {msg.payload}')
        self.process_message(msg)

    def subscribe_all_topics(self, mqtt_client):
        topic = "#"
        mqtt_client.subscribe(topic)

    def subscribe_active_clients_topic(self, mqtt_client):
        topic = CLIENT_COUNT_TOPIC
        mqtt_client.subscribe(topic)

    def process_message(self, msg):
        # Topic is in the following format for IoT devices:
        # /Devtest/devices/Dev-test/meters-data
        message_topic = msg.topic
        message_payload = msg.payload

        topic_data_list = message_topic.split("/")
        topic_data_length = len(topic_data_list)
        if topic_data_length >= 4:
            topic_type = topic_data_list[topic_data_length-1]
            device_name = topic_data_list[topic_data_length-2]
            group_name = topic_data_list[topic_data_length-3]

            if topic_type in [
                CLIENT_SYSTEM_STATUS_TOPIC_TYPE,
                CLIENT_METERS_DATA_TOPIC_TYPE,
                CLIENT_MODBUS_DATA_TOPIC_TYPE,
                CLIENT_UPDATE_RESP_TOPIC_TYPE,
                MEROSS_DEVICE_DATA_TOPIC_TYPE
            ]:
                logger.debug("MQTT data, group: %s, device: %s, topic: %s", group_name, device_name, topic_type)
                device = self.find_device(group_name, device_name, topic_type)
                message_data = json.loads(message_payload)
                process_raw_data(device, message_data, channel='mqtt', data_type=topic_type)
            elif topic_type not in [CLIENT_HEARTBEAT_RESP_TOPIC_TYPE, CLIENT_COMMAND_RESP_TOPIC_TYPE]:
                logger.error("MQTT unknown topic: %s", topic_type)
        else:
            logger.error("MQTT unknown topic: %s", msg.topic)

    def find_device(self, group_name, device_name, topic_type):

        dev_identifier = f"devices_list_cached_{group_name}_{device_name}"
        device_id = cache.get(dev_identifier)
        device = None
        if device_id is None:
            device = Device.objects.filter(
                alias=device_name,
                # types__name__in=group_name
            ).first()
            if device is None:
                dev_type, created = DeviceType.objects.get_or_create(
                    name=group_name
                )
                if created:
                    dev_type.save()
                device = Device(
                    alias=device_name
                )
                device.save()
                device.types.add(dev_type)
        else:
            device = Device.objects.filter(
                id=device_id
            ).first()

        if device_id is None and device:
            device_id = str(device.id)
            cache.set(dev_identifier, device_id, settings.DEVICE_PROPERTY_UPDATE_DELAY_MINUTES)

        return device

    def check_and_send_commands(self, client):
        """_summary_

        Args:
            client (_type_): _description_
        """
        # Get unsent commands
        last_cmd_id = None
        while True:
            try:
                commands = CommandsModal.objects.filter(
                    status='P'
                ).prefetch_related('device__types')

                if last_cmd_id is not None:
                    commands = commands.filter(
                        pk__gt=last_cmd_id
                    ).orderby('-command_in_time')

                for command in commands:
                    last_cmd_id = command.pk
                    device = command.device
                    device_types = [x.name for x in device.types]
                    for device_type_name in device_types:
                        cmd_cfg = MQTT_ENABLED_DEVICE_TYPES.get(device_type_name)
                        if cmd_cfg is not None:
                            topic_prefix = cmd_cfg.get('topic_prefix')
                            command_topic = cmd_cfg.get('command_topic')
                            topic = f"/{topic_prefix}/{device_type_name}/{device.alias}/{command_topic}"
                            client.publish(cmd_cfg.get('command_topic'), command.param)
                    command.status = 'E'
                    command.save()

            except Exception as ex:
                logger.exception(ex)
            time.sleep(60)