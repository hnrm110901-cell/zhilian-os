"""
响应脱敏装饰器 — 自动对 HR API 响应中的敏感字段进行脱敏

使用方式:
    from src.core.mask_response import mask_sensitive_fields

    @router.get("/hr/employees")
    @mask_sensitive_fields()
    async def list_employees(request: Request, ...):
        return {"items": [...]}

装饰器会根据请求头 X-User-Role 或查询参数 mask_level 自动确定脱敏级别。
"""

from functools import wraps

from fastapi import Request
from src.services.data_masking_service import DataMaskingService


def mask_sensitive_fields(sensitive_fields: set[str] | None = None):
    """响应脱敏装饰器

    Args:
        sensitive_fields: 可选，指定需要脱敏的字段名集合。
                         为 None 时使用 DataMaskingService 默认的全部敏感字段。
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 从 kwargs 中提取 request 对象
            request: Request | None = kwargs.get("request")

            # 执行原始函数
            result = await func(*args, **kwargs)

            # 确定脱敏级别：优先使用 mask_level 查询参数，其次从 X-User-Role 头获取
            role_level = None
            if request:
                # 查询参数 mask_level 用于测试覆盖
                mask_level_param = request.query_params.get("mask_level")
                if mask_level_param is not None:
                    try:
                        role_level = int(mask_level_param)
                    except ValueError:
                        pass

                # 从请求头获取角色
                if role_level is None:
                    role = request.headers.get("X-User-Role", "viewer")
                    role_level = DataMaskingService.get_role_level(role)

            if role_level is None:
                role_level = 0  # 默认最严格脱敏

            # 对响应数据进行脱敏
            if isinstance(result, dict):
                return DataMaskingService.mask_employee_data(result, role_level)
            elif isinstance(result, list):
                return DataMaskingService.mask_employee_list(result, role_level)

            return result

        return wrapper

    return decorator
