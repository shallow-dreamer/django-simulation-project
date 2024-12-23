from rest_framework.response import Response
from rest_framework.request import Request
from typing import Callable, Any
import hashlib
import json
from io import BytesIO
from django.http import HttpResponse
import csv
import zipfile
from celery import shared_task
from django.core.cache import cache

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

@shared_task
def generate_simulation_export(ids: list, user_id: int) -> str:
    """生成仿真结果导出文件的后台任务"""
    progress_key = f"sim_export_progress_{user_id}"
    cache.set(progress_key, {'status': 'processing', 'progress': 0}, timeout=3600)
    
    try:
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            simulations = ComSimulation.objects.filter(id__in=ids)
            total = len(simulations)
            
            for i, simulation in enumerate(simulations, 1):
                # 更新进度
                progress = (i / total) * 100
                cache.set(progress_key, {
                    'status': 'processing',
                    'progress': progress,
                    'current_simulation': simulation.name
                }, timeout=3600)
                
                # 导出仿真参数
                params = {
                    'id': simulation.id,
                    'name': simulation.name,
                    'parameters': simulation.parameters,
                    'created_at': simulation.created_at.isoformat(),
                    'status': simulation.status
                }
                zip_file.writestr(
                    f'{simulation.id}/parameters.json',
                    json.dumps(params, indent=2)
                )
                
                # 导出仿真结果
                if simulation.result_data:
                    zip_file.writestr(
                        f'{simulation.id}/results.json',
                        json.dumps(simulation.result_data, indent=2)
                    )
                
                # 导出眼图分析结果
                if simulation.is_completed:
                    analyzer = ComAnalyzer(simulation.result_data)
                    for port in simulation.result_data.get('ports', []):
                        eye_params = analyzer.analyze_eye_diagram(
                            simulation.result_data['port_results'][port]['time_data']
                        )
                        zip_file.writestr(
                            f'{simulation.id}/eye_diagram_port_{port}.json',
                            json.dumps(eye_params.__dict__, indent=2)
                        )
            
            # 添加汇总CSV
            with BytesIO() as csv_buffer:
                writer = csv.writer(csv_buffer)
                writer.writerow([
                    'ID', 'Name', 'Status', 'Created At', 
                    'Completed At', 'Error Message'
                ])
                for simulation in simulations:
                    writer.writerow([
                        simulation.id,
                        simulation.name,
                        simulation.status,
                        simulation.created_at.isoformat(),
                        simulation.completed_at.isoformat() if simulation.completed_at else '',
                        simulation.error_message or ''
                    ])
                zip_file.writestr('summary.csv', csv_buffer.getvalue())
        
        # 保存ZIP文件
        file_key = f"sim_export_file_{user_id}"
        cache.set(file_key, zip_buffer.getvalue(), timeout=3600)
        cache.set(progress_key, {'status': 'completed', 'progress': 100}, timeout=3600)
        
        return file_key
    except Exception as e:
        cache.set(progress_key, {
            'status': 'failed',
            'error': str(e)
        }, timeout=3600)
        raise

class ComSimulationViewSet(viewsets.ModelViewSet):
    # ...其他代码...

    @action(detail=False, methods=['post'])
    @cache_view_result('simulation_result', timeout=3600)
    def simulate(self, request):
        """执行COM仿真"""
        serializer = ComSimulationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
            
        simulation = serializer.save(user=request.user)
        
        # 启动仿真任务
        task = run_simulation.delay(simulation.id)
        
        return Response({
            'simulation_id': simulation.id,
            'task_id': task.id,
            'status': 'accepted'
        })

    @action(detail=True, methods=['post'])
    @cache_view_result('eye_diagram_analysis')
    def analyze_eye(self, request, pk=None):
        """分析眼图"""
        simulation = self.get_object()
        if not simulation.is_completed:
            return Response({'error': '仿真尚未完成'}, status=400)
            
        analyzer = ComAnalyzer(simulation.result_data)
        port = request.data.get('port')
        
        eye_params = analyzer.analyze_eye_diagram(
            simulation.result_data['port_results'][port]['time_data']
        )
        
        return Response({
            'port': port,
            'eye_parameters': {
                'height': eye_params.height,
                'width': eye_params.width,
                'jitter': eye_params.jitter,
                'crossing': eye_params.crossing_percentage
            }
        })

    @action(detail=False, methods=['post'])
    def bulk_simulate(self, request):
        """批量创建仿真任务"""
        simulations = request.data.get('simulations', [])
        if not simulations:
            return Response({'error': '未提供仿真参数'}, status=400)
            
        results = []
        for sim_data in simulations:
            try:
                serializer = ComSimulationSerializer(data=sim_data)
                if serializer.is_valid():
                    simulation = serializer.save(user=request.user)
                    # 启动仿真任务
                    task = run_simulation.delay(simulation.id)
                    results.append({
                        'simulation_id': simulation.id,
                        'task_id': task.id,
                        'status': 'accepted'
                    })
                else:
                    results.append({
                        'data': sim_data,
                        'status': 'failed',
                        'errors': serializer.errors
                    })
            except Exception as e:
                results.append({
                    'data': sim_data,
                    'status': 'failed',
                    'error': str(e)
                })
        
        return Response({
            'total': len(simulations),
            'results': results
        })

    @action(detail=False, methods=['post'])
    def bulk_export(self, request):
        """批量导出仿真结果"""
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'error': '未指定要导出的仿真'}, status=400)
        
        # 启动导出任务
        task = generate_simulation_export.delay(ids, request.user.id)
        
        return Response({
            'task_id': task.id,
            'status': 'accepted'
        })
    
    @action(detail=False, methods=['get'])
    def export_progress(self, request):
        """获取导出进度"""
        progress_key = f"sim_export_progress_{request.user.id}"
        progress = cache.get(progress_key)
        
        if not progress:
            return Response({'error': '未找到导出任务'}, status=404)
        
        if progress['status'] == 'completed':
            # 获取文件
            file_key = f"sim_export_file_{request.user.id}"
            file_data = cache.get(file_key)
            
            if file_data:
                response = HttpResponse(file_data, content_type='application/zip')
                response['Content-Disposition'] = 'attachment; filename="simulations.zip"'
                # 清理缓存
                cache.delete(progress_key)
                cache.delete(file_key)
                return response
        
        return Response(progress)