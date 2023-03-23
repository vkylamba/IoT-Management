import datetime
import json
import logging
from posixpath import split

import pytz
from api.serializers import MeterDataSerializer, meter_data
from device.clickhouse_models import DerivedData, MeterData, MeterLoad, WeatherData
from device.models import DeviceProperty, DeviceType, DeviceEquipment, device, DeviceStatus, Meter, RawData
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django_clickhouse.configuration import config
from django_clickhouse.database import connections
# from event.models import EventHistory

from .weather import get_weather_data_cached

logger = logging.getLogger('django')
LIGHT_EQUIPMENTS = ['CFL', 'Tubelight', 'Bulb']
SUMMER_EQUIPMENTS = ['Fan', 'Cooler', 'AC']
OTHER_EQUIPMENTS = ['TV', 'Water Pump']


class DataReports(object):
    """
        class to provide methods to access the device data.
    """

    def __init__(self, device):
        self.device = device
        self.device_types = [x.name for x in self.device.types.all()]
        self.rate = DeviceProperty.objects.filter(device=self.device, name='pay_per_unit').first()
        self.meters = Meter.objects.filter(
            device=self.device
        )

    def get_statistics_current_month(self, params='all'):
        """
            Get device statistics grouped by meter name. 
            Device's timezone is used in querying the data.
        """
        to_time = self.get_device_local_time()
        from_time = timezone.datetime(
            year=to_time.year, month=to_time.month, day=1
        )

        from_time = from_time.astimezone(pytz.utc)
        to_time = to_time.astimezone(pytz.utc)

        return self.get_statistics_by_time(
            params=params, from_time=from_time, to_time=to_time,
            aggregation_period=datetime.timedelta(days=30)
        )

    def get_statistics_current_day(self, params='all', cached=True):
        """
            Get device statistics grouped by meter name. 
            Device's timezone is used in querying the data.
        """
        time_now = self.get_device_local_time()
        time_now_zero_hour = datetime.datetime(
            year=time_now.year,
            month=time_now.month,
            day=time_now.day,
            tzinfo=time_now.tzinfo
        )
        date_today = time_now_zero_hour.astimezone(pytz.utc)
        date_tomorrow = date_today + timezone.timedelta(days=1)


        found_in_cache = False
        results = []
        if cached:
            device_ip_address = self.device.ip_address
            from_time_string = date_today.strftime("%Y-%m-%d")
            to_time_string = date_tomorrow.strftime("%Y-%m-%d")
            cache_name = f"day-stats-{params}-{device_ip_address}-{from_time_string}-{to_time_string}"

            results = cache.get(cache_name)
            found_in_cache = results is not None

        if not found_in_cache:
            results = self.get_statistics_by_time(
                params=params, from_time=date_today, to_time=date_tomorrow,
                aggregation_period=datetime.timedelta(days=1)
            )
            results = [x for x in results]
            cache.set(cache_name, results, settings.DEVICE_PROPERTY_UPDATE_DELAY_MINUTES)
        return results

    def get_statistics_by_time(self, params='all', from_time=None, to_time=None, aggregation_period=None):

        time_now = self.get_device_local_time()
        time_now = time_now.astimezone(pytz.utc)

        if from_time is None and to_time is None:
            delta = datetime.timedelta(days=1)
            yesterday = time_now - delta
            from_time = timezone.datetime(
                year=yesterday.year, month=yesterday.month, day=yesterday.day)
            to_time = timezone.datetime(
                year=time_now.year, month=time_now.month, day=time_now.day)
        elif to_time is None:
            to_time = timezone.datetime(
                year=time_now.year, month=time_now.month, day=time_now.day)
        elif from_time is None:
            from_time = timezone.datetime(
                year=time_now.year, month=time_now.month, day=time_now.day)

        device_ip_address = self.device.ip_address

        if aggregation_period is None or aggregation_period == datetime.timedelta(hours=1):
            time_aggregation = "toHour(data.data_arrival_time)"
        elif aggregation_period == datetime.timedelta(days=1):
            time_aggregation = "toDate(data.data_arrival_time)"
        elif aggregation_period == datetime.timedelta(days=7):
            time_aggregation = "toWeek(data.data_arrival_time)"
        elif aggregation_period >= datetime.timedelta(days=30):
            time_aggregation = "toMonth(data.data_arrival_time)"
        else:
            time_aggregation = "toHour(data.data_arrival_time)"

        from_time_string = from_time.strftime("%Y-%m-%dT%H:%M:%S")
        to_time_string = to_time.strftime("%Y-%m-%dT%H:%M:%S")

        meter_names = {}
        for meter in self.meters:
            meter_names[str(meter.id)] = meter.name
        meter_ids = list(meter_names.keys())

        logger.debug("Getting statistics: {}, {}, {}, {}".format(device_ip_address, aggregation_period, from_time_string, to_time_string))
        columns = [
            "meter",
            "aggregation_time",
            "data_points",
            "initial_time",
            "final_time",
            "avg_voltage",
            "min_voltage",
            "max_voltage",
            "avg_current",
            "min_current",
            "max_current",
            "avg_power",
            "min_power",
            "max_power",
            "avg_energy",
            "min_energy",
            "max_energy",
            "avg_runtime",
            "min_runtime",
            "max_runtime",
            "avg_frequency",
            "min_frequency",
            "max_frequency",
            "avg_temperature",
            "min_temperature",
            "max_temperature",
        ]
        connection = connections.get_connection(config.DEFAULT_DB_ALIAS)

        rows = connection.raw("""
            select
                meter,
                {time_aggregation} as aggregation_time,
                count(id) as data_points,
                min(data.data_arrival_time) as initial_time,
                max(data.data_arrival_time) as final_time,
                avg(data.voltage) as avg_voltage,
                min(data.voltage) as min_voltage,
                max(data.voltage) as max_voltage,
                avg(data.current) as avg_current,
                min(data.current) as min_current,
                max(data.current) as max_current,
                avg(data.power) as avg_power,
                min(data.power) as min_power,
                max(data.power) as max_power,
                avg(data.energy) as avg_energy,
                min(data.energy) as min_energy,
                max(data.energy) as max_energy,
                avg(data.runtime) as avg_runtime,
                min(data.runtime) as min_runtime,
                max(data.runtime) as max_runtime,
                avg(data.frequency) as avg_frequency,
                min(data.frequency) as min_frequency,
                max(data.frequency) as max_frequency,
                avg(data.temperature) as avg_temperature,
                min(data.temperature) as min_temperature,
                max(data.temperature) as max_temperature
            from meterdata as data
            where
                data.meter in {meter_ids}
                and data.data_arrival_time >= toDateTime('{from_time_string}')
                and data.data_arrival_time <  toDateTime('{to_time_string}')
            group by
                meter,
                aggregation_time
            order by aggregation_time
        """.format(
            time_aggregation=time_aggregation,
            meter_ids=meter_ids,
            from_time_string=from_time_string,
            to_time_string=to_time_string
        )).split('\n')

        data_list = (
            dict(zip(columns, row.split('\t'))) for row in rows
        )
        return (
            {
                **x,
                'meter_name': meter_names.get(x['meter'], ''),
            } for x in data_list
        )

    def get_latest_data(self):
        latest_meter_data = self.device.get_last_data_point(split_by_meters=True)
        if latest_meter_data is None:
            latest_meter_data = {}

        latest_raw_data = self.get_latest_raw_data()
        latest_meter_data.update({
            "raw_data_last_5": latest_raw_data
        })
        return latest_meter_data

    def get_latest_raw_data(self):
        raw_data = RawData.objects.filter(
            device=self.device
        ).order_by(
            '-data_arrival_time'
        )[0:5]
        return [{
            "data_arrival_time": x.data_arrival_time.strftime("%Y-%m-%dT%H:%M:%S"),
            "data": json.loads(x.data) if isinstance(x.data, str) else x.data 
        } for x in raw_data]

    def get_all_data(self, start_time, end_time, meter_type=None):
        meters = Meter.objects.filter(
            device=self.device
        )
        if meter_type is not None:
            meter_ids = [str(meter.id) for meter in meters if meter.meter_type in meter_type]
        else:
            meter_ids = [str(meter.id) for meter in meters]

        if meter_ids:
            data = MeterData.objects.filter(meter__in=meter_ids)

            if start_time is not None:
                data = data.filter(data_arrival_time__gte=start_time)
            if end_time is not None:
                data = data.filter(data_arrival_time__lte=end_time)
            data = data.order_by('data_arrival_time')

            return data
        return []

    def get_power_and_energy_data(self, start_time, end_time, meter_type=None):

        meter_names = {}
        for meter in self.meters:
            if meter_type is not None and meter.meter_type in meter_type:
                meter_names[str(meter.id)] = meter.name
            elif meter_type is None:
                meter_names[str(meter.id)] = meter.name

        meter_ids = list(meter_names.keys())

        from_time_string = start_time.strftime("%Y-%m-%dT%H:%M:%S")
        to_time_string = end_time.strftime("%Y-%m-%dT%H:%M:%S")

        connection = connections.get_connection(config.DEFAULT_DB_ALIAS)

        columns = [
            "meter",
            "data_arrival_time",
            "power",
            "energy"
        ]

        rows = connection.raw(
            """
                select
                    meter,
                    data_arrival_time,
                    round(sum(power), 2) as power,
                    round(sum(energy), 2) as energy
                from
                    meterdata as data
                where
                    data.meter in {meter_ids}
                    and data.data_arrival_time >= toDateTime('{from_time_string}')
                    and data.data_arrival_time <  toDateTime('{to_time_string}')
                group by
                    meter, data_arrival_time
                order by
                    data_arrival_time
            """.format(
                meter_ids=meter_ids,
                from_time_string=from_time_string,
                to_time_string=to_time_string
            )
        ).split('\n')

        data_list = (
            dict(zip(columns, row.split('\t'))) for row in rows
        )
        return (
            {
                'meter_name': meter_names.get(x['meter'], ''),
                'data_arrival_time': x.get('data_arrival_time'),
                'power': x.get('power'),
                'energy': x.get('energy')
            } for x in data_list
        )

    def get_historic_weather_data(self, start_time, end_time):
        from_time_string = start_time.strftime("%Y-%m-%dT%H:%M:%S")
        to_time_string = end_time.strftime("%Y-%m-%dT%H:%M:%S")

        connection = connections.get_connection(config.DEFAULT_DB_ALIAS)
        rows = connection.raw(
            """
                select
                    temperature,
                    humidity,
                    more_data as data,
                    data_arrival_time
                from
                    weatherdata as data
                where
                    data.device in {device_ids}
                    and data.data_arrival_time >= toDateTime('{from_time_string}')
                    and data.data_arrival_time <  toDateTime('{to_time_string}')
                order by
                    data_arrival_time
            """.format(
                device_ids=[str(self.device.id)],
                from_time_string=from_time_string,
                to_time_string=to_time_string
            )
        ).split('\n')

        data_list = []
        for row in rows:
            cols = row.split('\t')
            if len(cols) == 4:
                temperature = round(int(cols[0]) / 100, 0)  if cols[0].isdigit() else None
                humidity = round(int(cols[1]) / 100) if cols[1].isdigit() else None
                data = json.loads(cols[2])['weather'][0] if len(cols[2]) > 0 else {}
                description = data.get('description', '')
                icon = data.get('icon', '')

                data_list.append({
                    "temperature": temperature,
                    "humidity": humidity,
                    "description": description,
                    "icon": icon,
                    "data_arrival_time": cols[3]
                })

        return data_list

    def get_current_day_status_data(self):
        time_now = self.get_device_local_time()
        time_now_zero_hour = datetime.datetime(
            year=time_now.year,
            month=time_now.month,
            day=time_now.day,
            tzinfo=time_now.tzinfo
        )
        date_today = time_now_zero_hour.astimezone(pytz.utc)
        date_tomorrow = date_today + timezone.timedelta(days=1)

        status_types = [
            DeviceStatus.DAILY_STATUS
        ]
        
        data_list = DeviceStatus.objects.filter(
            device=self.device,
            name__in=status_types,
            created_at__gte=date_today,
            created_at__lt=date_tomorrow
        )

        return [{
            "name": x.name,
            "created_at": x.created_at.strftime(settings.TIME_FORMAT_STRING) if x.created_at is not None else None,
            "status": x.status
        } for x in data_list]

    def get_current_day_data(self):
        time_now = self.get_device_local_time()
        time_now_zero_hour = datetime.datetime(
            year=time_now.year,
            month=time_now.month,
            day=time_now.day,
            tzinfo=time_now.tzinfo
        )
        date_today = time_now_zero_hour.astimezone(pytz.utc)
        date_tomorrow = date_today + timezone.timedelta(days=1)

        meter_types = [
            Meter.LOAD_AC_METER,
            Meter.LOAD_DC_METER
        ]

        if DeviceType.SOLAR_HYBRID_INVERTER in self.device_types or DeviceType.CHARGE_CONTROLLER in self.device_types:
            meter_types.append(Meter.DC_METER)
        
        data_list = self.get_power_and_energy_data(
            date_today,
            date_tomorrow,
            meter_type=meter_types
        )

        return data_list

    def get_current_day_weather_data(self):
        time_now = self.get_device_local_time()
        time_now_zero_hour = datetime.datetime(
            year=time_now.year,
            month=time_now.month,
            day=time_now.day,
            tzinfo=time_now.tzinfo
        )
        date_today = time_now_zero_hour.astimezone(pytz.utc)
        date_tomorrow = date_today + timezone.timedelta(days=1)

        data_weather = self.get_historic_weather_data(
            date_today,
            date_tomorrow
        )

        return data_weather

    def get_appliances_current_day(self):
        time_now = self.get_device_local_time()
        time_now_zero_hour = datetime.datetime(
            year=time_now.year,
            month=time_now.month,
            day=time_now.day,
            tzinfo=time_now.tzinfo
        )
        date_today = time_now_zero_hour.astimezone(pytz.utc)
        date_tomorrow = date_today + timezone.timedelta(days=1)

        device_equipments = [eqp.id for eqp in self.device.get_all_equipments()]

        if len(device_equipments) > 0:
            load_list = MeterLoad.objects.filter(
                equipment__in=device_equipments
            ).filter(
                data_arrival_time__gte=date_today,
                data_arrival_time__lt=date_tomorrow
            ).order_by(
                'data_arrival_time'
            )
        else:
            load_list = []

        last_data_point = None
        load_data = {}

        time_diff = 0
        for load in load_list:

            if last_data_point is not None:
                time_diff = (load.data_arrival_time - last_data_point.data_arrival_time).total_seconds()

            if time_diff > 1000:
                time_diff = 5 * 60
            elif time_diff < 0:
                logger.error("Time diff is negative. {}".format(time_diff))

            load_name = load.equipment_name
            if load_name in load_data:
                load_data[load_name]['seconds'] = load_data[load_name]['seconds'] + time_diff
                load_data[load_name]['energy'] = float(load_data[load_name]['energy']) + float(load.power) * time_diff
            else:
                load_data[load_name] = {
                    'seconds': 0,
                    'energy': 0,
                    'money': 0
                }
            last_data_point = load

        rate = self.rate.get_value() if self.rate is not None else 0.0
        for load in load_data:
            load_data[load]['hours'] = load_data[load]['seconds'] // 3600
            load_data[load]['minutes'] = load_data[load]['seconds'] % 3600 // 60
            load_data[load]['energy'] = load_data[load]['energy'] / 3600000
            load_data[load]['money'] = load_data[load]['energy'] * rate

        return load_data

    def get_device_local_time(self):
        """
            Method to return local time for the device.
        """
        device_timezone = self.device.get_timezone()
        if device_timezone is None:
            dt = timezone.now()
        else:
            dt = timezone.datetime.now(device_timezone)
        return dt

    def get_possible_equipment_list(self):
        """
            Input: power data, current time, weather temperature. List of equipments.
            Output: List of equipments that could be running.
        """
        data = self.device.get_latest_data(meter_type=[Meter.LOAD_AC_METER])
        if data is None:
            return []
        loads = MeterLoad.objects.filter(
            data_point=str(data.id)
        )
        return [{
            'equipment': load.equipment_name,
            'qty': load.count,
            'power': load.power,
        } for load in loads]

    def get_local_weather_data(self):
        return get_weather_data_cached(self.device)

    def get_energy_saving_tips(self, equipments):
        """
            Method to take input as the list of equipments running.
            And return energy saving tips.
        """
        tips = []
        time_now = self.get_device_local_time()
        day_time = True if (time_now.hour > 7 and time_now.hour < 18) else False

        weather_data_now = get_weather_data_cached(self.device)
        if weather_data_now is None:
            logger.warning("Weather data not availabe for device {}".format(self.device.ip_address))
            return tips
        temperature = weather_data_now.get('main', {}).get('temp', 0)
        humidity = weather_data_now.get('main', {}).get('humidity', 0)
        wind_speed = weather_data_now.get('wind', {}).get('speed', 0)

        for equipment in equipments:
            name = equipment['equipment']
            power = equipment['power']
            qty = equipment['qty']
            tip = None
            if name == 'Bulb':
                tip = "Replace the bulb by LED/CFL to ${} per hour.".format(qty * (((power - qty * 8) * self.rate.get_value()) / 1000))
            elif day_time and (name == 'CFL' or name == 'LED'):
                tip = "It's day time. You might not need these CFLs/LEDs."
            elif name in ['Cooler', 'Fan']:
                if temperature < (273 + 22):
                    tip = "Its already cool enough. You dont need Fan/Cooler."
            if tip:
                tips.append(tip)
        return tips
    
    def get_alarms(self):
        return []

    def calculate_import_export_status(self, aggregated_energy_data):
        """
            Input: Method accepts aggregated data by meter, and time.
            Output: energy, import export status over time.
        """
        generation_meter_name = "solar_meter"
        load_meter_name = "load_meter"
        export_meter_name = "export_energy_meter"
        import_meter_name = "import_energy_meter"

        data_dict = {}

        min_exported, max_exported = None, None
        min_imported, max_imported = None, None
        min_generated, max_generated = None, None
        min_consumed, max_consumed = None, None

        for data_point in aggregated_energy_data:
            meter = data_point["meter_name"]
            if meter in [generation_meter_name, load_meter_name, export_meter_name, import_meter_name]:
                aggregation_time = data_point["aggregation_time"]

                # update time data
                time_data = data_dict.get(aggregation_time, {})
                time_data[meter] = float(data_point["max_energy"]) - float(data_point["min_energy"])
                data_dict[aggregation_time] = time_data

                if meter == generation_meter_name:
                    if min_generated is None:
                        min_generated = float(data_point["min_energy"])
                    max_generated = float(data_point["max_energy"])
                elif meter == load_meter_name:
                    if min_consumed is None:
                        min_consumed = float(data_point["min_energy"])
                    max_consumed = float(data_point["max_energy"])
                if meter == export_meter_name:
                    if min_exported is None:
                        min_exported = float(data_point["min_energy"])
                    max_exported = float(data_point["max_energy"])
                if meter == import_meter_name:
                    if min_imported is None:
                        min_imported = float(data_point["min_energy"])
                    max_imported = float(data_point["max_energy"])

        max_exported = 0 if max_exported is None else max_exported
        min_exported = 0 if min_exported is None else min_exported
        max_imported = 0 if max_imported is None else max_imported
        min_imported = 0 if min_imported is None else min_imported
        min_consumed = 0 if min_consumed is None else min_consumed
        max_consumed = 0 if max_consumed is None else max_consumed
        min_generated = 0 if min_generated is None else min_generated
        max_generated = 0 if max_generated is None else max_generated

        data = {
            "summary": {
                "exported": max_exported - min_exported,
                "imported":  max_imported - min_imported,
                "generated":  max_generated - min_generated,
                "consumed": max_consumed - min_consumed,
            },
            "by_time": data_dict
        }

        return data
