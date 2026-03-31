"""
全链路用餐旅程服务 — 徐记海鲜荟聚店业务流程引擎

覆盖消费者从预订→到店→用餐→离店→售后的完整生命周期：

Phase 1 — 多渠道预订/等位 → CDP自动关联
Phase 2 — 到店前：千人千面推送（邀请函/消费场景/菜品推荐）
Phase 3 — 老客识别：历史偏好/生日场景/自动化标签
Phase 4 — 餐中：巡台检查/问题识别/知识学习
Phase 5 — 离店前：满意度调查/营销触达
Phase 6 — 离店后：线上评价管理/企业售后

与现有模块集成：
  - IdentityResolutionService → consumer_id 解析
  - JourneyOrchestrator → 旅程触发（birthday_greeting 等）
  - JourneyNarrator → 千人千面文案（Maslow L1-5）
  - WeChatTriggerService → 企微推送
  - Customer360Service → 完整画像
  - CustomerSentimentService → 评价情感分析
  - BirthdayReminderService → 生日扫描
  - FloorPlan → 桌台推荐
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, exc as sa_exc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.queue import Queue, QueueStatus
from src.models.reservation import Reservation, ReservationStatus, ReservationType

logger = structlog.get_logger()


# ══════════════════════════════════════════════════════════════════
# Phase 1: 多渠道 → CDP 自动关联
# ══════════════════════════════════════════════════════════════════


async def link_consumer_to_reservation(
    session: AsyncSession,
    reservation: Reservation,
) -> Optional[str]:
    """
    预订创建后自动关联CDP消费者ID。

    Returns: consumer_id (str) or None
    """
    if reservation.consumer_id:
        return str(reservation.consumer_id)

    try:
        from src.services.identity_resolution_service import identity_resolution_service

        consumer_id = await identity_resolution_service.resolve(
            session,
            phone=reservation.customer_phone,
            display_name=reservation.customer_name,
        )
        if consumer_id:
            reservation.consumer_id = consumer_id
            await session.flush()
            logger.info(
                "reservation_consumer_linked",
                reservation_id=reservation.id,
                consumer_id=str(consumer_id),
            )
        return str(consumer_id) if consumer_id else None
    except (sa_exc.SQLAlchemyError, ImportError, ValueError) as e:
        logger.warning("consumer_link_failed", error=str(e))
        return None


async def link_consumer_to_queue(
    session: AsyncSession,
    queue: Queue,
) -> Optional[str]:
    """等位记录自动关联CDP消费者ID。"""
    if queue.consumer_id:
        return str(queue.consumer_id)

    try:
        from src.services.identity_resolution_service import identity_resolution_service

        consumer_id = await identity_resolution_service.resolve(
            session,
            phone=queue.customer_phone,
            display_name=queue.customer_name,
        )
        if consumer_id:
            queue.consumer_id = consumer_id
            await session.flush()
        return str(consumer_id) if consumer_id else None
    except (sa_exc.SQLAlchemyError, ImportError, ValueError) as e:
        logger.warning("queue_consumer_link_failed", error=str(e))
        return None


async def convert_queue_to_reservation(
    session: AsyncSession,
    queue_id: str,
    table_number: Optional[str] = None,
) -> Reservation:
    """
    等位叫号入座后自动创建预订记录（Gap #2 修复）。

    流程：Queue.CALLED/SEATED → 自动创建 Reservation(ARRIVED/SEATED)
    """
    import uuid

    result = await session.execute(select(Queue).where(Queue.queue_id == queue_id))
    queue = result.scalar_one_or_none()
    if not queue:
        raise ValueError(f"等位记录不存在: {queue_id}")
    if queue.status not in (QueueStatus.CALLED, QueueStatus.SEATED):
        raise ValueError(f"等位状态 {queue.status.value} 不允许转换为预订")

    today = date.today()
    now = datetime.now()
    reservation_id = f"RES_{today.strftime('%Y%m%d')}_{str(uuid.uuid4())[:8].upper()}"

    target_status = ReservationStatus.SEATED if queue.status == QueueStatus.SEATED else ReservationStatus.ARRIVED

    reservation = Reservation(
        id=reservation_id,
        store_id=queue.store_id,
        customer_name=queue.customer_name,
        customer_phone=queue.customer_phone,
        consumer_id=queue.consumer_id,
        reservation_type=ReservationType.REGULAR,
        reservation_date=today,
        reservation_time=now.time().replace(microsecond=0),
        party_size=queue.party_size,
        table_number=table_number or queue.table_number,
        status=target_status,
        arrival_time=now,
        special_requests=queue.special_requests,
        notes=f"由等位转换 (排队号: {queue.queue_number})",
    )

    session.add(reservation)
    await session.flush()
    logger.info(
        "queue_converted_to_reservation",
        queue_id=queue_id,
        reservation_id=reservation_id,
        queue_number=queue.queue_number,
    )
    return reservation


# ══════════════════════════════════════════════════════════════════
# Phase 2: 到店前 — 千人千面推送 + 智能桌台推荐
# ══════════════════════════════════════════════════════════════════


async def recommend_table(
    session: AsyncSession,
    store_id: str,
    party_size: int,
    reservation_date: date,
    reservation_time: time,
    preference: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    智能桌台推荐（Gap #3 修复）。

    按 party_size 匹配桌台容量 + 排除已占用桌台。
    preference: "包厢"/"大厅"/"VIP" — 偏好过滤
    """
    from src.models.floor_plan import TableDefinition, TableStatus

    # 查询所有活跃桌台
    stmt = select(TableDefinition).where(
        and_(
            TableDefinition.store_id == store_id,
            TableDefinition.is_active == True,  # noqa: E712
            TableDefinition.status != TableStatus.MAINTENANCE,
        )
    )
    result = await session.execute(stmt)
    tables = result.scalars().all()

    # 查询当日已占用桌台
    time_start = (datetime.combine(reservation_date, reservation_time) - timedelta(hours=1)).time()
    time_end = (datetime.combine(reservation_date, reservation_time) + timedelta(hours=1)).time()

    occupied_stmt = select(Reservation.table_number).where(
        and_(
            Reservation.store_id == store_id,
            Reservation.reservation_date == reservation_date,
            Reservation.reservation_time >= time_start,
            Reservation.reservation_time <= time_end,
            Reservation.status.in_(
                [
                    ReservationStatus.PENDING,
                    ReservationStatus.CONFIRMED,
                    ReservationStatus.ARRIVED,
                    ReservationStatus.SEATED,
                ]
            ),
            Reservation.table_number != None,  # noqa: E711
        )
    )
    occupied_result = await session.execute(occupied_stmt)
    occupied_tables = {r[0] for r in occupied_result.all()}

    # 过滤 + 评分
    candidates = []
    for t in tables:
        if t.table_number in occupied_tables:
            continue

        min_cap = t.min_capacity or 1
        max_cap = t.max_capacity or 4
        table_type = t.table_type or "大厅"

        # 容量匹配（人数在桌台范围内）
        if party_size < min_cap or party_size > max_cap:
            continue

        # 偏好过滤
        if preference and preference not in table_type:
            continue

        # 评分：容量匹配度（越贴合越高分）
        capacity_fit = 1.0 - abs(party_size - (min_cap + max_cap) / 2) / max(max_cap, 1)
        # 包厢加分（高端餐厅偏好）
        type_bonus = 0.2 if "包厢" in table_type or "VIP" in table_type else 0.0

        candidates.append(
            {
                "table_number": t.table_number,
                "table_type": table_type,
                "min_capacity": min_cap,
                "max_capacity": max_cap,
                "floor": t.floor or 1,
                "area_name": t.area_name or "",
                "score": round(capacity_fit + type_bonus, 2),
                "reason": _table_reason(table_type, min_cap, max_cap, party_size),
            }
        )

    # 按评分降序
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:5]


def _table_reason(table_type: str, min_cap: int, max_cap: int, party_size: int) -> str:
    if "包厢" in table_type or "VIP" in table_type:
        return f"{table_type}，容纳{min_cap}-{max_cap}人，私密安静"
    if party_size == max_cap:
        return f"容量完全匹配 ({max_cap}人桌)"
    return f"{table_type}，容纳{min_cap}-{max_cap}人"


async def generate_pre_arrival_push(
    session: AsyncSession,
    reservation_id: str,
) -> Dict[str, Any]:
    """
    到店前千人千面推送内容生成。

    T-1天 或 T-4小时触发。
    内容：确认信息 + 个性化菜品推荐 + 消费场景（生日/商务/家庭）。
    """
    result = await session.execute(select(Reservation).where(Reservation.id == reservation_id))
    reservation = result.scalar_one_or_none()
    if not reservation:
        return {"error": "预订不存在"}

    # 获取消费者画像
    profile = await _get_consumer_profile(reservation.consumer_id, reservation.customer_phone)

    # 千人千面内容
    content = {
        "reservation_id": reservation.id,
        "customer_name": reservation.customer_name,
        "reservation_date": reservation.reservation_date.isoformat(),
        "reservation_time": reservation.reservation_time.strftime("%H:%M"),
        "party_size": reservation.party_size,
        "store_id": reservation.store_id,
        "table_info": reservation.table_number or reservation.room_name or "待分配",
    }

    # 消费场景识别
    scene = _detect_consumption_scene(reservation, profile)
    content["scene"] = scene

    # 个性化推荐
    recommendations = []
    if profile.get("tags"):
        tags = profile["tags"]
        if "海鲜爱好者" in tags or "高频" in tags:
            recommendations.append(
                {
                    "type": "favorite_dish",
                    "message": "您上次点的招牌菜深受好评，本次为您预留食材",
                }
            )
        if "宴会客户" in tags:
            recommendations.append(
                {
                    "type": "upgrade",
                    "message": "VIP客户专享：包厢免费升级",
                }
            )

    if scene["type"] == "birthday":
        recommendations.append(
            {
                "type": "birthday_surprise",
                "message": "生日快乐！我们已为您准备了一份小惊喜",
            }
        )
    elif scene["type"] == "business":
        recommendations.append(
            {
                "type": "business_menu",
                "message": "商务宴请推荐：精选商务套餐，含发票服务",
            }
        )

    # 老客户历史偏好
    if profile.get("total_order_count", 0) >= 3:
        recommendations.append(
            {
                "type": "reorder",
                "message": f"根据您{profile.get('total_order_count', 0)}次消费记录，为您推荐心水菜品",
            }
        )

    content["recommendations"] = recommendations

    # 生成推送文案（调用 JourneyNarrator 千人千面）
    content["push_message"] = _format_pre_arrival_message(reservation, profile, scene)

    return content


async def get_pre_arrival_reservations(
    session: AsyncSession,
    store_id: str,
    hours_ahead: int = 24,
) -> List[Dict[str, Any]]:
    """
    获取即将到来的预订（用于定时触发推送）。

    Gap #1 修复：No-Show自动催确认。
    """
    now = datetime.now()
    target_time = now + timedelta(hours=hours_ahead)

    stmt = (
        select(Reservation)
        .where(
            and_(
                Reservation.store_id == store_id,
                Reservation.status.in_(
                    [
                        ReservationStatus.PENDING,
                        ReservationStatus.CONFIRMED,
                    ]
                ),
                Reservation.reservation_date >= now.date(),
                Reservation.reservation_date <= target_time.date(),
            )
        )
        .order_by(Reservation.reservation_date, Reservation.reservation_time)
    )

    result = await session.execute(stmt)
    reservations = result.scalars().all()

    upcoming = []
    for r in reservations:
        res_dt = datetime.combine(r.reservation_date, r.reservation_time)
        hours_until = (res_dt - now).total_seconds() / 3600

        if hours_until < 0 or hours_until > hours_ahead:
            continue

        upcoming.append(
            {
                "reservation_id": r.id,
                "customer_name": r.customer_name,
                "customer_phone": r.customer_phone,
                "consumer_id": str(r.consumer_id) if r.consumer_id else None,
                "reservation_date": r.reservation_date.isoformat(),
                "reservation_time": r.reservation_time.strftime("%H:%M"),
                "party_size": r.party_size,
                "status": r.status.value,
                "hours_until": round(hours_until, 1),
                "needs_confirmation": r.status == ReservationStatus.PENDING,
            }
        )

    return upcoming


async def send_pre_arrival_reminders(
    session: AsyncSession,
    store_id: str,
) -> Dict[str, Any]:
    """
    批量发送到店前提醒（Celery定时任务调用）。

    规则：
    - T-24h：确认推送（PENDING → 催确认 / CONFIRMED → 温馨提醒）
    - T-4h：最终提醒（含路线/停车信息）
    """
    sent_count = 0
    failed_count = 0

    # T-24h 批次
    upcoming_24h = await get_pre_arrival_reservations(session, store_id, hours_ahead=25)
    for item in upcoming_24h:
        if 20 <= item["hours_until"] <= 25:
            try:
                content = await generate_pre_arrival_push(session, item["reservation_id"])
                await _send_push(item, content, push_type="t_minus_24h")
                sent_count += 1
            except (ConnectionError, TimeoutError, ValueError) as e:
                logger.warning("pre_arrival_push_failed", reservation_id=item["reservation_id"], error=str(e))
                failed_count += 1

    # T-4h 批次
    upcoming_4h = await get_pre_arrival_reservations(session, store_id, hours_ahead=5)
    for item in upcoming_4h:
        if 3 <= item["hours_until"] <= 5:
            try:
                content = await generate_pre_arrival_push(session, item["reservation_id"])
                await _send_push(item, content, push_type="t_minus_4h")
                sent_count += 1
            except (ConnectionError, TimeoutError, ValueError) as e:
                logger.warning("pre_arrival_push_failed_4h", reservation_id=item["reservation_id"], error=str(e))
                failed_count += 1

    return {"sent": sent_count, "failed": failed_count, "store_id": store_id}


# ══════════════════════════════════════════════════════════════════
# Phase 3: 老客识别 — 点单偏好 + 生日场景 + 标签自动化
# ══════════════════════════════════════════════════════════════════


async def recognize_returning_customer(
    session: AsyncSession,
    customer_phone: str,
    store_id: str,
) -> Dict[str, Any]:
    """
    老客户识别 + 消费画像聚合。

    返回：历史偏好、上次消费、RFM等级、标签、生日信息、推荐动作。
    """
    profile = await _get_consumer_profile(None, customer_phone)

    # 历史预订
    res_stmt = (
        select(Reservation)
        .where(
            and_(
                Reservation.customer_phone == customer_phone,
                Reservation.status == ReservationStatus.COMPLETED,
            )
        )
        .order_by(Reservation.reservation_date.desc())
        .limit(10)
    )
    res_result = await session.execute(res_stmt)
    past_reservations = res_result.scalars().all()

    # 统计
    total_visits = len(past_reservations)
    stores_visited = list({r.store_id for r in past_reservations})
    preferred_times = {}
    preferred_types = {}
    for r in past_reservations:
        hour = r.reservation_time.hour if r.reservation_time else 0
        slot = "午餐" if 10 <= hour <= 14 else "晚餐" if 16 <= hour <= 21 else "其他"
        preferred_times[slot] = preferred_times.get(slot, 0) + 1
        t = r.reservation_type.value if hasattr(r.reservation_type, "value") else str(r.reservation_type)
        preferred_types[t] = preferred_types.get(t, 0) + 1

    # 生日检测
    birthday_info = _check_birthday_proximity(profile)

    # 自动标签推荐
    auto_tags = _generate_auto_tags(profile, total_visits, past_reservations)

    result = {
        "is_returning": total_visits > 0,
        "total_visits": total_visits,
        "rfm_level": profile.get("rfm_level", "S3"),
        "tags": profile.get("tags", []),
        "auto_tags": auto_tags,
        "preferred_times": preferred_times,
        "preferred_types": preferred_types,
        "stores_visited": stores_visited,
        "last_visit": past_reservations[0].reservation_date.isoformat() if past_reservations else None,
        "birthday_info": birthday_info,
        "lifetime_spend_yuan": round(profile.get("total_order_amount_fen", 0) / 100, 2),
    }

    # 推荐动作
    actions = []
    if birthday_info and birthday_info.get("is_upcoming"):
        actions.append(
            {
                "action": "birthday_surprise",
                "message": f"客户生日在{birthday_info['days_until']}天后，建议赠送生日蛋糕",
                "priority": "high",
            }
        )
    if total_visits >= 5 and "VIP" not in (profile.get("tags") or []):
        actions.append(
            {
                "action": "vip_upgrade",
                "message": f"已消费{total_visits}次（¥{result['lifetime_spend_yuan']}），建议升级VIP",
                "priority": "medium",
            }
        )
    if profile.get("rfm_level") in ("S4", "S5"):
        actions.append(
            {
                "action": "reactivation",
                "message": "客户处于流失风险，建议发送唤醒优惠券",
                "priority": "high",
            }
        )

    result["recommended_actions"] = actions
    return result


async def trigger_birthday_journey(
    session: AsyncSession,
    store_id: str,
    horizon_days: int = 3,
) -> List[Dict[str, Any]]:
    """
    扫描即将生日的客户并触发生日旅程。

    集成 BirthdayReminderService + JourneyOrchestrator。
    """
    triggered = []
    try:
        from src.services.birthday_reminder_service import BirthdayReminderService

        birthday_svc = BirthdayReminderService()
        events = await birthday_svc.scan_upcoming_events(session, store_id, horizon_days)

        for event in events:
            try:
                from src.services.journey_orchestrator import JourneyOrchestrator

                orchestrator = JourneyOrchestrator()
                result = await orchestrator.trigger(
                    customer_id=event["customer_id"],
                    store_id=store_id,
                    journey_id="birthday_greeting",
                    db=session,
                )
                triggered.append(
                    {
                        "customer_id": event["customer_id"],
                        "event_type": event.get("event_type", "birthday"),
                        "days_until": event.get("days_until", 0),
                        "journey_triggered": True,
                    }
                )
            except (sa_exc.SQLAlchemyError, ImportError, ValueError) as e:
                logger.warning("birthday_journey_trigger_failed", customer_id=event.get("customer_id"), error=str(e))
                triggered.append(
                    {
                        "customer_id": event.get("customer_id"),
                        "journey_triggered": False,
                        "error": str(e),
                    }
                )
    except (sa_exc.SQLAlchemyError, ImportError, ValueError) as e:
        logger.warning("birthday_scan_failed", error=str(e))

    return triggered


# ══════════════════════════════════════════════════════════════════
# Phase 4: 餐中 — 巡台检查 + 问题识别 + 知识学习
# ══════════════════════════════════════════════════════════════════

# 巡台检查项（5大维度）
PATROL_CHECKLIST = [
    {
        "id": "food_quality",
        "name": "菜品质量",
        "category": "菜品",
        "items": ["菜品温度适宜", "摆盘整洁", "份量达标", "口味正常"],
    },
    {
        "id": "service_speed",
        "name": "服务响应",
        "category": "服务",
        "items": ["上菜时间合理", "服务员响应及时", "主动加水/换骨碟"],
    },
    {
        "id": "environment",
        "name": "环境卫生",
        "category": "环境",
        "items": ["桌面整洁", "地面干净", "空调温度适宜", "灯光/音乐适当"],
    },
    {"id": "customer_mood", "name": "客户情绪", "category": "客户", "items": ["客户表情满意", "无投诉/不满", "用餐节奏正常"]},
    {
        "id": "special_needs",
        "name": "特殊需求",
        "category": "需求",
        "items": ["忌口已落实", "儿童椅/加位已安排", "生日/宴会布置到位"],
    },
]


async def create_patrol_record(
    session: AsyncSession,
    store_id: str,
    table_number: str,
    patrol_by: str,
    checklist_results: Dict[str, Any],
    issues: Optional[List[Dict[str, str]]] = None,
    reservation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    创建巡台记录。

    checklist_results: {"food_quality": 90, "service_speed": 85, ...}
    issues: [{"type": "菜品", "description": "鱼头偏咸", "severity": "medium"}]
    """
    from src.models.neural_event_log import NeuralEventLog

    now = datetime.utcnow()
    scores = checklist_results
    total_score = round(sum(scores.values()) / max(len(scores), 1), 1)

    # 问题识别
    identified_issues = issues or []
    has_critical = any(i.get("severity") == "critical" for i in identified_issues)

    # 存储为神经事件（可追溯 + 可分析）
    event_data = {
        "store_id": store_id,
        "table_number": table_number,
        "patrol_by": patrol_by,
        "reservation_id": reservation_id,
        "checklist_scores": scores,
        "total_score": total_score,
        "issues": identified_issues,
        "has_critical": has_critical,
        "patrol_time": now.isoformat(),
    }

    try:
        from src.services.neural_system import NeuralSystemOrchestrator

        orchestrator = NeuralSystemOrchestrator()
        await orchestrator.emit_event(
            event_type="quality.patrol_completed",
            event_source="floor_manager",
            data=event_data,
            store_id=store_id,
            priority="high" if has_critical else "normal",
        )
    except (ImportError, ConnectionError, ValueError) as e:
        logger.warning("patrol_event_emit_failed", error=str(e))

    # 知识学习建议
    learning = _generate_learning_suggestions(scores, identified_issues)

    result = {
        "patrol_time": now.isoformat(),
        "store_id": store_id,
        "table_number": table_number,
        "total_score": total_score,
        "scores": scores,
        "issues": identified_issues,
        "issue_count": len(identified_issues),
        "has_critical": has_critical,
        "learning_suggestions": learning,
    }

    # 关键问题自动通知店长
    if has_critical:
        await _notify_critical_issue(store_id, table_number, identified_issues)

    return result


def _generate_learning_suggestions(
    scores: Dict[str, float],
    issues: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """根据巡台评分和问题生成知识学习建议。"""
    suggestions = []

    for category, score in scores.items():
        if score < 70:
            suggestions.append(
                {
                    "category": category,
                    "score": score,
                    "suggestion": _LEARNING_MAP.get(category, "请关注该项服务标准"),
                    "priority": "high" if score < 50 else "medium",
                }
            )

    # 从问题中提取学习点
    for issue in issues:
        issue_type = issue.get("type", "")
        if issue_type == "菜品":
            suggestions.append(
                {
                    "category": "kitchen_knowledge",
                    "suggestion": f"菜品问题：{issue.get('description', '')}，建议回顾出品标准",
                    "priority": issue.get("severity", "medium"),
                }
            )
        elif issue_type == "服务":
            suggestions.append(
                {
                    "category": "service_training",
                    "suggestion": f"服务问题：{issue.get('description', '')}，建议加强服务培训",
                    "priority": issue.get("severity", "medium"),
                }
            )

    return suggestions


_LEARNING_MAP = {
    "food_quality": "建议学习：《出品质量标准手册》— 温度/摆盘/份量SOP",
    "service_speed": "建议学习：《服务响应标准》— 3分钟首次响应，15分钟上首道菜",
    "environment": "建议学习：《环境管理手册》— 清洁频次/温湿度标准",
    "customer_mood": "建议学习：《客户情绪识别》— 微表情/肢体语言解读",
    "special_needs": "建议学习：《特殊需求服务指南》— 忌口确认流程/儿童服务标准",
}


# ══════════════════════════════════════════════════════════════════
# Phase 5: 离店前 — 满意度调查 + 营销触达
# ══════════════════════════════════════════════════════════════════


async def trigger_satisfaction_survey(
    session: AsyncSession,
    reservation_id: str,
) -> Dict[str, Any]:
    """
    客人离店前触发满意度调查。

    在 SEATED → COMPLETED 转换时自动调用。
    推送微信满意度问卷 + 收集NPS评分。
    """
    result = await session.execute(select(Reservation).where(Reservation.id == reservation_id))
    reservation = result.scalar_one_or_none()
    if not reservation:
        return {"error": "预订不存在"}

    profile = await _get_consumer_profile(reservation.consumer_id, reservation.customer_phone)

    # 个性化调查内容
    survey = {
        "reservation_id": reservation.id,
        "customer_name": reservation.customer_name,
        "customer_phone": reservation.customer_phone,
        "store_id": reservation.store_id,
        "survey_type": "post_dining",
        "questions": [
            {"id": "nps", "type": "rating", "text": "您愿意推荐我们给朋友吗？(0-10)", "required": True},
            {"id": "food", "type": "rating", "text": "菜品满意度 (1-5)", "required": True},
            {"id": "service", "type": "rating", "text": "服务满意度 (1-5)", "required": True},
            {"id": "environment", "type": "rating", "text": "环境满意度 (1-5)", "required": True},
            {"id": "feedback", "type": "text", "text": "还有什么建议？", "required": False},
        ],
    }

    # 营销触达（根据消费等级）
    marketing = []
    rfm_level = profile.get("rfm_level", "S3")
    total_visits = profile.get("total_order_count", 0)

    if rfm_level in ("S1", "S2"):
        marketing.append(
            {
                "type": "vip_reward",
                "message": f"感谢您第{total_visits + 1}次光临！VIP客户专享：下次用餐赠送精美甜品",
            }
        )
    elif rfm_level == "S3":
        marketing.append(
            {
                "type": "next_visit_coupon",
                "message": "感谢用餐！赠送您一张满200减30优惠券，期待再次光临",
                "coupon": "next_visit_30",
            }
        )
    else:
        marketing.append(
            {
                "type": "review_incentive",
                "message": "写好评送小菜一份，下次到店出示即可",
            }
        )

    survey["marketing"] = marketing

    # 推送
    try:
        await _send_push(
            {"customer_phone": reservation.customer_phone, "reservation_id": reservation.id},
            survey,
            push_type="satisfaction_survey",
        )
        survey["sent"] = True
    except (ConnectionError, TimeoutError, ImportError) as e:
        logger.warning("satisfaction_survey_send_failed", error=str(e))
        survey["sent"] = False

    return survey


# ══════════════════════════════════════════════════════════════════
# Phase 6: 离店后 — 评价管理 + 企业售后
# ══════════════════════════════════════════════════════════════════


async def process_post_dining_review(
    session: AsyncSession,
    reservation_id: str,
    review_source: str,
    review_text: str,
    platform_rating: Optional[int] = None,
) -> Dict[str, Any]:
    """
    处理客户离店后评价（美团/大众点评/企微/内部）。

    流程：评价接收 → 情感分析 → 自动分类 → 触发售后动作。
    """
    result = await session.execute(select(Reservation).where(Reservation.id == reservation_id))
    reservation = result.scalar_one_or_none()

    # 情感分析
    sentiment = await _analyze_sentiment(review_text)

    review_record = {
        "reservation_id": reservation_id,
        "store_id": reservation.store_id if reservation else None,
        "customer_name": reservation.customer_name if reservation else None,
        "customer_phone": reservation.customer_phone if reservation else None,
        "review_source": review_source,
        "review_text": review_text,
        "platform_rating": platform_rating,
        "sentiment": sentiment,
        "processed_at": datetime.utcnow().isoformat(),
    }

    # 自动售后动作
    actions = []
    if sentiment["sentiment"] == "negative":
        actions.append(
            {
                "action": "review_repair",
                "message": f"差评预警：{sentiment.get('key_points', ['请关注'])[0]}",
                "priority": "critical",
                "auto_response": _generate_review_response(sentiment, "negative"),
            }
        )
        # 触发差评修复旅程
        if reservation and reservation.consumer_id:
            try:
                from src.services.journey_orchestrator import JourneyOrchestrator

                orchestrator = JourneyOrchestrator()
                await orchestrator.trigger(
                    customer_id=str(reservation.consumer_id),
                    store_id=reservation.store_id,
                    journey_id="dormant_wakeup",  # 复用唤醒旅程做挽回
                    db=session,
                )
                actions.append({"action": "repair_journey_triggered", "status": "success"})
            except (sa_exc.SQLAlchemyError, ImportError, ValueError) as e:
                logger.warning("repair_journey_failed", error=str(e))

    elif sentiment["sentiment"] == "positive":
        actions.append(
            {
                "action": "thank_and_promote",
                "message": "好评！可请客户转发至朋友圈获得小福利",
                "auto_response": _generate_review_response(sentiment, "positive"),
            }
        )

    review_record["actions"] = actions

    # 发送神经事件
    try:
        from src.services.neural_system import NeuralSystemOrchestrator

        orchestrator = NeuralSystemOrchestrator()
        await orchestrator.emit_event(
            event_type="crm.review_received",
            event_source=review_source,
            data=review_record,
            store_id=review_record.get("store_id", ""),
        )
    except (ImportError, ConnectionError, ValueError) as e:
        logger.warning("review_event_failed", error=str(e))

    return review_record


async def get_post_dining_summary(
    session: AsyncSession,
    store_id: str,
    days: int = 7,
) -> Dict[str, Any]:
    """
    离店后评价+售后综合管理看板。

    聚合：评价分布 + 情感趋势 + 需跟进客户 + 售后待处理。
    """
    since = date.today() - timedelta(days=days)

    # 近N天已完成预订
    stmt = select(Reservation).where(
        and_(
            Reservation.store_id == store_id,
            Reservation.status == ReservationStatus.COMPLETED,
            Reservation.reservation_date >= since,
        )
    )
    result = await session.execute(stmt)
    completed = result.scalars().all()

    # 统计
    total_completed = len(completed)
    no_show_stmt = select(func.count(Reservation.id)).where(
        and_(
            Reservation.store_id == store_id,
            Reservation.status == ReservationStatus.NO_SHOW,
            Reservation.reservation_date >= since,
        )
    )
    no_show_result = await session.execute(no_show_stmt)
    no_show_count = no_show_result.scalar() or 0

    cancelled_stmt = select(func.count(Reservation.id)).where(
        and_(
            Reservation.store_id == store_id,
            Reservation.status == ReservationStatus.CANCELLED,
            Reservation.reservation_date >= since,
        )
    )
    cancelled_result = await session.execute(cancelled_stmt)
    cancelled_count = cancelled_result.scalar() or 0

    # 需要跟进的客户（no-show + 取消的）
    followup_needed = []
    followup_stmt = (
        select(Reservation)
        .where(
            and_(
                Reservation.store_id == store_id,
                Reservation.status.in_([ReservationStatus.NO_SHOW, ReservationStatus.CANCELLED]),
                Reservation.reservation_date >= since,
            )
        )
        .order_by(Reservation.reservation_date.desc())
        .limit(20)
    )
    followup_result = await session.execute(followup_stmt)
    for r in followup_result.scalars().all():
        followup_needed.append(
            {
                "reservation_id": r.id,
                "customer_name": r.customer_name,
                "customer_phone": r.customer_phone,
                "status": r.status.value,
                "date": r.reservation_date.isoformat(),
                "followup_type": "no_show_recovery" if r.status == ReservationStatus.NO_SHOW else "cancellation_inquiry",
            }
        )

    return {
        "store_id": store_id,
        "period_days": days,
        "total_completed": total_completed,
        "no_show_count": no_show_count,
        "cancelled_count": cancelled_count,
        "completion_rate": round(total_completed / max(total_completed + no_show_count + cancelled_count, 1), 3),
        "followup_needed": followup_needed,
        "followup_count": len(followup_needed),
    }


# ══════════════════════════════════════════════════════════════════
# 内部辅助函数
# ══════════════════════════════════════════════════════════════════


async def _get_consumer_profile(
    consumer_id: Optional[Any],
    phone: Optional[str] = None,
) -> Dict[str, Any]:
    """获取消费者画像（CDP）。"""
    try:
        from src.services.identity_resolution_service import identity_resolution_service

        if consumer_id:
            from src.core.database import get_db_session
            from src.models.consumer_identity import ConsumerIdentity

            async with get_db_session() as session:
                result = await session.execute(select(ConsumerIdentity).where(ConsumerIdentity.id == consumer_id))
                consumer = result.scalar_one_or_none()
                if consumer:
                    return {
                        "consumer_id": str(consumer.id),
                        "display_name": consumer.display_name,
                        "birth_date": consumer.birth_date.isoformat() if consumer.birth_date else None,
                        "tags": consumer.tags or [],
                        "total_order_count": consumer.total_order_count or 0,
                        "total_order_amount_fen": consumer.total_order_amount_fen or 0,
                        "rfm_recency_days": consumer.rfm_recency_days,
                        "rfm_frequency": consumer.rfm_frequency,
                        "rfm_monetary_fen": consumer.rfm_monetary_fen,
                        "rfm_level": _calc_rfm_level(
                            consumer.rfm_recency_days,
                            consumer.rfm_frequency,
                            consumer.rfm_monetary_fen,
                        ),
                    }
    except (sa_exc.SQLAlchemyError, ImportError, ValueError) as e:
        logger.debug("consumer_profile_fallback", error=str(e))

    return {
        "consumer_id": str(consumer_id) if consumer_id else None,
        "display_name": None,
        "tags": [],
        "total_order_count": 0,
        "total_order_amount_fen": 0,
        "rfm_level": "S3",
    }


def _calc_rfm_level(recency: Optional[int], frequency: Optional[int], monetary: Optional[int]) -> str:
    """简化RFM等级计算。"""
    r = (
        5
        if (recency or 999) <= 7
        else 4 if (recency or 999) <= 14 else 3 if (recency or 999) <= 30 else 2 if (recency or 999) <= 60 else 1
    )
    f = (
        5
        if (frequency or 0) >= 20
        else 4 if (frequency or 0) >= 10 else 3 if (frequency or 0) >= 5 else 2 if (frequency or 0) >= 2 else 1
    )
    m = (
        5
        if (monetary or 0) >= 500000
        else 4 if (monetary or 0) >= 200000 else 3 if (monetary or 0) >= 80000 else 2 if (monetary or 0) >= 20000 else 1
    )
    total = r + f + m
    if total >= 13:
        return "S1"
    if total >= 10:
        return "S2"
    if total >= 7:
        return "S3"
    if total >= 4:
        return "S4"
    return "S5"


def _detect_consumption_scene(
    reservation: Reservation,
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    """识别消费场景（生日/商务/家庭/宴会/普通）。"""
    scene = {"type": "regular", "label": "日常用餐"}

    # 生日检测
    birthday_info = _check_birthday_proximity(profile)
    if birthday_info and birthday_info.get("is_upcoming"):
        scene = {"type": "birthday", "label": "生日聚餐", "details": birthday_info}
        return scene

    # 宴会
    if reservation.reservation_type == ReservationType.BANQUET:
        scene = {"type": "banquet", "label": "宴会活动"}
        return scene

    # 包厢 → 商务/VIP
    if reservation.reservation_type == ReservationType.PRIVATE_ROOM:
        if reservation.party_size >= 6:
            scene = {"type": "business", "label": "商务宴请"}
        else:
            scene = {"type": "vip_private", "label": "VIP私享"}
        return scene

    # 大人数 → 家庭聚餐
    if reservation.party_size >= 8:
        scene = {"type": "family", "label": "家庭聚餐"}
    elif reservation.party_size >= 4:
        scene = {"type": "friends", "label": "朋友聚会"}

    return scene


def _check_birthday_proximity(profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """检查生日是否临近。"""
    birth_str = profile.get("birth_date")
    if not birth_str:
        return None

    try:
        if isinstance(birth_str, str):
            birth = date.fromisoformat(birth_str)
        else:
            birth = birth_str

        today = date.today()
        this_year_birthday = birth.replace(year=today.year)
        if this_year_birthday < today:
            this_year_birthday = birth.replace(year=today.year + 1)

        days_until = (this_year_birthday - today).days
        return {
            "birth_date": birth.isoformat(),
            "days_until": days_until,
            "is_upcoming": days_until <= 7,
            "is_today": days_until == 0,
        }
    except (ValueError, TypeError):
        return None


def _generate_auto_tags(
    profile: Dict[str, Any],
    total_visits: int,
    past_reservations: list,
) -> List[str]:
    """根据消费行为自动生成标签。"""
    tags = []

    if total_visits >= 10:
        tags.append("铂金常客")
    elif total_visits >= 5:
        tags.append("高频客户")
    elif total_visits >= 2:
        tags.append("回头客")

    amount = profile.get("total_order_amount_fen", 0) / 100
    if amount >= 5000:
        tags.append("高消费")
    elif amount >= 2000:
        tags.append("中高消费")

    # 偏好类型
    banquet_count = sum(1 for r in past_reservations if r.reservation_type == ReservationType.BANQUET)
    if banquet_count >= 2:
        tags.append("宴会客户")

    private_room_count = sum(1 for r in past_reservations if r.reservation_type == ReservationType.PRIVATE_ROOM)
    if private_room_count >= 2:
        tags.append("包厢偏好")

    if profile.get("birth_date"):
        tags.append("生日已录入")

    return tags


def _format_pre_arrival_message(
    reservation: Reservation,
    profile: Dict[str, Any],
    scene: Dict[str, Any],
) -> str:
    """格式化千人千面推送文案。"""
    name = reservation.customer_name
    date_str = reservation.reservation_date.strftime("%m月%d日")
    time_str = reservation.reservation_time.strftime("%H:%M")
    party = reservation.party_size
    table = reservation.table_number or reservation.room_name or "待安排"

    # 称呼（根据RFM等级）
    rfm = profile.get("rfm_level", "S3")
    greeting = {
        "S1": f"尊敬的VIP客户{name}",
        "S2": f"亲爱的{name}",
        "S3": f"{name}您好",
        "S4": f"{name}您好",
        "S5": f"{name}您好",
    }.get(rfm, f"{name}您好")

    msg = f"【徐记海鲜·预订提醒】\n{greeting}，\n"
    msg += f"您预订的{date_str} {time_str} {party}位用餐已确认。\n"
    msg += f"桌位：{table}\n"

    if scene["type"] == "birthday":
        msg += "🎂 我们已为您准备生日惊喜！\n"
    elif scene["type"] == "business":
        msg += "📋 商务宴请支持开具发票，如需提前安排请告知。\n"

    total_visits = profile.get("total_order_count", 0)
    if total_visits >= 5:
        msg += f"感谢您第{total_visits + 1}次光临，期待为您服务！"
    else:
        msg += "期待您的光临！"

    return msg


async def _send_push(
    target: Dict[str, Any],
    content: Dict[str, Any],
    push_type: str,
) -> None:
    """发送推送（企微/短信），失败不阻塞。"""
    try:
        from src.services.wechat_trigger_service import wechat_trigger_service

        if hasattr(wechat_trigger_service, "trigger_push"):
            await wechat_trigger_service.trigger_push(
                f"reservation.{push_type}",
                {
                    "customer_phone": target.get("customer_phone", ""),
                    "reservation_id": target.get("reservation_id", ""),
                    "content": content,
                },
            )
    except (ImportError, ConnectionError, TimeoutError, ValueError) as e:
        logger.debug("push_send_fallback", push_type=push_type, error=str(e))


async def _notify_critical_issue(
    store_id: str,
    table_number: str,
    issues: List[Dict[str, str]],
) -> None:
    """关键问题自动通知店长。"""
    critical = [i for i in issues if i.get("severity") == "critical"]
    if not critical:
        return
    try:
        from src.services.wechat_trigger_service import wechat_trigger_service

        descriptions = "; ".join(i.get("description", "") for i in critical)
        await wechat_trigger_service.trigger_push(
            "quality.critical_issue",
            {
                "store_id": store_id,
                "table_number": table_number,
                "issues": descriptions,
            },
        )
    except (ImportError, ConnectionError, TimeoutError, ValueError) as e:
        logger.debug("critical_notify_failed", error=str(e))


async def _analyze_sentiment(text: str) -> Dict[str, Any]:
    """评价情感分析（调用现有服务或降级）。"""
    try:
        from src.services.customer_sentiment_service import CustomerReview, CustomerSentimentService

        svc = CustomerSentimentService()
        review = CustomerReview(text=text, source="internal")
        results = await svc.analyze_batch([review])
        if results:
            r = results[0]
            return {
                "sentiment": r.sentiment,
                "confidence": r.confidence,
                "key_points": r.key_points,
            }
    except (ImportError, ConnectionError, TimeoutError, ValueError) as e:
        logger.debug("sentiment_fallback", error=str(e))

    # 关键词降级分析
    negative_keywords = ["差", "难吃", "慢", "脏", "贵", "失望", "投诉", "不满", "退"]
    positive_keywords = ["好", "棒", "鲜", "赞", "满意", "推荐", "服务好", "环境好"]

    neg_count = sum(1 for k in negative_keywords if k in text)
    pos_count = sum(1 for k in positive_keywords if k in text)

    if neg_count > pos_count:
        return {"sentiment": "negative", "confidence": 0.6, "key_points": ["关键词匹配：负面"]}
    if pos_count > neg_count:
        return {"sentiment": "positive", "confidence": 0.6, "key_points": ["关键词匹配：正面"]}
    return {"sentiment": "neutral", "confidence": 0.5, "key_points": []}


def _generate_review_response(sentiment: Dict[str, Any], polarity: str) -> str:
    """生成评价自动回复。"""
    if polarity == "negative":
        points = sentiment.get("key_points", [])
        issue = points[0] if points else "您的反馈"
        return (
            f"非常抱歉给您带来不好的体验。关于【{issue}】，"
            f"我们已第一时间安排改进。店长将在24小时内与您联系，"
            f"诚邀您再次光临，为您提供更好的服务。"
        )
    return "感谢您的好评与认可！您的满意是我们最大的动力。" "期待再次为您服务，祝您生活愉快！"
