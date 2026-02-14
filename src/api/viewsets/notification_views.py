from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from notification.models import SentNotification
from api.serializers.notifications import SentNotificationSerializer


class SentNotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing sent push notifications.
    Only returns notifications of type 'P' (Push notification).
    """
    serializer_class = SentNotificationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Filter to only return push notifications ('P') for the current user.
        """
        return SentNotification.objects.filter(
            notification__method='P',
            notification__user=self.request.user
        ).select_related('notification', 'event').order_by('-sent_time')
