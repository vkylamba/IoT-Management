"""Report period normalization and StatusType resolution (automation, tasks, calculations)."""

from device.models import StatusType

REPORT_EVENT_MARKER_PREFIX = 'AUTO_REPORT_STATUS'

API_PERIOD_TO_EVENT_PERIOD = {
    'day': 'yesterday',
    'week': 'week',
    'month': 'month',
}

EVENT_PERIOD_TO_API_PERIOD = {value: key for key, value in API_PERIOD_TO_EVENT_PERIOD.items()}

_EVENT_PERIODS = frozenset({'yesterday', 'week', 'month'})
_COMPUTE_PERIODS = frozenset({'day', 'week', 'month'})


def normalize_compute_period(report_period):
    """Canonical period for report calculations and AssetStatus legacy keys (day/week/month)."""
    if report_period is None:
        return None
    value = str(report_period).strip().lower()
    if value == 'yesterday':
        return 'day'
    if value in _COMPUTE_PERIODS:
        return value
    if value in _EVENT_PERIODS:
        return 'day' if value == 'yesterday' else value
    return None


def normalize_event_period(report_period):
    """Canonical period for DeviceEvent markers and automation (yesterday/week/month)."""
    if report_period is None:
        return None
    value = str(report_period).strip().lower()
    if value in API_PERIOD_TO_EVENT_PERIOD:
        return API_PERIOD_TO_EVENT_PERIOD[value]
    if value in _EVENT_PERIODS:
        return value
    compute = normalize_compute_period(report_period)
    if compute == 'day':
        return 'yesterday'
    if compute in ('week', 'month'):
        return compute
    return None


def canonical_event_period(report_period):
    return normalize_event_period(report_period)


def status_type_lookup_periods(report_period):
    """`report_period` values to match on StatusType rows (DB may use day or yesterday)."""
    compute = normalize_compute_period(report_period)
    if compute == 'day':
        return ['day', 'yesterday']
    if compute in ('week', 'month'):
        return [compute]
    event = normalize_event_period(report_period)
    if event == 'yesterday':
        return ['day', 'yesterday']
    if event in ('week', 'month'):
        return [event]
    raw = str(report_period or '').strip().lower()
    return [raw] if raw else []


def coerce_active(value):
    if value is True or value == 1:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)


def collect_report_status_types(device, period_candidates):
    matches = []
    seen_ids = set()

    def add_from_query(queryset):
        for status_type in queryset.order_by('-created_at'):
            status_id = str(status_type.id)
            if status_id in seen_ids:
                continue
            seen_ids.add(status_id)
            matches.append(status_type)

    for period_candidate in period_candidates:
        add_from_query(
            StatusType.objects.filter(
                device=device,
                target_type=StatusType.STATUS_TARGET_REPORT,
                report_period=period_candidate,
            )
        )

    device_type = getattr(device, 'type', None)
    if device_type is not None:
        for period_candidate in period_candidates:
            add_from_query(
                StatusType.objects.filter(
                    device_type=device_type,
                    target_type=StatusType.STATUS_TARGET_REPORT,
                    report_period=period_candidate,
                )
            )

    return matches


def get_configured_report_status_type(device, report_period):
    """
    Report StatusType for this period (device or device type), preferring an active row.
    Falls back to the newest inactive row so automation can toggle `active`.
    """
    period_candidates = status_type_lookup_periods(report_period)
    if not period_candidates:
        return None

    matches = collect_report_status_types(device, period_candidates)
    if not matches:
        return None

    for status_type in matches:
        if coerce_active(getattr(status_type, 'active', False)):
            return status_type
    return matches[0]


def get_active_report_status_type(device, report_period):
    status_type = get_configured_report_status_type(device, report_period)
    if status_type is None or not coerce_active(getattr(status_type, 'active', False)):
        return None
    return status_type


def has_report_status_type_configured(device, report_period):
    return get_configured_report_status_type(device, report_period) is not None


def is_report_data_generation_enabled(device, report_period):
    return get_active_report_status_type(device, report_period) is not None


def get_report_event_marker(report_period):
    event_period = normalize_event_period(report_period)
    if not event_period:
        event_period = str(report_period or '').strip().lower()
    return f'{REPORT_EVENT_MARKER_PREFIX}:{event_period}'
