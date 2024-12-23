from app.core.decorators import cache_view_result
from rest_framework.parsers import MultiPartParser
from django.http import HttpResponse
import csv
import zipfile
from io import BytesIO
from celery import shared_task
from django.core.cache import cache

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

class SParameterViewSet(viewsets.ModelViewSet):
    # ...other code...

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

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser])
    def bulk_import(self, request):
        """批量导入S参数文件"""
        files = request.FILES.getlist('files')
        if not files:
            return Response({'error': '没有上传文件'}, status=400)
            
        results = []
        for file in files:
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
                
                results.append({
                    'file': file.name,
                    'status': 'success',
                    'id': parameter.id
                })
            except Exception as e:
                results.append({
                    'file': file.name,
                    'status': 'failed',
                    'error': str(e)
                })
        
        return Response({
            'total': len(files),
            'results': results
        })

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
                response = HttpResponse(file_data, content_type='application/zip')
                response['Content-Disposition'] = 'attachment; filename="s_parameters.zip"'
                # 清理缓存
                cache.delete(progress_key)
                cache.delete(file_key)
                return response
        
        return Response(progress)