from django.db import models
from app.core.models import TimeStampedModel, FileModel

class SParameter(FileModel):
    """S参数文件模型"""
    description = models.TextField(blank=True, verbose_name="描述")
    frequency_range = models.CharField(max_length=100, verbose_name="频率范围")
    
    class Meta:
        verbose_name = "S参数文件"
        verbose_name_plural = verbose_name

    def save_new_version(self, file, user, comment=''):
        """保存新版本"""
        # 获取当前最大版本号
        latest = self.history.order_by('-version').first()
        new_version = (latest.version + 1) if latest else 1
        
        # 创建历史记录
        history = SParameterHistory.objects.create(
            parameter=self,
            version=new_version,
            file=file,
            created_by=user,
            comment=comment
        )
        
        # 更新当前文件
        self.file = file
        self.save()
        
        return history

class SParameterHistory(models.Model):
    """S参数历史记录"""
    parameter = models.ForeignKey('SParameter', on_delete=models.CASCADE)
    version = models.IntegerField()
    file = models.FileField(upload_to='s_parameters/history/')
    data = models.JSONField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)
    comment = models.TextField(blank=True)
    
    class Meta:
        unique_together = ['parameter', 'version']
        ordering = ['-version'] 