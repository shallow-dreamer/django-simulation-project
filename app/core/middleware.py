from django.http import JsonResponse
from rest_framework.exceptions import APIException
from django.core.exceptions import ValidationError
import logging

logger = logging.getLogger(__name__)

class ErrorHandlerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
            return response
        except Exception as e:
            logger.exception("Unhandled exception")
            return self._handle_error(e)

    def _handle_error(self, exc):
        if isinstance(exc, APIException):
            return JsonResponse({
                'error': str(exc),
                'code': exc.status_code
            }, status=exc.status_code)
            
        if isinstance(exc, ValidationError):
            return JsonResponse({
                'error': exc.messages,
                'code': 400
            }, status=400)
            
        return JsonResponse({
            'error': '服务器内部错误',
            'code': 500
        }, status=500) 