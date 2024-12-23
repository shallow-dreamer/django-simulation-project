from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from .models import ExternalPlatform, ExternalDataFetch
from .serializers import (
    ExternalPlatformSerializer,
    ExternalDataFetchSerializer,
    DataSyncRequestSerializer
)
from .tasks import sync_platform_data, sync_all_platforms_data
from .sync import DataSyncService
from .core.decorators import cache_view_result

class ExternalPlatformViewSet(viewsets.ModelViewSet):
    """外部平台API视图集"""
    queryset = ExternalPlatform.objects.all()
    serializer_class = ExternalPlatformSerializer
    permission_classes = [IsAuthenticated]
    
    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        """触发平台数据同步"""
        platform = self.get_object()
        serializer = DataSyncRequestSerializer(data=request.data)
        
        if serializer.is_valid():
            task = sync_platform_data.delay(
                platform.id,
                serializer.validated_data['data_type'],
                serializer.validated_data.get('params')
            )
            return Response({
                'task_id': task.id,
                'status': 'accepted'
            }, status=status.HTTP_202_ACCEPTED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ExternalDataFetchViewSet(viewsets.ReadOnlyModelViewSet):
    """数据获取记录API视图集"""
    queryset = ExternalDataFetch.objects.all()
    serializer_class = ExternalDataFetchSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        platform_id = self.request.query_params.get('platform_id')
        data_type = self.request.query_params.get('data_type')
        status = self.request.query_params.get('status')
        
        if platform_id:
            queryset = queryset.filter(platform_id=platform_id)
        if data_type:
            queryset = queryset.filter(data_type=data_type)
        if status:
            queryset = queryset.filter(status=status)
            
        return queryset.select_related('platform') 

    @action(detail=False, methods=['post'])
    @cache_view_result('external_data', timeout=1800)
    def fetch_data(self, request):
        """获取外部数据"""
        serializer = DataSyncRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
            
        platform_id = serializer.validated_data.get('platform_id')
        data_type = serializer.validated_data['data_type']
        params = serializer.validated_data.get('params', {})
        
        platform = get_object_or_404(ExternalPlatform, id=platform_id)
        service = ExternalDataService(platform)
        
        try:
            result = service.fetch_data(data_type, params)
            return Response(result)
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=500)