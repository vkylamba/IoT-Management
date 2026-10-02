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


def apply_device_defaults_to_solar_summary(summary, device):
    site = summary.get('site') or {}
    lat = device.latitude()
    lon = device.longitude()
    if lat not in [None, '', 'None'] and lon not in [None, '', 'None']:
        site.update({
            'name': device.alias or device.name or device.ip_address,
            'lat': float(lat),
            'lon': float(lon),
        })
    summary['site'] = site

    plant = summary.get('plant') or {}
    plant.update({
        'solarDcKw': float(plant.get('solarDcKw') or 3.2),
        'inverterAcKw': float(plant.get('inverterAcKw') or 5.0),
        'householdLoadKw': float(plant.get('householdLoadKw') or 5.0),
    })
    summary['plant'] = plant
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
    summary = process_day(records, daily_html_path, raw_day_path, lat_deg=lat_deg, lon_deg=lon_deg)
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