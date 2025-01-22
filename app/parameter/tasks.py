# Django imports
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from django.conf import settings

# Python standard library
import csv
import json
from io import BytesIO
import zipfile
from datetime import timedelta

# Celery imports
from celery import shared_task

# Local imports
from .models import SParameter, Simulation
from .services import SimulationService

# 添加缺失的导入
import numpy as np
import matplotlib.pyplot as plt
from app.core.cache.manager import FileCacheManager

@shared_task
def generate_parameter_export(ids: list, user_id: int) -> str:
    """生成S参数导出文件的后台任务"""
    # 创建进度缓存键
    progress_key = f"export_progress_{user_id}"
    cache.set(progress_key, {'status': 'processing', 'progress': 0}, timeout=3600)
    
    try:
        # 创建ZIP文件
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            parameters = SParameter.objects.filter(id__in=ids)
            total = len(parameters)
            
            # 添加文件到ZIP
            for i, parameter in enumerate(parameters, 1):
                # 更新进度
                progress = (i / total) * 100
                cache.set(progress_key, {
                    'status': 'processing',
                    'progress': progress,
                    'current_file': parameter.name
                }, timeout=3600)
                
                # 添加原始文件
                zip_file.write(parameter.file.path, f'original/{parameter.name}')
                
                # 添加处理后的数据
                data = parameter.get_data()
                if data:
                    json_data = json.dumps(data, indent=2)
                    zip_file.writestr(f'processed/{parameter.name}.json', json_data)
            
            # 添加元数据CSV
            with BytesIO() as csv_buffer:
                writer = csv.writer(csv_buffer)
                writer.writerow(['ID', 'Name', 'Description', 'Created At'])
                for parameter in parameters:
                    writer.writerow([
                        parameter.id,
                        parameter.name,
                        parameter.description,
                        parameter.created_at.isoformat()
                    ])
                zip_file.writestr('metadata.csv', csv_buffer.getvalue())
        
        # 保存ZIP文件
        file_key = f"export_file_{user_id}"
        cache.set(file_key, zip_buffer.getvalue(), timeout=3600)
        cache.set(progress_key, {'status': 'completed', 'progress': 100}, timeout=3600)
        
        return file_key
    except Exception as e:
        cache.set(progress_key, {
            'status': 'failed',
            'error': str(e)
        }, timeout=3600)
        raise

@shared_task
def run_simulation(simulation_id: int, parameters: dict):
    """运行仿真任务"""
    try:
        with SimulationService(simulation_id) as sim:
            # 更新仿真状态
            simulation = Simulation.objects.get(id=simulation_id)
            simulation.status = 'processing'
            simulation.save()

            # 生成图表
            fig, ax = plt.subplots()
            x = np.linspace(0, 10, 100)
            y = np.sin(x)
            ax.plot(x, y)
            ax.set_title('Simulation Result')
            sim.save_plot('sine_wave', fig)
            
            # 保存文本结果
            sim.save_text('summary', 'Simulation completed successfully\nMax value: 1.0')
            
            # 保存数据
            sim.save_data('raw_data', {
                'x': x.tolist(),
                'y': y.tolist()
            })
            
            # 创建结果包
            result_path = sim.create_result_package()
            
            # 更新仿真记录
            simulation.result_file = result_path
            simulation.status = 'completed'
            simulation.save()
            
            return result_path
            
    except Exception as e:
        # 更新仿真状态为失败
        simulation = Simulation.objects.get(id=simulation_id)
        simulation.status = 'failed'
        simulation.error_message = str(e)
        simulation.save()
        raise

@shared_task
def cleanup_old_results():
    """清理过期的仿真结果"""
    # 获取过期时间设置
    expiry_days = getattr(settings, 'SIMULATION_RESULTS_EXPIRY_DAYS', 30)
    expiry_date = timezone.now() - timedelta(days=expiry_days)

    # 查找过期的仿真结果
    expired_simulations = Simulation.objects.filter(
        created_at__lt=expiry_date,
        status='completed'
    )

    for simulation in expired_simulations:
        # 删除结果文件
        if simulation.result_file:
            try:
                simulation.result_file.delete()
            except Exception as e:
                print(f"Error deleting file for simulation {simulation.id}: {e}")

        # 更新记录
        simulation.result_file = None
        simulation.save()

    return f"Cleaned up {expired_simulations.count()} simulation results"

@shared_task
def process_large_file(file_path: str):
    cache_manager = FileCacheManager(
        backend='file',
        timeout=86400,  # 24小时
        sub_dirs=['tasks', 'large_files']
    )
    
    def process_chunks(path):
        results = []
        with open(path, 'rb') as f:
            while chunk := f.read(8192):
                results.append(process_chunk(chunk))
        return results
    
    return cache_manager.cache_with_files(
        file_paths=file_path,
        func=process_chunks,
        args=(file_path,)
    ) 