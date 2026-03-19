"""财务智能建议引擎 — Phase 5 Month 10

Phase 5 闭环收官：聚合 Month 5-9 信号（健康评分 + 异常检测 + 对标排名 + 预测），
生成带¥影响 + 置信度 + 优先级的可执行财务建议，支持采纳/驳回状态跟踪。

建议来源（rec_type）：
  anomaly_severe    — 财务指标严重异常（severity=severe）
  anomaly_moderate  — 财务指标明显异常（severity=moderate）
  ranking_laggard   — 对标排名处于落后层级
  forecast_decline  — 预测值较历史均值下行趋势
  forecast_surge    — 成本类指标预测上行（food_cost_rate 预测升高）

紧急度（urgency）：
  high   — priority_score >= 70
  medium — priority_score >= 30
  low    — priority_score < 30
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ── 常量 ─────────────────────────────────────────────────────────────────────

METRICS = ("revenue", "food_cost_rate", "profit_margin", "health_score")

METRIC_LABELS = {
    "revenue": "月净收入",
    "food_cost_rate": "食材成本率",
    "profit_margin": "利润率",
    "health_score": "财务健康评分",
}

METRIC_UNITS = {
    "revenue": "¥",
    "food_cost_rate": "%",
    "profit_margin": "%",
    "health_score": "分",
}

REC_TYPES = (
    "anomaly_severe",
    "anomaly_moderate",
    "ranking_laggard",
    "forecast_decline",
    "forecast_surge",
)

# 紧急度阈值
URGENCY_HIGH = 70.0
URGENCY_MEDIUM = 30.0

# 默认置信度（按来源类型）
CONFIDENCE = {
    "anomaly_severe": 90.0,
    "anomaly_moderate": 75.0,
    "ranking_laggard": 80.0,
    "forecast_decline": 70.0,
    "forecast_surge": 70.0,
}


# ── 内部工具 ──────────────────────────────────────────────────────────────────


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(Decimal(str(val)))
    except Exception:
        return None


def _to_float(val, default: float = 0.0) -> float:
    r = _safe_float(val)
    return r if r is not None else default


# ══════════════════════════════════════════════════════════════════════════════
# 纯函数层
# ══════════════════════════════════════════════════════════════════════════════


def compute_priority_score(
    rec_type: str,
    yuan_impact: Optional[float],
    confidence_pct: float,
) -> float:
    """
    优先级分数 = |¥影响| 权重 + 置信度权重。
    公式：min(50, |yuan| / 1000) + confidence * 0.5
    上限 100。
    """
    impact_score = 0.0
    if yuan_impact is not None:
        impact_score = min(50.0, abs(yuan_impact) / 1000.0)
    conf_score = confidence_pct * 0.5
    # 严重异常额外加权
    if rec_type == "anomaly_severe":
        conf_score = min(50.0, conf_score * 1.2)
    return round(min(100.0, impact_score + conf_score), 2)


def classify_urgency(priority_score: float) -> str:
    if priority_score >= URGENCY_HIGH:
        return "high"
    if priority_score >= URGENCY_MEDIUM:
        return "medium"
    return "low"


def generate_rec_title(rec_type: str, metric: str) -> str:
    label = METRIC_LABELS.get(metric, metric)
    titles = {
        "anomaly_severe": f"【紧急】{label}出现严重异常",
        "anomaly_moderate": f"【关注】{label}出现明显偏差",
        "ranking_laggard": f"【提升】{label}落后同行",
        "forecast_decline": f"【预警】{label}预测持续下行",
        "forecast_surge": f"【预警】{label}预测持续上升",
    }
    return titles.get(rec_type, f"{label}建议")


def generate_rec_action(rec_type: str, metric: str) -> str:
    label = METRIC_LABELS.get(metric, metric)
    unit = METRIC_UNITS.get(metric, "")
    actions = {
        "anomaly_severe": {
            "revenue": "立即排查近期客流与营业时长，对比同期数据定位根因",
            "food_cost_rate": "紧急盘点食材库存，排查损耗来源，暂停高损耗品项",
            "profit_margin": "启动成本专项复核，锁定异常支出项目并制定缩减方案",
            "health_score": "召开财务专项会议，全面检查各分项评分并排查问题门店",
        },
        "anomaly_moderate": {
            "revenue": "分析近3周销售趋势，检查促销与节假日影响",
            "food_cost_rate": "核查采购单价与损耗记录，优化高成本食材采购策略",
            "profit_margin": "梳理固定与变动成本，识别可压缩开支",
            "health_score": "重点关注评分下降的子维度，制定针对性改善计划",
        },
        "ranking_laggard": {
            "revenue": "对标头部门店营销策略，分析差距原因制定追赶计划",
            "food_cost_rate": "参考头部门店采购与损耗管理经验，优化本店操作流程",
            "profit_margin": "学习头部门店成本结构，重点优化差距最大的成本项",
            "health_score": "向头部门店取经财务管理最佳实践，制定改善路线图",
        },
        "forecast_decline": {
            "revenue": "提前制定收入保障预案，加强预订及外卖渠道推广",
            "profit_margin": "预先收紧可变成本，减少下行期损失",
            "health_score": "预防性排查各财务维度风险，建立早期干预机制",
            "food_cost_rate": "预防食材成本超标，提前锁定关键食材价格",
        },
        "forecast_surge": {
            "food_cost_rate": "预警食材成本上升，提前与供应商谈判或寻找替代食材",
            "revenue": "收入预计超预期，提前备足人力与食材，避免供应不足",
            "profit_margin": "利润预计回升，保持当前策略并做好产能准备",
            "health_score": "财务状况预计改善，持续执行现有优化举措",
        },
    }
    return actions.get(rec_type, {}).get(metric, f"持续关注{label}变化，及时响应")


def generate_rec_description(
    rec_type: str,
    metric: str,
    actual_value: Optional[float],
    reference_value: Optional[float],
    deviation_pct: Optional[float],
    yuan_impact: Optional[float],
    extra_context: str = "",
) -> str:
    """生成中文描述，≤200字。"""
    label = METRIC_LABELS.get(metric, metric)
    unit = METRIC_UNITS.get(metric, "")

    def fmt(v: float) -> str:
        if metric == "revenue":
            return f"¥{v:,.0f}"
        if metric == "health_score":
            return f"{v:.1f}分"
        return f"{v:.1f}{unit}"

    parts: List[str] = []

    if actual_value is not None and reference_value is not None:
        parts.append(f"{label}当前 {fmt(actual_value)}，参考值 {fmt(reference_value)}")
        if deviation_pct is not None:
            parts.append(f"，偏差 {deviation_pct:+.1f}%")
        parts.append("。")

    if yuan_impact is not None and abs(yuan_impact) >= 100:
        parts.append(f"预计¥影响约 {abs(yuan_impact):,.0f} 元。")

    if extra_context:
        parts.append(extra_context)

    return "".join(parts)[:200]


def build_anomaly_recommendations(
    anomalies: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    将异常检测结果（来自 financial_anomaly_records）转为建议列表。
    只处理 severity in (severe, moderate)。
    """
    recs: List[Dict[str, Any]] = []
    for a in anomalies:
        severity = a.get("severity", "normal")
        if severity not in ("severe", "moderate"):
            continue

        metric = a.get("metric", "")
        rec_type = "anomaly_severe" if severity == "severe" else "anomaly_moderate"
        yuan = a.get("yuan_impact")
        conf = CONFIDENCE[rec_type]
        priority = compute_priority_score(rec_type, yuan, conf)
        actual = a.get("actual_value")
        expected = a.get("expected_value")
        dev = a.get("deviation_pct")
        context = a.get("description", "") or ""

        recs.append(
            {
                "rec_type": rec_type,
                "metric": metric,
                "title": generate_rec_title(rec_type, metric),
                "description": generate_rec_description(rec_type, metric, actual, expected, dev, yuan, context[:50]),
                "action": generate_rec_action(rec_type, metric),
                "expected_yuan_impact": round(yuan, 2) if yuan is not None else None,
                "confidence_pct": conf,
                "urgency": classify_urgency(priority),
                "priority_score": priority,
                "source_type": "anomaly",
                "source_ref": f"anomaly:{metric}",
            }
        )
    return recs


def build_ranking_recommendations(
    rankings: Dict[str, Any],  # {metric: {tier, percentile, rank, ...}}
    gaps: List[Dict[str, Any]],  # benchmark_gaps list
) -> List[Dict[str, Any]]:
    """将排名落后情况转为建议。只处理 tier=laggard 的指标。"""
    recs: List[Dict[str, Any]] = []
    # 找到各指标的 best gap 的¥潜力
    best_gap: Dict[str, Optional[float]] = {}
    for g in gaps:
        if g.get("benchmark_type") == "top_quartile" and g.get("gap_direction") == "below":
            metric = g.get("metric", "")
            best_gap[metric] = g.get("yuan_potential")

    for metric, entry in rankings.items():
        if entry.get("tier") != "laggard":
            continue
        rec_type = "ranking_laggard"
        yuan = best_gap.get(metric)
        conf = CONFIDENCE[rec_type]
        priority = compute_priority_score(rec_type, yuan, conf)
        actual = entry.get("value")
        percentile = entry.get("percentile")
        context = f"排名第{entry.get('rank')}位（{percentile:.0f}th 百分位）。" if percentile is not None else ""

        recs.append(
            {
                "rec_type": rec_type,
                "metric": metric,
                "title": generate_rec_title(rec_type, metric),
                "description": generate_rec_description(rec_type, metric, actual, None, None, yuan, context),
                "action": generate_rec_action(rec_type, metric),
                "expected_yuan_impact": round(yuan, 2) if yuan is not None else None,
                "confidence_pct": conf,
                "urgency": classify_urgency(priority),
                "priority_score": priority,
                "source_type": "ranking",
                "source_ref": f"ranking:{metric}",
            }
        )
    return recs


def build_forecast_recommendations(
    forecasts: Dict[str, Any],  # {metric: {trend_direction, predicted_value, ...}}
) -> List[Dict[str, Any]]:
    """
    将预测方向转为建议：
      revenue/profit_margin/health_score 下行 → forecast_decline
      food_cost_rate 上行 → forecast_surge
    """
    recs: List[Dict[str, Any]] = []
    for metric, fc in forecasts.items():
        if not isinstance(fc, dict):
            continue
        direction = fc.get("trend_direction", "flat")
        predicted = fc.get("predicted_value")
        actual = fc.get("actual_value") or fc.get("last_actual")  # may vary

        if metric in ("revenue", "profit_margin", "health_score") and direction == "down":
            rec_type = "forecast_decline"
        elif metric == "food_cost_rate" and direction == "up":
            rec_type = "forecast_surge"
        else:
            continue

        conf = CONFIDENCE[rec_type]
        priority = compute_priority_score(rec_type, None, conf)

        recs.append(
            {
                "rec_type": rec_type,
                "metric": metric,
                "title": generate_rec_title(rec_type, metric),
                "description": generate_rec_description(rec_type, metric, actual, predicted, None, None),
                "action": generate_rec_action(rec_type, metric),
                "expected_yuan_impact": None,
                "confidence_pct": conf,
                "urgency": classify_urgency(priority),
                "priority_score": priority,
                "source_type": "forecast",
                "source_ref": f"forecast:{metric}",
            }
        )
    return recs


def merge_and_prioritize(
    recs: List[Dict[str, Any]],
    max_recs: int = 10,
) -> List[Dict[str, Any]]:
    """
    合并去重（同 rec_type+metric 取第一个），按 priority_score DESC 排序，取前 max_recs 条。
    """
    seen: set = set()
    unique: List[Dict[str, Any]] = []
    for r in recs:
        key = (r["rec_type"], r["metric"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    unique.sort(key=lambda x: x["priority_score"], reverse=True)
    return unique[:max_recs]


# ══════════════════════════════════════════════════════════════════════════════
# DB 函数层
# ══════════════════════════════════════════════════════════════════════════════


async def _upsert_recommendation(
    db: AsyncSession,
    store_id: str,
    period: str,
    rec: Dict[str, Any],
) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.execute(
        text("""
            INSERT INTO financial_recommendations
                (store_id, period, rec_type, metric, title, description, action,
                 expected_yuan_impact, confidence_pct, urgency, priority_score,
                 source_type, source_ref, status, created_at, updated_at)
            VALUES
                (:sid, :period, :rtype, :metric, :title, :desc, :action,
                 :impact, :conf, :urgency, :score,
                 :stype, :sref, 'pending', :now, :now)
            ON CONFLICT (store_id, period, rec_type, metric) DO UPDATE SET
                title                = EXCLUDED.title,
                description          = EXCLUDED.description,
                action               = EXCLUDED.action,
                expected_yuan_impact = EXCLUDED.expected_yuan_impact,
                confidence_pct       = EXCLUDED.confidence_pct,
                urgency              = EXCLUDED.urgency,
                priority_score       = EXCLUDED.priority_score,
                source_type          = EXCLUDED.source_type,
                source_ref           = EXCLUDED.source_ref,
                updated_at           = EXCLUDED.updated_at
        """),
        {
            "sid": store_id,
            "period": period,
            "rtype": rec["rec_type"],
            "metric": rec["metric"],
            "title": rec["title"],
            "desc": rec.get("description", ""),
            "action": rec.get("action", ""),
            "impact": rec.get("expected_yuan_impact"),
            "conf": rec["confidence_pct"],
            "urgency": rec["urgency"],
            "score": rec["priority_score"],
            "stype": rec.get("source_type"),
            "sref": rec.get("source_ref"),
            "now": now,
        },
    )


async def _fetch_anomalies(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> List[Dict[str, Any]]:
    """从 financial_anomaly_records 拉取当期异常。"""
    rows = await db.execute(
        text("""
            SELECT metric, actual_value, expected_value, deviation_pct,
                   severity, description, yuan_impact
            FROM financial_anomaly_records
            WHERE store_id = :sid AND period = :period AND is_anomaly = true
        """),
        {"sid": store_id, "period": period},
    )
    return [
        {
            "metric": r[0],
            "actual_value": _safe_float(r[1]),
            "expected_value": _safe_float(r[2]),
            "deviation_pct": _safe_float(r[3]),
            "severity": r[4],
            "description": r[5],
            "yuan_impact": _safe_float(r[6]),
        }
        for r in rows.fetchall()
    ]


async def _fetch_rankings(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> Dict[str, Any]:
    """从 store_performance_rankings 拉取当期排名。"""
    rows = await db.execute(
        text("""
            SELECT metric, value, rank, total_stores, percentile, tier, rank_change
            FROM store_performance_rankings
            WHERE store_id = :sid AND period = :period
        """),
        {"sid": store_id, "period": period},
    )
    result: Dict[str, Any] = {}
    for r in rows.fetchall():
        result[r[0]] = {
            "metric": r[0],
            "value": _safe_float(r[1]),
            "rank": r[2],
            "total_stores": r[3],
            "percentile": _safe_float(r[4]),
            "tier": r[5],
            "rank_change": r[6],
        }
    return result


async def _fetch_gaps(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> List[Dict[str, Any]]:
    """从 store_benchmark_gaps 拉取对标差距。"""
    rows = await db.execute(
        text("""
            SELECT metric, benchmark_type, store_value, benchmark_value,
                   gap_pct, gap_direction, yuan_potential
            FROM store_benchmark_gaps
            WHERE store_id = :sid AND period = :period
        """),
        {"sid": store_id, "period": period},
    )
    return [
        {
            "metric": r[0],
            "benchmark_type": r[1],
            "store_value": _safe_float(r[2]),
            "benchmark_value": _safe_float(r[3]),
            "gap_pct": _safe_float(r[4]),
            "gap_direction": r[5],
            "yuan_potential": _safe_float(r[6]),
        }
        for r in rows.fetchall()
    ]


async def _fetch_forecasts(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> Dict[str, Any]:
    """从 financial_forecasts 拉取当期预测趋势。"""
    rows = await db.execute(
        text("""
            SELECT forecast_type, predicted_value, actual_value, accuracy_pct
            FROM financial_forecasts
            WHERE store_id = :sid AND target_period = :period
        """),
        {"sid": store_id, "period": period},
    )
    # We need trend_direction — derive from accuracy or use a simplified heuristic.
    # Since financial_forecasts may not store trend_direction directly,
    # we fetch it from the raw service table if available, else skip.
    # Simplified: treat accuracy < 85 with negative deviation as "down", > 115% as "up".
    result: Dict[str, Any] = {}
    for r in rows.fetchall():
        metric, pred, actual, acc = r[0], _safe_float(r[1]), _safe_float(r[2]), _safe_float(r[3])
        if pred is None:
            continue
        # Determine trend direction from predicted vs actual if actual exists,
        # otherwise treat any prediction as flat.
        trend = "flat"
        if actual is not None and actual != 0 and pred is not None:
            dev = (pred - actual) / abs(actual) * 100
            if dev < -5:
                trend = "down"
            elif dev > 5:
                trend = "up"
        result[metric] = {
            "predicted_value": pred,
            "actual_value": actual,
            "accuracy_pct": acc,
            "trend_direction": trend,
        }
    return result


async def generate_store_recommendations(
    db: AsyncSession,
    store_id: str,
    period: str,
    max_recs: int = 10,
) -> Dict[str, Any]:
    """
    聚合 Phase 5 全部信号 → 生成并持久化建议列表，返回汇总。
    """
    anomalies = await _fetch_anomalies(db, store_id, period)
    rankings = await _fetch_rankings(db, store_id, period)
    gaps = await _fetch_gaps(db, store_id, period)
    forecasts = await _fetch_forecasts(db, store_id, period)

    all_recs: List[Dict[str, Any]] = []
    all_recs.extend(build_anomaly_recommendations(anomalies))
    all_recs.extend(build_ranking_recommendations(rankings, gaps))
    all_recs.extend(build_forecast_recommendations(forecasts))

    final_recs = merge_and_prioritize(all_recs, max_recs=max_recs)

    for rec in final_recs:
        await _upsert_recommendation(db, store_id, period, rec)
    await db.commit()

    urgency_counts = {"high": 0, "medium": 0, "low": 0}
    for r in final_recs:
        urgency_counts[r["urgency"]] = urgency_counts.get(r["urgency"], 0) + 1

    return {
        "store_id": store_id,
        "period": period,
        "total_recs": len(final_recs),
        "urgency_counts": urgency_counts,
        "recommendations": final_recs,
    }


async def get_recommendations(
    db: AsyncSession,
    store_id: str,
    period: str,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """获取门店当期建议列表，按 priority_score DESC。"""
    if status:
        rows = await db.execute(
            text("""
                SELECT id, rec_type, metric, title, description, action,
                       expected_yuan_impact, confidence_pct, urgency, priority_score,
                       source_type, source_ref, status, created_at
                FROM financial_recommendations
                WHERE store_id = :sid AND period = :period AND status = :status
                ORDER BY priority_score DESC
            """),
            {"sid": store_id, "period": period, "status": status},
        )
    else:
        rows = await db.execute(
            text("""
                SELECT id, rec_type, metric, title, description, action,
                       expected_yuan_impact, confidence_pct, urgency, priority_score,
                       source_type, source_ref, status, created_at
                FROM financial_recommendations
                WHERE store_id = :sid AND period = :period
                ORDER BY priority_score DESC
            """),
            {"sid": store_id, "period": period},
        )
    return [
        {
            "id": r[0],
            "rec_type": r[1],
            "metric": r[2],
            "metric_label": METRIC_LABELS.get(r[2], r[2]),
            "title": r[3],
            "description": r[4],
            "action": r[5],
            "expected_yuan_impact": _safe_float(r[6]),
            "confidence_pct": _safe_float(r[7]),
            "urgency": r[8],
            "priority_score": _safe_float(r[9]),
            "source_type": r[10],
            "source_ref": r[11],
            "status": r[12],
            "created_at": r[13].isoformat() if r[13] else None,
        }
        for r in rows.fetchall()
    ]


async def update_recommendation_status(
    db: AsyncSession,
    rec_id: int,
    new_status: str,
) -> Dict[str, Any]:
    """将建议状态更新为 adopted 或 dismissed。"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if new_status == "adopted":
        result = await db.execute(
            text("""
                UPDATE financial_recommendations
                SET status = 'adopted', adopted_at = :now, updated_at = :now
                WHERE id = :rid AND status = 'pending'
                RETURNING id
            """),
            {"rid": rec_id, "now": now},
        )
    elif new_status == "dismissed":
        result = await db.execute(
            text("""
                UPDATE financial_recommendations
                SET status = 'dismissed', dismissed_at = :now, updated_at = :now
                WHERE id = :rid AND status = 'pending'
                RETURNING id
            """),
            {"rid": rec_id, "now": now},
        )
    else:
        return {"updated": False, "reason": f"无效状态: {new_status}"}

    row = result.fetchone()
    await db.commit()
    return {"updated": row is not None, "id": rec_id, "status": new_status}


async def get_recommendation_stats(
    db: AsyncSession,
    store_id: str,
    periods: int = 6,
) -> List[Dict[str, Any]]:
    """近 N 期建议采纳率统计，按期升序。"""
    rows = await db.execute(
        text("""
            SELECT period,
                   COUNT(*) FILTER (WHERE status = 'pending')  AS pending,
                   COUNT(*) FILTER (WHERE status = 'adopted')  AS adopted,
                   COUNT(*) FILTER (WHERE status = 'dismissed') AS dismissed,
                   COUNT(*) AS total
            FROM financial_recommendations
            WHERE store_id = :sid
            GROUP BY period
            ORDER BY period DESC
            LIMIT :lim
        """),
        {"sid": store_id, "lim": periods},
    )
    records = [
        {
            "period": r[0],
            "pending": r[1],
            "adopted": r[2],
            "dismissed": r[3],
            "total": r[4],
            "adoption_rate": round(r[2] / r[4] * 100, 1) if r[4] > 0 else 0.0,
        }
        for r in rows.fetchall()
    ]
    return list(reversed(records))


async def get_brand_rec_summary(
    db: AsyncSession,
    brand_id: str,
    period: str,
) -> Dict[str, Any]:
    """品牌级建议汇总（按 period 聚合全部门店）。"""
    rows = await db.execute(
        text("""
            SELECT store_id, urgency, status, expected_yuan_impact
            FROM financial_recommendations
            WHERE period = :period
            ORDER BY store_id
        """),
        {"period": period},
    )
    records = rows.fetchall()

    stores: set = set()
    urgency_counts: Dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    status_counts: Dict[str, int] = {"pending": 0, "adopted": 0, "dismissed": 0}
    total_yuan = 0.0

    for r in records:
        sid, urgency, status, impact = r[0], r[1], r[2], r[3]
        stores.add(sid)
        urgency_counts[urgency] = urgency_counts.get(urgency, 0) + 1
        status_counts[status] = status_counts.get(status, 0) + 1
        if impact is not None:
            total_yuan += abs(_to_float(impact))

    total = len(records)
    adopted = status_counts["adopted"]
    adoption_rate = round(adopted / total * 100, 1) if total > 0 else 0.0

    return {
        "brand_id": brand_id,
        "period": period,
        "total_recs": total,
        "affected_stores": len(stores),
        "urgency_counts": urgency_counts,
        "status_counts": status_counts,
        "adoption_rate": adoption_rate,
        "total_yuan_potential": round(total_yuan, 2),
    }
