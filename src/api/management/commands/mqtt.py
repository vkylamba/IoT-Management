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
SOURCE_TYPE_ESPHOME = "esphome"

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

# Home Assistant MQTT Discovery
HOMEASSISTANT_DISCOVERY_PREFIX = "homeassistant"

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
            self.process_message(msg, mqtt_client)
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
            # for the beken devices
            topic_to_subscribe = f"/+/devices/+/{topic}/+/+"
            mqtt_client.subscribe(topic_to_subscribe)
            # for the esphome devices
            topic_to_subscribe = f"/+/devices/+/{topic}/+/+/+"
            mqtt_client.subscribe(topic_to_subscribe)

    def subscribe_active_clients_topic(self, mqtt_client):
        topic = CLIENT_COUNT_TOPIC
        mqtt_client.subscribe(topic)

    def process_message(self, msg, mqtt_client):
        # Topic is in the following format for IoT devices:
        # /Devtest/devices/Dev-test/meters-data
        message_topic = msg.topic
        message_payload = msg.payload.decode('utf-8') if isinstance(msg.payload, bytes) else msg.payload

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
            if topic_data_length > 6 and SOURCE_TYPE_ESPHOME in message_topic:
                source_device_type = SOURCE_TYPE_ESPHOME
                data_key_name = topic_data_list[6]
                data_key_val = message_payload
                process_data = False
            elif topic_data_length > 5 and SOURCE_TYPE_BEKEN in message_topic:
                source_device_type = SOURCE_TYPE_BEKEN
                data_key_name = topic_data_list[5]
                data_key_val = message_payload
                process_data = False

            if source_device_type in [SOURCE_TYPE_BEKEN, SOURCE_TYPE_ESPHOME]:
                # Handle BEKEN and ESPHOME device data collection
                device_cache_key = f"beken_data_{group_name}_{device_name}"
                device_data = cache.get(device_cache_key, {})
                
                # Track previous power value for change detection
                previous_power = device_data.get('power')
                
                # Handle energy accumulation - if new energy is less than previous, add them
                if data_key_name == "energy":
                    previous_energy = device_data.get('energy')
                    if previous_energy is not None:
                        try:
                            prev_energy_float = float(previous_energy) if isinstance(previous_energy, (int, float, str)) else 0.0
                            current_energy = float(data_key_val) if isinstance(data_key_val, (int, float, str)) else 0.0
                            if current_energy < prev_energy_float:
                                # Energy counter reset detected, accumulate
                                data_key_val = prev_energy_float + current_energy
                                logger.debug("Energy counter reset detected for device %s, accumulating: %s + %s = %s", 
                                           device_name, prev_energy_float, current_energy, data_key_val)
                        except (ValueError, TypeError) as ex:
                            logger.warning("Error while parsing energy values for device %s: previous=%s, current=%s. Error: %s",
                                           device_name, previous_energy, data_key_val, str(ex))
                            pass
                
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
                
                # Publish if: 1) Time >= 119 seconds OR 2) Power value changed
                power_changed = False
                if data_key_name == "power":
                    try:
                        current_power = float(data_key_val)
                        if previous_power is not None:
                            prev_power_float = float(previous_power)
                            power_changed = abs(current_power - prev_power_float) > 0.01  # Allow small tolerance
                    except (ValueError, TypeError):
                        pass
                
                if time_diff >= 119 or power_changed:
                    process_data = True
                    message_payload = {}
                    # for each key in device_data, add to message_payload (excluding metadata)
                    for key, value in device_data.items():
                        if key not in ['timestamp', 'last_update']:
                            # Decode bytes if necessary, otherwise use value directly
                            if isinstance(value, bytes):
                                try:
                                    message_payload[key] = value.decode('utf-8')
                                except UnicodeDecodeError:
                                    message_payload[key] = str(value)
                            else:
                                message_payload[key] = value
                    message_payload = json.dumps(message_payload)
                    cache.delete(device_cache_key)
                    if power_changed:
                        logger.debug("Publishing due to power change for device: %s", device_name)

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
                
                # Publish Home Assistant discovery for MONA devices (only once per device)
                if source_device_type == SOURCE_TYPE_MONA and device is not None:
                    discovery_cache_key = f"ha_discovery_published_{device.id}"
                    if not cache.get(discovery_cache_key):
                        try:
                            self.publish_homeassistant_discovery(mqtt_client, device, group_name)
                            # Cache for 24 hours to avoid republishing on every message
                            cache.set(discovery_cache_key, True, 86400)
                        except Exception as ex:
                            logger.exception(f"Error publishing HA discovery for device {device.alias}: {ex}")
                
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

    def publish_homeassistant_discovery(self, client, device, group_name):
        """
        Publish Home Assistant MQTT discovery messages for a device.
        This allows Home Assistant to auto-discover the device and its sensors.
        Supports both IoT-GW-V1 (Modbus-GSM) and IoT-GW-V2 (Modbus-WiFi) schemas.
        
        Args:
            client: MQTT client instance
            device: Device object
            group_name: Device group name
        """
        device_id = device.alias.lower().replace(' ', '_')
        device_name = device.alias
        
        # Base device info shared across all sensors
        device_info = {
            "identifiers": [device_id],
            "name": device_name,
            "model": "IoT Gateway",
            "manufacturer": group_name,
            "sw_version": "1.0.0"
        }
        
        # State topic where device publishes its data
        state_topic = f"/{group_name}/devices/{device.alias}/meters-data"
        
        # Common sensors for both V1 and V2
        sensors = [
            # ADC Channels (0-5, 6 channels total)
            # {"name": "ADC Channel 0", "key": "adc_0", "value_template": "{{ value_json.adc['0'] | int(0) if value_json.adc is defined else 0 }}", "icon": "mdi:sine-wave"},
            # {"name": "ADC Channel 1", "key": "adc_1", "value_template": "{{ value_json.adc['1'] | int(0) if value_json.adc is defined else 0 }}", "icon": "mdi:sine-wave"},
            # {"name": "ADC Channel 2", "key": "adc_2", "value_template": "{{ value_json.adc['2'] | int(0) if value_json.adc is defined else 0 }}", "icon": "mdi:sine-wave"},
            # {"name": "ADC Channel 3", "key": "adc_3", "value_template": "{{ value_json.adc['3'] | int(0) if value_json.adc is defined else 0 }}", "icon": "mdi:sine-wave"},
            # {"name": "ADC Channel 4", "key": "adc_4", "value_template": "{{ value_json.adc['4'] | int(0) if value_json.adc is defined else 0 }}", "icon": "mdi:sine-wave"},
            # {"name": "ADC Channel 5", "key": "adc_5", "value_template": "{{ value_json.adc['5'] | int(0) if value_json.adc is defined else 0 }}", "icon": "mdi:sine-wave"},
            
            # DHT Sensor data - common to both
            {"name": "Temperature", "key": "temperature", "value_template": "{{ (value_json.dht.temperature | float(0)) / 100 if value_json.dht is defined else 0 }}", 
             "unit": "°C", "device_class": "temperature", "state_class": "measurement"},
            {"name": "Humidity", "key": "humidity", "value_template": "{{ (value_json.dht.humidity | float(0)) / 100 if value_json.dht is defined else 0 }}", 
             "unit": "%", "device_class": "humidity", "state_class": "measurement"},
            {"name": "Heat Index", "key": "heat_index", "value_template": "{{ (value_json.dht.hic | float(0)) / 100 if value_json.dht is defined else 0 }}", 
             "unit": "°C", "device_class": "temperature", "state_class": "measurement"},
            # {"name": "DHT State", "key": "dht_state", "value_template": "{{ value_json.dht.state | int(0) if value_json.dht is defined else 0 }}", "icon": "mdi:state-machine"},
        ]
        
        # Meter sensors - dynamically created based on meter type
        # Meters 1-6: Each can be energy/current/voltage meter or generic sensor
        for meter_num in range(0, 6):
            meter_key = f"meter_{meter_num}"
            
            # Type sensor for each meter
            sensors.append({
                "name": f"Meter {meter_num} Type",
                "key": f"{meter_key}_type",
                "value_template": f"{{{{ value_json.{meter_key}.typCfg | default('N/A') if value_json.{meter_key} is defined else 'N/A' }}}}",
                "icon": "mdi:tag"
            })
            
            # For energy meters (WAC/WDC), add all power-related fields
            sensors.append({
                "name": f"Meter {meter_num} Voltage",
                "key": f"{meter_key}_voltage",
                "value_template": f"{{{{ value_json.{meter_key}.voltage | float(0) if value_json.{meter_key} is defined and value_json.{meter_key}.voltage is defined else 0 }}}}",
                "unit": "V",
                "device_class": "voltage",
                "state_class": "measurement",
                "icon": "mdi:flash"
            })
            
            sensors.append({
                "name": f"Meter {meter_num} Current",
                "key": f"{meter_key}_current",
                "value_template": f"{{{{ value_json.{meter_key}.current | float(0) if value_json.{meter_key} is defined and value_json.{meter_key}.current is defined else 0 }}}}",
                "unit": "A",
                "device_class": "current",
                "state_class": "measurement",
                "icon": "mdi:current-ac"
            })
            
            sensors.append({
                "name": f"Meter {meter_num} Power",
                "key": f"{meter_key}_power",
                "value_template": f"{{{{ value_json.{meter_key}.power | float(0) if value_json.{meter_key} is defined and value_json.{meter_key}.power is defined else 0 }}}}",
                "unit": "W",
                "device_class": "power",
                "state_class": "measurement",
                "icon": "mdi:lightning-bolt"
            })
            
            sensors.append({
                "name": f"Meter {meter_num} Energy",
                "key": f"{meter_key}_energy",
                "value_template": f"{{{{ value_json.{meter_key}.energy | float(0) if value_json.{meter_key} is defined and value_json.{meter_key}.energy is defined else 0 }}}}",
                "unit": "Wh",
                "device_class": "energy",
                "state_class": "total_increasing",
                "icon": "mdi:counter"
            })
            
            sensors.append({
                "name": f"Meter {meter_num} Frequency",
                "key": f"{meter_key}_frequency",
                "value_template": f"{{{{ value_json.{meter_key}.frequency | float(0) if value_json.{meter_key} is defined and value_json.{meter_key}.frequency is defined else 0 }}}}",
                "unit": "Hz",
                "device_class": "frequency",
                "state_class": "measurement",
                "icon": "mdi:sine-wave"
            })
            
            sensors.append({
                "name": f"Meter {meter_num} Power Factor",
                "key": f"{meter_key}_pf",
                "value_template": f"{{{{ value_json.{meter_key}.powerFactor | float(0) if value_json.{meter_key} is defined and value_json.{meter_key}.powerFactor is defined else 0 }}}}",
                "unit": "",
                "device_class": "power_factor",
                "state_class": "measurement",
                "icon": "mdi:angle-acute"
            })
            
            # Generic value field (for non-energy meters like Distance, PIR, etc.)
            sensors.append({
                "name": f"Meter {meter_num} Value",
                "key": f"{meter_key}_val",
                "value_template": f"{{{{ value_json.{meter_key}.val | float(0) if value_json.{meter_key} is defined and value_json.{meter_key}.val is defined else 0 }}}}",
                "state_class": "measurement",
                "icon": "mdi:gauge"
            })
            
            # Generic frequency field (for non-energy meters)
            sensors.append({
                "name": f"Meter {meter_num} Freq",
                "key": f"{meter_key}_freq",
                "value_template": f"{{{{ value_json.{meter_key}.freq | float(0) if value_json.{meter_key} is defined and value_json.{meter_key}.freq is defined else 0 }}}}",
                "unit": "Hz",
                "state_class": "measurement",
                "icon": "mdi:sine-wave"
            })
        
        # Continue with other sensors
        # sensors.extend([
            # ADC RMS values (6 channels)
            # {"name": "ADC RMS Channel 0", "key": "adc_rms_0", "value_template": "{{ value_json.adcRms['0'] | int(0) if value_json.adcRms is defined else 0 }}", "icon": "mdi:sine-wave"},
            # {"name": "ADC RMS Channel 1", "key": "adc_rms_1", "value_template": "{{ value_json.adcRms['1'] | int(0) if value_json.adcRms is defined else 0 }}", "icon": "mdi:sine-wave"},
            # {"name": "ADC RMS Channel 2", "key": "adc_rms_2", "value_template": "{{ value_json.adcRms['2'] | int(0) if value_json.adcRms is defined else 0 }}", "icon": "mdi:sine-wave"},
            # {"name": "ADC RMS Channel 3", "key": "adc_rms_3", "value_template": "{{ value_json.adcRms['3'] | int(0) if value_json.adcRms is defined else 0 }}", "icon": "mdi:sine-wave"},
            # {"name": "ADC RMS Channel 4", "key": "adc_rms_4", "value_template": "{{ value_json.adcRms['4'] | int(0) if value_json.adcRms is defined else 0 }}", "icon": "mdi:sine-wave"},
            # {"name": "ADC RMS Channel 5", "key": "adc_rms_5", "value_template": "{{ value_json.adcRms['5'] | int(0) if value_json.adcRms is defined else 0 }}", "icon": "mdi:sine-wave"},
            
            # Network info - IoT-GW-V1 specific
            # {"name": "Network State", "key": "network_state", "value_template": "{{ value_json.network.state | default('unknown') if value_json.network is defined else 'unknown' }}", 
            #  "icon": "mdi:network"},
            # {"name": "Network IP", "key": "network_ip", "value_template": "{{ value_json.network.ip | default('0.0.0.0') if value_json.network is defined else '0.0.0.0' }}", 
            #  "icon": "mdi:ip-network"},
            # {"name": "Network TTS", "key": "network_tts", "value_template": "{{ value_json.network.tts | int(0) if value_json.network is defined else 0 }}", 
            #  "unit": "ms", "icon": "mdi:timer"},
            
            # System info - IoT-GW-V2 specific
            # {"name": "Battery", "key": "battery", "value_template": "{{ value_json.battery | float(0) if value_json.battery is defined else 0 }}", 
            #  "unit": "%", "device_class": "battery", "state_class": "measurement"},
            # {"name": "Uptime", "key": "uptime", "value_template": "{{ value_json.uptime | int(0) if value_json.uptime is defined else 0 }}", 
            #  "unit": "s", "device_class": "duration", "state_class": "total_increasing"},
        # ])
        
        # Text sensors for device info and firmware
        text_sensors = [
            # Time information
            {"name": "Time UTC", "key": "time_utc", "value_template": "{{ value_json.timeUTC | default('unknown') }}", "icon": "mdi:clock-outline"},
            {"name": "Time Delta", "key": "time_delta", "value_template": "{{ value_json.timeDelta | int(0) if value_json.timeDelta is defined else 0 }}", "icon": "mdi:timer-sand"},
            
            # Config info - IoT-GW-V1 specific
            # {"name": "Device Type", "key": "dev_type", "value_template": "{{ value_json.config.devType | default('unknown') if value_json.config is defined else 'unknown' }}", "icon": "mdi:chip"},
            # {"name": "Device ID", "key": "dev_id", "value_template": "{{ value_json.config.devId | default(0) if value_json.config is defined else 0 }}", "icon": "mdi:identifier"},
            # {"name": "Work Mode", "key": "work_mode", "value_template": "{{ value_json.config.workMode | default(0) if value_json.config is defined else 0 }}", "icon": "mdi:cog"},
            # {"name": "MAC Address", "key": "mac", "value_template": "{{ value_json.config.mac | default(value_json.mac) | default('unknown') }}", "icon": "mdi:network"},
            
            # Firmware versions - IoT-GW-V2 specific
            # {"name": "Core Version", "key": "core_version", "value_template": "{{ value_json.core_version | default('unknown') }}", "icon": "mdi:chip"},
            # {"name": "Firmware Version", "key": "fw_version", "value_template": "{{ value_json.fw_version | default('unknown') }}", "icon": "mdi:application-cog"},
        ]
        
        # Publish regular sensors
        for sensor in sensors:
            config_topic = f"{HOMEASSISTANT_DISCOVERY_PREFIX}/sensor/{device_id}/{sensor['key']}/config"
            
            config = {
                "name": sensor["name"],
                "unique_id": f"{device_id}_{sensor['key']}",
                "state_topic": state_topic,
                "value_template": sensor["value_template"],
                "device": device_info,
                "availability_topic": state_topic,
                "payload_available": "online",
                "payload_not_available": "offline"
            }
            
            # Add optional fields
            if sensor.get("unit"):
                config["unit_of_measurement"] = sensor["unit"]
            if sensor.get("device_class"):
                config["device_class"] = sensor["device_class"]
            if sensor.get("state_class"):
                config["state_class"] = sensor["state_class"]
            if sensor.get("icon"):
                config["icon"] = sensor["icon"]
            
            client.publish(config_topic, json.dumps(config), retain=True, qos=1)
            logger.debug(f"Published HA discovery for {device_name} - {sensor['name']}")
        
        # Publish text sensors
        for sensor in text_sensors:
            config_topic = f"{HOMEASSISTANT_DISCOVERY_PREFIX}/sensor/{device_id}/{sensor['key']}/config"
            
            config = {
                "name": sensor["name"],
                "unique_id": f"{device_id}_{sensor['key']}",
                "state_topic": state_topic,
                "value_template": sensor["value_template"],
                "device": device_info,
                "icon": sensor.get("icon", "mdi:information")
            }
            
            client.publish(config_topic, json.dumps(config), retain=True, qos=1)
            logger.debug(f"Published HA discovery for {device_name} - {sensor['name']}")
        
        logger.info(f"Published Home Assistant discovery for device {device_name} with {len(sensors) + len(text_sensors)} sensors")

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
