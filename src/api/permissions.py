from rest_framework import permissions
from device.models import Device

"""
    API permissions module.
    PERMISSIONS_ADMIN
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
            token = request.data.get("apikey")

        if not token:
            mac_address = request.data.get("config", {}).get("mac", "")

        if not token and len(mac_address) < 10:
            return False

        try:
            if token is not None:
                device = Device.objects.get(access_token=token)
            if mac_address != "":
                device = Device.objects.get(
                    mac=mac_address
                )
        except Device.DoesNotExist:
            return False

        else:
            request.device = device
            return True

    def has_permission(self, request, view):
        return self.check_device(request)

    def has_object_permission(self, request, view, obj):
        return self.check_device(request)
