"""
渠道分析 Service — Phase P1 (易订PRO能力)
渠道来源统计、转化率分析、佣金成本分析
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db_session
from src.models.reservation import Reservation, ReservationStatus
from src.models.reservation_channel import ChannelType, ReservationChannel

logger = structlog.get_logger()


class ChannelAnalyticsService:
    """预订渠道分析"""

    async def record_channel(
        self,
        session: AsyncSession,
        reservation_id: str,
        store_id: str,
        channel: str,
        external_order_id: Optional[str] = None,
        commission_rate: Optional[float] = None,
        utm_source: Optional[str] = None,
        utm_medium: Optional[str] = None,
        utm_campaign: Optional[str] = None,
    ) -> Dict[str, Any]:
        """记录预订渠道来源"""
        record = ReservationChannel(
            id=uuid.uuid4(),
            reservation_id=reservation_id,
            store_id=store_id,
            channel=ChannelType(channel),
            external_order_id=external_order_id,
            channel_commission_rate=commission_rate,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
        )
        session.add(record)
        await session.flush()
        logger.info("channel_recorded", reservation_id=reservation_id, channel=channel)
        return self._to_dict(record)

    async def get_channel_stats(
        self,
        session: AsyncSession,
        store_id: str,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """渠道统计（各渠道订单量/占比/佣金成本）"""
        query = (
            select(
                ReservationChannel.channel,
                func.count().label("count"),
                func.sum(ReservationChannel.channel_commission_amount).label("total_commission"),
            )
            .where(
                and_(
                    ReservationChannel.store_id == store_id,
                    func.date(ReservationChannel.created_at) >= start_date,
                    func.date(ReservationChannel.created_at) <= end_date,
                )
            )
            .group_by(ReservationChannel.channel)
            .order_by(func.count().desc())
        )
        result = await session.execute(query)
        rows = result.all()

        total = sum(r.count for r in rows)
        channels = []
        for r in rows:
            channels.append(
                {
                    "channel": r.channel.value if hasattr(r.channel, "value") else str(r.channel),
                    "count": r.count,
                    "percentage": round(r.count / total * 100, 1) if total > 0 else 0,
                    "total_commission": float(r.total_commission or 0),
                }
            )

        return {
            "store_id": store_id,
            "period": f"{start_date} ~ {end_date}",
            "total_reservations": total,
            "channels": channels,
        }

    async def get_channel_conversion(
        self,
        session: AsyncSession,
        store_id: str,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        """各渠道转化率（预订→完成）"""
        # 各渠道的总预订数
        total_query = (
            select(
                ReservationChannel.channel,
                func.count().label("total"),
            )
            .where(
                and_(
                    ReservationChannel.store_id == store_id,
                    func.date(ReservationChannel.created_at) >= start_date,
                    func.date(ReservationChannel.created_at) <= end_date,
                )
            )
            .group_by(ReservationChannel.channel)
        )

        # 完成的预订数（JOIN reservation 表）
        completed_query = (
            select(
                ReservationChannel.channel,
                func.count().label("completed"),
            )
            .join(Reservation, Reservation.id == ReservationChannel.reservation_id)
            .where(
                and_(
                    ReservationChannel.store_id == store_id,
                    func.date(ReservationChannel.created_at) >= start_date,
                    func.date(ReservationChannel.created_at) <= end_date,
                    Reservation.status == ReservationStatus.COMPLETED,
                )
            )
            .group_by(ReservationChannel.channel)
        )

        total_result = await session.execute(total_query)
        completed_result = await session.execute(completed_query)

        totals = {r.channel: r.total for r in total_result.all()}
        completeds = {r.channel: r.completed for r in completed_result.all()}

        conversions = []
        for channel, total in totals.items():
            completed = completeds.get(channel, 0)
            conversions.append(
                {
                    "channel": channel.value if hasattr(channel, "value") else str(channel),
                    "total": total,
                    "completed": completed,
                    "conversion_rate": round(completed / total * 100, 1) if total > 0 else 0,
                }
            )

        return sorted(conversions, key=lambda x: x["conversion_rate"], reverse=True)

    async def get_cancellation_analysis(
        self,
        session: AsyncSession,
        store_id: str,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """退订率分析（易订PRO核心功能）"""
        # 总预订 vs 取消
        query = select(
            func.count().label("total"),
            func.sum(
                case(
                    (Reservation.status == ReservationStatus.CANCELLED, 1),
                    else_=0,
                )
            ).label("cancelled"),
            func.sum(
                case(
                    (Reservation.status == ReservationStatus.NO_SHOW, 1),
                    else_=0,
                )
            ).label("no_show"),
        ).where(
            and_(
                Reservation.store_id == store_id,
                Reservation.reservation_date >= start_date,
                Reservation.reservation_date <= end_date,
            )
        )
        result = await session.execute(query)
        row = result.one()

        total = row.total or 0
        cancelled = row.cancelled or 0
        no_show = row.no_show or 0

        return {
            "store_id": store_id,
            "period": f"{start_date} ~ {end_date}",
            "total_reservations": total,
            "cancelled": cancelled,
            "no_show": no_show,
            "cancellation_rate": round(cancelled / total * 100, 1) if total > 0 else 0,
            "no_show_rate": round(no_show / total * 100, 1) if total > 0 else 0,
            "effective_rate": round((total - cancelled - no_show) / total * 100, 1) if total > 0 else 0,
        }

    def _to_dict(self, r: ReservationChannel) -> Dict[str, Any]:
        return {
            "id": str(r.id),
            "reservation_id": r.reservation_id,
            "store_id": r.store_id,
            "channel": r.channel.value if hasattr(r.channel, "value") else str(r.channel),
            "external_order_id": r.external_order_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }


channel_analytics_service = ChannelAnalyticsService()
