from asset.models import Asset, AssetAttribute, AssetBindingAgent, AssetType
from api.permissions import IsDeviceUser
from api.serializers.asset import (AssetAttributeSerializer, AssetBindingAgentSerializer,
                                   AssetSerializer, AssetTypeSerializer)
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


class AssetViewSet(viewsets.ViewSet):
    permission_classes = (IsAuthenticated, IsDeviceUser)

    DEFAULT_ASSET_TYPES = (
        {
            'name': 'Site',
            'slug': 'site',
            'category': AssetType.CATEGORY_INFRA,
            'description': 'Generic top-level site, campus, farm, building, or facility.'
        },
        {
            'name': 'Area',
            'slug': 'area',
            'category': AssetType.CATEGORY_ZONE,
            'description': 'Generic sub-area such as field, floor, room, or zone.'
        },
        {
            'name': 'Equipment',
            'slug': 'equipment',
            'category': AssetType.CATEGORY_INFRA,
            'description': 'Physical equipment or machine asset.'
        },
        {
            'name': 'Storage',
            'slug': 'storage',
            'category': AssetType.CATEGORY_STORAGE,
            'description': 'Tank, cooler, warehouse, shelf, or other storage asset.'
        },
        {
            'name': 'Sensor Group',
            'slug': 'sensor-group',
            'category': AssetType.CATEGORY_SENSOR_GROUP,
            'description': 'Logical grouping for one or more sensors or telemetry sources.'
        },
    )

    def _ensure_default_asset_types(self):
        existing_system_slugs = set(
            AssetType.objects.filter(is_system=True).values_list('slug', flat=True)
        )
        missing_types = [
            asset_type for asset_type in self.DEFAULT_ASSET_TYPES
            if asset_type['slug'] not in existing_system_slugs
        ]

        for asset_type in missing_types:
            AssetType.objects.create(
                owner=None,
                name=asset_type['name'],
                slug=asset_type['slug'],
                category=asset_type['category'],
                description=asset_type['description'],
                is_system=True,
                active=True,
            )

    def get_asset_types(self, request):
        self._ensure_default_asset_types()
        types = AssetType.objects.filter(Q(is_system=True) | Q(owner=request.user), active=True)
        serializer = AssetTypeSerializer(types, many=True)
        return Response(serializer.data)

    def create_asset_type(self, request):
        serializer = AssetTypeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save(owner=request.user, is_system=False)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update_asset_type(self, request, asset_type_id):
        asset_type = AssetType.objects.filter(id=asset_type_id, owner=request.user).first()
        if asset_type is None:
            return Response({'success': False, 'error': 'Asset type not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = AssetTypeSerializer(asset_type, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(serializer.data)

    def delete_asset_type(self, request, asset_type_id):
        asset_type = AssetType.objects.filter(id=asset_type_id, owner=request.user).first()
        if asset_type is None:
            return Response({'success': False, 'error': 'Asset type not found.'}, status=status.HTTP_404_NOT_FOUND)

        asset_type.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_assets(self, request):
        assets = Asset.objects.filter(owner=request.user).select_related('asset_type', 'parent')
        serializer = AssetSerializer(assets, many=True)
        return Response(serializer.data)

    def create_asset(self, request):
        serializer = AssetSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save(owner=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def get_asset(self, request, asset_id):
        asset = Asset.objects.filter(id=asset_id, owner=request.user).first()
        if asset is None:
            return Response({'success': False, 'error': 'Asset not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = AssetSerializer(asset)
        return Response(serializer.data)

    def update_asset(self, request, asset_id):
        asset = Asset.objects.filter(id=asset_id, owner=request.user).first()
        if asset is None:
            return Response({'success': False, 'error': 'Asset not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = AssetSerializer(asset, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(serializer.data)

    def delete_asset(self, request, asset_id):
        asset = Asset.objects.filter(id=asset_id, owner=request.user).first()
        if asset is None:
            return Response({'success': False, 'error': 'Asset not found.'}, status=status.HTTP_404_NOT_FOUND)

        asset.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def create_asset_attribute(self, request, asset_id):
        asset = Asset.objects.filter(id=asset_id, owner=request.user).first()
        if asset is None:
            return Response({'success': False, 'error': 'Asset not found.'}, status=status.HTTP_404_NOT_FOUND)

        payload = dict(request.data)
        payload['asset'] = str(asset.id)

        serializer = AssetAttributeSerializer(data=payload)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update_asset_attribute(self, request, attribute_id):
        attr = AssetAttribute.objects.filter(id=attribute_id, asset__owner=request.user).first()
        if attr is None:
            return Response({'success': False, 'error': 'Asset attribute not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = AssetAttributeSerializer(attr, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(serializer.data)

    def delete_asset_attribute(self, request, attribute_id):
        attr = AssetAttribute.objects.filter(id=attribute_id, asset__owner=request.user).first()
        if attr is None:
            return Response({'success': False, 'error': 'Asset attribute not found.'}, status=status.HTTP_404_NOT_FOUND)

        attr.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_asset_agents(self, request, asset_id=None):
        if asset_id:
            agents = AssetBindingAgent.objects.filter(owner=request.user, asset_id=asset_id).prefetch_related('devices')
        else:
            agents = AssetBindingAgent.objects.filter(owner=request.user).prefetch_related('devices')
        serializer = AssetBindingAgentSerializer(agents, many=True)
        return Response(serializer.data)

    def create_asset_agent(self, request):
        serializer = AssetBindingAgentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save(owner=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update_asset_agent(self, request, agent_id):
        agent = AssetBindingAgent.objects.filter(id=agent_id, owner=request.user).first()
        if agent is None:
            return Response({'success': False, 'error': 'Asset agent not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = AssetBindingAgentSerializer(agent, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(serializer.data)

    def delete_asset_agent(self, request, agent_id):
        agent = AssetBindingAgent.objects.filter(id=agent_id, owner=request.user).first()
        if agent is None:
            return Response({'success': False, 'error': 'Asset agent not found.'}, status=status.HTTP_404_NOT_FOUND)

        agent.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
