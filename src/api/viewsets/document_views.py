from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from functools import wraps

from device.models import Document, Device
from api.serializers import DocumentSerializer
from django.conf import settings


def device_admin(view_func):
    """
    Decorator to check if the requesting user is a device admin.
    Returns 403 or 404 if not authorized.
    """
    @wraps(view_func)
    def _wrapped_view(self, request, *args, **kwargs):
        device_id = kwargs.get('device_id')
        dev_user = request.user
        device = dev_user.device_list(return_objects=True, device_id=device_id)
        if isinstance(device, list):
            device = [x for x in device if x.ip_address == device_id]
            if len(device) == 0:
                return Response(status=status.HTTP_404_NOT_FOUND)
            device = device[0]
        if device is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if not dev_user.has_permission(settings.PERMISSIONS_ADMIN):
            return Response(status=status.HTTP_403_FORBIDDEN)
        return view_func(self, request, *args, **kwargs)
    return _wrapped_view


class DocumentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet to provide documents linked to a device or user.
    Checks if the requesting user is a device admin before providing device documents.
    """
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'], url_path='by-device/(?P<device_id>[^/.]+)')
    @device_admin
    def by_device(self, request, device_id=None):
        documents = Document.objects.filter(device_id=device_id)
        serializer = self.get_serializer(documents, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='by-user/(?P<user_id>[^/.]+)')
    def by_user(self, request, user_id=None):
        # Only allow users to access their own documents or if they are staff
        if str(request.user.id) != str(user_id) and not request.user.is_staff:
            return Response({'detail': 'Not authorized to view these documents.'}, status=status.HTTP_403_FORBIDDEN)
        documents = Document.objects.filter(user_id=user_id)
        serializer = self.get_serializer(documents, many=True)
        return Response(serializer.data)