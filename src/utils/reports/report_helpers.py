from datetime import datetime, timedelta

import pytz
from django.conf import settings
from django.utils import timezone

from device.models import AssetStatus, DeviceProperty, StatusType


REPORT_PERIOD_TO_LEGACY_NAME = {
    'yesterday': AssetStatus.LAST_DAY_REPORT,
    'week': AssetStatus.LAST_WEEK_REPORT,
    'month': AssetStatus.LAST_MONTH_REPORT,
}


def _normalize_report_period(report_period):
    if report_period is None:
        return None
    normalized_period = str(report_period).strip().lower()
    if normalized_period in REPORT_PERIOD_TO_LEGACY_NAME:
        return normalized_period
    return None


def get_report_status_type_for_period(device, report_period):
    normalized_period = _normalize_report_period(report_period)
    if normalized_period is None:
        return None

    query = {
        'target_type': StatusType.STATUS_TARGET_REPORT,
        'report_period': normalized_period,
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


def _build_day_windows(device_timezone, start_local_date, day_count):
    windows = []
    for day_offset in range(day_count):
        current_date = start_local_date + timedelta(days=day_offset)
        day_start_local = device_timezone.localize(datetime.combine(current_date, datetime.min.time()))
        day_end_local = day_start_local + timedelta(days=1)
        day_start_utc, day_end_utc = _to_local_window_utc(day_start_local, day_end_local)
        windows.append((current_date, day_start_utc, day_end_utc))
    return windows


def _extract_energy_point(status_payload):
    status_payload = status_payload or {}
    imported = float(status_payload.get('energy_imported_this_day', 0) or 0)
    exported = float(status_payload.get('energy_exported_this_day', 0) or 0)
    generated = float(status_payload.get('energy_generated_this_day', 0) or 0)
    consumed = float(status_payload.get('energy_consumed_this_day', 0) or 0)
    return {
        'imported': imported,
        'exported': exported,
        'generated': generated,
        'consumed': consumed,
    }


def _get_latest_status_for_window(device, status_names, start_utc, end_utc):
    for status_name in status_names:
        status_entry = AssetStatus.objects.filter(
            device=device,
            name=status_name,
            created_at__gte=start_utc,
            created_at__lt=end_utc,
        ).order_by('-created_at').first()
        if status_entry is not None and status_entry.status is not None:
            return status_entry.status
    return None


def _build_meter_row(imported, exported, generated=0.0, consumed=0.0):
    return {
        'solar_meter': float(generated),
        'load_meter': float(consumed),
        'import_energy_meter': float(imported),
        'export_energy_meter': float(exported),
    }


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


def _get_latest_running_status_payload(device, status_names):
    latest_status = None
    for status_name in status_names:
        status_entry = AssetStatus.objects.filter(
            device=device,
            name=status_name,
        ).order_by('-created_at').first()
        if status_entry is None or status_entry.status is None:
            continue
        if latest_status is None or status_entry.created_at > latest_status.created_at:
            latest_status = status_entry
    return latest_status.status if latest_status is not None else {}


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

    try:
        rate = float(rate)
    except (TypeError, ValueError):
        rate = 0.0
    return currency, rate


def _append_financial_fields(report_payload, summary, latest_running_status):
    currency, rate = _get_currency_and_rate(report_payload['device_obj'], latest_running_status)
    imported = summary['imported']
    exported = summary['exported']

    consumption_bill = imported * rate
    net_bill = (imported - exported) * rate

    report_payload.update({
        'currency': currency,
        'consumption_rate': rate,
        'consumption_bill': consumption_bill,
        'net_bill': net_bill,
        'savings': consumption_bill - net_bill,
        'energy_generated': summary['generated'],
        'energy_consumed': summary['consumed'],
        'energy_imported': imported,
        'energy_exported': exported,
    })


def _base_report_payload(device, from_utc, to_utc):
    payload = {
        'device_obj': device,
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


def _finalize_report_payload(report_payload):
    report_payload.pop('device_obj', None)
    return report_payload


def _calculate_yesterday_report(device):
    device_timezone = _get_device_timezone(device)
    local_now = timezone.now().astimezone(device_timezone)
    today_start_local = device_timezone.localize(datetime.combine(local_now.date(), datetime.min.time()))
    yesterday_start_local = today_start_local - timedelta(days=1)
    from_local = yesterday_start_local
    to_local = today_start_local
    from_utc, to_utc = _to_local_window_utc(from_local, to_local)

    status_names = _get_running_status_names_for_device(device)
    latest_running_status = _get_latest_running_status_payload(device, status_names)
    seven_day_windows = _build_day_windows(device_timezone, (yesterday_start_local - timedelta(days=6)).date(), 7)
    by_time = {}
    active_days = 0
    for day_date, day_start_utc, day_end_utc in seven_day_windows:
        status_payload = _get_latest_status_for_window(device, status_names, day_start_utc, day_end_utc)
        energy_point = _extract_energy_point(status_payload)
        if status_payload is not None:
            active_days += 1
        by_time[day_date.strftime('%Y-%m-%d')] = _build_meter_row(
            imported=energy_point['imported'],
            exported=energy_point['exported'],
            generated=energy_point['generated'],
            consumed=energy_point['consumed'],
        )

    summary = _build_summary_from_rows(by_time)
    report_payload = _base_report_payload(device, from_utc, to_utc)
    report_payload['active_data_days'] = active_days
    report_payload['per_day_energy_statistics'] = {
        'by_time': by_time,
        'summary': summary,
    }
    _append_financial_fields(report_payload, summary, latest_running_status)
    return _finalize_report_payload(report_payload)


def _calculate_week_report(device):
    device_timezone = _get_device_timezone(device)
    local_now = timezone.now().astimezone(device_timezone)
    current_week_start_local = device_timezone.localize(
        datetime.combine(local_now.date() - timedelta(days=local_now.weekday()), datetime.min.time())
    )
    last_week_start_local = current_week_start_local - timedelta(days=7)
    from_utc, to_utc = _to_local_window_utc(last_week_start_local, current_week_start_local)

    status_names = _get_running_status_names_for_device(device)
    latest_running_status = _get_latest_running_status_payload(device, status_names)
    by_time = {}
    active_windows = 0
    for weeks_back in range(4, 0, -1):
        week_start_local = current_week_start_local - timedelta(days=7 * weeks_back)
        week_end_local = week_start_local + timedelta(days=7)
        daily_windows = _build_day_windows(device_timezone, week_start_local.date(), 7)
        imported = 0.0
        exported = 0.0
        generated = 0.0
        consumed = 0.0
        has_data = False
        for _, day_start_utc, day_end_utc in daily_windows:
            status_payload = _get_latest_status_for_window(device, status_names, day_start_utc, day_end_utc)
            energy_point = _extract_energy_point(status_payload)
            imported += energy_point['imported']
            exported += energy_point['exported']
            generated += energy_point['generated']
            consumed += energy_point['consumed']
            if status_payload is not None:
                has_data = True
        if has_data:
            active_windows += 1
        label = f"week_{week_start_local.strftime('%Y-%m-%d')}"
        by_time[label] = _build_meter_row(imported, exported, generated, consumed)

    summary = _build_summary_from_rows(by_time)
    report_payload = _base_report_payload(device, from_utc, to_utc)
    report_payload['active_data_days'] = active_windows * 7
    report_payload['per_day_energy_statistics'] = {
        'by_time': by_time,
        'summary': summary,
    }
    _append_financial_fields(report_payload, summary, latest_running_status)
    return _finalize_report_payload(report_payload)


def _month_start(dt):
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _previous_month_start(month_start_local):
    return (month_start_local - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _calculate_month_report(device):
    device_timezone = _get_device_timezone(device)
    local_now = timezone.now().astimezone(device_timezone)
    current_month_start_local = _month_start(local_now)
    last_month_start_local = _previous_month_start(current_month_start_local)
    from_utc, to_utc = _to_local_window_utc(last_month_start_local, current_month_start_local)

    status_names = _get_running_status_names_for_device(device)
    latest_running_status = _get_latest_running_status_payload(device, status_names)
    by_time = {}
    active_windows = 0
    pointer = current_month_start_local
    monthly_windows = []
    for _ in range(3):
        month_end = pointer
        month_start = _previous_month_start(month_end)
        monthly_windows.append((month_start, month_end))
        pointer = month_start
    monthly_windows.reverse()

    for month_start_local, month_end_local in monthly_windows:
        day_count = (month_end_local.date() - month_start_local.date()).days
        daily_windows = _build_day_windows(device_timezone, month_start_local.date(), day_count)
        imported = 0.0
        exported = 0.0
        generated = 0.0
        consumed = 0.0
        has_data = False
        for _, day_start_utc, day_end_utc in daily_windows:
            status_payload = _get_latest_status_for_window(device, status_names, day_start_utc, day_end_utc)
            energy_point = _extract_energy_point(status_payload)
            imported += energy_point['imported']
            exported += energy_point['exported']
            generated += energy_point['generated']
            consumed += energy_point['consumed']
            if status_payload is not None:
                has_data = True
        if has_data:
            active_windows += 1
        label = month_start_local.strftime('%Y-%m')
        by_time[label] = _build_meter_row(imported, exported, generated, consumed)

    summary = _build_summary_from_rows(by_time)
    report_payload = _base_report_payload(device, from_utc, to_utc)
    report_payload['active_data_days'] = active_windows * 30
    report_payload['per_day_energy_statistics'] = {
        'by_time': by_time,
        'summary': summary,
    }
    _append_financial_fields(report_payload, summary, latest_running_status)
    return _finalize_report_payload(report_payload)


def calculate_report_status_for_period(device, report_period):
    normalized_period = _normalize_report_period(report_period)
    if normalized_period is None:
        return None

    if normalized_period == 'yesterday':
        report_payload = _calculate_yesterday_report(device)
    elif normalized_period == 'week':
        report_payload = _calculate_week_report(device)
    else:
        report_payload = _calculate_month_report(device)

    report_name = get_report_status_name_for_period(device, normalized_period)
    if report_name is None:
        return report_payload

    AssetStatus.objects.create(
        device=device,
        name=report_name,
        status=report_payload,
    )
    return report_payload