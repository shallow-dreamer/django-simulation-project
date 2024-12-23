class BaseError(Exception):
    """基础错误类"""
    def __init__(self, message: str, code: str = None):
        self.message = message
        self.code = code or 'unknown_error'
        super().__init__(message)

class ValidationError(BaseError):
    """验证错误"""
    pass

class ProcessingError(BaseError):
    """处理错误"""
    pass

class ResourceNotFoundError(BaseError):
    """资源不存在错误"""
    pass

class ServiceError(BaseError):
    """服务错误"""
    pass

def handle_error(func):
    """错误处理装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValidationError as e:
            return Response({
                'error': e.message,
                'code': e.code,
                'type': 'validation_error'
            }, status=400)
        except ResourceNotFoundError as e:
            return Response({
                'error': e.message,
                'code': e.code,
                'type': 'not_found'
            }, status=404)
        except ProcessingError as e:
            return Response({
                'error': e.message,
                'code': e.code,
                'type': 'processing_error'
            }, status=422)
        except ServiceError as e:
            return Response({
                'error': e.message,
                'code': e.code,
                'type': 'service_error'
            }, status=503)
        except Exception as e:
            logger.exception("Unexpected error")
            return Response({
                'error': str(e),
                'code': 'internal_error',
                'type': 'internal_error'
            }, status=500)
    return wrapper 