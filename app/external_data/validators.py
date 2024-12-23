from typing import Dict, Any, List
from abc import ABC, abstractmethod
from django.utils import timezone
from django.db import models

class DataValidator(ABC):
    """数据验证器基类"""
    
    @abstractmethod
    def validate(self, data: Dict) -> List[str]:
        """验证数据，返回错误信息列表"""
        pass

class SParameterDataValidator(DataValidator):
    """S参数数据验证器"""
    
    def validate(self, data: Dict) -> List[str]:
        errors = []
        
        # 验证必要字段
        required_fields = ['frequency_range', 'data_points']
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        
        # 验证数据格式
        if 'data_points' in data:
            if not isinstance(data['data_points'], list):
                errors.append("data_points must be a list")
            elif not all(isinstance(point, dict) for point in data['data_points']):
                errors.append("Each data point must be a dictionary")
        
        return errors

class DataCleanupService:
    """数据清理服务"""
    
    @staticmethod
    def cleanup_old_records(days: int = 30):
        """清理旧的数据获取记录"""
        cutoff_date = timezone.now() - timezone.timedelta(days=days)
        ExternalDataFetch.objects.filter(
            created_at__lt=cutoff_date,
            status__in=['completed', 'failed']
        ).delete()
    
    @staticmethod
    def cleanup_failed_records(hours: int = 24):
        """清理失败的数据获取记录"""
        cutoff_date = timezone.now() - timezone.timedelta(hours=hours)
        ExternalDataFetch.objects.filter(
            created_at__lt=cutoff_date,
            status='failed'
        ).delete() 