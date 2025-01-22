from functools import wraps
from celery import Task
from django.utils import timezone

from .models import TaskRecord
from .services import TaskMonitorService
from django.core.cache import cache
from django.conf import settings
import hashlib
import json
from rest_framework.response import Response
from rest_framework.request import Request
from typing import Callable, Any, Union, List, Dict, Optional
from pathlib import Path
from .cache.manager import CacheManager
import os

class MonitoredTask(Task):
    """带监控的Celery任务基类"""
    
    def apply_async(self, *args, **kwargs):
        # 创建任务记录
        task_name = self.name or f"{self.__class__.__name__}"
        input_data = {
            'args': args,
            'kwargs': kwargs,
        }
        
        # 获取任务ID并创建记录
        task = super().apply_async(*args, **kwargs)
        TaskMonitorService.create_task_record(
            task_id=task.id,
            name=task_name,
            input_data=input_data
        )
        return task
    
    def on_success(self, retval, task_id, args, kwargs):
        """任务成功回调"""
        try:
            task_record = TaskRecord.objects.get(task_id=task_id)
            TaskMonitorService.update_task_status(
                task_record,
                'success',
                output_data=retval,
                finished_at=timezone.now()
            )
        except TaskRecord.DoesNotExist:
            pass
        
        super().on_success(retval, task_id, args, kwargs)
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败回调"""
        try:
            task_record = TaskRecord.objects.get(task_id=task_id)
            TaskMonitorService.update_task_status(
                task_record,
                'failure',
                error_message=str(exc),
                finished_at=timezone.now()
            )
        except TaskRecord.DoesNotExist:
            pass
        
        super().on_failure(exc, task_id, args, kwargs, einfo) 

def cache_result(backend='default', timeout=None, key_prefix=None, key_generator=None):
    """
    缓存结果装饰器
    :param backend: 缓存后端
    :param timeout: 超时时间
    :param key_prefix: 键前缀
    :param key_generator: 自定义键生成函数
    """
    cache_manager = CacheManager(backend=backend, timeout=timeout)
    return cache_manager.cached(timeout=timeout, key_prefix=key_prefix, key_generator=key_generator)

def cache_method_result(backend='default', timeout=None):
    """缓存方法结果装饰器（用于类方法）"""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # 使用类名和方法名作为键前缀
            key_prefix = f"{self.__class__.__name__}_{func.__name__}"
            cache_manager = CacheManager(backend=backend, timeout=timeout)
            cached_func = cache_manager.cached(
                timeout=timeout, 
                key_prefix=key_prefix
            )(func)
            return cached_func(self, *args, **kwargs)
        return wrapper
    return decorator

def cache_view_result(cache_key: str, timeout: int = None):
    """视图结果缓存装饰器"""
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(view_instance, request: Request, *args, **kwargs) -> Response:
            # 只缓存POST请求
            if request.method != 'POST':
                return view_func(view_instance, request, *args, **kwargs)
            
            # 生成缓存键
            cache_data = {
                'body': request.data,
                'user_id': request.user.id,
                'path': request.path,
                'args': args,
                'kwargs': kwargs
            }
            
            key_parts = [
                settings.CACHE_KEY_PREFIX,
                cache_key,
                view_func.__name__,
                hashlib.md5(
                    json.dumps(cache_data, sort_keys=True).encode()
                ).hexdigest()
            ]
            cache_key_final = '_'.join(key_parts)
            
            # 尝试从缓存获取
            cached_response = cache.get(cache_key_final)
            if cached_response is not None:
                return Response(cached_response)
            
            # 执行视图函数
            response = view_func(view_instance, request, *args, **kwargs)
            
            # 只缓存成功的响应
            if response.status_code == 200:
                timeout_value = timeout or settings.CACHE_TIMEOUTS.get(cache_key, 300)
                cache.set(cache_key_final, response.data, timeout=timeout_value)
            
            return response
        return wrapper
    return decorator

def file_based_cache(
    file_params: Union[str, int, List[Union[str, int]], Dict[str, str]], 
    backend='default', 
    timeout=None,
    sub_dirs: List[str] = None,
    path_join_func: Callable = None
):
    """文件缓存装饰器"""
    cache_manager = CacheManager(
        backend=backend,
        timeout=timeout,
        sub_dirs=sub_dirs
    )
    cache_manager.path_join_func = path_join_func

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 获取文件路径
            paths = cache_manager.get_file_paths(file_params, args, kwargs)
            if not paths:
                return func(*args, **kwargs)
            
            # 使用缓存管理器执行
            return cache_manager.cache_with_files(paths, func, args, kwargs)
        return wrapper

    return decorator