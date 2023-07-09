import logging

# from celery.decorators import task
from device.models import DeviceStatus, User
from django.db.models import Q
from notification.models import Notification
from utils.reports import (get_daily_report, get_monthly_report,
                           get_weekly_report)

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

        create_user_notifications_for_reports(
            device_event.device,
            "NO_DATA_FROM_DEVICE",
            {
                "device": str(device_event.device),
                "ip_address": device_event.device.ip_address,
                "last_data_point": data
            }
        )


# @task
def periodic_system_check(action_id):
    action = Action.objects.get(id=action_id)
    device_event = action.device_event
    data = device_event.device.get_last_data_point()
    if device_event.eval_equation(data):
        latest_status = DeviceStatus.objects.filter(
            device=device_event.device,
            name=DeviceStatus.DAILY_STATUS
        ).order_by("-created_at").first()

        if latest_status is not None:
            status_data = latest_status.status
            if status_data is not None:
                system_state = status_data.get("system_state", "")
                if system_state is not None and system_state != "NA":
                    create_user_notifications_for_reports(
                        device_event.device, "SYSTEM_STATUS", status_data
                    )


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
        create_user_notifications_for_reports(
            device_event.device, DeviceStatus.LAST_MONTH_REPORT, report_data
        )

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
        create_user_notifications_for_reports(
            device_event.device, DeviceStatus.LAST_WEEK_REPORT, report_data
        )

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
        create_user_notifications_for_reports(
            device_event.device, DeviceStatus.LAST_DAY_REPORT, report_data
        )


def create_user_notifications_for_reports(device, report_type, report_data):
    users = User.objects.filter(
        ~Q(subnet_mask='')
    )
    # notifications = []
    for user in users:
        devices = user.device_list()
        if device.ip_address in devices:
            notification = Notification(
                name=f"{report_type} - {user.username}",
                method=Notification.TELEGRAM_BOT,
                user=user,
                title=report_type,
                data=report_data
            )
            notification.save()
            # notifications.append(notification)
    # Notification.objects.bulk_create(notifications)
