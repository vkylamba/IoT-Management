import random
import datetime
import requests
import json

SERVER_URL = "http://localhost:8113"

class Device(object):
    """
        Class representing a physical device.
        To mimic physical device and send data.
    """
    device_type = "E-Meter"
    server_url = SERVER_URL
    data_path = "/api/data/"
    time_delta = datetime.timedelta(minutes=10)
    date_format = "%Y-%m-%dT%H:%M:%S%z"

    def __init__(self, device_type=None, token=None):

        if device_type:
            self.device_type = device_type
        if token:
            self.token = token
        
        try:
            with open(f'data-{token}.txt') as json_file:
                data = json.load(json_file)
                if data is None:
                    data = {}
        except FileNotFoundError:
            data = {}
        
        self._data = data

    def get_last_update_time(self):
        if "last_update_time" in self._data:
            return datetime.datetime.strptime(self._data.get("last_update_time"), self.date_format)
        return None

    def send_data(self, data):
        data_to_send = {}
        for key in data:
            if "_meter" in key:
                data_to_send[key] = data[key]
        
        if 'last_update_time' in data:
            data_to_send['last_update_time'] = data['last_update_time']
        if 'metadata' in data:
            data_to_send['metadata'] = data['metadata']

        with open(f'data-{self.token}.txt', 'w') as json_file:
            json_file.write(json.dumps(data))
        resp = requests.post(self.server_url + self.data_path, json=data_to_send, headers={
            'Device': self.token
        })
        self._data = data
        if resp.status_code in [200, 201]:
            return True
        else:
            return resp.text
