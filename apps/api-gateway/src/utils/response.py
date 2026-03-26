"""
统一 API 响应格式

所有对外 API 端点应使用此模块的函数包装返回值，确保响应结构一致。

格式：
{
    "success": bool,
    "code": str,       # "OK" 或错误码（如 "NOT_FOUND", "VALIDATION_ERROR"）
    "message": str,    # 人类可读消息
    "data": Any        # 业务数据（成功时为实际数据，失败时为补充信息或 None）
}
"""

from __future__ import annotations

from typing import Any, Dict


def success_response(data: Any = None, message: str = "ok") -> Dict[str, Any]:
    """构造成功响应"""
    return {"success": True, "code": "OK", "message": message, "data": data}


def error_response(code: str, message: str, data: Any = None) -> Dict[str, Any]:
    """构造错误响应"""
    return {"success": False, "code": code, "message": message, "data": data}
