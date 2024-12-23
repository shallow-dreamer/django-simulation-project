from django.db import models
from app.core.models import TimeStampedModel

class ExternalPlatform(TimeStampedModel):
    """外部平台配置"""
    name = models.CharField(max_length=100, verbose_name="平台名称")
    api_key = models.CharField(max_length=255, verbose_name="API密钥")
    api_secret = models.CharField(max_length=255, verbose_name="API密钥")
    base_url = models.URLField(verbose_name="API基础URL")
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    
    class Meta:
        verbose_name = "外部平台"
        verbose_name_plural = verbose_name

class ExternalDataFetch(TimeStampedModel):
    """外部数据获取记录"""
    platform = models.ForeignKey(
        ExternalPlatform,
        on_delete=models.PROTECT,
        related_name='data_fetches',
        verbose_name="平台"
    )
    data_type = models.CharField(max_length=50, verbose_name="数据类型")
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', '待处理'),
            ('processing', '获取中'),
            ('completed', '已完成'),
            ('failed', '失败')
        ],
        default='pending',
        verbose_name="状态"
    )
    raw_data = models.JSONField(null=True, verbose_name="原始数据")
    processed_data = models.JSONField(null=True, verbose_name="处理后数据")
    error_message = models.TextField(blank=True, verbose_name="错误信息")
    
    class Meta:
        verbose_name = "数据获取记录"
        verbose_name_plural = verbose_name 