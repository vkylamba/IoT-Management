import logging

# from celery.decorators import task
from device.models import AssetStatus, User
from django.db.models import Q
from event.models import Action, EventHistory

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
    action = Action.objects.get(id=action_id)
    device_event = action.device_event
    data = device_event.device.get_last_data_point()
    if device_event.eval_equation(data):
        report_data = get_monthly_report(device_event.device)
        result = {
            "monthly_report": report_data
        }
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

# @task
def daily_energy_report(action_id):
    action = Action.objects.get(id=action_id)
    device_event = action.device_event
    data = device_event.device.get_last_data_point()
    if device_event.eval_equation(data):
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
