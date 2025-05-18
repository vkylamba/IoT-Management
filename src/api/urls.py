from django.urls import include, path, re_path
from rest_framework import routers

from api.viewsets import (AuthViewSet, DataViewSet, DeviceDetailsViewSet,
                          DeviceViewSet, EventViewSet, HeartbeatViewSet,
                          UserViewSet, VerifyAuthViewSet, WidgetViewSet,
                          DeviceOTAViewSet, ViewViewSet, DocumentViewSet)

router = routers.DefaultRouter()
router.register(r'user/details', UserViewSet)

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browse-able API.
urlpatterns = [
    # Auth Views
    re_path(
        r'^api-token-auth/$',
        AuthViewSet.as_view({'post': 'sign_in'}),
        name='login'
    ),
    re_path(
        r'^api-token-auth/register/$',
        AuthViewSet.as_view({'post': 'sign_up'})
    ),
    re_path(
        r'^verifyauth',
        VerifyAuthViewSet.as_view({'get': 'verify_auth'})
    ),

    # Dashboard views
    re_path(r'^dashboard/widgets', WidgetViewSet.as_view({'get': 'get_widgets'})),
    re_path(r'^dashboard/views', ViewViewSet.as_view({'get': 'get_views'})),

    # Device views
    re_path(
        r'^devices/types$',
        DeviceViewSet.as_view({'get': 'get_device_types'})
    ),
    re_path(
        r'^devices/$',
        DeviceViewSet.as_view({'get': 'get_devices', 'post': 'create_device'})
    ),
    re_path(
        r'^devices/markfavorite/(?P<device_id>[\w.]+)$',
        DeviceViewSet.as_view({'get': 'mark_as_favorite'})
    ),
    re_path(
        r'^devices/removefavorite/(?P<device_id>[\w.]+)$',
        DeviceViewSet.as_view({'delete': 'unmark_as_favorite'})
    ),

    # Device details views
    re_path(
        r'^device/settings/(?P<device_id>[\w.]+)$',
        DeviceDetailsViewSet.as_view({
            'get': 'device_settings_data',
            'post': 'set_settings_data',
        })
    ),
    re_path(
        r'^device/staticdata/(?P<device_id>[\w.]+)$',
        DeviceDetailsViewSet.as_view({
            'get': 'device_static_data',
            'post': 'update_static_data',
        })
    ),
    re_path(
        r'^device/staticdata/(?P<device_id>[\w.-]+)$',
        DeviceDetailsViewSet.as_view({
            'get': 'device_static_data',
            'post': 'update_static_data',
            'delete': 'remove_device',
        })
    ),
    # Document views
    re_path(
        r'^documents/by-device/(?P<device_id>[\w.-]+)$',
        DocumentViewSet.as_view({'get': 'by_device'})
    ),
    re_path(
        r'^documents/by-user/(?P<user_id>[\w.-]+)$',
        DocumentViewSet.as_view({'get': 'by_user'})
    ),
    re_path(
        r'^documents/upload/$',
        DocumentViewSet.as_view({'post': 'upload'})
    ),
    re_path(
        r'^documents/delete/(?P<pk>[0-9a-fA-F-]{36})$',
        DocumentViewSet.as_view({'delete': 'delete'})
    ),
    re_path(
        r'^device/dynamicdata/(?P<device_id>[\w.]+)$',
        DeviceDetailsViewSet.as_view({'post': 'get_dynamic_data'})
    ),
    re_path(
        r'^device/sendcommand/(?P<device_id>[\w.]+)$',
        DeviceDetailsViewSet.as_view({'post': 'send_command'})
    ),
    re_path(
        r'^device/reportdata/(?P<device_id>[\w.]+)/(?P<report_type>[\w]+)$',
        DeviceDetailsViewSet.as_view({'get': 'get_report'})
    ),
    re_path(
        r'^device/logs/(?P<device_id>[\w.]+)$',
        DeviceDetailsViewSet.as_view({'get': 'get_logs'})
    ),

    # Data views
    re_path(
        r'^data/$',
        DataViewSet.as_view({'post': 'create'})
    ),
    re_path(
        r'^data$',
        DataViewSet.as_view({'post': 'create'})
    ),

    # Device heartbeat views
    re_path(
        r'^heartbeat/$',
        HeartbeatViewSet.as_view({'get': 'get', 'post': 'post'})
    ),

    # Event views
    re_path(
        r'^events/past$',
        EventViewSet.as_view({'get': 'get_past_events'})
    ),
    re_path(r'^events/past/(?P<device_id>[\w.]+)$',
        EventViewSet.as_view({'get': 'get_past_events'})),
    re_path(r'^events/list/', EventViewSet.as_view({'get': 'get_events'})),
    re_path(r'^events/list/(?P<device_id>[\w.]+)?$',
        EventViewSet.as_view({'get': 'get_events'})),
    re_path(r'^events/types/',
        EventViewSet.as_view({'get': 'get_event_types'})),
    re_path(r'^events/(?P<dev_event_id>[\w.]+)$',
        EventViewSet.as_view({'get': 'get_event'})),
    re_path(r'^events/create/(?P<dev_event_id>[\w.]+)?$',
        EventViewSet.as_view({'post': 'create_event'})),
    re_path(r'^events/delete/(?P<dev_event_id>[\w.]+)$',
        EventViewSet.as_view({'delete': 'delete_event'})),

    # OTA update download for device
    re_path(r'^ota/device/download/(?P<device>[\w-]+)',
        DeviceOTAViewSet.as_view({'get': 'download_update_for_device'})),
    # OTA update download for device type
    re_path(r'^ota/device_group/download/(?P<device_group>[\w-]+)',
        DeviceOTAViewSet.as_view({'get': 'download_update_for_device_group'})),
    # OTA update check for device types
    re_path(r'^ota/device_group/(?P<device_group>[\w-]+)',
        DeviceOTAViewSet.as_view({'get': 'get_updates_for_device_group'})),
    # OTA update check for device
    re_path(r'^ota/device/(?P<device>[\w.-]+)',
        DeviceOTAViewSet.as_view({'get': 'get_updates_for_device'})),
    # OTA config update check for device
    re_path(r'^ota/cfg/device/(?P<device>[\w.-]+)',
        DeviceOTAViewSet.as_view({'get': 'get_cfg_updates_for_device', 'post': 'get_cfg_updates_for_device'}))
]

urlpatterns += router.urls
