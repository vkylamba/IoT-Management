from event.models import Action, DeviceEvent
from utils.reports.report_delivery import (
    get_report_email_action,
    parse_recipient_list,
    serialize_report_email_action,
    upsert_report_email_action,
)
from utils.reports.report_status import (
    API_PERIOD_TO_EVENT_PERIOD,
    EVENT_PERIOD_TO_API_PERIOD,
    coerce_active,
    get_configured_report_status_type,
    get_report_event_marker,
    has_report_status_type_configured,
    is_report_data_generation_enabled,
)

REPORT_PERIOD_META = {
    'yesterday': {
        'action_task': 'event.tasks.daily_energy_report',
        'event_type_name': 'Daily Report',
    },
    'week': {
        'action_task': 'event.tasks.weekly_energy_report',
        'event_type_name': 'Weekly Report',
    },
    'month': {
        'action_task': 'event.tasks.monthly_energy_report',
        'event_type_name': 'Monthly Report',
    },
}

SCHEDULE_HINTS = {
    'yesterday': 'Runs every day at 00:05 (server time).',
    'week': 'Runs every Monday at 00:10 (server time).',
    'month': 'Runs on the last day of each month at 23:45 (server time).',
}


def _format_crontab(schedule):
    if schedule is None:
        return None
    return {
        'minute': schedule.minute,
        'hour': schedule.hour,
        'day_of_week': schedule.day_of_week,
        'day_of_month': schedule.day_of_month,
        'month_of_year': schedule.month_of_year,
        'hint': None,
    }


def _get_report_event(device, report_period):
    marker = get_report_event_marker(report_period)
    return DeviceEvent.objects.filter(device=device, equation_threshold=marker).order_by('-created_at').first()


def _get_report_action(device_event, report_period):
    if device_event is None:
        return None
    task_name = REPORT_PERIOD_META.get(report_period, {}).get('action_task')
    if not task_name:
        return None
    return Action.objects.filter(device_event=device_event, task=task_name).first()


def build_period_settings(device, report_period):
    status_type = get_configured_report_status_type(device, report_period)
    device_event = _get_report_event(device, report_period)
    action = _get_report_action(device_event, report_period)
    email_meta = serialize_report_email_action(get_report_email_action(device_event) if device_event else None)

    schedule = device_event.schedule if device_event else None
    crontab = _format_crontab(schedule)

    generation_configured = has_report_status_type_configured(device, report_period)
    generation_enabled = is_report_data_generation_enabled(device, report_period)

    return {
        'report_period': report_period,
        'api_period': EVENT_PERIOD_TO_API_PERIOD.get(report_period, report_period),
        'label': REPORT_PERIOD_META.get(report_period, {}).get('event_type_name', report_period),
        'generation_configured': generation_configured,
        'generation_enabled': generation_enabled,
        'status_type_id': str(status_type.id) if status_type else None,
        'status_type_name': status_type.name if status_type else None,
        'schedule_enabled': bool(
            device_event is not None
            and device_event.active
            and action is not None
            and action.active
        ),
        'event_id': str(device_event.id) if device_event else None,
        'schedule': crontab,
        'schedule_hint': SCHEDULE_HINTS.get(report_period),
        'email_enabled': email_meta['email_enabled'],
        'email_recipients': email_meta['email_recipients'],
        'last_email_sent_at': email_meta['last_email_sent_at'],
    }


def get_device_report_settings(device):
    periods = {}
    for api_period, report_period in API_PERIOD_TO_EVENT_PERIOD.items():
        periods[api_period] = build_period_settings(device, report_period)
    return {
        'device_id': device.ip_address or str(device.id),
        'periods': periods,
    }


def update_device_report_settings(device, user, payload, sync_report_events=None):
    periods_payload = (payload or {}).get('periods') or {}
    updated = []

    for api_period, period_patch in periods_payload.items():
        report_period = API_PERIOD_TO_EVENT_PERIOD.get(api_period)
        if report_period is None or not isinstance(period_patch, dict):
            continue

        status_type = get_configured_report_status_type(device, report_period)
        if 'generation_enabled' in period_patch:
            requested_enabled = bool(period_patch['generation_enabled'])
            if status_type is None:
                if requested_enabled:
                    raise ValueError(
                        f'No report status type configured for {api_period}. Add one under Device Details first.'
                    )
            else:
                status_type.active = requested_enabled
                status_type.save(update_fields=['active'])

        device_event = _get_report_event(device, report_period)
        if device_event is None and (
            period_patch.get('schedule_enabled') is not None or period_patch.get('email_enabled') is not None
        ):
            if sync_report_events is not None:
                sync_report_events(device, user)
            device_event = _get_report_event(device, report_period)

        if device_event is not None and 'schedule_enabled' in period_patch:
            enabled = bool(period_patch['schedule_enabled'])
            device_event.active = enabled
            device_event.save(update_fields=['active'])
            action = _get_report_action(device_event, report_period)
            if action is not None:
                action.active = enabled
                action.save(update_fields=['active'])

        if device_event is not None and (
            'email_enabled' in period_patch or 'email_recipients' in period_patch
        ):
            current = get_report_email_action(device_event)
            enabled = bool(period_patch.get('email_enabled', current.get('enabled', True) if current else False))
            recipients = period_patch.get('email_recipients')
            if recipients is None and current is not None:
                recipients = parse_recipient_list(current.get('emails'))
            elif recipients is None:
                recipients = []
            if enabled and not recipients:
                raise ValueError(f'Add at least one email recipient to enable {api_period} report delivery.')
            if enabled:
                upsert_report_email_action(device_event, recipients, enabled=True)
            else:
                if current is None:
                    device_event.actions_config = [
                        action for action in (device_event.actions_config or [])
                        if not (action.get('report_delivery') and action.get('channel') == 'email')
                    ]
                    device_event.save(update_fields=['actions_config'])
                else:
                    upsert_report_email_action(device_event, recipients, enabled=False)

        updated.append(api_period)

    if sync_report_events is not None:
        sync_report_events(device, user)
    return {
        'updated_periods': updated,
        'settings': get_device_report_settings(device),
    }
