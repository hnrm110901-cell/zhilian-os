"""
审计日志中间件
自动记录API请求和操作
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import time
import structlog

from src.services.audit_log_service import audit_log_service
from src.models.audit_log import AuditAction, ResourceType

logger = structlog.get_logger()


class AuditLogMiddleware(BaseHTTPMiddleware):
    """审计日志中间件"""

    # 需要记录的路径前缀
    AUDIT_PATHS = [
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/users",
        "/api/v1/finance",
        "/api/v1/backup",
        "/api/v1/supply-chain",
        "/api/v1/multi-store",
    ]

    # 不需要记录的路径
    EXCLUDE_PATHS = [
        "/api/v1/health",
        "/api/v1/audit/logs",  # 避免查询审计日志时产生新的审计日志
        "/docs",
        "/redoc",
        "/openapi.json",
    ]

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        """处理请求"""
        start_time = time.time()

        # 检查是否需要记录
        should_audit = self._should_audit(request.url.path)

        # 获取用户信息
        user_info = None
        if should_audit:
            user_info = await self._get_user_info(request)

        # 处理请求
        response = await call_next(request)

        # 记录审计日志
        if should_audit and user_info:
            process_time = time.time() - start_time
            await self._log_request(request, response, user_info, process_time)

        return response

    def _should_audit(self, path: str) -> bool:
        """判断是否需要记录审计日志"""
        # 排除不需要记录的路径
        for exclude_path in self.EXCLUDE_PATHS:
            if path.startswith(exclude_path):
                return False

        # 检查是否在需要记录的路径中
        for audit_path in self.AUDIT_PATHS:
            if path.startswith(audit_path):
                return True

        return False

    async def _get_user_info(self, request: Request) -> dict:
        """获取用户信息"""
        try:
            # 尝试从请求状态中获取用户信息
            if hasattr(request.state, "user"):
                user = request.state.user
                return {
                    "user_id": str(user.id),
                    "username": user.username,
                    "user_role": user.role.value if hasattr(user.role, 'value') else str(user.role),
                    "store_id": user.store_id,
                }

            # 如果没有用户信息，尝试从Authorization头解析
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
                from src.core.security import decode_access_token
                payload = decode_access_token(token)
                return {
                    "user_id": payload.get("sub"),
                    "username": payload.get("username"),
                    "user_role": payload.get("role"),
                    "store_id": payload.get("store_id"),
                }

        except Exception as e:
            logger.warning("获取用户信息失败", error=str(e))

        return None

    async def _log_request(
        self,
        request: Request,
        response: Response,
        user_info: dict,
        process_time: float
    ):
        """记录请求日志"""
        try:
            # 确定操作类型和资源类型
            action, resource_type = self._determine_action_and_resource(
                request.method,
                request.url.path
            )

            # 确定操作状态
            status = "success" if response.status_code < 400 else "failed"

            # 获取IP地址
            ip_address = request.client.host if request.client else None

            # 获取User Agent
            user_agent = request.headers.get("User-Agent")

            # 生成描述
            description = self._generate_description(
                request.method,
                request.url.path,
                response.status_code
            )

            # 记录审计日志
            await audit_log_service.log_action(
                action=action,
                resource_type=resource_type,
                user_id=user_info["user_id"],
                username=user_info.get("username"),
                user_role=user_info.get("user_role"),
                description=description,
                ip_address=ip_address,
                user_agent=user_agent,
                request_method=request.method,
                request_path=str(request.url.path),
                status=status,
                store_id=user_info.get("store_id"),
            )

        except Exception as e:
            logger.error("记录审计日志失败", error=str(e), path=request.url.path)

    def _determine_action_and_resource(self, method: str, path: str) -> tuple[str, str]:
        """确定操作类型和资源类型"""
        # 登录/登出
        if "/auth/login" in path:
            return AuditAction.LOGIN, ResourceType.SYSTEM
        if "/auth/logout" in path:
            return AuditAction.LOGOUT, ResourceType.SYSTEM

        # 用户管理
        if "/users" in path:
            if method == "POST":
                return AuditAction.USER_CREATE, ResourceType.USER
            elif method == "PUT" or method == "PATCH":
                return AuditAction.USER_UPDATE, ResourceType.USER
            elif method == "DELETE":
                return AuditAction.USER_DELETE, ResourceType.USER
            else:
                return AuditAction.VIEW, ResourceType.USER

        # 财务管理
        if "/finance/transactions" in path:
            if method == "POST":
                return AuditAction.TRANSACTION_CREATE, ResourceType.TRANSACTION
            elif method == "PUT" or method == "PATCH":
                return AuditAction.TRANSACTION_UPDATE, ResourceType.TRANSACTION
            elif method == "DELETE":
                return AuditAction.TRANSACTION_DELETE, ResourceType.TRANSACTION
            else:
                return AuditAction.VIEW, ResourceType.TRANSACTION

        if "/finance/budgets" in path:
            if method == "POST":
                return AuditAction.BUDGET_CREATE, ResourceType.BUDGET
            elif method == "PUT" or method == "PATCH":
                return AuditAction.BUDGET_UPDATE, ResourceType.BUDGET
            else:
                return AuditAction.VIEW, ResourceType.BUDGET

        if "/finance/reports/export" in path:
            return AuditAction.REPORT_EXPORT, ResourceType.REPORT

        # 备份管理
        if "/backup" in path:
            if "create" in path or method == "POST":
                return AuditAction.BACKUP_CREATE, ResourceType.BACKUP
            elif "restore" in path:
                return AuditAction.BACKUP_RESTORE, ResourceType.BACKUP
            elif method == "DELETE":
                return AuditAction.BACKUP_DELETE, ResourceType.BACKUP
            else:
                return AuditAction.VIEW, ResourceType.BACKUP

        # 供应链管理
        if "/supply-chain" in path:
            if method == "POST":
                return AuditAction.CREATE, ResourceType.PURCHASE_ORDER
            elif method == "PUT" or method == "PATCH":
                return AuditAction.UPDATE, ResourceType.PURCHASE_ORDER
            elif method == "DELETE":
                return AuditAction.DELETE, ResourceType.PURCHASE_ORDER
            else:
                return AuditAction.VIEW, ResourceType.PURCHASE_ORDER

        # 默认
        if method == "POST":
            return AuditAction.CREATE, ResourceType.SYSTEM
        elif method in ["PUT", "PATCH"]:
            return AuditAction.UPDATE, ResourceType.SYSTEM
        elif method == "DELETE":
            return AuditAction.DELETE, ResourceType.SYSTEM
        else:
            return AuditAction.VIEW, ResourceType.SYSTEM

    def _generate_description(self, method: str, path: str, status_code: int) -> str:
        """生成操作描述"""
        action_map = {
            "GET": "查询",
            "POST": "创建",
            "PUT": "更新",
            "PATCH": "修改",
            "DELETE": "删除",
        }

        action = action_map.get(method, method)
        status = "成功" if status_code < 400 else "失败"

        # 提取资源名称
        resource = path.split("/")[-1] if "/" in path else path

        return f"{action} {resource} {status}"
