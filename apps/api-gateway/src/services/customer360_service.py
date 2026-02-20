"""
客户360画像服务
Customer 360 Profile Service

聚合所有客户触点数据，生成统一的客户视图和时间线
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from ..models.order import Order
from ..models.reservation import Reservation
from ..models.integration import MemberSync, POSTransaction, ReservationSync
from ..models.audit_log import AuditLog
from ..core.database import get_db_session

logger = structlog.get_logger()


class Customer360Service:
    """客户360画像服务"""

    async def get_customer_profile(
        self,
        customer_identifier: str,
        identifier_type: str = "phone",
        store_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取客户360画像

        Args:
            customer_identifier: 客户标识（手机号、会员ID等）
            identifier_type: 标识类型 (phone, member_id, email)
            store_id: 门店ID（可选，用于多租户隔离）

        Returns:
            客户360画像数据
        """
        async with get_session() as session:
            try:
                logger.info(
                    "获取客户360画像",
                    identifier=customer_identifier,
                    type=identifier_type,
                    store_id=store_id,
                )

                # 1. 获取会员基础信息
                member_info = await self._get_member_info(
                    session, customer_identifier, identifier_type, store_id
                )

                # 2. 获取订单历史
                order_history = await self._get_order_history(
                    session, customer_identifier, identifier_type, store_id
                )

                # 3. 获取预订记录
                reservation_history = await self._get_reservation_history(
                    session, customer_identifier, identifier_type, store_id
                )

                # 4. 获取POS交易记录
                pos_transactions = await self._get_pos_transactions(
                    session, customer_identifier, identifier_type, store_id
                )

                # 5. 获取活动日志
                activity_logs = await self._get_activity_logs(
                    session, customer_identifier, identifier_type, store_id
                )

                # 6. 生成客户时间线
                timeline = await self._generate_timeline(
                    order_history,
                    reservation_history,
                    pos_transactions,
                    activity_logs,
                )

                # 7. 计算客户价值指标
                customer_value = await self._calculate_customer_value(
                    order_history, pos_transactions
                )

                # 8. 生成客户标签
                customer_tags = await self._generate_customer_tags(
                    member_info,
                    order_history,
                    reservation_history,
                    customer_value,
                )

                # 9. 构建完整画像
                profile = {
                    "customer_identifier": customer_identifier,
                    "identifier_type": identifier_type,
                    "member_info": member_info,
                    "customer_value": customer_value,
                    "customer_tags": customer_tags,
                    "statistics": {
                        "total_orders": len(order_history),
                        "total_reservations": len(reservation_history),
                        "total_pos_transactions": len(pos_transactions),
                        "total_activities": len(activity_logs),
                    },
                    "timeline": timeline,
                    "recent_orders": order_history[:5],  # 最近5笔订单
                    "recent_reservations": reservation_history[:3],  # 最近3次预订
                    "generated_at": datetime.now().isoformat(),
                }

                logger.info(
                    "客户360画像生成成功",
                    identifier=customer_identifier,
                    total_events=len(timeline),
                )

                return profile

            except Exception as e:
                logger.error(
                    "获取客户360画像失败",
                    identifier=customer_identifier,
                    error=str(e),
                    exc_info=e,
                )
                raise

    async def _get_member_info(
        self,
        session: AsyncSession,
        identifier: str,
        identifier_type: str,
        store_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """获取会员基础信息"""
        try:
            query = select(MemberSync)

            if identifier_type == "phone":
                query = query.where(MemberSync.phone == identifier)
            elif identifier_type == "member_id":
                query = query.where(MemberSync.member_id == identifier)
            elif identifier_type == "email":
                query = query.where(MemberSync.email == identifier)

            if store_id:
                query = query.where(MemberSync.store_id == store_id)

            result = await session.execute(query)
            member = result.scalar_one_or_none()

            if member:
                return {
                    "member_id": member.member_id,
                    "name": member.name,
                    "phone": member.phone,
                    "email": member.email,
                    "level": member.level,
                    "points": member.points,
                    "balance": float(member.balance) if member.balance else 0.0,
                    "birthday": member.birthday.isoformat() if member.birthday else None,
                    "gender": member.gender,
                    "registered_at": member.registered_at.isoformat() if member.registered_at else None,
                    "last_activity": member.last_activity.isoformat() if member.last_activity else None,
                }

            return None

        except Exception as e:
            logger.error("获取会员信息失败", error=str(e))
            return None

    async def _get_order_history(
        self,
        session: AsyncSession,
        identifier: str,
        identifier_type: str,
        store_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        """获取订单历史"""
        try:
            query = select(Order).order_by(desc(Order.order_time))

            # 根据标识类型查询
            if identifier_type == "phone":
                query = query.where(Order.customer_phone == identifier)
            elif identifier_type == "member_id":
                query = query.where(Order.member_id == identifier)

            if store_id:
                query = query.where(Order.store_id == store_id)

            # 限制最近100笔订单
            query = query.limit(100)

            result = await session.execute(query)
            orders = result.scalars().all()

            return [
                {
                    "order_id": order.order_id,
                    "order_number": order.order_number,
                    "order_type": order.order_type,
                    "status": order.status,
                    "total": float(order.total),
                    "order_time": order.order_time.isoformat(),
                    "completed_at": order.completed_at.isoformat() if order.completed_at else None,
                    "table_number": order.table_number,
                    "customer_name": order.customer_name,
                    "customer_phone": order.customer_phone,
                }
                for order in orders
            ]

        except Exception as e:
            logger.error("获取订单历史失败", error=str(e))
            return []

    async def _get_reservation_history(
        self,
        session: AsyncSession,
        identifier: str,
        identifier_type: str,
        store_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        """获取预订记录"""
        try:
            # 查询本地预订表
            query = select(Reservation).order_by(desc(Reservation.reservation_date))

            if identifier_type == "phone":
                query = query.where(Reservation.customer_phone == identifier)
            elif identifier_type == "email":
                query = query.where(Reservation.customer_email == identifier)

            if store_id:
                query = query.where(Reservation.store_id == store_id)

            query = query.limit(50)

            result = await session.execute(query)
            reservations = result.scalars().all()

            reservation_list = [
                {
                    "reservation_id": res.reservation_id,
                    "customer_name": res.customer_name,
                    "customer_phone": res.customer_phone,
                    "party_size": res.party_size,
                    "reservation_date": res.reservation_date.isoformat(),
                    "status": res.status,
                    "table_number": res.table_number,
                    "special_requests": res.special_requests,
                    "created_at": res.created_at.isoformat(),
                }
                for res in reservations
            ]

            # 查询同步的预订记录（来自易订等外部系统）
            sync_query = select(ReservationSync).order_by(desc(ReservationSync.reservation_date))

            if identifier_type == "phone":
                sync_query = sync_query.where(ReservationSync.customer_phone == identifier)

            if store_id:
                sync_query = sync_query.where(ReservationSync.store_id == store_id)

            sync_query = sync_query.limit(50)

            sync_result = await session.execute(sync_query)
            sync_reservations = sync_result.scalars().all()

            for sync_res in sync_reservations:
                reservation_list.append({
                    "reservation_id": sync_res.external_reservation_id,
                    "customer_name": sync_res.customer_name,
                    "customer_phone": sync_res.customer_phone,
                    "party_size": sync_res.party_size,
                    "reservation_date": sync_res.reservation_date.isoformat(),
                    "status": sync_res.status,
                    "source": sync_res.source,
                    "channel": sync_res.channel,
                    "synced_at": sync_res.synced_at.isoformat() if sync_res.synced_at else None,
                })

            # 按时间排序
            reservation_list.sort(key=lambda x: x.get("reservation_date", ""), reverse=True)

            return reservation_list

        except Exception as e:
            logger.error("获取预订记录失败", error=str(e))
            return []

    async def _get_pos_transactions(
        self,
        session: AsyncSession,
        identifier: str,
        identifier_type: str,
        store_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        """获取POS交易记录"""
        try:
            query = select(POSTransaction).order_by(desc(POSTransaction.transaction_time))

            # POS交易主要通过手机号关联
            if identifier_type in ["phone", "member_id"]:
                # 假设customer_info字段存储JSON，包含phone或member_id
                # 这里需要根据实际数据结构调整
                pass

            if store_id:
                query = query.where(POSTransaction.store_id == store_id)

            query = query.limit(100)

            result = await session.execute(query)
            transactions = result.scalars().all()

            return [
                {
                    "transaction_id": trans.transaction_id,
                    "external_transaction_id": trans.external_transaction_id,
                    "transaction_type": trans.transaction_type,
                    "total_amount": float(trans.total_amount),
                    "payment_method": trans.payment_method,
                    "transaction_time": trans.transaction_time.isoformat(),
                    "status": trans.status,
                    "items_count": len(trans.items) if trans.items else 0,
                }
                for trans in transactions
            ]

        except Exception as e:
            logger.error("获取POS交易记录失败", error=str(e))
            return []

    async def _get_activity_logs(
        self,
        session: AsyncSession,
        identifier: str,
        identifier_type: str,
        store_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        """获取活动日志"""
        try:
            # 审计日志可能通过user_id或resource_id关联
            query = select(AuditLog).order_by(desc(AuditLog.timestamp)).limit(100)

            # 这里需要根据实际情况调整查询条件
            # 可能需要通过user_id或其他字段关联

            result = await session.execute(query)
            logs = result.scalars().all()

            return [
                {
                    "log_id": log.id,
                    "action": log.action,
                    "resource_type": log.resource_type,
                    "resource_id": log.resource_id,
                    "timestamp": log.timestamp.isoformat(),
                    "ip_address": log.ip_address,
                    "user_agent": log.user_agent,
                }
                for log in logs
            ]

        except Exception as e:
            logger.error("获取活动日志失败", error=str(e))
            return []

    async def _generate_timeline(
        self,
        orders: List[Dict],
        reservations: List[Dict],
        pos_transactions: List[Dict],
        activity_logs: List[Dict],
    ) -> List[Dict[str, Any]]:
        """生成客户时间线"""
        timeline = []

        # 添加订单事件
        for order in orders:
            timeline.append({
                "event_type": "order",
                "event_time": order["order_time"],
                "title": f"订单 {order['order_number']}",
                "description": f"{order['order_type']} - ¥{order['total']}",
                "status": order["status"],
                "data": order,
            })

        # 添加预订事件
        for reservation in reservations:
            timeline.append({
                "event_type": "reservation",
                "event_time": reservation["reservation_date"],
                "title": f"预订 - {reservation['party_size']}人",
                "description": f"状态: {reservation['status']}",
                "status": reservation["status"],
                "data": reservation,
            })

        # 添加POS交易事件
        for transaction in pos_transactions:
            timeline.append({
                "event_type": "pos_transaction",
                "event_time": transaction["transaction_time"],
                "title": f"POS交易 - ¥{transaction['total_amount']}",
                "description": f"{transaction['payment_method']}",
                "status": transaction["status"],
                "data": transaction,
            })

        # 按时间倒序排序
        timeline.sort(key=lambda x: x["event_time"], reverse=True)

        return timeline

    async def _calculate_customer_value(
        self,
        orders: List[Dict],
        pos_transactions: List[Dict],
    ) -> Dict[str, Any]:
        """计算客户价值指标"""
        try:
            # 总消费金额
            total_spent = sum(order["total"] for order in orders)
            total_spent += sum(trans["total_amount"] for trans in pos_transactions)

            # 订单数量
            total_orders = len(orders) + len(pos_transactions)

            # 平均订单金额
            avg_order_value = total_spent / total_orders if total_orders > 0 else 0

            # 最近消费时间
            last_order_time = None
            if orders:
                last_order_time = orders[0]["order_time"]

            # 首次消费时间
            first_order_time = None
            if orders:
                first_order_time = orders[-1]["order_time"]

            # 客户生命周期（天数）
            customer_lifetime_days = 0
            if first_order_time and last_order_time:
                first_dt = datetime.fromisoformat(first_order_time)
                last_dt = datetime.fromisoformat(last_order_time)
                customer_lifetime_days = (last_dt - first_dt).days

            # 消费频率（每月订单数）
            order_frequency = 0
            if customer_lifetime_days > 0:
                order_frequency = total_orders / (customer_lifetime_days / 30)

            # 客户价值评分（简单算法）
            # RFM模型：Recency（最近消费）、Frequency（消费频率）、Monetary（消费金额）
            rfm_score = 0
            if last_order_time:
                days_since_last_order = (datetime.now() - datetime.fromisoformat(last_order_time)).days
                recency_score = max(0, 100 - days_since_last_order)  # 越近越高
                frequency_score = min(100, order_frequency * 10)  # 频率越高越好
                monetary_score = min(100, total_spent / 100)  # 金额越高越好
                rfm_score = (recency_score + frequency_score + monetary_score) / 3

            return {
                "total_spent": round(total_spent, 2),
                "total_orders": total_orders,
                "avg_order_value": round(avg_order_value, 2),
                "last_order_time": last_order_time,
                "first_order_time": first_order_time,
                "customer_lifetime_days": customer_lifetime_days,
                "order_frequency_per_month": round(order_frequency, 2),
                "rfm_score": round(rfm_score, 2),
                "customer_tier": self._get_customer_tier(rfm_score),
            }

        except Exception as e:
            logger.error("计算客户价值失败", error=str(e))
            return {}

    def _get_customer_tier(self, rfm_score: float) -> str:
        """根据RFM评分获取客户等级"""
        if rfm_score >= 80:
            return "VIP"
        elif rfm_score >= 60:
            return "高价值"
        elif rfm_score >= 40:
            return "中价值"
        elif rfm_score >= 20:
            return "低价值"
        else:
            return "流失风险"

    async def _generate_customer_tags(
        self,
        member_info: Optional[Dict],
        orders: List[Dict],
        reservations: List[Dict],
        customer_value: Dict,
    ) -> List[str]:
        """生成客户标签"""
        tags = []

        # 会员标签
        if member_info:
            tags.append("会员")
            if member_info.get("level"):
                tags.append(f"会员等级:{member_info['level']}")

        # 价值标签
        if customer_value.get("customer_tier"):
            tags.append(customer_value["customer_tier"])

        # 消费习惯标签
        if customer_value.get("order_frequency_per_month", 0) > 4:
            tags.append("高频消费")
        elif customer_value.get("order_frequency_per_month", 0) > 2:
            tags.append("中频消费")

        if customer_value.get("avg_order_value", 0) > 200:
            tags.append("高客单价")

        # 预订习惯标签
        if len(reservations) > 5:
            tags.append("预订常客")

        # 活跃度标签
        if customer_value.get("last_order_time"):
            days_since_last = (datetime.now() - datetime.fromisoformat(customer_value["last_order_time"])).days
            if days_since_last <= 7:
                tags.append("活跃用户")
            elif days_since_last <= 30:
                tags.append("一般活跃")
            elif days_since_last <= 90:
                tags.append("沉睡用户")
            else:
                tags.append("流失用户")

        return tags


# 全局服务实例
customer360_service = Customer360Service()
