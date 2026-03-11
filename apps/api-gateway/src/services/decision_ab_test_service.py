"""
DecisionPushABTestService — 决策推送 4 时间点 A/B 测试分析

通过分析 DecisionLog 的 created_at 时段，将每条决策归因到最近一次推送
时间点，统计各时间点的决策采纳率、响应速度等指标，评估哪个推送时间效果最优。

4 个推送时间点（Variant）：
  A — 晨推   08:00  归因窗口 [08:00, 12:00)
  B — 午推   12:00  归因窗口 [12:00, 17:30)
  C — 战前   17:30  归因窗口 [17:30, 20:30)
  D — 晚推   20:30  归因窗口 [20:30, 08:00 次日)

核心指标：
  - adoption_rate   决策采纳率 = approved / total
  - response_minutes 平均响应时长（approved_at - created_at）
  - confidence       Wilson Score 置信区间下界（评估统计显著性）
  - winner           当前最优时间点

统计方法：
  Wilson Score 置信区间（单侧 95%）衡量小样本采纳率的可信度：
  lower = (p + z²/2n - z*√(p(1-p)/n + z²/4n²)) / (1 + z²/n)
  其中 z=1.645（单侧 90% CI）
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.decision_log import DecisionLog, DecisionStatus

logger = structlog.get_logger()

# 4 个推送时间点定义：name → (start_hour_min, end_hour_min exclusive)
PUSH_VARIANTS: List[Dict[str, Any]] = [
    {"id": "A", "label": "晨推",  "time": "08:00", "window_start": (8,  0),  "window_end": (12, 0)},
    {"id": "B", "label": "午推",  "time": "12:00", "window_start": (12, 0),  "window_end": (17, 30)},
    {"id": "C", "label": "战前",  "time": "17:30", "window_start": (17, 30), "window_end": (20, 30)},
    {"id": "D", "label": "晚推",  "time": "20:30", "window_start": (20, 30), "window_end": (32, 0)},  # 32:00 = 次日 08:00
]

_Z_90 = 1.6449  # 单侧 90% 置信区间 z 值（等价于双侧 80% CI）


def _assign_variant(dt: datetime) -> str:
    """将 decision_log.created_at 归因到对应推送时间点 Variant ID。"""
    h, m = dt.hour, dt.minute
    total_min = h * 60 + m
    if 8 * 60 <= total_min < 12 * 60:
        return "A"
    if 12 * 60 <= total_min < 17 * 60 + 30:
        return "B"
    if 17 * 60 + 30 <= total_min < 20 * 60 + 30:
        return "C"
    return "D"  # [20:30, 08:00 次日)


def _wilson_lower(successes: int, total: int, z: float = _Z_90) -> float:
    """
    Wilson Score 置信区间下界（可信度指标）。
    total=0 时返回 0.0。
    """
    if total == 0:
        return 0.0
    p = successes / total
    z2 = z * z
    n = total
    center = (p + z2 / (2 * n))
    margin = z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)
    lower = (center - margin) / (1 + z2 / n)
    return round(max(0.0, lower), 4)


class DecisionPushABTestService:
    """决策推送时间点 A/B 测试分析服务。"""

    @staticmethod
    async def analyze(
        session: AsyncSession,
        store_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        lookback_days: int = 30,
    ) -> Dict[str, Any]:
        """
        分析各推送时间点的决策采纳效果。

        Args:
            store_id:      指定门店（None = 全门店汇总）
            start_date:    统计起始日期（None 则用 end_date - lookback_days）
            end_date:      统计截止日期（None 则用今天）
            lookback_days: 回望天数（start_date 为 None 时有效）

        Returns:
            {
              period, total_decisions, variants: [...],
              winner_id, winner_label, recommendation
            }
        """
        today = date.today()
        _end   = end_date   or today
        _start = start_date or (_end - timedelta(days=lookback_days))

        filters = [
            DecisionLog.created_at >= datetime.combine(_start, datetime.min.time()),
            DecisionLog.created_at <= datetime.combine(_end,   datetime.max.time()),
        ]
        if store_id:
            filters.append(DecisionLog.store_id == store_id)

        rows = (
            await session.execute(
                select(
                    DecisionLog.id,
                    DecisionLog.created_at,
                    DecisionLog.approved_at,
                    DecisionLog.decision_status,
                )
                .where(and_(*filters))
            )
        ).all()

        # 归因到各 Variant
        buckets: Dict[str, Dict[str, Any]] = {
            v["id"]: {"total": 0, "approved": 0, "response_minutes": []}
            for v in PUSH_VARIANTS
        }
        for row in rows:
            vid = _assign_variant(row.created_at)
            b = buckets[vid]
            b["total"] += 1
            if row.decision_status in (
                DecisionStatus.APPROVED, DecisionStatus.EXECUTED
            ):
                b["approved"] += 1
                if row.approved_at:
                    delta_min = (row.approved_at - row.created_at).total_seconds() / 60
                    if 0 < delta_min < 1440:  # 仅统计 24h 内的响应
                        b["response_minutes"].append(delta_min)

        # 构建 Variant 统计结果
        variant_stats: List[Dict[str, Any]] = []
        for v in PUSH_VARIANTS:
            b = buckets[v["id"]]
            total    = b["total"]
            approved = b["approved"]
            adoption = round(approved / total, 4) if total else 0.0
            resp_mins = b["response_minutes"]
            avg_resp  = round(sum(resp_mins) / len(resp_mins), 1) if resp_mins else None
            wilson    = _wilson_lower(approved, total)

            variant_stats.append({
                "id":              v["id"],
                "label":           v["label"],
                "push_time":       v["time"],
                "total":           total,
                "approved":        approved,
                "adoption_rate":   adoption,
                "adoption_pct":    round(adoption * 100, 1),
                "avg_response_minutes": avg_resp,
                "wilson_lower":    wilson,
                "sufficient_data": total >= 10,  # 样本量 ≥ 10 才视为数据可信
            })

        # 选出 winner：Wilson Score 最高且有足够数据的 Variant
        eligible = [s for s in variant_stats if s["sufficient_data"]]
        winner = max(eligible, key=lambda s: s["wilson_lower"]) if eligible else None

        # 生成建议文字
        if not eligible:
            recommendation = "数据量不足（每个时间点需至少 10 条决策），建议收集更多数据后再评估"
        elif winner:
            recommendation = (
                f"当前最优推送时间点为【{winner['label']} {winner['push_time']}】，"
                f"采纳率 {winner['adoption_pct']}%，"
                f"统计置信度评分 {winner['wilson_lower']:.3f}。"
                + (f" 平均响应时长 {winner['avg_response_minutes']:.0f} 分钟。"
                   if winner['avg_response_minutes'] else "")
            )
        else:
            recommendation = "暂无显著最优时间点"

        return {
            "period":           f"{_start.isoformat()} ~ {_end.isoformat()}",
            "store_id":         store_id or "all",
            "total_decisions":  len(rows),
            "variants":         variant_stats,
            "winner_id":        winner["id"]    if winner else None,
            "winner_label":     winner["label"] if winner else None,
            "recommendation":   recommendation,
            "generated_at":     datetime.utcnow().isoformat(),
        }

    @staticmethod
    async def compare_stores(
        session: AsyncSession,
        store_ids: List[str],
        lookback_days: int = 30,
    ) -> Dict[str, Any]:
        """
        多门店横向对比各推送时间点效果，找出普遍最优时间点。
        """
        results = {}
        for sid in store_ids:
            try:
                r = await DecisionPushABTestService.analyze(
                    session=session, store_id=sid, lookback_days=lookback_days
                )
                results[sid] = r
            except Exception as exc:
                logger.warning("ab_test_store_failed", store_id=sid, error=str(exc))

        # 汇总各 Variant 的跨店均值
        variant_agg: Dict[str, List[float]] = {v["id"]: [] for v in PUSH_VARIANTS}
        for r in results.values():
            for s in r.get("variants", []):
                if s["sufficient_data"]:
                    variant_agg[s["id"]].append(s["adoption_rate"])

        global_variants = []
        for v in PUSH_VARIANTS:
            rates = variant_agg[v["id"]]
            global_variants.append({
                "id":            v["id"],
                "label":         v["label"],
                "push_time":     v["time"],
                "store_count":   len(rates),
                "avg_adoption_pct": round(sum(rates) / len(rates) * 100, 1) if rates else None,
            })

        best = max(
            (g for g in global_variants if g["store_count"] > 0),
            key=lambda g: g["avg_adoption_pct"] or 0,
            default=None,
        )

        return {
            "lookback_days": lookback_days,
            "store_count":   len(results),
            "global_variants": global_variants,
            "global_winner_id":    best["id"]    if best else None,
            "global_winner_label": best["label"] if best else None,
            "store_results":  results,
            "generated_at":   datetime.utcnow().isoformat(),
        }


decision_ab_test_service = DecisionPushABTestService()
