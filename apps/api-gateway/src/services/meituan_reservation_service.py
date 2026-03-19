"""
美团预订同步服务
- 入站: Webhook -> 签名验证 -> 归一化 -> 写库 -> 发神经系统事件
- 出站: 本地状态变更 -> 检查 ReservationSync -> 调适配器推回
- 幂等: 按 external_order_id 去重
"""

import uuid
from datetime import date, datetime, time
from typing import Any, Dict, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..models.integration import ReservationSync, SyncStatus
from ..models.reservation import Reservation, ReservationStatus, ReservationType
from ..models.reservation_channel import ChannelType, ReservationChannel

logger = structlog.get_logger()

# 美团 store_id -> 本地 store_id 映射（后续可从DB读取）
_STORE_MAP: Dict[str, str] = {}


class MeituanReservationService:
    """美团预订同步服务"""

    # -- 入站: Webhook处理 --

    async def handle_webhook(self, event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理美团预订推送"""
        external_id = data.get("reservation_id", "")
        if not external_id:
            raise ValueError("缺少 reservation_id")

        if event_type == "reservation.cancelled":
            return await self._handle_cancel(data)

        # reservation.created 或 reservation.updated
        return await self._handle_create_or_update(data)

    async def _handle_create_or_update(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建或更新预订"""
        external_id = data.get("reservation_id", "")
        store_id = self._resolve_store_id(data.get("store_id", ""))

        async with get_db_session() as session:
            # 幂等检查：按 external_order_id 查找
            existing = await session.execute(
                select(ReservationChannel).where(ReservationChannel.external_order_id == external_id)
            )
            channel_record = existing.scalar_one_or_none()

            if channel_record:
                # 更新已有预订
                result = await session.execute(select(Reservation).where(Reservation.id == channel_record.reservation_id))
                reservation = result.scalar_one_or_none()
                if reservation:
                    reservation.customer_name = data.get("customer_name", reservation.customer_name)
                    reservation.party_size = data.get("party_size", reservation.party_size)
                    reservation.special_requests = data.get("special_requests", reservation.special_requests)
                    await session.commit()
                    logger.info("meituan_reservation_updated", reservation_id=reservation.id, external_id=external_id)
                    return {"action": "updated", "reservation_id": reservation.id}

            # 创建新预订
            res_date = date.fromisoformat(data.get("reservation_date", date.today().isoformat()))
            res_time_str = data.get("reservation_time", "18:00")
            res_time = time.fromisoformat(res_time_str)

            reservation_id = f"RES_{res_date.strftime('%Y%m%d')}_{str(uuid.uuid4())[:8].upper()}"
            customer_name = data.get("customer_name", "美团客户")
            customer_phone = data.get("customer_phone", "")
            party_size = data.get("party_size", 2)

            reservation = Reservation(
                id=reservation_id,
                store_id=store_id,
                customer_name=customer_name,
                customer_phone=customer_phone,
                party_size=party_size,
                reservation_date=res_date,
                reservation_time=res_time,
                reservation_type=ReservationType.REGULAR,
                room_name=data.get("table_type"),
                special_requests=data.get("special_requests"),
                status=ReservationStatus.CONFIRMED,
            )
            session.add(reservation)

            # 渠道记录
            source = data.get("source", "meituan")
            channel_type = ChannelType.DIANPING if source == "dianping" else ChannelType.MEITUAN
            channel = ReservationChannel(
                reservation_id=reservation_id,
                store_id=store_id,
                channel=channel_type,
                external_order_id=external_id,
                converted_at=datetime.utcnow(),
            )
            session.add(channel)

            # 同步记录（用于出站同步）
            # ReservationSync 有多个 NOT NULL 字段，全部填充
            sync = ReservationSync(
                system_id=uuid.uuid4(),
                store_id=store_id,
                reservation_id=reservation_id,
                external_reservation_id=external_id,
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_count=party_size,
                reservation_date=datetime.combine(res_date, res_time),
                reservation_time=res_time_str,
                table_type=data.get("table_type"),
                status="confirmed",
                source=source,
                channel=source,
                special_requirements=data.get("special_requests"),
                sync_status=SyncStatus.SUCCESS,
                synced_at=datetime.utcnow(),
                raw_data=data,
            )
            session.add(sync)

            await session.commit()
            logger.info("meituan_reservation_created", reservation_id=reservation_id, external_id=external_id)
            return {"action": "created", "reservation_id": reservation_id}

    async def _handle_cancel(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理美团取消"""
        external_id = data.get("reservation_id", "")

        async with get_db_session() as session:
            result = await session.execute(
                select(ReservationChannel).where(ReservationChannel.external_order_id == external_id)
            )
            channel_record = result.scalar_one_or_none()
            if not channel_record:
                logger.warning("meituan_cancel_not_found", external_id=external_id)
                return {"action": "skipped", "reason": "not_found"}

            res_result = await session.execute(select(Reservation).where(Reservation.id == channel_record.reservation_id))
            reservation = res_result.scalar_one_or_none()
            if reservation and reservation.status not in (
                ReservationStatus.CANCELLED,
                ReservationStatus.COMPLETED,
            ):
                reservation.status = ReservationStatus.CANCELLED
                reservation.cancelled_at = datetime.utcnow()
                await session.commit()
                logger.info("meituan_reservation_cancelled", reservation_id=reservation.id, external_id=external_id)
                return {"action": "cancelled", "reservation_id": reservation.id}

            return {"action": "skipped", "reason": "already_terminal"}

    # -- 出站: 同步到美团 --

    async def sync_to_meituan(
        self,
        session: AsyncSession,
        reservation_id: str,
        action: str,
    ) -> Dict[str, Any]:
        """将本地状态变更推回美团"""
        # 查找同步记录
        result = await session.execute(select(ReservationSync).where(ReservationSync.reservation_id == reservation_id))
        sync_record = result.scalar_one_or_none()
        if not sync_record:
            raise ValueError("该预订非美团渠道，无需同步")

        external_id = sync_record.external_reservation_id

        # 调用美团API（通过适配器）
        try:
            adapter = self._get_adapter()
            if not adapter:
                logger.warning("meituan_adapter_not_configured")
                return {"synced": False, "reason": "adapter_not_configured"}

            if action == "confirm":
                await adapter.confirm_reservation(external_id)
            elif action == "cancel":
                await adapter.cancel_reservation(external_id)
            elif action == "no_show":
                await adapter.update_reservation_status(external_id, "no_show")
            else:
                raise ValueError(f"不支持的操作: {action}")

            # 更新同步状态
            sync_record.sync_status = SyncStatus.SUCCESS
            sync_record.synced_at = datetime.utcnow()
            await session.commit()

            logger.info("meituan_sync_success", reservation_id=reservation_id, external_id=external_id, action=action)
            return {"synced": True, "external_id": external_id, "action": action}

        except Exception as e:
            sync_record.sync_status = SyncStatus.FAILED
            await session.commit()
            logger.error("meituan_sync_failed", error=str(e), reservation_id=reservation_id)
            return {"synced": False, "error": str(e)}

    # -- 内部方法 --

    def _resolve_store_id(self, meituan_store_id: str) -> str:
        """美团门店ID -> 本地门店ID"""
        return _STORE_MAP.get(meituan_store_id, meituan_store_id)

    def _get_adapter(self):
        """获取美团适配器实例（含预订方法混入）"""
        try:
            import os
            import sys

            # 确保适配器包可导入
            repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
            adapter_src = os.path.join(repo_root, "packages", "api-adapters", "meituan-saas", "src")
            if adapter_src not in sys.path:
                sys.path.insert(0, adapter_src)

            from adapter import MeituanSaasAdapter

            config = {
                "app_key": os.getenv("MEITUAN_APP_KEY", ""),
                "app_secret": os.getenv("MEITUAN_APP_SECRET", ""),
            }
            if config["app_key"] and config["app_secret"]:
                return MeituanSaasAdapter(config)
        except Exception:
            pass
        return None


# 单例
meituan_reservation_service = MeituanReservationService()
