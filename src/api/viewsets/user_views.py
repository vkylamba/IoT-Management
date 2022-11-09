import json
import logging

from api.permissions import IsDeviceUser
from api.serializers import UserSerializer
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import filters, viewsets
from rest_framework.parsers import FileUploadParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

PERMISSIONS_ADMIN = settings.PERMISSIONS_ADMIN

User = get_user_model()
logger = logging.getLogger('django')


class UserViewSet(viewsets.ModelViewSet):
    """
        API endpoint to provide user details.
    """
    permission_classes = (IsAuthenticated, IsDeviceUser)
    parser_class = (FileUploadParser,)
    serializer_class = UserSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'email', 'first_name', 'last_name']
    queryset = User.objects.all()

    def list(self, request):
        if request.user.is_superuser:
            return super(UserViewSet, self).list(request)
        else:
            return Response(data=self.serializer_class(request.user).data)

    def post(self, request, pk):
        if 'file' in request.data:
            file = request.data.pop('file')[0]
            request.user.dev_image.save(file.name, file, save=True)
        if 'document' in request.data:
            json_doc = request.data.pop('document')[0]
            data = json.loads(json_doc.read())
            request.data.update(data)
        return super(UserViewSet, self).partial_update(request, pk)
