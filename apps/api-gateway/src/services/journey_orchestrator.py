"""
旅程编排引擎
Journey Orchestrator

将现有单步旅程升级为多步延迟触发旅程：
  T+0   → 立即执行（欢迎消息 + 发券）
  T+1d  → 条件触发（若用户仍未完成目标行为）
  T+3d  → 条件触发（最后唤醒机会）

内置三条核心旅程：
  member_activation      — 入会激活（T+0 / T+1d / T+3d）
  first_order_conversion — 首单转化（T+6h / T+1d）
  dormant_wakeup         — 沉睡唤醒（T+0 / T+2d）

纯函数（无副作用）：
  evaluate_condition(condition, orders_since_journey) → bool
  format_journey_message(template_id, store_id, customer_id) → str

服务类（依赖 DB / Celery）：
  JourneyOrchestrator.get_definition(journey_id) → JourneyDefinition | None
  JourneyOrchestrator.trigger(customer_id, store_id, journey_id, db) → dict
  JourneyOrchestrator.execute_step(journey_db_id, step_index, db, ...) → dict
"""

from __future__ import annotations

import inspect
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


async def _maybe_await(value: Any) -> Any:
    """Support both real async DB results and AsyncMock coroutine returns."""
    if inspect.isawaitable(value):
        return await value
    return value


# ── 数据类 ────────────────────────────────────────────────────────────────────


@dataclass
class JourneyStep:
    """旅程中的单个步骤。"""

    step_id: str
    delay_minutes: int  # 0 = T+0，1440 = T+1d，4320 = T+3d
    channel: str  # "wxwork" / "miniapp" / "sms"
    template_id: str  # 消息模板 ID
    condition: Optional[Dict] = None  # {"event_not_exist": "order_pay"}
    action: Optional[Dict] = None  # {"issue_coupon": "new_member_coupon"}


@dataclass
class JourneyDefinition:
    """完整的旅程定义。"""

    journey_id: str
    name: str
    trigger_events: List[str]  # 触发该旅程的事件名称列表
    steps: List[JourneyStep]
    success_metrics: List[str]  # ["order_pay"]


# ── 内置旅程定义 ──────────────────────────────────────────────────────────────

BUILTIN_JOURNEYS: Dict[str, JourneyDefinition] = {
    "member_activation": JourneyDefinition(
        journey_id="member_activation",
        name="入会激活",
        trigger_events=["member_register", "add_wxwork_friend"],
        steps=[
            JourneyStep(
                step_id="welcome",
                delay_minutes=0,
                channel="wxwork",
                template_id="journey_welcome",
                action={"issue_coupon": "new_member_coupon"},
            ),
            JourneyStep(
                step_id="profile_prompt",
                delay_minutes=1440,  # T+1d
                channel="wxwork",
                template_id="journey_profile_prompt",
                condition={"event_not_exist": "order_pay"},
            ),
            JourneyStep(
                step_id="first_visit_offer",
                delay_minutes=4320,  # T+3d
                channel="wxwork",
                template_id="journey_first_visit_offer",
                condition={"event_not_exist": "order_pay"},
                action={"issue_coupon": "first_visit_coupon"},
            ),
        ],
        success_metrics=["order_pay"],
    ),
    "first_order_conversion": JourneyDefinition(
        journey_id="first_order_conversion",
        name="首单转化",
        trigger_events=["member_register"],
        steps=[
            JourneyStep(
                step_id="menu_recommend",
                delay_minutes=360,  # T+6h
                channel="wxwork",
                template_id="journey_menu_recommend",
                condition={"event_not_exist": "order_pay"},
            ),
            JourneyStep(
                step_id="first_order_coupon",
                delay_minutes=1440,  # T+1d
                channel="wxwork",
                template_id="journey_first_order_coupon",
                condition={"event_not_exist": "order_pay"},
                action={"issue_coupon": "first_order_coupon"},
            ),
        ],
        success_metrics=["order_pay"],
    ),
    "dormant_wakeup": JourneyDefinition(
        journey_id="dormant_wakeup",
        name="沉睡唤醒",
        trigger_events=["inactivity_45d"],
        steps=[
            JourneyStep(
                step_id="content_touch",
                delay_minutes=0,
                channel="wxwork",
                template_id="journey_seasonal_content",
            ),
            JourneyStep(
                step_id="comeback_coupon",
                delay_minutes=2880,  # T+2d
                channel="wxwork",
                template_id="journey_comeback_coupon",
                action={"issue_coupon": "comeback_coupon"},
            ),
        ],
        success_metrics=["order_pay"],
    ),
    "proactive_remind": JourneyDefinition(
        journey_id="proactive_remind",
        name="主动提醒（需求预测触发）",
        trigger_events=["demand_prediction"],
        steps=[
            JourneyStep(
                step_id="visit_reminder",
                delay_minutes=0,
                channel="wxwork",
                template_id="journey_proactive_remind",
            ),
        ],
        success_metrics=["order_pay"],
    ),
    "birthday_greeting": JourneyDefinition(
        journey_id="birthday_greeting",
        name="生日祝福",
        trigger_events=["birthday_upcoming"],
        steps=[
            JourneyStep(
                step_id="birthday_wish",
                delay_minutes=0,
                channel="wxwork",
                template_id="birthday_wish",
                action={"issue_coupon": "birthday_coupon"},
            ),
        ],
        success_metrics=["order_pay"],
    ),
    "anniversary_greeting": JourneyDefinition(
        journey_id="anniversary_greeting",
        name="入会周年纪念",
        trigger_events=["member_anniversary"],
        steps=[
            JourneyStep(
                step_id="anniversary_wish",
                delay_minutes=0,
                channel="wxwork",
                template_id="anniversary_wish",
                action={"issue_coupon": "anniversary_coupon"},
            ),
        ],
        success_metrics=["order_pay"],
    ),
}


# ── 纯函数 ────────────────────────────────────────────────────────────────────


def evaluate_condition(
    condition: Optional[Dict],
    orders_since_journey: int,
) -> bool:
    """
    评估步骤执行条件（纯函数，无副作用）。

    Args:
        condition:             条件字典，None 表示无条件执行
        orders_since_journey:  旅程开始后该客户的订单数

    Returns:
        True = 执行该步骤，False = 跳过

    >>> evaluate_condition(None, 0)
    True
    >>> evaluate_condition({"event_not_exist": "order_pay"}, 0)
    True
    >>> evaluate_condition({"event_not_exist": "order_pay"}, 1)
    False
    """
    if condition is None:
        return True

    event = condition.get("event_not_exist")
    if event == "order_pay":
        return orders_since_journey == 0

    # 未知条件类型：默认执行（宽松策略）
    return True


def format_journey_message(
    template_id: str,
    store_id: str,
    customer_id: str,
) -> str:
    """
    格式化旅程消息文本（纯函数）。

    各模板内容可由门店配置后台覆盖（未来扩展点）。
    """
    _TEMPLATES: Dict[str, str] = {
        "journey_welcome": "欢迎加入！您已获得新会员专属优惠券，下次到店出示即可使用 🎉",
        "journey_profile_prompt": "您好！完善个人信息（生日/口味偏好）后可享受专属推荐，点击填写",
        "journey_first_visit_offer": "专属首单优惠限时领取，到店下单立减 ¥30，有效期3天，欢迎光临",
        "journey_menu_recommend": "为您精选当季招牌菜，点击查看今日推荐 👨‍🍳",
        "journey_first_order_coupon": "首单专属折扣券已发放，7天内有效，欢迎携友到店体验",
        "journey_seasonal_content": "时隔许久，我们想念您了！近期新品上线，欢迎回来品鉴 🍜",
        "journey_comeback_coupon": "专属回归礼遇券已送达，凭此券到店享受85折优惠，期待再见",
        "journey_proactive_remind": "根据您的消费节奏，这两天可能会想吃点好的。今日有新鲜食材到店，欢迎来尝鲜",
        "birthday_wish": "生日快乐！感谢一路陪伴，您的专属生日礼包已准备好，到店出示即可兑换",
        "anniversary_wish": "感谢一年来的陪伴！您已是我们的老朋友，专属周年礼已送达，欢迎到店领取",
    }
    return _TEMPLATES.get(template_id, f"您有一条来自门店的消息，欢迎到店")


# ── 服务类 ────────────────────────────────────────────────────────────────────


class JourneyOrchestrator:
    """
    旅程编排引擎。

    职责：
      1. 触发旅程（创建 DB 记录 + 调度所有步骤的 Celery 延迟任务）
      2. 执行单步（条件检查 → 频控 → 发消息 → 更新 DB）

    依赖注入（测试友好）：
      execute_step() 接受可选的 wechat_service / freq_cap_engine 参数，
      不传时静默跳过发送，便于单元测试。
    """

    def get_definition(self, journey_id: str) -> Optional[JourneyDefinition]:
        """返回内置旅程定义（未来可扩展为 DB 查询）。"""
        return BUILTIN_JOURNEYS.get(journey_id)

    async def trigger(
        self,
        customer_id: str,
        store_id: str,
        journey_id: str,
        db: AsyncSession,
        *,
        wechat_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        触发旅程：
          1. 校验旅程定义
          2. 写入 private_domain_journeys 记录（status=running）
          3. 为每个步骤调度 Celery 延迟任务

        Returns:
            {
                "journey_db_id": str,
                "journey_id":    str,
                "steps_scheduled": int,
                "total_steps":   int,
            }
            or {"error": str} on failure.
        """
        definition = self.get_definition(journey_id)
        if definition is None:
            return {"error": f"未知旅程: {journey_id}"}

        journey_db_id = str(uuid.uuid4())
        now = datetime.utcnow()
        unique_journey_id = f"{journey_id}:{customer_id}:{now.strftime('%Y%m%d%H%M%S')}"

        # 计算第一步的预期执行时间（用于 catch-up dispatcher）
        first_step_delay = definition.steps[0].delay_minutes if definition.steps else 0
        next_action_at = now + timedelta(minutes=first_step_delay)

        await db.execute(
            text("""
                INSERT INTO private_domain_journeys
                    (id, journey_id, store_id, customer_id, journey_type,
                     status, current_step, total_steps,
                     started_at, next_action_at, step_history, created_at, updated_at)
                VALUES
                    (:id, :journey_id, :store_id, :customer_id, :journey_type,
                     'running', 0, :total_steps,
                     :started_at, :next_action_at, '[]'::json, NOW(), NOW())
                ON CONFLICT (journey_id) DO NOTHING
            """),
            {
                "id": journey_db_id,
                "journey_id": unique_journey_id,
                "store_id": store_id,
                "customer_id": customer_id,
                "journey_type": journey_id,
                "total_steps": len(definition.steps),
                "started_at": now,
                "next_action_at": next_action_at,
            },
        )
        await db.commit()

        # 调度各步骤 Celery 延迟任务（内部 import 避免循环依赖）
        steps_scheduled = 0
        try:
            from src.core.celery_tasks import execute_journey_step  # noqa: PLC0415

            for idx, step in enumerate(definition.steps):
                execute_journey_step.apply_async(
                    args=[journey_db_id, idx, wechat_user_id],
                    countdown=step.delay_minutes * 60,
                )
                steps_scheduled += 1
        except Exception as exc:
            logger.warning(
                "journey.schedule_failed",
                journey_db_id=journey_db_id,
                error=str(exc),
            )

        logger.info(
            "journey.triggered",
            journey_db_id=journey_db_id,
            journey_id=journey_id,
            customer_id=customer_id,
            store_id=store_id,
            steps_scheduled=steps_scheduled,
        )
        return {
            "journey_db_id": journey_db_id,
            "journey_id": journey_id,
            "steps_scheduled": steps_scheduled,
            "total_steps": len(definition.steps),
        }

    async def execute_step(
        self,
        journey_db_id: str,
        step_index: int,
        db: AsyncSession,
        *,
        wechat_user_id: Optional[str] = None,
        wechat_service=None,
        freq_cap_engine=None,
        narrator=None,
    ) -> Dict[str, Any]:
        """
        执行旅程的第 step_index 步。

        步骤：
          1. 加载旅程记录（private_domain_journeys）
          2. 检查旅程仍在进行（status=running）
          3. 获取旅程定义和当前步骤配置
          4. 查询条件：旅程开始后是否已有订单
          5. 频控检查
          6. 查询会员画像（用于个性化消息生成）
          7. 发送企微消息（通过 JourneyNarrator 生成个性化文本）
          8. 更新 step_history / current_step / status

        Returns:
            {
                "step_id":        str,
                "executed":       bool,
                "sent":           bool,      # 仅 executed=True 时有意义
                "skipped_reason": str,       # 仅 executed=False 时有意义
            }
        """
        # 1. 加载记录
        row = await db.execute(
            text("""
                SELECT id, journey_type, customer_id, store_id,
                       status, started_at, step_history
                FROM private_domain_journeys
                WHERE id = :id
            """),
            {"id": journey_db_id},
        )
        journey = await _maybe_await(row.fetchone())
        if not journey:
            return {"error": "旅程记录不存在", "journey_db_id": journey_db_id}

        # 2. 已结束的旅程不再执行
        if journey.status not in ("running", "pending"):
            return {
                "skipped": True,
                "reason": f"旅程已结束 (status={journey.status})",
            }

        # 3. 获取步骤定义
        definition = self.get_definition(journey.journey_type)
        if not definition or step_index >= len(definition.steps):
            return {"error": "步骤索引越界", "step_index": step_index}

        step = definition.steps[step_index]

        # 4. 条件检查（旅程开始后的新订单数）
        orders_since = await self._count_orders_since(journey.customer_id, journey.store_id, journey.started_at, db)
        should_execute = evaluate_condition(step.condition, orders_since)

        if not should_execute:
            step_result: Dict[str, Any] = {
                "step_id": step.step_id,
                "executed": False,
                "skipped_reason": "条件不满足（用户已完成目标行为）",
            }
        else:
            # 5. 频控检查
            can_send = True
            if freq_cap_engine:
                can_send = await freq_cap_engine.can_send(journey.customer_id, journey.store_id, step.channel)

            if not can_send:
                step_result = {
                    "step_id": step.step_id,
                    "executed": False,
                    "skipped_reason": "频控限制",
                }
            else:
                # 6. 查询会员画像（供 JourneyNarrator 个性化生成）
                member_profile = await self._get_member_profile(journey.customer_id, journey.store_id, db)
                # 7. 发送消息
                msg_result = await self._send_message(
                    step,
                    journey.customer_id,
                    journey.store_id,
                    wechat_user_id,
                    wechat_service,
                    profile=member_profile,
                    narrator=narrator,
                )
                if freq_cap_engine and msg_result.get("sent"):
                    await freq_cap_engine.record_send(journey.customer_id, journey.store_id, step.channel)
                step_result = {
                    "step_id": step.step_id,
                    "executed": True,
                    "sent": msg_result.get("sent", False),
                    "channel": step.channel,
                    "action": step.action,
                }

        # 8. 更新 DB
        existing_history: List = list(journey.step_history or [])
        existing_history.append(
            {
                "step_index": step_index,
                "executed_at": datetime.utcnow().isoformat(),
                **step_result,
            }
        )
        is_last = step_index >= len(definition.steps) - 1
        new_status = "completed" if is_last else "running"

        # 计算下一步的预期执行时间（用于 catch-up dispatcher）
        next_action_at = None
        if not is_last:
            next_step = definition.steps[step_index + 1]
            next_action_at = datetime.utcnow() + timedelta(minutes=next_step.delay_minutes)

        await db.execute(
            text("""
                UPDATE private_domain_journeys
                SET current_step   = :step,
                    step_history   = :history::json,
                    status         = :status,
                    next_action_at = :next_action_at,
                    completed_at   = :completed_at,
                    updated_at     = NOW()
                WHERE id = :id
            """),
            {
                "step": step_index + 1,
                "history": json.dumps(existing_history),
                "status": new_status,
                "next_action_at": next_action_at,
                "completed_at": datetime.utcnow() if is_last else None,
                "id": journey_db_id,
            },
        )
        await db.commit()

        logger.info(
            "journey.step_executed",
            journey_db_id=journey_db_id,
            step_index=step_index,
            step_id=step.step_id,
            executed=step_result.get("executed"),
        )
        return step_result

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _count_orders_since(
        self,
        customer_id: str,
        store_id: str,
        since: datetime,
        db: AsyncSession,
    ) -> int:
        """返回旅程开始后该客户的订单数（用于条件评估）。"""
        try:
            row = await db.execute(
                text("""
                    SELECT COUNT(*) AS cnt
                    FROM orders
                    WHERE store_id = :store_id
                      AND (customer_id = :cid OR customer_phone = :cid)
                      AND created_at >= :since
                """),
                {"store_id": store_id, "cid": customer_id, "since": since},
            )
            result = await _maybe_await(row.fetchone())
            return int(result.cnt) if result else 0
        except Exception as exc:
            logger.warning("journey.count_orders_failed", error=str(exc))
            return 0

    async def _send_message(
        self,
        step: JourneyStep,
        customer_id: str,
        store_id: str,
        wechat_user_id: Optional[str],
        wechat_service,
        *,
        profile=None,
        narrator=None,
    ) -> Dict[str, Any]:
        """通过企微发送旅程消息。无服务/无 user_id 时静默跳过。

        Args:
            profile:  MemberProfile（由 _get_member_profile 获取）
            narrator: JourneyNarrator 实例（None 时降级为静态模板）
        """
        if not wechat_service or not wechat_user_id:
            logger.debug(
                "journey.send_skipped_no_wechat",
                customer_id=customer_id,
                template_id=step.template_id,
            )
            return {"sent": False, "reason": "无企微服务或接收者ID"}

        # 优先使用 JourneyNarrator 生成个性化文本，降级为静态模板
        if narrator is not None:
            content = await narrator.generate(
                template_id=step.template_id,
                store_id=store_id,
                customer_id=customer_id,
                profile=profile,
            )
        else:
            content = format_journey_message(step.template_id, store_id, customer_id)

        try:
            await wechat_service.send_text_message(content=content, touser=wechat_user_id)
            return {"sent": True}
        except Exception as exc:
            logger.warning(
                "journey.send_failed",
                customer_id=customer_id,
                template_id=step.template_id,
                error=str(exc),
            )
            return {"sent": False, "error": str(exc)}

    async def _get_member_profile(
        self,
        customer_id: str,
        store_id: str,
        db: AsyncSession,
    ):
        """
        查询会员基础画像（用于 JourneyNarrator 个性化生成）。

        策略：先读 Redis 缓存（MemberContextStore），miss 再查 DB，
        命中 DB 后写透到缓存，下次直接命中 Redis。

        查询失败或无记录时返回 None，上层降级为静态模板。
        """
        from src.services.journey_narrator import MemberProfile

        # 1. 尝试 Redis 缓存
        try:
            from src.services.member_context_store import get_context_store

            ctx_store = await get_context_store()
            if ctx_store:
                cached = await ctx_store.get(store_id, customer_id)
                if cached:
                    return MemberProfile(
                        frequency=cached.get("frequency", 0),
                        monetary=cached.get("monetary", 0),
                        recency_days=cached.get("recency_days"),
                        lifecycle_state=cached.get("lifecycle_state"),
                    )
        except Exception:
            pass  # Redis 不可用，继续走 DB

        # 2. 查 DB
        try:
            execute_result = await db.execute(
                text("""
                    SELECT frequency, monetary, recency_days, lifecycle_state
                    FROM private_domain_members
                    WHERE customer_id = :cid AND store_id = :sid
                    LIMIT 1
                """),
                {"cid": customer_id, "sid": store_id},
            )
            row = await _maybe_await(execute_result.fetchone())
            if not row:
                return None

            profile = MemberProfile(
                frequency=row[0] or 0,
                monetary=row[1] or 0,
                recency_days=row[2],
                lifecycle_state=row[3],
            )

            # 3. 写透到 Redis（异步，失败不影响主流程）
            try:
                from src.services.journey_narrator import classify_maslow_level
                from src.services.member_context_store import get_context_store

                ctx_store = await get_context_store()
                if ctx_store:
                    await ctx_store.set(
                        store_id,
                        customer_id,
                        {
                            "frequency": profile.frequency,
                            "monetary": profile.monetary,
                            "recency_days": profile.recency_days,
                            "lifecycle_state": profile.lifecycle_state,
                            "maslow_level": classify_maslow_level(profile),
                        },
                    )
            except Exception as exc:
                logger.debug("journey.ctx_cache_write_failed", store_id=store_id, customer_id=customer_id, error=str(exc))

            return profile
        except Exception as exc:
            logger.debug(
                "journey.get_member_profile_failed",
                customer_id=customer_id,
                error=str(exc),
            )
        return None
