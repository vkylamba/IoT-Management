import json
import logging
from django.shortcuts import get_object_or_404
from device.models import DeviceConfig, DeviceFirmware
from django.conf import settings
from django.http import FileResponse
from device.models.device import Device
from rest_framework import status, viewsets, serializers
from rest_framework.response import Response

logger = logging.getLogger('django')


class DeviceConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceConfig
        fields = ('data',)

    def to_representation(self, device_config):
        return device_config.data


class DeviceOTAViewSet(viewsets.ModelViewSet):
    """
        API endpoint to provide device firmware updates details.
    """
    permission_classes = ()
    authentication_classes = ()
    serializer_class = DeviceConfigSerializer

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
        file_resp['Content-Disposition'] = 'attachment; filename="{}.bin"'.format(device)
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

    def get_cfg_updates_for_device(self, request, device):
        """
            returned data format:
            {
                "key": "value"
            }
        """
        logger.info(f"OTA cfg check call request device {device}")
        device = get_object_or_404(Device, alias__iexact=device)
        cfg = DeviceConfig.objects.filter(
            device=device,
        ).order_by('-created_at').first()
        existing_cfg_version = cfg.data.get('cfg_version') if cfg is not None else None
        device_cfg_version = ''
        if request.method == 'POST':
            device_cfg_data = request.data
            logger.info(f"Device: {device}, Checking new config data from device {device_cfg_data}")
            device_cfg_version = device_cfg_data.get('cfg_version', '') if device_cfg_data is not None else ''
            logger.info(f"Device: {device}, New config version is: {device_cfg_version}. Existing config version: {existing_cfg_version}")
            should_save_config = device_cfg_version is None or existing_cfg_version is None or device_cfg_version != existing_cfg_version
            should_save_config = should_save_config and device_cfg_data is not None
            if should_save_config:
                new_cfg = DeviceConfig.objects.create(
                    device=device,
                    data=device_cfg_data,
                    active=False
                )
                new_cfg.save()
                logger.info(f"Saved new config for device {device}")
        if cfg is not None and cfg.active and existing_cfg_version != device_cfg_version:
            return Response(data=cfg.data)
        return Response(status=status.HTTP_404_NOT_FOUND)
