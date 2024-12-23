from celery import shared_task
from typing import Any, Dict
from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from .models import TaskRecord
from .services import TaskMonitorService
from .decorators import MonitoredTask
from celery.exceptions import MaxRetriesExceededError

@shared_task(bind=True, base=MonitoredTask, max_retries=3, default_retry_delay=60)
def process_file_task(self, file_id: int, processor_class: str, model_path: str, **kwargs):
    """处理文件的任务"""
    task_record = TaskRecord.objects.get(task_id=self.request.id)
    TaskMonitorService.update_task_status(
        task_record,
        'started',
        started_at=timezone.now()
    )
    
    try:
        # 动态导入模型类和处理器类
        model_module_path, model_name = model_path.rsplit('.', 1)
        model_class = apps.get_model(model_module_path, model_name)
        
        module_path, class_name = processor_class.rsplit('.', 1)
        module = __import__(module_path, fromlist=[class_name])
        processor_class = getattr(module, class_name)
        
        # 获取文件实例
        instance = model_class.objects.get(id=file_id)
        
        # 初始化处理器并执行处理
        processor = processor_class(instance)
        
        # 记录处理进度
        def progress_callback(current, total, message=""):
            TaskMonitorService.update_task_status(
                task_record,
                'started',
                runtime_data={
                    'progress': (current / total) * 100,
                    'message': message
                }
            )
        
        # 执行处理
        result = processor.execute(progress_callback=progress_callback, **kwargs)
        
        return {
            'status': 'success',
            'result': result
        }
    except ObjectDoesNotExist as e:
        # 对象不存在不需要重试
        return {
            'status': 'error',
            'error': f'找不到ID为{file_id}的{model_path}实例'
        }
    except Exception as e:
        # 其他错误尝试重试
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            return {
                'status': 'error',
                'error': f'处理失败(重试次数已达上限): {str(e)}'
            }

@shared_task
def cleanup_task():
    """定期清理临时文件和过期数据的任务"""
    # 实现清理逻辑
    pass 

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def retry_task(self, func, *args, **kwargs):
    """带重试机制的任务包装器"""
    try:
        return func(*args, **kwargs)
    except Exception as exc:
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            # 记录最终失败
            raise 