from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class SimulationParameters:
    """仿真参数数据类"""
    frequency_range: tuple
    port_mapping: Dict[str, int]
    settings: Dict[str, Any]

    def validate(self) -> List[str]:
        """验证参数"""
        errors = []
        
        # 验证频率范围
        start_freq, end_freq = self.frequency_range
        if start_freq >= end_freq:
            errors.append("起始频率必须小于结束频率")
            
        # 验证端口映射
        if not self.port_mapping:
            errors.append("必须指定端口映射")
            
        # 验证设置
        required_settings = ['resolution', 'max_iterations']
        for setting in required_settings:
            if setting not in self.settings:
                errors.append(f"缺少必要的设置: {setting}")
                
        return errors 