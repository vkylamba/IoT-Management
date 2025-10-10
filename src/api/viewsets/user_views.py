import json
import logging

from api.permissions import IsDeviceUser
from api.serializers import UserSerializer
from device.models import StatusType, UserDeviceType
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import filters, status, viewsets
from rest_framework.parsers import FileUploadParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

PERMISSIONS_ADMIN = settings.PERMISSIONS_ADMIN

User = get_user_model()
logger = logging.getLogger('django')


class UserViewSet(viewsets.ModelViewSet):
    """
        API endpoint to provide user details.
    """
    permission_classes = (IsAuthenticated, IsDeviceUser)
    parser_class = (FileUploadParser,)
    serializer_class = UserSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'email', 'first_name', 'last_name']
    queryset = User.objects.all()

    def list(self, request):
        if request.user.is_superuser:
            return super(UserViewSet, self).list(request)
        else:
            return Response(data=self.serializer_class(request.user).data)

    def post(self, request, pk):
        if 'file' in request.data:
            file = request.data.pop('file')[0]
            request.user.dev_image.save(file.name, file, save=True)
        if 'document' in request.data:
            json_doc = request.data.pop('document')[0]
            data = json.loads(json_doc.read())
            request.data.update(data)

        if request.user.has_permission(PERMISSIONS_ADMIN):
            # handle the device and status types update
            available_device_types = request.data.get("available_device_types", [])
            available_status_types = request.data.get("available_status_types", [])

            errors = []
            user_device_types = UserDeviceType.objects.filter(user=request.user)
            devices_ids_to_keep = []
            for available_device_type in available_device_types:
                device_type_id = available_device_type.get("id")
                if device_type_id is not None:
                    device_type = user_device_types.filter(
                        id=device_type_id
                    ).first()
                    if device_type is None:
                        errors.append(f"Device type with id {device_type_id} not found!")
                        continue
                else:
                    device_type = UserDeviceType()
                if len(errors) == 0:
                    device_type.name = available_device_type.get("name", device_type.code)
                    device_type.code = device_type.name.upper() if device_type.name is not None else None
                    device_type.details = available_device_type.get("details", device_type.details)
                    device_type.identifier_field = available_device_type.get("identifier_field", device_type.identifier_field)
                    device_type.data_schema = available_device_type.get("data_schema", device_type.data_schema)
                    if device_type.user is None:
                        device_type.user = request.user
                    device_type.save()
                devices_ids_to_keep.append(device_type.id)
            
            # Delete the remaining device types
            user_device_types.filter(~Q(id__in=devices_ids_to_keep)).delete()

            user_status_types = StatusType.objects.filter(user=request.user)
            status_ids_to_keep = []
            for available_status_type in available_status_types:
                status_type_id = available_status_type.get("id")
                if status_type_id is not None:
                    status_type = StatusType.objects.filter(
                        id=status_type_id
                    ).first()
                    if status_type is None:
                        errors.append(f"Status type with id {status_type_id} not found!")
                        continue
                else:
                    status_type = StatusType()
                if len(errors) == 0:
                    status_type.name = available_status_type.get("name", status_type.name)
                    status_type.target_type = available_status_type.get("target_type", status_type.target_type)
                    status_type.update_trigger = available_status_type.get("update_trigger", status_type.update_trigger)
                    if status_type.user is None:
                        status_type.user = request.user
                    status_type.translation_schema = available_status_type.get("translation_schema", status_type.translation_schema)
                    status_type.save()

                if getattr(status_type, 'id') is not None:
                    status_ids_to_keep.append(status_type.id)

            # Delete the remaining status types
            if len(errors) == 0:
                user_status_types.filter(~Q(id__in=status_ids_to_keep)).delete()
            
            if len(errors) > 0:
                return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        return super(UserViewSet, self).partial_update(request, pk)
