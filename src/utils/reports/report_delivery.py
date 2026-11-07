import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from utils.solar.monthly_report_job import build_device_monthly_report_cache_path

logger = logging.getLogger('django')

REPORT_EMAIL_CHANNEL = 'email'
REPORT_DELIVERY_MARKER = 'report_delivery'

PERIOD_LABELS = {
    'yesterday': 'Daily',
    'week': 'Weekly',
    'month': 'Monthly',
}

EMAIL_SPLIT_PATTERN = re.compile(r'[,\s;]+')


def parse_recipient_list(raw_value):
    if not raw_value:
        return []
    if isinstance(raw_value, list):
        candidates = raw_value
    else:
        candidates = EMAIL_SPLIT_PATTERN.split(str(raw_value))
    emails = []
    for candidate in candidates:
        email = str(candidate or '').strip()
        if email and '@' in email and email not in emails:
            emails.append(email)
    return emails


def get_report_email_action(device_event):
    for action in device_event.actions_config or []:
        if action.get('channel') == REPORT_EMAIL_CHANNEL and action.get(REPORT_DELIVERY_MARKER):
            return action
    return None


def serialize_report_email_action(action):
    if action is None:
        return {
            'email_enabled': False,
            'email_recipients': [],
            'last_email_sent_at': None,
        }
    return {
        'email_enabled': bool(action.get('enabled', True)),
        'email_recipients': parse_recipient_list(action.get('emails')),
        'last_email_sent_at': action.get('last_sent_at'),
    }


def build_report_email_action(emails, enabled=True, last_sent_at=None):
    email_blob = ', '.join(parse_recipient_list(emails))
    payload = {
        'channel': REPORT_EMAIL_CHANNEL,
        REPORT_DELIVERY_MARKER: True,
        'enabled': bool(enabled),
        'emails': email_blob or None,
        'template_title': '{{device}} {{period}} energy report',
        'template_text': 'Your {{period}} HTML energy report for {{device}} is attached.',
    }
    if last_sent_at:
        payload['last_sent_at'] = last_sent_at
    return payload


def upsert_report_email_action(device_event, emails, enabled, last_sent_at=None):
    existing = get_report_email_action(device_event)
    if last_sent_at is None and existing:
        last_sent_at = existing.get('last_sent_at')
    other_actions = [
        action for action in (device_event.actions_config or [])
        if not (action.get('channel') == REPORT_EMAIL_CHANNEL and action.get(REPORT_DELIVERY_MARKER))
    ]
    email_action = build_report_email_action(emails, enabled=enabled, last_sent_at=last_sent_at)
    device_event.actions_config = [*other_actions, email_action]
    device_event.save(update_fields=['actions_config'])
    return email_action


def _report_day_html_path(device, day_date):
    from utils.reports.report_helpers import _report_day_html_url

    return Path(_report_day_html_url(device, day_date)['path'])


def resolve_report_html_path(device, report_period, selection=None):
    selection = selection or {}
    normalized = (report_period or '').strip().lower()
    if normalized == 'yesterday':
        day_value = (selection.get('day') or '').strip()
        if day_value:
            day_date = datetime.strptime(day_value, '%Y-%m-%d').date()
        else:
            day_date = timezone.localdate() - timedelta(days=1)
        path = _report_day_html_path(device, day_date)
        return path if path.is_file() else None

    if normalized == 'month':
        month = (selection.get('month') or '').strip() or timezone.localdate().strftime('%Y-%m')
        path = build_device_monthly_report_cache_path(device.ip_address or str(device.id), month)
        return path if path.is_file() else None

    return None


def _public_report_url(request, relative_url):
    if request is not None:
        return request.build_absolute_uri(relative_url)
    site = getattr(settings, 'REPORT_PUBLIC_BASE_URL', '') or ''
    if site:
        return f"{site.rstrip('/')}/{relative_url.lstrip('/')}"
    return relative_url


def send_report_html_email(device, report_period, html_path, *, report_url=None, extra_context=None, fallback_summary=None):
    device_event = extra_context.get('device_event') if extra_context else None
    if device_event is None:
        return {'sent': False, 'reason': 'missing_device_event'}

    email_action = get_report_email_action(device_event)
    if email_action is None or not email_action.get('enabled', True):
        return {'sent': False, 'reason': 'email_disabled'}

    recipients = parse_recipient_list(email_action.get('emails'))
    if not recipients:
        return {'sent': False, 'reason': 'no_recipients'}

    period_label = PERIOD_LABELS.get(report_period, report_period)
    device_label = device.ip_address or device.alias or str(device.id)
    subject = f"{period_label} energy report — {device_label}"

    plain_lines = [
        f"Your {period_label.lower()} HTML energy report for {device_label} is ready.",
    ]
    if fallback_summary and isinstance(fallback_summary, dict):
        plain_lines.append('')
        plain_lines.append('Summary snapshot:')
        for key, value in list(fallback_summary.items())[:12]:
            plain_lines.append(f'- {key}: {value}')
    plain_body = '\n'.join(plain_lines)
    if report_url:
        plain_lines.insert(1, f"View online: {report_url}")
        plain_body = '\n'.join(plain_lines)

    html_body = f"""
    <html><body style="font-family: sans-serif; color: #222;">
    <h2>{period_label} report — {device_label}</h2>
    <p>Your HTML energy report is attached when available.</p>
    {f'<p><a href="{report_url}">Open report in browser</a></p>' if report_url else ''}
    </body></html>
    """

    message = EmailMultiAlternatives(
        subject=subject,
        body=plain_body,
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@localhost'),
        to=recipients,
    )
    message.attach_alternative(html_body, 'text/html')

    if html_path is not None:
        path = Path(html_path)
        if path.is_file():
            message.attach(path.name, path.read_bytes(), 'text/html')

    try:
        message.send(fail_silently=False)
    except Exception as exc:
        logger.exception('Failed to send %s report email for device %s: %s', report_period, device_label, exc)
        return {'sent': False, 'reason': str(exc)}

    sent_at = timezone.now().isoformat()
    upsert_report_email_action(
        device_event,
        email_action.get('emails'),
        enabled=True,
        last_sent_at=sent_at,
    )

    return {'sent': True, 'recipients': recipients, 'sent_at': sent_at}


def deliver_scheduled_report_email(device_event, report_period, selection=None, request=None, fallback_summary=None):
    device = device_event.device
    if device is None:
        return {'sent': False, 'reason': 'missing_device'}

    html_path = resolve_report_html_path(device, report_period, selection=selection)
    report_url = None
    if html_path is not None:
        relative = str(html_path).split('media/')[-1] if 'media/' in str(html_path) else None
        if relative:
            report_url = _public_report_url(request, f"{settings.MEDIA_URL.rstrip('/')}/{relative}")

    return send_report_html_email(
        device,
        report_period,
        html_path,
        report_url=report_url,
        extra_context={'device_event': device_event},
        fallback_summary=fallback_summary,
    )
