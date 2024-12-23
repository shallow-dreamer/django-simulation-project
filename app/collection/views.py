from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.contenttypes.models import ContentType
from .models import Collection
from .serializers import CollectionSerializer

class CollectionViewSet(viewsets.ModelViewSet):
    """收藏API视图集"""
    serializer_class = CollectionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Collection.objects.filter(
            user=self.request.user,
            is_deleted=False
        )
    
    @action(detail=False, methods=['post'])
    def toggle(self, request):
        """切换收藏状态"""
        content_type = ContentType.objects.get(
            app_label=request.data.get('app_label'),
            model=request.data.get('model')
        )
        obj_id = request.data.get('object_id')
        
        collection = Collection.objects.filter(
            user=request.user,
            content_type=content_type,
            object_id=obj_id
        ).first()
        
        if collection:
            collection.is_deleted = not collection.is_deleted
            collection.save()
        else:
            collection = Collection.objects.create(
                user=request.user,
                content_type=content_type,
                object_id=obj_id
            )
        
        return Response(CollectionSerializer(collection).data) 