from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from app.core.models import TimeStampedModel

User = get_user_model()

class Collection(TimeStampedModel):
    """通用收藏模型"""
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='collections',
        verbose_name="用户"
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    is_deleted = models.BooleanField(default=False, verbose_name="是否已移除")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="移除时间")
    
    class Meta:
        verbose_name = "收藏"
        verbose_name_plural = verbose_name
        unique_together = ['user', 'content_type', 'object_id']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['user', 'is_deleted']),
        ] 