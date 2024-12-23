from django.db import models
from django.utils import timezone

class TimeStampedModel(models.Model):
    """
    抽象基类，提供创建时间和更新时间字段
    """
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        abstract = True

class FileModel(TimeStampedModel):
    """
    文件模型的抽象基类
    """
    file = models.FileField(upload_to='uploads/%Y/%m/%d/', verbose_name="文件")
    file_name = models.CharField(max_length=255, verbose_name="文件名")
    file_size = models.BigIntegerField(verbose_name="文件大小")
    file_type = models.CharField(max_length=50, verbose_name="文件类型")

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.file:
            self.file_name = self.file.name
            self.file_size = self.file.size
            self.file_type = self.file.name.split('.')[-1]
        super().save(*args, **kwargs) 

class TaskRecord(TimeStampedModel):
    """任务执行记录"""
    task_id = models.CharField(max_length=255, unique=True, verbose_name="Celery任务ID")
    name = models.CharField(max_length=255, verbose_name="任务名称")
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', '等待中'),
            ('started', '执行中'),
            ('success', '成功'),
            ('failure', '失败'),
            ('revoked', '已取消'),
        ],
        default='pending',
        verbose_name="状态"
    )
    input_data = models.JSONField(verbose_name="输入数据")
    output_data = models.JSONField(null=True, verbose_name="输出数据")
    runtime_data = models.JSONField(default=dict, verbose_name="运行时数据")
    error_message = models.TextField(blank=True, verbose_name="错误信息")
    started_at = models.DateTimeField(null=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, verbose_name="完成时间")
    
    class Meta:
        verbose_name = "任务记录"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=['task_id']),
            models.Index(fields=['status']),
        ] 