"""
合规证照服务
Compliance Service

核心职责：
- 证照 CRUD
- 到期状态自动计算
- 扫描即将到期/已过期证照
- 触发 compliance.* 事件到神经系统
"""
import uuid
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.core.database import get_db_session
from src.models.compliance import ComplianceLicense, LicenseType, LicenseStatus

logger = structlog.get_logger()

# 提醒阈值（天）
REMIND_THRESHOLDS = [30, 15, 7]


def _compute_status(expiry_date: date, remind_days: int = 30) -> LicenseStatus:
    """根据到期日计算当前状态"""
    today = date.today()
    if expiry_date < today:
        return LicenseStatus.EXPIRED
    if (expiry_date - today).days <= remind_days:
        return LicenseStatus.EXPIRE_SOON
    return LicenseStatus.VALID


class ComplianceService:
    """合规证照服务"""

    async def create_license(
        self,
        store_id: str,
        license_type: LicenseType,
        license_name: str,
        expiry_date: date,
        license_number: Optional[str] = None,
        holder_name: Optional[str] = None,
        holder_employee_id: Optional[str] = None,
        issue_date: Optional[date] = None,
        remind_days_before: int = 30,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """新增证照记录"""
        async with get_db_session() as session:
            license_obj = ComplianceLicense(
                id=str(uuid.uuid4()),
                store_id=store_id,
                license_type=license_type,
                license_name=license_name,
                license_number=license_number,
                holder_name=holder_name,
                holder_employee_id=holder_employee_id,
                issue_date=issue_date,
                expiry_date=expiry_date,
                status=_compute_status(expiry_date, remind_days_before),
                remind_days_before=remind_days_before,
                notes=notes,
            )
            session.add(license_obj)
            await session.commit()
            await session.refresh(license_obj)
            logger.info("compliance_license_created", id=license_obj.id, store_id=store_id)
            return license_obj.to_dict()

    async def list_licenses(
        self,
        store_id: Optional[str] = None,
        status: Optional[LicenseStatus] = None,
        license_type: Optional[LicenseType] = None,
    ) -> List[Dict[str, Any]]:
        """查询证照列表"""
        async with get_db_session() as session:
            filters = []
            if store_id:
                filters.append(ComplianceLicense.store_id == store_id)
            if status:
                filters.append(ComplianceLicense.status == status)
            if license_type:
                filters.append(ComplianceLicense.license_type == license_type)

            result = await session.execute(
                select(ComplianceLicense)
                .where(and_(*filters) if filters else True)
                .order_by(ComplianceLicense.expiry_date.asc())
            )
            return [r.to_dict() for r in result.scalars().all()]

    async def update_license(
        self,
        license_id: str,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """更新证照信息"""
        async with get_db_session() as session:
            result = await session.execute(
                select(ComplianceLicense).where(ComplianceLicense.id == license_id)
            )
            license_obj = result.scalar_one_or_none()
            if not license_obj:
                return None

            for key, value in kwargs.items():
                if hasattr(license_obj, key) and value is not None:
                    setattr(license_obj, key, value)

            # 重新计算状态
            license_obj.status = _compute_status(
                license_obj.expiry_date, license_obj.remind_days_before
            )
            await session.commit()
            await session.refresh(license_obj)
            return license_obj.to_dict()

    async def delete_license(self, license_id: str) -> bool:
        """删除证照记录"""
        async with get_db_session() as session:
            result = await session.execute(
                select(ComplianceLicense).where(ComplianceLicense.id == license_id)
            )
            license_obj = result.scalar_one_or_none()
            if not license_obj:
                return False
            await session.delete(license_obj)
            await session.commit()
            return True

    async def scan_expiring(
        self,
        store_id: Optional[str] = None,
        horizon_days: int = 30,
    ) -> Dict[str, Any]:
        """
        扫描即将到期和已过期的证照。

        由 Celery 定时任务或 ComplianceAgent 调用。
        返回需要提醒的证照列表，并更新状态字段。
        """
        today = date.today()
        horizon = today + timedelta(days=horizon_days)

        async with get_db_session() as session:
            filters = [ComplianceLicense.expiry_date <= horizon]
            if store_id:
                filters.append(ComplianceLicense.store_id == store_id)

            result = await session.execute(
                select(ComplianceLicense)
                .where(and_(*filters))
                .order_by(ComplianceLicense.expiry_date.asc())
            )
            licenses = result.scalars().all()

            expired = []
            expiring = []

            for lic in licenses:
                new_status = _compute_status(lic.expiry_date, lic.remind_days_before)
                if lic.status != new_status:
                    lic.status = new_status

                days_left = (lic.expiry_date - today).days
                entry = {**lic.to_dict(), "days_left": days_left}

                if new_status == LicenseStatus.EXPIRED:
                    expired.append(entry)
                else:
                    expiring.append(entry)

            await session.commit()

        logger.info(
            "compliance_scan_complete",
            expired=len(expired),
            expiring=len(expiring),
            store_id=store_id,
        )

        return {
            "scanned_at": datetime.utcnow().isoformat(),
            "store_id": store_id,
            "expired": expired,
            "expiring_soon": expiring,
            "total_alerts": len(expired) + len(expiring),
        }
