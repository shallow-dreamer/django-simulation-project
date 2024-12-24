from django.db import models
from django.contrib.auth import get_user_model

class Simulation(models.Model):
    STATUS_CHOICES = (
        ('pending', '等待中'),
        ('processing', '处理中'),
        ('completed', '已完成'),
        ('failed', '失败'),
    )

    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    result_file = models.FileField(upload_to='simulations/', null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    parameters = models.JSONField()  # 存储仿真参数
    retry_count = models.IntegerField(default=0)  # 重试次数
    expires_at = models.DateTimeField(null=True)  # 结果过期时间 

class SParameterHistory(models.Model):
    """S参数处理历史记录"""
    parameter = models.ForeignKey(SParameter, on_delete=models.CASCADE)
    processing_type = models.CharField(max_length=50)
    processed_data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at'] 

class SParameter(models.Model):
    """S参数模型"""
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='s_parameters/')
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_data(self):
        """获取处理后的数据"""
        latest_history = self.sparameterhistory_set.filter(
            processing_type='parse'
        ).first()
        return latest_history.processed_data if latest_history else None

    class Meta:
        ordering = ['-created_at'] 