import numpy as np
from typing import List, Dict, Tuple
from dataclasses import dataclass

@dataclass
class FrequencyPoint:
    frequency: float
    s_parameters: np.ndarray  # 复数矩阵

class SParameterAnalyzer:
    """S参数分析器"""
    def __init__(self, data_points: List[Dict]):
        self.frequency_points = self._convert_data_points(data_points)
        
    def _convert_data_points(self, data_points: List[Dict]) -> List[FrequencyPoint]:
        """转换数据点为频率点对象"""
        points = []
        for point in data_points:
            values = point['values']
            num_ports = int(np.sqrt(len(values) // 2))
            s_matrix = np.zeros((num_ports, num_ports), dtype=complex)
            
            for i in range(num_ports):
                for j in range(num_ports):
                    idx = 2 * (i * num_ports + j)
                    s_matrix[i, j] = complex(values[idx], values[idx + 1])
            
            points.append(FrequencyPoint(
                frequency=point['frequency'],
                s_parameters=s_matrix
            ))
        return points
    
    def get_return_loss(self, port: int) -> List[Tuple[float, float]]:
        """获取指定端口的回波损耗"""
        return [
            (point.frequency, -20 * np.log10(abs(point.s_parameters[port, port])))
            for point in self.frequency_points
        ]
    
    def get_insertion_loss(self, port1: int, port2: int) -> List[Tuple[float, float]]:
        """获取两个端口间的插入损耗"""
        return [
            (point.frequency, -20 * np.log10(abs(point.s_parameters[port1, port2])))
            for point in self.frequency_points
        ]
    
    def get_impedance(self, port: int, z0: float = 50.0) -> List[Tuple[float, complex]]:
        """计算指定端口的阻抗"""
        return [
            (point.frequency, z0 * (1 + point.s_parameters[port, port]) / 
                                 (1 - point.s_parameters[port, port]))
            for point in self.frequency_points
        ] 
    
    def get_group_delay(self, port1: int, port2: int) -> List[Tuple[float, float]]:
        """计算群延时"""
        phase_data = []
        for point in self.frequency_points:
            phase = np.angle(point.s_parameters[port1, port2])
            phase_data.append((point.frequency, phase))
        
        # 计算相位差分
        group_delay = []
        for i in range(1, len(phase_data)):
            f1, p1 = phase_data[i-1]
            f2, p2 = phase_data[i]
            
            # 处理相位包裹
            phase_diff = p2 - p1
            if phase_diff > np.pi:
                phase_diff -= 2 * np.pi
            elif phase_diff < -np.pi:
                phase_diff += 2 * np.pi
                
            delay = -phase_diff / (2 * np.pi * (f2 - f1))
            group_delay.append((f2, delay))
        
        return group_delay
    
    def get_vswr(self, port: int) -> List[Tuple[float, float]]:
        """计算电压驻波比"""
        return [
            (point.frequency, (1 + abs(point.s_parameters[port, port])) /
                             (1 - abs(point.s_parameters[port, port])))
            for point in self.frequency_points
        ]
    
    def get_stability_factor(self) -> List[Tuple[float, float]]:
        """计算稳定性因子 (K-factor)"""
        k_factors = []
        for point in self.frequency_points:
            s = point.s_parameters
            if s.shape[0] != 2:  # 只适用于二端口网络
                continue
            
            s11 = s[0, 0]
            s12 = s[0, 1]
            s21 = s[1, 0]
            s22 = s[1, 1]
            
            delta = s11 * s22 - s12 * s21
            k = (1 - abs(s11)**2 - abs(s22)**2 + abs(delta)**2) / (2 * abs(s12 * s21))
            k_factors.append((point.frequency, k))
        
        return k_factors