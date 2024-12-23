from typing import Dict, Any, List, Callable
from dataclasses import dataclass
from enum import Enum
from django.dispatch import Signal, receiver
from functools import wraps
from django.db.models.signals import post_save
from django.contrib.auth.models import User
from app.parameter.models import SParameter
from app.simulation.models import ComSimulation
import logging

logger = logging.getLogger(__name__)

class Events(Enum):
    """事件类型枚举"""
    PARAMETER_UPDATED = 'parameter_updated'
    SIMULATION_COMPLETED = 'simulation_completed'
    EXTERNAL_DATA_SYNCED = 'external_data_synced'
    COLLECTION_CHANGED = 'collection_changed'

@dataclass
class Event:
    type: Events
    sender: Any
    data: Dict[str, Any]

class EventManager:
    """事件管理器"""
    _handlers: Dict[Events, List[Callable]] = {}
    
    @classmethod
    def subscribe(cls, event_type: Events, handler: Callable):
        """订阅事件"""
        if event_type not in cls._handlers:
            cls._handlers[event_type] = []
        cls._handlers[event_type].append(handler)
    
    @classmethod
    def publish(cls, event_type: Events, sender: Any, **data):
        """发布事件"""
        if event_type not in cls._handlers:
            return
            
        event = Event(type=event_type, sender=sender, data=data)
        for handler in cls._handlers[event_type]:
            try:
                handler(event)
            except Exception as e:
                logger.exception(f"Error handling event {event_type}: {str(e)}")

# 使用示例
@receiver(post_save, sender=SParameter)
def handle_parameter_update(sender, instance, created, **kwargs):
    """处理S参数更新"""
    EventManager.publish(
        Events.PARAMETER_UPDATED,
        sender=instance,
        parameter_id=instance.id,
        is_new=created
    )

@receiver(Events.PARAMETER_UPDATED)
def update_related_simulations(event: Event):
    """更新相关的仿真"""
    parameter_id = event.data['parameter_id']
    simulations = ComSimulation.objects.filter(
        s_parameter_id=parameter_id,
        status='completed'
    )
    
    for simulation in simulations:
        simulation.status = 'outdated'
        simulation.save()