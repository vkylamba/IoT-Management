import logging

from device.models import DeviceProperty, Meter
from utils.dev_data import DataReports
from utils.solar.utilization_matrix import get_solar_system_state

logger = logging.getLogger("django")


def get_temperature_data_current_day(dr):
    stats = dr.get_statistics_current_day()
    
    temperature_data = {}
    for meter_stats in stats:
        meter_name = meter_stats['meter_name']
        avg_temperature = float(meter_stats.get('avg_temperature', 0))
        # max_temperature = float(meter_stats.get('max_temperature', 0))
        # min_temperature = float(meter_stats.get('min_temperature', 0))

        temperature_data[meter_name] = avg_temperature

    return temperature_data

def get_energy_data_current_day(dr):
    stats = dr.get_statistics_current_day()
    
    energy_data = {}
    for meter_stats in stats:
        meter_name = meter_stats['meter_name']
        max_energy = float(meter_stats.get('max_energy', 0))
        min_energy = float(meter_stats.get('min_energy', 0))

        energy_data[meter_name] = max_energy - min_energy
    
    return energy_data

def get_energy_data_current_month(dr):
    stats = dr.get_statistics_current_month()
    
    energy_data = {}
    for meter_stats in stats:
        meter_name = meter_stats['meter_name']
        max_energy = float(meter_stats.get('max_energy', 0))
        min_energy = float(meter_stats.get('min_energy', 0))

        energy_data[meter_name] = max_energy - min_energy
    
    return energy_data

def update_monthly_bill(dev_prop, device, **kwargs):
    energy_this_month = kwargs.get("energy_this_month")
    pay_per_unit, created = DeviceProperty.objects.get_or_create(
        device=device,
        name="pay_per_unit"
    )
    pay_per_unit = float(pay_per_unit.value) if pay_per_unit.value != '' else 0
    kwh = energy_this_month.get("load_meter", 0)
    dev_prop['value'] = pay_per_unit * kwh

def update_currency(dev_prop, device, **kwargs):
    currency, created = DeviceProperty.objects.get_or_create(
        device=device,
        name="currency"
    )
    currency = currency.value
    dev_prop['value'] = currency

def update_pay_per_unit(dev_prop, device, **kwargs):
    pay_per_unit, created = DeviceProperty.objects.get_or_create(
        device=device,
        name="pay_per_unit"
    )
    pay_per_unit = float(pay_per_unit.value) if pay_per_unit.value != '' else 0
    dev_prop['value'] = pay_per_unit

def update_cost_savings(dev_prop, device, **kwargs):
    energy_this_month = kwargs.get("energy_this_month")
    pay_per_unit, created = DeviceProperty.objects.get_or_create(
        device=device,
        name="pay_per_unit"
    )
    pay_per_unit = float(pay_per_unit.value) if pay_per_unit.value != '' else 0
    kwh = energy_this_month.get("solar_meter", 0)
    dev_prop['value'] = pay_per_unit * kwh

def update_energy_generated_this_month(dev_prop, device, **kwargs):
    energy_this_month = kwargs.get("energy_this_month")
    kwh = energy_this_month.get("solar_meter", 0)
    dev_prop['value'] = kwh

def update_energy_consumed_this_month(dev_prop, device, **kwargs):
    energy_this_month = kwargs.get("energy_this_month")
    kwh = energy_this_month.get("load_meter", 0)
    dev_prop['value'] = kwh

def update_energy_exported_this_month(dev_prop, device, **kwargs):
    energy_this_month = kwargs.get("energy_this_month")
    energy_data = energy_this_month
    dev_prop['value'] = energy_data.get("export_energy_meter", 0)

def update_energy_imported_this_month(dev_prop, device, **kwargs):
    energy_data = kwargs.get("energy_this_month")
    dev_prop['value'] = energy_data.get("import_energy_meter", 0)

def update_energy_generated_this_day(dev_prop, device, **kwargs):
    energy_this_day = kwargs.get("energy_this_day")
    kwh = energy_this_day.get("solar_meter", 0)
    dev_prop['value'] = kwh

def update_energy_consumed_this_day(dev_prop, device, **kwargs):
    energy_this_day = kwargs.get("energy_this_day")
    kwh = energy_this_day.get("load_meter", 0)
    dev_prop['value'] = kwh


def update_energy_exported_this_day(dev_prop, device, **kwargs):
    energy_data = kwargs.get("energy_this_day")
    dev_prop['value'] = energy_data.get("export_energy_meter", 0)

def update_energy_imported_this_day(dev_prop, device, **kwargs):
    energy_data = kwargs.get("energy_this_day")
    dev_prop['value'] = energy_data.get("import_energy_meter", 0)


def update_battery_charging_status_solar_inverter(dev_prop, device, **kwargs):
    meters_and_data = kwargs.get("meters_and_data")
    inverter_power = 0
    battery_power = 0
    battery_current = 0
    status = ""

    for meter_and_data in meters_and_data:
        meter = meter_and_data["meter"]
        data_point = meter_and_data["data"]
        if meter.name == "battery_meter":
            battery_power = data_point.get("power", 0)
            battery_current = data_point.get("current", 0)
        if meter.name == "inverter_meter":
            inverter_power = data_point.get("power", 0)

    battery_power = -1 * battery_power if battery_power < 0 else battery_power
    if inverter_power < 0:
        status = "Charging"
        battery_power =  -1 * inverter_power if inverter_power < 0 else inverter_power
    elif battery_current < 0:
        status = "Charging"
    else:
        status = "Discharging"

    dev_prop['value'] = f"{status} {round(battery_power, 2)} W"


def update_battery_charging_status_solar_inverter_mona_v1(dev_prop, device, **kwargs):
    meters_and_data = kwargs.get("meters_and_data")
    solar_power = 0
    grid_power = 0
    load_power = 0
    status = ""

    for meter_and_data in meters_and_data:
        meter = meter_and_data["meter"]
        data_point = meter_and_data["data"]
        if meter.name == "solar_meter":
            solar_power = data_point.get("power", 0)
        if meter.name == "grid_meter":
            grid_power = data_point.get("power", 0)
        if meter.name == "load_meter":
            load_power = data_point.get("power", 0)

    if solar_power > (grid_power + load_power) and grid_power > 0:
        status = "Charging"
        battery_power = solar_power - (grid_power + load_power)
    elif solar_power <= 0 and grid_power > load_power:
        status = "Charging"
        battery_power = grid_power - load_power
    else:
        status = "Discharging"
        battery_power = load_power - (solar_power + grid_power)

    dev_prop['value'] = f"{status} {round(battery_power, 2)} W"


def update_battery_charging_status(dev_prop, device, **kwargs):
    meters_and_data = kwargs.get("meters_and_data")
    battery_power = 0
    battery_current = 0
    status = ""

    for meter_and_data in meters_and_data:
        meter = meter_and_data["meter"]
        data_point = meter_and_data["data"]
        if meter.name == "battery_meter":
            battery_power = data_point.get("power", 0)
            battery_current = data_point.get("current", 0)

    battery_power = -1 * battery_power if battery_power < 0 else battery_power
    if battery_current < 0:
        status = "Charging"
    else:
        status = "Discharging"

    dev_prop['value'] = f"{status} {round(battery_power, 2)} W"


def update_net_meter_status(dev_prop, device, **kwargs):
    meters_and_data = kwargs.get("meters_and_data")
    grid_voltage = 0
    grid_power = 0
    status = ""

    for meter_and_data in meters_and_data:
        meter = meter_and_data["meter"]
        data_point = meter_and_data["data"]
        if meter.name == "grid_meter":
            grid_voltage = data_point.get("voltage", 0)
            grid_power = data_point.get("power", 0)

    if grid_voltage == 0:
        status = "Grid Absent"
    elif grid_power < 0:
        status = "Exporting"
    else:
        status = "Importing"
    
    grid_power =  -1 * grid_power if grid_power < 0 else grid_power
    dev_prop['value'] = f"{status} {round(grid_power, 2)} W"


def update_net_meter_status_mona_v1(dev_prop, device, **kwargs):
    # The assumption here is that the inverter charges the batteries on Solar
    # So if the solar power is more than the load and grid power combined then it is exporting
    meters_and_data = kwargs.get("meters_and_data")
    solar_power = 0
    grid_current = 0
    grid_power = 0
    load_power = 0
    status = ""

    for meter_and_data in meters_and_data:
        meter = meter_and_data["meter"]
        data_point = meter_and_data["data"]
        if meter.name == "solar_meter":
            solar_power = data_point.get("power", 0)
        if meter.name == "grid_meter":
            grid_current = data_point.get("current", 0)
            grid_power = data_point.get("power", 0)
        if meter.name == "load_meter":
            load_power = data_point.get("power", 0)

    if grid_current == 0:
        status = "Grid Absent"
    elif grid_power > 0 and solar_power < (grid_power + load_power) and load_power > 0.3 * grid_power:
        status = "Importing"
    elif solar_power > (grid_power + load_power) and grid_power > 0:
        status = "Exporting"
    else:
        status = "Unknown"

    dev_prop['value'] = f"{status} {round(grid_power, 2)} W"


def update_solar_status(dev_prop, device, **kwargs):

    meters_and_data = kwargs.get("meters_and_data")
    solar_power = 0

    for meter_and_data in meters_and_data:
        meter = meter_and_data["meter"]
        data_point = meter_and_data["data"]
        if meter.name == "solar_meter":
            solar_power = data_point.get("power", 0)

    dev_prop['value'] = f"{round(solar_power, 2)} W"


def update_load_status(dev_prop, device, **kwargs):
    meters_and_data = kwargs.get("meters_and_data")
    load_power = 0

    for meter_and_data in meters_and_data:
        meter = meter_and_data["meter"]
        data_point = meter_and_data["data"]
        if meter.meter_type == Meter.LOAD_AC_METER:
            load_power += data_point.get("power", 0)

    dev_prop['value'] = f"{round(load_power, 2)} W"


def update_weather_status(dev_prop, device, **kwargs):
    dev_prop['value'] = kwargs.get("device_weather_data")


def update_system_temperature_status(dev_prop, device, **kwargs):

    meters_and_data = kwargs.get("meters_and_data")
    system_temperature = 0.0
    system_humidity = 0.0

    for meter_and_data in meters_and_data:
        meter = meter_and_data["meter"]
        data_point = meter_and_data["data"]
        if meter.name == "weather_meter":
            system_temperature += data_point.get("temperature", 0)
            system_humidity += data_point.get("humidity", 0)

    dev_prop['value'] = f"{round(system_temperature, 2)} C, {round(system_humidity, 2)} H"


def update_system_status(dev_prop, device, **kwargs):

    meters_and_data = kwargs.get("meters_and_data")
    device_localtime = kwargs.get("device_localtime")
    device_weather_data = kwargs.get("device_weather_data")

    grid_voltage = 0
    grid_power = 0
    load_power = 0
    solar_power = 0

    grid_status = ""
    solar_status = ""
    day_status = ""
    load_status = ""
    weather_status = ""

    for meter_and_data in meters_and_data:
        meter = meter_and_data["meter"]
        data_point = meter_and_data["data"]
        if meter.name == "grid_meter":
            grid_voltage = data_point.get("voltage", 0)
            grid_power += data_point.get("power", 0)
        elif meter.meter_type == Meter.LOAD_AC_METER:
            load_power += data_point.get("power", 0)
        elif meter.name == "solar_meter":
            solar_power += data_point.get("power", 0)

    if grid_voltage == 0:
        grid_status = "ABSENT"
    elif grid_power < 0:
        grid_status = "EXPORTING"
    elif grid_power > 0:
        grid_status = "IMPORTING"
    else:
        grid_status = "PRESENT"

    if solar_power > 1000:
        solar_status = "HIGH"
    elif solar_power < 500:
        solar_status = "LOW"
    else:
        solar_status = "MEDIUM"

    if device_localtime.hour < 6 and device_localtime.hour > 18:
        day_status = "NIGHT"
    elif device_localtime.hour >= 6 and device_localtime.hour < 11:
        day_status = "MORNING"
    elif device_localtime.hour >= 11 and device_localtime.hour <= 16:
        day_status = "NOON"
    else:
        day_status = "EVENING"

    if load_power > 1000:
        load_status = "HIGH"
    elif load_power < 500:
        load_status = "LOW"
    else:
        load_status = "MEDIUM"

    if device_weather_data is not None:
        device_weather_data = device_weather_data.get("weather", [{}])[0]
        device_weather_data = device_weather_data.get("description", "").lower()
        if "cloud" in device_weather_data:
            weather_status = "CLOUDY"
        elif "rain" in device_weather_data:
            weather_status = "RAINY"
        else:
            weather_status = "SUNNY"

    dev_prop['value'] = get_solar_system_state(grid_status, solar_status, day_status, load_status, weather_status)


def update_system_status_mona_v1(dev_prop, device, **kwargs):

    meters_and_data = kwargs.get("meters_and_data")
    device_localtime = kwargs.get("device_localtime")
    device_weather_data = kwargs.get("device_weather_data")

    grid_current = 0
    grid_power = 0
    load_power = 0
    solar_power = 0

    grid_status = ""
    solar_status = ""
    day_status = ""
    load_status = ""
    weather_status = ""

    system_temperature = 0.0
    system_humidity = 0.0

    for meter_and_data in meters_and_data:
        meter = meter_and_data["meter"]
        data_point = meter_and_data["data"]
        if meter.name == "grid_meter":
            grid_current = data_point.get("current", 0)
            grid_power += data_point.get("power", 0)
        elif meter.meter_type == Meter.LOAD_AC_METER:
            load_power += data_point.get("power", 0)
        elif meter.name == "solar_meter":
            solar_power += data_point.get("power", 0)
        elif meter.name == "weather_meter":
            system_temperature += data_point.get("temperature", 0)
            system_humidity += data_point.get("humidity", 0)

    if grid_current == 0:
        grid_status = "ABSENT"
    if solar_power > (grid_power + load_power) and grid_power > 0:
        grid_status = "EXPORTING"
    elif grid_power > 0:
        grid_status = "IMPORTING"
    else:
        grid_status = "PRESENT"

    if solar_power == 0:
        solar_status = "ZERO"
    elif solar_power > 1000:
        solar_status = "HIGH"
    elif solar_power < 500:
        solar_status = "LOW"
    else:
        solar_status = "MEDIUM"

    if device_localtime.hour >= 6 and device_localtime.hour < 11:
        day_status = "MORNING"
    elif device_localtime.hour >= 11 and device_localtime.hour <= 16:
        day_status = "NOON"
    elif device_localtime.hour >= 16 and device_localtime.hour <= 19:
        day_status = "EVENING"
    else:
        day_status = "NIGHT"

    if load_power > 1000:
        load_status = "HIGH"
    elif load_power < 500:
        load_status = "LOW"
    else:
        load_status = "MEDIUM"

    weather_status = "SUNNY"
    if device_weather_data is not None:
        device_weather_data = device_weather_data.get("weather", [{}])[0]
        device_weather_data = device_weather_data.get("description", "").lower()
        if "cloud" in device_weather_data:
            weather_status = "CLOUDY"
        elif "rain" in device_weather_data:
            weather_status = "RAINY"
        else:
            weather_status = "SUNNY"


    dev_prop['value'] = get_solar_system_state(grid_status, solar_status, day_status, load_status, weather_status)



def update_device_properties(device, meters_and_data):
    from .device_properties import DEV_PROPERTIES
    dr = DataReports(device)
    dev_props = []
    for dev_type in dr.device_types:
        dev_props.extend(DEV_PROPERTIES.get(dev_type, []))

    energy_this_month = get_energy_data_current_month(dr)
    energy_this_day = get_energy_data_current_day(dr)
    # temperature_data_this_day = get_temperature_data_current_day(dr)
    device_localtime = dr.get_device_local_time()
    device_weather_data = dr.get_local_weather_data()

    data = {}
    for dev_prop in dev_props:
        logger.info("Updating property {} for device {}".format(dev_prop, device.ip_address))
        if dev_prop['update']:
            dev_prop['update_method'](
                dev_prop, device,
                energy_this_month=energy_this_month,
                energy_this_day=energy_this_day,
                meters_and_data=meters_and_data,
                device_localtime=device_localtime,
                device_weather_data=device_weather_data
            )

        data[dev_prop['name']] = dev_prop['value']
    else:
        prop_names = ', '.join([x["name"] for x in dev_props])
        logger.info(f"Device: {device.ip_address}, Updated properties: {prop_names}")
    return data
