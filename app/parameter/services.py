from django.core.cache import cache
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils import timezone
from django.conf import settings
import json
import tempfile
from pathlib import Path
import zipfile
from datetime import datetime, timedelta
from tempfile import TemporaryDirectory, NamedTemporaryFile

from app.core.services import ProcessingService
from .models import SParameter, SParameterHistory, Simulation

class SParameterProcessor(ProcessingService):
    """S参数处理服务"""
    def __init__(self, parameter: SParameter):
        super().__init__()
        self.parameter = parameter

    def process(self, **kwargs) -> dict:
        try:
            # 读取文件内容
            with self.parameter.file.open('r') as f:
                content = f.read()
            
            # 解析S参数数据
            parsed_data = self._parse_touchstone(content)
            
            # 创建处理历史记录
            history = SParameterHistory.objects.create(
                parameter=self.parameter,
                processing_type='parse',
                processed_data=parsed_data
            )
            
            return parsed_data
        except Exception as e:
            self.add_error(f"处理S参数文件失败: {str(e)}")
            raise

    def _parse_touchstone(self, content: str) -> dict:
        """解析Touchstone格式文件"""
        lines = content.strip().split('\n')
        header = None
        data_points = []
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('!'): 
                continue
            
            if line.startswith('#'):
                # 解析头部信息
                header = self._parse_header(line)
                continue
            
            # 解析数据点
            values = [float(v) for v in line.split()]
            data_points.append({
                'frequency': values[0],
                'values': values[1:]
            })
        
        return {
            'header': header,
            'data_points': data_points,
            'num_ports': self._calculate_num_ports(data_points[0]['values'])
        }

    def _parse_header(self, line: str) -> dict:
        """解析头部信息"""
        parts = line[1:].strip().split()
        return {
            'unit': parts[0],
            'parameter_type': parts[1],
            'format': parts[2],
            'r': float(parts[3]) if len(parts) > 3 else 50.0
        }

    def _calculate_num_ports(self, values: list) -> int:
        """根据数据点计算端口数"""
        return int((len(values) / 2) ** 0.5)

class SParameterDataService:
    """S参数数据服务"""
    def __init__(self, parameter: SParameter):
        self.parameter = parameter
        self._data_cache = None
    
    @property
    def data(self) -> dict:
        """获取数据(带缓存)"""
        if self._data_cache is None:
            cache_key = f"s_parameter_data_{self.parameter.id}"
            self._data_cache = cache.get(cache_key)
            
            if self._data_cache is None:
                self._data_cache = self._load_data()
                cache.set(cache_key, self._data_cache, timeout=3600)
        
        return self._data_cache
    
    def _load_data(self) -> dict:
        """加载数据"""
        with self.parameter.file.open('r') as f:
            content = f.read()
            
        # 解析数据
        data = self._parse_touchstone(content)
        
        # 预计算常用值
        self._precompute_common_values(data)
        
        return data
    
    def _precompute_common_values(self, data: dict):
        """预计算常用值"""
        # 计算每个端口的回波损耗
        data['return_loss'] = {}
        for port in range(data['num_ports']):
            data['return_loss'][port] = self._calculate_return_loss(data, port)
        
        # 计算插入损耗矩阵
        data['insertion_loss'] = {}
        for port1 in range(data['num_ports']):
            for port2 in range(data['num_ports']):
                if port1 != port2:
                    key = f"{port1}_{port2}"
                    data['insertion_loss'][key] = self._calculate_insertion_loss(
                        data, port1, port2
                    )

class SParameterAnalyzer:
    def __init__(self, data_points):
        self.data_points = data_points

    def get_return_loss(self, port):
        # 实现返回损耗分析
        pass

    def get_insertion_loss(self, port1, port2):
        # 实现插入损耗分析
        pass

    def get_vswr(self, port):
        # 实现驻波比分析
        pass

class RetryManager:
    def __init__(self, max_retries=3, delay=5):
        self.max_retries = max_retries
        self.delay = delay

    def should_retry(self, simulation):
        """判断是否应该重试"""
        return (simulation.status == 'failed' and 
                simulation.retry_count < self.max_retries)

    def handle_retry(self, simulation):
        """处理重试逻辑"""
        if self.should_retry(simulation):
            simulation.retry_count += 1
            simulation.status = 'pending'
            simulation.save()
            # 延迟重试
            run_simulation.apply_async(
                args=[simulation.id, simulation.parameters],
                countdown=self.delay * simulation.retry_count
            )
            return True
        return False

class SimulationService:
    def __init__(self, simulation_id):
        self.simulation_id = simulation_id
        self._temp_dir = None
        self.files_to_pack = []
        self.retry_manager = RetryManager()

    def __enter__(self):
        """使用 TemporaryDirectory 上下文管理器"""
        self._temp_dir = TemporaryDirectory()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """自动清理临时目录"""
        if self._temp_dir:
            self._temp_dir.cleanup()

    def save_plot(self, name: str, figure=None):
        """保存图表到临时文件"""
        if figure is None:
            figure = plt.gcf()
        
        file_path = Path(self._temp_dir.name) / f"{name}.png"
        figure.savefig(file_path)
        plt.close(figure)
        
        self.files_to_pack.append(('plots', file_path))
        return file_path

    def save_text(self, name: str, content: str):
        """保存文本到临时文件"""
        file_path = Path(self._temp_dir.name) / f"{name}.txt"
        file_path.write_text(content, encoding='utf-8')
        
        self.files_to_pack.append(('texts', file_path))
        return file_path

    def save_data(self, name: str, data: dict):
        """保存数据到临时JSON文件"""
        file_path = Path(self._temp_dir.name) / f"{name}.json"
        file_path.write_text(json.dumps(data, indent=2), encoding='utf-8')
        
        self.files_to_pack.append(('data', file_path))
        return file_path

    def create_result_package(self) -> str:
        """创建结果压缩包"""
        # 使用 NamedTemporaryFile 创建临时 ZIP 文件
        with NamedTemporaryFile(suffix='.zip', delete=False) as temp_zip:
            with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # 添加文件到 ZIP
                for category, file_path in self.files_to_pack:
                    archive_path = f"{category}/{file_path.name}"
                    zip_file.write(file_path, archive_path)
                
                # 添加元数据
                metadata = {
                    'simulation_id': self.simulation_id,
                    'file_count': len(self.files_to_pack),
                    'categories': list(set(cat for cat, _ in self.files_to_pack)),
                    'files': [
                        {
                            'category': cat,
                            'name': path.name,
                            'size': path.stat().st_size
                        }
                        for cat, path in self.files_to_pack
                    ]
                }
                zip_file.writestr('metadata.json', json.dumps(metadata, indent=2))

        try:
            # 读取临时 ZIP 文件并保存到存储
            zip_path = f"simulations/simulation_{self.simulation_id}_results.zip"
            with open(temp_zip.name, 'rb') as f:
                default_storage.save(zip_path, ContentFile(f.read()))
            
            return zip_path
        finally:
            # 清理临时 ZIP 文件
            Path(temp_zip.name).unlink(missing_ok=True)

    def handle_error(self, error_message):
        """处理错误"""
        simulation = Simulation.objects.get(id=self.simulation_id)
        simulation.status = 'failed'
        simulation.error_message = error_message
        simulation.save()
        
        # 尝试重试
        self.retry_manager.handle_retry(simulation)