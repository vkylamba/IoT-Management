from api.permissions import IsDeviceUser
from dashboard.models import DASHBOARD_SOURCES
from device.models import DeviceProperty
from django.conf import settings
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from dashboard.superset import SupersetDashboard

PERMISSIONS_ADMIN = settings.PERMISSIONS_ADMIN


DEFAULT_WIDGETS = [
    "total_devices",
    "active_devices",
    "total_energy_generated_today",
    "total_energy_consumed_today",
    "total_energy_exported_today",
    "total_profit_today"
]


class WidgetViewSet(viewsets.ViewSet):
    """
        API endpoint to provide user details.
    """
    permission_classes = (IsAuthenticated, IsDeviceUser)

    def get_widgets(self, request):

        user = request.user
        user_data = {
            "results": []
        }
        # user_widgets = user.userwidget_set.filter(
        #     active=True
        # )
        user_widgets = user.userwidget_set.filter()

        total_devices = 0
        active_devices = 0
        total_energy_generated_this_day = 0
        total_energy_generation_limit_this_day = 0
        total_energy_consumed_this_day = 0
        total_energy_consumption_limit_this_day = 0
        total_energy_imported_this_day = 0
        total_energy_import_limit_this_day = 0
        total_energy_exported_this_day = 0
        total_energy_export_limit_this_day = 0

        user_devices = user.device_list(return_objects=True)
        user_device_ids = [
            str(d.id) for d in user_devices
        ]
        all_dev_props = DeviceProperty.objects.filter(
            device__id__in=user_device_ids
        ).select_related("device")
        all_dev_prop_values = {}
        for dev_prop in all_dev_props:
            existing_values = all_dev_prop_values.get(str(dev_prop.device.id), {})
            existing_values[dev_prop.name] = dev_prop.value
            all_dev_prop_values[str(dev_prop.device.id)] = existing_values

        for device in user_devices:
            latest_data = device.get_latest_data()
            properties = all_dev_prop_values.get(str(device.id), {})
            total_devices += 1
            if latest_data is not None and latest_data.data_arrival_time.date() == timezone.now().date():
                active_devices += 1

            total_energy_generated_this_day += float(properties.get("energy_generated_this_day", 0.0))
            total_energy_generation_limit_this_day += float(properties.get("energy_generation_limit_this_day", 0.0))

            total_energy_consumed_this_day += float(properties.get("energy_consumed_this_day", 0.0))
            total_energy_consumption_limit_this_day += float(properties.get("energy_consumption_limit_this_day", 0.0))

            total_energy_imported_this_day += float(properties.get("energy_imported_this_day", 0.0))
            total_energy_import_limit_this_day += float(properties.get("energy_import_limit_this_day", 0.0))

            total_energy_exported_this_day += float(properties.get("energy_exported_this_day", 0.0))
            total_energy_export_limit_this_day += float(properties.get("energy_export_limit_this_day", 0.0))

        summary_daya = {
            "total_devices": total_devices,
            "active_devices": active_devices,
            "total_energy_generated_this_day": total_energy_generated_this_day,
            "total_energy_generation_limit_this_day": total_energy_generation_limit_this_day,
            "total_energy_consumed_this_day": total_energy_consumed_this_day,
            "total_energy_consumption_limit_this_day": total_energy_consumption_limit_this_day,
            "total_energy_imported_this_day": total_energy_imported_this_day,
            "total_energy_import_limit_this_day": total_energy_import_limit_this_day,
            "total_energy_exported_this_day": total_energy_exported_this_day,
            "total_energy_export_limit_this_day": total_energy_export_limit_this_day,
        }


        for widget in user_widgets:
            if not widget.active:
                continue
            dash = None
            if widget.widget.metadata != None and  widget.widget.metadata.get("source") == DASHBOARD_SOURCES.superset:
                dash = SupersetDashboard(widget.widget.metadata.get("name"))     

            widget_data = {
                "widget": {
                    "name": widget.widget.name,
                    "type": widget.widget.type,
                    "description": widget.widget.description,
                    "metadata": widget.widget.metadata
                },
                "display_order": widget.display_order,
                "metadata": widget.metadata,
                "updated_at": widget.updated_at.strftime(settings.TIME_FORMAT_STRING)
            }

            if dash is not None:
                widget_data["dashboard_data"] = dash.get_details()

            user_data["results"].append(widget_data)

        user_data["results"].append({
            "widget": {
                "name": "summary",
                "type": "summary",
                "description": "summary",
                "metadata": summary_daya
            },
            "display_order": 0,
            "metadata": {},
            "updated_at": timezone.now().strftime(settings.TIME_FORMAT_STRING)
        })

        return Response(user_data)
