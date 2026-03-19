"""
客户自助预订服务
公开H5页面使用，通过手机号+验证码认证
"""

import secrets
import uuid
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.reservation import Reservation, ReservationStatus, ReservationType
from ..models.reservation_channel import ChannelType, ReservationChannel
from ..models.store import Store

logger = structlog.get_logger()

# Redis key for phone token
_TOKEN_PREFIX = "public:phone_token:"  # public:phone_token:{token} → phone, TTL 24h
TOKEN_EXPIRE_SECONDS = 86400  # 24 hours


class PublicReservationService:
    """客户自助预订服务"""

    def __init__(self):
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            from .redis_cache_service import RedisCacheService

            cache = RedisCacheService()
            await cache.initialize()
            self._redis = cache._redis
        return self._redis

    # ── Token 管理 ──

    async def create_phone_token(self, phone: str) -> str:
        """验证码校验通过后，创建 phone token（24h TTL）"""
        redis = await self._get_redis()
        token = secrets.token_hex(16)
        key = f"{_TOKEN_PREFIX}{token}"
        await redis.set(key, phone, ex=TOKEN_EXPIRE_SECONDS)
        logger.info("public_phone_token_created", phone=phone[-4:])
        return token

    async def get_phone_by_token(self, token: str) -> Optional[str]:
        """通过 token 获取手机号"""
        redis = await self._get_redis()
        key = f"{_TOKEN_PREFIX}{token}"
        phone = await redis.get(key)
        return phone

    # ── 门店查询 ──

    async def get_public_stores(self, session: AsyncSession) -> List[Dict[str, Any]]:
        """获取门店列表（仅公开信息：名称/地址）"""
        result = await session.execute(select(Store).where(Store.is_active == True))
        stores = result.scalars().all()
        return [
            {
                "id": s.id,
                "name": s.name,
                "address": getattr(s, "address", ""),
                "phone": getattr(s, "phone", ""),
            }
            for s in stores
        ]

    # ── 可用时段查询 ──

    async def get_store_availability(
        self,
        session: AsyncSession,
        store_id: str,
        target_date: date,
    ) -> Dict[str, Any]:
        """查询门店可用时段+桌型"""
        # 查询当天已有预订
        result = await session.execute(
            select(Reservation).where(
                and_(
                    Reservation.store_id == store_id,
                    Reservation.reservation_date == target_date,
                    Reservation.status.in_(
                        [
                            ReservationStatus.PENDING,
                            ReservationStatus.CONFIRMED,
                            ReservationStatus.ARRIVED,
                            ReservationStatus.SEATED,
                        ]
                    ),
                )
            )
        )
        existing = result.scalars().all()

        # 统计各时段已预订数量
        booked_by_time: Dict[str, int] = {}
        for r in existing:
            time_key = r.reservation_time.strftime("%H:%M") if r.reservation_time else "unknown"
            booked_by_time[time_key] = booked_by_time.get(time_key, 0) + 1

        # 生成可用时段（午餐 11:00-14:00，晚餐 17:00-21:00）
        # 每个时段容量假设为 20 桌（后续可从 store config 读取）
        capacity_per_slot = 20
        slots = []
        for meal, start_h, end_h in [("午餐", 11, 14), ("晚餐", 17, 21)]:
            for h in range(start_h, end_h + 1):
                for m in [0, 30]:
                    time_str = f"{h:02d}:{m:02d}"
                    booked = booked_by_time.get(time_str, 0)
                    available = max(0, capacity_per_slot - booked)
                    slots.append(
                        {
                            "time": time_str,
                            "meal_period": meal,
                            "booked": booked,
                            "available": available,
                        }
                    )

        # 桌型信息
        table_types = [
            {"type": "大厅", "min_size": 1, "max_size": 6},
            {"type": "包厢", "min_size": 4, "max_size": 20},
        ]

        return {
            "store_id": store_id,
            "date": target_date.isoformat(),
            "slots": slots,
            "table_types": table_types,
        }

    # ── 创建预订 ──

    async def create_public_reservation(
        self,
        session: AsyncSession,
        phone: str,
        store_id: str,
        customer_name: str,
        party_size: int,
        reservation_date: date,
        reservation_time: time,
        reservation_type: str = "regular",
        table_type: Optional[str] = None,
        special_requests: Optional[str] = None,
        dietary_restrictions: Optional[str] = None,
    ) -> Reservation:
        """创建公开预订"""
        reservation_id = f"RES_{reservation_date.strftime('%Y%m%d')}_{str(uuid.uuid4())[:8].upper()}"

        reservation = Reservation(
            id=reservation_id,
            store_id=store_id,
            customer_name=customer_name,
            customer_phone=phone,
            party_size=party_size,
            reservation_date=reservation_date,
            reservation_time=reservation_time,
            reservation_type=ReservationType(reservation_type),
            room_name=table_type,
            special_requests=special_requests,
            dietary_restrictions=dietary_restrictions,
            status=ReservationStatus.PENDING,
        )
        session.add(reservation)

        # 记录渠道来源
        channel = ReservationChannel(
            reservation_id=reservation_id,
            store_id=store_id,
            channel=ChannelType.WECHAT,
            converted_at=datetime.utcnow(),
        )
        session.add(channel)

        await session.commit()
        await session.refresh(reservation)

        logger.info("public_reservation_created", reservation_id=reservation_id, store_id=store_id, phone=phone[-4:])
        return reservation

    # ── 查询我的预订 ──

    async def lookup_reservations(
        self,
        session: AsyncSession,
        phone: str,
    ) -> List[Reservation]:
        """按手机号查询预订"""
        result = await session.execute(
            select(Reservation)
            .where(Reservation.customer_phone == phone)
            .order_by(Reservation.reservation_date.desc(), Reservation.reservation_time.desc())
            .limit(50)
        )
        return list(result.scalars().all())

    # ── 取消预订 ──

    async def cancel_reservation(
        self,
        session: AsyncSession,
        reservation_id: str,
        phone: str,
    ) -> Reservation:
        """取消预订（仅 pending/confirmed 状态允许）"""
        result = await session.execute(
            select(Reservation).where(
                and_(
                    Reservation.id == reservation_id,
                    Reservation.customer_phone == phone,
                )
            )
        )
        reservation = result.scalar_one_or_none()
        if not reservation:
            raise ValueError("预订不存在或无权操作")

        if reservation.status not in (ReservationStatus.PENDING, ReservationStatus.CONFIRMED):
            raise ValueError(f"当前状态 {reservation.status.value} 不允许取消")

        reservation.status = ReservationStatus.CANCELLED
        reservation.cancelled_at = datetime.utcnow()
        await session.commit()
        await session.refresh(reservation)

        logger.info("public_reservation_cancelled", reservation_id=reservation_id, phone=phone[-4:])
        return reservation


# 单例
public_reservation_service = PublicReservationService()
