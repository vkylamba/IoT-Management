import logging

# from celery.decorators import task
from api.monthly_report_jobs import (
    current_report_month,
    enqueue_monthly_report_job,
    is_last_day_of_month,
)
from device.models import AssetStatus, User
from django.db.models import Q
from event.models import Action, EventHistory
from utils.reports.daily_reports import get_daily_report
from utils.reports.report_helpers import calculate_report_status_for_period, get_report_status_type_for_period
from utils.reports.weekly_reports import get_weekly_report

logger = logging.getLogger('django')


# @task
def no_data_check(action_id):
    action = Action.objects.get(id=action_id)
    device_event = action.device_event
    data = device_event.device.get_last_data_point()
    if device_event.eval_equation(data):
        result = {
            "user_notification": f"No data from device {device_event.device.ip_address}"
        }
        event_history = EventHistory(
            device_event=device_event,
            action=action,
            result=result
        )
        event_history.save()


# @task
def periodic_system_check(action_id):
    action = Action.objects.get(id=action_id)
    device_event = action.device_event
    data = device_event.device.get_last_data_point()
    if device_event.eval_equation(data):
        latest_status = AssetStatus.objects.filter(
            device=device_event.device,
            name=AssetStatus.DAILY_STATUS
        ).order_by("-created_at").first()

        if latest_status is not None:
            status_data = latest_status.status
            if status_data is not None:
                system_state = status_data.get("system_state", "")
                if system_state is not None and system_state != "NA":
                    pass


# @task
def monthly_energy_report(action_id):
    if not is_last_day_of_month():
        return

    action = Action.objects.get(id=action_id)
    device_event = action.device_event
    data = device_event.device.get_last_data_point()
    if device_event.eval_equation(data):
        device = device_event.device
        if get_report_status_type_for_period(device, 'month') is None:
            calculate_report_status_for_period(device, 'month')
        report_month = current_report_month()
        job_id = enqueue_monthly_report_job(device, report_month, force_refresh=False)
        result = {
            'month': report_month,
            'monthly_report_job_id': job_id,
            'queued': job_id is not None,
        }
        if job_id is None:
            result['error'] = 'Failed to enqueue monthly HTML report job.'
        event_history = EventHistory(
            device_event=device_event,
            action=action,
            result=result
        )
        event_history.save()


# @task
def weekly_energy_report(action_id):
    action = Action.objects.get(id=action_id)
    device_event = action.device_event
    data = device_event.device.get_last_data_point()
    if device_event.eval_equation(data):
        if get_report_status_type_for_period(device_event.device, 'week') is None:
            calculate_report_status_for_period(device_event.device, 'week')
        report_data = get_weekly_report(device_event.device)
        result = {
            "weekly_report": report_data
        }
        event_history = EventHistory(
            device_event=device_event,
            action=action,
            result=result
        )
        event_history.save()
        from utils.reports.report_delivery import deliver_scheduled_report_email
        email_result = deliver_scheduled_report_email(
            device_event,
            'week',
            fallback_summary=report_data if isinstance(report_data, dict) else None,
        )
        if email_result.get('sent'):
            result['email_delivery'] = email_result
            event_history.result = result
            event_history.save(update_fields=['result'])



# @task
def daily_energy_report(action_id):
    action = Action.objects.get(id=action_id)
    device_event = action.device_event
    data = device_event.device.get_last_data_point()
    if device_event.eval_equation(data):
        if get_report_status_type_for_period(device_event.device, 'yesterday') is None:
            calculate_report_status_for_period(device_event.device, 'yesterday', force_refresh=True)
        report_data = get_daily_report(device_event.device)
        result = {
            "daily_report": report_data
        }
        event_history = EventHistory(
            device_event=device_event,
            action=action,
            result=result
        )
        event_history.save()
        from utils.reports.report_delivery import deliver_scheduled_report_email
        email_result = deliver_scheduled_report_email(
            device_event,
            'yesterday',
            fallback_summary=report_data if isinstance(report_data, dict) else None,
        )
        if email_result.get('sent'):
            result['email_delivery'] = email_result
            event_history.result = result
            event_history.save(update_fields=['result'])
