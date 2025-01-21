from django.core.cache.backends.redis import RedisCache
from django.core.cache.backends.filebased import FileBasedCache
from django.core.cache.backends.locmem import LocMemCache
from typing import List, Any

class CustomRedisCache(RedisCache):
    """自定义Redis缓存后端"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 添加自定义功能

    def get_many(self, keys):
        """批量获取缓存"""
        return super().get_many(keys)

    def get_many_by_pattern(self, pattern: str) -> dict:
        """使用模式匹配获取多个缓存"""
        client = self._client
        keys = client.keys(pattern)
        if not keys:
            return {}
        return {k.decode(): self.get(k) for k in keys}
    
    def delete_many_by_pattern(self, pattern: str) -> int:
        """使用模式匹配删除多个缓存"""
        client = self._client
        keys = client.keys(pattern)
        if not keys:
            return 0
        return client.delete(*keys)

    def get_or_set(self, key: str, default_func: callable, timeout=None) -> Any:
        """获取缓存，不存在则设置"""
        value = self.get(key)
        if value is None:
            value = default_func()
            self.set(key, value, timeout)
        return value

class CustomFileCache(FileBasedCache):
    """自定义文件缓存后端"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 添加自定义功能

    def get_many(self, keys):
        """批量获取缓存"""
        return super().get_many(keys)

    def get_or_create(self, key: str, creator_func: callable, timeout=None) -> Any:
        """获取或创建缓存"""
        value = self.get(key)
        if value is None:
            value = creator_func()
            self.set(key, value, timeout)
        return value
    
    def touch(self, key: str, timeout=None) -> bool:
        """更新缓存过期时间"""
        value = self.get(key)
        if value is not None:
            self.set(key, value, timeout)
            return True
        return False

class CustomMemoryCache(LocMemCache):
    """自定义内存缓存后端"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 添加自定义功能 

    def get_keys_with_prefix(self, prefix: str) -> List[str]:
        """获取指定前缀的所有键"""
        return [k for k in self._cache.keys() if k.startswith(prefix)]
    
    def clear_with_prefix(self, prefix: str) -> int:
        """清除指定前缀的所有缓存"""
        keys = self.get_keys_with_prefix(prefix)
        for key in keys:
            self.delete(key)
        return len(keys) 