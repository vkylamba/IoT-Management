import random
import datetime
import requests
import json

MAX_CURRENT_LIMIT_LOAD = 10
MAX_CURRENT_LIMIT_INVERTER = 30
MAX_CURRENT_LIMIT_GRID = 100
MIN_CURRENT_LIMIT_SOLAR = 0
MAX_CURRENT_LIMIT_SOLAR = 100
MIN_CURRENT_LIMIT_BATTERY = -100
MAX_CURRENT_LIMIT_BATTERY = 100

SERVER_URL = "http://localhost:8113"

SOLAR_TO_BATTERY = 0.3

class Device(object):
    """
            Class representing a physycal device.
            To mimic physical device and send data.
    """

    device_type = "E-Meter"
    server_url = SERVER_URL
    data_path = "/api/data/"
    time_delta = datetime.timedelta(minutes=10)
    try:
        with open('data.txt') as json_file:
            _data = json.load(json_file)
            if _data is None:
                _data = {}
    except FileNotFoundError:
        _data = {}

    def __init__(self, device_type=None, token=None):

        if device_type:
            self.device_type = device_type
        if token:
            self.token = token

    def _generate_solar_meter_data(self):
        """
            Method to generate solar meter data.
        """
        data = self._data
        solar_data = data.get('solar_meter', {})
        energy = solar_data.get('energy', 0)

        hour_now = datetime.datetime.now().hour
        if hour_now > 6 and hour_now < 18:
            voltage = 100 - 5 * (hour_now % 12 - 12) + random.randrange(0, 10)
        else:
            voltage = 0

        current = random.randrange(MIN_CURRENT_LIMIT_SOLAR, MAX_CURRENT_LIMIT_SOLAR)
        power = voltage * current
        energy += (power * self.time_delta.total_seconds()) / 3600000

        solar_data = {
            "voltage": voltage,
            "current": current,
            "power": power,
            "energy": energy,
        }

        data["solar_meter"] = solar_data
        self._data = data

    def _generate_load_meter_data(self):
        """
            Method to generate load meter data.
        """
        data = self._data
        load_data = data.get('load_meter', {})
        energy = load_data.get('energy', 0)

        voltage = random.randrange(220, 240)
        current = random.randrange(0, MAX_CURRENT_LIMIT_LOAD)
        power = voltage * current
        energy += (power * self.time_delta.total_seconds()) / 3600000
        # energy += (power * self.time_delta.total_seconds())

        load_data = {
            "voltage": voltage,
            "current": current,
            "power": power,
            "energy": energy,
        }

        data["load_meter"] = load_data
        self._data = data

    def _generate_inverter_and_grid_meter_data(self):
        """
            Method to generate inverter meter data.
        """
        data = self._data
        load_data = data.get('load_meter', {})
        solar_data = data.get('solar_meter', {})
        inverter_data = data.get('inverter_meter', {})
        battery_data = data.get('battery_meter', {})
        grid_data = data.get('grid_meter', {})

        inverter_energy = inverter_data.get('energy', 0)

        hour_now = datetime.datetime.now().hour

        grid_voltage = random.randrange(220, 240)
        grid_energy = grid_data.get('energy', 0)

        battery_voltage = 60 + (hour_now % 12 - 12)
        battery_energy = battery_data.get('energy', 0)

        solar_power = solar_data.get('power', 0)
        load_power = load_data.get('power', 0)
        load_voltage = load_data.get('voltage', 0)
        load_current = load_data.get('current', 0)

        solar_surplus = solar_power - load_power

        ## If available solar power is less than load
        if (solar_surplus < 0):
            ## if batteries are discharged, charge battery and supply partly to load from solar, and grid
            if (battery_voltage < 45):
                battery_current = -1 * (solar_power * SOLAR_TO_BATTERY) / battery_voltage
                inverter_voltage = load_voltage
                grid_voltage = load_voltage
                
                inverter_current = solar_power * (1 - SOLAR_TO_BATTERY) / inverter_voltage
                grid_current = load_current - inverter_current

            else:
            ## if batteries are charged, the load is partly on solar, and partly on battery
                battery_current = (load_power - solar_power) / battery_voltage
                inverter_voltage = load_voltage
                inverter_current = load_current
                grid_current = 0

        else: ## if solar power is more then load
            if (battery_voltage < 45): ## if batteries are discharged, charge battery
                battery_current =  (load_power - solar_power) / battery_voltage

                inverter_voltage = load_voltage

                inverter_current = load_current
                grid_current = 0
            else: ## if batteries are charged, export the power to grid
                battery_current = 0

                inverter_voltage = load_voltage
                grid_voltage = load_voltage

                grid_current = (load_power - solar_power) / grid_voltage ## grid current will be negative here
                inverter_current = load_current - grid_current

        battery_power = battery_voltage * battery_current
        battery_energy += battery_power * (self.time_delta.total_seconds()) / 3600000

        grid_power = grid_voltage * grid_current
        grid_energy += grid_power * (self.time_delta.total_seconds()) / 3600000

        inverter_power = inverter_voltage * inverter_current
        inverter_energy += inverter_power * (self.time_delta.total_seconds()) / 3600000


        battery_data = {
            "voltage": battery_voltage,
            "current": battery_current,
            "power": battery_power,
            "energy": battery_energy,
        }

        inverter_data = {
            "voltage": inverter_voltage,
            "current": inverter_current,
            "power": inverter_power,
            "energy": inverter_energy,
        }

        grid_data = {
            "voltage": grid_voltage,
            "current": grid_current,
            "power": grid_power,
            "energy": grid_energy,
        }

        data["battery_meter"] = battery_data
        data["grid_meter"] = grid_data
        data["inverter_meter"] = inverter_data

        self._data = data

    def generate_data_point(self):
        """
            Method to generate a fake dat point.
        """

        if self.device_type == "solar":
            self._generate_load_meter_data()
            self._generate_solar_meter_data()
            self._generate_inverter_and_grid_meter_data()
        else:
            self._generate_load_meter_data()

        return self._data

    def send_data(self):
        data = self.generate_data_point()
        with open('data.txt', 'w') as json_file:
            json_file.write(json.dumps(data))
        resp = requests.post(self.server_url + self.data_path, json=data, headers={
            'Device': self.token
        })
        self.data = {}
        if resp.status_code in [200, 201]:
            return True
        else:
            return resp.text


if __name__ == '__main__':

    dev1 = Device(device_type="solar", token='2e4012d8a66887bb188ac2602dcb8c7615361fa4')
    # dev1 = Device(token='7f4958742a73ef89f59d695df0d3e79a5cf27e3e')
    print("Sending data..")
    print(dev1.send_data())