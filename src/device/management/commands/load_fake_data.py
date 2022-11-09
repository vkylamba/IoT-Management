import random
import sys
from uuid import uuid4

from device.clickhouse_models import (MeterData, WeatherData,
                                      create_model_instance)
from device.models import Device, Meter, RawData
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


class Command(BaseCommand):

    """
        Command to load fake data into database.
    """

    help = 'Loads fake data set into database.'

    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument('device_ip', nargs='+', type=str)
        parser.add_argument('device_type', nargs='+', type=str)
        parser.add_argument('days', nargs='+', type=int)

    @transaction.atomic
    def handle(self, *args, **options):

        device_ip = options.get('device_ip')
        device_type = options.get('device_type', 'stand_alone_ac_meter')
        days = options.get('days')

        if not device_ip:
            sys.exit("Device ip not provided.")

        if not days:
            days = timezone.timedelta(days=7)
        else:
            days = timezone.timedelta(days=days[0])

        if device_type == 'stand_alone_ac_meter':
            pass
        elif device_type == 'solar_inverter':
            pass

        # Find the device
        device, created = Device.objects.get_or_create(ip_address=device_ip[0])
        if created:
            device.installation_date = timezone.now().date()
            device.save()

        if len(device.meter_set.all()) == 0:
            meter = Meter(
                id=str(uuid4()),
                name=f"load_meter",
                device=device,
                meter_type=Meter.LOAD_AC_METER
            )
            meter.save()
            device.meter_set.add(meter)
            device.save()
        else:
            meter = device.meter_set.all()[0]


        time_now = timezone.now()
        time_then = time_now - days
        start_time = timezone.datetime(
            year=time_then.year,
            month=time_then.month,
            day=time_then.day,
            tzinfo=time_now.tzinfo,
        )
        # end_time = timezone.datetime(
        #     year=time_now.year,
        #     month=time_now.month,
        #     day=time_now.day,
        #     tzinfo=time_now.tzinfo,
        # )
        end_time = time_now
        time_delta = timezone.timedelta(minutes=10)
        energy = 0
        runtime = 0

        while (end_time - start_time).total_seconds() > 0:
            voltage = random.randrange(2200, 2500)
            current = random.randrange(0, 1000)
            power = voltage * current
            energy += power * time_delta.total_seconds() / 1000.0
            runtime += time_delta.total_seconds()
            data_dict = {
                "meter": meter.id,
                "data_arrival_time": start_time,
                "voltage": voltage,
                "current": current,
                "power": power,
                "energy": energy,
                "runtime": runtime,
                "state": 0,
            }
            data_obj = create_model_instance(RawData, {
                "id": uuid4(),
                "device": device,
                "data_arrival_time": start_time,
                "data": {
                    "voltage": voltage,
                    "current": current,
                    "power": power,
                    "energy": energy,
                    "runtime": runtime,
                    "state": 0,
                }
            })
            create_model_instance(MeterData, data_dict)
            create_model_instance(WeatherData, {
                "id": uuid4(),
                "device": device,
                "temperature": random.randrange(100, 500),
                "humidity": random.randrange(20, 50),
                "wind_speed": random.randrange(0, 100)
            })
            start_time += time_delta
