from dataclasses import dataclass
from typing import List, Dict, Optional
import numpy as np
from scipy import signal

@dataclass
class EyeDiagramParams:
    """眼图参数"""
    height: float  # 眼高
    width: float   # 眼宽
    jitter: float  # 抖动
    crossing_percentage: float  # 交叉点位置

class ComAnalyzer:
    """COM分析器"""
    def __init__(self, simulation_data: Dict):
        self.data = simulation_data
        self.sample_rate = simulation_data.get('sample_rate', 1e9)
        self.bit_rate = simulation_data.get('bit_rate', 1e9)
        
    def analyze_eye_diagram(self, signal_data: List[float]) -> EyeDiagramParams:
        """分析眼图参数"""
        # 重采样到每个UI的固定点数
        samples_per_ui = int(self.sample_rate / self.bit_rate)
        num_uis = len(signal_data) // samples_per_ui
        
        # 重构眼图数据
        eye_data = np.reshape(signal_data[:num_uis * samples_per_ui], 
                            (num_uis, samples_per_ui))
        
        # 计算眼图参数
        height = np.max(eye_data) - np.min(eye_data)
        width = self._calculate_eye_width(eye_data)
        jitter = self._calculate_jitter(eye_data)
        crossing = self._find_crossing_percentage(eye_data)
        
        return EyeDiagramParams(
            height=height,
            width=width,
            jitter=jitter,
            crossing_percentage=crossing
        )
    
    def _calculate_eye_width(self, eye_data: np.ndarray) -> float:
        """计算眼宽"""
        # 找到眼图的中心位置
        center_idx = eye_data.shape[1] // 2
        threshold = (np.max(eye_data) + np.min(eye_data)) / 2
        
        # 计算每个UI的交叉点
        crossings = []
        for row in eye_data:
            # 寻找上升沿和下降沿的交叉点
            for i in range(1, len(row)):
                if (row[i-1] < threshold and row[i] >= threshold) or \
                   (row[i-1] >= threshold and row[i] < threshold):
                    crossings.append(i)
        
        if not crossings:
            return 0.0
        
        # 计算抖动范围
        min_crossing = min(crossings)
        max_crossing = max(crossings)
        
        # 转换为UI单位
        ui_width = 1.0 - (max_crossing - min_crossing) / eye_data.shape[1]
        return max(0.0, ui_width)
    
    def _calculate_jitter(self, eye_data: np.ndarray) -> float:
        """计算抖动"""
        threshold = (np.max(eye_data) + np.min(eye_data)) / 2
        crossings = []
        
        # 对每个UI寻找交叉点
        for row in eye_data:
            row_crossings = []
            for i in range(1, len(row)):
                if (row[i-1] < threshold and row[i] >= threshold) or \
                   (row[i-1] >= threshold and row[i] < threshold):
                    # 使用线性插值获取更精确的交叉点位置
                    x1, x2 = i-1, i
                    y1, y2 = row[i-1], row[i]
                    crossing = x1 + (threshold - y1) * (x2 - x1) / (y2 - y1)
                    row_crossings.append(crossing)
            if row_crossings:
                crossings.extend(row_crossings)
        
        if not crossings:
            return 0.0
        
        # 计算交叉点的标准差作为抖动指标
        return np.std(crossings)
    
    def _find_crossing_percentage(self, eye_data: np.ndarray) -> float:
        """计算交叉点位置"""
        # 计算垂直方向的直方图
        hist, bins = np.histogram(eye_data.flatten(), bins=100)
        
        # 找到两个主要的电平
        peaks = signal.find_peaks(hist)[0]
        if len(peaks) < 2:
            return 0.0
        
        low_level = bins[peaks[0]]
        high_level = bins[peaks[-1]]
        
        # 计算交叉点位置
        crossing_level = (high_level - low_level) * 0.5 + low_level
        return (crossing_level - low_level) / (high_level - low_level) * 100