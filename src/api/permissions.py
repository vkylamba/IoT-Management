from rest_framework import permissions
from device.models import Device, User

"""
    API permissions module.
"""


class IsDeviceUser(permissions.BasePermission):
    """
        Permission to check if the user id a dev user
    """

    def has_permission(self, request, view):
        if request.user:
            return True
        return False

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        return True
        # if request.method in permissions.SAFE_METHODS:
        #     return True

        # return request.user.has_permission("PERMISSIONS_ADMIN")


class IsDevice(permissions.BasePermission):
    """
        Permission to check if the request user is device
    """

    def check_device(self, request):
        token = request.META.get("HTTP_DEVICE")
        mac_address = ""
        if not token:
            token = request.data.get("apiKey")

        if not token:
            mac_address = request.data.get("config", {}).get("mac", "")

        if not token and len(mac_address) < 10:
            return False

        device = False
        if token is not None:
            device = Device.objects.filter(access_token=token).first()
            if not device and mac_address != "":
                device = Device.objects.filter(
                    mac=mac_address
                ).first()
        
        if not device:
            # check if it is a user data token
            user = User.objects.filter(device_data_token=token).first()
            if not user:
                return False
            request.user = user
            return True
        else:
            request.device = device
            return True

    def has_permission(self, request, view):
        return self.check_device(request)

    def has_object_permission(self, request, view, obj):
        return self.check_device(request)
