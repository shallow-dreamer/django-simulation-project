from celery import shared_task
from django.utils import timezone
from app.core.decorators import MonitoredTask
from .sync import DataSyncService
from .models import ExternalPlatform

@shared_task(bind=True, base=MonitoredTask)
def sync_platform_data(self, platform_id: int, data_type: str, params: Dict = None):
    """同步指定平台的数据"""
    platform = ExternalPlatform.objects.get(id=platform_id)
    sync_service = DataSyncService(platform)
    return sync_service.sync_data(data_type, params)

@shared_task(bind=True, base=MonitoredTask)
def sync_all_platforms_data(self, data_type: str, params: Dict = None):
    """同步所有平台的数据"""
    return DataSyncService.sync_all_platforms(data_type, params)

@shared_task
def schedule_platform_sync():
    """调度平台数据同步"""
    for platform in ExternalPlatform.objects.filter(is_active=True):
        sync_platform_data.delay(
            platform.id,
            'daily_data',
            {'date': timezone.now().date().isoformat()}
        ) 