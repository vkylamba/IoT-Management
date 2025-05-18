from .device_details_views import DeviceDetailsViewSet, DataViewSet, HeartbeatViewSet
from .device_views import DeviceViewSet
from .event_views import EventViewSet
from .user_views import UserViewSet
from .auth import AuthViewSet, VerifyAuthViewSet
from .device_ota_views import DeviceOTAViewSet
from .document_views import DocumentViewSet
# from .social_auth import FacebookLogin, GithubLogin

from .widget_views import WidgetViewSet
from .views import ViewViewSet

__all__ = [
    'WidgetViewSet', 'ViewViewSet', 'DeviceViewSet',
    'DeviceDetailsViewSet', 'HeartbeatViewSet', 'DataViewSet', 'EventViewSet',
    'UserViewSet', 'AuthViewSet', 'VerifyAuthViewSet',
    'DeviceOTAViewSet', 'DocumentViewSet'
    # 'FacebookLogin', 'GithubLogin'
]
