from typing import Type
from .adapters import PlatformAdapter, Platform1Adapter, Platform2Adapter, KeysightAdapter, AgilentAdapter, RohdeSchwartzAdapter
from .services import ExternalDataService
from .models import ExternalPlatform

class PlatformAdapterFactory:
    """平台适配器工厂"""
    
    _adapters = {
        'platform1': Platform1Adapter,
        'platform2': Platform2Adapter,
        'keysight': KeysightAdapter,
        'agilent': AgilentAdapter,
        'rohde_schwartz': RohdeSchwartzAdapter,
    }
    
    @classmethod
    def get_adapter(cls, platform: ExternalPlatform) -> PlatformAdapter:
        """获取平台适配器"""
        adapter_class = cls._adapters.get(platform.name)
        if not adapter_class:
            raise ValueError(f"Unsupported platform: {platform.name}")
        
        service = ExternalDataService(platform)
        return adapter_class(service)
    
    @classmethod
    def register_adapter(cls, platform_name: str, adapter_class: Type[PlatformAdapter]):
        """注册新的平台适配器"""
        cls._adapters[platform_name] = adapter_class 