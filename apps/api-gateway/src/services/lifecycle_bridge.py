"""
全链路闭环桥接服务 — Lifecycle Bridge

打通预订/宴会/订单/私域四大系统的断点：

Bridge 1: 预订→订单（Reservation → Order）
  - 到店签到时自动准备订单
  - 预排菜自动转入订单菜品
  - 订单完成时反向更新预订状态

Bridge 2: 宴会→采购（Banquet → Procurement）
  - 签约时 BEO 采购清单自动转采购单
  - 备料阶段触发厨房预警

Bridge 3: 订单→CDP（Order → CDP/Private Domain）
  - 订单完成时自动关联消费者ID
  - 发射 order_completed 信号到信号总线
  - 更新 RFM Recency + Monetary
  - 触发旅程成功度评估

Bridge 4: 私域→预订闭环（Journey → Reservation Conversion）
  - 旅程发券后追踪核销
  - 预订创建时检查活跃旅程
  - 旅程 success_metrics 自动评估

Bridge 5: 跨智能体事件总线扩展
  - 统一事件发射器（emit_lifecycle_event）
  - 订阅器注册（可扩展新路由）
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.order import Order, OrderItem, OrderStatus
from src.models.queue import Queue
from src.models.reservation import Reservation, ReservationStatus

if TYPE_CHECKING:
    from src.core.business_context import BusinessContext

logger = structlog.get_logger()


# ══════════════════════════════════════════════════════════════════
# Bridge 1: 预订 → 订单
# ══════════════════════════════════════════════════════════════════


async def prepare_order_from_reservation(
    session: AsyncSession,
    reservation_id: str,
    ctx: Optional["BusinessContext"] = None,
) -> Dict[str, Any]:
    """
    预订到店时自动准备订单（ARRIVED 状态触发）。

    1. 从预订记录提取客户/桌台信息
    2. 从预排菜提取已确认菜品
    3. 创建 Order + OrderItem
    4. 关联 consumer_id
    """
    result = await session.execute(select(Reservation).where(Reservation.id == reservation_id))
    reservation = result.scalar_one_or_none()
    if not reservation:
        return {"error": f"预订 {reservation_id} 不存在"}

    # 检查是否已有关联订单（防重复）
    existing_order = await session.execute(
        select(Order).where(
            and_(
                Order.store_id == reservation.store_id,
                Order.table_number == reservation.table_number,
                Order.customer_phone == reservation.customer_phone,
                Order.status != OrderStatus.CANCELLED.value,
                func.date(Order.order_time) == reservation.reservation_date,
            )
        )
    )
    if existing_order.scalar_one_or_none():
        return {"message": "该预订已有关联订单", "reservation_id": reservation_id}

    # 获取预排菜
    order_items = []
    pre_order_total = 0
    try:
        from src.models.reservation_pre_order import PreOrderStatus, ReservationPreOrder

        po_result = await session.execute(
            select(ReservationPreOrder)
            .where(
                and_(
                    ReservationPreOrder.reservation_id == reservation_id,
                    ReservationPreOrder.status.in_(
                        [
                            PreOrderStatus.CONFIRMED,
                            PreOrderStatus.PREPARING,
                        ]
                    ),
                )
            )
            .order_by(ReservationPreOrder.sort_order)
        )
        pre_orders = po_result.scalars().all()

        for po in pre_orders:
            item = OrderItem(
                id=uuid.uuid4(),
                item_id=str(po.dish_id) if po.dish_id else po.dish_code or "PREORDER",
                item_name=po.dish_name,
                quantity=po.quantity,
                unit_price=round(po.unit_price / 100, 2),  # 分→元
                subtotal=round(po.subtotal / 100, 2),
                notes=po.taste_note,
            )
            order_items.append(item)
            pre_order_total += po.subtotal

            # 标记预排菜为备料中
            po.status = PreOrderStatus.PREPARING
    except Exception as e:
        logger.warning("prepare_order.pre_order_failed", error=str(e))

    # 创建订单
    total_yuan = round(pre_order_total / 100, 2) if pre_order_total else 0
    order = Order(
        id=uuid.uuid4(),
        store_id=reservation.store_id,
        table_number=reservation.table_number or "",
        customer_name=reservation.customer_name,
        customer_phone=reservation.customer_phone,
        consumer_id=reservation.consumer_id,
        status=OrderStatus.PENDING.value,
        total_amount=total_yuan,
        final_amount=pre_order_total,  # 分
        order_time=datetime.utcnow(),
        notes=f"预订自动转单: {reservation_id}",
        order_metadata={
            "reservation_id": reservation_id,
            "party_size": reservation.party_size,
            "pre_order_count": len(order_items),
        },
    )
    session.add(order)

    for item in order_items:
        item.order_id = order.id
        session.add(item)

    await session.flush()

    # 累积上下文
    if ctx:
        ctx.add_breadcrumb(f"reservation:{reservation_id}")
        ctx.add_breadcrumb(f"order:{order.id}")
        ctx.accumulate("order_id", str(order.id))
        ctx.accumulate("items_count", len(order_items))

    logger.info(
        "order_created_from_reservation",
        reservation_id=reservation_id,
        order_id=str(order.id),
        items=len(order_items),
        trace_id=ctx.trace_id if ctx else None,
    )

    return {
        "order_id": str(order.id),
        "reservation_id": reservation_id,
        "items_count": len(order_items),
        "total_yuan": total_yuan,
        "message": f"预订转订单成功，{len(order_items)}项预排菜已导入",
    }


async def sync_order_completion_to_reservation(
    session: AsyncSession,
    order_id: str,
    ctx: Optional["BusinessContext"] = None,
) -> Optional[str]:
    """
    订单完成时反向更新预订状态为 COMPLETED。

    通过 order_metadata.reservation_id 查找关联预订。
    """
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order or not order.order_metadata:
        return None

    res_id = order.order_metadata.get("reservation_id")
    if not res_id:
        return None

    res_result = await session.execute(select(Reservation).where(Reservation.id == res_id))
    reservation = res_result.scalar_one_or_none()
    if reservation and reservation.status == ReservationStatus.SEATED:
        reservation.status = ReservationStatus.COMPLETED
        logger.info("reservation_auto_completed", reservation_id=res_id, order_id=str(order_id))
        return res_id

    return None


# ══════════════════════════════════════════════════════════════════
# Bridge 2: 宴会 → 采购
# ══════════════════════════════════════════════════════════════════


async def trigger_procurement_from_beo(
    session: AsyncSession,
    reservation_id: str,
    beo_data: Dict[str, Any],
    ctx: Optional["BusinessContext"] = None,
) -> Dict[str, Any]:
    """
    宴会签约后 BEO 采购清单自动转采购建议。

    从 BEO 的 procurement_addon 提取食材需求，
    写入采购建议记录 + 触发企微通知厨房/采购。
    """
    procurement_addon = beo_data.get("procurement_addon", [])
    if not procurement_addon:
        return {"message": "BEO 无采购附加项", "items": 0}

    # 获取预订信息
    result = await session.execute(select(Reservation).where(Reservation.id == reservation_id))
    reservation = result.scalar_one_or_none()
    if not reservation:
        return {"error": f"预订 {reservation_id} 不存在"}

    party_size = reservation.party_size or 10
    event_date = reservation.reservation_date

    # 生成采购建议清单
    procurement_items = []
    for addon in procurement_addon:
        category = addon.get("category", "未分类")
        items = addon.get("items", [])
        multiplier = addon.get("multiplier", 1.0)

        for item in items:
            procurement_items.append(
                {
                    "category": category,
                    "item_name": item.get("name", category),
                    "base_quantity": item.get("quantity", 0),
                    "adjusted_quantity": round(item.get("quantity", 0) * multiplier * (party_size / 10), 1),
                    "unit": item.get("unit", "份"),
                    "estimated_cost_yuan": round(item.get("cost", 0) * multiplier * (party_size / 10) / 100, 2),
                    "priority": "high" if event_date and (event_date - date.today()).days <= 3 else "normal",
                }
            )

    # 写入神经事件（供采购Agent消费）
    try:
        await _emit_lifecycle_event(
            session=session,
            store_id=reservation.store_id,
            event_type="banquet.procurement_needed",
            payload={
                "reservation_id": reservation_id,
                "event_date": event_date.isoformat() if event_date else None,
                "party_size": party_size,
                "items": procurement_items,
                "beo_id": beo_data.get("beo_id"),
            },
        )
    except Exception as e:
        logger.warning("procurement_event_emit_failed", error=str(e))

    # 触发企微通知（fire-and-forget）
    try:
        from src.services.wechat_trigger_service import wechat_trigger_service

        if hasattr(wechat_trigger_service, "trigger"):
            days_until = (event_date - date.today()).days if event_date else "?"
            items_summary = ", ".join(f"{i['item_name']}×{i['adjusted_quantity']}" for i in procurement_items[:5])
            await wechat_trigger_service.trigger(
                "banquet.procurement_alert",
                {
                    "store_id": reservation.store_id,
                    "reservation_id": reservation_id,
                    "event_date": event_date.isoformat() if event_date else "",
                    "days_until": str(days_until),
                    "items_summary": items_summary,
                    "total_items": str(len(procurement_items)),
                },
            )
    except Exception:
        pass

    logger.info(
        "procurement_triggered_from_beo",
        reservation_id=reservation_id,
        items=len(procurement_items),
    )

    return {
        "reservation_id": reservation_id,
        "event_date": event_date.isoformat() if event_date else None,
        "procurement_items": procurement_items,
        "total_items": len(procurement_items),
        "total_estimated_cost_yuan": round(sum(i["estimated_cost_yuan"] for i in procurement_items), 2),
    }


# ══════════════════════════════════════════════════════════════════
# Bridge 3: 订单 → CDP/私域
# ══════════════════════════════════════════════════════════════════


async def on_order_completed(
    session: AsyncSession,
    order_id: str,
    ctx: Optional["BusinessContext"] = None,
) -> Dict[str, Any]:
    """
    订单完成时的CDP闭环：

    1. 解析消费者ID（phone → consumer_id）
    2. 发射 order_completed 信号到私域
    3. 更新 RFM（Recency=today, Monetary+=amount）
    4. 评估活跃旅程的 success_metrics
    5. 反向更新关联预订状态
    """
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        return {"error": f"订单 {order_id} 不存在"}

    actions_taken = []

    # 累积上下文
    if ctx:
        ctx.add_breadcrumb(f"order_completed:{order_id}")
        ctx.accumulate("order_amount_yuan", float(order.total_amount or 0))

    # Step 1: 解析消费者ID
    consumer_id = order.consumer_id
    if not consumer_id and order.customer_phone:
        try:
            from src.services.identity_resolution_service import IdentityResolutionService

            svc = IdentityResolutionService(session)
            consumer = await svc.resolve(order.customer_phone)
            if consumer:
                consumer_id = consumer.id
                order.consumer_id = consumer_id
                actions_taken.append("consumer_id_linked")
        except Exception as e:
            logger.warning("order_cdp.resolve_failed", error=str(e))

    # Step 2: 发射 order_completed 信号
    try:
        signal_id = await _emit_lifecycle_event(
            session=session,
            store_id=order.store_id,
            event_type="order.completed",
            payload={
                "order_id": str(order.id),
                "consumer_id": str(consumer_id) if consumer_id else None,
                "customer_phone": order.customer_phone,
                "amount_yuan": float(order.total_amount or 0),
                "items_count": len(order.items) if order.items else 0,
                "table_number": order.table_number,
            },
        )
        actions_taken.append(f"signal_emitted:{signal_id}")
    except Exception as e:
        logger.warning("order_cdp.signal_failed", error=str(e))

    # Step 3: 更新私域 RFM
    if consumer_id:
        try:
            await _update_rfm_on_order(
                session,
                str(consumer_id),
                order.store_id,
                float(order.total_amount or 0),
            )
            actions_taken.append("rfm_updated")
        except Exception as e:
            logger.warning("order_cdp.rfm_failed", error=str(e))

    # Step 4: 评估旅程 success_metrics
    if consumer_id:
        try:
            evaluated = await _evaluate_journey_success(
                session,
                str(consumer_id),
                order.store_id,
            )
            if evaluated:
                actions_taken.append(f"journeys_evaluated:{evaluated}")
        except Exception as e:
            logger.warning("order_cdp.journey_eval_failed", error=str(e))

    # Step 5: 反向更新预订
    try:
        res_id = await sync_order_completion_to_reservation(session, str(order_id), ctx=ctx)
        if res_id:
            actions_taken.append(f"reservation_completed:{res_id}")
    except Exception as e:
        logger.warning("order_cdp.reservation_sync_failed", error=str(e))

    # 累积最终状态到上下文
    if ctx:
        ctx.accumulate("actions_taken", actions_taken)
        ctx.accumulate("consumer_id", str(consumer_id) if consumer_id else None)

    logger.info(
        "order_completed_lifecycle",
        order_id=str(order_id),
        actions=actions_taken,
        trace_id=ctx.trace_id if ctx else None,
    )

    return {
        "order_id": str(order_id),
        "consumer_id": str(consumer_id) if consumer_id else None,
        "actions": actions_taken,
    }


async def _update_rfm_on_order(
    session: AsyncSession,
    consumer_id: str,
    store_id: str,
    amount_yuan: float,
) -> None:
    """更新消费者的 RFM 指标"""
    try:
        from src.models.consumer_identity import ConsumerIdentity

        result = await session.execute(select(ConsumerIdentity).where(ConsumerIdentity.id == consumer_id))
        consumer = result.scalar_one_or_none()
        if consumer:
            # Recency: 最近消费日期
            consumer.last_order_at = datetime.utcnow()
            # Frequency: 消费次数+1
            if hasattr(consumer, "order_count"):
                consumer.order_count = (consumer.order_count or 0) + 1
            # Monetary: 累计消费
            if hasattr(consumer, "total_spent"):
                consumer.total_spent = (consumer.total_spent or 0) + int(amount_yuan * 100)
            logger.info("rfm_updated", consumer_id=consumer_id, amount=amount_yuan)
    except Exception as e:
        logger.warning("rfm_update_failed", consumer_id=consumer_id, error=str(e))


async def _evaluate_journey_success(
    session: AsyncSession,
    consumer_id: str,
    store_id: str,
) -> int:
    """
    评估消费者所有活跃旅程的 success_metrics。

    如果旅程的 success_metrics 包含 "order_pay"，
    且消费者刚完成订单，则标记旅程为成功。
    """
    evaluated = 0
    try:
        # 查找消费者的活跃旅程
        rows = await session.execute(
            text("""
                SELECT id, journey_type, status
                FROM private_domain_journeys
                WHERE customer_id = :cid
                  AND store_id = :sid
                  AND status = 'active'
            """),
            {"cid": consumer_id, "sid": store_id},
        )
        active_journeys = rows.fetchall()

        from src.services.journey_orchestrator import BUILTIN_JOURNEYS

        for journey in active_journeys:
            j_id, j_type, j_status = journey[0], journey[1], journey[2]
            definition = BUILTIN_JOURNEYS.get(j_type)
            if definition and "order_pay" in definition.success_metrics:
                # 标记旅程成功
                await session.execute(
                    text("""
                        UPDATE private_domain_journeys
                        SET status = 'success',
                            completed_at = :now
                        WHERE id = :jid
                    """),
                    {"now": datetime.utcnow(), "jid": j_id},
                )
                evaluated += 1
                logger.info("journey_success", journey_id=str(j_id), type=j_type)
    except Exception as e:
        logger.warning("journey_eval_failed", error=str(e))

    return evaluated


# ══════════════════════════════════════════════════════════════════
# Bridge 4: 私域→预订闭环
# ══════════════════════════════════════════════════════════════════


async def check_active_journeys_on_reservation(
    session: AsyncSession,
    customer_phone: str,
    store_id: str,
    ctx: Optional["BusinessContext"] = None,
) -> Dict[str, Any]:
    """
    创建预订时检查客户是否有活跃旅程（如沉睡唤醒+优惠券）。

    如果有活跃旅程，标记旅程进展为 "reservation_created"，
    返回旅程信息供前端展示优惠提示。
    """
    active_journeys = []
    try:
        # 通过手机号查找消费者ID
        from src.services.identity_resolution_service import IdentityResolutionService

        svc = IdentityResolutionService(session)
        consumer = await svc.resolve(customer_phone)
        if not consumer:
            return {"has_active_journey": False, "journeys": []}

        rows = await session.execute(
            text("""
                SELECT id, journey_type, status, started_at
                FROM private_domain_journeys
                WHERE customer_id = :cid
                  AND store_id = :sid
                  AND status = 'active'
            """),
            {"cid": str(consumer.id), "sid": store_id},
        )
        for row in rows.fetchall():
            j_id, j_type, j_status, j_started = row
            from src.services.journey_orchestrator import BUILTIN_JOURNEYS

            definition = BUILTIN_JOURNEYS.get(j_type)
            active_journeys.append(
                {
                    "journey_id": str(j_id),
                    "journey_type": j_type,
                    "journey_name": definition.name if definition else j_type,
                    "started_at": j_started.isoformat() if j_started else None,
                }
            )

            # 更新旅程进度
            await session.execute(
                text("""
                    UPDATE private_domain_journeys
                    SET metadata = jsonb_set(
                        COALESCE(metadata, '{}')::jsonb,
                        '{reservation_created_at}',
                        to_jsonb(:now::text)
                    )
                    WHERE id = :jid
                """),
                {"now": datetime.utcnow().isoformat(), "jid": j_id},
            )
    except Exception as e:
        logger.warning("check_journeys_failed", error=str(e))

    return {
        "has_active_journey": len(active_journeys) > 0,
        "journeys": active_journeys,
        "hint": "客户有活跃营销旅程，可提示优惠" if active_journeys else None,
    }


# ══════════════════════════════════════════════════════════════════
# Bridge 5: 统一事件发射器
# ══════════════════════════════════════════════════════════════════


async def _emit_lifecycle_event(
    session: AsyncSession,
    store_id: str,
    event_type: str,
    payload: Dict[str, Any],
) -> str:
    """
    统一生命周期事件发射器。

    所有跨模块事件通过此函数发射到 neural_event_log 表，
    供信号总线/Agent/Celery 异步消费。
    """
    event_id = f"LCE_{event_type.replace('.', '_')}_{uuid.uuid4().hex[:8]}"
    try:
        await session.execute(
            text("""
                INSERT INTO neural_event_logs
                    (id, store_id, event_type, payload, status, created_at)
                VALUES
                    (gen_random_uuid(), :store_id, :event_type,
                     :payload::jsonb, 'pending', :now)
            """),
            {
                "store_id": store_id,
                "event_type": event_type,
                "payload": __import__("json").dumps(payload, default=str),
                "now": datetime.utcnow(),
            },
        )
    except Exception as e:
        # 表名可能不同，降级处理
        logger.warning("lifecycle_event_emit_fallback", event_type=event_type, error=str(e))

    logger.info("lifecycle_event_emitted", event_id=event_id, type=event_type)
    return event_id


# ══════════════════════════════════════════════════════════════════
# 综合闭环 API（供 API 层调用）
# ══════════════════════════════════════════════════════════════════


async def get_customer_lifecycle_view(
    session: AsyncSession,
    customer_phone: str,
    store_id: str,
) -> Dict[str, Any]:
    """
    客户全生命周期视图 — 一次性返回客户在四大系统中的全部状态。

    用于老客到店弹屏、客户360画像。
    """
    view: Dict[str, Any] = {
        "customer_phone": customer_phone[:3] + "****" + customer_phone[-4:],
        "store_id": store_id,
    }

    # 1. 预订历史
    try:
        res_result = await session.execute(
            select(Reservation)
            .where(
                and_(
                    Reservation.customer_phone == customer_phone,
                    Reservation.store_id == store_id,
                )
            )
            .order_by(Reservation.reservation_date.desc())
            .limit(10)
        )
        reservations = res_result.scalars().all()
        view["reservations"] = {
            "total": len(reservations),
            "recent": [
                {
                    "id": r.id,
                    "date": r.reservation_date.isoformat() if r.reservation_date else None,
                    "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                    "party_size": r.party_size,
                    "type": r.reservation_type.value if hasattr(r.reservation_type, "value") else str(r.reservation_type),
                }
                for r in reservations[:5]
            ],
        }
    except Exception:
        view["reservations"] = {"total": 0, "recent": []}

    # 2. 订单历史
    try:
        order_result = await session.execute(
            select(Order)
            .where(
                and_(
                    Order.customer_phone == customer_phone,
                    Order.store_id == store_id,
                )
            )
            .order_by(Order.order_time.desc())
            .limit(10)
        )
        orders = order_result.scalars().all()
        total_spent = sum(float(o.total_amount or 0) for o in orders)
        view["orders"] = {
            "total": len(orders),
            "total_spent_yuan": round(total_spent, 2),
            "avg_order_yuan": round(total_spent / len(orders), 2) if orders else 0,
            "last_order": orders[0].order_time.isoformat() if orders and orders[0].order_time else None,
        }
    except Exception:
        view["orders"] = {"total": 0, "total_spent_yuan": 0}

    # 3. CDP 消费者画像
    try:
        from src.services.identity_resolution_service import IdentityResolutionService

        svc = IdentityResolutionService(session)
        consumer = await svc.resolve(customer_phone)
        if consumer:
            view["cdp"] = {
                "consumer_id": str(consumer.id),
                "tags": consumer.tags if hasattr(consumer, "tags") else [],
                "rfm_level": consumer.rfm_level if hasattr(consumer, "rfm_level") else None,
            }
        else:
            view["cdp"] = None
    except Exception:
        view["cdp"] = None

    # 4. 活跃旅程
    try:
        journey_info = await check_active_journeys_on_reservation(
            session,
            customer_phone,
            store_id,
        )
        view["active_journeys"] = journey_info
    except Exception:
        view["active_journeys"] = {"has_active_journey": False, "journeys": []}

    return view
