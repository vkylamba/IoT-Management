import sys
import json
import os
import logging
import time
import random
from datetime import datetime

import paho.mqtt.client as mqtt

logger = logging
logging.basicConfig(level=logging.DEBUG)

CLIENT_SYSTEM_STATUS_TOPIC_TYPE = "status"
CLIENT_METERS_DATA_TOPIC_TYPE = "meters-data"
CLIENT_MODBUS_DATA_TOPIC_TYPE = "modbus-data"
CLIENT_UPDATE_RESP_TOPIC_TYPE = "update-response"
CLIENT_CMD_RESP_TOPIC_TYPE = "cmd-resp"
CLIENT_CMD_REQ_TOPIC_TYPE = "cmd-resp"
CLIENT_CMD_REQ_TOPIC_TYPE = "cmd-req"
CLIENT_HEARTBEAT_TOPIC_TYPE = "heartbeat"
CLIENT_COMMAND_RESP_TOPIC_TYPE = "command"

MQTT_ENABLED_DEVICE_COMMANDS = {
    'status': "/{dev_mqtt_user}/devices/{device_alias}/status",
    'meters-data': "/{dev_mqtt_user}/devices/{device_alias}/meters-data",
    'modbus-data': "/{dev_mqtt_user}/devices/{device_alias}/modbus-data",
    'cmd-req': "/{dev_mqtt_user}/devices/{device_alias}/cmd-req",
    'update-trigger': "/{dev_mqtt_user}/devices/{device_alias}/update-trigger",
}

MQTT_DEV_USER = 'demo-device'
MQTT_DEV_PASSWORD = 'demo-device'
MQTT_BROKER = 'mqtt.okosengineering.com'
MQTT_PORT = 9023
MQTT_KEEPALIVE = True


class MqttDevice:
    """
        MQTT script mimicking the behavior of a IoT-Gateway device. Connected to monitor a grid connected solar system.
        ADC 0: Inverter Output AC Voltage.
        ADC 1: AC Current - Grid
        ADC 2: AC Current - Load
        ADC 3: DC Voltage - Solar
        ADC 4: DC Current - Solar
        ADC 5: DC Current - Battery
        
        status data sample:
        {
            "battery": 0, // device internal battery level
            "core_version": "6.0.1",
            "fw_version": "1.1.5",
            "mac": 48646759836492,
            "uptime": 5233
        }
        
        meters-data sample:
        {
            "adc": {
                "0": 1150,
                "1": 5,
                "2": 6,
                "3": 539,
                "4": 1942,
                "5": 240
            },
            "dht": {
                "hic": 40,
                "humidity": 14,
                "state": 3,
                "temperature": 41.9
            },
            "meter_0": {
                "current": 1.28,
                "energy": 30851056,
                "frequency": 50,
                "power": 295.2,
                "powerFactor": -0.1,
                "typCfg": "WAC[0,1]",
                "voltage": 231.1
            },
            "meter_1": {
                "current": 1.3,
                "energy": 10115610,
                "frequency": 50,
                "power": 300.7,
                "powerFactor": -0.7,
                "typCfg": "WAC[0,2]",
                "voltage": 231.1
            },
            "meter_2": {
                "current": 4.39,
                "energy": 32295806,
                "power": 222.4,
                "typCfg": "WDC[3,4]",
                "voltage": 50.7
            },
            "meter_3": {
                "current": 4.39,
                "typCfg": "ADC[5]"
            },
            "timeDelta": 600,
            "timeUTC": "2024-05-03 09:46:49"
        }
    """

    help = 'Starts the mqtt device client mimicking a IoT-Gateway device.'
    
    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument('device_alias', nargs='+', type=str)
        parser.add_argument('device_type', nargs='+', type=str)
        parser.add_argument('data_frequency', nargs='+', type=int)
        parser.add_argument('modbus_enabled', nargs='+', type=bool)

    def handle(self, *args, **options):
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

        self.client.username_pw_set(MQTT_DEV_USER, MQTT_DEV_PASSWORD)

        self.client.connect(
            host=MQTT_BROKER,
            port=int(MQTT_PORT),
            keepalive=MQTT_KEEPALIVE
        )
        
        self.device_alias = options.get('device_alias', 'dev-test-5')
        self.device_type = options.get('device_type', 'IoT-GW-Solar')
        self.data_frequency = options.get('data_frequency', 300)
        self.modbus_enabled = options.get('modbus_enabled', False)
        
        self.battery_level = random.randint(10, 100)
        self.core_version = "0.1"
        self.fw_version = "1.0.0"
        self.mac = "d8:80:39:4f:7d:3c"
        self.uptime = 0
        
        self.first_pass = True

        self.client.loop_start()
        self.loop_running = True
        self.last_status_update_time = datetime.utcnow()
        self.last_meter_data_update_time = datetime.utcnow()
        self.last_modbus_data_update_time = datetime.utcnow()
        self.check_and_send_data()

    def on_connect(self, mqtt_client, user_data, flags, rc):
        if rc == 0:
            logger.info('MQTT connected successful')
            self.subscribe_to_topics(mqtt_client)
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

    def subscribe_to_topics(self, mqtt_client):
        mqtt_client.subscribe(CLIENT_CMD_REQ_TOPIC_TYPE)
        mqtt_client.subscribe(CLIENT_HEARTBEAT_TOPIC_TYPE)

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
            group_name = topic_data_list[topic_data_length-4]

            if topic_type in [
                CLIENT_CMD_REQ_TOPIC_TYPE,
                CLIENT_HEARTBEAT_TOPIC_TYPE
            ]:
                logger.debug("MQTT data, group: %s, device: %s, topic: %s", group_name, device_name, topic_type)
                try:
                    message_data = json.loads(message_payload)
                except Exception:
                    logger.warning(f"Invalid json data: {message_payload}")
            else:
                logger.warning("MQTT unknown topic: %s", topic_type)
        else:
            logger.warning("MQTT unknown topic: %s", msg.topic)

    def check_and_send_data(self):
        while self.loop_running:
            self.uptime += 60
            time_now = datetime.utcnow()
            if self.first_pass or (time_now - self.last_status_update_time).total_seconds() >= 60:
                self.send_device_status()
                self.last_status_update_time = time_now
            if self.first_pass or (time_now - self.last_meter_data_update_time).total_seconds() >= self.data_frequency:
                self.send_device_meter_data()
                self.last_meter_data_update_time = time_now
            if (self.modbus_enabled or self.first_pass) and (time_now - self.last_modbus_data_update_time).total_seconds() >= self.data_frequency:
                self.send_device_modbus_data()
                self.last_modbus_data_update_time = time_now
                
            self.first_pass = False

            logging.info("Sleeping for 60 seconds")
            time.sleep(60)

    def send_device_status(self):
        logger.info("Sending device status data")
        data_topic = MQTT_ENABLED_DEVICE_COMMANDS['status']
        data_topic = data_topic.format(
            dev_mqtt_user=MQTT_DEV_USER,
            device_alias=self.device_alias
        )
        status_data = {
            "battery": self.battery_level,
            "core_version": self.core_version,
            "fw_version": self.fw_version,
            "uptime": self.uptime
        }
        status_data = json.dumps(status_data)
        logger.info("Publishing MQTT %s: %s", data_topic, status_data)
        self.client.publish(data_topic, status_data, 1)

    def get_solar_adc_values(self):
        time_now = datetime.utcnow()
        hour = time_now.hour
        minute = time_now.minute
        time_val = hour * 60 + minute

        if time_val < 6*60:
            time_val = 6*60
        if time_val > 19*60:
            time_val = 19*60
        if time_val > 14*60:
            time_val = time_val -  14*60

        time_val_normalized = time_val / (19*60 - 6*60)
        
        adc_3 = time_val_normalized * 100 + random.randint(0, 15) # connected to voltage channel
        adc_4 = time_val_normalized * 30 + random.randint(0, 15) # connected to grid current channel
        
        if adc_3 < 500:
            adc_4 = 0

        return int(adc_3 * 10), int(adc_4 * 10)
    
    def get_grid_and_load_adc_values(self, solar_power):
        grid_available = random.randint(0, 1)
        adc_0 = random.randint(230, 240)
        adc_2 = random.randint(3, 15)
        if grid_available < 1:
            adc_1 = 0
        else:
            adc_1 = adc_2 - solar_power // adc_0
        
        adc_1 = adc_1 - random.randint(0, 5)
        adc_5 = (adc_2 - adc_1) * 5
        if adc_1 < 0:
            adc_1 = -1 * adc_1

        return adc_0 * 10, adc_1 * 10, adc_2 * 10, adc_5 * 10
    
    def get_temperature_and_humidity(self):
        time_now = datetime.utcnow()
        hour = time_now.hour
        minute = time_now.minute
        time_val = hour * 60 + minute
        time_val = (time_val -  12*60) / 24
        if time_val < 0:
            time_val = -1 * time_val

        temperature = time_val * 30 + random.randint(0, 5)
        humidity = time_val * 40 + random.randint(10, 20)
        
        return temperature // 10, humidity // 10
    
    def write_energy_values_to_file(self):
        # write energy values to json file
        filename = 'mqtt-client-energy-values.json'
        with open(filename, 'w') as file:
            energy_values = {
                'grid_energy': self.grid_energy,
                'load_energy': self.load_energy,
                'solar_energy': self.solar_energy
            }
            json.dump(energy_values, file)

    def read_energy_values_from_file(self):
        # read energy values from json file
        filename = 'mqtt-client-energy-values.json'
        if os.path.exists(filename):
            with open(filename, 'r') as file:
                energy_values = json.load(file)
                self.grid_energy = energy_values.get('grid_energy', 0)
                self.load_energy = energy_values.get('load_energy', 0)
                self.solar_energy = energy_values.get('solar_energy', 0)
        else:
            self.grid_energy = 0
            self.load_energy = 0
            self.solar_energy = 0

    def send_device_meter_data(self):
        logger.info("Sending device meters-data")
        data_topic = MQTT_ENABLED_DEVICE_COMMANDS['meters-data']
        data_topic = data_topic.format(
            dev_mqtt_user=MQTT_DEV_USER,
            device_alias=self.device_alias
        )
        
        # adc_0 is connected to voltage channel
        # adc_1 is connected to grid current channel
        # adc_2 is connected to load current channel
        # adc_3 is connected to solar voltage channel
        # adc_4 is connected to solar current channel
        # adc_5 is connected to battery current channel
        
        adc_3, adc_4 = self.get_solar_adc_values()
        solar_voltage = adc_3 * 0.1 + 10
        solar_current = adc_4 * 0.1
        solar_power = solar_voltage * solar_current
        
        adc_0, adc_1, adc_2, adc_5 = self.get_grid_and_load_adc_values(solar_power)
        
        temperature, humidity = self.get_temperature_and_humidity()

        ac_voltage = adc_0 // 10
        frequency = 50
        grid_pf = 1
        load_pf = 1
        if ac_voltage < 220:
            frequency = 0
            ac_voltage = 0
        
        grid_current = adc_1 // 10
        load_current = adc_2 // 10
        grid_power = ac_voltage * grid_current
        load_power = ac_voltage * load_current
        battery_current = adc_5 // 10
        
        if solar_power > grid_power + load_power:
            grid_pf = -1

        if getattr(self, 'grid_energy', None) is None:
            self.read_energy_values_from_file()

        self.grid_energy = self.grid_energy + grid_power * self.data_frequency
        self.load_energy = self.load_energy + load_power * self.data_frequency
        self.solar_energy = self.solar_energy + solar_power * self.data_frequency
        
        self.write_energy_values_to_file()

        meter_data = {
            "adc": {
                "0": adc_0,
                "1": adc_1,
                "2": adc_2,
                "3": adc_3,
                "4": adc_4,
                "5": adc_5
            },
            "dht": {
                "hic": 40,
                "humidity": humidity,
                "state": 3,
                "temperature": temperature
            },
            "meter_0": {
                "current": grid_current,
                "energy": self.grid_energy,
                "frequency": frequency,
                "power": grid_power,
                "powerFactor": grid_pf,
                "typCfg": "WAC[0,1]",
                "voltage": ac_voltage
            },
            "meter_1": {
                "current": load_current,
                "energy": self.load_energy,
                "frequency": frequency,
                "power": load_power,
                "powerFactor": load_pf,
                "typCfg": "WAC[0,2]",
                "voltage": ac_voltage
            },
            "meter_2": {
                "current": solar_current,
                "energy": self.solar_energy,
                "power": solar_power,
                "typCfg": "WDC[3,4]",
                "voltage": solar_voltage
            },
            "meter_3": {
                "current": battery_current,
                "typCfg": "ADC[5]"
            },
            "timeDelta": 600,
            "timeUTC": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        }
        meter_data = json.dumps(meter_data)
        logger.info("Publishing MQTT %s: %s", data_topic, meter_data)
        self.client.publish(data_topic, meter_data, 1)

if __name__ == '__main__':
    MqttDevice().handle()
