from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SParameterViewSet

# 创建路由器并注册视图集
router = DefaultRouter()
router.register(r's-parameters', SParameterViewSet, basename='s-parameter')

urlpatterns = [
    path('', include(router.urls)),
]

# 生成的 URL 模式:
# /s-parameters/ - GET(列表), POST(创建)
# /s-parameters/{id}/ - GET(详情), PUT(更新), DELETE(删除)
# /s-parameters/{id}/analyze/ - POST(分析)
# /s-parameters/bulk_import/ - POST(批量导入)
# /s-parameters/import_progress/ - GET(导入进度)
# /s-parameters/bulk_export/ - POST(批量导出)
# /s-parameters/export_progress/ - GET(导出进度)
# /s-parameters/{id}/validate/ - GET(验证)
# /s-parameters/{id}/retry_processing/ - POST(重试处理)
# /s-parameters/{id}/download_results/ - GET(下载仿真结果)
# /s-parameters/{id}/retry_simulation/ - POST(重试仿真)
# /s-parameters/{id}/simulation_status/ - GET(获取仿真状态) 