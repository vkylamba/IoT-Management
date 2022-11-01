from rest_framework import serializers
from django.contrib.auth import get_user_model


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
            'devices': []
        }

        for device in user_devices:
            device_data = {
                "ip_address": device.ip_address,
                "alias": device.alias,
                "type": ", ".join([typ.name for typ in device.types.all()])
            }
            data["devices"].append(device_data)

        return data
