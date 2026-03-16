"""
DecisionPushService — 决策型企微推送服务（v2.0 P0）

四个时间点推送：
  08:00 晨推  — 今日 Top3 决策，含¥影响+置信度+一键操作
  12:00 午推  — 上午异常汇总（损耗/成本率超标）
  17:30 战前  — 晚高峰备战核查（库存/排班/销售预期）
  20:30 晚推  — 当日执行回顾+待批准决策提醒

消息格式：textcard（标题 + 描述 + 一键操作按钮）
  - 描述行：¥预期影响 | 置信度 | 执行难度
  - 按钮文字：立即审批 / 查看详情

核心规则（CLAUDE.md Rule 7）：
  每条推送 = 建议动作 + 预期¥影响 + 置信度 + 一键操作入口
  纯信息不推送
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.decision_flow_state import DecisionFlowState
from src.services.decision_priority_engine import DecisionPriorityEngine
from src.services.waste_guard_service import WasteGuardService

try:
    from src.services.wechat_service import wechat_service
except Exception:
    wechat_service = None

logger = structlog.get_logger()

# 企微 textcard 描述字段最大 512 字符
_DESC_MAX = 512
# 一键操作按钮跳转基础URL（可通过环境变量覆盖）
_APPROVAL_BASE_URL = os.getenv(
    "WECHAT_APPROVAL_BASE_URL",
    "https://your-domain.com/decisions",
)


def _get_wechat_service():
    global wechat_service
    if wechat_service is None:
        from src.services.wechat_service import wechat_service as _wechat_service

        wechat_service = _wechat_service
    return wechat_service


# ── 卡片描述格式化 ─────────────────────────────────────────────────────────────


def _format_card_description(decisions: List[Dict[str, Any]]) -> str:
    """
    将 Top3 决策格式化为 textcard description 文本（最大 512 字符）。

    每条决策格式：
      序号. 【标题】
      行动：...
      ¥节省：xxx | 置信度：xx% | 难度：easy
    """
    lines = []
    for d in decisions[:3]:
        saving = d.get("expected_saving_yuan", 0.0)
        conf = d.get("confidence_pct", 0.0)
        diff = d.get("execution_difficulty", "medium")
        rank = d.get("rank", 1)
        title = d.get("title", "未知决策")
        action = d.get("action", "")
        trust = d.get("trust_score", 0.0)

        trust_label = f" | 信任分{trust:.0f}" if trust > 0 else ""
        lines.append(
            f"{rank}. 【{title}】\n" f"   {action}\n" f"   💰¥{saving:.0f} | 置信度{conf:.0f}%{trust_label} | 难度:{diff}"
        )

    desc = "\n\n".join(lines) if lines else "今日无高优先级决策"
    return desc[:_DESC_MAX]


def _format_anomaly_description(
    waste_report: Optional[Dict[str, Any]],
    decisions: List[Dict[str, Any]],
) -> str:
    """12:00午推：损耗+成本率异常描述"""
    lines = []

    if waste_report:
        rate = waste_report.get("waste_rate_pct", 0.0)
        status = waste_report.get("waste_rate_status", "ok")
        total = waste_report.get("total_waste_yuan", 0.0)
        if status != "ok":
            emoji = "🔴" if status == "critical" else "⚠️"
            lines.append(f"{emoji} 损耗率 {rate:.1f}%（¥{total:.0f}），状态：{status}")
        top5 = waste_report.get("top5", [])
        if top5:
            top_item = top5[0]
            lines.append(
                f"   损耗第1：{top_item.get('item_name', '')} ¥{top_item.get('waste_cost_yuan', 0):.0f}"
                f"，归因：{top_item.get('action', '')}"
            )

    if not lines and not decisions:
        return "今日上午无重大异常"

    for d in decisions[:2]:
        saving = d.get("expected_saving_yuan", 0.0)
        conf = d.get("confidence_pct", 0.0)
        lines.append(f"• {d.get('title', '')}（¥{saving:.0f}，置信度{conf:.0f}%）")

    desc = "\n".join(lines)
    return desc[:_DESC_MAX]


def _format_prebattle_description(
    decisions: List[Dict[str, Any]],
    store_name: str,
) -> str:
    """17:30战前推：聚焦库存+排班类决策"""
    inventory_decs = [d for d in decisions if d.get("source") == "inventory"]
    other_decs = [d for d in decisions if d.get("source") != "inventory"]

    lines = [f"【{store_name}】晚高峰备战核查"]
    if inventory_decs:
        lines.append("📦 库存决策：")
        for d in inventory_decs[:2]:
            lines.append(f"  • {d.get('title', '')} — {d.get('action', '')[:40]}")
    if other_decs:
        lines.append("📊 其他建议：")
        for d in other_decs[:1]:
            saving = d.get("expected_saving_yuan", 0.0)
            lines.append(f"  • {d.get('title', '')}（¥{saving:.0f}）")
    if not inventory_decs and not other_decs:
        lines.append("✅ 库存与经营指标均正常")

    return "\n".join(lines)[:_DESC_MAX]


def _format_evening_description(
    decisions: List[Dict[str, Any]],
    pending_count: int,
) -> str:
    """20:30晚推：当日回顾+待审批提醒"""
    lines = []
    total_saving = sum(d.get("expected_saving_yuan", 0.0) for d in decisions)

    if pending_count > 0:
        lines.append(f"⏳ 还有 {pending_count} 条决策待审批，建议睡前处理")
    if total_saving > 0:
        lines.append(f"💰 今日决策预期节省合计：¥{total_saving:.0f}")

    for d in decisions[:3]:
        conf = d.get("confidence_pct", 0.0)
        lines.append(f"• {d.get('title', '')} — 置信度{conf:.0f}%")

    if not lines:
        lines.append("✅ 今日经营正常，无待处理决策")

    return "\n".join(lines)[:_DESC_MAX]


# ── DecisionPushService ────────────────────────────────────────────────────────


class DecisionPushService:
    """
    决策型企微推送服务。

    用法::

        from src.services.decision_push_service import DecisionPushService
        result = await DecisionPushService.push_morning_decisions(
            store_id="S001", brand_id="B001",
            recipient_user_id="boss_wechat_id", db=session,
        )
    """

    @staticmethod
    async def push_morning_decisions(
        store_id: str,
        brand_id: str,
        recipient_user_id: str,
        db: AsyncSession,
        store_name: str = "",
        monthly_revenue_yuan: float = 0.0,
    ) -> Dict[str, Any]:
        """
        08:00晨推：今日 Top3 决策卡片。

        Returns:
            {"sent": bool, "decision_count": int, "message_id": str | None, "flow_id": str}
        """
        state = DecisionFlowState.new(store_id=store_id, push_window="08:00晨推")
        wechat = _get_wechat_service()

        engine = DecisionPriorityEngine(store_id=store_id)
        try:
            decisions = await engine.get_top3(
                db=db,
                monthly_revenue_yuan=monthly_revenue_yuan,
            )
        except Exception as exc:
            logger.warning("decision_push.morning.engine_failed", store_id=store_id, error=str(exc))
            decisions = []

        if not decisions:
            logger.info("decision_push.morning.no_decisions", store_id=store_id)
            return {"sent": False, "decision_count": 0, "message_id": None, "flow_id": state.flow_id}

        state.set_decisions_from_engine(decisions)

        title = f"【晨推·Top{len(decisions)}决策】{store_name or store_id}"
        description = _format_card_description(decisions)
        action_url = f"{_APPROVAL_BASE_URL}?store_id={store_id}&window=morning"

        result = await wechat.send_decision_card(
            title=title,
            description=description,
            action_url=action_url,
            btntxt="立即审批",
            to_user_id=recipient_user_id,
        )

        state.push_sent = result.get("status") == "sent"
        state.push_message_id = result.get("message_id")
        if not state.push_sent:
            state.push_error = result.get("error") or result.get("status")
        state.mark_completed()
        await state.save_to_redis()

        logger.info(
            "decision_push.morning.sent",
            store_id=store_id,
            decision_count=len(decisions),
            status=result.get("status"),
            flow_id=state.flow_id,
        )
        return {
            "sent": state.push_sent,
            "decision_count": len(decisions),
            "message_id": state.push_message_id,
            "flow_id": state.flow_id,
        }

    @staticmethod
    async def push_noon_anomaly(
        store_id: str,
        brand_id: str,
        recipient_user_id: str,
        db: AsyncSession,
        store_name: str = "",
    ) -> Dict[str, Any]:
        """
        12:00午推：上午损耗/异常汇总卡片。

        仅当存在 warning/critical 异常时推送（纯信息不推）。
        """
        state = DecisionFlowState.new(store_id=store_id, push_window="12:00午推")
        wechat = _get_wechat_service()

        today = date.today()
        start = today.replace(day=1)  # 本月1日

        # 获取损耗摘要
        try:
            waste_summary = await WasteGuardService.get_waste_rate_summary(
                store_id=store_id,
                start_date=start,
                end_date=today,
                db=db,
            )
        except Exception as exc:
            logger.warning("decision_push.noon.waste_failed", store_id=store_id, error=str(exc))
            waste_summary = None

        # 获取 Top3 决策（午推重点：food_cost/reasoning 类）
        engine = DecisionPriorityEngine(store_id=store_id)
        try:
            decisions = await engine.get_top3(db=db)
        except Exception as exc:
            logger.warning("decision_push.noon.engine_failed", store_id=store_id, error=str(exc))
            decisions = []

        # 仅在有实质性异常时推送
        has_anomaly = (waste_summary and waste_summary.get("waste_rate_status") in ("warning", "critical")) or any(
            d.get("source") in ("food_cost", "reasoning") for d in decisions
        )
        if not has_anomaly:
            logger.info("decision_push.noon.no_anomaly", store_id=store_id)
            return {"sent": False, "decision_count": 0, "message_id": None, "flow_id": state.flow_id}

        state.set_decisions_from_engine(decisions)

        title = f"【12:00异常推送】{store_name or store_id}"
        description = _format_anomaly_description(waste_summary, decisions)
        action_url = f"{_APPROVAL_BASE_URL}?store_id={store_id}&window=noon"

        result = await wechat.send_decision_card(
            title=title,
            description=description,
            action_url=action_url,
            btntxt="查看详情",
            to_user_id=recipient_user_id,
        )

        state.push_sent = result.get("status") == "sent"
        state.push_message_id = result.get("message_id")
        if not state.push_sent:
            state.push_error = result.get("error") or result.get("status")
        state.mark_completed()
        await state.save_to_redis()

        logger.info(
            "decision_push.noon.sent",
            store_id=store_id,
            status=result.get("status"),
            flow_id=state.flow_id,
        )
        return {
            "sent": state.push_sent,
            "decision_count": len(decisions),
            "message_id": state.push_message_id,
            "flow_id": state.flow_id,
        }

    @staticmethod
    async def push_prebattle_decisions(
        store_id: str,
        brand_id: str,
        recipient_user_id: str,
        db: AsyncSession,
        store_name: str = "",
        monthly_revenue_yuan: float = 0.0,
    ) -> Dict[str, Any]:
        """
        17:30战前推：聚焦库存+排班的备战核查卡片。

        仅当存在库存类决策时推送。
        """
        state = DecisionFlowState.new(store_id=store_id, push_window="17:30战前")
        wechat = _get_wechat_service()

        engine = DecisionPriorityEngine(store_id=store_id)
        try:
            decisions = await engine.get_top3(
                db=db,
                monthly_revenue_yuan=monthly_revenue_yuan,
            )
        except Exception as exc:
            logger.warning("decision_push.prebattle.engine_failed", store_id=store_id, error=str(exc))
            decisions = []

        # 战前推：仅在有库存或紧急决策时推送
        actionable = [d for d in decisions if d.get("source") == "inventory" or d.get("urgency_hours", 99) < 4]
        if not actionable:
            logger.info("decision_push.prebattle.no_actionable", store_id=store_id)
            return {"sent": False, "decision_count": 0, "message_id": None, "flow_id": state.flow_id}

        state.set_decisions_from_engine(decisions)

        title = f"【17:30战前核查】{store_name or store_id}"
        description = _format_prebattle_description(decisions, store_name or store_id)
        action_url = f"{_APPROVAL_BASE_URL}?store_id={store_id}&window=prebattle"

        result = await wechat.send_decision_card(
            title=title,
            description=description,
            action_url=action_url,
            btntxt="一键审批",
            to_user_id=recipient_user_id,
        )

        state.push_sent = result.get("status") == "sent"
        state.push_message_id = result.get("message_id")
        if not state.push_sent:
            state.push_error = result.get("error") or result.get("status")
        state.mark_completed()
        await state.save_to_redis()

        logger.info(
            "decision_push.prebattle.sent",
            store_id=store_id,
            actionable_count=len(actionable),
            flow_id=state.flow_id,
        )
        return {
            "sent": state.push_sent,
            "decision_count": len(decisions),
            "message_id": state.push_message_id,
            "flow_id": state.flow_id,
        }

    @staticmethod
    async def push_evening_recap(
        store_id: str,
        brand_id: str,
        recipient_user_id: str,
        db: AsyncSession,
        store_name: str = "",
        monthly_revenue_yuan: float = 0.0,
    ) -> Dict[str, Any]:
        """
        20:30晚推：当日经营故事简报 + 待批决策提醒。

        描述文本由 NarrativeEngine 生成（≤200字，固定格式）：
          今日概况（1句话）+ 异常预警（TOP3）+ 明日建议（1个行动）

        仅在有待批或高优先级决策时推送（纯信息不推）。
        """
        from src.services.narrative_engine import NarrativeEngine

        state = DecisionFlowState.new(store_id=store_id, push_window="20:30晚推")
        wechat = _get_wechat_service()

        # 查询该门店待审批决策数
        pending_count = await _count_pending_approvals(store_id, db)
        state.pending_count = pending_count

        engine = DecisionPriorityEngine(store_id=store_id)
        try:
            decisions = await engine.get_top3(
                db=db,
                monthly_revenue_yuan=monthly_revenue_yuan,
            )
        except Exception as exc:
            logger.warning("decision_push.evening.engine_failed", store_id=store_id, error=str(exc))
            decisions = []

        if pending_count == 0 and not decisions:
            logger.info("decision_push.evening.nothing_to_push", store_id=store_id)
            return {"sent": False, "decision_count": 0, "message_id": None, "flow_id": state.flow_id}

        state.set_decisions_from_engine(decisions)

        title = f"【20:30晚推·经营简报】{store_name or store_id}"

        # NarrativeEngine 生成故事简报；失败时降级为原有格式
        try:
            description = await NarrativeEngine.generate_store_brief(
                store_id=store_id,
                target_date=date.today(),
                db=db,
                store_label=store_name or store_id,
                top_decisions=decisions,
                pending_count=pending_count,
            )
        except Exception as exc:
            logger.warning("decision_push.evening.narrative_failed", store_id=store_id, error=str(exc))
            description = _format_evening_description(decisions, pending_count)

        state.narrative = description
        action_url = f"{_APPROVAL_BASE_URL}?store_id={store_id}&window=evening"

        result = await wechat.send_decision_card(
            title=title,
            description=description,
            action_url=action_url,
            btntxt="立即审批" if pending_count > 0 else "查看详情",
            to_user_id=recipient_user_id,
        )

        state.push_sent = result.get("status") == "sent"
        state.push_message_id = result.get("message_id")
        if not state.push_sent:
            state.push_error = result.get("error") or result.get("status")
        state.mark_completed()
        await state.save_to_redis()

        logger.info(
            "decision_push.evening.sent",
            store_id=store_id,
            pending_count=pending_count,
            decision_count=len(decisions),
            flow_id=state.flow_id,
        )
        return {
            "sent": state.push_sent,
            "pending_approvals": pending_count,
            "decision_count": len(decisions),
            "message_id": state.push_message_id,
            "flow_id": state.flow_id,
        }


# ── 辅助函数 ───────────────────────────────────────────────────────────────────


async def _count_pending_approvals(store_id: str, db: AsyncSession) -> int:
    """查询指定门店的待审批决策数量。"""
    try:
        from sqlalchemy import select
        from src.models.decision_log import DecisionLog, DecisionStatus

        result = await db.execute(
            select(func.count(DecisionLog.id)).where(
                and_(
                    DecisionLog.store_id == store_id,
                    DecisionLog.decision_status == DecisionStatus.PENDING,
                )
            )
        )
        return result.scalar() or 0
    except Exception as exc:
        logger.warning("decision_push.count_pending_failed", store_id=store_id, error=str(exc))
        return 0
