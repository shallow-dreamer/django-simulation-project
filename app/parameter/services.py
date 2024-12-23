from app.core.services import ProcessingService
from .models import SParameter, SParameterHistory
from django.core.cache import cache

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