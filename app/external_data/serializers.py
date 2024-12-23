from rest_framework import serializers
from .models import ExternalPlatform, ExternalDataFetch

class ExternalPlatformSerializer(serializers.ModelSerializer):
    """外部平台序列化器"""
    class Meta:
        model = ExternalPlatform
        fields = ['id', 'name', 'base_url', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

class ExternalDataFetchSerializer(serializers.ModelSerializer):
    """数据获取记录序列化器"""
    platform_name = serializers.CharField(source='platform.name', read_only=True)
    
    class Meta:
        model = ExternalDataFetch
        fields = [
            'id', 'platform', 'platform_name', 'data_type', 'status',
            'raw_data', 'processed_data', 'error_message',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

class DataSyncRequestSerializer(serializers.Serializer):
    """数据同步请求序列化器"""
    platform_id = serializers.IntegerField(required=False)
    data_type = serializers.CharField()
    params = serializers.DictField(required=False) 