import logging
from datetime import datetime, timedelta

import pytz
from django.conf import settings
from django.utils import timezone

from device.models import AssetStatus, DeviceProperty, StatusType
from utils.solar.monthly_report_job import get_or_generate_device_day_summary
from utils.solar.solar_day_html import NoDayData

logger = logging.getLogger('django') 


REPORT_PERIOD_TO_LEGACY_NAME = {
    'day': AssetStatus.LAST_DAY_REPORT,
    'week': AssetStatus.LAST_WEEK_REPORT,
    'month': AssetStatus.LAST_MONTH_REPORT,
}


def _normalize_report_period(report_period):
    if report_period is None:
        return None
    normalized_period = str(report_period).strip().lower()
    if normalized_period == 'yesterday':
        return 'day'
    if normalized_period in REPORT_PERIOD_TO_LEGACY_NAME:
        return normalized_period
    return None


def _status_type_period_candidates(normalized_period):
    if normalized_period == 'day':
        return ['day', 'yesterday']
    return [normalized_period]


def get_report_status_type_for_period(device, report_period):
    normalized_period = _normalize_report_period(report_period)
    if normalized_period is None:
        return None

    period_candidates = _status_type_period_candidates(normalized_period)
    for period_candidate in period_candidates:
        query = {
            'target_type': StatusType.STATUS_TARGET_REPORT,
            'report_period': period_candidate,
        }

        status_type = StatusType.objects.filter(device=device, **query).order_by('-created_at')
        for candidate in status_type:
            if getattr(candidate, 'active', False):
                return candidate

        device_type = getattr(device, 'type', None)
        if device_type is not None:
            status_type = StatusType.objects.filter(device_type=device_type, **query).order_by('-created_at')
            for candidate in status_type:
                if getattr(candidate, 'active', False):
                    return candidate

    return None


def get_report_status_names_for_period(device, report_period):
    normalized_period = _normalize_report_period(report_period)
    if normalized_period is None:
        return []

    legacy_name = REPORT_PERIOD_TO_LEGACY_NAME[normalized_period]
    report_status_type = get_report_status_type_for_period(device, normalized_period)
    if report_status_type is None or not report_status_type.name:
        return [legacy_name]

    status_names = [report_status_type.name]
    if report_status_type.name != legacy_name:
        status_names.append(legacy_name)
    return status_names


def get_report_status_name_for_period(device, report_period):
    status_names = get_report_status_names_for_period(device, report_period)
    return status_names[0] if status_names else None


def get_latest_report_data_for_period(device, report_period):
    for report_name in get_report_status_names_for_period(device, report_period):
        report_status = AssetStatus.objects.filter(
            device=device,
            name=report_name,
        ).order_by('-created_at').first()
        if report_status and report_status.status is not None:
            return report_status.status
    return None


def _get_device_timezone(device):
    device_timezone = getattr(device, 'get_timezone', lambda: None)()
    return device_timezone or pytz.utc


def _to_local_window_utc(start_local, end_local):
    return start_local.astimezone(pytz.utc), end_local.astimezone(pytz.utc)


def _get_running_status_names_for_device(device):
    status_types = StatusType.objects.filter(
        device=device,
        target_type=StatusType.STATUS_TARGET_DEVICE,
    ).order_by('-created_at')

    names = []
    for status_type in status_types:
        if not getattr(status_type, 'active', False):
            continue
        if status_type.name and status_type.name not in names:
            names.append(status_type.name)

    if AssetStatus.DAILY_STATUS not in names:
        names.append(AssetStatus.DAILY_STATUS)
    return names


def _build_day_windows(start_local_date, day_count):
    windows = []
    for day_offset in range(day_count):
        windows.append(start_local_date + timedelta(days=day_offset))
    return windows


def _build_meter_row(imported, exported, generated=0.0, consumed=0.0, report_html_path='', report_html_url=''):
    return {
        'solar_meter': float(generated),
        'load_meter': float(consumed),
        'import_energy_meter': float(imported),
        'export_energy_meter': float(exported),
        'report_html_path': report_html_path,
        'report_html_url': report_html_url,
    }


def _report_day_html_url(device, day_date):
    normalized_device = str(device.ip_address or device.id).strip().replace('/', '_').replace('\\', '_')
    day_stamp = day_date.strftime('%Y-%m-%d')
    media_root = str(settings.MEDIA_ROOT).rstrip('/')
    relative_path = f'device-reports/{normalized_device}/grid-solar-day-{day_stamp}.html'
    return {
        'path': f'{media_root}/{relative_path}',
        'url': f"{settings.MEDIA_URL.rstrip('/')}/{relative_path}",
    }


def _parse_report_selection(normalized_period, selection):
    selection = selection or {}
    if normalized_period == 'day':
        day_value = (selection.get('day') or '').strip()
        if not day_value:
            return {}
        return {'day': datetime.strptime(day_value, '%Y-%m-%d').date()}

    if normalized_period == 'week':
        week_start_value = (selection.get('week_start') or '').strip()
        if not week_start_value:
            return {}
        return {'week_start': datetime.strptime(week_start_value, '%Y-%m-%d').date()}

    month_value = (selection.get('month') or '').strip()
    if not month_value:
        return {}
    month_start = datetime.strptime(month_value, '%Y-%m').date().replace(day=1)
    return {'month_start': month_start, 'month': month_value}


def _build_summary_from_rows(rows):
    totals = {
        'generated': 0.0,
        'consumed': 0.0,
        'imported': 0.0,
        'exported': 0.0,
    }
    for row in rows.values():
        totals['generated'] += float(row.get('solar_meter', 0) or 0)
        totals['consumed'] += float(row.get('load_meter', 0) or 0)
        totals['imported'] += float(row.get('import_energy_meter', 0) or 0)
        totals['exported'] += float(row.get('export_energy_meter', 0) or 0)

    totals['energy_generated'] = totals['generated']
    totals['energy_consumed'] = totals['consumed']
    totals['energy_imported'] = totals['imported']
    totals['energy_exported'] = totals['exported']
    return totals

def _get_currency_and_rate(device, latest_running_status):
    latest_running_status = latest_running_status or {}
    currency_property = DeviceProperty.objects.filter(device=device, name='currency').first()
    rate_property = DeviceProperty.objects.filter(device=device, name='pay_per_unit').first()

    currency = latest_running_status.get('currency')
    if currency in [None, ''] and currency_property:
        currency = currency_property.get_value()
    if currency in [None, '']:
        currency = '$'

    rate = latest_running_status.get('pay_per_unit')
    if rate in [None, ''] and rate_property:
        rate = rate_property.get_value()
    if rate in [None, '']:
        rate = 0

    rate_value = rate if isinstance(rate, (int, float, str)) else 0
    try:
        rate = float(rate_value)
    except (TypeError, ValueError):
        rate = 0.0
    return currency, rate


def _base_report_payload(device, from_utc, to_utc):
    payload = {
        'device': device.alias,
        'device_ip_address': device.ip_address,
        'report_generation_time': timezone.now().strftime(settings.TIME_FORMAT_STRING),
        'from_time': from_utc.strftime(settings.TIME_FORMAT_STRING),
        'to_time': to_utc.strftime(settings.TIME_FORMAT_STRING),
    }
    total_investment = DeviceProperty.objects.filter(device=device, name='total_investment').first()
    total_recovery_amount = DeviceProperty.objects.filter(device=device, name='total_recovery_amount').first()
    payload['total_investment'] = total_investment.get_value() if total_investment else 0
    payload['total_recovery_amount'] = total_recovery_amount.get_value() if total_recovery_amount else 0
    return payload


def _load_latest_running_status(device):
    for status_name in _get_running_status_names_for_device(device):
        latest_status = AssetStatus.objects.filter(
            device=device,
            name=status_name,
        ).order_by('-created_at').first()
        if latest_status and latest_status.status:
            return latest_status.status
    return {}


def _report_window_for_period(device_timezone, normalized_period, selection=None):
    parsed_selection = _parse_report_selection(normalized_period, selection)
    local_now = timezone.now().astimezone(device_timezone)
    today_start_local = device_timezone.localize(datetime.combine(local_now.date(), datetime.min.time()))

    if normalized_period == 'day':
        selected_day = parsed_selection.get('day')
        if selected_day is not None:
            from_local = device_timezone.localize(datetime.combine(selected_day, datetime.min.time()))
            return from_local, from_local + timedelta(days=1), parsed_selection
        from_local = today_start_local - timedelta(days=1)
        to_local = today_start_local
        return from_local, to_local, parsed_selection

    if normalized_period == 'week':
        week_start = parsed_selection.get('week_start')
        if week_start is not None:
            from_local = device_timezone.localize(datetime.combine(week_start, datetime.min.time()))
            return from_local, from_local + timedelta(days=7), parsed_selection
        from_local = today_start_local - timedelta(days=7)
        to_local = today_start_local
        return from_local, to_local, parsed_selection

    month_start = parsed_selection.get('month_start')
    if month_start is not None:
        from_local = device_timezone.localize(datetime.combine(month_start, datetime.min.time()))
        next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        to_local = device_timezone.localize(datetime.combine(next_month, datetime.min.time()))
        return from_local, to_local, parsed_selection

    month_start_local = device_timezone.localize(datetime.combine(local_now.date().replace(day=1), datetime.min.time()))
    return month_start_local, today_start_local, parsed_selection


def _calculate_report_from_raw_data(device, normalized_period, selection=None):
    device_timezone = _get_device_timezone(device)
    from_local, to_local, parsed_selection = _report_window_for_period(device_timezone, normalized_period, selection=selection)
    from_utc, to_utc = _to_local_window_utc(from_local, to_local)

    by_time = {}
    active_data_days = 0
    day_count = max(1, (to_local.date() - from_local.date()).days)
    day_windows = _build_day_windows(from_local.date(), day_count)

    for day_date in day_windows:
        try:
            day_result = get_or_generate_device_day_summary(device, day_date, force_refresh=False)
            summary = day_result['summary']
            totals = summary.get('totals', {})
            report_link = _report_day_html_url(device, day_date)
            generated = float(totals.get('estimatedGenKwh') or totals.get('idealSolarKwh') or 0)
            consumed = float(totals.get('loadKwh') or 0)
            imported = float(totals.get('importKwh') or 0)
            exported = float(totals.get('exportKwh') or 0)
            day_row = _build_meter_row(
                imported,
                exported,
                generated,
                consumed,
                report_html_path=report_link['path'],
                report_html_url=report_link['url'],
            )
            by_time[day_date.strftime('%Y-%m-%d')] = day_row
            active_data_days += 1
        except NoDayData:
            report_link = _report_day_html_url(device, day_date)
            day_row = _build_meter_row(0, 0, 0, 0, report_html_path=report_link['path'], report_html_url=report_link['url'])
            by_time[day_date.strftime('%Y-%m-%d')] = day_row
        except Exception:
            logger.exception('Failed to build solar summary for %s (%s)', device.ip_address, day_date)
            report_link = _report_day_html_url(device, day_date)
            day_row = _build_meter_row(0, 0, 0, 0, report_html_path=report_link['path'], report_html_url=report_link['url'])
            by_time[day_date.strftime('%Y-%m-%d')] = day_row

    summary = _build_summary_from_rows(by_time)
    report_payload = _base_report_payload(device, from_utc, to_utc)
    report_payload['active_data_days'] = active_data_days
    report_payload['per_day_energy_statistics'] = {
        'by_time': by_time,
        'summary': summary
    }
    if parsed_selection.get('day') is not None:
        report_payload['selected_day'] = parsed_selection['day'].isoformat()
    if parsed_selection.get('week_start') is not None:
        report_payload['selected_week_start'] = parsed_selection['week_start'].isoformat()
    if parsed_selection.get('month') is not None:
        report_payload['selected_month'] = parsed_selection['month']
    return report_payload


def calculate_report_status_for_period(device, report_period, selection=None, persist=True):
    normalized_period = _normalize_report_period(report_period)
    if normalized_period is None:
        return None

    report_payload = _calculate_report_from_raw_data(device, normalized_period, selection=selection)

    report_name = get_report_status_name_for_period(device, normalized_period)
    if report_name is None or not persist:
        return report_payload

    AssetStatus.objects.create(
        device=device,
        name=report_name,
        status=report_payload,
    )
    return report_payload
