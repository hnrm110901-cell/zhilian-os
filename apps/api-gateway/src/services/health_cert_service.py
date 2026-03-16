"""健康证服务 — 录入/查询/到期预警/状态批量更新"""

import uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class HealthCertService:

    @staticmethod
    async def create_certificate(
        session: AsyncSession,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """创建健康证记录"""
        from src.models.health_certificate import HealthCertificate

        # 根据到期日期自动判定初始状态
        expiry = data["expiry_date"]
        today = date.today()
        if expiry < today:
            status = "expired"
        elif (expiry - today).days <= 30:
            status = "expiring_soon"
        else:
            status = "valid"

        cert = HealthCertificate(
            id=uuid.uuid4(),
            brand_id=data["brand_id"],
            store_id=data["store_id"],
            employee_id=data["employee_id"],
            employee_name=data["employee_name"],
            certificate_number=data.get("certificate_number"),
            issue_date=data["issue_date"],
            expiry_date=expiry,
            issuing_authority=data.get("issuing_authority"),
            certificate_image_url=data.get("certificate_image_url"),
            status=status,
            physical_exam_date=data.get("physical_exam_date"),
            physical_exam_result=data.get("physical_exam_result"),
            notes=data.get("notes"),
        )
        session.add(cert)
        await session.flush()
        logger.info("health_cert.created", cert_id=str(cert.id), employee=cert.employee_name)
        return {
            "id": str(cert.id),
            "status": cert.status,
            "employee_name": cert.employee_name,
        }

    @staticmethod
    async def update_certificate(
        session: AsyncSession,
        cert_id: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """更新健康证记录"""
        from src.models.health_certificate import HealthCertificate

        result = await session.execute(select(HealthCertificate).where(HealthCertificate.id == uuid.UUID(cert_id)))
        cert = result.scalar_one_or_none()
        if not cert:
            raise ValueError("健康证记录不存在")

        updatable_fields = [
            "employee_name",
            "certificate_number",
            "issue_date",
            "expiry_date",
            "issuing_authority",
            "certificate_image_url",
            "status",
            "physical_exam_date",
            "physical_exam_result",
            "notes",
            "store_id",
        ]
        for field in updatable_fields:
            if field in data:
                setattr(cert, field, data[field])

        # 如果更新了到期日期且未手动设置状态，自动重新判定
        if "expiry_date" in data and "status" not in data:
            today = date.today()
            expiry = data["expiry_date"]
            if expiry < today:
                cert.status = "expired"
            elif (expiry - today).days <= 30:
                cert.status = "expiring_soon"
            else:
                cert.status = "valid"

        await session.flush()
        return {"id": str(cert.id), "status": cert.status}

    @staticmethod
    async def list_certificates(
        session: AsyncSession,
        brand_id: str,
        store_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        status: Optional[str] = None,
        employee_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分页查询健康证列表"""
        from src.models.health_certificate import HealthCertificate

        query = select(HealthCertificate).where(HealthCertificate.brand_id == brand_id)
        count_query = select(func.count(HealthCertificate.id)).where(HealthCertificate.brand_id == brand_id)

        if store_id:
            query = query.where(HealthCertificate.store_id == store_id)
            count_query = count_query.where(HealthCertificate.store_id == store_id)
        if status:
            query = query.where(HealthCertificate.status == status)
            count_query = count_query.where(HealthCertificate.status == status)
        if employee_name:
            query = query.where(HealthCertificate.employee_name.contains(employee_name))
            count_query = count_query.where(HealthCertificate.employee_name.contains(employee_name))

        # 总数
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        # 分页数据
        offset = (page - 1) * page_size
        query = query.order_by(HealthCertificate.expiry_date.asc()).limit(page_size).offset(offset)
        result = await session.execute(query)
        certs = result.scalars().all()

        today = date.today()
        items = []
        for c in certs:
            days_remaining = (c.expiry_date - today).days if c.expiry_date else 0
            items.append(
                {
                    "id": str(c.id),
                    "brand_id": c.brand_id,
                    "store_id": c.store_id,
                    "employee_id": c.employee_id,
                    "employee_name": c.employee_name,
                    "certificate_number": c.certificate_number,
                    "issue_date": c.issue_date.isoformat() if c.issue_date else None,
                    "expiry_date": c.expiry_date.isoformat() if c.expiry_date else None,
                    "issuing_authority": c.issuing_authority,
                    "certificate_image_url": c.certificate_image_url,
                    "status": c.status,
                    "days_remaining": days_remaining,
                    "physical_exam_date": c.physical_exam_date.isoformat() if c.physical_exam_date else None,
                    "physical_exam_result": c.physical_exam_result,
                    "notes": c.notes,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
            )

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    async def get_certificate(session: AsyncSession, cert_id: str) -> Dict[str, Any]:
        """获取健康证详情"""
        from src.models.health_certificate import HealthCertificate

        result = await session.execute(select(HealthCertificate).where(HealthCertificate.id == uuid.UUID(cert_id)))
        cert = result.scalar_one_or_none()
        if not cert:
            raise ValueError("健康证记录不存在")

        today = date.today()
        days_remaining = (cert.expiry_date - today).days if cert.expiry_date else 0
        return {
            "id": str(cert.id),
            "brand_id": cert.brand_id,
            "store_id": cert.store_id,
            "employee_id": cert.employee_id,
            "employee_name": cert.employee_name,
            "certificate_number": cert.certificate_number,
            "issue_date": cert.issue_date.isoformat() if cert.issue_date else None,
            "expiry_date": cert.expiry_date.isoformat() if cert.expiry_date else None,
            "issuing_authority": cert.issuing_authority,
            "certificate_image_url": cert.certificate_image_url,
            "status": cert.status,
            "days_remaining": days_remaining,
            "physical_exam_date": cert.physical_exam_date.isoformat() if cert.physical_exam_date else None,
            "physical_exam_result": cert.physical_exam_result,
            "notes": cert.notes,
            "created_at": cert.created_at.isoformat() if cert.created_at else None,
            "updated_at": cert.updated_at.isoformat() if cert.updated_at else None,
        }

    @staticmethod
    async def check_expiring(session: AsyncSession, brand_id: str, days_ahead: int = 30) -> List[Dict[str, Any]]:
        """查询即将到期的健康证（N天内到期）"""
        from src.models.health_certificate import HealthCertificate

        today = date.today()
        deadline = today + timedelta(days=days_ahead)
        result = await session.execute(
            select(HealthCertificate)
            .where(
                HealthCertificate.brand_id == brand_id,
                HealthCertificate.expiry_date <= deadline,
                HealthCertificate.expiry_date >= today,
                HealthCertificate.status.in_(["valid", "expiring_soon"]),
            )
            .order_by(HealthCertificate.expiry_date.asc())
        )
        certs = result.scalars().all()
        return [
            {
                "id": str(c.id),
                "employee_name": c.employee_name,
                "store_id": c.store_id,
                "expiry_date": c.expiry_date.isoformat(),
                "days_remaining": (c.expiry_date - today).days,
                "status": c.status,
            }
            for c in certs
        ]

    @staticmethod
    async def get_expired(session: AsyncSession, brand_id: str) -> List[Dict[str, Any]]:
        """查询所有已过期健康证"""
        from src.models.health_certificate import HealthCertificate

        today = date.today()
        result = await session.execute(
            select(HealthCertificate)
            .where(
                HealthCertificate.brand_id == brand_id,
                HealthCertificate.expiry_date < today,
                HealthCertificate.status != "revoked",
            )
            .order_by(HealthCertificate.expiry_date.asc())
        )
        certs = result.scalars().all()
        return [
            {
                "id": str(c.id),
                "employee_name": c.employee_name,
                "store_id": c.store_id,
                "expiry_date": c.expiry_date.isoformat(),
                "days_overdue": (today - c.expiry_date).days,
                "status": c.status,
            }
            for c in certs
        ]

    @staticmethod
    async def auto_update_status(session: AsyncSession, brand_id: str) -> Dict[str, Any]:
        """批量更新健康证状态：valid→expiring_soon（<30天）、expiring_soon→expired（已过期）"""
        from src.models.health_certificate import HealthCertificate

        today = date.today()
        soon_threshold = today + timedelta(days=30)

        # valid → expiring_soon（30天内到期）
        res1 = await session.execute(
            update(HealthCertificate)
            .where(
                HealthCertificate.brand_id == brand_id,
                HealthCertificate.status == "valid",
                HealthCertificate.expiry_date <= soon_threshold,
                HealthCertificate.expiry_date >= today,
            )
            .values(status="expiring_soon")
        )
        to_expiring = res1.rowcount

        # valid / expiring_soon → expired（已过期）
        res2 = await session.execute(
            update(HealthCertificate)
            .where(
                HealthCertificate.brand_id == brand_id,
                HealthCertificate.status.in_(["valid", "expiring_soon"]),
                HealthCertificate.expiry_date < today,
            )
            .values(status="expired")
        )
        to_expired = res2.rowcount

        await session.flush()
        logger.info(
            "health_cert.auto_update",
            brand_id=brand_id,
            to_expiring=to_expiring,
            to_expired=to_expired,
        )
        return {
            "updated_to_expiring_soon": to_expiring,
            "updated_to_expired": to_expired,
        }

    @staticmethod
    async def get_stats(session: AsyncSession, brand_id: str) -> Dict[str, Any]:
        """健康证统计：有效/即将到期/已过期数量 + 合规率"""
        from src.models.health_certificate import HealthCertificate

        result = await session.execute(
            select(
                HealthCertificate.status,
                func.count(HealthCertificate.id).label("count"),
            )
            .where(HealthCertificate.brand_id == brand_id)
            .group_by(HealthCertificate.status)
        )
        rows = result.all()
        counts: Dict[str, int] = {r.status: r.count for r in rows}

        valid = counts.get("valid", 0)
        expiring_soon = counts.get("expiring_soon", 0)
        expired = counts.get("expired", 0)
        revoked = counts.get("revoked", 0)
        total = valid + expiring_soon + expired + revoked

        compliance_rate = round((valid + expiring_soon) / total * 100, 1) if total > 0 else 100.0

        return {
            "valid": valid,
            "expiring_soon": expiring_soon,
            "expired": expired,
            "revoked": revoked,
            "total": total,
            "compliance_rate": compliance_rate,
        }

    @staticmethod
    async def delete_certificate(session: AsyncSession, cert_id: str) -> Dict[str, Any]:
        """删除健康证记录"""
        from src.models.health_certificate import HealthCertificate

        result = await session.execute(select(HealthCertificate).where(HealthCertificate.id == uuid.UUID(cert_id)))
        cert = result.scalar_one_or_none()
        if not cert:
            raise ValueError("健康证记录不存在")

        await session.delete(cert)
        await session.flush()
        logger.info("health_cert.deleted", cert_id=cert_id)
        return {"id": cert_id, "deleted": True}
