import json
import logging
import os
import tempfile
import uuid
from calendar import monthrange
from datetime import datetime

import sentry_sdk
from api.utils import DEVICE_MONTHLY_REPORT_QUEUE_KEY, DEVICE_MONTHLY_REPORT_QUEUE_MAX_LENGTH
from django.utils import timezone
from django_redis import get_redis_connection

logger = logging.getLogger('django')

MONTHLY_REPORT_JOB_STATUS_DIR = os.path.join(
    tempfile.gettempdir(),
    'iot-management-monthly-report-jobs',
)
MONTHLY_REPORT_JOB_STATUS_TTL_SECONDS = 12 * 60 * 60


def is_last_day_of_month(when=None):
    when = when or timezone.now()
    if timezone.is_aware(when):
        when = timezone.localtime(when)
    return when.day == monthrange(when.year, when.month)[1]


def current_report_month(when=None):
    when = when or timezone.now()
    if timezone.is_aware(when):
        when = timezone.localtime(when)
    return when.strftime('%Y-%m')


def _serialize_job_value(value):
    if isinstance(value, dict):
        return {str(key): _serialize_job_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_job_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _get_monthly_report_job_status_path(job_id):
    os.makedirs(MONTHLY_REPORT_JOB_STATUS_DIR, exist_ok=True)
    return os.path.join(MONTHLY_REPORT_JOB_STATUS_DIR, f'{job_id}.json')


def load_monthly_report_job_status(job_id):
    status_path = _get_monthly_report_job_status_path(job_id)
    if not os.path.exists(status_path):
        return None

    if timezone.now().timestamp() - os.path.getmtime(status_path) > MONTHLY_REPORT_JOB_STATUS_TTL_SECONDS:
        try:
            os.remove(status_path)
        except OSError:
            logger.warning('Failed to remove expired monthly report job state: %s', status_path)
        return None

    with open(status_path, 'r', encoding='utf-8') as handle:
        return json.load(handle)


def write_monthly_report_job_status(job_id, data):
    status_path = _get_monthly_report_job_status_path(job_id)
    serialized_data = _serialize_job_value({
        **data,
        'updated_at': timezone.now().isoformat(),
    })
    temp_path = f'{status_path}.tmp'
    with open(temp_path, 'w', encoding='utf-8') as handle:
        json.dump(serialized_data, handle)
    os.replace(temp_path, status_path)
    return serialized_data


def update_monthly_report_job_status(job_id, patch):
    current_data = load_monthly_report_job_status(job_id) or {}
    current_data.update(patch)
    return write_monthly_report_job_status(job_id, current_data)


def report_monthly_report_failure(
    exc,
    *,
    device=None,
    device_id=None,
    report_month=None,
    job_id=None,
    source=None,
):
    device_identifier = device_id
    if device is not None:
        device_identifier = getattr(device, 'ip_address', None) or str(getattr(device, 'pk', device_id))
    logger.exception(
        'Monthly report job failed (%s) device=%s month=%s job_id=%s: %s',
        source or 'unknown',
        device_identifier,
        report_month,
        job_id,
        exc,
    )
    with sentry_sdk.push_scope() as scope:
        scope.set_tag('monthly_report_job', 'true')
        if source:
            scope.set_tag('monthly_report_source', source)
        if device_identifier:
            scope.set_extra('device_identifier', device_identifier)
        if report_month:
            scope.set_extra('report_month', report_month)
        if job_id:
            scope.set_extra('job_id', job_id)
        sentry_sdk.capture_exception(exc)


def enqueue_monthly_report_job(device, report_month, force_refresh=False):
    if device is None:
        report_monthly_report_failure(
            RuntimeError('Monthly report queue is unavailable (missing device).'),
            device=device,
            report_month=report_month,
            source='enqueue',
        )
        return None

    job_id = uuid.uuid4().hex
    queue_entry = {
        'job_id': job_id,
        'device_id': str(getattr(device, 'pk', None) or getattr(device, 'id', '')),
        'device_identifier': device.ip_address or device.alias or str(device.id),
        'report_month': report_month,
        'force_refresh': bool(force_refresh),
        'queued_at': timezone.now().isoformat(),
    }

    try:
        redis_connection = get_redis_connection('default')
        payload = json.dumps(queue_entry)
        pipeline = redis_connection.pipeline()
        pipeline.rpush(DEVICE_MONTHLY_REPORT_QUEUE_KEY, payload)
        pipeline.ltrim(
            DEVICE_MONTHLY_REPORT_QUEUE_KEY,
            -DEVICE_MONTHLY_REPORT_QUEUE_MAX_LENGTH,
            -1,
        )
        pipeline.execute()
    except Exception as exc:
        report_monthly_report_failure(
            exc,
            device=device,
            report_month=report_month,
            job_id=job_id,
            source='enqueue',
        )
        return None

    write_monthly_report_job_status(job_id, {
        'job_id': job_id,
        'status': 'queued',
        'message': 'Monthly report generation queued.',
        'month': report_month,
        'device_id': str(getattr(device, 'pk', None) or getattr(device, 'id', '')),
        'device_identifier': device.ip_address or device.alias or str(device.id),
        'progress_percent': 0,
        'queued_at': timezone.now().isoformat(),
    })
    return job_id
