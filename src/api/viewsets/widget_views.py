from api.permissions import IsDeviceUser
from dashboard.models import DASHBOARD_SOURCES, Widget
from device.models import DeviceProperty, RawData
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
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        user_data = {
            "results": []
        }
        user_widgets = list(
            user.userwidget_set.order_by('display_order')
        )

        widget_ids = [user_widget.widget_id for user_widget in user_widgets if user_widget.widget_id]
        widgets_by_id = {
            widget.name: widget
            for widget in Widget.objects.filter(name__in=widget_ids)
        }

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
        user_device_ids = [d.id for d in user_devices]

        active_device_ids = set(
            RawData.objects.filter(
                device_id__in=user_device_ids,
                data_arrival_time__gte=today_start
            ).values_list('device_id', flat=True).distinct()
        )
        active_devices = len(active_device_ids)

        required_property_names = [
            "energy_generated_this_day",
            "energy_generation_limit_this_day",
            "energy_consumed_this_day",
            "energy_consumption_limit_this_day",
            "energy_imported_this_day",
            "energy_import_limit_this_day",
            "energy_exported_this_day",
            "energy_export_limit_this_day",
        ]
        all_dev_props = DeviceProperty.objects.filter(
            device_id__in=user_device_ids,
            name__in=required_property_names
        ).values_list('device_id', 'name', 'value')
        all_dev_prop_values = {}
        for device_id, property_name, property_value in all_dev_props:
            existing_values = all_dev_prop_values.get(str(device_id), {})
            existing_values[property_name] = property_value
            all_dev_prop_values[str(device_id)] = existing_values

        for device in user_devices:
            properties = all_dev_prop_values.get(str(device.id), {})
            total_devices += 1

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

        dashboard_details_cache = {}

        for widget in user_widgets:
            if not widget.active:
                continue

            widget_model = widgets_by_id.get(widget.widget_id)
            if widget_model is None:
                continue

            dashboard_data = None
            if (
                settings.SUPERSET_ENABLED
                and widget_model.metadata != None
                and widget_model.metadata.get("source") == DASHBOARD_SOURCES.superset
            ):
                dashboard_name = widget_model.metadata.get("name")
                if dashboard_name in dashboard_details_cache:
                    dashboard_data = dashboard_details_cache[dashboard_name]
                else:
                    dashboard = SupersetDashboard(dashboard_name)
                    dashboard_data = dashboard.get_details()
                    dashboard_details_cache[dashboard_name] = dashboard_data

            widget_data = {
                "widget": {
                    "name": widget_model.name,
                    "type": widget_model.type,
                    "description": widget_model.description,
                    "metadata": widget_model.metadata
                },
                "display_order": widget.display_order,
                "metadata": widget.metadata,
                "updated_at": widget.updated_at.strftime(settings.TIME_FORMAT_STRING)
            }

            if dashboard_data is not None:
                widget_data["dashboard_data"] = dashboard_data

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
