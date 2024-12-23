from abc import ABC, abstractmethod
from typing import Dict, Any
from .services import ExternalDataService

class PlatformAdapter(ABC):
    """平台适配器基类"""
    
    def __init__(self, service: ExternalDataService):
        self.service = service
    
    @abstractmethod
    def transform_request(self, params: Dict) -> Dict:
        """转换请求参数"""
        pass
    
    @abstractmethod
    def transform_response(self, data: Dict) -> Dict:
        """转换响应数据"""
        pass
    
    def fetch_data(self, endpoint: str, params: Dict = None) -> Dict[str, Any]:
        """获取数据的通用流程"""
        transformed_params = self.transform_request(params or {})
        raw_data = self.service.fetch_data(endpoint, transformed_params)
        return self.transform_response(raw_data)

class Platform1Adapter(PlatformAdapter):
    """Platform1的适配器"""
    
    def transform_request(self, params: Dict) -> Dict:
        """转换Platform1的请求参数"""
        return {
            'api_version': 'v1',
            **params
        }
    
    def transform_response(self, data: Dict) -> Dict:
        """转换Platform1的响应数据"""
        return {
            'data': data.get('response', {}).get('data', []),
            'metadata': data.get('response', {}).get('metadata', {})
        }

class Platform2Adapter(PlatformAdapter):
    """Platform2的适配器"""
    
    def transform_request(self, params: Dict) -> Dict:
        """转换Platform2的请求参数"""
        return {
            'version': '2.0',
            'params': params
        }
    
    def transform_response(self, data: Dict) -> Dict:
        """转换Platform2的响应数据"""
        return {
            'data': data.get('result', []),
            'metadata': data.get('meta', {})
        }

class KeysightAdapter(PlatformAdapter):
    """Keysight平台适配器"""
    
    def transform_request(self, params: Dict) -> Dict:
        """转换Keysight的请求参数"""
        return {
            'apiVersion': '2.0',
            'measurement': params.get('measurement', 'sparameter'),
            'format': 'touchstone',
            **params
        }
    
    def transform_response(self, data: Dict) -> Dict:
        """转换Keysight的响应数据"""
        return {
            'type': 's_parameter',
            'file_url': data.get('resultUrl'),
            'frequency_range': f"{data.get('startFreq', 0)}-{data.get('stopFreq', 0)}",
            'description': data.get('description', ''),
            'raw_data': data.get('measurements', [])
        }

class AgilentAdapter(PlatformAdapter):
    """Agilent平台适配器"""
    
    def transform_request(self, params: Dict) -> Dict:
        """转换Agilent的请求参数"""
        return {
            'version': '1.0',
            'type': 'network_analysis',
            'parameters': {
                'measurement_type': 's_parameter',
                **params
            }
        }
    
    def transform_response(self, data: Dict) -> Dict:
        """转换Agilent的响应数据"""
        measurement = data.get('measurement', {})
        return {
            'type': 's_parameter',
            'file_url': measurement.get('data_url'),
            'frequency_range': measurement.get('frequency_range', ''),
            'description': measurement.get('notes', ''),
            'raw_data': measurement.get('data', [])
        }

class RohdeSchwartzAdapter(PlatformAdapter):
    """罗德与施瓦茨平台适配器"""
    
    def transform_request(self, params: Dict) -> Dict:
        """转换R&S的请求参数"""
        return {
            'api_version': '3.0',
            'request_type': 'measurement',
            'settings': {
                'type': 'vector_network_analysis',
                **params
            }
        }
    
    def transform_response(self, data: Dict) -> Dict:
        """转换R&S的响应数据"""
        result = data.get('result', {})
        return {
            'type': 's_parameter',
            'file_url': result.get('file_location'),
            'frequency_range': f"{result.get('start_freq')}-{result.get('stop_freq')}",
            'description': result.get('measurement_info', ''),
            'raw_data': result.get('measurement_data', [])
        } 