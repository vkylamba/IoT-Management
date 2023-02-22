import datetime

import pytz
from device.models import Meter
from device.models import DeviceProperty, DeviceStatus, DeviceType
from django.conf import settings
from django.utils import timezone
from pipe import select, where
from utils.dev_data import DataReports


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

    last_month_data = [meter_data for meter_data in get_statistics_yesterday(dr, from_time, to_time)]
    
    if len(last_month_data) == 0:
        return None
    
    energy_export_data = list(last_month_data | where(lambda x: x['meter_name'] == 'export_energy_meter'))[0]
    
    data_points = float(energy_export_data.get('data_points'))
    active_data_days = data_points * 10 / 60 / 24

    energy_exported = float(energy_export_data.get('max_energy', 0)) - float(energy_export_data.get('min_energy', 0))
    
    energy_import_data = list(last_month_data | where(lambda x: x['meter_name'] == 'import_energy_meter'))[0]
    energy_imported = float(energy_import_data.get('max_energy', 0)) - float(energy_import_data.get('min_energy', 0))
    
    energy_generation_data = list(last_month_data | where(lambda x: x['meter_name'] == 'solar_meter'))[0]
    energy_generated = float(energy_generation_data.get('max_energy', 0)) - float(energy_generation_data.get('min_energy', 0))
    
    energy_consumption_data = list(last_month_data | where(lambda x: x['meter_name'] == 'load_meter'))[0]
    energy_consumed = float(energy_consumption_data.get('max_energy', 0)) - float(energy_consumption_data.get('min_energy', 0))
    
    
    consumption_rate = dr.rate.get_value()
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
        "energy_exported": energy_exported,
        "energy_imported": energy_imported,
        "energy_generated": energy_generated,
        "energy_consumed": energy_consumed,
        "consumption_rate": consumption_rate,
        "consumption_bill": consumption_bill,
        "net_bill": net_bill,
        "savings": savings,
        "currency": currency,
        "total_investment": total_investment,
        "total_recovery_amount": total_recovery_amount,
        'power_history_yesterday': [x for x in get_yesterdays_power_data(dr, from_time, to_time)],
        "per_day_energy_statistics": get_statistics_for_each_day_in_last_week(dr, from_time_1, to_time)
    }
   
    dev_status = DeviceStatus(
        device=device,
        name=DeviceStatus.LAST_DAY_REPORT,
        status=daily_report
    )
    dev_status.save()
    return daily_report
