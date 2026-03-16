"""菜品生命周期管理引擎 — Phase 6 Month 6

基于 BCG 象限演变 + 营收/销量趋势，将每道菜归入生命周期阶段，
检测阶段跃迁（phase_changed），生成阶段匹配的¥化行动建议。

阶段定义:
  launch  — 新品（当期首次出现或仅1期数据）
  growth  — 成长期（需求快速增长）
  peak    — 成熟期（稳定高盈利）
  decline — 衰退期（需求/收入下滑）
  exit    — 退出期（持续亏损，建议下架）
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ── 常量 ───────────────────────────────────────────────────────────────────────
PHASES = ["launch", "growth", "peak", "decline", "exit"]

# 趋势阈值（百分比）
GROWTH_ORDER_THRESHOLD = 10.0  # 销量增幅≥10% → 成长信号
DECLINE_REVENUE_THRESHOLD = -5.0  # 营收降幅≥5%  → 衰退信号
DECLINE_REVENUE_STRONG = -10.0  # 问号菜降幅>10% → 衰退
EXIT_REVENUE_THRESHOLD = -20.0  # 营收降幅≥20% + 销量降幅≥20% → 退出
EXIT_ORDER_THRESHOLD = -20.0

# 各阶段¥影响估算系数（相对于当期营收）
PHASE_IMPACT_RATE: dict[str, float] = {
    "launch": 0.20,  # 加速推广可增加 20% 营收
    "growth": 0.05,  # 供应优化节省 5% 成本
    "peak": 0.03,  # 定价效率提升 3%
    "decline": 0.30,  # 重新定位可挽回 30% 衰退量
    "exit": 0.00,  # 退出收益用固定厨房节省代替
}
EXIT_KITCHEN_SAVINGS = 300.0  # ¥/期，退出菜品释放厨房资源

# 各阶段行动建议配置
PHASE_ACTION: dict[str, dict] = {
    "launch": {
        "recommended_action": "accelerate_growth",
        "action_label": "加速推广",
        "action_description": "新品上线期，重点推荐+试吃活动，快速积累口碑与销量",
    },
    "growth": {
        "recommended_action": "expand_presence",
        "action_label": "扩大影响",
        "action_description": "需求快速增长，稳定供货节奏，适当提高曝光与套餐搭配",
    },
    "peak": {
        "recommended_action": "optimize_profitability",
        "action_label": "精细化运营",
        "action_description": "处于成熟期高盈利，聚焦成本精细化与定价效率最大化",
    },
    "decline": {
        "recommended_action": "reposition_or_reduce",
        "action_label": "重新定位/控成本",
        "action_description": "需求下滑，评估调整口味/定价或减少食材备货以延长生命周期",
    },
    "exit": {
        "recommended_action": "plan_exit",
        "action_label": "规划退市",
        "action_description": "持续衰退亏损，建议逐步从菜单下架，释放厨房与备货资源",
    },
}


# ── 纯函数 ─────────────────────────────────────────────────────────────────────


def compute_revenue_trend(current: float, previous: float) -> float:
    """环比营收变化率（%）。previous=0 → 0.0。"""
    if previous == 0:
        return 0.0
    return round((current - previous) / abs(previous) * 100.0, 2)


def compute_order_trend(current: int, previous: int) -> float:
    """环比销量变化率（%）。previous=0 → 0.0。"""
    if previous == 0:
        return 0.0
    return round((current - previous) / abs(previous) * 100.0, 2)


def classify_lifecycle_phase(bcg_quadrant: str, revenue_trend_pct: float, order_trend_pct: float, is_new: bool) -> str:
    """
    基于 BCG 象限 + 环比趋势 + 是否新品，判断生命周期阶段。

    优先级：新品 → 退出 → 衰退 → 成长 → 成熟
    """
    if is_new:
        return "launch"

    # 退出：dog 且营收销量双双暴跌
    if bcg_quadrant == "dog" and revenue_trend_pct <= EXIT_REVENUE_THRESHOLD and order_trend_pct <= EXIT_ORDER_THRESHOLD:
        return "exit"

    # 衰退：dog/cash_cow 营收下滑，或 question_mark 强衰退
    if bcg_quadrant in ("dog", "cash_cow") and revenue_trend_pct < DECLINE_REVENUE_THRESHOLD:
        return "decline"
    if bcg_quadrant == "question_mark" and revenue_trend_pct < DECLINE_REVENUE_STRONG:
        return "decline"

    # 成长：star/question_mark 销量高速增长
    if bcg_quadrant in ("star", "question_mark") and order_trend_pct >= GROWTH_ORDER_THRESHOLD:
        return "growth"

    # 成熟：star/cash_cow 稳定
    if bcg_quadrant in ("star", "cash_cow"):
        return "peak"

    # question_mark 默认 growth（潜力期）
    return "growth"


def detect_phase_transition(current_phase: str, prev_phase: Optional[str]) -> bool:
    """当前阶段与上期阶段不同则视为发生跃迁。prev_phase=None 不算跃迁（首次分析）。"""
    if prev_phase is None:
        return False
    return current_phase != prev_phase


def compute_phase_duration(current_phase: str, prev_phase: Optional[str], prev_duration: int) -> int:
    """
    当前处于本阶段的连续月数。
    同阶段：prev_duration + 1；新阶段：1；无历史：1。
    """
    if prev_phase is None or current_phase != prev_phase:
        return 1
    return prev_duration + 1


def compute_lifecycle_impact(phase: str, revenue_yuan: float, revenue_trend_pct: float) -> float:
    """
    估算采取阶段建议动作的¥潜在收益。
    decline：按衰退量的30%可挽回；exit：固定厨房节省；其余按营收比例。
    """
    if phase == "exit":
        return EXIT_KITCHEN_SAVINGS
    if phase == "decline":
        decline_amount = abs(revenue_trend_pct / 100.0) * revenue_yuan
        return round(decline_amount * PHASE_IMPACT_RATE["decline"], 2)
    return round(revenue_yuan * PHASE_IMPACT_RATE.get(phase, 0.0), 2)


def compute_lifecycle_confidence(phase: str, phase_duration_months: int, order_count: int) -> float:
    """
    置信度（0~90）。阶段稳定时间越长、销量越大越可信。
    launch 阶段数据少，置信度固定较低。
    """
    if phase == "launch":
        return 50.0
    base = min(70.0, 40.0 + phase_duration_months * 5.0)
    if order_count >= 100:
        base = min(90.0, base + 15.0)
    elif order_count >= 50:
        base = min(90.0, base + 8.0)
    return base


def build_lifecycle_record(
    store_id: str, period: str, current: dict, prev: Optional[dict], prev_lifecycle: Optional[dict]
) -> dict:
    """
    为单道菜构造完整生命周期记录。

    current/prev 来自 dish_profitability_records。
    prev_lifecycle 来自上期 dish_lifecycle_records（可为 None）。
    """
    is_new = prev is None
    rev_trend = compute_revenue_trend(
        float(current.get("revenue_yuan") or 0),
        float(prev["revenue_yuan"]) if prev else 0,
    )
    order_trend = compute_order_trend(
        int(current.get("order_count") or 0),
        int(prev["order_count"]) if prev else 0,
    )
    fcr_trend = round(
        float(current.get("food_cost_rate") or 0)
        - float(prev["food_cost_rate"] if prev else current.get("food_cost_rate") or 0),
        2,
    )

    bcg = current.get("bcg_quadrant") or "unknown"
    phase = classify_lifecycle_phase(bcg, rev_trend, order_trend, is_new)

    prev_phase = prev_lifecycle.get("phase") if prev_lifecycle else None
    prev_dur = int(prev_lifecycle.get("phase_duration_months") or 0) if prev_lifecycle else 0
    changed = detect_phase_transition(phase, prev_phase)
    duration = compute_phase_duration(phase, prev_phase, prev_dur)

    revenue_yuan = float(current.get("revenue_yuan") or 0)
    impact = compute_lifecycle_impact(phase, revenue_yuan, rev_trend)
    confidence = compute_lifecycle_confidence(phase, duration, int(current.get("order_count") or 0))

    action = PHASE_ACTION[phase]

    return {
        "store_id": store_id,
        "period": period,
        "dish_id": current["dish_id"],
        "dish_name": current["dish_name"],
        "category": current.get("category"),
        "bcg_quadrant": bcg,
        "order_count": int(current.get("order_count") or 0),
        "revenue_yuan": revenue_yuan,
        "gross_profit_margin": float(current.get("gross_profit_margin") or 0),
        "food_cost_rate": float(current.get("food_cost_rate") or 0),
        "revenue_trend_pct": rev_trend,
        "order_trend_pct": order_trend,
        "fcr_trend_pp": fcr_trend,
        "phase": phase,
        "prev_phase": prev_phase,
        "phase_changed": changed,
        "phase_duration_months": duration,
        "recommended_action": action["recommended_action"],
        "action_label": action["action_label"],
        "action_description": action["action_description"],
        "expected_impact_yuan": impact,
        "confidence_pct": confidence,
    }


# ── 期间辅助 ───────────────────────────────────────────────────────────────────


def _prev_period(period: str) -> str:
    year, month = int(period[:4]), int(period[5:7])
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


def _start_period(period: str, n: int) -> str:
    year, month = int(period[:4]), int(period[5:7])
    total = year * 12 + (month - 1) - (n - 1)
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


# ── 数据库函数 ──────────────────────────────────────────────────────────────────


async def _fetch_profitability(db: AsyncSession, store_id: str, period: str) -> list[dict]:
    """从 dish_profitability_records 拉取该期所有菜品快照。"""
    sql = text("""
        SELECT dish_id, dish_name, category, bcg_quadrant,
               order_count, revenue_yuan, gross_profit_margin, food_cost_rate
        FROM dish_profitability_records
        WHERE store_id = :store_id AND period = :period
    """)
    rows = (await db.execute(sql, {"store_id": store_id, "period": period})).fetchall()
    return [
        {
            "dish_id": r[0],
            "dish_name": r[1],
            "category": r[2],
            "bcg_quadrant": r[3],
            "order_count": int(r[4] or 0),
            "revenue_yuan": float(r[5] or 0),
            "gross_profit_margin": float(r[6] or 0),
            "food_cost_rate": float(r[7] or 0),
        }
        for r in rows
    ]


async def _fetch_prev_lifecycles(db: AsyncSession, store_id: str, period: str) -> dict[str, dict]:
    """拉取上期所有菜品的生命周期记录，返回 {dish_id: record}。"""
    prev = _prev_period(period)
    sql = text("""
        SELECT dish_id, phase, phase_duration_months
        FROM dish_lifecycle_records
        WHERE store_id = :store_id AND period = :period
    """)
    rows = (await db.execute(sql, {"store_id": store_id, "period": prev})).fetchall()
    return {r[0]: {"phase": r[1], "phase_duration_months": int(r[2] or 1)} for r in rows}


async def _upsert_lifecycle_record(db: AsyncSession, rec: dict) -> None:
    """幂等写入，全量覆盖。"""
    sql = text("""
        INSERT INTO dish_lifecycle_records (
            store_id, period, dish_id, dish_name, category, bcg_quadrant,
            order_count, revenue_yuan, gross_profit_margin, food_cost_rate,
            revenue_trend_pct, order_trend_pct, fcr_trend_pp,
            phase, prev_phase, phase_changed, phase_duration_months,
            recommended_action, action_label, action_description,
            expected_impact_yuan, confidence_pct,
            computed_at, updated_at
        ) VALUES (
            :store_id, :period, :dish_id, :dish_name, :category, :bcg_quadrant,
            :order_count, :revenue_yuan, :gross_profit_margin, :food_cost_rate,
            :revenue_trend_pct, :order_trend_pct, :fcr_trend_pp,
            :phase, :prev_phase, :phase_changed, :phase_duration_months,
            :recommended_action, :action_label, :action_description,
            :expected_impact_yuan, :confidence_pct,
            NOW(), NOW()
        )
        ON CONFLICT (store_id, period, dish_id) DO UPDATE SET
            dish_name              = EXCLUDED.dish_name,
            category               = EXCLUDED.category,
            bcg_quadrant           = EXCLUDED.bcg_quadrant,
            order_count            = EXCLUDED.order_count,
            revenue_yuan           = EXCLUDED.revenue_yuan,
            gross_profit_margin    = EXCLUDED.gross_profit_margin,
            food_cost_rate         = EXCLUDED.food_cost_rate,
            revenue_trend_pct      = EXCLUDED.revenue_trend_pct,
            order_trend_pct        = EXCLUDED.order_trend_pct,
            fcr_trend_pp           = EXCLUDED.fcr_trend_pp,
            phase                  = EXCLUDED.phase,
            prev_phase             = EXCLUDED.prev_phase,
            phase_changed          = EXCLUDED.phase_changed,
            phase_duration_months  = EXCLUDED.phase_duration_months,
            recommended_action     = EXCLUDED.recommended_action,
            action_label           = EXCLUDED.action_label,
            action_description     = EXCLUDED.action_description,
            expected_impact_yuan   = EXCLUDED.expected_impact_yuan,
            confidence_pct         = EXCLUDED.confidence_pct,
            updated_at             = NOW()
    """)
    await db.execute(sql, rec)


async def compute_lifecycle_analysis(db: AsyncSession, store_id: str, period: str) -> dict:
    """
    门店当期生命周期分析主入口。幂等。
    返回 {dish_count, phase_counts, transition_count, total_impact_yuan}
    """
    current_list = await _fetch_profitability(db, store_id, period)
    if not current_list:
        await db.commit()
        return {
            "store_id": store_id,
            "period": period,
            "dish_count": 0,
            "phase_counts": {},
            "transition_count": 0,
            "total_impact_yuan": 0.0,
        }

    prev_period = _prev_period(period)
    prev_list = await _fetch_profitability(db, store_id, prev_period)
    prev_by_id = {d["dish_id"]: d for d in prev_list}
    prev_lifecycles = await _fetch_prev_lifecycles(db, store_id, period)

    phase_counts: dict[str, int] = {p: 0 for p in PHASES}
    transition_count = 0
    total_impact = 0.0

    for dish in current_list:
        prev_dish = prev_by_id.get(dish["dish_id"])
        prev_lc = prev_lifecycles.get(dish["dish_id"])
        rec = build_lifecycle_record(store_id, period, dish, prev_dish, prev_lc)
        await _upsert_lifecycle_record(db, rec)
        phase_counts[rec["phase"]] = phase_counts.get(rec["phase"], 0) + 1
        if rec["phase_changed"]:
            transition_count += 1
        total_impact += rec["expected_impact_yuan"]

    await db.commit()
    return {
        "store_id": store_id,
        "period": period,
        "dish_count": len(current_list),
        "phase_counts": phase_counts,
        "transition_count": transition_count,
        "total_impact_yuan": round(total_impact, 2),
    }


async def get_lifecycle_records(
    db: AsyncSession, store_id: str, period: str, phase: Optional[str] = None, limit: int = 100
) -> list[dict]:
    """
    查询门店当期生命周期记录，可按阶段过滤。
    L011合规：两路 text() 分支。
    """
    if phase:
        sql = text("""
            SELECT id, dish_id, dish_name, category, bcg_quadrant,
                   order_count, revenue_yuan, gross_profit_margin, food_cost_rate,
                   revenue_trend_pct, order_trend_pct, fcr_trend_pp,
                   phase, prev_phase, phase_changed, phase_duration_months,
                   recommended_action, action_label, action_description,
                   expected_impact_yuan, confidence_pct
            FROM dish_lifecycle_records
            WHERE store_id = :store_id AND period = :period AND phase = :phase
            ORDER BY expected_impact_yuan DESC
            LIMIT :limit
        """)
        params = {"store_id": store_id, "period": period, "phase": phase, "limit": limit}
    else:
        sql = text("""
            SELECT id, dish_id, dish_name, category, bcg_quadrant,
                   order_count, revenue_yuan, gross_profit_margin, food_cost_rate,
                   revenue_trend_pct, order_trend_pct, fcr_trend_pp,
                   phase, prev_phase, phase_changed, phase_duration_months,
                   recommended_action, action_label, action_description,
                   expected_impact_yuan, confidence_pct
            FROM dish_lifecycle_records
            WHERE store_id = :store_id AND period = :period
            ORDER BY phase, expected_impact_yuan DESC
            LIMIT :limit
        """)
        params = {"store_id": store_id, "period": period, "limit": limit}

    rows = (await db.execute(sql, params)).fetchall()
    cols = [
        "id",
        "dish_id",
        "dish_name",
        "category",
        "bcg_quadrant",
        "order_count",
        "revenue_yuan",
        "gross_profit_margin",
        "food_cost_rate",
        "revenue_trend_pct",
        "order_trend_pct",
        "fcr_trend_pp",
        "phase",
        "prev_phase",
        "phase_changed",
        "phase_duration_months",
        "recommended_action",
        "action_label",
        "action_description",
        "expected_impact_yuan",
        "confidence_pct",
    ]
    return [dict(zip(cols, r)) for r in rows]


async def get_lifecycle_summary(db: AsyncSession, store_id: str, period: str) -> dict:
    """按阶段聚合：菜品数、总¥影响、平均阶段时长、跃迁数。"""
    sql = text("""
        SELECT
            phase,
            COUNT(*)                                        AS dish_count,
            COUNT(*) FILTER (WHERE phase_changed = true)    AS transition_count,
            SUM(expected_impact_yuan)                       AS total_impact,
            AVG(phase_duration_months)                      AS avg_duration,
            AVG(revenue_trend_pct)                          AS avg_rev_trend,
            SUM(revenue_yuan)                               AS total_revenue
        FROM dish_lifecycle_records
        WHERE store_id = :store_id AND period = :period
        GROUP BY phase
        ORDER BY phase
    """)
    rows = (await db.execute(sql, {"store_id": store_id, "period": period})).fetchall()

    by_phase = []
    total_dishes = 0
    total_impact = 0.0
    total_transitions = 0

    for r in rows:
        item = {
            "phase": r[0],
            "dish_count": int(r[1]),
            "transition_count": int(r[2]),
            "total_impact": float(r[3] or 0),
            "avg_duration": float(r[4] or 0),
            "avg_rev_trend": float(r[5] or 0),
            "total_revenue": float(r[6] or 0),
            "action_label": PHASE_ACTION[r[0]]["action_label"] if r[0] in PHASE_ACTION else r[0],
        }
        by_phase.append(item)
        total_dishes += item["dish_count"]
        total_impact += item["total_impact"]
        total_transitions += item["transition_count"]

    return {
        "store_id": store_id,
        "period": period,
        "total_dishes": total_dishes,
        "total_transitions": total_transitions,
        "by_phase": by_phase,
        "total_impact_yuan": round(total_impact, 2),
    }


async def get_phase_transition_alerts(db: AsyncSession, store_id: str, period: str) -> list[dict]:
    """返回本期发生阶段跃迁的菜品，按期望¥影响降序——需要重点关注。"""
    sql = text("""
        SELECT dish_id, dish_name, category, bcg_quadrant,
               prev_phase, phase, phase_duration_months,
               revenue_trend_pct, order_trend_pct,
               revenue_yuan, expected_impact_yuan,
               action_label, action_description
        FROM dish_lifecycle_records
        WHERE store_id = :store_id AND period = :period AND phase_changed = true
        ORDER BY expected_impact_yuan DESC
    """)
    rows = (await db.execute(sql, {"store_id": store_id, "period": period})).fetchall()
    cols = [
        "dish_id",
        "dish_name",
        "category",
        "bcg_quadrant",
        "prev_phase",
        "phase",
        "phase_duration_months",
        "revenue_trend_pct",
        "order_trend_pct",
        "revenue_yuan",
        "expected_impact_yuan",
        "action_label",
        "action_description",
    ]
    return [dict(zip(cols, r)) for r in rows]


async def get_dish_lifecycle_history(db: AsyncSession, store_id: str, dish_id: str, periods: int = 12) -> list[dict]:
    """某道菜近 N 期的生命周期演变历史。"""
    sql = text("""
        SELECT period, bcg_quadrant, phase, prev_phase, phase_changed,
               phase_duration_months, revenue_yuan, order_count,
               revenue_trend_pct, order_trend_pct,
               action_label, expected_impact_yuan
        FROM dish_lifecycle_records
        WHERE store_id = :store_id AND dish_id = :dish_id
        ORDER BY period DESC
        LIMIT :periods
    """)
    rows = (await db.execute(sql, {"store_id": store_id, "dish_id": dish_id, "periods": periods})).fetchall()
    cols = [
        "period",
        "bcg_quadrant",
        "phase",
        "prev_phase",
        "phase_changed",
        "phase_duration_months",
        "revenue_yuan",
        "order_count",
        "revenue_trend_pct",
        "order_trend_pct",
        "action_label",
        "expected_impact_yuan",
    ]
    return [dict(zip(cols, r)) for r in rows]
