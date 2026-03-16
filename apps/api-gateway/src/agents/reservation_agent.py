"""
ReservationAgent - 预订与宴会管理智能体

负责：预订管理、宴会管理、座位分配、冲突检测、提醒通知。
委托给 ReservationRepository 和现有 reservations API 服务层执行 DB 操作。
宴会相关功能通过 BanquetAgent / banquet_lifecycle_service 提供。
"""

import datetime
import time
from typing import Any, Dict, List

import structlog
from src.core.base_agent import AgentResponse, BaseAgent

logger = structlog.get_logger()

_SUPPORTED_ACTIONS = [
    "create_reservation",
    "update_reservation",
    "cancel_reservation",
    "get_reservation",
    "list_reservations",
    "check_availability",
    "assign_seating",
    "send_reminder",
    "get_analytics",
]


class ReservationAgent(BaseAgent):
    """预订与宴会管理智能体"""

    def __init__(self):
        super().__init__(config={})

    def get_supported_actions(self) -> List[str]:
        return _SUPPORTED_ACTIONS

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        start = time.time()
        store_id = params.get("store_id", "STORE001")
        logger.info("reservation_agent.execute", action=action, store_id=store_id)

        if action not in _SUPPORTED_ACTIONS:
            return AgentResponse(
                success=False,
                error=f"不支持的操作: {action}。支持: {', '.join(_SUPPORTED_ACTIONS)}",
                execution_time=time.time() - start,
            )

        try:
            from datetime import date

            from sqlalchemy import and_, func, select
            from src.core.database import get_db_session
            from src.models.reservation import Reservation, ReservationStatus, ReservationType

            async with get_db_session() as session:
                data = await self._dispatch(
                    action,
                    params,
                    store_id,
                    session,
                    Reservation,
                    ReservationStatus,
                    ReservationType,
                    select,
                    and_,
                    func,
                    date,
                )

        except Exception as exc:
            logger.error("reservation_agent.execute_failed", action=action, store_id=store_id, error=str(exc))
            return AgentResponse(
                success=False,
                error=str(exc),
                execution_time=time.time() - start,
            )

        return AgentResponse(
            success=True,
            data=data,
            execution_time=time.time() - start,
        )

    async def _dispatch(
        self, action, params, store_id, session, Reservation, ReservationStatus, ReservationType, select, and_, func, date
    ):

        if action == "list_reservations":
            query = select(Reservation).where(Reservation.store_id == store_id)
            if params.get("reservation_date"):
                query = query.where(Reservation.reservation_date == params["reservation_date"])
            if params.get("status"):
                query = query.where(Reservation.status == params["status"])
            limit = int(params.get("limit", 50))
            query = query.order_by(Reservation.reservation_date.desc()).limit(limit)
            rows = (await session.execute(query)).scalars().all()
            return {
                "store_id": store_id,
                "total": len(rows),
                "reservations": [self._serialize(r) for r in rows],
            }

        elif action == "get_reservation":
            rid = params.get("reservation_id")
            if not rid:
                return {"error": "reservation_id 必填"}
            row = await session.get(Reservation, rid)
            if not row:
                return {"error": f"预约 {rid} 不存在"}
            return self._serialize(row)

        elif action == "check_availability":
            target_date = params.get("date", date.today().isoformat())
            party_size = int(params.get("party_size", 2))
            result = await session.execute(
                select(func.count())
                .select_from(Reservation)
                .where(
                    and_(
                        Reservation.store_id == store_id,
                        Reservation.reservation_date == target_date,
                        Reservation.status.in_(["pending", "confirmed", "seated"]),
                    )
                )
            )
            confirmed_count = result.scalar() or 0
            max_reservations = int(params.get("max_daily_reservations", 30))
            available = confirmed_count < max_reservations
            return {
                "store_id": store_id,
                "date": target_date,
                "party_size": party_size,
                "available": available,
                "confirmed_count": confirmed_count,
                "remaining_slots": max(0, max_reservations - confirmed_count),
            }

        elif action == "get_analytics":
            end_dt = date.today()
            start_dt = end_dt - datetime.timedelta(days=int(params.get("days", 30)))
            result = await session.execute(
                select(Reservation).where(
                    and_(
                        Reservation.store_id == store_id,
                        Reservation.reservation_date >= start_dt,
                        Reservation.reservation_date <= end_dt,
                    )
                )
            )
            rows = result.scalars().all()
            total = len(rows)
            completed = sum(1 for r in rows if str(r.status).endswith("completed"))
            no_show = sum(1 for r in rows if str(r.status).endswith("no_show"))
            total_guests = sum(r.party_size for r in rows)
            return {
                "store_id": store_id,
                "period_days": params.get("days", 30),
                "total_reservations": total,
                "completed": completed,
                "no_show": no_show,
                "total_guests": total_guests,
                "avg_party_size": round(total_guests / total, 1) if total else 0,
                "no_show_rate": round(no_show / total, 3) if total else 0,
            }

        elif action in ("create_reservation", "update_reservation", "cancel_reservation", "assign_seating", "send_reminder"):
            # 写操作委托给 REST API 层，Agent 返回路由指引
            return {
                "store_id": store_id,
                "action": action,
                "note": f"写操作请通过 /api/v1/reservations 端点执行",
                "endpoint": "/api/v1/reservations",
            }

        return {"store_id": store_id, "action": action}

    @staticmethod
    def _serialize(r) -> dict:
        return {
            "id": str(r.id),
            "store_id": r.store_id,
            "customer_name": r.customer_name,
            "customer_phone": r.customer_phone,
            "party_size": r.party_size,
            "reservation_date": str(r.reservation_date),
            "reservation_time": str(r.reservation_time),
            "status": str(r.status.value if hasattr(r.status, "value") else r.status),
            "reservation_type": str(r.reservation_type.value if hasattr(r.reservation_type, "value") else r.reservation_type),
            "table_number": r.table_number,
            "special_requests": r.special_requests,
            "notes": r.notes,
        }
