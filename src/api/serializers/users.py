from rest_framework import serializers
from django.contrib.auth import get_user_model
from device.models import UserDeviceType, StatusType
from .device import UserDeviceTypeSerializer, StatusTypeSerializer

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'city',
            'country',
            'postal_code',
            'description',
        )

    def to_representation(self, user):
        user_devices = user.device_list(return_objects=True)
        available_device_types = UserDeviceType.objects.filter(
            user=user
        ).all()
        available_status_types = StatusType.objects.filter(
            user=user
        ).all()
        dev_types = []
        for dev_type in available_device_types:
            if not dev_type.active: continue
            dev_types.append(UserDeviceTypeSerializer(dev_type).data)
        
        status_types = []
        for status_type in available_status_types:
            if not status_type.active: continue
            status_types.append(StatusTypeSerializer(status_type).data)

        data = {
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'avatar': user.dev_image.url if user.dev_image else None,
            'city': user.city,
            'country': user.country,
            'postal_code': user.postal_code,
            'about_me': user.description,
            'device_data_token': user.device_data_token,
            'devices': [],
            'available_device_types': dev_types,
            'available_status_types': status_types
        }


        for device in user_devices:
            device_data = {
                "ip_address": device.ip_address,
                "alias": device.alias,
                "type": ", ".join([typ.name for typ in device.types.all()])
            }
            data["devices"].append(device_data)

        return data
