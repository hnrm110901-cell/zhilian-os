"""
数据脱敏服务 — 按角色级别自动脱敏敏感字段（API 响应层）

与 sensitive_data_service.py（加密存取层）和 crypto.py（加密算法层）不同，
本服务专注于 API 响应时的显示脱敏，不涉及数据库读写。

角色级别：
  admin / hr_manager (level 3): 可查看完整数据（需审计日志记录）
  store_manager / hr_staff (level 2): 部分脱敏（手机号中间4位隐藏、身份证保留前3后4）
  employee / viewer (level 1): 高度脱敏（仅显示末4位）
  anonymous (level 0): 完全隐藏

使用:
  from src.services.data_masking_service import DataMaskingService

  masked = DataMaskingService.mask_employee_data(employee_dict, role_level=2)
  masked_list = DataMaskingService.mask_employee_list(employees, role_level=1)
  level = DataMaskingService.get_role_level("store_manager")  # → 2
"""
from typing import Optional

import structlog

from src.core.crypto import field_crypto

logger = structlog.get_logger()


class DataMaskingService:
    """API 响应层数据脱敏服务 — 按角色级别自动脱敏"""

    # ── 角色 → 脱敏级别映射 ──────────────────────────────────
    ROLE_LEVELS: dict[str, int] = {
        "super_admin": 3,
        "admin": 3,
        "hr_manager": 3,
        "hr_staff": 2,
        "store_manager": 2,
        "manager": 2,
        "employee": 1,
        "viewer": 1,
    }

    # ── 脱敏规则：字段名 → {级别: 脱敏函数} ──────────────────
    # 每个 lambda 接收明文值，返回脱敏后的字符串
    MASKING_RULES: dict[str, dict[int, callable]] = {
        "phone": {
            3: lambda v: v,                           # admin: 13812345678
            2: lambda v: v[:3] + "****" + v[-4:] if len(v) >= 7 else "****",
            1: lambda v: "****" + v[-4:] if len(v) >= 4 else "****",
            0: lambda v: "****",
        },
        "mobile": {  # phone 的别名字段，同样规则
            3: lambda v: v,
            2: lambda v: v[:3] + "****" + v[-4:] if len(v) >= 7 else "****",
            1: lambda v: "****" + v[-4:] if len(v) >= 4 else "****",
            0: lambda v: "****",
        },
        "id_card_no": {
            3: lambda v: v,                           # admin: 430111199901011234
            2: lambda v: v[:3] + "***********" + v[-4:] if len(v) >= 7 else "****",
            1: lambda v: "**************" + v[-4:] if len(v) >= 4 else "****",
            0: lambda v: "****",
        },
        "bank_account": {
            3: lambda v: v,                           # admin: 6222031234567890
            2: lambda v: "****" + v[-4:] if len(v) >= 4 else "****",
            1: lambda v: "****" + v[-4:] if len(v) >= 4 else "****",
            0: lambda v: "****",
        },
        "email": {
            3: lambda v: v,                           # admin: zhangsan@example.com
            2: lambda v: v[0] + "***@" + v.split("@")[1] if "@" in v and len(v) > 1 else "***",
            1: lambda v: "***@***",
            0: lambda v: "****",
        },
        "emergency_phone": {
            3: lambda v: v,
            2: lambda v: v[:3] + "****" + v[-4:] if len(v) >= 7 else "****",
            1: lambda v: "****",
            0: lambda v: "****",
        },
        "emergency_contact_phone": {  # 别名
            3: lambda v: v,
            2: lambda v: v[:3] + "****" + v[-4:] if len(v) >= 7 else "****",
            1: lambda v: "****",
            0: lambda v: "****",
        },
    }

    # 所有敏感字段名集合（用于快速判断）
    SENSITIVE_FIELDS: set[str] = set(MASKING_RULES.keys())

    # ── 核心方法 ──────────────────────────────────────────────

    @classmethod
    def get_role_level(cls, role: str) -> int:
        """将角色字符串映射为脱敏级别（0-3）

        未知角色默认为 level 0（完全隐藏），保障安全
        """
        return cls.ROLE_LEVELS.get(role, 0)

    @classmethod
    def mask_value(cls, field_name: str, value: str, role_level: int) -> str:
        """对单个字段值进行脱敏

        Args:
            field_name: 字段名（如 phone / id_card_no）
            value: 明文值（或已加密的 ENC: 前缀值）
            role_level: 脱敏级别 0-3

        Returns:
            脱敏后的字符串
        """
        if not value:
            return value or ""

        # 已脱敏的值不重复脱敏（幂等性）
        if cls._is_already_masked(value):
            return value

        # 处理加密值：解密后再脱敏
        plaintext = cls._decrypt_if_needed(value, role_level)

        # 查找脱敏规则
        rules = cls.MASKING_RULES.get(field_name)
        if not rules:
            return plaintext

        # 限制 role_level 范围
        level = max(0, min(3, role_level))
        mask_fn = rules.get(level, rules.get(0, lambda v: "****"))

        try:
            return mask_fn(plaintext)
        except Exception:
            logger.warning("脱敏处理异常，返回完全隐藏", field=field_name)
            return "****"

    @classmethod
    def mask_employee_data(cls, data: dict, role_level: int = 0) -> dict:
        """对员工数据字典中的敏感字段进行脱敏

        Args:
            data: 员工数据字典（单条记录）
            role_level: 脱敏级别 0-3

        Returns:
            脱敏后的数据字典（原字典不会被修改）
        """
        if not data or not isinstance(data, dict):
            return data

        result = dict(data)

        for key, value in result.items():
            # 递归处理嵌套字典（如 employee 子对象）
            if isinstance(value, dict):
                result[key] = cls.mask_employee_data(value, role_level)
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                result[key] = cls.mask_employee_list(value, role_level)
            elif key in cls.SENSITIVE_FIELDS and isinstance(value, str):
                result[key] = cls.mask_value(key, value, role_level)

        return result

    @classmethod
    def mask_employee_list(cls, employees: list[dict], role_level: int = 0) -> list[dict]:
        """批量脱敏员工数据列表

        Args:
            employees: 员工数据字典列表
            role_level: 脱敏级别 0-3

        Returns:
            脱敏后的列表
        """
        if not employees:
            return employees

        return [cls.mask_employee_data(emp, role_level) for emp in employees]

    # ── 内部工具 ──────────────────────────────────────────────

    @classmethod
    def _is_already_masked(cls, value: str) -> bool:
        """判断值是否已经被脱敏（包含连续的 * 号且不是加密值）

        避免重复脱敏导致数据完全丢失
        """
        if not value:
            return False
        if value.startswith("ENC:"):
            return False
        # 如果值主要由 * 组成，认为已脱敏
        star_count = value.count("*")
        if star_count >= 4 and star_count / len(value) > 0.5:
            return True
        return False

    @classmethod
    def _decrypt_if_needed(cls, value: str, role_level: int) -> str:
        """如果值是加密的（ENC: 前缀），根据角色级别决定是否解密

        - admin (level 3): 解密后返回明文（由上层脱敏规则决定是否显示全部）
        - 其他级别: 也需要解密才能正确脱敏（否则只能返回 ****）
        """
        if not value or not value.startswith("ENC:"):
            return value

        try:
            plaintext = field_crypto.decrypt(value)
            return plaintext
        except Exception:
            logger.warning("脱敏服务解密失败，返回完全隐藏")
            return "****"
