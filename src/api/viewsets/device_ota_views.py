import json
import logging

from django.conf import settings
from rest_framework import viewsets
from rest_framework.response import Response

logger = logging.getLogger('django')


class DeviceOTAViewSet(viewsets.ModelViewSet):
    """
        API endpoint to provide device firmware updates details.
    """
    permission_classes = ()
    authentication_classes = ()

    def get_updates_for_device_type(self, request, device_type):
        """
            returned data format:
            {
                "ver": "x.y"
            }
        """
        logger.debug(f"OTA check call request device type {device_type}")
        return Response(data={
            "ver": "x.y"
        })
    
    def get_updates_for_device(self, request, device):
        """
            returned data format:
            {
                "ver": "x.y"
            }
        """
        logger.debug(f"OTA check call request device type {device}")
        return Response(data={
            "ver": "x.y"
        })

    def download_update_for_device(self, request, device):
        """
            returned data format:
            {
                "ver": "x.y"
            }
        """
        logger.debug(f"OTA check call request device type {device}")
        return Response(data={
            "ver": "x.y"
        })
    
    def download_update_for_device_type(self, request, device_type):
        """
            returned data format:
            {
                "ver": "x.y"
            }
        """
        logger.debug(f"OTA check call request device type {device_type}")
        return Response(data={
            "ver": "x.y"
        })
