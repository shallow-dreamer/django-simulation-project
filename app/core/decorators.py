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
from typing import Callable, Any, Union, List, Dict
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
    """
    基于文件内容的缓存装饰器
    :param file_params: 文件参数配置，支持多种格式：
        - str: 单个参数名
        - int: 单个位置参数索引
        - List[Union[str, int]]: 多个参数，将被拼接
        - Dict[str, str]: 键为参数名，值为参数类型('path'/'name')
    :param backend: 缓存后端
    :param timeout: 超时时间
    :param sub_dirs: 子目录列表
    :param path_join_func: 自定义路径拼接函数
    """
    cache_manager = CacheManager(
        backend=backend,
        timeout=timeout,
        sub_dirs=sub_dirs
    )
    
    def get_file_paths(args, kwargs) -> List[str]:
        """获取所有文件路径"""
        paths = []
        
        if isinstance(file_params, (str, int)):
            # 单个参数
            path = _get_single_path(file_params, args, kwargs)
            if path:
                paths.append(path)
                
        elif isinstance(file_params, list):
            # 多个参数需要拼接
            path_parts = []
            for param in file_params:
                part = _get_single_path(param, args, kwargs)
                if part:
                    path_parts.append(part)
            
            if path_parts:
                # 使用自定义拼接函数或默认的 os.path.join
                join_func = path_join_func or os.path.join
                paths.append(join_func(*path_parts))
                
        elif isinstance(file_params, dict):
            # 复杂的路径配置
            path_parts = {'path': [], 'name': []}
            for param, param_type in file_params.items():
                value = _get_single_path(param, args, kwargs)
                if value:
                    path_parts[param_type].append(value)
            
            # 拼接路径
            if path_parts['path'] or path_parts['name']:
                base_path = os.path.join(*path_parts['path']) if path_parts['path'] else ''
                filename = os.path.join(*path_parts['name']) if path_parts['name'] else ''
                if base_path and filename:
                    paths.append(os.path.join(base_path, filename))
                elif base_path:
                    paths.append(base_path)
                elif filename:
                    paths.append(filename)
        
        return paths
    
    def _get_single_path(param, args, kwargs) -> str:
        """获取单个路径参数"""
        if isinstance(param, int) and len(args) > param:
            return str(args[param])
        elif isinstance(param, str) and param in kwargs:
            return str(kwargs[param])
        return None

    def key_generator(*args, **kwargs):
        """基于文件内容生成缓存键"""
        file_paths = get_file_paths(args, kwargs)
        if not file_paths:
            return None
            
        # 计算所有文件的组合哈希
        hashes = []
        for path in file_paths:
            file_hash = cache_manager.get_file_hash(path)
            if file_hash:
                hashes.append(file_hash)
                
        if not hashes:
            return None
            
        # 组合多个哈希
        return '_'.join(hashes)

    return cache_manager.cached(
        timeout=timeout,
        key_generator=key_generator
    )