"""
NarrativeEngine — 经营故事叙述器（架构升级 v2.1）

将结构化经营数据转换为老板30秒可读的自然语言简报。

固定格式（3段）：
  今日概况（1句话）
  异常预警（TOP3，按严重度排序）
  明日建议（1个行动）

约束：
  - 总字数 ≤ 200字（硬截断保证）
  - 纯信息不推送；无异常时输出正常确认
  - 与 DecisionPushService.push_evening_recap() 集成，
    替代原有简单数据列表，升级为"经营故事"叙述

Rule 6 兼容：所有金额使用 _yuan 字段（元，含¥符号）
Rule 8 兼容：仅聚合 MVP 范围内数据（成本率/损耗/决策采纳）
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

BRIEF_MAX_CHARS = 200  # 简报字数硬上限


# ════════════════════════════════════════════════════════════════════════════════
# 纯函数（无 DB 依赖，便于单元测试）
# ════════════════════════════════════════════════════════════════════════════════


def _build_overview(
    store_label: str,
    cost_metrics: Dict[str, Any],
    decision_summary: Dict[str, Any],
) -> str:
    """
    生成今日概况一句话（≈40字以内）。

    示例：芙蓉区店今日营收¥12,400，成本率31.2%（正常），决策采纳2/3
    """
    revenue = cost_metrics.get("revenue_yuan", 0.0)
    cost_pct = cost_metrics.get("actual_cost_pct", 0.0)
    status_label = cost_metrics.get("cost_rate_label", "正常")
    approved = decision_summary.get("approved", 0)
    total_dec = decision_summary.get("total", 0)

    overview = f"{store_label}今日营收¥{revenue:,.0f}，成本率{cost_pct:.1f}%（{status_label}）"
    if total_dec > 0:
        overview += f"，决策采纳{approved}/{total_dec}"
    return overview


def _detect_anomalies(
    cost_metrics: Dict[str, Any],
    waste_top5: Optional[List[Dict[str, Any]]],
    pending_count: int,
    top_decisions: List[Dict[str, Any]],
) -> List[str]:
    """
    检测异常事项，按严重度排序，返回最多3条简短描述。

    严重度：0=critical，1=warning，2=info
    """
    candidates: List[tuple[int, str]] = []  # (priority, text)

    # 1. 成本率异常（最高优先级）
    cost_status = cost_metrics.get("cost_rate_status", "ok")
    cost_pct = cost_metrics.get("actual_cost_pct", 0.0)
    if cost_status == "critical":
        candidates.append((0, f"🔴 食材成本严重超标：{cost_pct:.1f}%，需立即干预"))
    elif cost_status == "warning":
        candidates.append((1, f"⚠️ 食材成本偏高：{cost_pct:.1f}%，关注趋势"))

    # 2. 损耗TOP1（若有）
    if waste_top5:
        top = waste_top5[0]
        waste_yuan = top.get("waste_cost_yuan", 0.0)
        item_name = top.get("item_name", "")
        reason = top.get("action", "") or "建议核查"
        if waste_yuan > 0 and item_name:
            candidates.append(
                (
                    1 if cost_status == "critical" else 2,
                    f"⚠️ {item_name}损耗¥{waste_yuan:.0f}居首，{reason[:18]}",
                )
            )

    # 3. 待审批决策
    if pending_count > 0:
        total_saving = _sum_saving(top_decisions)
        saving_text = f"¥{total_saving:.0f}" if total_saving > 0 else "待统计"
        candidates.append((2, f"⏳ {pending_count}条决策待审批，预期节省{saving_text}"))

    candidates.sort(key=lambda x: x[0])
    return [text for _, text in candidates[:3]]


def _sum_saving(decisions: List[Dict[str, Any]]) -> float:
    """汇总决策预期节省金额"""
    return sum(d.get("expected_saving_yuan", 0.0) or d.get("net_benefit_yuan", 0.0) for d in decisions)


def _build_action(
    top_decisions: List[Dict[str, Any]],
    cost_metrics: Dict[str, Any],
) -> str:
    """
    生成明日1个具体行动建议。

    优先级：有高优决策时取第1个决策的 action；
    否则基于成本率状态生成通用建议。
    """
    if top_decisions:
        action = top_decisions[0].get("action", "")
        if action:
            return f"✅ 明日建议：{action[:46]}"

    cost_status = cost_metrics.get("cost_rate_status", "ok")
    if cost_status == "critical":
        return "✅ 明日建议：重点核查超标食材，与厨师长核对BOM用量"
    if cost_status == "warning":
        return "✅ 明日建议：关注成本率变化，确认备料量是否合理"
    return "✅ 明日建议：维持当前节奏，关注明日天气和客流预测"


def compose_brief(
    store_label: str,
    cost_metrics: Dict[str, Any],
    decision_summary: Dict[str, Any],
    waste_top5: Optional[List[Dict[str, Any]]],
    pending_count: int,
    top_decisions: List[Dict[str, Any]],
) -> str:
    """
    合成 ≤200字 的经营简报（纯函数，无副作用）。

    格式：
        今日概况一句话
        [异常1]
        [异常2]
        [异常3]
        明日建议一句话

    Returns:
        str: 截断至 BRIEF_MAX_CHARS 的简报文字
    """
    overview = _build_overview(store_label, cost_metrics, decision_summary)
    anomalies = _detect_anomalies(cost_metrics, waste_top5, pending_count, top_decisions)
    action = _build_action(top_decisions, cost_metrics)

    parts = [overview] + anomalies + [action]
    brief = "\n".join(parts)

    if len(brief) > BRIEF_MAX_CHARS:
        brief = brief[: BRIEF_MAX_CHARS - 1] + "…"

    return brief


# ════════════════════════════════════════════════════════════════════════════════
# NarrativeEngine（含 DB 查询的完整入口）
# ════════════════════════════════════════════════════════════════════════════════


class NarrativeEngine:
    """
    经营故事叙述器主入口。

    从 DB 拉取当日经营快照 + 损耗数据，生成 ≤200字 简报，
    供 DecisionPushService.push_evening_recap() 调用。

    设计原则：
    - 所有 DB 查询复用已有 Service，不重复 SQL
    - 任何子查询失败均静默降级，保证简报始终输出
    - top_decisions / pending_count 可由调用方传入，避免重复查询
    """

    @staticmethod
    async def generate_store_brief(
        store_id: str,
        target_date: date,
        db: Any,
        store_label: str = "",
        top_decisions: Optional[List[Dict[str, Any]]] = None,
        pending_count: int = 0,
    ) -> str:
        """
        生成指定门店当日经营简报（≤200字）。

        Args:
            store_id:      门店 ID
            target_date:   目标日期（通常为 date.today()）
            db:            AsyncSession
            store_label:   展示用门店名称，默认用 store_id
            top_decisions: 已从 DecisionPriorityEngine 获取的决策列表
                           （传入可避免重复查询）
            pending_count: 待审批决策数（传入可避免重复查询）

        Returns:
            str: ≤200字简报，失败时返回简短兜底文字
        """
        from src.services.case_story_generator import CaseStoryGenerator
        from src.services.waste_guard_service import WasteGuardService

        label = store_label or store_id

        # ── 当日经营快照（cost_metrics + decision_summary）────────────────────
        try:
            daily_story = await CaseStoryGenerator.generate_daily_story(
                store_id=store_id,
                target_date=target_date,
                db=db,
            )
            cost_metrics = daily_story["cost_metrics"]
            decision_summary = daily_story["decision_summary"]
        except Exception as exc:
            logger.warning(
                "narrative_engine.story_failed",
                store_id=store_id,
                error=str(exc),
            )
            cost_metrics = {
                "revenue_yuan": 0.0,
                "actual_cost_pct": 0.0,
                "cost_rate_status": "ok",
                "cost_rate_label": "正常",
            }
            decision_summary = {"total": 0, "approved": 0}

        # ── 损耗 TOP5 ─────────────────────────────────────────────────────────
        try:
            waste_report = await WasteGuardService.get_top5_waste(
                store_id=store_id,
                start_date=target_date,
                end_date=target_date + timedelta(days=1),
                db=db,
            )
            waste_top5 = waste_report.get("top5", [])
        except Exception as exc:
            logger.warning(
                "narrative_engine.waste_failed",
                store_id=store_id,
                error=str(exc),
            )
            waste_top5 = []

        return compose_brief(
            store_label=label,
            cost_metrics=cost_metrics,
            decision_summary=decision_summary,
            waste_top5=waste_top5,
            pending_count=pending_count,
            top_decisions=top_decisions or [],
        )
