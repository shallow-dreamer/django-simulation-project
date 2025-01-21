from django.core.cache.backends.redis import RedisCache
from django.core.cache.backends.filebased import FileBasedCache
from django.core.cache.backends.locmem import LocMemCache
from typing import List, Any
import os
from pathlib import Path

# 方案一：自定义缓存后端
class CustomRedisCache(RedisCache):
    """自定义Redis缓存后端 - 方案一"""
    
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
    """自定义文件缓存后端 - 方案一"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 添加自定义功能

    def make_sub_dir_key(self, key: str, sub_dirs: list = None) -> str:
        """
        生成包含子目录的缓存键
        :param key: 原始键
        :param sub_dirs: 子目录列表，如 ['user_1', 'data_type_2']
        :return: 新的缓存键路径
        """
        if not sub_dirs:
            return key
            
        # 确保子目录存在
        current_dir = Path(self._dir)
        for sub_dir in sub_dirs:
            current_dir = current_dir / str(sub_dir)
            current_dir.mkdir(parents=True, exist_ok=True)
            
        # 返回完整路径
        return str(current_dir / key)

    def get_with_sub_dirs(self, key: str, sub_dirs: list = None, default=None):
        """在子目录中获取缓存"""
        full_key = self.make_sub_dir_key(key, sub_dirs)
        return super().get(full_key, default)

    def set_with_sub_dirs(self, key: str, value, sub_dirs: list = None, timeout=None):
        """在子目录中设置缓存"""
        full_key = self.make_sub_dir_key(key, sub_dirs)
        return super().set(full_key, value, timeout)

    def delete_with_sub_dirs(self, key: str, sub_dirs: list = None):
        """在子目录中删除缓存"""
        full_key = self.make_sub_dir_key(key, sub_dirs)
        return super().delete(full_key)

    def clear_sub_dir(self, sub_dirs: list):
        """清除指定子目录的所有缓存"""
        if not sub_dirs:
            return
            
        dir_path = Path(self._dir)
        for sub_dir in sub_dirs:
            dir_path = dir_path / str(sub_dir)
            
        if dir_path.exists():
            for cache_file in dir_path.glob('*'):
                if cache_file.is_file():
                    cache_file.unlink()

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
    """自定义内存缓存后端 - 方案一"""
    
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


# 方案二：使用混入类扩展原生后端
from .mixins import SubDirCacheMixin

class SubDirFileBasedCache(SubDirCacheMixin, FileBasedCache):
    """支持子目录的文件缓存 - 方案二"""
    pass

class SubDirRedisCache(SubDirCacheMixin, RedisCache):
    """支持子目录的Redis缓存 - 方案二"""
    pass

class SubDirLocMemCache(SubDirCacheMixin, LocMemCache):
    """支持子目录的内存缓存 - 方案二"""
    pass 