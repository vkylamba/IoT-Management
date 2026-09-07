from device.models import AssetStatus, StatusType


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