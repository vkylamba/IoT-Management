from .device_details_views import DeviceDetailsViewSet, DataViewSet, HeartbeatViewSet
from .device_views import DeviceViewSet
from .event_views import EventViewSet
from .user_views import UserViewSet
from .auth import AuthViewSet, VerifyAuthViewSet
from .device_ota_views import DeviceOTAViewSet
# from .social_auth import FacebookLogin, GithubLogin

from .widget_views import WidgetViewSet

__all__ = [
    'WidgetViewSet', 'DeviceViewSet',
    'DeviceDetailsViewSet', 'HeartbeatViewSet', 'DataViewSet', 'EventViewSet',
    'UserViewSet', 'AuthViewSet', 'VerifyAuthViewSet',
    'DeviceOTAViewSet',
    # 'FacebookLogin', 'GithubLogin'
]
