"""
敏感数据管理服务 — 加密存取 + 审计日志

职责:
  1. 加密写入/解密读取员工 PII 字段（id_card_no / bank_account）
  2. 脱敏读取（列表展示用，不记审计）
  3. 批量加密已有明文数据（一次性迁移）
  4. 每次读写自动写入 sensitive_data_audit_logs

使用:
  svc = SensitiveDataService()
  await svc.set_sensitive_field(db, "EMP001", "id_card_no", "110101...", "ADMIN01")
  plain = await svc.get_sensitive_field(db, "EMP001", "id_card_no", "ADMIN01")
  masked = await svc.get_masked_field(db, "EMP001", "id_card_no")
"""

from typing import Optional

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.crypto import field_crypto
from src.models.employee import Employee
from src.models.sensitive_audit_log import SensitiveDataAuditLog

logger = structlog.get_logger()

# 允许加密的字段白名单 → (Employee 属性名, 脱敏类型)
_SENSITIVE_FIELDS: dict[str, str] = {
    "id_card_no": "id_card",
    "bank_account": "bank_account",
    "phone": "phone",
}


class SensitiveDataService:
    """敏感数据管理服务 — 加密存取 + 审计日志"""

    # ── 加密写入 ────────────────────────────────────────

    async def set_sensitive_field(
        self,
        db: AsyncSession,
        employee_id: str,
        field_name: str,
        plaintext: str,
        operator_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        """加密写入敏感字段 + 记录审计日志

        Returns:
            {"employee_id": ..., "field_name": ..., "status": "ok"}
        Raises:
            ValueError: 字段名不在白名单
            LookupError: 员工不存在
        """
        self._validate_field(field_name)

        # 查员工
        employee = await self._get_employee(db, employee_id)

        # 加密
        encrypted = field_crypto.encrypt(plaintext)

        # 写入
        setattr(employee, field_name, encrypted)
        db.add(employee)

        # 审计日志
        audit = SensitiveDataAuditLog(
            operator_id=operator_id,
            employee_id=employee_id,
            field_name=field_name,
            action="write",
            ip_address=ip_address,
            user_agent=user_agent,
            store_id=employee.store_id,
            detail=f"字段已{'加密' if field_crypto.enabled else '明文'}写入",
        )
        db.add(audit)
        await db.flush()

        logger.info(
            "敏感字段写入",
            employee_id=employee_id,
            field=field_name,
            encrypted=field_crypto.enabled,
            operator=operator_id,
        )

        return {
            "employee_id": employee_id,
            "field_name": field_name,
            "status": "ok",
        }

    # ── 解密读取 ────────────────────────────────────────

    async def get_sensitive_field(
        self,
        db: AsyncSession,
        employee_id: str,
        field_name: str,
        operator_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> str:
        """解密读取敏感字段 + 记录审计日志

        Returns:
            解密后的明文值
        """
        self._validate_field(field_name)
        employee = await self._get_employee(db, employee_id)

        raw_value = getattr(employee, field_name, None) or ""
        plaintext = field_crypto.decrypt(raw_value)

        # 审计日志
        audit = SensitiveDataAuditLog(
            operator_id=operator_id,
            employee_id=employee_id,
            field_name=field_name,
            action="read",
            ip_address=ip_address,
            user_agent=user_agent,
            store_id=employee.store_id,
        )
        db.add(audit)
        await db.flush()

        logger.info(
            "敏感字段读取",
            employee_id=employee_id,
            field=field_name,
            operator=operator_id,
        )

        return plaintext

    # ── 脱敏读取（列表展示，不审计） ─────────────────────

    async def get_masked_field(
        self,
        db: AsyncSession,
        employee_id: str,
        field_name: str,
    ) -> str:
        """获取脱敏后的字段值（不记录审计，用于列表展示）"""
        self._validate_field(field_name)
        employee = await self._get_employee(db, employee_id)

        raw_value = getattr(employee, field_name, None) or ""
        plaintext = field_crypto.decrypt(raw_value)
        mask_type = _SENSITIVE_FIELDS[field_name]
        return field_crypto.mask(plaintext, mask_type)

    async def get_all_masked(
        self,
        db: AsyncSession,
        employee_id: str,
    ) -> dict:
        """批量获取所有敏感字段的脱敏值（列表页用）"""
        employee = await self._get_employee(db, employee_id)
        result = {}
        for field_name, mask_type in _SENSITIVE_FIELDS.items():
            raw_value = getattr(employee, field_name, None) or ""
            plaintext = field_crypto.decrypt(raw_value)
            result[field_name] = field_crypto.mask(plaintext, mask_type)
        return result

    # ── 批量加密迁移 ────────────────────────────────────

    async def batch_encrypt_existing(
        self,
        db: AsyncSession,
        operator_id: str,
        store_id: Optional[str] = None,
        batch_size: int = 100,
    ) -> dict:
        """批量加密已有明文数据（一次性迁移用）

        只处理未加密的记录（不以 ENC: 开头），跳过空值和已加密值。

        Args:
            store_id: 按门店过滤（None=全部）
            batch_size: 每批处理数量

        Returns:
            {"total_scanned": N, "encrypted_count": M, "fields": {...}}
        """
        if not field_crypto.enabled:
            return {
                "total_scanned": 0,
                "encrypted_count": 0,
                "error": "FIELD_ENCRYPTION_KEY 未配置，无法执行加密迁移",
            }

        stmt = select(Employee)
        if store_id:
            stmt = stmt.where(Employee.store_id == store_id)

        result = await db.execute(stmt)
        employees = result.scalars().all()

        total_scanned = len(employees)
        encrypted_count = 0
        field_counts: dict[str, int] = {f: 0 for f in _SENSITIVE_FIELDS}

        for emp in employees:
            changed = False
            for field_name in _SENSITIVE_FIELDS:
                raw_value = getattr(emp, field_name, None)
                if not raw_value:
                    continue
                if field_crypto.is_encrypted(raw_value):
                    continue
                # 明文 → 加密
                encrypted = field_crypto.encrypt(raw_value)
                setattr(emp, field_name, encrypted)
                field_counts[field_name] += 1
                changed = True

            if changed:
                db.add(emp)
                encrypted_count += 1

        # 审计日志
        audit = SensitiveDataAuditLog(
            operator_id=operator_id,
            employee_id="BATCH",
            field_name="all",
            action="batch_encrypt",
            store_id=store_id or "ALL",
            detail=f"扫描 {total_scanned} 人，加密 {encrypted_count} 人",
        )
        db.add(audit)
        await db.flush()

        logger.info(
            "批量加密完成",
            total_scanned=total_scanned,
            encrypted_count=encrypted_count,
            field_counts=field_counts,
            store_id=store_id,
            operator=operator_id,
        )

        return {
            "total_scanned": total_scanned,
            "encrypted_count": encrypted_count,
            "fields": field_counts,
        }

    # ── 内部工具 ────────────────────────────────────────

    @staticmethod
    def _validate_field(field_name: str) -> None:
        if field_name not in _SENSITIVE_FIELDS:
            raise ValueError(f"不支持的敏感字段: {field_name}，" f"允许值: {list(_SENSITIVE_FIELDS.keys())}")

    @staticmethod
    async def _get_employee(db: AsyncSession, employee_id: str) -> Employee:
        stmt = select(Employee).where(Employee.id == employee_id)
        result = await db.execute(stmt)
        employee = result.scalar_one_or_none()
        if not employee:
            raise LookupError(f"员工不存在: {employee_id}")
        return employee


# 全局单例
sensitive_data_service = SensitiveDataService()
