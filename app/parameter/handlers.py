from app.core.events import EventManager, Events
from app.external_data.models import ExternalDataFetch
from .models import SParameter
from .services import SParameterProcessor

@EventManager.subscribe(Events.DATA_FETCHED)
def handle_external_data_fetch(sender, platform, data, **kwargs):
    """处理从外部平台获取的数据"""
    if data.get('type') == 's_parameter':
        # 创建或更新S参数记录
        s_parameter = SParameter.objects.create(
            file=data.get('file_url'),
            description=data.get('description'),
            frequency_range=data.get('frequency_range')
        )
        
        # 处理S参数数据
        processor = SParameterProcessor(s_parameter)
        processor.process(data=data.get('raw_data'))

@EventManager.subscribe(Events.PROCESSING_COMPLETED)
def handle_processing_completed(sender, instance, result, **kwargs):
    """处理S参数处理完成事件"""
    if isinstance(instance, SParameter):
        # 更新处理历史记录
        instance.histories.create(
            processing_type='auto_process',
            processed_data=result
        ) 