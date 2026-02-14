from rest_framework import serializers
from notification.models import SentNotification


class SentNotificationSerializer(serializers.ModelSerializer):
    """Serializer for SentNotification model"""
    notification_name = serializers.CharField(source='notification.name', read_only=True)
    notification_method = serializers.CharField(source='notification.method', read_only=True)
    event_id = serializers.UUIDField(source='event.id', read_only=True)
    
    class Meta:
        model = SentNotification
        fields = ['id', 'notification', 'notification_name', 'notification_method', 
                  'event', 'event_id', 'sent_time']
        read_only_fields = ['id', 'sent_time']
