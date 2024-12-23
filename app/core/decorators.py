from functools import wraps
from celery import Task
from django.utils import timezone
from .services import TaskMonitorService
from django.core.cache import cache
from django.conf import settings
import hashlib
import json
from rest_framework.response import Response
from rest_framework.request import Request
from typing import Callable, Any

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

def cache_result(cache_key: str, timeout: int = None):
    """缓存结果装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            key_parts = [
                settings.CACHE_KEY_PREFIX,
                cache_key,
                func.__name__,
                hashlib.md5(
                    json.dumps((args, kwargs), sort_keys=True).encode()
                ).hexdigest()
            ]
            cache_key_final = '_'.join(key_parts)
            
            # 尝试从缓存获取
            result = cache.get(cache_key_final)
            if result is not None:
                return result
            
            # 执行函数
            result = func(*args, **kwargs)
            
            # 设置缓存
            timeout_value = timeout or settings.CACHE_TIMEOUTS.get(cache_key, 300)
            cache.set(cache_key_final, result, timeout=timeout_value)
            
            return result
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