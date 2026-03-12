"""
案例故事生成器（Case Story Generator）

职责：
  自动聚合门店经营数据，生成可叙述的案例故事，用于：
    1. 月度经营报告 PDF 的叙事章节
    2. DecisionPriorityEngine 历史案例检索
    3. 续费演示材料（展示 ROI）

叙事维度：
  - 日维度：当日经营快照（营业额/成本率/损耗/决策执行）
  - 周维度：周环比分析（成本率趋势/决策采纳率/损耗变化）
  - 月维度：月度深度报告（Top3 成本改善案例 + 关键决策回顾）

数据来源（无需新表，复用现有）：
  - orders：营业额
  - inventory_transactions（type=usage）：实际食材成本
  - decision_log：决策执行情况（status/outcome）
  - bom_templates + bom_items + dishes：理论成本率

Rule 6 兼容：所有金额字段均附 _yuan 伴随字段（元，2位小数）
Rule 8 兼容：仅在10个MVP功能范围内收集数据
Rule 9 兼容：本模块即 Rule 9 的实现目标
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# ── 成本率状态阈值 ────────────────────────────────────────────────────────────
COST_RATE_OK       = float(os.getenv("COST_RATE_OK",       "0.30"))  # ≤30% 正常
COST_RATE_WARNING  = float(os.getenv("COST_RATE_WARNING",  "0.32"))  # 32–39.99% 警告
COST_RATE_CRITICAL = float(os.getenv("COST_RATE_CRITICAL", "0.40"))  # ≥40% 严重

# ── 状态文字映射 ──────────────────────────────────────────────────────────────
_STATUS_LABEL = {
    "ok":       "正常",
    "warning":  "偏高",
    "critical": "超标",
}


def _fen_to_yuan(fen: int | float) -> float:
    """分 → 元（保留2位小数）"""
    return round(float(fen) / 100, 2)


def _cost_rate_status(actual_pct: float) -> str:
    if actual_pct >= COST_RATE_CRITICAL * 100:
        return "critical"
    if actual_pct >= COST_RATE_WARNING * 100:
        return "warning"
    return "ok"


# ════════════════════════════════════════════════════════════════════════════════
# 内部查询函数（参数化 SQL，遵循 L010/L011 规则）
# ════════════════════════════════════════════════════════════════════════════════

async def _query_revenue(
    db: AsyncSession, store_id: str, start: date, end: date
) -> int:
    """返回区间内的总营业额（分）"""
    row = await db.execute(
        text(
            "SELECT COALESCE(SUM(total_amount), 0) FROM orders "
            "WHERE store_id = :sid AND created_at >= :start AND created_at < :end"
        ),
        {"sid": store_id, "start": start, "end": end},
    )
    return int(row.scalar() or 0)


async def _query_actual_cost(
    db: AsyncSession, store_id: str, start: date, end: date
) -> int:
    """返回区间内的实际食材成本（分，取 usage 事务 ABS(SUM)）"""
    row = await db.execute(
        text(
            "SELECT COALESCE(ABS(SUM(total_cost)), 0) FROM inventory_transactions "
            "WHERE store_id = :sid AND transaction_type = 'usage' "
            "AND transaction_time >= :start AND transaction_time < :end"
        ),
        {"sid": store_id, "start": start, "end": end},
    )
    return int(row.scalar() or 0)


async def _query_waste_cost(
    db: AsyncSession, store_id: str, start: date, end: date
) -> int:
    """返回区间内的损耗成本（分，取 waste 事务 ABS(SUM)）"""
    row = await db.execute(
        text(
            "SELECT COALESCE(ABS(SUM(total_cost)), 0) FROM inventory_transactions "
            "WHERE store_id = :sid AND transaction_type = 'waste' "
            "AND transaction_time >= :start AND transaction_time < :end"
        ),
        {"sid": store_id, "start": start, "end": end},
    )
    return int(row.scalar() or 0)


async def _query_decisions(
    db: AsyncSession, store_id: str, start: date, end: date
) -> List[Dict[str, Any]]:
    """返回区间内的决策日志（status/outcome/ai_suggestion）"""
    rows = await db.execute(
        text(
            "SELECT id, decision_status, outcome, ai_suggestion, ai_confidence, created_at "
            "FROM decision_log "
            "WHERE store_id = :sid AND created_at >= :start AND created_at < :end "
            "ORDER BY created_at DESC"
        ),
        {"sid": store_id, "start": start, "end": end},
    )
    results = []
    for r in rows.fetchall():
        suggestion = r.ai_suggestion if isinstance(r.ai_suggestion, dict) else {}
        results.append({
            "id":               r.id,
            "status":           r.decision_status,
            "outcome":          r.outcome,
            "confidence":       float(r.ai_confidence or 0),
            "action":           suggestion.get("action", ""),
            "expected_saving_yuan": float(suggestion.get("expected_saving_yuan", 0)),
            "created_at":       str(r.created_at),
        })
    return results


# ════════════════════════════════════════════════════════════════════════════════
# 辅助聚合函数（纯函数，便于测试）
# ════════════════════════════════════════════════════════════════════════════════

def _compute_cost_metrics(
    revenue_fen: int,
    actual_cost_fen: int,
    waste_cost_fen: int,
) -> Dict[str, Any]:
    """计算成本率相关指标（含 _yuan 伴随字段）"""
    revenue_yuan       = _fen_to_yuan(revenue_fen)
    actual_cost_yuan   = _fen_to_yuan(actual_cost_fen)
    waste_cost_yuan    = _fen_to_yuan(waste_cost_fen)

    actual_cost_pct = (
        round(actual_cost_fen / revenue_fen * 100, 2) if revenue_fen > 0 else 0.0
    )
    waste_pct = (
        round(waste_cost_fen / revenue_fen * 100, 2) if revenue_fen > 0 else 0.0
    )

    return {
        "revenue_fen":        revenue_fen,
        "revenue_yuan":       revenue_yuan,
        "actual_cost_fen":    actual_cost_fen,
        "actual_cost_yuan":   actual_cost_yuan,
        "actual_cost_pct":    actual_cost_pct,
        "waste_cost_fen":     waste_cost_fen,
        "waste_cost_yuan":    waste_cost_yuan,
        "waste_pct":          waste_pct,
        "cost_rate_status":   _cost_rate_status(actual_cost_pct),
        "cost_rate_label":    _STATUS_LABEL[_cost_rate_status(actual_cost_pct)],
    }


def _summarize_decisions(decisions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """汇总决策执行情况"""
    total      = len(decisions)
    approved   = sum(1 for d in decisions if d["status"] in ("APPROVED", "EXECUTED"))
    rejected   = sum(1 for d in decisions if d["status"] == "REJECTED")
    successful = sum(1 for d in decisions if d["outcome"] == "success")
    total_saving_yuan = sum(
        d["expected_saving_yuan"] for d in decisions if d["status"] == "APPROVED"
    )
    adoption_rate = round(approved / total * 100, 1) if total > 0 else 0.0

    return {
        "total":              total,
        "approved":           approved,
        "rejected":           rejected,
        "successful":         successful,
        "adoption_rate_pct":  adoption_rate,
        "total_saving_yuan":  round(total_saving_yuan, 2),
    }


def _narrative_sentence(
    store_id: str,
    period_label: str,
    cost_metrics: Dict[str, Any],
    decision_summary: Dict[str, Any],
) -> str:
    """生成一段可读的案例叙述文字（用于 PDF 报告）"""
    cost_pct    = cost_metrics["actual_cost_pct"]
    status_lbl  = cost_metrics["cost_rate_label"]
    saving_yuan = decision_summary["total_saving_yuan"]
    adopted     = decision_summary["approved"]
    total_dec   = decision_summary["total"]

    parts = [
        f"{period_label}，门店 {store_id} 食材成本率为 {cost_pct}%（{status_lbl}），",
        f"营业额 ¥{cost_metrics['revenue_yuan']}，",
    ]
    if saving_yuan > 0:
        parts.append(f"通过 {adopted}/{total_dec} 个决策落地，累计节省 ¥{saving_yuan}。")
    else:
        parts.append(f"本期共发起 {total_dec} 个决策，待统计收益。")

    if cost_metrics["waste_cost_yuan"] > 0:
        parts.append(
            f"损耗成本 ¥{cost_metrics['waste_cost_yuan']}，占营收 {cost_metrics['waste_pct']}%。"
        )

    return "".join(parts)


# ════════════════════════════════════════════════════════════════════════════════
# 核心：CaseStoryGenerator
# ════════════════════════════════════════════════════════════════════════════════

class CaseStoryGenerator:
    """案例故事生成器：聚合成本率/损耗/决策数据，输出结构化案例故事"""

    # ── 日维度 ──────────────────────────────────────────────────────────────────

    @staticmethod
    async def generate_daily_story(
        store_id:    str,
        target_date: date,
        db:          AsyncSession,
    ) -> Dict[str, Any]:
        """
        生成指定日期的经营快照案例。

        Returns:
            {
              store_id, date, period, cost_metrics, decision_summary,
              narrative, generated_at
            }
        """
        next_day = target_date + timedelta(days=1)

        revenue_fen     = await _query_revenue(db, store_id, target_date, next_day)
        actual_cost_fen = await _query_actual_cost(db, store_id, target_date, next_day)
        waste_cost_fen  = await _query_waste_cost(db, store_id, target_date, next_day)
        decisions       = await _query_decisions(db, store_id, target_date, next_day)

        cost_metrics = _compute_cost_metrics(revenue_fen, actual_cost_fen, waste_cost_fen)
        decision_summary = _summarize_decisions(decisions)
        period_label = target_date.strftime("%Y年%-m月%-d日")

        return {
            "store_id":        store_id,
            "date":            str(target_date),
            "period":          "daily",
            "period_label":    period_label,
            "cost_metrics":    cost_metrics,
            "decision_summary": decision_summary,
            "decisions":       decisions,
            "narrative":       _narrative_sentence(
                store_id, period_label, cost_metrics, decision_summary
            ),
            "generated_at":    datetime.utcnow().isoformat(),
        }

    # ── 周维度 ──────────────────────────────────────────────────────────────────

    @staticmethod
    async def generate_weekly_story(
        store_id:   str,
        week_start: date,
        db:         AsyncSession,
    ) -> Dict[str, Any]:
        """
        生成以 week_start（周一）为起点的7天经营分析。
        含周环比（与上周同期对比）。
        """
        week_end       = week_start + timedelta(days=7)
        prev_start     = week_start - timedelta(days=7)
        prev_end       = week_start

        # 本周数据
        revenue_fen     = await _query_revenue(db, store_id, week_start, week_end)
        actual_cost_fen = await _query_actual_cost(db, store_id, week_start, week_end)
        waste_cost_fen  = await _query_waste_cost(db, store_id, week_start, week_end)
        decisions       = await _query_decisions(db, store_id, week_start, week_end)

        # 上周数据（用于环比）
        prev_revenue_fen     = await _query_revenue(db, store_id, prev_start, prev_end)
        prev_actual_cost_fen = await _query_actual_cost(db, store_id, prev_start, prev_end)

        cost_metrics     = _compute_cost_metrics(revenue_fen, actual_cost_fen, waste_cost_fen)
        decision_summary = _summarize_decisions(decisions)

        # 环比计算（避免除零）
        revenue_wow = (
            round((revenue_fen - prev_revenue_fen) / prev_revenue_fen * 100, 1)
            if prev_revenue_fen > 0 else 0.0
        )
        prev_cost_pct = (
            round(prev_actual_cost_fen / prev_revenue_fen * 100, 2)
            if prev_revenue_fen > 0 else 0.0
        )
        cost_pct_delta = round(cost_metrics["actual_cost_pct"] - prev_cost_pct, 2)

        period_label = f"{week_start.strftime('%Y年%-m月%-d日')}周"

        return {
            "store_id":          store_id,
            "week_start":        str(week_start),
            "week_end":          str(week_end),
            "period":            "weekly",
            "period_label":      period_label,
            "cost_metrics":      cost_metrics,
            "decision_summary":  decision_summary,
            "week_over_week": {
                "revenue_wow_pct":    revenue_wow,
                "cost_pct_delta":     cost_pct_delta,
                "prev_cost_pct":      prev_cost_pct,
                "prev_revenue_yuan":  _fen_to_yuan(prev_revenue_fen),
            },
            "narrative":         _narrative_sentence(
                store_id, period_label, cost_metrics, decision_summary
            ),
            "generated_at":      datetime.utcnow().isoformat(),
        }

    # ── 月维度 ──────────────────────────────────────────────────────────────────

    @staticmethod
    async def generate_monthly_story(
        store_id: str,
        year:     int,
        month:    int,
        db:       AsyncSession,
    ) -> Dict[str, Any]:
        """
        生成月度经营报告所需的案例叙事数据。

        含：
          - 全月成本率趋势（按周汇总）
          - Top3 决策节省案例（按 expected_saving_yuan DESC）
          - 关键数据摘要（月度总营业额/成本率/损耗/决策采纳数）
          - 完整叙述文字（用于 PDF）
        """
        from calendar import monthrange
        _, last_day = monthrange(year, month)
        month_start = date(year, month, 1)
        month_end   = date(year, month, last_day) + timedelta(days=1)

        revenue_fen     = await _query_revenue(db, store_id, month_start, month_end)
        actual_cost_fen = await _query_actual_cost(db, store_id, month_start, month_end)
        waste_cost_fen  = await _query_waste_cost(db, store_id, month_start, month_end)
        decisions       = await _query_decisions(db, store_id, month_start, month_end)

        cost_metrics     = _compute_cost_metrics(revenue_fen, actual_cost_fen, waste_cost_fen)
        decision_summary = _summarize_decisions(decisions)

        # Top3 节省决策
        top3_decisions = sorted(
            [d for d in decisions if d["status"] in ("APPROVED", "EXECUTED")],
            key=lambda d: d["expected_saving_yuan"],
            reverse=True,
        )[:3]

        # 按周汇总成本趋势
        weekly_trend = []
        cursor = month_start
        while cursor < month_end:
            w_end = min(cursor + timedelta(days=7), month_end)
            w_rev  = await _query_revenue(db, store_id, cursor, w_end)
            w_cost = await _query_actual_cost(db, store_id, cursor, w_end)
            w_pct  = round(w_cost / w_rev * 100, 2) if w_rev > 0 else 0.0
            weekly_trend.append({
                "week_start":        str(cursor),
                "revenue_yuan":      _fen_to_yuan(w_rev),
                "actual_cost_pct":   w_pct,
                "cost_rate_status":  _cost_rate_status(w_pct),
            })
            cursor = w_end

        period_label = f"{year}年{month}月"

        return {
            "store_id":          store_id,
            "year":              year,
            "month":             month,
            "period":            "monthly",
            "period_label":      period_label,
            "cost_metrics":      cost_metrics,
            "decision_summary":  decision_summary,
            "top3_decisions":    top3_decisions,
            "weekly_trend":      weekly_trend,
            "narrative":         _narrative_sentence(
                store_id, period_label, cost_metrics, decision_summary
            ),
            "generated_at":      datetime.utcnow().isoformat(),
        }

    # ── 跨区间摘要（供 scenario_matcher 检索历史数据用）──────────────────────

    @staticmethod
    async def get_metrics_summary(
        store_id:   str,
        start_date: date,
        end_date:   date,
        db:         AsyncSession,
    ) -> Dict[str, Any]:
        """
        轻量级接口：返回区间内的关键指标，不生成叙述文字。
        用于 ScenarioMatcher 等场景快速匹配。
        """
        revenue_fen     = await _query_revenue(db, store_id, start_date, end_date)
        actual_cost_fen = await _query_actual_cost(db, store_id, start_date, end_date)
        waste_cost_fen  = await _query_waste_cost(db, store_id, start_date, end_date)
        decisions       = await _query_decisions(db, store_id, start_date, end_date)

        cost_metrics     = _compute_cost_metrics(revenue_fen, actual_cost_fen, waste_cost_fen)
        decision_summary = _summarize_decisions(decisions)

        return {
            "store_id":          store_id,
            "start_date":        str(start_date),
            "end_date":          str(end_date),
            "cost_metrics":      cost_metrics,
            "decision_summary":  decision_summary,
        }
