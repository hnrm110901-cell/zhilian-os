"""
HR 操作审计中间件（stub）
记录 HR 敏感操作路径的请求，供合规审计使用。
当前为透传实现，待 HR 模块 model 文件就绪后补全。
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from fastapi import Request


class HROperationAuditMiddleware(BaseHTTPMiddleware):
    """HR 敏感操作审计中间件（透传占位）"""

    HR_PATHS = [
        "/api/v1/hr/",
        "/api/v1/payroll/",
        "/api/v1/employees/",
    ]

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        return await call_next(request)
