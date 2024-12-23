from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from app.core.services import BaseService
from .models import Collection

class CollectionService(BaseService):
    """收藏服务"""
    
    @staticmethod
    def add_to_collection(user, obj):
        """添加到收藏"""
        content_type = ContentType.objects.get_for_model(obj)
        collection, created = Collection.objects.get_or_create(
            user=user,
            content_type=content_type,
            object_id=obj.id,
            defaults={'is_deleted': False}
        )
        if not created and collection.is_deleted:
            collection.is_deleted = False
            collection.deleted_at = None
            collection.save()
        return collection

    @staticmethod
    def remove_from_collection(user, obj):
        """从收藏中移除"""
        content_type = ContentType.objects.get_for_model(obj)
        try:
            collection = Collection.objects.get(
                user=user,
                content_type=content_type,
                object_id=obj.id,
                is_deleted=False
            )
            collection.is_deleted = True
            collection.deleted_at = timezone.now()
            collection.save()
            return True
        except Collection.DoesNotExist:
            return False

    @staticmethod
    def get_user_collections(user, content_type=None):
        """获取用户的收藏列表"""
        collections = Collection.objects.filter(
            user=user,
            is_deleted=False
        )
        if content_type:
            collections = collections.filter(content_type=content_type)
        return collections 