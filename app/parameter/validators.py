from typing import List

class TouchstoneValidator:
    """Touchstone文件验证器"""
    def validate_frequency_range(self, data: dict) -> List[str]:
        errors = []
        if not data.get('data_points'):
            errors.append("数据点不能为空")
            return errors
            
        frequencies = [point['frequency'] for point in data['data_points']]
        if not frequencies:
            errors.append("频率数据不能为空")
            return errors
            
        if not all(frequencies[i] < frequencies[i+1] for i in range(len(frequencies)-1)):
            errors.append("频率必须单调递增")
            
        return errors

    def validate_port_data(self, data: dict) -> List[str]:
        errors = []
        num_ports = data.get('num_ports', 0)
        expected_values = num_ports * num_ports * 2  # 每个端口的实部和虚部
        
        for point in data.get('data_points', []):
            if len(point.get('values', [])) != expected_values:
                errors.append(f"数据点值的数量不正确，期望{expected_values}个值")
                break
                
        return errors 

class SParameterValidator:
    """S参数验证器"""
    def __init__(self, data: dict):
        self.data = data
        self.errors = []

    def validate(self) -> bool:
        """执行所有验证"""
        self._validate_structure()
        self._validate_frequencies()
        self._validate_port_consistency()
        self._validate_data_values()
        return len(self.errors) == 0

    def _validate_structure(self):
        """验证数据结构"""
        required_fields = ['header', 'data_points', 'num_ports']
        for field in required_fields:
            if field not in self.data:
                self.errors.append(f"缺少必要字段: {field}")

    def _validate_frequencies(self):
        """验证频率数据"""
        if not self.data.get('data_points'):
            return
            
        frequencies = [point['frequency'] for point in self.data['data_points']]
        if not frequencies:
            self.errors.append("频率数据不能为空")
            return
            
        # 检查频率单调性
        if not all(frequencies[i] < frequencies[i+1] for i in range(len(frequencies)-1)):
            self.errors.append("频率必须单调递增")
            
        # 检查频率范围
        if frequencies[0] < 0:
            self.errors.append("频率不能为负值")

    def _validate_port_consistency(self):
        """验证端口数据一致性"""
        num_ports = self.data.get('num_ports', 0)
        expected_values = num_ports * num_ports * 2  # 每个端口的实部和虚部
        
        for point in self.data.get('data_points', []):
            if len(point.get('values', [])) != expected_values:
                self.errors.append(f"数据点值的数量不正确，期望{expected_values}个值")
                break

    def _validate_data_values(self):
        """验证数据值的合理性"""
        for point in self.data.get('data_points', []):
            values = point.get('values', [])
            # S参数的幅度不应超过1
            for i in range(0, len(values), 2):
                magnitude = (values[i]**2 + values[i+1]**2)**0.5
                if magnitude > 1.1:  # 允许10%的误差
                    self.errors.append(f"S参数幅度异常: {magnitude}")
                    break 