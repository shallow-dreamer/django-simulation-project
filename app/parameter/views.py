from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.core.files import File
from django.core.cache import cache
from django.conf import settings

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser

import hashlib
import tempfile
from pathlib import Path
import os
from django.utils import timezone

from .models import SParameter, Simulation
from .serializers import SParameterSerializer, SimulationSerializer
from .services import (
    SParameterProcessor, 
    SParameterAnalyzer,
    SimulationService,
    RetryManager
)
from .validators import SParameterValidator
from app.core.decorators import cache_view_result, cache_result, cache_method_result, file_based_cache
from .tasks import generate_parameter_export, run_simulation
from app.core.cache import CacheManager

class SParameterViewSet(viewsets.ModelViewSet):
    queryset = SParameter.objects.all()
    serializer_class = SParameterSerializer
    parser_classes = [MultiPartParser]
    validator_class = SParameterValidator()

    def get_queryset(self):
        """增加查询过滤功能"""
        queryset = super().get_queryset()
        if self.request.query_params.get('name'):
            queryset = queryset.filter(name__icontains=self.request.query_params['name'])
        if self.request.query_params.get('created_after'):
            queryset = queryset.filter(created_at__gte=self.request.query_params['created_after'])
        return queryset

    @action(detail=True, methods=['post'])
    @cache_view_result('parameter_analysis')
    def analyze(self, request, pk=None):
        """分析S参数"""
        instance = self.get_object()
        analyzer = SParameterAnalyzer(instance.get_data()['data_points'])
        
        analysis_type = request.data.get('type')
        port = request.data.get('port')
        
        if analysis_type == 'return_loss':
            result = analyzer.get_return_loss(port)
        elif analysis_type == 'insertion_loss':
            port2 = request.data.get('port2')
            result = analyzer.get_insertion_loss(port, port2)
        elif analysis_type == 'vswr':
            result = analyzer.get_vswr(port)
        else:
            return Response({'error': '不支持的分析类型'}, status=400)
            
        return Response({
            'type': analysis_type,
            'data': result
        }) 

    @action(detail=False, methods=['post'])
    def bulk_import(self, request):
        """批量导入S参数文件"""
        files = request.FILES.getlist('files')
        if not files:
            return Response({'error': '没有上传文件'}, status=400)
            
        # 添加文件格式预校验
        validator = self.validator_class()
        invalid_files = []
        for file in files:
            if not validator.is_valid_format(file):
                invalid_files.append(file.name)
        
        if invalid_files:
            return Response({
                'error': '文件格式无效',
                'invalid_files': invalid_files
            }, status=400)

        # 保持原有导入逻辑不变...
        results = []
        total_files = len(files)
        
        for index, file in enumerate(files, 1):
            try:
                # 创建S参数记录
                parameter = SParameter.objects.create(
                    name=file.name,
                    file=file,
                    user=request.user
                )
                
                # 处理文件
                processor = SParameterProcessor(parameter)
                processor.process()
                
                # 添加进度信息
                progress = (index / total_files) * 100
                results.append({
                    'file': file.name,
                    'status': 'success',
                    'id': parameter.id,
                    'progress': progress
                })
                
                # 缓存当前进度
                cache.set(
                    f'import_progress_{request.user.id}',
                    {'current': index, 'total': total_files, 'progress': progress},
                    timeout=3600
                )
                
            except Exception as e:
                results.append({
                    'file': file.name,
                    'status': 'failed',
                    'error': str(e),
                    'progress': progress
                })
        
        return Response({
            'total': total_files,
            'results': results
        })

    @action(detail=False, methods=['get'])
    def import_progress(self, request):
        """获取导入进度"""
        progress = cache.get(f'import_progress_{request.user.id}')
        if not progress:
            return Response({'error': '未找到导入任务'}, status=404)
        return Response(progress)

    @action(detail=False, methods=['post'])
    def bulk_export(self, request):
        """批量导出S参数文件"""
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'error': '未指定要导出的文件'}, status=400)
        
        # 启动导出任务
        task = generate_parameter_export.delay(ids, request.user.id)
        
        return Response({
            'task_id': task.id,
            'status': 'accepted'
        })
    
    @action(detail=False, methods=['get'])
    def export_progress(self, request):
        """获取导出进度"""
        progress_key = f"export_progress_{request.user.id}"
        progress = cache.get(progress_key)
        
        if not progress:
            return Response({'error': '未找到导出任务'}, status=404)
        
        if progress['status'] == 'completed':
            # 获取文件
            file_key = f"export_file_{request.user.id}"
            file_data = cache.get(file_key)
            
            if file_data:
                # 使用 default_storage 保存并获取下载 URL
                temp_file_path = f'temp/exports/s_parameters_{request.user.id}.zip'
                default_storage.save(temp_file_path, ContentFile(file_data))
                
                download_url = default_storage.url(temp_file_path)
                
                # 清理缓存
                cache.delete(progress_key)
                cache.delete(file_key)
                
                return Response({
                    'status': 'completed',
                    'download_url': download_url
                })
        
        return Response(progress)

    @action(detail=True, methods=['get'])
    def validate(self, request, pk=None):
        """验证单个S参数文件"""
        instance = self.get_object()
        validation_result = self.validator_class.validate_file(instance.file_path)
        return Response(validation_result)

    @action(detail=True, methods=['post'])
    def retry_processing(self, request, pk=None):
        """重试失败的文件处理"""
        instance = self.get_object()
        try:
            processor = SParameterProcessor(instance)
            processor.process()
            return Response({'status': 'success'})
        except Exception as e:
            return Response({
                'status': 'failed',
                'error': str(e)
            }, status=400)

    @action(detail=False, methods=['post'])
    def initiate_upload(self, request):
        """初始化大文件上传"""
        file_name = request.data.get('fileName')
        file_size = request.data.get('fileSize')
        chunk_size = request.data.get('chunkSize', 1024 * 1024)  # 默认1MB

        if not all([file_name, file_size]):
            return Response({
                'error': '缺少必要参数'
            }, status=400)

        # 生成上传ID
        upload_id = hashlib.md5(f"{file_name}{file_size}{request.user.id}".encode()).hexdigest()
        
        # 计算分片数量
        total_chunks = (file_size + chunk_size - 1) // chunk_size
        
        # 创建临时目录路径
        temp_dir = f'temp/{upload_id}'
        if not default_storage.exists(temp_dir):
            default_storage.makedirs(temp_dir)
        
        # 保存上传信息到缓存
        cache.set(f'upload_{upload_id}', {
            'file_name': file_name,
            'file_size': file_size,
            'chunk_size': chunk_size,
            'total_chunks': total_chunks,
            'uploaded_chunks': [],
            'user_id': request.user.id,
            'temp_dir': temp_dir
        }, timeout=86400)  # 24小时过期
        
        return Response({
            'uploadId': upload_id,
            'totalChunks': total_chunks,
            'chunkSize': chunk_size
        })

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser])
    def upload_chunk(self, request):
        """上传文件分片"""
        upload_id = request.data.get('uploadId')
        chunk_index = request.data.get('chunkIndex')
        chunk_file = request.FILES.get('chunk')
        
        if not all([upload_id, chunk_index is not None, chunk_file]):
            return Response({
                'error': '缺少必要参数'
            }, status=400)
            
        upload_info = cache.get(f'upload_{upload_id}')
        if not upload_info:
            return Response({
                'error': '上传会话已过期'
            }, status=400)
            
        # 验证用户权限
        if upload_info['user_id'] != request.user.id:
            return Response({
                'error': '无权访问此上传会话'
            }, status=403)
            
        # 保存分片
        chunk_index = int(chunk_index)
        chunk_path = f"{upload_info['temp_dir']}/chunk_{chunk_index}"
        
        # 使用 default_storage 保存分片
        default_storage.save(chunk_path, ContentFile(chunk_file.read()))
                
        # 更新上传进度
        upload_info['uploaded_chunks'].append(chunk_index)
        cache.set(f'upload_{upload_id}', upload_info, timeout=86400)
        
        progress = len(upload_info['uploaded_chunks']) / upload_info['total_chunks'] * 100
        
        return Response({
            'uploaded': True,
            'progress': progress
        })

    @action(detail=False, methods=['post'])
    def complete_upload(self, request):
        """完成文件上传"""
        upload_id = request.data.get('uploadId')
        if not upload_id:
            return Response({
                'error': '缺少上传ID'
            }, status=400)
            
        upload_info = cache.get(f'upload_{upload_id}')
        if not upload_info:
            return Response({
                'error': '上传会话已过期'
            }, status=400)
            
        # 验证所有分片是否都已上传
        if len(upload_info['uploaded_chunks']) != upload_info['total_chunks']:
            return Response({
                'error': '文件未完整上传',
                'missing_chunks': list(set(range(upload_info['total_chunks'])) - 
                                    set(upload_info['uploaded_chunks']))
            }, status=400)
            
        try:
            # 创建临时文件进行合并
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                # 合并所有分片
                for i in range(upload_info['total_chunks']):
                    chunk_path = f"{upload_info['temp_dir']}/chunk_{i}"
                    chunk_content = default_storage.open(chunk_path).read()
                    temp_file.write(chunk_content)
                
                temp_file.flush()
                
                # 创建最终文件路径
                final_path = f"uploads/{upload_info['file_name']}"
                
                # 将临时文件保存到存储中
                with open(temp_file.name, 'rb') as f:
                    default_storage.save(final_path, File(f))
                        
            # 创建S参数记录
            parameter = SParameter.objects.create(
                name=upload_info['file_name'],
                file=final_path,
                user=request.user
            )
            
            # 获取文件URL
            file_url = self.get_file_url(final_path)
            
            # 清理临时文件
            default_storage.delete_directory(upload_info['temp_dir'])
            
            # 清理缓存
            cache.delete(f'upload_{upload_id}')
            
            # 删除本地临时文件
            Path(temp_file.name).unlink()
            
            return Response({
                'status': 'success',
                'id': parameter.id,
                'file_url': file_url
            })
            
        except Exception as e:
            return Response({
                'error': f'合并文件失败: {str(e)}'
            }, status=500)

    @action(detail=False, methods=['get'])
    def upload_status(self, request):
        """获取上传状态"""
        upload_id = request.query_params.get('uploadId')
        if not upload_id:
            return Response({
                'error': '缺少上传ID'
            }, status=400)
            
        upload_info = cache.get(f'upload_{upload_id}')
        if not upload_info:
            return Response({
                'error': '上传会话不存在或已过期'
            }, status=404)
            
        if upload_info['user_id'] != request.user.id:
            return Response({
                'error': '无权访问此上传会话'
            }, status=403)
            
        progress = len(upload_info['uploaded_chunks']) / upload_info['total_chunks'] * 100
        
        return Response({
            'fileName': upload_info['file_name'],
            'fileSize': upload_info['fileSize'],
            'totalChunks': upload_info['total_chunks'],
            'uploadedChunks': upload_info['uploaded_chunks'],
            'progress': progress
        })

    def get_file_url(self, file_path):
        """获取文件的访问URL"""
        if default_storage.exists(file_path):
            return default_storage.url(file_path)
        return None

    def retrieve(self, request, *args, **kwargs):
        """重写获取详情方法，添加文件URL"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data
        
        # 添加文件URL
        if instance.file:
            data['file_url'] = self.get_file_url(instance.file.name)
            
        return Response(data)

    @action(detail=True, methods=['get'])
    def download_results(self, request, pk=None):
        """下载仿真结果"""
        simulation = self.get_object()
        
        if not simulation.result_file:
            return Response({
                'error': '仿真结果不存在'
            }, status=404)
        
        # 获取文件URL
        file_url = default_storage.url(simulation.result_file.name)
        
        return Response({
            'download_url': file_url
        })

    @action(detail=True, methods=['post'])
    def retry_simulation(self, request, pk=None):
        """手动重试仿真"""
        simulation = self.get_object()
        retry_manager = RetryManager()
        
        if retry_manager.handle_retry(simulation):
            return Response({'status': 'retry scheduled'})
        else:
            return Response({
                'error': 'Maximum retry attempts reached or simulation not failed'
            }, status=400)

    @action(detail=True, methods=['get'])
    def simulation_status(self, request, pk=None):
        """获取仿真状态"""
        simulation = self.get_object()
        return Response({
            'status': simulation.status,
            'retry_count': simulation.retry_count,
            'error_message': simulation.error_message if simulation.status == 'failed' else None,
            'created_at': simulation.created_at,
            'updated_at': simulation.updated_at
        })

    @action(detail=True, methods=['get'])
    @cache_result(backend='redis', timeout=3600)
    def get_analysis(self, request, pk=None):
        """获取分析结果（使用装饰器缓存）"""
        instance = self.get_object()
        result = self.analyze_data(instance)
        return Response(result)

    @action(detail=True, methods=['get'])
    @cache_result(
        backend='redis',
        timeout=3600,
        key_generator=lambda *args, **kwargs: f"custom_key_{kwargs.get('pk')}"
    )
    def get_custom_cache(self, request, pk=None):
        instance = self.get_object()
        result = self.process_data(instance)
        return Response(result)

    @action(detail=False, methods=['post'])
    @file_based_cache(
        file_params='file_path',
        backend='file',
        timeout=3600,
        sub_dirs=['user_data', 'parameters']
    )
    def process_file(self, request):
        file_path = request.data.get('file_path')
        result = self.process_single_file(file_path)
        return Response(result)

    @action(detail=False, methods=['post'])
    @file_based_cache(file_params=0)  # 第一个参数是文件路径
    def process_file_by_position(self, file_path, other_param):
        pass
    
    @action(detail=False, methods=['post'])
    @file_based_cache(file_params=['base_path', 'filename'])
    def process_file_with_parts(self, base_path, filename):
        pass
    
    @action(detail=False, methods=['post'])
    @file_based_cache(
        file_params={
            'base_dir': 'path',
            'sub_dir': 'path',
            'filename': 'name'
        }
    )
    def process_complex_path(self, base_dir, sub_dir, filename):
        pass
    
    @action(detail=False, methods=['post'])
    @file_based_cache(
        file_params=['path', 'name'],
        path_join_func=lambda path, name: f"{path}/{name}.txt"
    )
    def process_custom_path(self, path, name):
        pass
    
    @action(detail=False, methods=['post'])
    @file_based_cache(
        file_params={
            'base_path': 'path',
            'year': 'path',
            'month': 'path',
            'filename': 'name'
        },
        backend='file',
        timeout=3600
    )
    def process_dated_file(self, request):
        base_path = request.data.get('base_path')
        year = request.data.get('year')
        month = request.data.get('month')
        filename = request.data.get('filename')
        
        # 处理文件
        result = self.process_file_content(
            os.path.join(base_path, year, month, filename)
        )
        return Response(result)

    @action(detail=False, methods=['post'])
    def clear_cache(self, request):
        """清理指定模式的缓存"""
        pattern = request.data.get('pattern', '')
        cache_manager = CacheManager(backend='default')
        deleted_count = cache_manager.delete_pattern(pattern)
        return Response({
            'deleted_count': deleted_count
        })

    @action(detail=True, methods=['post'])
    def extend_cache(self, request, pk=None):
        """延长缓存时间"""
        instance = self.get_object()
        cache_manager = CacheManager(backend='file')
        cache_key = f"parameter_data_{instance.id}"
        
        if cache_manager.touch(cache_key, timeout=7200):
            return Response({'status': 'extended'})
        return Response({'status': 'not_found'}, status=404)

    @action(detail=False, methods=['post'])
    def process_multiple_files(self, request):
        """处理多个文件并单独缓存结果"""
        file_list = request.data.get('files', [])
        
        # 使用支持子目录的文件缓存
        cache_manager = CacheManager(
            backend='file',  # 使用扩展的文件缓存后端
            timeout=3600,
            sub_dirs=[f'user_{request.user.id}', 'parameter_data']
        )
        
        results = {}
        for file_info in file_list:
            file_path = str(file_info)
            file_hash = cache_manager.get_file_hash(file_path)
            if not file_hash:
                continue
            
            cache_key = f"file_result_{file_hash}"
            cached_result = cache_manager.get(cache_key)
            
            if cached_result is not None:
                results[file_path] = cached_result
                continue
            
            result = self.process_single_file(file_path)
            cache_manager.set(cache_key, result)
            results[file_path] = result
        
        return Response(results)

    @action(detail=False, methods=['post'])
    def clear_user_cache(self, request):
        """清理用户的缓存数据"""
        sub_dirs = [f'user_{request.user.id}']
        cache_manager = CacheManager(
            backend='file',
            sub_dirs=sub_dirs
        )
        cache_manager.clear_sub_dir()
        return Response({'status': 'cleared'})

    def process_single_file(self, file_path: str) -> dict:
        """处理单个文件的具体逻辑"""
        # 这里是实际的文件处理逻辑
        with open(file_path, 'r') as f:
            content = f.read()
            # 进行处理...
            result = {
                'file_size': os.path.getsize(file_path),
                'processed_data': content[:100],  # 示例处理
                'timestamp': timezone.now().isoformat()
            }
        return result

@shared_task
def run_simulation(simulation_id: int, parameters: dict):
    """运行仿真任务"""
    try:
        with SimulationService(simulation_id) as sim:
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
            simulation = Simulation.objects.get(id=simulation_id)
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