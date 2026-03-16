"""
私域健康分引擎
Private Domain Health Score Engine

综合评分：5个维度加权 → 0-100分
  ① 会员质量    30分 — S4/S5 高价值会员占比
  ② 留存控制    25分 — 低风险会员比例（risk_score < 0.4）
  ③ 信号响应    20分 — 近30天信号已处理率
  ④ 旅程完成    15分 — 近30天旅程完成率
  ⑤ 增长势能    10分 — 近7天新客激活率

等级：优秀(85+) / 良好(70-84) / 待改善(50-69) / 预警(<50)

所有查询全部容错降级，不影响页面渲染。
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# ── 维度权重 ──────────────────────────────────────────────────────────────────

DIMENSIONS = [
    {"key": "member_quality", "label": "会员质量", "weight": 30},
    {"key": "churn_control", "label": "留存控制", "weight": 25},
    {"key": "signal_response", "label": "信号响应", "weight": 20},
    {"key": "journey_complete", "label": "旅程完成", "weight": 15},
    {"key": "growth_momentum", "label": "增长势能", "weight": 10},
]

_DIMENSION_ACTIONS: Dict[str, str] = {
    "member_quality": "优化 RFM 运营策略，将 S2/S3 会员升级为高价值 S4/S5",
    "churn_control": "立即启动高风险会员唤醒旅程，降低流失率",
    "signal_response": "处理积压信号（差评/流失预警），提升运营响应速度",
    "journey_complete": "检查旅程卡点，优化触达时机和消息内容",
    "growth_momentum": "加强新客激活流程，提升 7 天首单转化率",
}


# ── 内部查询 helpers ──────────────────────────────────────────────────────────


async def _scalar(db: AsyncSession, sql: str, params: dict, default=0):
    try:
        row = (await db.execute(text(sql), params)).fetchone()
        return row[0] if row and row[0] is not None else default
    except Exception as exc:
        logger.warning("health_svc.query_failed", sql=sql[:80], error=str(exc))
        return default


# ── 五维度计算 ────────────────────────────────────────────────────────────────


async def _dim_member_quality(store_id: str, db: AsyncSession) -> Dict[str, Any]:
    """S4/S5 高价值会员占比 → 满分 30 分"""
    total = await _scalar(
        db,
        """
        SELECT COUNT(*) FROM private_domain_members
        WHERE store_id = :s
    """,
        {"s": store_id},
    )

    premium = await _scalar(
        db,
        """
        SELECT COUNT(*) FROM private_domain_members
        WHERE store_id = :s AND rfm_level IN ('S4', 'S5')
    """,
        {"s": store_id},
    )

    rate = premium / total if total > 0 else 0.0
    score = round(rate * 30, 1)
    return {
        "key": "member_quality",
        "label": "会员质量",
        "score": score,
        "max": 30,
        "rate": round(rate, 3),
        "detail": f"高价值会员 {int(premium)}/{int(total)}（{rate:.1%}）",
    }


async def _dim_churn_control(store_id: str, db: AsyncSession) -> Dict[str, Any]:
    """低风险会员比例（risk_score < 0.4）→ 满分 25 分"""
    total = await _scalar(
        db,
        """
        SELECT COUNT(*) FROM private_domain_members
        WHERE store_id = :s
    """,
        {"s": store_id},
    )

    safe = await _scalar(
        db,
        """
        SELECT COUNT(*) FROM private_domain_members
        WHERE store_id = :s AND risk_score < 0.4
    """,
        {"s": store_id},
    )

    rate = safe / total if total > 0 else 0.0
    score = round(rate * 25, 1)
    return {
        "key": "churn_control",
        "label": "留存控制",
        "score": score,
        "max": 25,
        "rate": round(rate, 3),
        "detail": f"低风险会员 {int(safe)}/{int(total)}（{rate:.1%}）",
    }


async def _dim_signal_response(store_id: str, db: AsyncSession) -> Dict[str, Any]:
    """近 30 天信号已处理率 → 满分 20 分"""
    since = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()

    total = await _scalar(
        db,
        """
        SELECT COUNT(*) FROM private_domain_signals
        WHERE store_id = :s AND triggered_at::date >= :since
    """,
        {"s": store_id, "since": since},
    )

    resolved = await _scalar(
        db,
        """
        SELECT COUNT(*) FROM private_domain_signals
        WHERE store_id = :s
          AND triggered_at::date >= :since
          AND resolved_at IS NOT NULL
    """,
        {"s": store_id, "since": since},
    )

    rate = resolved / total if total > 0 else 1.0  # 无信号视为满分
    score = round(rate * 20, 1)
    return {
        "key": "signal_response",
        "label": "信号响应",
        "score": score,
        "max": 20,
        "rate": round(rate, 3),
        "detail": f"已处理信号 {int(resolved)}/{int(total)}（30天）",
    }


async def _dim_journey_complete(store_id: str, db: AsyncSession) -> Dict[str, Any]:
    """近 30 天旅程完成率 → 满分 15 分"""
    since = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()

    total = await _scalar(
        db,
        """
        SELECT COUNT(*) FROM private_domain_journeys
        WHERE store_id = :s AND started_at::date >= :since
    """,
        {"s": store_id, "since": since},
    )

    completed = await _scalar(
        db,
        """
        SELECT COUNT(*) FROM private_domain_journeys
        WHERE store_id = :s
          AND started_at::date >= :since
          AND status = 'completed'
    """,
        {"s": store_id, "since": since},
    )

    rate = completed / total if total > 0 else 1.0  # 无旅程视为满分
    score = round(rate * 15, 1)
    return {
        "key": "journey_complete",
        "label": "旅程完成",
        "score": score,
        "max": 15,
        "rate": round(rate, 3),
        "detail": f"旅程完成 {int(completed)}/{int(total)}（30天）",
    }


async def _dim_growth_momentum(store_id: str, db: AsyncSession) -> Dict[str, Any]:
    """近 7 天新客激活率 → 满分 10 分
    新客 = 近7天加入的会员；激活 = 该会员有 new_customer 类型 completed 旅程
    """
    since = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()

    new_members = await _scalar(
        db,
        """
        SELECT COUNT(*) FROM private_domain_members
        WHERE store_id = :s AND created_at::date >= :since
    """,
        {"s": store_id, "since": since},
    )

    activated = await _scalar(
        db,
        """
        SELECT COUNT(DISTINCT j.customer_id)
        FROM private_domain_journeys j
        JOIN private_domain_members m
          ON m.store_id = j.store_id AND m.customer_id = j.customer_id
        WHERE j.store_id  = :s
          AND j.journey_type = 'new_customer'
          AND j.status       = 'completed'
          AND m.created_at::date >= :since
    """,
        {"s": store_id, "since": since},
    )

    rate = activated / new_members if new_members > 0 else 1.0  # 无新客视为满分
    score = round(rate * 10, 1)
    return {
        "key": "growth_momentum",
        "label": "增长势能",
        "score": score,
        "max": 10,
        "rate": round(rate, 3),
        "detail": f"新客激活 {int(activated)}/{int(new_members)}（7天）",
    }


# ── 等级与行动建议 ─────────────────────────────────────────────────────────────


def _grade(total_score: float) -> Dict[str, str]:
    if total_score >= 85:
        return {"level": "优秀", "color": "green", "desc": "私域运营状态优秀，保持现有策略并挖掘裂变增长"}
    if total_score >= 70:
        return {"level": "良好", "color": "blue", "desc": "整体健康，关注薄弱维度可进一步提升续费率"}
    if total_score >= 50:
        return {"level": "待改善", "color": "orange", "desc": "存在明显短板，建议优先处理得分最低的维度"}
    return {"level": "预警", "color": "red", "desc": "私域健康度较低，需要立即介入改善关键指标"}


def _top_actions(dims: List[Dict[str, Any]], n: int = 3) -> List[Dict[str, str]]:
    """按得分/满分比值升序，取最薄弱的 n 个维度作为行动建议"""
    sorted_dims = sorted(dims, key=lambda d: d["score"] / d["max"] if d["max"] > 0 else 1.0)
    actions = []
    for d in sorted_dims[:n]:
        actions.append(
            {
                "dimension": d["label"],
                "score_pct": f"{d['score'] / d['max'] * 100:.0f}%" if d["max"] > 0 else "0%",
                "action": _DIMENSION_ACTIONS[d["key"]],
                "urgency": "high" if d["score"] / d["max"] < 0.5 else "medium",
            }
        )
    return actions


# ── 对外主接口 ────────────────────────────────────────────────────────────────


async def calculate_health_score(store_id: str, db: AsyncSession) -> Dict[str, Any]:
    """
    计算私域健康分并返回完整分析报告。

    Returns:
        {
            "store_id":      str,
            "as_of":         ISO datetime,
            "total_score":   float,          # 0-100
            "grade":         {"level", "color", "desc"},
            "dimensions":    [...],           # 5个维度明细
            "top_actions":   [...],           # Top3 行动建议
        }
    """
    dims = await _gather_dims(store_id, db)
    total = round(sum(d["score"] for d in dims), 1)
    grade = _grade(total)
    actions = _top_actions(dims)

    return {
        "store_id": store_id,
        "as_of": datetime.datetime.utcnow().isoformat(),
        "total_score": total,
        "grade": grade,
        "dimensions": dims,
        "top_actions": actions,
    }


async def _gather_dims(store_id: str, db: AsyncSession) -> List[Dict[str, Any]]:
    """顺序执行各维度计算（AsyncSession 不支持真并发）"""
    return [
        await _dim_member_quality(store_id, db),
        await _dim_churn_control(store_id, db),
        await _dim_signal_response(store_id, db),
        await _dim_journey_complete(store_id, db),
        await _dim_growth_momentum(store_id, db),
    ]
