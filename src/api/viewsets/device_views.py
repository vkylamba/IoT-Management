import datetime
import logging

from api.permissions import IsDeviceUser
from device.models import Device, DeviceType
from dashboard.models import Widget, UserWidget
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

logger = logging.getLogger('django')


class DeviceViewSet(viewsets.ViewSet):
    """
        ViewSet to provide uviews related to data analysis.
    """
    permission_classes = (IsAuthenticated, IsDeviceUser)

    def get_devices(self, request):
        """
            View to return list of devices owned by user.
        """
        user = request.user
        devices_list = []
        error = "success"

        for device in user.device_list(return_objects=True):
            other_data = device.other_data

            try:
                device_type = device.device_type
            except Exception as Ex:
                device_type = None

            other_data = device.other_data
            if other_data is None:
                other_data = {}

            devices_list += [
                {
                    "id": device.id,
                    "alias": device.alias,
                    "name": device.name,
                    "ip_address": str(device.ip_address),
                    "lat":  other_data.get("latitude", device.latitude()),
                    "long": other_data.get("longitude", device.longitude()),
                    "type": device_type.name if device_type is not None else None,
                    "face": device.avatar.url if device.avatar else None,
                    "address": device.address,
                    "other_data": other_data
                }
            ]

        data = {
            "username": user.username,
            "error": error,
            'devices': devices_list,
            'userAvatar': user.dev_image.url if user.dev_image else None
        }
        return Response(data)

    def get_device_types(self, request):
        """
            View to return device types.
        """
        data = []
        for dev_type in DeviceType.objects.all():
            data.append({'value': dev_type.name, 'label': dev_type.name})
        return Response(data)

    def create_device(self, request, *args):
        data = request.data

        device_type = data.get('device_type')
        device_name = data.get('device_name')

        if any([device_name is None, device_type is None]):
            resp_status = status.HTTP_400_BAD_REQUEST
            error = "Device name and device type are required"
            data = {
                'success': False,
                'error': error
            }
            return Response(status=resp_status, data=data)

        dev_type, created = DeviceType.objects.get_or_create(
            name=device_type
        )
        if created:
            dev_type.save()

        device = Device.objects.filter(
            alias=device_name
        ).first()
        if device:
            return Response(
                status=status.HTTP_200_OK,
                data={
                    "name": device.name,
                    'alias': device.alias,
                    'ip_address': device.ip_address,
                    'access_token': device.access_token
                }
            )

        device_contact_number = data.get('contact')
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        avatar = data.get('avatar')
        if avatar:
            fs = FileSystemStorage()
            avatar = fs.save(avatar.name, avatar)

        error = None
        resp_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        dev_user = request.user
        _, next_ip_address = dev_user.device_list(
            return_next_address=True
        )
        if next_ip_address is not None and not Device.objects.filter(
            ip_address=next_ip_address
        ).exists():
            device = Device(
                alias=device_name,
                ip_address=next_ip_address,
                installation_date=timezone.now(),
                device_contact_number=device_contact_number,
                avatar=avatar
            )
            if latitude is not None and longitude is not None:
                device.position = "{}, {}".format(latitude, longitude)
            device.save()
            device.types.add(dev_type)
            device.save()
            resp_status = status.HTTP_201_CREATED
        else:
            logger.error(
                "Device with ip address {} already exists.".format(next_ip_address))
            error = "Error Occurred."
            resp_status = status.HTTP_422_UNPROCESSABLE_ENTITY

        data = {
            'success': False if error else True,
            'error': error
        }
        return Response(status=resp_status, data=data)

    def mark_as_favorite(self, request, device_id=None):
        # Find out the user
        dev_user = request.user
        device = dev_user.device_list(return_objects=True, device_id=device_id)

        if isinstance(device, list):
            return Response(status=status.HTTP_404_NOT_FOUND)

        user_widget = dev_user.userwidget_set.filter(
            active=True,
            widget__name__icontains='favorite devices'
        ).first()

        if not user_widget:
            widget, created = Widget.objects.get_or_create(
                name="Favorite Devices"
            )
            if created:
                widget.type = Widget.FAVORITE
                widget.save()
            user_widget = UserWidget(
                user=dev_user,
                widget=widget,
                active=True,
                metadata={
                    "favorite_devices": []
                }
            )
            user_widget.save()

        if user_widget.metadata is None:
            user_widget.metadata = {}

        favorite_devices = user_widget.metadata.get("favorite_devices", [])
        if device.id not in favorite_devices:
            favorite_devices.append(str(device.id))
            user_widget.metadata["favorite_devices"] = favorite_devices
            user_widget.save()
        return Response(status=status.HTTP_200_OK)

    def unmark_as_favorite(self, request, device_id=None):
        dev_user = request.user
        device = dev_user.device_list(return_objects=True, device_id=device_id)

        if isinstance(device, list):
            return Response(status=status.HTTP_404_NOT_FOUND)

        user_widget = dev_user.userwidget_set.filter(
            active=True,
            widget__name__icontains='favorite devices'
        ).first()

        if not user_widget:
            return Response(status=status.HTTP_204_NO_CONTENT)

        if user_widget.metadata is None:
            user_widget.metadata = {}

        favorite_devices = user_widget.metadata.get("favorite_devices", [])
        if device.id in favorite_devices:
            user_widget.metadata["favorite_devices"] = [x for x in favorite_devices if x != device.id]
            user_widget.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
