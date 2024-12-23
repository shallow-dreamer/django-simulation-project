from django.db import models
from app.core.models import TimeStampedModel
from app.parameter.models import SParameter

class FomChiCalculation(TimeStampedModel):
    """Fom_chi计算"""
    name = models.CharField(max_length=100, verbose_name="计算名称")
    description = models.TextField(blank=True, verbose_name="描述")
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', '待处理'),
            ('processing', '处理中'),
            ('completed', '已完成'),
            ('failed', '失败')
        ],
        default='pending',
        verbose_name="状态"
    )
    s_parameter = models.ForeignKey(
        SParameter,
        on_delete=models.PROTECT,
        related_name='fom_chi_calculations',
        verbose_name="S参数文件"
    )
    result_data = models.JSONField(null=True, verbose_name="计算结果")
    
    class Meta:
        verbose_name = "Fom_chi计算"
        verbose_name_plural = verbose_name 