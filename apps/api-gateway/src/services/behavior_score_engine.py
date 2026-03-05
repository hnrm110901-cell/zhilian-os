"""
BehaviorScoreEngine — AI建议采纳率跟踪（架构升级 v2.1）

追踪 AI 建议的完整生命周期：
  发出 → 采纳/拒绝 → 执行 → 48h效果反馈

核心指标：
  采纳率   = 采纳数 / 发出数（adopted / total）
  执行准确率 = 已有效果反馈数 / 采纳数（feedback_count / adopted）
  累计节省¥ = 已采纳建议的 expected_saving_yuan 累加（不归因到个人，归因到系统）

用途：
  - 向老板证明系统 ROI（"跟着 AI 走"的行为价值量化）
  - 月度报告 decision_summary 字段的权威数据源
  - 品牌级 ROI 汇总（供续费决策参考）

Rule 6 兼容：所有金额字段含 _yuan 后缀
Rule 3 兼容：不重复 SQL，从现有 DecisionLog 模型聚合
"""

from __future__ import annotations

import os
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# 月服务费基准（元/门店/月），用于 ROI 计算；可通过环境变量覆盖
_MONTHLY_SYSTEM_COST_YUAN = float(os.getenv("MONTHLY_SYSTEM_COST_YUAN", "2000"))

# "有效采纳"状态集合（店长主动接受或执行）
_ADOPTED_STATUSES = {"approved", "modified", "executed"}
# "效果反馈已到位"状态集合（outcome 不为 PENDING）
_FEEDBACK_OUTCOMES = {"success", "failure", "partial"}


# ════════════════════════════════════════════════════════════════════════════════
# 纯函数（无 DB 依赖，便于单元测试）
# ════════════════════════════════════════════════════════════════════════════════

def compute_adoption_rate(decisions: List[Dict[str, Any]]) -> float:
    """
    计算 AI 建议采纳率（0.0–1.0）。

    采纳 = decision_status in (approved / modified / executed)

    Args:
        decisions: 决策 dict 列表，每条含 'decision_status'

    Returns:
        float 0.0–1.0；无数据时返回 0.0
    """
    total = len(decisions)
    if total == 0:
        return 0.0
    adopted = sum(
        1 for d in decisions
        if (d.get("decision_status") or "").lower() in _ADOPTED_STATUSES
    )
    return round(adopted / total, 4)


def compute_execution_accuracy(decisions: List[Dict[str, Any]]) -> float:
    """
    计算已采纳建议中的执行准确率（0.0–1.0）。

    执行准确率 = 有效果反馈条数 / 采纳总数
    有效果反馈 = outcome in (success / failure / partial)

    Args:
        decisions: 决策 dict 列表，每条含 'decision_status' 和 'outcome'

    Returns:
        float 0.0–1.0；无采纳记录时返回 0.0
    """
    adopted = [
        d for d in decisions
        if (d.get("decision_status") or "").lower() in _ADOPTED_STATUSES
    ]
    if not adopted:
        return 0.0
    with_feedback = sum(
        1 for d in adopted
        if (d.get("outcome") or "").lower() in _FEEDBACK_OUTCOMES
    )
    return round(with_feedback / len(adopted), 4)


def compute_total_saving(decisions: List[Dict[str, Any]]) -> float:
    """
    汇总采纳建议的预期节省¥（元）。

    只累加已采纳的建议（不归因到个人，代表系统整体价值）。
    优先取 ai_suggestion.expected_saving_yuan，其次取顶层 expected_saving_yuan。

    Returns:
        float 元，保留2位小数
    """
    total = 0.0
    for d in decisions:
        if (d.get("decision_status") or "").lower() not in _ADOPTED_STATUSES:
            continue
        suggestion = d.get("ai_suggestion") or {}
        saving = (
            suggestion.get("expected_saving_yuan")
            or d.get("expected_saving_yuan")
            or 0.0
        )
        total += float(saving)
    return round(total, 2)


def _classify_adoption(rate_pct: float) -> str:
    """
    采纳率等级：high(≥70%) / medium(≥40%) / low(<40%)
    """
    if rate_pct >= 70:
        return "high"
    if rate_pct >= 40:
        return "medium"
    return "low"


# ════════════════════════════════════════════════════════════════════════════════
# BehaviorScoreEngine（含 DB 查询的完整入口）
# ════════════════════════════════════════════════════════════════════════════════

class BehaviorScoreEngine:
    """
    AI建议采纳率跟踪引擎。

    用法::

        from src.services.behavior_score_engine import BehaviorScoreEngine

        # 门店月度报告
        report = await BehaviorScoreEngine.get_store_report(
            store_id="S001",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            db=session,
        )

        # 品牌级 ROI 汇总
        roi = await BehaviorScoreEngine.get_system_roi_summary(
            brand_id="B001",
            month=date(2026, 3, 1),
            db=session,
        )
    """

    @staticmethod
    async def get_store_report(
        store_id:   str,
        start_date: date,
        end_date:   date,
        db:         AsyncSession,
    ) -> Dict[str, Any]:
        """
        门店维度 AI 建议采纳报告。

        Returns::

            {
                "store_id":             str,
                "period_start":         str,
                "period_end":           str,
                "total_sent":           int,    # AI建议发出数
                "total_adopted":        int,    # 采纳数（approved+modified+executed）
                "total_rejected":       int,    # 拒绝数
                "adoption_rate_pct":    float,  # 采纳率%
                "adoption_level":       str,    # high/medium/low
                "feedback_count":       int,    # 48h内有效果反馈的数量
                "execution_accuracy_pct": float, # 执行准确率%
                "total_saving_yuan":    float,  # 累计预期节省¥（Rule 6）
                "generated_at":         str,
            }
        """
        from src.models.decision_log import DecisionLog

        # 拉取区间内所有决策记录（原始 ORM 对象）
        result = await db.execute(
            select(DecisionLog).where(
                and_(
                    DecisionLog.store_id  == store_id,
                    DecisionLog.created_at >= datetime.combine(start_date, datetime.min.time()),
                    DecisionLog.created_at  < datetime.combine(end_date, datetime.max.time()),
                )
            )
        )
        records = result.scalars().all()

        # 转为 dict 便于纯函数处理
        decisions = [_record_to_dict(r) for r in records]

        adoption_rate  = compute_adoption_rate(decisions)
        exec_accuracy  = compute_execution_accuracy(decisions)
        total_saving   = compute_total_saving(decisions)

        adopted_count   = sum(
            1 for d in decisions
            if (d.get("decision_status") or "").lower() in _ADOPTED_STATUSES
        )
        rejected_count  = sum(
            1 for d in decisions
            if (d.get("decision_status") or "").lower() == "rejected"
        )
        feedback_count  = sum(
            1 for d in decisions
            if (d.get("decision_status") or "").lower() in _ADOPTED_STATUSES
            and (d.get("outcome") or "").lower() in _FEEDBACK_OUTCOMES
        )

        adoption_rate_pct = round(adoption_rate * 100, 1)

        logger.info(
            "behavior_score.store_report",
            store_id=store_id,
            total=len(decisions),
            adopted=adopted_count,
            adoption_rate_pct=adoption_rate_pct,
        )

        return {
            "store_id":                store_id,
            "period_start":            start_date.isoformat(),
            "period_end":              end_date.isoformat(),
            "total_sent":              len(decisions),
            "total_adopted":           adopted_count,
            "total_rejected":          rejected_count,
            "adoption_rate_pct":       adoption_rate_pct,
            "adoption_level":          _classify_adoption(adoption_rate_pct),
            "feedback_count":          feedback_count,
            "execution_accuracy_pct":  round(exec_accuracy * 100, 1),
            "total_saving_yuan":       total_saving,
            "generated_at":            datetime.utcnow().isoformat(),
        }

    @staticmethod
    async def get_system_roi_summary(
        brand_id: str,
        month:    date,
        db:       AsyncSession,
    ) -> Dict[str, Any]:
        """
        品牌级 ROI 汇总（供老板续费决策参考）。

        聚合该品牌所有活跃门店当月的采纳率 + 节省¥，
        对比月服务费，计算系统 ROI 倍数。

        Args:
            brand_id:  品牌 ID（当前版本获取所有活跃门店，未来支持多品牌过滤）
            month:     目标月份（取该月 1 日即可）
            db:        AsyncSession

        Returns::

            {
                "brand_id":              str,
                "year_month":            str,         # "2026-03"
                "store_count":           int,
                "total_sent":            int,
                "total_adopted":         int,
                "avg_adoption_rate_pct": float,
                "total_saving_yuan":     float,
                "monthly_cost_yuan":     float,       # 品牌当月服务费
                "roi_multiple":          float,       # total_saving / monthly_cost
                "roi_label":             str,         # 优秀/良好/持平/待提升
                "generated_at":          str,
            }
        """
        from src.models.store import Store

        # 获取所有活跃门店
        stores_result = await db.execute(
            select(Store).where(Store.is_active == True)
        )
        stores = stores_result.scalars().all()

        # 月份区间
        year  = month.year
        mo    = month.month
        days  = monthrange(year, mo)[1]
        start = date(year, mo, 1)
        end   = date(year, mo, days)

        # 逐店聚合（单店失败静默跳过）
        total_sent    = 0
        total_adopted = 0
        total_saving  = 0.0
        store_count   = 0

        for store in stores:
            try:
                report = await BehaviorScoreEngine.get_store_report(
                    store_id=store.id,
                    start_date=start,
                    end_date=end,
                    db=db,
                )
                total_sent    += report["total_sent"]
                total_adopted += report["total_adopted"]
                total_saving  += report["total_saving_yuan"]
                store_count   += 1
            except Exception as exc:
                logger.warning(
                    "behavior_score.roi_store_failed",
                    store_id=store.id,
                    error=str(exc),
                )

        avg_adoption = round(
            (total_adopted / total_sent * 100) if total_sent > 0 else 0.0, 1
        )
        monthly_cost  = _MONTHLY_SYSTEM_COST_YUAN * store_count
        roi_multiple  = round(total_saving / monthly_cost, 2) if monthly_cost > 0 else 0.0
        roi_label     = _roi_label(roi_multiple)

        logger.info(
            "behavior_score.roi_summary",
            brand_id=brand_id,
            year_month=f"{year:04d}-{mo:02d}",
            store_count=store_count,
            roi_multiple=roi_multiple,
        )

        return {
            "brand_id":              brand_id,
            "year_month":            f"{year:04d}-{mo:02d}",
            "store_count":           store_count,
            "total_sent":            total_sent,
            "total_adopted":         total_adopted,
            "avg_adoption_rate_pct": avg_adoption,
            "total_saving_yuan":     round(total_saving, 2),
            "monthly_cost_yuan":     round(monthly_cost, 2),
            "roi_multiple":          roi_multiple,
            "roi_label":             roi_label,
            "generated_at":          datetime.utcnow().isoformat(),
        }


# ── 内部工具 ────────────────────────────────────────────────────────────────────

def _record_to_dict(record: Any) -> Dict[str, Any]:
    """将 DecisionLog ORM 对象转为计算用 dict"""
    suggestion = record.ai_suggestion or {}
    return {
        "id":                  record.id,
        "store_id":            record.store_id,
        "decision_type":       record.decision_type,
        "decision_status":     record.decision_status.value
                               if hasattr(record.decision_status, "value")
                               else str(record.decision_status or ""),
        "outcome":             record.outcome.value
                               if hasattr(record.outcome, "value")
                               else str(record.outcome or ""),
        "ai_suggestion":       suggestion,
        "expected_saving_yuan": suggestion.get("expected_saving_yuan", 0.0),
        "approved_at":         record.approved_at,
        "created_at":          record.created_at,
    }


def _roi_label(roi: float) -> str:
    """ROI 倍数 → 文字等级"""
    if roi >= 10:
        return "优秀"
    if roi >= 5:
        return "良好"
    if roi >= 1:
        return "持平"
    return "待提升"
