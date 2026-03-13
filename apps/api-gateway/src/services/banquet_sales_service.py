"""
宴会销控 Service — Phase P2 (宴荟佳能力)
档期管理 · 销售漏斗 · 竞对分析 · 动态定价建议
"""
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import select, func, and_, case, update
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import structlog

from src.core.database import get_db_session
from src.models.banquet_sales import (
    BanquetDateConfig, AuspiciousLevel, DateBookingStatus,
    SalesFunnelRecord, FunnelStage,
    BanquetCompetitor,
)

logger = structlog.get_logger()


class BanquetSalesService:
    """宴会销控引擎"""

    # ── 档期管理 ──────────────────────────────────────────

    async def configure_date(
        self,
        session: AsyncSession,
        store_id: str,
        target_date: date,
        auspicious_level: str = "normal",
        price_multiplier: float = 1.0,
        max_tables: Optional[int] = None,
        hall_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """配置档期（吉日等级+定价系数）"""
        # 查找已有配置
        existing = await session.execute(
            select(BanquetDateConfig).where(and_(
                BanquetDateConfig.store_id == store_id,
                BanquetDateConfig.target_date == target_date,
                BanquetDateConfig.hall_id == hall_id,
            ))
        )
        config = existing.scalar_one_or_none()

        if config:
            config.auspicious_level = AuspiciousLevel(auspicious_level)
            config.price_multiplier = price_multiplier
            if max_tables is not None:
                config.max_tables = max_tables
            if notes:
                config.notes = notes
        else:
            config = BanquetDateConfig(
                id=uuid.uuid4(),
                store_id=store_id,
                hall_id=hall_id,
                target_date=target_date,
                auspicious_level=AuspiciousLevel(auspicious_level),
                price_multiplier=price_multiplier,
                max_tables=max_tables,
                notes=notes,
            )
            session.add(config)

        await session.flush()
        return self._date_config_to_dict(config)

    async def get_calendar(
        self,
        session: AsyncSession,
        store_id: str,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        """获取档期日历（销控看板核心数据）"""
        query = (
            select(BanquetDateConfig)
            .where(and_(
                BanquetDateConfig.store_id == store_id,
                BanquetDateConfig.target_date >= start_date,
                BanquetDateConfig.target_date <= end_date,
            ))
            .order_by(BanquetDateConfig.target_date)
        )
        result = await session.execute(query)
        return [self._date_config_to_dict(c) for c in result.scalars().all()]

    async def lock_date(
        self,
        session: AsyncSession,
        store_id: str,
        target_date: date,
        reservation_id: str,
        lock_days: int = 7,
    ) -> Dict[str, Any]:
        """锁定档期（客户意向中）"""
        result = await session.execute(
            select(BanquetDateConfig).where(and_(
                BanquetDateConfig.store_id == store_id,
                BanquetDateConfig.target_date == target_date,
            ))
        )
        config = result.scalar_one_or_none()
        if not config:
            config = BanquetDateConfig(
                id=uuid.uuid4(),
                store_id=store_id,
                target_date=target_date,
            )
            session.add(config)

        config.booking_status = DateBookingStatus.LOCKED
        config.locked_by_reservation_id = reservation_id
        config.locked_at = datetime.utcnow()
        config.lock_expires_at = datetime.utcnow() + timedelta(days=lock_days)
        await session.flush()
        logger.info("date_locked", store_id=store_id, date=str(target_date), reservation=reservation_id)
        return self._date_config_to_dict(config)

    async def get_pricing_suggestion(
        self,
        session: AsyncSession,
        store_id: str,
        target_date: date,
        base_price_per_table: int,
    ) -> Dict[str, Any]:
        """AI动态定价建议"""
        result = await session.execute(
            select(BanquetDateConfig).where(and_(
                BanquetDateConfig.store_id == store_id,
                BanquetDateConfig.target_date == target_date,
            ))
        )
        config = result.scalar_one_or_none()

        multiplier = float(config.price_multiplier) if config else 1.0
        level = config.auspicious_level.value if config else "normal"
        booked = config.booked_tables if config else 0
        max_t = config.max_tables if config else 30

        # 去化率
        utilization = booked / max_t if max_t > 0 else 0

        # 动态调价逻辑
        if utilization >= 0.8:
            # 去化率高，可以涨价
            adjustment = 1.1
            reason = f"去化率{utilization*100:.0f}%，需求旺盛，建议适当上调"
        elif utilization <= 0.3 and (target_date - date.today()).days <= 30:
            # 去化率低且临近，建议降价
            adjustment = 0.9
            reason = f"去化率仅{utilization*100:.0f}%，距宴会日仅{(target_date - date.today()).days}天，建议促销"
        else:
            adjustment = 1.0
            reason = "去化率正常，维持当前定价"

        suggested_price = int(base_price_per_table * multiplier * adjustment)

        return {
            "store_id": store_id,
            "target_date": str(target_date),
            "auspicious_level": level,
            "base_multiplier": multiplier,
            "dynamic_adjustment": adjustment,
            "base_price_yuan": round(base_price_per_table / 100, 2),
            "suggested_price_yuan": round(suggested_price / 100, 2),
            "utilization_rate": round(utilization * 100, 1),
            "reason": reason,
        }

    # ── 销售漏斗 ──────────────────────────────────────────

    async def create_lead(
        self,
        session: AsyncSession,
        store_id: str,
        customer_name: str,
        customer_phone: str,
        event_type: Optional[str] = None,
        owner_employee_id: Optional[str] = None,
        target_date: Optional[date] = None,
        table_count: Optional[int] = None,
        estimated_value: int = 0,
    ) -> Dict[str, Any]:
        """创建销售线索"""
        record = SalesFunnelRecord(
            id=uuid.uuid4(),
            store_id=store_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            event_type=event_type,
            owner_employee_id=owner_employee_id,
            target_date=target_date,
            table_count=table_count,
            estimated_value=estimated_value,
            conversion_probability=0.15,  # 初始概率
        )
        session.add(record)
        await session.flush()
        logger.info("lead_created", store_id=store_id, customer=customer_name)
        return self._funnel_to_dict(record)

    async def advance_stage(
        self,
        session: AsyncSession,
        record_id: str,
        new_stage: str,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """推进漏斗阶段"""
        result = await session.execute(
            select(SalesFunnelRecord).where(SalesFunnelRecord.id == record_id)
        )
        record = result.scalar_one_or_none()
        if not record:
            raise ValueError(f"线索不存在: {record_id}")

        now = datetime.utcnow()

        # 记录跟进
        if note:
            notes = record.follow_up_notes or []
            notes.append({"time": now.isoformat(), "note": note, "stage": new_stage})
            record.follow_up_notes = notes
            record.follow_up_count = len(notes)
            record.last_follow_up_at = now

        # 计算停留时长
        if record.entered_stage_at:
            record.stage_duration_hours = int((now - record.entered_stage_at).total_seconds() / 3600)

        # 推进阶段
        record.current_stage = FunnelStage(new_stage)
        record.entered_stage_at = now

        # 更新AI转化概率
        stage_probs = {
            "lead": 0.15, "intent": 0.35, "room_lock": 0.55,
            "negotiation": 0.70, "signed": 0.95, "preparation": 0.98,
            "completed": 1.0, "lost": 0.0,
        }
        record.conversion_probability = stage_probs.get(new_stage, 0.5)

        await session.flush()
        logger.info("stage_advanced", record_id=str(record_id), new_stage=new_stage)
        return self._funnel_to_dict(record)

    async def get_funnel_stats(
        self,
        session: AsyncSession,
        store_id: str,
    ) -> Dict[str, Any]:
        """漏斗统计（各阶段数量+金额）"""
        query = (
            select(
                SalesFunnelRecord.current_stage,
                func.count().label('count'),
                func.sum(SalesFunnelRecord.estimated_value).label('total_value'),
                func.avg(SalesFunnelRecord.conversion_probability).label('avg_prob'),
            )
            .where(SalesFunnelRecord.store_id == store_id)
            .group_by(SalesFunnelRecord.current_stage)
        )
        result = await session.execute(query)
        stages = []
        for r in result.all():
            stages.append({
                "stage": r.current_stage.value if hasattr(r.current_stage, 'value') else str(r.current_stage),
                "count": r.count,
                "total_value_yuan": round(float(r.total_value or 0) / 100, 2),
                "avg_probability": round(float(r.avg_prob or 0) * 100, 1),
            })
        return {"store_id": store_id, "stages": stages}

    async def list_funnel(
        self,
        session: AsyncSession,
        store_id: str,
        stage: Optional[str] = None,
        employee_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """查询漏斗列表"""
        query = select(SalesFunnelRecord).where(SalesFunnelRecord.store_id == store_id)
        if stage:
            query = query.where(SalesFunnelRecord.current_stage == FunnelStage(stage))
        if employee_id:
            query = query.where(SalesFunnelRecord.owner_employee_id == employee_id)
        query = query.order_by(SalesFunnelRecord.conversion_probability.desc())

        result = await session.execute(query)
        return [self._funnel_to_dict(r) for r in result.scalars().all()]

    async def mark_lost(
        self,
        session: AsyncSession,
        record_id: str,
        lost_reason: str,
        lost_to_competitor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """标记输单"""
        result = await session.execute(
            select(SalesFunnelRecord).where(SalesFunnelRecord.id == record_id)
        )
        record = result.scalar_one_or_none()
        if not record:
            raise ValueError(f"线索不存在: {record_id}")

        record.current_stage = FunnelStage.LOST
        record.conversion_probability = 0.0
        record.lost_reason = lost_reason
        record.lost_to_competitor = lost_to_competitor

        # 更新竞对数据
        if lost_to_competitor:
            comp_result = await session.execute(
                select(BanquetCompetitor).where(and_(
                    BanquetCompetitor.store_id == record.store_id,
                    BanquetCompetitor.competitor_name == lost_to_competitor,
                ))
            )
            competitor = comp_result.scalar_one_or_none()
            if competitor:
                competitor.lost_deals_count += 1
                reasons = competitor.common_lost_reasons or []
                if lost_reason not in reasons:
                    reasons.append(lost_reason)
                competitor.common_lost_reasons = reasons
            else:
                new_comp = BanquetCompetitor(
                    id=uuid.uuid4(),
                    store_id=record.store_id,
                    competitor_name=lost_to_competitor,
                    lost_deals_count=1,
                    common_lost_reasons=[lost_reason],
                )
                session.add(new_comp)

        await session.flush()
        return self._funnel_to_dict(record)

    # ── 竞对分析 ──────────────────────────────────────────

    async def list_competitors(
        self,
        session: AsyncSession,
        store_id: str,
    ) -> List[Dict[str, Any]]:
        """竞对列表"""
        result = await session.execute(
            select(BanquetCompetitor)
            .where(BanquetCompetitor.store_id == store_id)
            .order_by(BanquetCompetitor.lost_deals_count.desc())
        )
        return [self._competitor_to_dict(c) for c in result.scalars().all()]

    # ── 辅助方法 ──────────────────────────────────────────

    def _date_config_to_dict(self, c: BanquetDateConfig) -> Dict[str, Any]:
        return {
            "id": str(c.id),
            "store_id": c.store_id,
            "target_date": str(c.target_date),
            "auspicious_level": c.auspicious_level.value if hasattr(c.auspicious_level, 'value') else str(c.auspicious_level),
            "price_multiplier": float(c.price_multiplier) if c.price_multiplier else 1.0,
            "booking_status": c.booking_status.value if hasattr(c.booking_status, 'value') else str(c.booking_status),
            "max_tables": c.max_tables,
            "booked_tables": c.booked_tables,
            "notes": c.notes,
        }

    def _funnel_to_dict(self, r: SalesFunnelRecord) -> Dict[str, Any]:
        return {
            "id": str(r.id),
            "store_id": r.store_id,
            "customer_name": r.customer_name,
            "customer_phone": r.customer_phone,
            "event_type": r.event_type,
            "current_stage": r.current_stage.value if hasattr(r.current_stage, 'value') else str(r.current_stage),
            "owner_employee_id": r.owner_employee_id,
            "follow_up_count": r.follow_up_count,
            "conversion_probability": r.conversion_probability,
            "estimated_value_yuan": round(float(r.estimated_value or 0) / 100, 2),
            "target_date": str(r.target_date) if r.target_date else None,
            "table_count": r.table_count,
            "lost_reason": r.lost_reason,
            "lost_to_competitor": r.lost_to_competitor,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

    def _competitor_to_dict(self, c: BanquetCompetitor) -> Dict[str, Any]:
        return {
            "id": str(c.id),
            "store_id": c.store_id,
            "competitor_name": c.competitor_name,
            "price_range_yuan": f"¥{(c.competitor_price_min or 0)/100:.0f}-¥{(c.competitor_price_max or 0)/100:.0f}/桌",
            "lost_deals_count": c.lost_deals_count,
            "won_deals_count": c.won_deals_count,
            "common_lost_reasons": c.common_lost_reasons or [],
        }


banquet_sales_service = BanquetSalesService()
