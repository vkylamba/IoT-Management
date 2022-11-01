from django.conf.urls import include, url
from rest_framework import routers

from api.viewsets import (AuthViewSet, DataViewSet, DeviceDetailsViewSet,
                          DeviceViewSet, EventViewSet, FacebookLogin,
                          GithubLogin, HeartbeatViewSet, UserViewSet,
                          VerifyAuthViewSet, WidgetViewSet)

router = routers.DefaultRouter()
router.register(r'user/details', UserViewSet)

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    # Auth Views
    url(
        r'^api-token-auth/$',
        AuthViewSet.as_view({'post': 'sign_in'}),
        name='login'
    ),
    url(
        r'^api-token-auth/register/$',
        AuthViewSet.as_view({'post': 'sign_up'})
    ),
    url(
        r'^verifyauth',
        VerifyAuthViewSet.as_view({'get': 'verify_auth'})
    ),

    # Dashboard views
    url(r'^dashboard/widgets', WidgetViewSet.as_view({'get': 'get_widgets'})),

    # Device views
    url(
        r'^devices/types$',
        DeviceViewSet.as_view({'get': 'get_device_types'})
    ),
    url(
        r'^devices/$',
        DeviceViewSet.as_view({'get': 'get_devices'})
    ),
    url(
        r'^devices/$',
        DeviceViewSet.as_view({'post': 'create_device'})
    ),
    url(
        r'^devices/markfavorite/(?P<device_id>[\w.]+)$',
        DeviceViewSet.as_view({'get': 'mark_as_favorite'})
    ),
    url(
        r'^devices/removefavorite/(?P<device_id>[\w.]+)$',
        DeviceViewSet.as_view({'delete': 'unmark_as_favorite'})
    ),

    # Device details views
    url(
        r'^device/settings/(?P<device_id>[\w.]+)$',
        DeviceDetailsViewSet.as_view({
            'get': 'device_settings_data',
            'post': 'set_settings_data',
        })
    ),
    url(
        r'^device/staticdata/(?P<device_id>[\w.]+)$',
        DeviceDetailsViewSet.as_view({
            'get': 'device_static_data',
            'post': 'update_static_data'
        })
    ),
    url(
        r'^device/dynamicdata/(?P<device_id>[\w.]+)$',
        DeviceDetailsViewSet.as_view({'get': 'get_dynamic_data'})
    ),
    url(
        r'^device/sendcommand/(?P<device_id>[\w.]+)$',
        DeviceDetailsViewSet.as_view({'post': 'send_command'})
    ),
    url(
        r'^device/reportdata/(?P<device_id>[\w.]+)/(?P<report_type>[\w]+)$',
        DeviceDetailsViewSet.as_view({'get': 'get_report'})
    ),

    # Data views
    url(
        r'^data/$',
        DataViewSet.as_view({'post': 'create'})
    ),

    # Device heartbeat views
    url(
        r'^heartbeat/$',
        HeartbeatViewSet.as_view({'get': 'get', 'post': 'post'})
    ),

    # Event views
    url(
        r'^events/past$',
        EventViewSet.as_view({'get': 'get_past_events'})
    ),
    url(r'^events/past/(?P<device_id>[\w.]+)$',
        EventViewSet.as_view({'get': 'get_past_events'})),
    url(r'^events/list$', EventViewSet.as_view({'get': 'get_events'})),
    url(r'^events/list/(?P<device_id>[\w.]+)?$',
        EventViewSet.as_view({'get': 'get_events'})),
    url(r'^events/types(/)?$',
        EventViewSet.as_view({'get': 'get_event_types'})),
    url(r'^events/(?P<dev_event_id>[\w.]+)$',
        EventViewSet.as_view({'get': 'get_event'})),
    url(r'^events/create/(?P<dev_event_id>[\w.]+)?$',
        EventViewSet.as_view({'post': 'create_event'})),
    url(r'^events/delete/(?P<dev_event_id>[\w.]+)$',
        EventViewSet.as_view({'delete': 'delete_event'})),
    url(r'^api-auth/', include('rest_framework.urls', namespace='rest_framework_auth')),

    # Rest auth views
    url(r'^rest-auth/github', GithubLogin.as_view(), name='github_login'),
    url(r'^rest-auth/facebook', FacebookLogin.as_view(), name='fb_login'),
    url(r'^rest-auth/registration/', include('rest_auth.registration.urls')),
    url(r'^rest-auth/', include('rest_auth.urls')),
    url(r'^accounts/', include('allauth.urls')),
]

urlpatterns += router.urls
