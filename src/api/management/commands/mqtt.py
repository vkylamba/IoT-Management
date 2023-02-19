import json
import logging
import time

import paho.mqtt.client as mqtt
from api.utils import process_raw_data
from device.models import Device, DeviceType
from device_schemas.device_types import IOT_GW_DEVICES
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand

logger = logging.getLogger('application')


ROOT_CA_FILE_PATH = ".cert/root_ca.crt"

CLIENT_SYSTEM_STATUS_TOPIC_TYPE = "status"
CLIENT_METERS_DATA_TOPIC_TYPE = "meters-data"
CLIENT_MODBUS_DATA_TOPIC_TYPE = "modbus-data"
CLIENT_UPDATE_RESP_TOPIC_TYPE = "update-response"
CLIENT_HEARTBEAT_RESP_TOPIC_TYPE = "heartbeat"
CLIENT_COMMAND_RESP_TOPIC_TYPE = "command"

MEROSS_DEVICE_DATA_TOPIC_TYPE = "publish"

CLIENT_COUNT_TOPIC = "$SYS/broker/clients/connected"


class Command(BaseCommand):

    """
        Command to start telegram bot.
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

                client.loop_forever()
            except Exception as ex:
                logger.exception(ex)
            time.sleep(10)

    def on_connect(self, mqtt_client, user_data, flags, rc):
        if rc == 0:
            logger.info('MQTT connected successful')
            self.subscribe_all_topics(mqtt_client)
            self.subscribe_active_clients_topic(mqtt_client)
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
                process_raw_data(device, message_data)
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
                alias__iexact=device_name,
                types__name__in=group_name
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