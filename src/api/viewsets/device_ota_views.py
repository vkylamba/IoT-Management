import json
import logging

from device.models import DeviceFirmware
from django.conf import settings
from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.response import Response

logger = logging.getLogger('django')


class DeviceOTAViewSet(viewsets.ModelViewSet):
    """
        API endpoint to provide device firmware updates details.
    """
    permission_classes = ()
    authentication_classes = ()

    def get_updates_for_device_group(self, request, device_group):
        """
            returned data format:
            {
                "ver": "x.y"
            }
        """
        logger.debug(f"OTA check call request device group {device_group}")
        firmware = DeviceFirmware.objects.filter(
            group_name__iexact=device_group
        ).order_by('-created_at').first()

        if firmware:
            return Response(data={
                "ver": firmware.version
            })
        return Response(status=status.HTTP_404_NOT_FOUND)

    def get_updates_for_device(self, request, device):
        """
            returned data format:
            {
                "ver": "x.y"
            }
        """
        logger.debug(f"OTA check call request device {device}")
        firmware = DeviceFirmware.objects.filter(
            device_type__name__iexact=device
        ).order_by('-created_at').first()

        if firmware:
            return Response(data={
                "ver": firmware.version
            })
        return Response(status=status.HTTP_404_NOT_FOUND)

    def download_update_for_device(self, request, device):
        """
            returned data format:
            {
                "ver": "x.y"
            }
        """
        logger.debug(f"Download firmware device type {device}")
        device_token = request.query_params.get('token')
        firmware = DeviceFirmware.objects.filter(
            device_type__name__iexact=device
        ).order_by('-created_at').first()

        if not firmware:
            return Response(status=status.HTTP_404_NOT_FOUND)

        open_file = firmware.document.open()
        file_resp = FileResponse(open_file)
        file_resp['Content-Disposition'] = 'attachment; filename="{}.bin"'.format(device_group)
        file_resp['Content-Length'] = open_file.size
        return file_resp

    def download_update_for_device_group(self, request, device_group):
        """
            returned data format:
            {
                "ver": "x.y"
            }
        """
        logger.debug(f"Download firmware device group {device_group}")
        device_token = request.query_params.get('token')
        firmware = DeviceFirmware.objects.filter(
            group_name__iexact=device_group
        ).order_by('-created_at').first()

        if not firmware:
            return Response(status=status.HTTP_404_NOT_FOUND)

        open_file = firmware.document.open()
        file_resp = FileResponse(open_file)
        file_resp['Content-Disposition'] = 'attachment; filename="{}.bin"'.format(device_group)
        file_resp['Content-Length'] = open_file.size
        return file_resp
