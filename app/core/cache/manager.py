from django.core.cache import caches
from django.conf import settings
from functools import wraps
import hashlib
import json
import inspect
from typing import Callable, Any, Union, List, Optional
from pathlib import Path
from django.core.cache.backends.redis import RedisCache
from django.core.cache.backends.filebased import FileBasedCache
from django.core.cache.backends.locmem import LocMemCache
from django.core.cache.backends import CustomFileCache
from app.core.cache.mixins import SubDirCacheMixin
import os
from .file_utils import FilePathHandler, FileHasher

class CacheManager:
    """缓存管理器"""
    
    def __init__(self, backend='default', timeout=None, key_prefix=None, sub_dirs=None):
        self.backend = backend
        self.timeout = timeout or getattr(settings, 'CACHE_TIMEOUT', 300)
        self.key_prefix = key_prefix or getattr(settings, 'CACHE_KEY_PREFIX', '')
        self.sub_dirs = sub_dirs
        self._cache = caches[backend]

    def get(self, key, default=None):
        """获取缓存"""
        if isinstance(self._cache, SubDirCacheMixin) and self.sub_dirs:
            return self._cache.get_with_sub_dirs(key, self.sub_dirs, default)
        return self._cache.get(key, default)

    def set(self, key, value, timeout=None):
        """设置缓存"""
        if isinstance(self._cache, SubDirCacheMixin) and self.sub_dirs:
            return self._cache.set_with_sub_dirs(key, value, self.sub_dirs, timeout or self.timeout)
        return self._cache.set(key, value, timeout or self.timeout)

    def delete(self, key):
        """删除缓存"""
        if isinstance(self._cache, SubDirCacheMixin) and self.sub_dirs:
            return self._cache.delete_with_sub_dirs(key, self.sub_dirs)
        return self._cache.delete(key)

    def clear(self):
        """清除所有缓存"""
        self._cache.clear()

    def clear_sub_dir(self):
        """清除子目录缓存"""
        if isinstance(self._cache, SubDirCacheMixin) and self.sub_dirs:
            return self._cache.clear_sub_dir(self.sub_dirs)

    def get_cache_key(self, *args, key_generator: Callable = None, **kwargs) -> str:
        """生成缓存键"""
        if key_generator:
            key = key_generator(*args, **kwargs)
        else:
            args_str = json.dumps(args, sort_keys=True)
            kwargs_str = json.dumps(kwargs, sort_keys=True)
            key = hashlib.md5(f"{args_str}{kwargs_str}".encode()).hexdigest()
        return f"{self.key_prefix}{key}"

    def cached(self, timeout=None, key_prefix=None, key_generator=None):
        """基本缓存装饰器"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                if key_prefix:
                    cache_key = f"{key_prefix}_{self.get_cache_key(*args, key_generator=key_generator, **kwargs)}"
                else:
                    cache_key = f"{func.__name__}_{self.get_cache_key(*args, key_generator=key_generator, **kwargs)}"
                
                cached_value = self.get(cache_key)
                if cached_value is not None:
                    return cached_value
                
                result = func(*args, **kwargs)
                self.set(cache_key, result, timeout)
                return result
            return wrapper
        return decorator

class FileCacheManager(CacheManager):
    """文件缓存管理器"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_handler = FilePathHandler()
        self.file_hasher = FileHasher()

    def get_file_paths(self, file_params, args=None, kwargs=None) -> List[str]:
        """获取文件路径列表"""
        return self.file_handler.get_paths(file_params, args, kwargs)

    def cache_with_files(
        self,
        file_paths: Union[str, List[str]],
        func: Callable,
        args: tuple = None,
        kwargs: dict = None
    ) -> Any:
        """使用文件内容进行缓存"""
        args = args or ()
        kwargs = kwargs or {}
        paths = [file_paths] if isinstance(file_paths, str) else file_paths
        
        files_hash = self.file_hasher.get_files_hash(paths)
        if not files_hash:
            return func(*args, **kwargs)
        
        cache_key = f"file_cache_{files_hash}"
        cached_value = self.get(cache_key)
        if cached_value is not None:
            return cached_value
        
        result = func(*args, **kwargs)
        self.set(cache_key, result)
        return result

    def get_file_hash(self, file_path: Union[str, Path]) -> Optional[str]:
        """获取文件内容的哈希值"""
        path = Path(file_path)
        if not path.exists():
            return None
            
        with open(path, 'rb') as f:
            file_hash = hashlib.md5()
            for chunk in iter(lambda: f.read(4096), b''):
                file_hash.update(chunk)
        return file_hash.hexdigest()

    def get_files_cache_key(self, file_paths: List[str]) -> Optional[str]:
        """生成基于文件内容的缓存键"""
        hashes = []
        for path in file_paths:
            file_hash = self.get_file_hash(path)
            if file_hash:
                hashes.append(file_hash)
        
        return f"file_cache_{'_'.join(hashes)}" if hashes else None

    def get_or_set(self, key: str, default_func: callable, timeout=None):
        """获取缓存，不存在则设置"""
        if isinstance(self._cache, RedisCache):
            return self._cache.get_or_set(key, default_func, timeout)
        
        value = self.get(key)
        if value is None:
            value = default_func()
            self.set(key, value, timeout)
        return value

    def delete_pattern(self, pattern: str) -> int:
        """删除匹配模式的缓存"""
        if isinstance(self._cache, RedisCache):
            return self._cache.delete_many_by_pattern(pattern)
        elif isinstance(self._cache, LocMemCache):
            return self._cache.clear_with_prefix(pattern)
        return 0

    def touch(self, key: str, timeout=None) -> bool:
        """更新缓存过期时间"""
        if isinstance(self._cache, FileBasedCache):
            return self._cache.touch(key, timeout)
        value = self.get(key)
        if value is not None:
            self.set(key, value, timeout)
            return True
        return False 