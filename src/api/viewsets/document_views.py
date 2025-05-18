import json
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from device.models import Document
from api.serializers import DocumentSerializer
from django.conf import settings
from api.viewsets.common_utils import is_device_admin

class DocumentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet to provide documents linked to a device or user.
    Checks if the requesting user is a device admin before providing device documents.
    """
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'], url_path='by-device/(?P<device_id>[^/.]+)')
    def by_device(self, request, device_id=None):
        device, is_admin = is_device_admin(request.user, device_id)
        if device is None or not is_admin:
            return Response({'detail': 'Not authorized to view these documents.'}, status=status.HTTP_403_FORBIDDEN)
        # Fetch documents for the device
        documents = Document.objects.filter(device=device)
        serializer = self.get_serializer(documents, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='by-user/(?P<user_id>[^/.]+)')
    def by_user(self, request, user_id=None):
        # Only allow users to access their own documents or if they are staff
        if str(request.user.id) != str(user_id) and not request.user.is_staff:
            return Response({'detail': 'Not authorized to view these documents.'}, status=status.HTTP_403_FORBIDDEN)
        documents = Document.objects.filter(user_id=user_id)
        serializer = self.get_serializer(documents, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='upload')
    def upload(self, request):
        """
        Upload a document for a device or a user.
        Expects 'file', and either 'device_id' or 'user_id' in the request data.
        """
        file = request.FILES.get('file')
        json_document = request.data.get('document')

        if not file or not json_document:
            return Response({'detail': 'File and document data are required.'}, status=status.HTTP_400_BAD_REQUEST)

        # read the json_document
        try:
            document_data = json.load(json_document)
        except json.JSONDecodeError:
            return Response({'detail': 'Invalid JSON format.'}, status=status.HTTP_400_BAD_REQUEST)

        device_ip_address = document_data.get('device_ip_address')
        user_id = document_data.get('user_id')
        doc_name = document_data.get('doc_name')
        doc_type = document_data.get('doc_type')
        if not doc_name or not doc_type:
            return Response({'detail': 'Document name and type are required.'}, status=status.HTTP_400_BAD_REQUEST)
        # Check if either device_ip_address or user_id is provided
        if not device_ip_address and not user_id:
            return Response({'detail': 'Either device ip_address or user_id must be provided.'}, status=status.HTTP_400_BAD_REQUEST)

        if device_ip_address:
            # Check device admin permission
            device, is_admin = is_device_admin(request.user, device_ip_address)
            if device is None or not is_admin:
                return Response({'detail': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)
            document = Document.objects.create(
                device=device, doc_name=doc_name, doc_type=doc_type,
                document=file, updated_by=request.user
            )
        else:
            # Only allow users to upload for themselves or staff
            if str(request.user.id) != str(user_id) and not request.user.has_permission(settings.PERMISSIONS_ADMIN):
                return Response({'detail': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)
            document = Document.objects.create(
                user=request.user, doc_name=doc_name, doc_type=doc_type,
                document=file, updated_by=request.user
            )

        serializer = self.get_serializer(document)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path='delete')
    def delete(self, request, pk=None):
        """
        Delete a document by document id (pk).
        Only the owner, device admin, or staff can delete.
        """
        try:
            document = Document.objects.get(pk=pk)
        except Document.DoesNotExist:
            return Response({'detail': 'Document not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Check permissions
        if document.device_id:
            device, is_admin = is_device_admin(request.user, document.device.ip_address)
            if device is None or not is_admin:
                return Response({'detail': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)
        elif document.user_id:
            if str(request.user.id) != str(document.user_id) and not request.user.is_staff:
                return Response({'detail': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)
        else:
            return Response({'detail': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)

        document.delete()
        return Response({'detail': 'Document deleted.'}, status=status.HTTP_204_NO_CONTENT)
