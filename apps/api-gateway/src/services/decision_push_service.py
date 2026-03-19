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
from sqlalchemy import and_, func, select, text
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


# ── 三源数据融合：跨系统洞察 ──────────────────────────────────────────────────


async def _fetch_cross_system_insights(
    store_id: str,
    brand_id: str,
    db: AsyncSession,
    date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    聚合品智POS / 微生活会员 / 奥琦玮供应链三源数据，返回跨系统洞察。

    每个子查询独立 try/except，单源失败不影响其他源。
    金额：DB 存分 → 展示元（÷100）。
    """
    today = date or datetime.now().strftime("%Y-%m-%d")
    result: Dict[str, Any] = {
        "pos": None,
        "member": None,
        "supply": None,
        "cross_system": None,
    }

    # ── 1. POS 数据（品智）──────────────────────────────────────────────────
    try:
        pos_row = await db.execute(
            text("""
                SELECT
                    COALESCE(SUM(final_amount), 0)   AS total_revenue_fen,
                    COUNT(*)                          AS order_count,
                    CASE WHEN COUNT(*) > 0
                         THEN COALESCE(SUM(final_amount), 0) / COUNT(*)
                         ELSE 0 END                   AS avg_ticket_fen
                FROM orders
                WHERE store_id = :store_id
                  AND DATE(created_at) = :today
            """),
            {"store_id": store_id, "today": today},
        )
        pos_data = pos_row.mappings().first()

        # Top3 菜品
        top_dishes_rows = await db.execute(
            text("""
                SELECT oi.dish_name, SUM(oi.quantity) AS total_qty
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                WHERE o.store_id = :store_id
                  AND DATE(o.created_at) = :today
                GROUP BY oi.dish_name
                ORDER BY total_qty DESC
                LIMIT 3
            """),
            {"store_id": store_id, "today": today},
        )
        top_dishes = [r.dish_name for r in top_dishes_rows.all() if r.dish_name]

        result["pos"] = {
            "today_revenue_yuan": (pos_data["total_revenue_fen"] or 0) / 100.0 if pos_data else 0.0,
            "order_count": pos_data["order_count"] if pos_data else 0,
            "avg_ticket_yuan": (pos_data["avg_ticket_fen"] or 0) / 100.0 if pos_data else 0.0,
            "top_dishes": top_dishes,
        }
    except Exception as exc:
        logger.warning("cross_system_insights.pos_failed", store_id=store_id, error=str(exc))
        result["pos"] = {
            "today_revenue_yuan": 0.0,
            "order_count": 0,
            "avg_ticket_yuan": 0.0,
            "top_dishes": [],
        }

    # ── 2. 会员数据（微生活）─────────────────────────────────────────────────
    try:
        member_row = await db.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (
                        WHERE last_visit_at >= NOW() - INTERVAL '30 days'
                    ) AS active_30d,
                    COUNT(*) FILTER (
                        WHERE created_at >= NOW() - INTERVAL '7 days'
                    ) AS new_7d,
                    COUNT(*) FILTER (
                        WHERE last_visit_at < NOW() - INTERVAL '60 days'
                          AND total_spend_fen > 50000
                    ) AS churning,
                    CASE WHEN COUNT(*) > 0
                         THEN COALESCE(SUM(stored_value_fen), 0) / COUNT(*)
                         ELSE 0 END AS avg_stored_fen
                FROM private_domain_members
                WHERE store_id = :store_id
            """),
            {"store_id": store_id},
        )
        m = member_row.mappings().first()
        result["member"] = {
            "active_members_30d": m["active_30d"] if m else 0,
            "new_members_7d": m["new_7d"] if m else 0,
            "churning_members": m["churning"] if m else 0,
            "avg_stored_value_yuan": (m["avg_stored_fen"] or 0) / 100.0 if m else 0.0,
        }
    except Exception as exc:
        logger.warning("cross_system_insights.member_failed", store_id=store_id, error=str(exc))
        result["member"] = {
            "active_members_30d": 0,
            "new_members_7d": 0,
            "churning_members": 0,
            "avg_stored_value_yuan": 0.0,
        }

    # ── 3. 供应链数据（奥琦玮）────────────────────────────────────────────────
    try:
        supply_row = await db.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (
                        WHERE current_stock < safety_stock AND current_stock IS NOT NULL
                    ) AS low_stock_items,
                    0 AS pending_orders
                FROM inventory_items
                WHERE store_id = :store_id
            """),
            {"store_id": store_id},
        )
        s = supply_row.mappings().first()
        low_stock = s["low_stock_items"] if s else 0

        # 待收货采购单
        try:
            po_row = await db.execute(
                text("""
                    SELECT COUNT(*) AS cnt
                    FROM purchase_orders
                    WHERE store_id = :store_id
                      AND status IN ('pending', 'ordered')
                """),
                {"store_id": store_id},
            )
            po = po_row.mappings().first()
            pending_orders = po["cnt"] if po else 0
        except Exception:
            pending_orders = 0

        # 昨日损耗
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        try:
            waste_row = await db.execute(
                text("""
                    SELECT COALESCE(SUM(waste_cost_fen), 0) AS total_waste_fen
                    FROM waste_events
                    WHERE store_id = :store_id
                      AND DATE(created_at) = :yesterday
                """),
                {"store_id": store_id, "yesterday": yesterday},
            )
            w = waste_row.mappings().first()
            waste_yuan = (w["total_waste_fen"] or 0) / 100.0 if w else 0.0
        except Exception:
            waste_yuan = 0.0

        # 食材成本率（本月累计食材成本 / 本月累计营收）
        try:
            cost_row = await db.execute(
                text("""
                    SELECT
                        COALESCE(SUM(ingredient_cost_fen), 0) AS cost_fen,
                        COALESCE(SUM(revenue_fen), 0)         AS rev_fen
                    FROM daily_summaries
                    WHERE store_id = :store_id
                      AND summary_date >= DATE_TRUNC('month', CURRENT_DATE)
                """),
                {"store_id": store_id},
            )
            c = cost_row.mappings().first()
            cost_fen = c["cost_fen"] if c else 0
            rev_fen = c["rev_fen"] if c else 0
            cost_ratio = round((cost_fen / rev_fen * 100), 1) if rev_fen > 0 else 0.0
        except Exception:
            cost_ratio = 0.0

        result["supply"] = {
            "low_stock_items": low_stock,
            "pending_orders": pending_orders,
            "yesterday_waste_yuan": waste_yuan,
            "cost_ratio": cost_ratio,
        }
    except Exception as exc:
        logger.warning("cross_system_insights.supply_failed", store_id=store_id, error=str(exc))
        result["supply"] = {
            "low_stock_items": 0,
            "pending_orders": 0,
            "yesterday_waste_yuan": 0.0,
            "cost_ratio": 0.0,
        }

    # ── 4. 跨系统关联洞察 ─────────────────────────────────────────────────────
    try:
        # 高价值会员7天未到店
        hv_row = await db.execute(
            text("""
                SELECT COUNT(*) AS cnt
                FROM private_domain_members
                WHERE store_id = :store_id
                  AND total_spend_fen > 100000
                  AND last_visit_at < NOW() - INTERVAL '7 days'
            """),
            {"store_id": store_id},
        )
        hv = hv_row.mappings().first()
        high_value_no_visit = hv["cnt"] if hv else 0

        # 热销菜品对应食材库存不足
        popular_low_stock: List[str] = []
        if result["pos"] and result["pos"]["top_dishes"]:
            for dish_name in result["pos"]["top_dishes"]:
                try:
                    ls_row = await db.execute(
                        text("""
                            SELECT ii.item_name
                            FROM bom_items bi
                            JOIN bom_templates bt ON bt.id = bi.bom_id
                            JOIN dishes d ON d.id = bt.dish_id
                            JOIN inventory_items ii ON ii.item_name = bi.ingredient_name
                                AND ii.store_id = :store_id
                            WHERE d.name = :dish_name
                              AND ii.current_stock < ii.safety_stock
                            LIMIT 1
                        """),
                        {"store_id": store_id, "dish_name": dish_name},
                    )
                    ls = ls_row.first()
                    if ls:
                        popular_low_stock.append(dish_name)
                except Exception:
                    pass

        # 会员消费与成本差异（会员人均消费 vs 人均食材成本）
        member_avg = result.get("pos", {}).get("avg_ticket_yuan", 0.0)
        cost_r = result.get("supply", {}).get("cost_ratio", 0.0)
        gap = round(member_avg * (1 - cost_r / 100), 2) if member_avg > 0 else 0.0

        result["cross_system"] = {
            "high_value_member_no_visit_7d": high_value_no_visit,
            "popular_dish_low_stock": popular_low_stock,
            "member_spend_vs_cost_gap": gap,
        }
    except Exception as exc:
        logger.warning("cross_system_insights.cross_failed", store_id=store_id, error=str(exc))
        result["cross_system"] = {
            "high_value_member_no_visit_7d": 0,
            "popular_dish_low_stock": [],
            "member_spend_vs_cost_gap": 0.0,
        }

    return result


def _format_cross_system_alert_description(
    insights: Dict[str, Any],
    alerts: List[Dict[str, str]],
    store_name: str,
) -> str:
    """跨系统异常告警卡片描述格式化。"""
    lines = [f"【{store_name}】跨系统异常检测"]

    for alert in alerts[:3]:
        emoji = alert.get("emoji", "🔔")
        title = alert.get("title", "")
        detail = alert.get("detail", "")
        conf = alert.get("confidence_pct", 0)
        lines.append(f"{emoji} {title}")
        lines.append(f"   {detail}")
        lines.append(f"   置信度{conf}%")

    # 附加数据摘要
    pos = insights.get("pos") or {}
    supply = insights.get("supply") or {}
    if pos.get("today_revenue_yuan"):
        lines.append(f"\n📊 今日营收：¥{pos['today_revenue_yuan']:.0f}，{pos.get('order_count', 0)}单")
    if supply.get("cost_ratio"):
        lines.append(f"📦 食材成本率：{supply['cost_ratio']:.1f}%")

    desc = "\n".join(lines)
    return desc[:_DESC_MAX]


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

        # ── 三源数据融合：补充跨系统决策 ──────────────────────────────────
        try:
            insights = await _fetch_cross_system_insights(
                store_id=store_id, brand_id=brand_id, db=db,
            )
            cross = insights.get("cross_system") or {}
            supply = insights.get("supply") or {}

            # 高价值会员7天未到店 → 回访计划
            if cross.get("high_value_member_no_visit_7d", 0) > 5:
                decisions.append({
                    "rank": len(decisions) + 1,
                    "title": "启动高价值会员回访计划",
                    "action": f"{cross['high_value_member_no_visit_7d']}位高价值会员7天未到店，建议短信/企微触达",
                    "expected_saving_yuan": cross["high_value_member_no_visit_7d"] * 80,
                    "confidence_pct": 72,
                    "execution_difficulty": "easy",
                    "source": "cross_system",
                })

            # 热销菜品食材库存不足 → 紧急补货
            popular_low = cross.get("popular_dish_low_stock", [])
            if popular_low:
                decisions.append({
                    "rank": len(decisions) + 1,
                    "title": "热销菜品食材预警，建议紧急补货",
                    "action": f"{'、'.join(popular_low[:3])}对应食材低于安全库存",
                    "expected_saving_yuan": len(popular_low) * 200,
                    "confidence_pct": 85,
                    "execution_difficulty": "medium",
                    "source": "cross_system",
                })

            # 食材成本率偏高 → 检查损耗
            if supply.get("cost_ratio", 0) > 38:
                decisions.append({
                    "rank": len(decisions) + 1,
                    "title": "食材成本率偏高，建议检查损耗",
                    "action": f"本月成本率{supply['cost_ratio']:.1f}%（阈值38%），昨日损耗¥{supply.get('yesterday_waste_yuan', 0):.0f}",
                    "expected_saving_yuan": supply.get("yesterday_waste_yuan", 0) * 5,
                    "confidence_pct": 78,
                    "execution_difficulty": "medium",
                    "source": "cross_system",
                })
        except Exception as exc:
            logger.warning("decision_push.morning.cross_system_failed", store_id=store_id, error=str(exc))

        state.set_decisions_from_engine(decisions)

        title = f"【晨推·Top{min(len(decisions), 3)}决策】{store_name or store_id}"
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


    @staticmethod
    async def push_cross_system_alert(
        store_id: str,
        brand_id: str,
        recipient_user_id: str,
        db: AsyncSession,
        store_name: str = "",
    ) -> Dict[str, Any]:
        """
        跨系统异常告警推送（每2小时，营业时段 10:00-22:00）。

        聚合 POS + 会员 + 供应链三源数据，检测跨系统异常：
          - 高价值会员流失 + 营收下降 → 紧急告警
          - 热销菜品食材库存不足 → 采购告警
          - 成本率飙升 + 损耗增加 → 止损告警

        仅在检测到异常时推送（纯信息不推 — Rule 7）。

        Returns:
            {"sent": bool, "alert_count": int, "message_id": str | None, "flow_id": str}
        """
        state = DecisionFlowState.new(store_id=store_id, push_window="跨系统告警")
        wechat = _get_wechat_service()

        try:
            insights = await _fetch_cross_system_insights(
                store_id=store_id, brand_id=brand_id, db=db,
            )
        except Exception as exc:
            logger.warning("decision_push.cross_alert.insights_failed", store_id=store_id, error=str(exc))
            return {"sent": False, "alert_count": 0, "message_id": None, "flow_id": state.flow_id}

        cross = insights.get("cross_system") or {}
        pos = insights.get("pos") or {}
        supply = insights.get("supply") or {}
        member = insights.get("member") or {}

        alerts: List[Dict[str, str]] = []

        # 告警1：高价值会员流失 + 营收下降
        hv_no_visit = cross.get("high_value_member_no_visit_7d", 0)
        churning = member.get("churning_members", 0)
        if hv_no_visit > 5 and churning > 3:
            estimated_loss = hv_no_visit * 150  # 预估流失金额
            alerts.append({
                "emoji": "🔴",
                "title": "高价值会员流失预警",
                "detail": (
                    f"{hv_no_visit}位高价值会员7天未到店，{churning}位沉睡风险。"
                    f"预估月损失¥{estimated_loss}"
                ),
                "confidence_pct": 75,
                "expected_saving_yuan": str(estimated_loss),
                "action_type": "member_recall",
            })

        # 告警2：热销菜品食材库存不足
        popular_low = cross.get("popular_dish_low_stock", [])
        if popular_low:
            alerts.append({
                "emoji": "📦",
                "title": "热销菜品食材紧急补货",
                "detail": (
                    f"{'、'.join(popular_low[:3])}对应食材低于安全库存，"
                    f"可能导致晚高峰缺菜。待收货采购单{supply.get('pending_orders', 0)}笔"
                ),
                "confidence_pct": 88,
                "expected_saving_yuan": str(len(popular_low) * 300),
                "action_type": "emergency_purchase",
            })

        # 告警3：成本率飙升 + 损耗增加
        cost_ratio = supply.get("cost_ratio", 0)
        waste_yuan = supply.get("yesterday_waste_yuan", 0)
        if cost_ratio > 38 and waste_yuan > 200:
            alerts.append({
                "emoji": "⚠️",
                "title": "成本率+损耗双高告警",
                "detail": (
                    f"本月成本率{cost_ratio:.1f}%（阈值38%），"
                    f"昨日损耗¥{waste_yuan:.0f}。建议立即盘点+检查出品流程"
                ),
                "confidence_pct": 82,
                "expected_saving_yuan": str(int(waste_yuan * 3)),
                "action_type": "loss_prevention",
            })

        if not alerts:
            logger.info("decision_push.cross_alert.no_anomaly", store_id=store_id)
            return {"sent": False, "alert_count": 0, "message_id": None, "flow_id": state.flow_id}

        title = f"【跨系统告警·{len(alerts)}项异常】{store_name or store_id}"
        description = _format_cross_system_alert_description(insights, alerts, store_name or store_id)
        action_url = f"{_APPROVAL_BASE_URL}?store_id={store_id}&window=cross_alert"

        result = await wechat.send_decision_card(
            title=title,
            description=description,
            action_url=action_url,
            btntxt="立即处理",
            to_user_id=recipient_user_id,
        )

        state.push_sent = result.get("status") == "sent"
        state.push_message_id = result.get("message_id")
        if not state.push_sent:
            state.push_error = result.get("error") or result.get("status")
        state.mark_completed()
        await state.save_to_redis()

        logger.info(
            "decision_push.cross_alert.sent",
            store_id=store_id,
            alert_count=len(alerts),
            alert_types=[a.get("action_type") for a in alerts],
            flow_id=state.flow_id,
        )
        return {
            "sent": state.push_sent,
            "alert_count": len(alerts),
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
