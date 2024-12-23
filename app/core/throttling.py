from rest_framework.throttling import SimpleRateThrottle

class UserRateThrottle(SimpleRateThrottle):
    """用户请求限流"""
    rate = '1000/hour'  # 每小时1000次请求
    
    def get_cache_key(self, request, view):
        if request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        return f"throttle_user_{ident}"

class BurstRateThrottle(SimpleRateThrottle):
    """突发请求限流"""
    rate = '60/minute'  # 每分钟60次请求
    
    def get_cache_key(self, request, view):
        return f"throttle_burst_{self.get_ident(request)}" 