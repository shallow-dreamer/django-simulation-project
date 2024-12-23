from django.db import models
from django.utils import timezone
from datetime import timedelta
from typing import Optional

class SyncMonitor(models.Model):
    """同步监控记录"""
    platform = models.ForeignKey('ExternalPlatform', on_delete=models.CASCADE)
    sync_type = models.CharField(max_length=50)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True)
    status = models.CharField(max_length=20)
    records_processed = models.IntegerField(default=0)
    errors = models.JSONField(default=list)
    
    class Meta:
        indexes = [
            models.Index(fields=['platform', 'sync_type']),
            models.Index(fields=['start_time']),
        ]

class SyncMetrics:
    """同步指标计算"""
    def __init__(self, platform_id: int):
        self.platform_id = platform_id
    
    def get_success_rate(self, days: int = 7) -> float:
        """计算成功率"""
        cutoff = timezone.now() - timedelta(days=days)
        total = SyncMonitor.objects.filter(
            platform_id=self.platform_id,
            start_time__gte=cutoff
        ).count()
        
        if not total:
            return 0.0
            
        success = SyncMonitor.objects.filter(
            platform_id=self.platform_id,
            start_time__gte=cutoff,
            status='completed'
        ).count()
        
        return (success / total) * 100
    
    def get_average_duration(self, days: int = 7) -> timedelta:
        """计算平均同步时长"""
        cutoff = timezone.now() - timedelta(days=days)
        records = SyncMonitor.objects.filter(
            platform_id=self.platform_id,
            start_time__gte=cutoff,
            end_time__isnull=False
        )
        
        if not records:
            return timedelta()
            
        total_duration = sum(
            (r.end_time - r.start_time).total_seconds() 
            for r in records
        )
        return timedelta(seconds=total_duration / records.count()) 

class SyncMonitorService:
    """同步监控服务"""
    def __init__(self):
        self.metrics = {}
        self.alerts = []

    def update_metrics(self, platform_id: int):
        """更新监控指标"""
        metrics = SyncMetrics(platform_id)
        self.metrics[platform_id] = {
            'success_rate': metrics.get_success_rate(),
            'avg_duration': metrics.get_average_duration(),
            'last_sync': self._get_last_sync(platform_id),
            'error_count': self._get_error_count(platform_id)
        }
        self._check_alerts(platform_id)

    def _get_last_sync(self, platform_id: int) -> Optional[datetime]:
        """获取最后同步时间"""
        last_sync = SyncMonitor.objects.filter(
            platform_id=platform_id,
            status='completed'
        ).order_by('-end_time').first()
        return last_sync.end_time if last_sync else None

    def _get_error_count(self, platform_id: int) -> int:
        """获取错误次数"""
        return SyncMonitor.objects.filter(
            platform_id=platform_id,
            status='failed',
            start_time__gte=timezone.now() - timedelta(hours=24)
        ).count()

    def _check_alerts(self, platform_id: int):
        """检查告警条件"""
        metrics = self.metrics[platform_id]
        
        # 检查成功率
        if metrics['success_rate'] < 90:
            self.alerts.append({
                'platform_id': platform_id,
                'type': 'success_rate',
                'message': f"同步成功率低于90%: {metrics['success_rate']}%"
            })
        
        # 检查错误次数
        if metrics['error_count'] > 5:
            self.alerts.append({
                'platform_id': platform_id,
                'type': 'error_count',
                'message': f"24小时内失败次数过多: {metrics['error_count']}"
            })
        
        # 检查最后同步时间
        if metrics['last_sync']:
            hours_since_last_sync = (timezone.now() - metrics['last_sync']).total_seconds() / 3600
            if hours_since_last_sync > 24:
                self.alerts.append({
                    'platform_id': platform_id,
                    'type': 'sync_delay',
                    'message': f"同步延迟超过24小时: {hours_since_last_sync:.1f}小时"
                })