from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.permissions import IsDeviceUser
from dashboard.models import View
from dashboard.serializers import ViewSerializer
from device.models import DeviceProperty


class ViewViewSet(viewsets.ViewSet):
    """
        API endpoint to provide view details.
    """
    permission_classes = (IsAuthenticated, IsDeviceUser)

    def get_views(self, request):
        view_types = request.query_params.get("view_types", [])
        
        views = View.objects.filter(
            user=request.user
        )
        view_types = view_types.split(',') if view_types is not None else []
        if len(view_types) > 0:
            views = views.filter(
                view_type__in=view_types
            )

        data = ViewSerializer(views, many=True).data
        return Response(data)
