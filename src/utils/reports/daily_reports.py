import datetime

import pytz
from device.models import (Device, DeviceProperty, DeviceStatus, DeviceType,
                           Meter, RawData)
from django.conf import settings
from django.utils import timezone
from pipe import select, where
from utils.dev_data import DataReports
from device_schemas.device_types import IOT_GW_SHAKTI_SOLAR_PUMP, IOT_GW_SOLAR_CC


def get_statistics_yesterday(dr, from_time, to_time, params='all'):
    """
        Get device statistics gourped by meter name. 
        Device's timezone is used in querying the data.
    """
    return dr.get_statistics_by_time(
        params=params, from_time=from_time, to_time=to_time,
        aggregation_period=datetime.timedelta(days=1)
    )


def get_statistics_for_each_day_in_last_week(dr, from_time, to_time, params='energy'):
    """
        Get device statistics gourped by meter name. 
        Device's timezone is used in querying the data.
    """    
    energy_history = dr.get_statistics_by_time(
        params,
        from_time,
        to_time,
        timezone.timedelta(days=1)
    )
    
    return dr.calculate_import_export_status(
        energy_history
    )


def get_yesterdays_power_data(dr, from_time, to_time):
    meter_types = [
        Meter.LOAD_AC_METER
    ]

    if DeviceType.SOLAR_HYBRID_INVERTER in dr.device_types:
        meter_types.extend([Meter.DC_METER, Meter.AC_METER])

    return dr.get_power_and_energy_data(
        from_time,
        to_time,
        meter_type=meter_types
    )


def get_daily_report(device):
    dr = DataReports(device)
    local_time = dr.get_device_local_time()
    
    to_time = datetime.datetime(local_time.year, local_time.month, local_time.day)
    from_time = to_time - datetime.timedelta(days=1)
    from_time_1 = to_time - datetime.timedelta(days=7)

    local_time = local_time.astimezone(pytz.utc)
    from_time = from_time.astimezone(pytz.utc)
    to_time = to_time.astimezone(pytz.utc)
    from_time_1 = from_time_1.astimezone(pytz.utc)


    device_type = device.type
    if device_type is not None:
        device_type = device_type.code

    if device_type in (IOT_GW_SHAKTI_SOLAR_PUMP, IOT_GW_SOLAR_CC):
        data_points = RawData.objects.filter(
            device=device,
            data_arrival_time__gt=from_time,
            data_arrival_time__lte=to_time
        ).count()
        energy_consumed = device.other_data.get("energy_consumed_this_day", 0)
        energy_generated = device.other_data.get("energy_generated_this_day", 0)
        energy_imported = device.other_data.get("energy_imported_this_day", 0)
        energy_exported = device.other_data.get("energy_exported_this_day", 0)
        meter_names = []
    else:
        last_day_data = [meter_data for meter_data in get_statistics_yesterday(dr, from_time, to_time)]
        
        if len(last_day_data) == 0:
            return None

        meter_names = [meter.name for meter in dr.meters]
    
        energy_export_data = list(last_day_data | where(lambda x: x['meter_name'] == 'export_energy_meter'))
        if len(energy_export_data) > 0:
            energy_export_data = energy_export_data[0]
        else:
            energy_export_data = {}

        energy_import_data = list(last_day_data | where(lambda x: x['meter_name'] == 'import_energy_meter'))
        if len(energy_import_data) > 0:
            energy_import_data = energy_import_data[0]
        else:
            energy_import_data = {}

        energy_generation_data = list(last_day_data | where(lambda x: x['meter_name'] == 'solar_meter'))
        if len(energy_generation_data) > 0:
            energy_generation_data = energy_generation_data[0]
        else:
            energy_generation_data = {}

        energy_consumption_data = list(last_day_data | where(lambda x: x['meter_name'] == 'load_meter'))
        if len(energy_consumption_data) > 0:
            energy_consumption_data = energy_consumption_data[0]
        else:
            energy_consumption_data = {}

        any_meter_data = list(last_day_data | where(lambda x: x['meter_name'] in meter_names))
        if len(any_meter_data) > 0:
            any_meter_data = any_meter_data[0]
        else:
            any_meter_data = {}
        data_points = float(any_meter_data.get('data_points', 0))

        energy_exported = float(energy_export_data.get('max_energy', 0)) - float(energy_export_data.get('min_energy', 0))
        energy_imported = float(energy_import_data.get('max_energy', 0)) - float(energy_import_data.get('min_energy', 0))
        energy_generated = float(energy_generation_data.get('max_energy', 0)) - float(energy_generation_data.get('min_energy', 0))
        energy_consumed = float(energy_consumption_data.get('max_energy', 0)) - float(energy_consumption_data.get('min_energy', 0))


    data_frequency_minutes = DeviceProperty.objects.filter(device=device, name='data_frequency_minutes').first()
    if data_frequency_minutes:
        data_frequency_minutes = data_frequency_minutes.get_value()
    else:
        data_frequency_minutes = 10

    active_data_days = data_points * data_frequency_minutes / 60 / 24

    if dr.rate is not None:
        consumption_rate = dr.rate.get_value()
    else:
        consumption_rate = 10
    consumption_bill = energy_consumed * consumption_rate

    net_bill = (energy_imported - energy_exported) * consumption_rate
    savings = consumption_bill - net_bill
    
    total_investment = DeviceProperty.objects.filter(device=device, name='total_investment').first()
    total_recovery_amount = DeviceProperty.objects.filter(device=device, name='total_recovery_amount').first()
    currency = DeviceProperty.objects.filter(device=device, name='currency').first()
    
    if total_investment:
        total_investment = total_investment.get_value()
    if total_recovery_amount:
        total_recovery_amount = total_recovery_amount.get_value()
    if currency:
        currency = currency.get_value()

    daily_report = {
        "device": device.alias,
        "device_ip_address": device.ip_address,
        "report_generation_time": local_time.strftime(settings.TIME_FORMAT_STRING),
        "from_time": from_time.strftime(settings.TIME_FORMAT_STRING),
        "to_time": to_time.strftime(settings.TIME_FORMAT_STRING),
        "active_data_days": active_data_days,
        "currency": currency,
        "total_investment": total_investment,
        "total_recovery_amount": total_recovery_amount,
        'power_history_yesterday': [x for x in get_yesterdays_power_data(dr, from_time, to_time)],
        "per_day_energy_statistics": get_statistics_for_each_day_in_last_week(dr, from_time_1, to_time)
    }

    if "export_energy_meter" in meter_names:
        daily_report["energy_exported"] = energy_exported

    if "import_energy_meter" in meter_names:
        daily_report["energy_imported"] = energy_imported
    
    if "solar_meter" in meter_names:
        daily_report["energy_generated"] = energy_generated

    if "load_meter" in meter_names:
        daily_report["energy_consumed"] = energy_consumed
        daily_report["consumption_rate"] = consumption_rate
        daily_report["consumption_bill"] = consumption_bill
        daily_report["net_bill"] = net_bill
        daily_report["savings"] = savings

    dev_status = DeviceStatus(
        device=device,
        name=DeviceStatus.LAST_DAY_REPORT,
        status=daily_report
    )
    dev_status.save()
    return daily_report
