from rest_framework import authentication
from rest_framework import exceptions

from .models import Device


class DeviceAuthentication(authentication.BaseAuthentication):

    """
        Authentication class for the device.
    """

    def authenticate(self, request):
        token = request.META.get('HTTP_DEVICE')
        if not token:
            return None

        try:
            device = Device.objects.get(access_token=token)
        except Device.DoesNotExist:
            raise exceptions.AuthenticationFailed('No such device')

        return (device, None)
