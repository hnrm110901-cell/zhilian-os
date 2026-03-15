"""
HR操作审计中间件 — 自动记录所有HR写操作（POST/PUT/DELETE）

功能:
  - 拦截 /api/v1/hr/ 和 /api/v1/payroll/ 路径下的写操作
  - 自动解析模块名、操作类型、资源ID
  - 脱敏敏感字段（身份证号、银行卡号、手机号等）
  - 通过 BackgroundTask 异步写入数据库，不阻塞响应
"""
import copy
import json
import re
import time
from typing import Optional

import structlog
from starlette.background import BackgroundTask
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger()

# 需要审计的路径前缀
AUDIT_PATHS = [
    "/api/v1/hr/",
    "/api/v1/payroll/",
]

# 排除审计的路径（避免递归记录）
EXCLUDE_PATHS = [
    "/api/v1/hr/audit/",
]

# 敏感字段名集合（递归脱敏）
SENSITIVE_FIELDS = {
    "password", "id_card_no", "id_card_number", "id_number",
    "bank_account", "bank_card_no", "bank_card_number",
    "phone", "mobile", "telephone", "contact_phone",
    "token", "secret", "access_token", "refresh_token",
}

# 路径到模块的映射规则
MODULE_PATTERNS = [
    (r"/api/v1/payroll/", "payroll"),
    (r"/api/v1/hr/leave", "leave"),
    (r"/api/v1/hr/attendance", "attendance"),
    (r"/api/v1/hr/schedule", "schedule"),
    (r"/api/v1/hr/settlement", "settlement"),
    (r"/api/v1/hr/employee", "employee"),
    (r"/api/v1/hr/recruitment", "recruitment"),
    (r"/api/v1/hr/performance", "performance"),
    (r"/api/v1/hr/commission", "commission"),
    (r"/api/v1/hr/reward-penalty", "reward_penalty"),
    (r"/api/v1/hr/social-insurance", "social_insurance"),
    (r"/api/v1/hr/training", "training"),
    (r"/api/v1/hr/lifecycle", "lifecycle"),
    (r"/api/v1/hr/growth", "growth"),
    (r"/api/v1/hr/import", "import"),
    (r"/api/v1/hr/exit-interview", "exit_interview"),
    (r"/api/v1/hr/report", "report"),
    (r"/api/v1/hr/sensitive", "sensitive"),
    (r"/api/v1/hr/rules", "rules"),
    (r"/api/v1/hr/payslip", "payslip"),
    (r"/api/v1/hr/approval", "approval"),
]

# 路径关键词到操作类型的映射
ACTION_KEYWORDS = {
    "approve": "approve",
    "reject": "reject",
    "cancel": "cancel",
    "submit": "submit",
    "revoke": "revoke",
    "confirm": "confirm",
    "batch": "batch",
}


class HROperationAuditMiddleware(BaseHTTPMiddleware):
    """HR操作审计中间件 — 拦截写操作并异步记录审计日志"""

    async def dispatch(self, request: Request, call_next) -> Response:
        # 只拦截写操作
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return await call_next(request)

        path = request.url.path

        # 检查路径是否需要审计
        if not any(path.startswith(p) for p in AUDIT_PATHS):
            return await call_next(request)

        # 排除特定路径
        if any(path.startswith(p) for p in EXCLUDE_PATHS):
            return await call_next(request)

        # 读取请求体（需要在 call_next 之前）
        body_bytes = await request.body()
        request_data = _safe_parse_json(body_bytes)
        masked_data = _mask_sensitive(request_data) if request_data else None

        # 解析审计元数据
        module = _extract_module(path)
        action = _extract_action(request.method, path)
        resource_type = _extract_resource_type(path)
        resource_id = _extract_resource_id(path)

        # 提取操作人信息
        operator_id = _extract_operator_id(request)
        operator_name = request.headers.get("X-Operator-Name")
        operator_role = request.headers.get("X-Operator-Role")
        store_id = request.headers.get("X-Store-Id", request.query_params.get("store_id"))
        brand_id = request.headers.get("X-Brand-Id", request.query_params.get("brand_id"))

        # 客户端信息
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("User-Agent", "")[:500]

        # 执行请求
        start = time.time()
        try:
            response = await call_next(request)
        except Exception as exc:
            # 请求异常也要记录
            _schedule_audit_write(
                operator_id=operator_id,
                operator_name=operator_name,
                operator_role=operator_role,
                action=action,
                module=module,
                resource_type=resource_type,
                resource_id=resource_id,
                method=request.method,
                path=path,
                ip_address=ip_address,
                user_agent=user_agent,
                request_body=masked_data,
                response_status=500,
                success="false",
                error_message=str(exc)[:2000],
                store_id=store_id,
                brand_id=brand_id,
            )
            raise

        duration_ms = int((time.time() - start) * 1000)
        success = "true" if response.status_code < 400 else "false"
        error_msg = None if success == "true" else f"HTTP {response.status_code}"

        # 通过 background task 异步写入，不阻塞响应
        _schedule_audit_write(
            operator_id=operator_id,
            operator_name=operator_name,
            operator_role=operator_role,
            action=action,
            module=module,
            resource_type=resource_type,
            resource_id=resource_id,
            method=request.method,
            path=path,
            ip_address=ip_address,
            user_agent=user_agent,
            request_body=masked_data,
            response_status=response.status_code,
            success=success,
            error_message=error_msg,
            store_id=store_id,
            brand_id=brand_id,
        )

        return response


# ── 辅助函数 ───────────────────────────────────────────────

def _schedule_audit_write(**kwargs):
    """调度后台审计日志写入（异步，不阻塞主请求）"""
    import asyncio

    async def _do_write():
        try:
            from src.core.database import async_session_factory
            from src.models.operation_audit_log import OperationAuditLog

            async with async_session_factory() as session:
                log = OperationAuditLog(**kwargs)
                session.add(log)
                await session.commit()
        except Exception as e:
            logger.error("写入HR操作审计日志失败", error=str(e), module=kwargs.get("module"))

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_do_write())
    except RuntimeError:
        # 没有运行中的事件循环，跳过
        logger.warning("无法写入HR操作审计日志：没有运行中的事件循环")


def _safe_parse_json(body: bytes) -> Optional[dict]:
    """安全解析JSON请求体"""
    if not body:
        return None
    try:
        data = json.loads(body)
        return data if isinstance(data, dict) else {"_raw": data}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _mask_sensitive(data: dict) -> dict:
    """递归脱敏敏感字段"""
    if not isinstance(data, dict):
        return data
    masked = {}
    for key, value in data.items():
        if key.lower() in SENSITIVE_FIELDS:
            if isinstance(value, str) and len(value) > 4:
                masked[key] = value[:2] + "***" + value[-2:]
            else:
                masked[key] = "***"
        elif isinstance(value, dict):
            masked[key] = _mask_sensitive(value)
        elif isinstance(value, list):
            masked[key] = [
                _mask_sensitive(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            masked[key] = value
    return masked


def _extract_module(path: str) -> str:
    """从路径提取模块名: /api/v1/hr/leave/... → leave"""
    for pattern, module in MODULE_PATTERNS:
        if path.startswith(pattern) or re.match(pattern, path):
            return module
    # 兜底：取 /hr/ 后的第一段
    match = re.search(r"/hr/([a-z_-]+)", path)
    if match:
        return match.group(1).replace("-", "_")
    return "hr"


def _extract_action(method: str, path: str) -> str:
    """推断操作类型: POST + /approve → approve"""
    # 先检查路径关键词
    path_lower = path.lower()
    for keyword, action in ACTION_KEYWORDS.items():
        if f"/{keyword}" in path_lower:
            return action

    # 按HTTP方法推断
    method_action_map = {
        "POST": "create",
        "PUT": "update",
        "PATCH": "update",
        "DELETE": "delete",
    }
    return method_action_map.get(method, "unknown")


def _extract_resource_type(path: str) -> str:
    """从路径提取资源类型: /api/v1/hr/leave/requests/xxx → leave_request"""
    # 去掉前缀，取有意义的路径段
    stripped = re.sub(r"^/api/v1/(hr|payroll)/", "", path)
    parts = [p for p in stripped.split("/") if p and not _is_id(p)]
    if len(parts) >= 2:
        return f"{parts[0]}_{parts[1]}".rstrip("s")  # leave/requests → leave_request
    elif len(parts) == 1:
        return parts[0].rstrip("s")
    return "unknown"


def _extract_resource_id(path: str) -> Optional[str]:
    """从路径提取资源ID（最后一个看起来像ID的路径段）"""
    parts = path.rstrip("/").split("/")
    for part in reversed(parts):
        if _is_id(part):
            return part
    return None


def _is_id(s: str) -> bool:
    """判断字符串是否像ID（UUID或纯数字）"""
    if not s:
        return False
    # UUID 格式
    if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", s, re.I):
        return True
    # 纯数字ID
    if s.isdigit() and len(s) <= 20:
        return True
    return False


def _extract_operator_id(request: Request) -> str:
    """提取操作人ID（优先级：JWT → Header → query param → 默认system）"""
    # 从 request.state 获取（如果 auth middleware 已解析）
    if hasattr(request.state, "user"):
        user = request.state.user
        return str(getattr(user, "id", "system"))

    # 从 Authorization header 解析 JWT
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from src.core.security import decode_access_token
            payload = decode_access_token(auth_header.split(" ")[1])
            return payload.get("sub", "system")
        except Exception:
            pass

    # 从自定义 header
    return request.headers.get("X-Operator-Id", request.query_params.get("operator_id", "system"))
