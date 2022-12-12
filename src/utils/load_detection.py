import json
import logging

from datascience.train_machine import Train
from device.clickhouse_models import (MeterLoad, WeatherData,
                                      create_model_instance)
from device.models import Device, Meter
from django.utils import timezone

from .weather import get_weather_data_cached

logger = logging.getLogger('application')
load_model = Train()


def get_load_data_ai(device, data_point, sorted_equipments, temperature, humidity, wind_speed):
    """
        Method to find out appliances list based on the data.
    """
    equipments = []

    if isinstance(data_point, dict):
        power = data_point.get("power", 0)
        data_arrival_time = data_point["data_arrival_time"]

        temperature = data_point.get("temperature", temperature)
        humidity = data_point.get("humidity", humidity)
        wind_speed = data_point.get("humidity", wind_speed)

    else:
        power = data_point.power
        data_arrival_time = data_point.data_arrival_time

    input_data_list = [
        # float(data_point.device.latitude()),
        # float(data_point.device.longitude()),
        data_arrival_time.month,
        data_arrival_time.day,
        data_arrival_time.weekday(),
        data_arrival_time.hour,
        power,
        temperature,
        humidity,
        wind_speed,
    ]

    for load in sorted_equipments:
        input_data_list[4] = power
        if load.equipment.name in load_model.targets:
            try:
                model = load_model.targets[load.equipment.name]
                number = int(model.predict([input_data_list]))
                equipment_avg_power = (load.equipment.max_power + load.equipment.min_power) / 2
                if number > 0 and equipment_avg_power <= power:
                    # Find the suitable number.
                    while number * equipment_avg_power > power:
                        number -= 1
                    load_data = {
                        'equipment': load,
                        'name': load.equipment.name,
                        'qty': number,
                        'power': equipment_avg_power * number,
                    }
                    power -= equipment_avg_power * number
                    equipments.append(load_data)
            except Exception as ex:
                logger.exception(f"Exception occurred while checking for load {load.equipment.name}", ex)
    return equipments


def detect_and_save_meter_loads(device: Device, meters_and_data, data_arrival_time):
    """
    Method to find the loads connected to a meter and store in the MeterLoad table.
    """
    all_equipments = device.get_all_equipments()

    weather_data_now = get_weather_data_cached(device)
    temperature = weather_data_now.get('main', {}).get('temp', 0) if weather_data_now is not None else 0
    humidity = weather_data_now.get('main', {}).get('humidity', 0) if weather_data_now is not None else 0
    wind_speed = weather_data_now.get('wind', {}).get('speed', 0) if weather_data_now is not None else 0

    data = {
        "weather": weather_data_now
    }
    if weather_data_now is not None and len(weather_data_now.keys()) > 0:
        create_model_instance(
            WeatherData,
            {
                "device": device.id,
                "data_arrival_time": data_arrival_time,
                "temperature": (temperature - 273) * 100,
                "humidity": humidity * 100,
                "wind_speed": wind_speed * 100,
                "more_data": json.dumps(weather_data_now)
            }
        )

    for meter_and_data in meters_and_data:

        meter = meter_and_data["meter"]
        
        if meter.meter_type == Meter.LOAD_AC_METER:
            data_point = meter_and_data["data"]

            meter_equipments = [x for x in all_equipments if x.meter_id == str(meter.id)]
            if len(meter_equipments) == 0:
                meter_equipments = all_equipments

            loads = get_load_data_ai(
                device,
                data_point,
                meter_equipments,
                (temperature - 273) * 10, # Convert from kelvin to degrees * 10
                humidity,
                wind_speed * 3.6 # convert from m/s to kh/h
            )

            meter_loads = [
                MeterLoad(
                    equipment=load["equipment"] if isinstance(load, dict) else load.equipment,
                    equipment_name=load['name'],
                    device=device.id,
                    data_point=data_point["id"] if isinstance(data_point, dict) else data_point.id,
                    count=load['qty'],
                    power=load['power'],
                    data_arrival_time=data_point["data_arrival_time"] if isinstance(data_point, dict) else data_point.data_arrival_time
                ) for load in loads
            ]

            MeterLoad.objects.bulk_create(meter_loads)

            data["loads"] = loads
    return data
