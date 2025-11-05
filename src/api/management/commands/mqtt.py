import sys
from django.utils import timezone
import json
import logging
import time

from device.models.ota import DeviceConfig
import paho.mqtt.client as mqtt
from api.utils import process_raw_data
from device.models import Command as CommandsModal
from device.models import Device, DeviceType
from device_schemas.device_types import IOT_GW_DEVICES
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand

logger = logging.getLogger('django')

SOURCE_TYPE_MONA = "mona"
SOURCE_TYPE_BEKEN = "beken"

ROOT_CA_FILE_PATH = "root_ca.crt"

CLIENT_SYSTEM_STATUS_TOPIC_TYPE = "status"
CLIENT_METERS_DATA_TOPIC_TYPE = "meters-data"
CLIENT_SENSORS_DATA_TOPIC_TYPE = "sensors-data"
CLIENT_MODBUS_DATA_TOPIC_TYPE = "modbus-data"
CLIENT_DEVICE_PARAMS_TOPIC_TYPE = "params"
CLIENT_UPDATE_RESP_TOPIC_TYPE = "update-response"
CLIENT_CMD_RESP_TOPIC_TYPE = "cmd-resp"
CLIENT_CMD_REQ_TOPIC_TYPE = "cmd-req"
CLIENT_HEARTBEAT_RESP_TOPIC_TYPE = "heartbeat"
CLIENT_COMMAND_RESP_TOPIC_TYPE = "command"

MEROSS_DEVICE_DATA_TOPIC_TYPE = "publish"

CLIENT_COUNT_TOPIC = "$SYS/broker/clients/connected"


MQTT_ENABLED_DEVICE_COMMANDS = {
    'cmd-req': "/{dev_mqtt_user}/devices/{device_alias}/cmd-req",
    'update-trigger': "/{dev_mqtt_user}/devices/{device_alias}/update-trigger",
}


class Command(BaseCommand):

    """
        Command to start mqtt service.
    """

    help = 'Starts the mqtt service.'

    def handle(self, *args, **options):
        client = mqtt.Client()
        client.on_connect = self.on_connect
        client.on_disconnect = self.on_disconnect
        client.on_message = self.on_message
        # client.on_log = self.on_log
        client.on_subscribe = self.on_subscribe
        
        client.username_pw_set(settings.MQTT_USER, settings.MQTT_PASSWORD)
        
        if getattr(settings, "MQTT_USE_SSL", False):
            client.tls_set(ROOT_CA_FILE_PATH)
            client.tls_insecure_set(False)

        client.connect(
            host=settings.MQTT_BROKER,
            port=int(settings.MQTT_PORT),
            keepalive=settings.MQTT_KEEPALIVE
        )

        client.loop_start()
        self.loop_running = True
        self.check_and_send_commands(client)

    def on_connect(self, mqtt_client, user_data, flags, rc):
        if rc == 0:
            logger.info('MQTT connected successful')
            self.subscribe_all_topics(mqtt_client)
            # self.subscribe_active_clients_topic(mqtt_client)
        else:
            logger.info('MQTT, Bad connection. Code:', rc)

    def on_disconnect(self, mqtt_client, userdata, rc=0):
        logging.info("MQTT disconnected result code " + str(rc))
        mqtt_client.loop_stop()

    def on_message(self, mqtt_client, user_data, msg):
        logger.info(f'Received message on topic: {msg.topic} with payload: {msg.payload}')
        try:
            self.process_message(msg)
        except Exception as ex:
            logger.exception(f'Exception ocurred while processing MQTT message: {ex}')
            mqtt_client.loop_stop()
            self.loop_running = False
            sys.exit(500)

    def on_log(self, mqtt_client, obj, level, string):
        logger.info(f"{level}: {string}")
    
    def on_subscribe(self, userdata, mid, reason_code, properties):
        logger.info(f"subscription: {reason_code}, mid: {mid}, properties: {properties}")

    def subscribe_all_topics(self, mqtt_client):
        # topic = "#"
        # mqtt_client.subscribe(topic)
        topics = [
            CLIENT_SYSTEM_STATUS_TOPIC_TYPE,
            CLIENT_DEVICE_PARAMS_TOPIC_TYPE,
            CLIENT_METERS_DATA_TOPIC_TYPE,
            CLIENT_SENSORS_DATA_TOPIC_TYPE,
            CLIENT_MODBUS_DATA_TOPIC_TYPE,
            CLIENT_UPDATE_RESP_TOPIC_TYPE,
            CLIENT_CMD_RESP_TOPIC_TYPE,
            MEROSS_DEVICE_DATA_TOPIC_TYPE
        ]
        for topic in topics:
            topic_to_subscribe = f"/+/devices/+/{topic}"
            mqtt_client.subscribe(topic_to_subscribe)
            topic_to_subscribe = f"/+/devices/+/{topic}/+/+"
            mqtt_client.subscribe(topic_to_subscribe)

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
        source_device_type = SOURCE_TYPE_MONA
        process_data = True
        logger.debug("MQTT message on topic: %s", message_topic)
        if topic_data_length > 4:
            group_name = topic_data_list[1]
            device_name = topic_data_list[3]
            topic_type = topic_data_list[4]

            data_key_name = None
            data_key_val = message_payload
            if topic_data_length > 5:
                source_device_type = SOURCE_TYPE_BEKEN
                data_key_name = topic_data_list[5]
                data_key_val = message_payload
                process_data = False

            if source_device_type == SOURCE_TYPE_BEKEN:
                # Handle BEKEN device data collection
                device_cache_key = f"beken_data_{group_name}_{device_name}"
                device_data = cache.get(device_cache_key, {})
                
                # Add current data to the dict
                current_time = timezone.now()
                device_data[data_key_name] = data_key_val
                if 'timestamp' not in device_data:
                    device_data['timestamp'] = current_time.isoformat()
                device_data['last_update'] = current_time.isoformat()
                
                # Cache the updated data
                cache.set(device_cache_key, device_data, 300)  # 5 minutes cache
                
                # Check if data is older than 120 seconds
                first_timestamp = device_data.get('timestamp')
                first_time = timezone.datetime.fromisoformat(first_timestamp)
                time_diff = (current_time - first_time).total_seconds()
                
                if time_diff >= 119:
                    process_data = True
                    del device_data['timestamp']
                    del device_data['last_update']
                    message_payload = json.dumps(device_data)
                    cache.delete(device_cache_key)

            if topic_type in [
                CLIENT_SYSTEM_STATUS_TOPIC_TYPE,
                CLIENT_DEVICE_PARAMS_TOPIC_TYPE,
                CLIENT_METERS_DATA_TOPIC_TYPE,
                CLIENT_SENSORS_DATA_TOPIC_TYPE,
                CLIENT_MODBUS_DATA_TOPIC_TYPE,
                CLIENT_CMD_RESP_TOPIC_TYPE,
                CLIENT_UPDATE_RESP_TOPIC_TYPE,
                MEROSS_DEVICE_DATA_TOPIC_TYPE
            ] and (process_data or source_device_type == SOURCE_TYPE_MONA):
                logger.debug("MQTT data, group: %s, device: %s, topic: %s", group_name, device_name, topic_type)
                try:
                    message_data = json.loads(message_payload)
                except Exception:
                    logger.warning(f"Invalid json data: {message_payload}")
                    return
                
                device = self.find_device(group_name, device_name, topic_type)
                if topic_type == CLIENT_CMD_RESP_TOPIC_TYPE:
                    self.process_command_response(device, message_data)
                else:
                    process_raw_data(device, message_data, channel='mqtt', data_type=topic_type)
            elif not process_data:
                logger.debug("MQTT data cached for later processing, group: %s, device: %s, topic: %s", group_name, device_name, topic_type)
            elif topic_type not in [CLIENT_HEARTBEAT_RESP_TOPIC_TYPE, CLIENT_COMMAND_RESP_TOPIC_TYPE]:
                logger.warning("MQTT unknown topic: %s", topic_type)
        else:
            logger.warning("MQTT unknown topic: %s", msg.topic)

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

    def process_command_response(self, device, message_data):
        """
        Process command response message and update the matching command.
        
        Args:
            device: The device object
            message_data: Dict containing command response data
        """
        try:
            command_text = message_data.get('command', '')
            response = message_data.get('response', '')
            
            if not command_text or not device:
                logger.warning("Missing command or device in command response")
                return
            temp = command_text.split()
            cmd_name = temp[0] if temp else ''
            cmd_param = ' '.join(temp[1:]) if len(temp) > 1 else ''
            # Find the last matching command for this device that hasn't been responded to
            command = CommandsModal.objects.filter(
                device=device,
                command__icontains=cmd_name if cmd_name else '',  # Match first word of command
                param__icontains=cmd_param if cmd_param else '',  # Match remaining command parameters
                status__in=['S']  # Sent but not responded
            ).order_by('-command_in_time').first()
            
            if command:
                command.response = response
                command.response_time = timezone.now()
                command.status = 'C'  # Completed
                command.save()
                logger.info(f"Updated command {command.id} with response for device {device.alias}")
            else:
                logger.warning(f"No matching command found for response: {command_text} on device {device.alias}")
                
        except Exception as ex:
            logger.exception(f"Error processing command response: {ex}")

    def check_and_send_commands(self, client):
        """_summary_

        Args:
            client (_type_): _description_
        """
        # Get unsent commands
        while self.loop_running:
            commands = CommandsModal.objects.filter(status__iexact='P').order_by('-command_in_time')
            for command in commands:
                logger.info("Found command waiting to be processed: %s for device: %s", command.command, command.device.ip_address)
                device = command.device
                # get latest active device config
                cfg = DeviceConfig.objects.filter(
                    device=device
                ).order_by('-created_at').first()
                if cfg is None:
                    logger.warning("Config not found for device %s", command.device.ip_address)
                cfg_data = cfg.data if (cfg is not None and cfg.data is not None) else {}
                dev_mqtt_user = cfg_data.get('mqtt_user', 'Devtest')
                dev_mqtt_user = dev_mqtt_user if dev_mqtt_user is not None else 'Devtest'
                # dev_mqtt_group = cfg_data.get('group_id', 'Devtest')
                default_command_topic = MQTT_ENABLED_DEVICE_COMMANDS.get('cmd-req', '')
                command_topic = default_command_topic.format(
                    dev_mqtt_user=dev_mqtt_user,
                    device_alias=device.alias
                )
                logger.info("Publishing MQTT %s: %s", command_topic, command.param)
                payload = f"""{{"command":"{command.command} {command.param}", "device":"{device.alias}"}}"""
                client.publish(command_topic, payload, 1)
                command.status = 'S' # Sent
                command.command_read_time = timezone.datetime.utcnow()
                command.save()
            time.sleep(10)
