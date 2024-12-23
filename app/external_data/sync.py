from typing import Dict, Any, List
from django.db import transaction
from django.utils import timezone
from app.core.events import EventManager, Events
from .models import ExternalPlatform, ExternalDataFetch
from .factories import PlatformAdapterFactory

class DataSyncService:
    """数据同步服务"""
    
    def __init__(self, platform: ExternalPlatform):
        self.platform = platform
        self.adapter = PlatformAdapterFactory.get_adapter(platform)
    
    def sync_data(self, data_type: str, params: Dict = None) -> Dict[str, Any]:
        """同步指定类型的数据"""
        try:
            with transaction.atomic():
                # 获取数据
                data = self.adapter.fetch_data(f"/{data_type}", params)
                
                # 发布同步完成事件
                EventManager.publish(
                    Events.DATA_FETCHED,
                    sender=self,
                    platform=self.platform,
                    data_type=data_type,
                    data=data
                )
                
                return data
        except Exception as e:
            # 发布同步失败事件
            EventManager.publish(
                Events.PROCESSING_FAILED,
                sender=self,
                platform=self.platform,
                data_type=data_type,
                error=str(e)
            )
            raise

    @classmethod
    def sync_all_platforms(cls, data_type: str, params: Dict = None) -> List[Dict[str, Any]]:
        """同步所有启用的平台数据"""
        results = []
        for platform in ExternalPlatform.objects.filter(is_active=True):
            try:
                sync_service = cls(platform)
                result = sync_service.sync_data(data_type, params)
                results.append({
                    'platform': platform.name,
                    'status': 'success',
                    'data': result
                })
            except Exception as e:
                results.append({
                    'platform': platform.name,
                    'status': 'error',
                    'error': str(e)
                })
        return results 