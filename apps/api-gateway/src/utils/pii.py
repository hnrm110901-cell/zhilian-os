"""
PII 脱敏工具

手机号脱敏规则: 138****5678（保留前3位和后4位，中间4位替换为****）
"""
import re
from typing import Optional


def mask_phone(phone: Optional[str]) -> Optional[str]:
    """
    手机号脱敏

    Args:
        phone: 原始手机号（11位中国大陆手机号）

    Returns:
        脱敏后的手机号，如 138****5678；非手机号格式原样返回
    """
    if not phone:
        return phone
    cleaned = re.sub(r"[\s\-()]", "", phone)
    if re.match(r"^1[3-9]\d{9}$", cleaned):
        return f"{cleaned[:3]}****{cleaned[7:]}"
    # 非标准格式（如座机）：保留前2位和后2位
    if len(cleaned) >= 6:
        return f"{cleaned[:2]}{'*' * (len(cleaned) - 4)}{cleaned[-2:]}"
    return "****"
