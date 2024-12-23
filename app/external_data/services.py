import requests
from typing import Dict, Any, Optional
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from django.conf import settings
from app.core.services import ProcessingService
from app.core.events import EventManager, Events
from .models import ExternalPlatform, ExternalDataFetch, SyncMonitor
import time
from django.db import transaction
from django.core.cache import cache
import hashlib
from django.utils import timezone
from datetime import timedelta
import json
import logging

logger = logging.getLogger(__name__)

class ExternalDataService(ProcessingService):
    """外部数据服务"""
    def __init__(self, platform: ExternalPlatform):
        super().__init__()
        self.platform = platform
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """创建带重试机制的会话"""
        session = requests.Session()
        
        # 配置重试策略
        retry_strategy = Retry(
            total=settings.EXTERNAL_PLATFORMS.get(self.platform.name, {}).get('retry_count', 3),
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # 设置请求头
        session.headers.update({
            'Authorization': f'Bearer {self.platform.api_key}',
            'Content-Type': 'application/json'
        })
        
        return session

    def fetch_data(self, endpoint: str, params: Dict = None) -> Dict[str, Any]:
        """获取外部数据"""
        # 生成请求的唯一标识
        request_key = self._generate_request_key(endpoint, params)
        lock_key = f"lock_{request_key}"
        
        # 使用缓存实现分布式锁
        if not cache.add(lock_key, "1", timeout=300):  # 5分钟超时
            raise ValueError("相同的请求正在处理中")
            
        try:
            with transaction.atomic():
                fetch_record = None
                retry_count = 0
                max_retries = settings.EXTERNAL_PLATFORMS.get(self.platform.name, {}).get('retry_count', 3)
                
                while retry_count < max_retries:
                    try:
                        # 创建数据获取记录
                        fetch_record = ExternalDataFetch.objects.create(
                            platform=self.platform,
                            data_type=endpoint,
                            status='processing'
                        )
                        
                        # 发送请求
                        url = f"{self.platform.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
                        timeout = settings.EXTERNAL_PLATFORMS.get(self.platform.name, {}).get('timeout', 30)
                        
                        response = self.session.get(url, params=params, timeout=timeout)
                        response.raise_for_status()
                        data = response.json()
                        
                        # 更新记录状态
                        fetch_record.status = 'completed'
                        fetch_record.raw_data = data
                        fetch_record.processed_data = self.process_raw_data(data)
                        fetch_record.save()
                        
                        # 发布事件
                        EventManager.publish(
                            Events.DATA_FETCHED,
                            sender=self,
                            platform=self.platform,
                            data=fetch_record.processed_data
                        )
                        
                        return fetch_record.processed_data
                        
                    except requests.exceptions.RequestException as e:
                        retry_count += 1
                        if retry_count >= max_retries:
                            raise
                        time.sleep(2 ** retry_count)  # 指数退避
                    except Exception as e:
                        error_msg = f"处理数据失败: {str(e)}"
                        self.add_error(error_msg)
                        if fetch_record:
                            fetch_record.status = 'failed'
                            fetch_record.error_message = error_msg
                            fetch_record.save()
                        raise
        finally:
            cache.delete(lock_key)

    def process_raw_data(self, raw_data: Dict) -> Dict:
        """处理原始数据"""
        # 子类可以重写此方法实现具体的数据处理逻辑
        return raw_data

    def _generate_request_key(self, endpoint: str, params: Dict = None) -> str:
        """生成请求的唯一标识"""
        key_parts = [
            self.platform.name,
            endpoint,
            str(sorted(params.items()) if params else '')
        ]
        return hashlib.md5('|'.join(key_parts).encode()).hexdigest()

    def recover_failed_syncs(self):
        """恢复失败的同步任务"""
        failed_syncs = SyncMonitor.objects.filter(
            platform=self.platform,
            status='failed',
            start_time__gte=timezone.now() - timedelta(hours=24)
        )
        
        for sync in failed_syncs:
            try:
                # 重新执行同步
                result = self.fetch_data(
                    sync.sync_type,
                    json.loads(sync.details.get('params', '{}'))
                )
                
                # 更新同步记录
                sync.status = 'completed'
                sync.end_time = timezone.now()
                sync.errors = []
                sync.save()
                
                # 记录恢复成功
                logger.info(f"Successfully recovered sync {sync.id} for platform {self.platform.name}")
                
            except Exception as e:
                # 记录恢复失败
                sync.errors.append({
                    'time': timezone.now().isoformat(),
                    'error': str(e)
                })
                sync.save()
                logger.error(f"Failed to recover sync {sync.id}: {str(e)}")