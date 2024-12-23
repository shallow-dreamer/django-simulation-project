from typing import Any, Type
from django.db import models
from django.core.files.base import File
from celery.result import AsyncResult
from .models import TaskRecord

class BaseService:
    """基础服务类"""
    def __init__(self):
        self._errors = []

    @property
    def errors(self):
        return self._errors

    def add_error(self, error):
        self._errors.append(error)

    def has_errors(self):
        return len(self._errors) > 0

class FileService(BaseService):
    """文件处理服务"""
    def handle_file_upload(self, file: File, model_class: Type[models.Model], **kwargs) -> models.Model:
        """通用文件上传处理"""
        try:
            # 添加进度回调
            total_size = file.size
            uploaded_size = 0
            
            def upload_callback(chunk_size):
                nonlocal uploaded_size
                uploaded_size += chunk_size
                if self.progress_callback:
                    progress = (uploaded_size / total_size) * 100
                    self.progress_callback(uploaded_size, total_size, f"已上传 {progress:.1f}%")
            
            instance = model_class(file=file, **kwargs)
            instance.save()
            
            return instance
        except Exception as e:
            self.add_error(f"文件上传失败: {str(e)}")
            raise

class ProcessingService(BaseService):
    """数据处理服务基类"""
    def __init__(self):
        super().__init__()
        self.status = 'pending'
        self.progress_callback = None
    
    def pre_process(self, **kwargs) -> bool:
        """处理前的准备工作"""
        return True

    def process(self, **kwargs) -> Any:
        """
        数据处理抽象方法
        子类必须实现此方法
        """
        raise NotImplementedError

    def post_process(self, result: Any) -> Any:
        """处理后的清理工作"""
        return result

    def execute(self, progress_callback=None, **kwargs):
        """执行完整的处理流程"""
        self.progress_callback = progress_callback
        try:
            if not self.pre_process(**kwargs):
                return None
            
            self.status = 'processing'
            if self.progress_callback:
                self.progress_callback(0, 100, "开始处理")
                
            result = self.process(**kwargs)
            self.status = 'completed'
            
            if self.progress_callback:
                self.progress_callback(100, 100, "处理完成")
                
            return self.post_process(result)
        except Exception as e:
            self.status = 'failed'
            self.add_error(str(e))
            raise

class TaskMonitorService(BaseService):
    """任务监控服务"""
    
    @staticmethod
    def create_task_record(task_id: str, name: str, input_data: dict) -> TaskRecord:
        """创建任务记录"""
        return TaskRecord.objects.create(
            task_id=task_id,
            name=name,
            input_data=input_data
        )
    
    @staticmethod
    def update_task_status(task_record: TaskRecord, status: str, **kwargs):
        """更新任务状态"""
        task_record.status = status
        for key, value in kwargs.items():
            setattr(task_record, key, value)
        task_record.save()
    
    @staticmethod
    def get_task_info(task_id: str) -> dict:
        """获取任务信息"""
        result = AsyncResult(task_id)
        task_record = TaskRecord.objects.get(task_id=task_id)
        
        return {
            'task_id': task_id,
            'status': result.status,
            'result': result.result if result.successful() else None,
            'error': str(result.result) if result.failed() else None,
            'runtime_data': task_record.runtime_data,
            'started_at': task_record.started_at,
            'finished_at': task_record.finished_at,
        }

class DataConsistencyService:
    """数据一致性检查服务"""
    def check_simulation_consistency(self):
        """检查仿真数据一致性"""
        # 检查悬空引用
        dangling_sims = ComSimulation.objects.filter(
            s_parameter__isnull=True
        ).update(status='invalid')
        
        # 检查文件完整性
        for sim in ComSimulation.objects.filter(status='completed'):
            if not sim.s_parameter.file:
                sim.status = 'invalid'
                sim.save()
        
        # 检查结果数据完整性
        for sim in ComSimulation.objects.filter(status='completed'):
            if not self._validate_result_data(sim.result_data):
                sim.status = 'invalid'
                sim.save()
    
    def check_parameter_consistency(self):
        """检查S参数数据一致性"""
        for param in SParameter.objects.all():
            # 检查文件存在性
            if not param.file:
                param.status = 'invalid'
                param.save()
                continue
            
            # 检查数据完整性
            try:
                data = param.get_data()
                validator = SParameterValidator(data)
                if not validator.validate():
                    param.status = 'invalid'
                    param.save()
            except Exception:
                param.status = 'invalid'
                param.save()