from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from .models import Collection

class ContentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentType
        fields = ['app_label', 'model']

class CollectionSerializer(serializers.ModelSerializer):
    content_type = ContentTypeSerializer()
    content_object_repr = serializers.SerializerMethodField()
    
    class Meta:
        model = Collection
        fields = [
            'id', 'user', 'content_type', 'object_id',
            'content_object_repr', 'is_deleted', 'deleted_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_content_object_repr(self, obj):
        """获取被收藏对象的字符串表示"""
        if obj.content_object:
            return str(obj.content_object)
        return None 