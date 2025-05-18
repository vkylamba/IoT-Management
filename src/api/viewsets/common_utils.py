from django.conf import settings
from django.core.cache import cache
from functools import wraps
from rest_framework.response import Response
from rest_framework import status


def is_device_admin(user, device_id, use_cache=True):
    cached_data = None
    if use_cache:
        cached_data = cache.get("is_device_admin{}".format(device_id))

    if cached_data is None:
        device = user.device_list(return_objects=True, device_id=device_id)
        cache.set("is_device_admin{}".format(device_id), device, 60 * 5)
    else:
        device = cached_data
        
    if isinstance(device, list):
        device = [x for x in device if x.ip_address == device_id]
        if len(device) == 0:
            return None, False
        device = device[0]
    return device, user.has_permission(settings.PERMISSIONS_ADMIN)


def device_admin(view_func):
    """
    Decorator to check if the requesting user is a device admin.
    Returns 403 or 404 if not authorized.
    """
    @wraps(view_func)
    def _wrapped_view(self, request, *args, **kwargs):
        device_id = kwargs.get('device_id')
        dev_user = request.user
        device, is_admin = is_device_admin(dev_user, device_id)
        if device is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if not is_admin:
            return Response(status=status.HTTP_403_FORBIDDEN)
        return view_func(self, request, *args, **kwargs)
    return _wrapped_view