"""菜单优化建议引擎 — Phase 6 Month 2

消费 dish_profitability_records 的 BCG 四象限数据，为每道菜生成
¥量化的优化建议，支撑「成本率降低2个点」目标。

建议类型:
  price_increase — 明星/现金牛菜品具备提价空间
  cost_reduction — 食材成本率偏高，优化 BOM/采购
  promote        — 高毛利低人气菜品需加强推广
  discontinue    — 低效菜品建议下架
  bundle         — 问题菜纳入套餐捆绑提升曝光
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────────────────
REC_TYPES = ["price_increase", "cost_reduction", "promote", "discontinue", "bundle"]

REC_LABELS: dict[str, str] = {
    "price_increase": "提价空间",
    "cost_reduction": "降本优化",
    "promote": "推广增量",
    "discontinue": "建议下架",
    "bundle": "套餐捆绑",
}

REC_TITLES: dict[str, str] = {
    "price_increase": "明星菜品具备提价空间",
    "cost_reduction": "食材成本率偏高需优化",
    "promote": "高毛利菜品需加强推广",
    "discontinue": "低效菜品建议下架",
    "bundle": "建议纳入套餐提升曝光",
}

REC_ACTIONS: dict[str, str] = {
    "price_increase": "建议小幅上调定价5-10%，同步监控复购率与客诉",
    "cost_reduction": "审查BOM配方与采购单价，与供应商重新谈判",
    "promote": "在菜单黄金区域重点展示，搭配限时折扣或套餐推荐",
    "discontinue": "本期末下架此菜，备料预算转移至明星菜",
    "bundle": "将此菜纳入套餐组合，利用明星菜带动曝光",
}

# 提价参数
PRICE_INCREASE_MIN_GPM = 60.0  # 毛利率 ≥ 60% 才建议提价
PRICE_INCREASE_LIFT_PCT = 7.0  # 建议提价幅度 %
PRICE_DEMAND_RETENTION = 0.92  # 提价后保留的需求比例

# 降本参数
COST_REDUCTION_FCR_THRESHOLD = 38.0  # 食材成本率 > 38% 触发降本建议
COST_REDUCTION_TARGET_FCR = 35.0  # 目标食材成本率 %

# 推广参数
PROMOTE_LIFT_PCT = 30.0  # 推广后预期销量提升 %
BUNDLE_LIFT_PCT = 20.0  # 套餐捆绑后预期销量提升 %

# 下架参数（同时满足两条件才触发）
DISCONTINUE_MAX_ORDERS = 15  # 月销量 ≤ N 单
DISCONTINUE_MAX_GPM = 30.0  # 毛利率 ≤ 30%

# 优先级打分
PROFIT_IMPACT_DIVISOR = 500.0  # ¥500 = 1 影响分

# ── 纯函数 ────────────────────────────────────────────────────────────────────


def compute_price_increase_impact(
    avg_selling_price: float,
    order_count: int,
    lift_pct: float = PRICE_INCREASE_LIFT_PCT,
    demand_retention: float = PRICE_DEMAND_RETENTION,
) -> dict:
    """估算小幅提价带来的利润增量。

    profit_delta = 单价提升额 × 留存订单数
    （保守估算：只计入提价带来的额外边际利润，不计入因需求下降的损失）
    """
    if avg_selling_price <= 0 or order_count <= 0:
        return {"revenue_delta": 0.0, "profit_delta": 0.0, "new_price": avg_selling_price}
    new_price = avg_selling_price * (1 + lift_pct / 100)
    new_orders = order_count * demand_retention
    revenue_delta = new_price * new_orders - avg_selling_price * order_count
    # 利润增量 = 单位提价额 × 留存订单数（变动成本不变）
    profit_delta = avg_selling_price * (lift_pct / 100) * new_orders
    return {
        "revenue_delta": round(revenue_delta, 2),
        "profit_delta": round(profit_delta, 2),
        "new_price": round(new_price, 2),
    }


def compute_cost_reduction_impact(
    revenue_yuan: float,
    current_fcr: float,
    target_fcr: float = COST_REDUCTION_TARGET_FCR,
) -> dict:
    """食材成本率从 current_fcr 降至 target_fcr 的¥利润增量。"""
    if revenue_yuan <= 0 or current_fcr <= target_fcr:
        return {"cost_saving": 0.0, "profit_delta": 0.0}
    saving = (current_fcr - target_fcr) / 100.0 * revenue_yuan
    return {"cost_saving": round(saving, 2), "profit_delta": round(saving, 2)}


def compute_promote_impact(
    order_count: int,
    avg_selling_price: float,
    gross_profit_margin: float,
    lift_pct: float = PROMOTE_LIFT_PCT,
) -> dict:
    """推广使销量提升 lift_pct% 带来的¥利润增量。"""
    if order_count <= 0 or avg_selling_price <= 0:
        return {"order_delta": 0, "revenue_delta": 0.0, "profit_delta": 0.0}
    extra_orders = order_count * lift_pct / 100.0
    revenue_delta = extra_orders * avg_selling_price
    profit_delta = revenue_delta * gross_profit_margin / 100.0
    return {
        "order_delta": round(extra_orders),
        "revenue_delta": round(revenue_delta, 2),
        "profit_delta": round(profit_delta, 2),
    }


def compute_discontinue_impact(
    revenue_yuan: float,
    gross_profit_yuan: float,
) -> dict:
    """下架低效菜品的净影响。

    收益：释放厨房产能（估算固定成本节省 ¥300/期）
    损失：该菜品当前毛利（若为负则 0）
    """
    kitchen_savings = 300.0
    lost_profit = max(0.0, gross_profit_yuan)
    profit_delta = kitchen_savings - lost_profit
    return {
        "kitchen_savings": kitchen_savings,
        "lost_profit": round(lost_profit, 2),
        "profit_delta": round(profit_delta, 2),
    }


def compute_bundle_impact(
    order_count: int,
    avg_selling_price: float,
    gross_profit_margin: float,
    lift_pct: float = BUNDLE_LIFT_PCT,
) -> dict:
    """套餐捆绑带来的¥利润增量（保守于 promote）。"""
    return compute_promote_impact(order_count, avg_selling_price, gross_profit_margin, lift_pct)


def compute_priority_score(
    rec_type: str,
    profit_impact_yuan: float,
    confidence_pct: float,
) -> float:
    """优先级评分 0-100。¥影响越大、置信度越高 → 分越高。"""
    impact_score = min(50.0, abs(profit_impact_yuan) / PROFIT_IMPACT_DIVISOR)
    conf_score = min(50.0, confidence_pct * 0.5)
    return min(100.0, round(impact_score + conf_score, 1))


def classify_urgency(priority_score: float) -> str:
    if priority_score >= 70.0:
        return "high"
    if priority_score >= 30.0:
        return "medium"
    return "low"


def generate_rec_description(
    rec_type: str,
    dish_name: str,
    profit_impact: float,
    current_fcr: float,
    current_gpm: float,
    order_count: int,
) -> str:
    """生成不超过 200 字的建议描述。"""
    desc_map = {
        "price_increase": (
            f"{dish_name}属明星菜（人气+毛利双高），毛利率{current_gpm:.1f}%，"
            f"食材成本率{current_fcr:.1f}%，适度提价{PRICE_INCREASE_LIFT_PCT:.0f}%"
            f"预计增利¥{profit_impact:.0f}"
        ),
        "cost_reduction": (
            f"{dish_name}食材成本率{current_fcr:.1f}%偏高，"
            f"通过优化BOM或供应商价格降至{COST_REDUCTION_TARGET_FCR:.0f}%，"
            f"预计增利¥{profit_impact:.0f}"
        ),
        "promote": (
            f"{dish_name}毛利率{current_gpm:.1f}%优秀但月销仅{order_count}次，"
            f"加强推广预计增销{int(order_count * PROMOTE_LIFT_PCT / 100)}次，"
            f"增利¥{profit_impact:.0f}"
        ),
        "discontinue": (
            f"{dish_name}月销{order_count}次、毛利率{current_gpm:.1f}%，" f"下架可释放厨房产能，净增效¥{profit_impact:.0f}"
        ),
        "bundle": (
            f"{dish_name}毛利率{current_gpm:.1f}%高但月销仅{order_count}次，" f"纳入套餐组合预计增利¥{profit_impact:.0f}"
        ),
    }
    return desc_map.get(rec_type, f"{dish_name}优化建议")[:200]


def build_dish_recommendations(dish: dict) -> list[dict]:
    """为单道菜品生成优化建议（最多 2 条，按优先级排序）。

    BCG四象限映射:
      star          → price_increase（若 gpm ≥ 60%）+ cost_reduction（若 fcr > 38%）
      cash_cow      → cost_reduction（若 fcr > 38%）+ price_increase（若 gpm ≥ 40%）
      question_mark → promote + bundle
      dog           → discontinue（若达到下架条件）或 cost_reduction / promote
    """
    quadrant = dish.get("bcg_quadrant", "dog")
    fcr = float(dish.get("food_cost_rate", 0.0) or 0.0)
    gpm = float(dish.get("gross_profit_margin", 0.0) or 0.0)
    cnt = int(dish.get("order_count", 0) or 0)
    price = float(dish.get("avg_selling_price", 0.0) or 0.0)
    revenue = float(dish.get("revenue_yuan", 0.0) or 0.0)
    profit = float(dish.get("gross_profit_yuan", 0.0) or 0.0)
    name = dish.get("dish_name", "")

    def _make(rec_type: str, rev_delta: float, cost_delta: float, profit_delta: float, confidence: float) -> dict:
        score = compute_priority_score(rec_type, profit_delta, confidence)
        return {
            "rec_type": rec_type,
            "title": REC_TITLES[rec_type],
            "action": REC_ACTIONS[rec_type],
            "description": generate_rec_description(rec_type, name, profit_delta, fcr, gpm, cnt),
            "expected_revenue_impact_yuan": round(rev_delta, 2),
            "expected_cost_impact_yuan": round(cost_delta, 2),
            "expected_profit_impact_yuan": round(profit_delta, 2),
            "confidence_pct": confidence,
            "priority_score": score,
            "urgency": classify_urgency(score),
        }

    recs: list[dict] = []

    if quadrant == "star":
        if gpm >= PRICE_INCREASE_MIN_GPM:
            imp = compute_price_increase_impact(price, cnt)
            recs.append(_make("price_increase", imp["revenue_delta"], 0.0, imp["profit_delta"], 75.0))
        if fcr > COST_REDUCTION_FCR_THRESHOLD:
            imp2 = compute_cost_reduction_impact(revenue, fcr)
            recs.append(_make("cost_reduction", 0.0, -imp2["cost_saving"], imp2["profit_delta"], 80.0))

    elif quadrant == "cash_cow":
        if fcr > COST_REDUCTION_FCR_THRESHOLD:
            imp = compute_cost_reduction_impact(revenue, fcr)
            recs.append(_make("cost_reduction", 0.0, -imp["cost_saving"], imp["profit_delta"], 80.0))
        if gpm >= 40.0:
            imp2 = compute_price_increase_impact(price, cnt, lift_pct=5.0)
            recs.append(_make("price_increase", imp2["revenue_delta"], 0.0, imp2["profit_delta"], 60.0))

    elif quadrant == "question_mark":
        imp = compute_promote_impact(cnt, price, gpm)
        imp2 = compute_bundle_impact(cnt, price, gpm)
        recs.append(_make("promote", imp["revenue_delta"], 0.0, imp["profit_delta"], 65.0))
        recs.append(_make("bundle", imp2["revenue_delta"], 0.0, imp2["profit_delta"], 55.0))

    else:  # dog
        if cnt <= DISCONTINUE_MAX_ORDERS and gpm <= DISCONTINUE_MAX_GPM:
            imp = compute_discontinue_impact(revenue, profit)
            recs.append(_make("discontinue", -revenue, 0.0, imp["profit_delta"], 70.0))
        elif fcr > COST_REDUCTION_FCR_THRESHOLD:
            imp = compute_cost_reduction_impact(revenue, fcr)
            recs.append(_make("cost_reduction", 0.0, -imp["cost_saving"], imp["profit_delta"], 65.0))
        else:
            imp = compute_promote_impact(cnt, price, gpm)
            recs.append(_make("promote", imp["revenue_delta"], 0.0, imp["profit_delta"], 45.0))

    # 按优先级降序，最多返回 2 条
    recs.sort(key=lambda r: r["priority_score"], reverse=True)
    return recs[:2]


def summarize_recommendations(records: list[dict]) -> dict:
    """纯函数：聚合建议列表的¥影响和计数。"""
    totals: dict[str, dict] = {rt: {"count": 0, "total_profit_impact_yuan": 0.0, "adopted": 0} for rt in REC_TYPES}
    for r in records:
        rt = r.get("rec_type", "")
        if rt in totals:
            totals[rt]["count"] += 1
            totals[rt]["total_profit_impact_yuan"] += float(r.get("expected_profit_impact_yuan") or 0.0)
            if r.get("status") == "adopted":
                totals[rt]["adopted"] += 1

    total_impact = sum(v["total_profit_impact_yuan"] for v in totals.values())
    pending_count = sum(1 for r in records if r.get("status") == "pending")
    adopted_count = sum(1 for r in records if r.get("status") == "adopted")
    return {
        "by_type": [
            {
                "rec_type": rt,
                "label": REC_LABELS[rt],
                "count": v["count"],
                "total_profit_impact_yuan": round(v["total_profit_impact_yuan"], 2),
                "adopted": v["adopted"],
            }
            for rt, v in totals.items()
        ],
        "total_count": sum(v["count"] for v in totals.values()),
        "total_profit_impact_yuan": round(total_impact, 2),
        "pending_count": pending_count,
        "adopted_count": adopted_count,
    }


# ── DB 辅助 ───────────────────────────────────────────────────────────────────


def _to_float(val) -> float:
    if val is None:
        return 0.0
    try:
        return float(Decimal(str(val)))
    except Exception:
        return 0.0


# ── DB 函数 ───────────────────────────────────────────────────────────────────


async def _fetch_profitability_records(db: AsyncSession, store_id: str, period: str) -> list[dict]:
    sql = text("""
        SELECT
            dish_id, dish_name, category, bcg_quadrant,
            order_count, avg_selling_price,
            revenue_yuan, food_cost_yuan, food_cost_rate,
            gross_profit_yuan, gross_profit_margin,
            popularity_percentile, profit_percentile
        FROM dish_profitability_records
        WHERE store_id = :sid AND period = :period
        ORDER BY gross_profit_yuan DESC
    """)
    result = await db.execute(sql, {"sid": store_id, "period": period})
    rows = result.fetchall()
    keys = [
        "dish_id",
        "dish_name",
        "category",
        "bcg_quadrant",
        "order_count",
        "avg_selling_price",
        "revenue_yuan",
        "food_cost_yuan",
        "food_cost_rate",
        "gross_profit_yuan",
        "gross_profit_margin",
        "popularity_percentile",
        "profit_percentile",
    ]
    return [dict(zip(keys, row)) for row in rows]


async def _upsert_recommendation(db: AsyncSession, store_id: str, period: str, dish: dict, rec: dict) -> None:
    sql = text("""
        INSERT INTO menu_optimization_records (
            store_id, period, dish_id, dish_name, category, bcg_quadrant,
            rec_type, title, description, action,
            expected_revenue_impact_yuan, expected_cost_impact_yuan,
            expected_profit_impact_yuan,
            confidence_pct, priority_score, urgency,
            current_fcr, current_gpm, current_order_count,
            current_avg_price, current_revenue_yuan, current_profit_yuan,
            status, computed_at, updated_at
        ) VALUES (
            :sid, :period, :dish_id, :dish_name, :category, :bcg_quadrant,
            :rec_type, :title, :description, :action,
            :rev_impact, :cost_impact, :profit_impact,
            :confidence, :priority, :urgency,
            :fcr, :gpm, :cnt, :price, :revenue, :profit,
            'pending', NOW(), NOW()
        )
        ON CONFLICT (store_id, period, dish_id, rec_type) DO UPDATE SET
            title                        = EXCLUDED.title,
            description                  = EXCLUDED.description,
            action                       = EXCLUDED.action,
            expected_revenue_impact_yuan = EXCLUDED.expected_revenue_impact_yuan,
            expected_cost_impact_yuan    = EXCLUDED.expected_cost_impact_yuan,
            expected_profit_impact_yuan  = EXCLUDED.expected_profit_impact_yuan,
            confidence_pct               = EXCLUDED.confidence_pct,
            priority_score               = EXCLUDED.priority_score,
            urgency                      = EXCLUDED.urgency,
            current_fcr                  = EXCLUDED.current_fcr,
            current_gpm                  = EXCLUDED.current_gpm,
            current_order_count          = EXCLUDED.current_order_count,
            current_avg_price            = EXCLUDED.current_avg_price,
            current_revenue_yuan         = EXCLUDED.current_revenue_yuan,
            current_profit_yuan          = EXCLUDED.current_profit_yuan,
            updated_at                   = NOW()
        WHERE menu_optimization_records.status = 'pending'
    """)
    await db.execute(
        sql,
        {
            "sid": store_id,
            "period": period,
            "dish_id": dish["dish_id"],
            "dish_name": dish["dish_name"],
            "category": dish.get("category"),
            "bcg_quadrant": dish.get("bcg_quadrant"),
            "rec_type": rec["rec_type"],
            "title": rec["title"],
            "description": rec["description"],
            "action": rec["action"],
            "rev_impact": rec["expected_revenue_impact_yuan"],
            "cost_impact": rec["expected_cost_impact_yuan"],
            "profit_impact": rec["expected_profit_impact_yuan"],
            "confidence": rec["confidence_pct"],
            "priority": rec["priority_score"],
            "urgency": rec["urgency"],
            "fcr": _to_float(dish.get("food_cost_rate")),
            "gpm": _to_float(dish.get("gross_profit_margin")),
            "cnt": dish.get("order_count", 0),
            "price": _to_float(dish.get("avg_selling_price")),
            "revenue": _to_float(dish.get("revenue_yuan")),
            "profit": _to_float(dish.get("gross_profit_yuan")),
        },
    )


async def generate_menu_recommendations(db: AsyncSession, store_id: str, period: str) -> dict:
    """从 dish_profitability_records 读取 BCG 数据，生成并持久化优化建议。幂等操作。"""
    dishes = await _fetch_profitability_records(db, store_id, period)
    if not dishes:
        return {"store_id": store_id, "period": period, "dish_count": 0, "rec_count": 0}

    total_recs = 0
    for dish in dishes:
        # 统一 float 类型（DB 可能返回 Decimal）
        for k in ("food_cost_rate", "gross_profit_margin", "avg_selling_price", "revenue_yuan", "gross_profit_yuan"):
            dish[k] = _to_float(dish.get(k))

        recs = build_dish_recommendations(dish)
        for rec in recs:
            await _upsert_recommendation(db, store_id, period, dish, rec)
            total_recs += 1

    await db.commit()
    return {
        "store_id": store_id,
        "period": period,
        "dish_count": len(dishes),
        "rec_count": total_recs,
    }


# ── 查询辅助 ──────────────────────────────────────────────────────────────────

_REC_SELECT = """
    SELECT
        id, dish_id, dish_name, category, bcg_quadrant,
        rec_type, title, description, action,
        expected_revenue_impact_yuan, expected_cost_impact_yuan,
        expected_profit_impact_yuan,
        confidence_pct, priority_score, urgency,
        current_fcr, current_gpm, current_order_count,
        current_avg_price, current_revenue_yuan, current_profit_yuan,
        status, computed_at
    FROM menu_optimization_records
"""

_REC_KEYS = [
    "id",
    "dish_id",
    "dish_name",
    "category",
    "bcg_quadrant",
    "rec_type",
    "title",
    "description",
    "action",
    "expected_revenue_impact_yuan",
    "expected_cost_impact_yuan",
    "expected_profit_impact_yuan",
    "confidence_pct",
    "priority_score",
    "urgency",
    "current_fcr",
    "current_gpm",
    "current_order_count",
    "current_avg_price",
    "current_revenue_yuan",
    "current_profit_yuan",
    "status",
    "computed_at",
]

_FLOAT_KEYS = {
    "expected_revenue_impact_yuan",
    "expected_cost_impact_yuan",
    "expected_profit_impact_yuan",
    "confidence_pct",
    "priority_score",
    "current_fcr",
    "current_gpm",
    "current_avg_price",
    "current_revenue_yuan",
    "current_profit_yuan",
}


def _parse_rec_rows(rows) -> list[dict]:
    out = []
    for row in rows:
        d = dict(zip(_REC_KEYS, row))
        d["rec_label"] = REC_LABELS.get(d["rec_type"], d["rec_type"])
        for k in _FLOAT_KEYS:
            d[k] = _to_float(d.get(k))
        d["computed_at"] = d["computed_at"].isoformat() if d.get("computed_at") else None
        out.append(d)
    return out


async def get_menu_recommendations(
    db: AsyncSession,
    store_id: str,
    period: str,
    rec_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """查询菜单优化建议，支持按 rec_type 和 status 过滤。"""
    # L011: 条件数量固定（4种组合），用 if/else 选择独立 text() 分支
    if rec_type is not None and status is not None:
        sql = text(
            _REC_SELECT + "WHERE store_id=:sid AND period=:period AND rec_type=:rt AND status=:st "
            "ORDER BY priority_score DESC, expected_profit_impact_yuan DESC LIMIT :lim"
        )
        params = {"sid": store_id, "period": period, "rt": rec_type, "st": status, "lim": limit}
    elif rec_type is not None:
        sql = text(
            _REC_SELECT + "WHERE store_id=:sid AND period=:period AND rec_type=:rt "
            "ORDER BY priority_score DESC, expected_profit_impact_yuan DESC LIMIT :lim"
        )
        params = {"sid": store_id, "period": period, "rt": rec_type, "lim": limit}
    elif status is not None:
        sql = text(
            _REC_SELECT + "WHERE store_id=:sid AND period=:period AND status=:st "
            "ORDER BY priority_score DESC, expected_profit_impact_yuan DESC LIMIT :lim"
        )
        params = {"sid": store_id, "period": period, "st": status, "lim": limit}
    else:
        sql = text(
            _REC_SELECT + "WHERE store_id=:sid AND period=:period "
            "ORDER BY priority_score DESC, expected_profit_impact_yuan DESC LIMIT :lim"
        )
        params = {"sid": store_id, "period": period, "lim": limit}

    result = await db.execute(sql, params)
    return _parse_rec_rows(result.fetchall())


async def get_recommendation_summary(db: AsyncSession, store_id: str, period: str) -> dict:
    """按 rec_type × status 聚合¥影响。"""
    sql = text("""
        SELECT rec_type, status, COUNT(*) AS cnt,
               COALESCE(SUM(expected_profit_impact_yuan), 0) AS total_impact
        FROM menu_optimization_records
        WHERE store_id = :sid AND period = :period
        GROUP BY rec_type, status
    """)
    result = await db.execute(sql, {"sid": store_id, "period": period})
    rows = result.fetchall()

    by_type: dict[str, dict] = {
        rt: {"count": 0, "total_profit_impact_yuan": 0.0, "adopted": 0, "pending": 0} for rt in REC_TYPES
    }
    pending_impact = 0.0
    for row in rows:
        rt, status_val, cnt, impact = row[0], row[1], int(row[2]), _to_float(row[3])
        if rt in by_type:
            by_type[rt]["count"] += cnt
            by_type[rt]["total_profit_impact_yuan"] += impact
            if status_val == "adopted":
                by_type[rt]["adopted"] += cnt
            elif status_val == "pending":
                by_type[rt]["pending"] += cnt
                pending_impact += impact

    return {
        "by_type": [
            {
                "rec_type": rt,
                "label": REC_LABELS[rt],
                **v,
                "total_profit_impact_yuan": round(v["total_profit_impact_yuan"], 2),
            }
            for rt, v in by_type.items()
        ],
        "total_pending_profit_impact_yuan": round(pending_impact, 2),
        "pending_count": sum(v["pending"] for v in by_type.values()),
        "adopted_count": sum(v["adopted"] for v in by_type.values()),
    }


async def update_recommendation_status(db: AsyncSession, rec_id: int, new_status: str) -> dict:
    if new_status not in ("adopted", "dismissed"):
        return {"updated": False, "reason": "invalid_status"}

    if new_status == "adopted":
        sql = text("""
            UPDATE menu_optimization_records
            SET status = 'adopted', adopted_at = NOW(), updated_at = NOW()
            WHERE id = :rid AND status = 'pending'
            RETURNING id
        """)
    else:
        sql = text("""
            UPDATE menu_optimization_records
            SET status = 'dismissed', dismissed_at = NOW(), updated_at = NOW()
            WHERE id = :rid AND status = 'pending'
            RETURNING id
        """)
    result = await db.execute(sql, {"rid": rec_id})
    row = result.fetchone()
    if row:
        await db.commit()
        return {"updated": True, "rec_id": rec_id, "new_status": new_status}
    return {"updated": False, "reason": "not_found_or_not_pending"}


async def get_dish_recommendations(db: AsyncSession, store_id: str, dish_id: str, periods: int = 6) -> list[dict]:
    """查询指定菜品近 N 期的历史优化建议。"""
    sql = text("""
        SELECT period, rec_type, title,
               expected_profit_impact_yuan, confidence_pct,
               priority_score, urgency, status
        FROM menu_optimization_records
        WHERE store_id = :sid AND dish_id = :did
        ORDER BY period DESC
        LIMIT :lim
    """)
    result = await db.execute(sql, {"sid": store_id, "did": dish_id, "lim": periods * 3})
    return [
        {
            "period": row[0],
            "rec_type": row[1],
            "rec_label": REC_LABELS.get(row[1], row[1]),
            "title": row[2],
            "expected_profit_impact_yuan": _to_float(row[3]),
            "confidence_pct": _to_float(row[4]),
            "priority_score": _to_float(row[5]),
            "urgency": row[6],
            "status": row[7],
        }
        for row in result.fetchall()
    ]
