
from device.models import DeviceStatus
from notification.models import Notification


def parse_notification_html(notification: Notification) -> str:

    html = 'Couldn\'t parse'
    if notification.title == DeviceStatus.LAST_DAY_REPORT:
        html = parse_last_day_report(notification)
    elif notification.title == DeviceStatus.LAST_WEEK_REPORT:
        html = parse_last_week_report(notification)
    elif notification.title == DeviceStatus.LAST_MONTH_REPORT:
        html = parse_last_month_report(notification)
    elif notification.title == "SYSTEM_STATUS":
        html = parse_system_notification(notification)
    elif notification.title == "NO_DATA_FROM_DEVICE":
        html = parse_no_data_notification(notification)
    else:
        html = notification.title

    return html


def parse_last_day_report(notification: Notification) -> str:
    status_data = notification.data
    currency =  status_data.get("currency", "$")
    html = f"""Yesterday's report for device: {status_data.get("device")}:
        Device IP: {status_data.get("device_ip_address")}
        From {status_data.get("from_time")} to {status_data.get("to_time")}
        Report generation time: {status_data.get("report_generation_time")}
        Data availability: {round(status_data.get("active_data_days", 0) * 100.0, 1)}%
        Money Saved: {round(status_data.get("savings", 0), 2)} {currency}
        Net bill: {round(status_data.get("net_bill", 0), 2)} {currency}
        Consumption bill: {round(status_data.get("consumption_bill", 0), 2)} {currency}
        Consumption rate: {round(status_data.get("consumption_rate", 0), 2)} {currency}
        Generated: {round(status_data.get("energy_generated", 0), 2)} kwh
        Consumed: {round(status_data.get("energy_consumed", 0), 2)} kwh
        Exported: {round(status_data.get("energy_exported", 0), 2)} kwh
        Imported: {round(status_data.get("energy_imported", 0), 2)} kwh
    """
    return html.replace('\t', '')


def parse_last_week_report(notification: Notification) -> str:
    status_data = notification.data
    currency =  status_data.get("currency", "$")
    html = f"""Last week's report for device: {status_data.get("device")}:
        Device IP: {status_data.get("device_ip_address")}
        From {status_data.get("from_time")} to {status_data.get("to_time")}
        Report generation time: {status_data.get("report_generation_time")}
        Data availability: {round(status_data.get("active_data_days", 0) / 7 * 100.0, 1)}%
        Money Saved: {round(status_data.get("savings", 0), 2)} {currency}
        Net bill: {round(status_data.get("net_bill", 0), 2)} {currency}
        Consumption bill: {round(status_data.get("consumption_bill", 0), 2)} {currency}
        Consumption rate: {round(status_data.get("consumption_rate", 0), 2)} {currency}
        Generated: {round(status_data.get("energy_generated", 0), 2)} kwh
        Consumed: {round(status_data.get("energy_consumed", 0), 2)} kwh
        Exported: {round(status_data.get("energy_exported", 0), 2)} kwh
        Imported: {round(status_data.get("energy_imported", 0), 2)} kwh
    """
    return html.replace('\t', '')


def parse_last_month_report(notification: Notification) -> str:
    status_data = notification.data
    currency =  status_data.get("currency", "$")
    html = f"""Last months's report for device: {status_data.get("device")}:
        Device IP: {status_data.get("device_ip_address")}
        From {status_data.get("from_time")} to {status_data.get("to_time")}
        Report generation time: {status_data.get("report_generation_time")}
        Data availability: {round(status_data.get("active_data_days", 0) / 30 * 100.0, 1)}%
        Money Saved: {round(status_data.get("savings", 0), 2)} {currency}
        Net bill: {round(status_data.get("net_bill", 0), 2)} {currency}
        Consumption bill: {round(status_data.get("consumption_bill", 0), 2)} {currency}
        Consumption rate: {round(status_data.get("consumption_rate", 0), 2)} {currency}
        Generated: {round(status_data.get("energy_generated", 0), 2)} kwh
        Consumed: {round(status_data.get("energy_consumed", 0), 2)} kwh
        Exported: {round(status_data.get("energy_exported", 0), 2)} kwh
        Imported: {round(status_data.get("energy_imported", 0), 2)} kwh
    """
    return html.replace('\t', '')


def render_status_to_html(status: dict) -> str:
    html = ''
    if status:
        status_type = status.name
        device = status.device.ip_address
        status_data = status.status

        if status_type == DeviceStatus.DAILY_STATUS:

            html = f"""
                Solar: {status_data.get("solar_status")}
                Load: {status_data.get("load_status")}
                Battery: {status_data.get("battery_charging_status")}
                Net: {status_data.get("net_meter_status")}
                System: {status_data.get("system_state")}
                Generated today: {round(status_data.get("energy_generated_this_day", 0), 2)} kwh
                Consumption today: {round(status_data.get("energy_consumed_this_day", 0), 2)} kwh
                Exported today: {round(status_data.get("energy_exported_this_day", 0), 2)} kwh
                Imported today: {round(status_data.get("energy_imported_this_day", 0), 2)} kwh
            """

    return html.replace('\t', '')


def parse_system_notification(notification: Notification) -> str:
    notification_data = notification.data
    system_state = notification_data.get("system_state", "")
    html = f"""{system_state}:
        Net meter status: {notification_data.get("net_meter_status", "")}
        Solar status: {notification_data.get("solar_status", "")}
        Battery status: {notification_data.get("battery_charging_status", "")}
        Load status: {notification_data.get("load_status", "")}
    """
    return html.replace('\t', '')


def parse_no_data_notification(notification: Notification) -> str:
    notification_data = notification.data
    device = notification_data.get("ip_address", "")
    html = f"""No data from device {device}
    """
    return html.replace('\t', '')