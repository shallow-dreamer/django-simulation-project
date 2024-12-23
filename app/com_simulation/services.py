from app.core.services import ProcessingService
from .models import ComSimulation
from .parameters import SimulationParameters
import numpy as np

class ComSimulationProcessor(ProcessingService):
    """Com仿真处理服务"""
    def __init__(self, simulation: ComSimulation):
        super().__init__()
        self.simulation = simulation

    def pre_process(self, **kwargs) -> bool:
        """仿真前的准备工作"""
        if not self.simulation.s_parameter:
            self.add_error("缺少S参数文件")
            return False
        return True

    def process(self, **kwargs) -> dict:
        """执行Com仿真"""
        try:
            # 验证参数
            params = SimulationParameters(
                frequency_range=(kwargs.get('start_freq'), kwargs.get('end_freq')),
                port_mapping=kwargs.get('port_mapping', {}),
                settings=kwargs.get('settings', {})
            )
            errors = params.validate()
            if errors:
                for error in errors:
                    self.add_error(error)
                return None

            # 更新状态
            self.simulation.status = self.status
            self.simulation.save()
            
            # 执行仿真
            result_data = self._run_simulation(params)
            
            # 处理结果
            processed_result = self._process_result(result_data)
            
            # 保存结果
            self.simulation.result_data = processed_result
            self.simulation.status = 'completed'
            self.simulation.save()
            
            return processed_result
        except Exception as e:
            self.simulation.status = 'failed'
            self.simulation.error_message = str(e)
            self.simulation.save()
            raise

    def _process_result(self, result_data: dict) -> dict:
        """处理仿真结果"""
        # 添加结果验证
        if not result_data.get('success'):
            self.add_error(result_data.get('error', '仿真失败'))
            return None
            
        # 添加结果分析
        analysis = {
            'max_value': max(result_data.get('values', [])),
            'min_value': min(result_data.get('values', [])),
            'average': sum(result_data.get('values', [])) / len(result_data.get('values', [1])),
        }
        
        return {
            **result_data,
            'analysis': analysis
        }

    def post_process(self, result: dict) -> dict:
        """仿真后的清理和数据整理工作"""
        # 可以在这里添加结果验证、数据转换等逻辑
        return result 

    def _run_simulation(self, params: SimulationParameters) -> dict:
        """执行仿真计算"""
        try:
            # 获取S参数数据
            s_param_data = self.simulation.s_parameter.get_data()
            
            # 验证端口映射
            port_mapping = params.port_mapping
            if not all(port in s_param_data['ports'] for port in port_mapping.values()):
                self.add_error("端口映射无效")
                return None
            
            # 执行仿真计算
            result = {
                'simulation_type': 'com',
                'parameter_id': self.simulation.s_parameter.id,
                'port_results': {},
                'success': True
            }
            
            # 对每个端口对执行计算
            for name, port in port_mapping.items():
                port_result = self._calculate_port(
                    s_param_data,
                    port,
                    params.frequency_range,
                    params.settings
                )
                result['port_results'][name] = port_result
            
            return result
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _calculate_port(self, s_param_data: dict, port: int, freq_range: tuple, settings: dict) -> dict:
        """计算单个端口的结果"""
        try:
            # 提取频率范围内的数据
            start_freq, end_freq = freq_range
            freq_mask = np.logical_and(
                s_param_data['frequencies'] >= start_freq,
                s_param_data['frequencies'] <= end_freq
            )
            
            frequencies = s_param_data['frequencies'][freq_mask]
            port_data = s_param_data['s_parameters'][freq_mask, port, :]
            
            # 应用设置参数
            sample_rate = settings.get('sample_rate', 1e9)
            bit_rate = settings.get('bit_rate', 1e9)
            
            # 生成时域响应
            time_data = self._generate_time_response(
                frequencies,
                port_data,
                sample_rate,
                bit_rate
            )
            
            # 分析眼图
            analyzer = ComAnalyzer({
                'sample_rate': sample_rate,
                'bit_rate': bit_rate
            })
            eye_params = analyzer.analyze_eye_diagram(time_data)
            
            return {
                'port': port,
                'time_data': time_data.tolist(),
                'eye_params': {
                    'height': eye_params.height,
                    'width': eye_params.width,
                    'jitter': eye_params.jitter,
                    'crossing': eye_params.crossing_percentage
                }
            }
        except Exception as e:
            self.add_error(f"端口{port}计算失败: {str(e)}")
            return None

    def _generate_time_response(self, frequencies: np.ndarray, s_parameters: np.ndarray,
                              sample_rate: float, bit_rate: float) -> np.ndarray:
        """生成时域响应"""
        # 设置时域参数
        num_bits = 1000  # 模拟比特数
        samples_per_bit = int(sample_rate / bit_rate)
        total_samples = num_bits * samples_per_bit
        
        # 生成PRBS序列
        prbs_seq = self._generate_prbs_sequence(num_bits)
        
        # 生成基带信号
        time = np.arange(total_samples) / sample_rate
        baseband = np.repeat(prbs_seq, samples_per_bit)
        
        # 频域转换
        freq_response = np.zeros(total_samples//2 + 1, dtype=complex)
        freq_points = np.fft.rfftfreq(total_samples, 1/sample_rate)
        
        # 插值S参数到所需频点
        interpolated_s = np.interp(freq_points, frequencies, s_parameters)
        
        # 应用信道响应
        signal_fft = np.fft.rfft(baseband)
        output_fft = signal_fft * interpolated_s
        
        # 转回时域
        time_signal = np.fft.irfft(output_fft)
        
        return time_signal

    def _generate_prbs_sequence(self, length: int) -> np.ndarray:
        """生成PRBS序列"""
        # 使用PRBS-7生成器
        register = np.ones(7, dtype=int)
        sequence = np.zeros(length, dtype=int)
        
        for i in range(length):
            sequence[i] = register[-1]
            feedback = register[0] ^ register[6]
            register[1:] = register[:-1]
            register[0] = feedback
        
        return 2 * sequence - 1  # 转换为±1序列