import json
import logging
from urllib.parse import parse_qs
from django.shortcuts import get_object_or_404
from device.models import DeviceConfig, DeviceFirmware
from django.conf import settings
from django.http import FileResponse
from django.http.request import RawPostDataException
from device.models.device import Device
from rest_framework import status, viewsets, serializers
from rest_framework.exceptions import ParseError, UnsupportedMediaType
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

    def parse_config_text(self, text):
        if not isinstance(text, str):
            return None

        text = text.strip()
        if not text:
            return None

        try:
            parsed = json.loads(text, strict=False)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

        if isinstance(parsed, dict) and len(parsed) == 1 and isinstance(parsed.get('config'), dict):
            return parsed.get('config')

        return parsed if isinstance(parsed, dict) else None

    def normalize_config_payload(self, payload):
        if payload is None:
            return {}

        if hasattr(payload, 'dict'):
            payload = payload.dict()
        elif not isinstance(payload, dict):
            payload = dict(payload)

        if not isinstance(payload, dict):
            return {}

        config_payload = payload.get('config')
        if isinstance(config_payload, dict):
            return config_payload

        if isinstance(config_payload, str):
            parsed_config = self.parse_config_text(config_payload)
            if parsed_config is not None:
                return parsed_config

        if len(payload) == 1:
            key, value = next(iter(payload.items()))
            if isinstance(value, str):
                parsed_value = self.parse_config_text(value)
                if parsed_value is not None:
                    return parsed_value

            if value in [None, '', ['']] and isinstance(key, str):
                parsed_key = self.parse_config_text(key)
                if parsed_key is not None:
                    return parsed_key

        return payload

    def get_request_payload(self, request):
        raw_body = ""
        django_request = getattr(request, '_request', request)

        try:
            raw_body = django_request.body.decode('utf-8', errors='ignore').strip()
        except RawPostDataException:
            raw_body = getattr(django_request, '_body', b'').decode(
                'utf-8', errors='ignore'
            ).strip()

        try:
            payload = request.data
            if payload is None:
                return {}
            return self.normalize_config_payload(payload)
        except (ParseError, UnsupportedMediaType, ValueError, TypeError) as ex:
            payload_preview = raw_body[:2000] if raw_body else '<empty>'
            logger.warning(
                "OTA cfg payload parse fallback triggered: %s. Raw payload preview: %s",
                ex,
                payload_preview,
            )

        if not raw_body:
            return {}

        parsed_json = self.parse_config_text(raw_body)
        if parsed_json is not None:
            return parsed_json

        parsed_form = parse_qs(raw_body, keep_blank_values=True)
        return self.normalize_config_payload({
            key: values[-1] if isinstance(values, list) and values else values
            for key, values in parsed_form.items()
        })

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
        device_configs = list(DeviceConfig.objects.filter(
            device=device,
        ).order_by('-created_at'))
        latest_cfg = device_configs[0] if device_configs else None
        active_cfg = next(
            (config for config in device_configs if getattr(config, 'active', False)),
            None,
        )

        existing_cfg_version = (
            latest_cfg.data.get('cfg_version')
            if latest_cfg is not None and latest_cfg.data is not None
            else None
        )
        active_cfg_version = (
            active_cfg.data.get('cfg_version')
            if active_cfg is not None and active_cfg.data is not None
            else None
        )
        device_cfg_version = ''
        if request.method == 'POST':
            device_cfg_data = self.get_request_payload(request)
            logger.info(f"Device: {device}, Checking new config data from device {device_cfg_data}")
            device_cfg_version = device_cfg_data.get('cfg_version', '') if device_cfg_data is not None else ''
            logger.info(f"Device: {device}, New config version is: {device_cfg_version}. Existing config version: {existing_cfg_version}")
            should_save_config = device_cfg_version is None or existing_cfg_version is None or device_cfg_version != existing_cfg_version
            should_save_config = should_save_config and device_cfg_data is not None
            if should_save_config:
                new_cfg = DeviceConfig.objects.create(
                    device=device,
                    data=device_cfg_data,
                    active=True
                )
                new_cfg.save()
                logger.info(f"Saved new config for device {device}")
                # Mark all other configs as inactive
                DeviceConfig.objects.filter(device=device).exclude(id=new_cfg.id).update(active=False)
                active_cfg = new_cfg
                active_cfg_version = device_cfg_version
            else:
                logger.info(f"No need to save new config for device {device} as version is the same or data is invalid")

        if active_cfg is not None and active_cfg_version != device_cfg_version:
            return Response(data=active_cfg.data)

        if request.method == 'POST':
            return Response(data={})

        return Response(status=status.HTTP_404_NOT_FOUND)
