"""
客户风控 Service — Phase P1 (客必得能力)
客户归属管理、离职交接、流失预警扫描
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db_session
from src.models.customer_ownership import CustomerOwnership, CustomerRiskAlert, RiskLevel, RiskType, TransferReason
from src.models.reservation import Reservation, ReservationStatus

logger = structlog.get_logger()


class CustomerRiskService:
    """客户归属与风控管理"""

    # ── 客户归属 ──────────────────────────────────────────

    async def assign_customer(
        self,
        session: AsyncSession,
        store_id: str,
        customer_phone: str,
        customer_name: str,
        owner_employee_id: str,
    ) -> Dict[str, Any]:
        """分配客户归属"""
        # 检查是否已有归属
        existing = await session.execute(
            select(CustomerOwnership).where(
                and_(
                    CustomerOwnership.store_id == store_id,
                    CustomerOwnership.customer_phone == customer_phone,
                    CustomerOwnership.is_active == True,
                )
            )
        )
        old = existing.scalar_one_or_none()
        if old:
            # 自动转移
            old.is_active = False
            old.transferred_at = datetime.utcnow()

        ownership = CustomerOwnership(
            id=uuid.uuid4(),
            store_id=store_id,
            customer_phone=customer_phone,
            customer_name=customer_name,
            owner_employee_id=owner_employee_id,
            transferred_from=old.owner_employee_id if old else None,
            transfer_reason=TransferReason.MANUAL if old else None,
        )
        session.add(ownership)
        await session.flush()
        logger.info("customer_assigned", phone=customer_phone, owner=owner_employee_id)
        return self._ownership_to_dict(ownership)

    async def transfer_customers(
        self,
        session: AsyncSession,
        store_id: str,
        from_employee_id: str,
        to_employee_id: str,
        reason: str = "resignation",
    ) -> Dict[str, Any]:
        """批量交接客户（离职场景）"""
        result = await session.execute(
            select(CustomerOwnership).where(
                and_(
                    CustomerOwnership.store_id == store_id,
                    CustomerOwnership.owner_employee_id == from_employee_id,
                    CustomerOwnership.is_active == True,
                )
            )
        )
        records = list(result.scalars().all())

        now = datetime.utcnow()
        transferred_count = 0
        for r in records:
            r.is_active = False
            r.transferred_at = now

            new_ownership = CustomerOwnership(
                id=uuid.uuid4(),
                store_id=store_id,
                customer_phone=r.customer_phone,
                customer_name=r.customer_name,
                owner_employee_id=to_employee_id,
                transferred_from=from_employee_id,
                transferred_at=now,
                transfer_reason=TransferReason(reason),
                total_visits=r.total_visits,
                total_spent=r.total_spent,
                last_visit_at=r.last_visit_at,
                customer_level=r.customer_level,
            )
            session.add(new_ownership)
            transferred_count += 1

        await session.flush()
        logger.info(
            "customers_transferred", from_employee=from_employee_id, to_employee=to_employee_id, count=transferred_count
        )

        return {
            "transferred_count": transferred_count,
            "from_employee_id": from_employee_id,
            "to_employee_id": to_employee_id,
            "reason": reason,
        }

    async def list_ownership(
        self,
        session: AsyncSession,
        store_id: str,
        employee_id: Optional[str] = None,
        level: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """查询客户归属列表"""
        query = select(CustomerOwnership).where(
            and_(
                CustomerOwnership.store_id == store_id,
                CustomerOwnership.is_active == True,
            )
        )
        if employee_id:
            query = query.where(CustomerOwnership.owner_employee_id == employee_id)
        if level:
            query = query.where(CustomerOwnership.customer_level == level)
        query = query.order_by(CustomerOwnership.total_spent.desc())

        result = await session.execute(query)
        return [self._ownership_to_dict(r) for r in result.scalars().all()]

    async def get_employee_stats(
        self,
        session: AsyncSession,
        store_id: str,
    ) -> List[Dict[str, Any]]:
        """各销售的客户统计"""
        query = (
            select(
                CustomerOwnership.owner_employee_id,
                func.count().label("customer_count"),
                func.sum(CustomerOwnership.total_spent).label("total_revenue"),
                func.avg(CustomerOwnership.total_visits).label("avg_visits"),
            )
            .where(
                and_(
                    CustomerOwnership.store_id == store_id,
                    CustomerOwnership.is_active == True,
                )
            )
            .group_by(CustomerOwnership.owner_employee_id)
            .order_by(func.sum(CustomerOwnership.total_spent).desc())
        )
        result = await session.execute(query)
        return [
            {
                "employee_id": r.owner_employee_id,
                "customer_count": r.customer_count,
                "total_revenue_yuan": round(float(r.total_revenue or 0) / 100, 2),
                "avg_visits": round(float(r.avg_visits or 0), 1),
            }
            for r in result.all()
        ]

    # ── 流失预警 ──────────────────────────────────────────

    async def scan_risk_customers(
        self,
        session: AsyncSession,
        store_id: str,
        dormant_days: int = 30,
    ) -> Dict[str, Any]:
        """扫描流失风险客户（定时任务调用）"""
        now = datetime.utcnow()
        cutoff = now - timedelta(days=dormant_days)

        # 找出超过 dormant_days 未消费的客户
        query = select(CustomerOwnership).where(
            and_(
                CustomerOwnership.store_id == store_id,
                CustomerOwnership.is_active == True,
                or_(
                    CustomerOwnership.last_visit_at < cutoff,
                    CustomerOwnership.last_visit_at.is_(None),
                ),
            )
        )
        result = await session.execute(query)
        at_risk = list(result.scalars().all())

        alerts_created = 0
        for customer in at_risk:
            days_since = (now - customer.last_visit_at).days if customer.last_visit_at else 999

            # 风险等级判定
            if days_since >= 90:
                risk_level = RiskLevel.HIGH
                churn_prob = 0.85
            elif days_since >= 60:
                risk_level = RiskLevel.HIGH
                churn_prob = 0.65
            elif days_since >= dormant_days:
                risk_level = RiskLevel.MEDIUM
                churn_prob = 0.40
            else:
                continue

            # 检查是否已有未解决的预警
            existing = await session.execute(
                select(CustomerRiskAlert).where(
                    and_(
                        CustomerRiskAlert.store_id == store_id,
                        CustomerRiskAlert.customer_phone == customer.customer_phone,
                        CustomerRiskAlert.is_resolved == False,
                    )
                )
            )
            if existing.scalar_one_or_none():
                continue

            # 生成AI建议
            if customer.customer_level in ("VIP", "GOLD"):
                suggested_action = f"高价值客户{days_since}天未到店，建议店长亲自致电关怀，赠送专属优惠券"
                suggested_offer = "满300减80专属券"
            else:
                suggested_action = f"客户{days_since}天未消费，建议发送唤醒短信+优惠券"
                suggested_offer = "满200减30回归券"

            alert = CustomerRiskAlert(
                id=uuid.uuid4(),
                store_id=store_id,
                customer_phone=customer.customer_phone,
                customer_name=customer.customer_name,
                risk_level=risk_level,
                risk_type=RiskType.DORMANT,
                risk_score=churn_prob,
                last_visit_days=days_since,
                predicted_churn_probability=churn_prob,
                suggested_action=suggested_action,
                suggested_offer=suggested_offer,
            )
            session.add(alert)
            alerts_created += 1

        await session.flush()
        logger.info("risk_scan_complete", store_id=store_id, alerts_created=alerts_created)
        return {
            "store_id": store_id,
            "scanned_customers": len(at_risk),
            "alerts_created": alerts_created,
        }

    async def list_risk_alerts(
        self,
        session: AsyncSession,
        store_id: str,
        risk_level: Optional[str] = None,
        unresolved_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """查询流失预警列表"""
        query = select(CustomerRiskAlert).where(CustomerRiskAlert.store_id == store_id)
        if unresolved_only:
            query = query.where(CustomerRiskAlert.is_resolved == False)
        if risk_level:
            query = query.where(CustomerRiskAlert.risk_level == RiskLevel(risk_level))
        query = query.order_by(CustomerRiskAlert.risk_score.desc())

        result = await session.execute(query)
        return [self._alert_to_dict(a) for a in result.scalars().all()]

    async def resolve_alert(
        self,
        session: AsyncSession,
        alert_id: str,
        action_by: str,
        action_result: str,
    ) -> Dict[str, Any]:
        """标记预警已处理"""
        result = await session.execute(select(CustomerRiskAlert).where(CustomerRiskAlert.id == alert_id))
        alert = result.scalar_one_or_none()
        if not alert:
            raise ValueError(f"预警不存在: {alert_id}")

        alert.action_taken = True
        alert.action_taken_at = datetime.utcnow()
        alert.action_by = action_by
        alert.action_result = action_result
        alert.is_resolved = True

        await session.flush()
        logger.info("alert_resolved", alert_id=str(alert_id), action_by=action_by)
        return self._alert_to_dict(alert)

    # ── 辅助方法 ──────────────────────────────────────────

    def _ownership_to_dict(self, r: CustomerOwnership) -> Dict[str, Any]:
        return {
            "id": str(r.id),
            "store_id": r.store_id,
            "customer_phone": r.customer_phone,
            "customer_name": r.customer_name,
            "owner_employee_id": r.owner_employee_id,
            "customer_level": r.customer_level,
            "total_visits": r.total_visits,
            "total_spent_yuan": round(float(r.total_spent or 0) / 100, 2),
            "last_visit_at": r.last_visit_at.isoformat() if r.last_visit_at else None,
            "assigned_at": r.assigned_at.isoformat() if r.assigned_at else None,
            "transferred_from": r.transferred_from,
            "transfer_reason": r.transfer_reason.value if r.transfer_reason else None,
        }

    def _alert_to_dict(self, a: CustomerRiskAlert) -> Dict[str, Any]:
        return {
            "id": str(a.id),
            "store_id": a.store_id,
            "customer_phone": a.customer_phone,
            "customer_name": a.customer_name,
            "risk_level": a.risk_level.value if hasattr(a.risk_level, "value") else str(a.risk_level),
            "risk_type": a.risk_type.value if hasattr(a.risk_type, "value") else str(a.risk_type),
            "risk_score": a.risk_score,
            "last_visit_days": a.last_visit_days,
            "predicted_churn_probability": a.predicted_churn_probability,
            "suggested_action": a.suggested_action,
            "suggested_offer": a.suggested_offer,
            "action_taken": a.action_taken,
            "action_result": a.action_result,
            "is_resolved": a.is_resolved,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }


customer_risk_service = CustomerRiskService()
