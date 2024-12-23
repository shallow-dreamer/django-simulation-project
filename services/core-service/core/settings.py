from decouple import config

# 服务发现配置
SERVICE_REGISTRY = {
    'parameter': config('PARAMETER_SERVICE_URL'),
    'simulation': config('SIMULATION_SERVICE_URL'),
    'external_data': config('EXTERNAL_DATA_SERVICE_URL'),
}

# 分布式缓存配置
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': config('REDIS_URL'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# 分布式会话配置
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default' 