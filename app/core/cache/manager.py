from django.core.cache import caches
from django.conf import settings
from functools import wraps
import hashlib
import json
import inspect
from typing import Callable, Any, Union
from pathlib import Path
from django.core.cache.backends.redis import RedisCache
from django.core.cache.backends.filebased import FileBasedCache
from django.core.cache.backends.locmem import LocMemCache

class CacheManager:
    """缓存管理器"""
    
    def __init__(self, backend='default', timeout=None, key_prefix=None):
        self.backend = backend
        self.timeout = timeout or getattr(settings, 'CACHE_TIMEOUT', 300)
        self.key_prefix = key_prefix or getattr(settings, 'CACHE_KEY_PREFIX', '')
        self._cache = caches[backend]

    def get_file_hash(self, file_path: Union[str, Path]) -> str:
        """获取文件内容的哈希值"""
        path = Path(file_path)
        if not path.exists():
            return None
            
        with open(path, 'rb') as f:
            file_hash = hashlib.md5()
            # 分块读取大文件
            for chunk in iter(lambda: f.read(4096), b''):
                file_hash.update(chunk)
        return file_hash.hexdigest()

    def get_cache_key(self, *args, key_generator: Callable = None, **kwargs) -> str:
        """
        生成缓存键
        :param args: 函数参数
        :param key_generator: 自定义键生成函数
        :param kwargs: 函数关键字参数
        :return: 缓存键
        """
        if key_generator:
            # 使用自定义键生成器
            key = key_generator(*args, **kwargs)
        else:
            # 默认键生成策略
            args_str = json.dumps(args, sort_keys=True)
            kwargs_str = json.dumps(kwargs, sort_keys=True)
            key = hashlib.md5(f"{args_str}{kwargs_str}".encode()).hexdigest()
            
        return f"{self.key_prefix}{key}"

    def get(self, key, default=None):
        """获取缓存"""
        return self._cache.get(key, default)

    def set(self, key, value, timeout=None):
        """设置缓存"""
        timeout = timeout or self.timeout
        self._cache.set(key, value, timeout)

    def delete(self, key):
        """删除缓存"""
        self._cache.delete(key)

    def clear(self):
        """清除所有缓存"""
        self._cache.clear()

    def cached(self, timeout=None, key_prefix=None, key_generator=None):
        """
        缓存装饰器
        :param timeout: 缓存超时时间
        :param key_prefix: 键前缀
        :param key_generator: 自定义键生成函数
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # 生成缓存键
                if key_prefix:
                    cache_key = f"{key_prefix}_{self.get_cache_key(*args, key_generator=key_generator, **kwargs)}"
                else:
                    cache_key = f"{func.__name__}_{self.get_cache_key(*args, key_generator=key_generator, **kwargs)}"

                # 尝试获取缓存
                cached_value = self.get(cache_key)
                if cached_value is not None:
                    return cached_value

                # 执行函数
                result = func(*args, **kwargs)

                # 设置缓存
                self.set(cache_key, result, timeout or self.timeout)

                return result
            return wrapper
        return decorator 

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