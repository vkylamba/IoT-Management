from datetime import datetime, timedelta
from pathlib import Path

from device.models import Device, RawData
from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from device.models.device import DeviceProperty
from utils.solar.solar_day_html import NoDayData, load_local_day, process_day
from utils.solar.solar_month import month_dates, render_month_html


def build_device_monthly_report_cache_path(device_id, report_month=None):
    normalized_device = str(device_id or 'unknown').strip().replace('/', '_').replace('\\', '_')
    normalized_month = str(report_month or datetime.utcnow().strftime('%Y-%m')).strip()
    if not normalized_month:
        normalized_month = datetime.utcnow().strftime('%Y-%m')
    return Path(settings.MEDIA_ROOT) / 'device-reports' / normalized_device / f'{normalized_month}.html'


def build_device_monthly_report_raw_day_path(device_id, day_stamp):
    normalized_device = str(device_id or 'unknown').strip().replace('/', '_').replace('\\', '_')
    return Path(settings.MEDIA_ROOT) / 'device-reports' / normalized_device / 'raw-data' / f'{day_stamp}.json'


def build_device_monthly_report_day_html_path(device_id, day_stamp):
    normalized_device = str(device_id or 'unknown').strip().replace('/', '_').replace('\\', '_')
    return Path(settings.MEDIA_ROOT) / 'device-reports' / normalized_device / f'grid-solar-day-{day_stamp}.html'


def build_device_monthly_report_raw_dir(device_id):
    normalized_device = str(device_id or 'unknown').strip().replace('/', '_').replace('\\', '_')
    return Path(settings.MEDIA_ROOT) / 'device-reports' / normalized_device / 'raw-data'


def _safe_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _device_report_properties(device):
    properties = {}
    device_properties = ((getattr(device, 'other_data', None) or {}).get('device_properties') or {})
    if isinstance(device_properties, dict):
        properties.update(device_properties)

    for prop in DeviceProperty.objects.filter(device=device):
        try:
            properties[prop.name] = prop.get_value()
        except Exception:
            properties[prop.name] = prop.value
    return properties


def apply_device_defaults_to_solar_summary(summary, device):
    report_properties = _device_report_properties(device)

    site = summary.get('site') or {}
    site_name = report_properties.get('site_name') or device.alias or device.name or device.ip_address
    site_lat = _safe_float(report_properties.get('site_lat'), None)
    site_lon = _safe_float(report_properties.get('site_lon'), None)
    if site_lat is None or site_lon is None:
        lat = device.latitude()
        lon = device.longitude()
        lat_from_device = _safe_float(lat, None)
        lon_from_device = _safe_float(lon, None)
        if site_lat is None:
            site_lat = lat_from_device
        if site_lon is None:
            site_lon = lon_from_device

    site.update({'name': site_name})
    if site_lat is not None:
        site['lat'] = site_lat
    if site_lon is not None:
        site['lon'] = site_lon
    summary['site'] = site

    plant = summary.get('plant') or {}
    plant_value_overrides = {
        'solarDcKw': _safe_float(report_properties.get('plant_solar_dc_kw'), None),
        'inverterAcKw': _safe_float(report_properties.get('plant_inverter_ac_kw'), None),
        'householdLoadKw': _safe_float(report_properties.get('plant_household_load_kw'), None),
        'batteryAh': _safe_float(report_properties.get('plant_battery_ah'), None),
        'batteryAgeYears': _safe_float(report_properties.get('plant_battery_age_years'), None),
        'tiltDeg': _safe_float(report_properties.get('plant_tilt_deg'), None),
        'performanceRatio': _safe_float(report_properties.get('plant_performance_ratio'), None),
    }
    for key, value in plant_value_overrides.items():
        if value is not None:
            plant[key] = value

    if report_properties.get('plant_battery_type') not in [None, '']:
        plant['batteryType'] = report_properties.get('plant_battery_type')
    if report_properties.get('plant_azimuth') not in [None, '']:
        plant['azimuth'] = report_properties.get('plant_azimuth')

    plant['solarDcKw'] = float(plant.get('solarDcKw') or 3.2)
    plant['inverterAcKw'] = float(plant.get('inverterAcKw') or 5.0)
    plant['householdLoadKw'] = float(plant.get('householdLoadKw') or 5.0)
    summary['plant'] = plant

    tariff = summary.get('tariff') or {}
    tariff_value_overrides = {
        'importInrPerKwh': _safe_float(report_properties.get('tariff_import_inr_per_kwh'), None),
        'exportInrPerKwh': _safe_float(report_properties.get('tariff_export_inr_per_kwh'), None),
        'fixedInrPerMonth': _safe_float(report_properties.get('tariff_fixed_inr_per_month'), None),
    }
    for key, value in tariff_value_overrides.items():
        if value is not None:
            tariff[key] = value
    if report_properties.get('tariff_notes') not in [None, '']:
        tariff['notes'] = report_properties.get('tariff_notes')
    summary['tariff'] = tariff

    co2_kg_per_kwh = _safe_float(report_properties.get('co2_kg_per_kwh'), None)
    if co2_kg_per_kwh is not None:
        summary['co2KgPerKwh'] = co2_kg_per_kwh

    return summary


def _query_day_records_from_db(device, day_start, day_end):
    query_records = list(
        RawData.objects.filter(
            device=device,
            data_arrival_time__gte=day_start,
            data_arrival_time__lt=day_end,
            data_type__in=['meters-data', 'weather'],
        ).order_by('data_arrival_time')
    )
    day_records = []
    for record in query_records:
        if record.data_arrival_time is None:
            continue
        day_records.append({
            'id': str(record.id),
            'device_ip': record.device.ip_address,
            'channel': record.channel,
            'data_type': record.data_type,
            'data_arrival_time': record.data_arrival_time.isoformat().replace('+00:00', 'Z') if timezone.is_aware(record.data_arrival_time) else record.data_arrival_time.isoformat(),
            'data': record.data or {},
        })
    return day_records


def _device_coordinates(device):
    lat = device.latitude()
    lon = device.longitude()
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return None, None
    return lat, lon


def _device_meter_types_by_name(device):
    meter_types = {}
    for meter in device.get_meters():
        meter_name = str(getattr(meter, 'name', '') or '').strip()
        if not meter_name:
            continue
        meter_types[meter_name] = str(getattr(meter, 'meter_type', '') or '').strip()
    return meter_types


def get_or_generate_device_day_summary(device, day, force_refresh=False):
    day_stamp = day.isoformat()
    day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    raw_dir = build_device_monthly_report_raw_dir(device.ip_address or str(device.id))
    raw_day_path = build_device_monthly_report_raw_day_path(device.ip_address or str(device.id), day_stamp)
    daily_html_path = build_device_monthly_report_day_html_path(device.ip_address or str(device.id), day_stamp)

    records = None
    if not force_refresh:
        try:
            records = load_local_day(raw_dir, day_stamp)
        except NoDayData:
            records = None

    if records is None:
        records = _query_day_records_from_db(device, day_start, day_end)

    lat_deg, lon_deg = _device_coordinates(device)
    meter_types_by_name = _device_meter_types_by_name(device)
    summary = process_day(
        records,
        daily_html_path,
        raw_day_path,
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        meter_types_by_name=meter_types_by_name,
    )
    summary = apply_device_defaults_to_solar_summary(summary, device)
    return {
        'summary': summary,
        'records_count': len(records),
        'day_stamp': day_stamp,
        'raw_path': raw_day_path,
        'html_path': daily_html_path,
    }


def generate_device_monthly_report_job(device_pk, report_month, force_refresh=False, progress_callback=None):
    close_old_connections()
    try:
        device = Device.objects.filter(pk=device_pk).first()
        if device is None:
            raise ValueError('Device not found.')

        report_path = build_device_monthly_report_cache_path(device.ip_address or str(device.id), report_month)

        if report_path.exists() and not force_refresh:
            return {
                'device': device,
                'report_path': report_path,
                'cached': True,
                'generated': False,
                'daily_reports_generated': 0,
                'missing_days': [],
                'records_collected': 0,
            }

        year, month = map(int, report_month.split('-'))
        day_list = month_dates(year, month)
        total_days = len(day_list)

        summaries = []
        missing_days = []
        total_records_loaded = 0

        for day_index, day in enumerate(day_list):
            try:
                day_result = get_or_generate_device_day_summary(device, day, force_refresh=force_refresh)
                summaries.append(day_result['summary'])
                total_records_loaded += day_result['records_count']
            except NoDayData:
                missing_days.append(day.isoformat())
            except Exception:
                missing_days.append(day.isoformat())

            if progress_callback is not None:
                progress = min(95, int(((day_index + 1) / total_days) * 95)) if total_days else 95
                progress_callback({
                    'message': f'Processed day {day_index + 1} of {total_days} for {report_month}.',
                    'progress_percent': progress,
                    'records_collected': total_records_loaded,
                    'daily_reports_generated': len(summaries),
                    'missing_days': len(missing_days),
                })

            close_old_connections()

        if not summaries:
            raise ValueError(f'No meter data found for {report_month}.')

        report_path.parent.mkdir(parents=True, exist_ok=True)
        monthly_html = render_month_html(year, month, summaries, missing_days)
        report_path.write_text(monthly_html, encoding='utf-8')

        return {
            'device': device,
            'report_path': report_path,
            'cached': False,
            'generated': True,
            'daily_reports_generated': len(summaries),
            'missing_days': missing_days,
            'records_collected': total_records_loaded,
        }
    finally:
        close_old_connections()