"""菜品智能定价引擎 — Phase 6 Month 5

基于 BCG 象限 + 需求弹性 + 食材成本率，为每道菜生成具体售价调整建议，
量化预期收入/利润 ¥ 变化，支持采纳/忽略状态跟踪。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ── 常量 ───────────────────────────────────────────────────────────────────────
REC_ACTIONS = ["increase", "decrease", "maintain"]
ELASTICITY_CLASSES = ["inelastic", "moderate", "elastic"]
STATUSES = ["pending", "adopted", "dismissed"]

# 提价幅度
STAR_PRICE_LIFT_PCT = 8.0  # 明星菜提价 8%
CASH_COW_PRICE_LIFT_PCT = 5.0  # 金牛菜提价 5%
HIGH_FCR_PRICE_LIFT_PCT = 6.0  # 高成本率菜提价保利润 6%
QUESTION_MARK_PRICE_DROP_PCT = -8.0  # 问号菜降价刺激销量 8%

# 触发条件
MIN_GPM_FOR_STAR_INCREASE = 55.0  # 明星菜 GPM≥55% 才建议提价
MIN_GPM_FOR_COW_INCREASE = 45.0  # 金牛菜 GPM≥45%
MAX_ORDERS_FOR_QM_DECREASE = 30  # 问号菜销量<30 单才建议降价
FCR_HIGH_THRESHOLD = 42.0  # 成本率>42% 视为偏高

# 弹性对应的需求变化系数
DEMAND_RETENTION: dict[str, float] = {
    "inelastic": 0.95,  # 提价后客单数保留 95%
    "moderate": 0.88,
    "elastic": 0.80,
}
DEMAND_BOOST: dict[str, float] = {
    "inelastic": 1.08,  # 降价后客单数增幅 8%
    "moderate": 1.15,
    "elastic": 1.20,
}


# ── 纯函数 ─────────────────────────────────────────────────────────────────────


def classify_price_elasticity(bcg_quadrant: str, order_count: int, store_avg_order_count: float) -> str:
    """
    基于 BCG 象限和销量判断需求弹性。
    star/cash_cow → inelastic；dog → elastic；
    question_mark: 销量高于全店均值 120% → inelastic，否则 moderate。
    """
    if bcg_quadrant in ("star", "cash_cow"):
        return "inelastic"
    if bcg_quadrant == "dog":
        return "elastic"
    # question_mark
    if store_avg_order_count > 0 and order_count >= store_avg_order_count * 1.2:
        return "inelastic"
    return "moderate"


def compute_price_recommendation(dish: dict) -> Optional[dict]:
    """
    根据 BCG 象限 / GPM / FCR / 销量给出 rec_action + suggested_price + price_change_pct。
    返回 None 表示建议维持现价（maintain）。

    dish 必须包含: bcg_quadrant, food_cost_rate, gross_profit_margin,
                   order_count, current_price
    """
    bcg = dish["bcg_quadrant"]
    fcr = float(dish.get("food_cost_rate") or 0)
    gpm = float(dish.get("gross_profit_margin") or 0)
    cnt = int(dish.get("order_count") or 0)
    price = float(dish.get("current_price") or 0)

    if price <= 0:
        return None

    # 明星菜高毛利 → 提价
    if bcg == "star" and gpm >= MIN_GPM_FOR_STAR_INCREASE:
        lift = STAR_PRICE_LIFT_PCT
        return {
            "rec_action": "increase",
            "suggested_price": round(price * (1 + lift / 100), 1),
            "price_change_pct": lift,
            "reasoning": f"明星菜毛利率{gpm:.1f}%，需求稳健，可提价{lift:.0f}%",
        }

    # 金牛菜高毛利 → 小幅提价
    if bcg == "cash_cow" and gpm >= MIN_GPM_FOR_COW_INCREASE:
        lift = CASH_COW_PRICE_LIFT_PCT
        return {
            "rec_action": "increase",
            "suggested_price": round(price * (1 + lift / 100), 1),
            "price_change_pct": lift,
            "reasoning": f"金牛菜客群稳定，小幅提价{lift:.0f}%不影响销量",
        }

    # 问号菜销量低 → 降价刺激转化
    if bcg == "question_mark" and cnt < MAX_ORDERS_FOR_QM_DECREASE:
        drop = QUESTION_MARK_PRICE_DROP_PCT  # 负数
        return {
            "rec_action": "decrease",
            "suggested_price": round(price * (1 + drop / 100), 1),
            "price_change_pct": drop,
            "reasoning": f"问号菜销量仅{cnt}单，降价{abs(drop):.0f}%刺激需求转化",
        }

    # 食材成本率偏高 → 提价保利润
    if fcr >= FCR_HIGH_THRESHOLD:
        lift = HIGH_FCR_PRICE_LIFT_PCT
        return {
            "rec_action": "increase",
            "suggested_price": round(price * (1 + lift / 100), 1),
            "price_change_pct": lift,
            "reasoning": f"食材成本率{fcr:.1f}%偏高，提价{lift:.0f}%保护毛利",
        }

    return None


def compute_demand_change(current_orders: int, price_change_pct: float, elasticity_class: str) -> float:
    """预测价格变动后的期望销量。"""
    if price_change_pct > 0:
        return round(current_orders * DEMAND_RETENTION.get(elasticity_class, 0.88), 1)
    if price_change_pct < 0:
        return round(current_orders * DEMAND_BOOST.get(elasticity_class, 1.15), 1)
    return float(current_orders)


def compute_revenue_delta(current_price: float, suggested_price: float, current_orders: int, expected_orders: float) -> float:
    """预期营收变化 = 新营收 - 旧营收。"""
    return round(suggested_price * expected_orders - current_price * current_orders, 2)


def compute_profit_delta(revenue_delta: float, gross_profit_margin: float) -> float:
    """预期利润变化 ≈ 营收变化 × 毛利率（简化：成本结构不变）。"""
    return round(revenue_delta * gross_profit_margin / 100.0, 2)


def compute_pricing_confidence(bcg_quadrant: str, order_count: int, rec_action: str) -> float:
    """
    置信度（0~95）。维持建议最确定；明星/金牛+大销量最高；低销量或dog最低。
    """
    if rec_action == "maintain":
        return 90.0
    if bcg_quadrant in ("star", "cash_cow") and order_count >= 50:
        return 85.0
    if bcg_quadrant in ("star", "cash_cow"):
        return 70.0
    if bcg_quadrant == "question_mark" and order_count >= 30:
        return 60.0
    return 45.0


def build_pricing_record(store_id: str, period: str, dish: dict, store_avg_order_count: float) -> dict:
    """
    为单道菜构造完整的定价建议记录。
    dish 来自 _fetch_dishes_for_pricing，包含所有 dish_profitability_records 字段。
    """
    current_price = float(dish.get("avg_selling_price") or 0)
    order_count = int(dish.get("order_count") or 0)
    bcg = dish.get("bcg_quadrant") or "unknown"
    gpm = float(dish.get("gross_profit_margin") or 0)

    rec = compute_price_recommendation(
        {
            "bcg_quadrant": bcg,
            "food_cost_rate": dish.get("food_cost_rate"),
            "gross_profit_margin": gpm,
            "order_count": order_count,
            "current_price": current_price,
        }
    )

    if rec is None:
        rec = {
            "rec_action": "maintain",
            "suggested_price": current_price,
            "price_change_pct": 0.0,
            "reasoning": "当前定价合理，无需调整",
        }

    elasticity = classify_price_elasticity(bcg, order_count, store_avg_order_count)
    expected_cnt = compute_demand_change(order_count, rec["price_change_pct"], elasticity)
    rev_delta = compute_revenue_delta(current_price, rec["suggested_price"], order_count, expected_cnt)
    profit_delta = compute_profit_delta(rev_delta, gpm)
    confidence = compute_pricing_confidence(bcg, order_count, rec["rec_action"])

    return {
        "store_id": store_id,
        "period": period,
        "dish_id": dish["dish_id"],
        "dish_name": dish["dish_name"],
        "category": dish.get("category"),
        "bcg_quadrant": bcg,
        "current_price": current_price,
        "order_count": order_count,
        "revenue_yuan": float(dish.get("revenue_yuan") or 0),
        "gross_profit_margin": gpm,
        "food_cost_rate": float(dish.get("food_cost_rate") or 0),
        "rec_action": rec["rec_action"],
        "suggested_price": rec["suggested_price"],
        "price_change_pct": rec["price_change_pct"],
        "elasticity_class": elasticity,
        "expected_order_count": expected_cnt,
        "expected_revenue_delta_yuan": rev_delta,
        "expected_profit_delta_yuan": profit_delta,
        "confidence_pct": confidence,
        "reasoning": rec["reasoning"],
    }


# ── 期间辅助 ───────────────────────────────────────────────────────────────────


def _start_period(period: str, n: int) -> str:
    year, month = int(period[:4]), int(period[5:7])
    total = year * 12 + (month - 1) - (n - 1)
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


# ── 数据库函数 ──────────────────────────────────────────────────────────────────


async def _fetch_dishes_for_pricing(db: AsyncSession, store_id: str, period: str) -> list[dict]:
    """从 dish_profitability_records 拉取本店当期所有菜品盈利快照。"""
    sql = text("""
        SELECT dish_id, dish_name, category, bcg_quadrant,
               avg_selling_price, order_count, revenue_yuan,
               gross_profit_margin, food_cost_rate
        FROM dish_profitability_records
        WHERE store_id = :store_id AND period = :period
        ORDER BY revenue_yuan DESC
    """)
    rows = (await db.execute(sql, {"store_id": store_id, "period": period})).fetchall()
    return [
        {
            "dish_id": r[0],
            "dish_name": r[1],
            "category": r[2],
            "bcg_quadrant": r[3],
            "avg_selling_price": float(r[4] or 0),
            "order_count": int(r[5] or 0),
            "revenue_yuan": float(r[6] or 0),
            "gross_profit_margin": float(r[7] or 0),
            "food_cost_rate": float(r[8] or 0),
        }
        for r in rows
    ]


async def _upsert_pricing_record(db: AsyncSession, rec: dict) -> None:
    """幂等写入：ON CONFLICT 只覆盖 status='pending' 的行（保留已采纳/忽略的决策）。"""
    sql = text("""
        INSERT INTO dish_pricing_records (
            store_id, period, dish_id, dish_name, category, bcg_quadrant,
            current_price, order_count, revenue_yuan,
            gross_profit_margin, food_cost_rate,
            rec_action, suggested_price, price_change_pct, elasticity_class,
            expected_order_count, expected_revenue_delta_yuan,
            expected_profit_delta_yuan, confidence_pct, reasoning,
            status, computed_at, updated_at
        ) VALUES (
            :store_id, :period, :dish_id, :dish_name, :category, :bcg_quadrant,
            :current_price, :order_count, :revenue_yuan,
            :gross_profit_margin, :food_cost_rate,
            :rec_action, :suggested_price, :price_change_pct, :elasticity_class,
            :expected_order_count, :expected_revenue_delta_yuan,
            :expected_profit_delta_yuan, :confidence_pct, :reasoning,
            'pending', NOW(), NOW()
        )
        ON CONFLICT (store_id, period, dish_id) DO UPDATE SET
            dish_name              = EXCLUDED.dish_name,
            category               = EXCLUDED.category,
            bcg_quadrant           = EXCLUDED.bcg_quadrant,
            current_price          = EXCLUDED.current_price,
            order_count            = EXCLUDED.order_count,
            revenue_yuan           = EXCLUDED.revenue_yuan,
            gross_profit_margin    = EXCLUDED.gross_profit_margin,
            food_cost_rate         = EXCLUDED.food_cost_rate,
            rec_action             = EXCLUDED.rec_action,
            suggested_price        = EXCLUDED.suggested_price,
            price_change_pct       = EXCLUDED.price_change_pct,
            elasticity_class       = EXCLUDED.elasticity_class,
            expected_order_count   = EXCLUDED.expected_order_count,
            expected_revenue_delta_yuan = EXCLUDED.expected_revenue_delta_yuan,
            expected_profit_delta_yuan  = EXCLUDED.expected_profit_delta_yuan,
            confidence_pct         = EXCLUDED.confidence_pct,
            reasoning              = EXCLUDED.reasoning,
            updated_at             = NOW()
        WHERE dish_pricing_records.status = 'pending'
    """)
    await db.execute(sql, rec)


async def generate_pricing_recommendations(db: AsyncSession, store_id: str, period: str) -> dict:
    """
    为门店当期所有菜品生成定价建议。幂等，保留已采纳/忽略的记录。
    返回 {dish_count, increase_count, decrease_count, maintain_count,
           total_revenue_delta_yuan, total_profit_delta_yuan}
    """
    dishes = await _fetch_dishes_for_pricing(db, store_id, period)
    if not dishes:
        await db.commit()
        return {
            "store_id": store_id,
            "period": period,
            "dish_count": 0,
            "increase_count": 0,
            "decrease_count": 0,
            "maintain_count": 0,
            "total_revenue_delta_yuan": 0.0,
            "total_profit_delta_yuan": 0.0,
        }

    avg_orders = sum(d["order_count"] for d in dishes) / len(dishes)

    counts = {"increase": 0, "decrease": 0, "maintain": 0}
    total_rev_delta = 0.0
    total_profit_delta = 0.0

    for dish in dishes:
        rec = build_pricing_record(store_id, period, dish, avg_orders)
        await _upsert_pricing_record(db, rec)
        counts[rec["rec_action"]] += 1
        total_rev_delta += rec["expected_revenue_delta_yuan"]
        total_profit_delta += rec["expected_profit_delta_yuan"]

    await db.commit()
    return {
        "store_id": store_id,
        "period": period,
        "dish_count": len(dishes),
        "increase_count": counts["increase"],
        "decrease_count": counts["decrease"],
        "maintain_count": counts["maintain"],
        "total_revenue_delta_yuan": round(total_rev_delta, 2),
        "total_profit_delta_yuan": round(total_profit_delta, 2),
    }


async def get_pricing_recommendations(
    db: AsyncSession,
    store_id: str,
    period: str,
    rec_action: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """
    查询定价建议列表，支持 rec_action + status 双重过滤。
    L011合规：4路 text() 分支。
    """
    if rec_action and status:
        sql = text("""
            SELECT id, dish_id, dish_name, category, bcg_quadrant,
                   current_price, order_count, revenue_yuan,
                   gross_profit_margin, food_cost_rate,
                   rec_action, suggested_price, price_change_pct, elasticity_class,
                   expected_order_count, expected_revenue_delta_yuan,
                   expected_profit_delta_yuan, confidence_pct, reasoning,
                   status, adopted_price, adopted_at, dismissed_at
            FROM dish_pricing_records
            WHERE store_id = :store_id AND period = :period
              AND rec_action = :rec_action AND status = :status
            ORDER BY expected_profit_delta_yuan DESC
            LIMIT :limit
        """)
        params = {"store_id": store_id, "period": period, "rec_action": rec_action, "status": status, "limit": limit}
    elif rec_action:
        sql = text("""
            SELECT id, dish_id, dish_name, category, bcg_quadrant,
                   current_price, order_count, revenue_yuan,
                   gross_profit_margin, food_cost_rate,
                   rec_action, suggested_price, price_change_pct, elasticity_class,
                   expected_order_count, expected_revenue_delta_yuan,
                   expected_profit_delta_yuan, confidence_pct, reasoning,
                   status, adopted_price, adopted_at, dismissed_at
            FROM dish_pricing_records
            WHERE store_id = :store_id AND period = :period
              AND rec_action = :rec_action
            ORDER BY expected_profit_delta_yuan DESC
            LIMIT :limit
        """)
        params = {"store_id": store_id, "period": period, "rec_action": rec_action, "limit": limit}
    elif status:
        sql = text("""
            SELECT id, dish_id, dish_name, category, bcg_quadrant,
                   current_price, order_count, revenue_yuan,
                   gross_profit_margin, food_cost_rate,
                   rec_action, suggested_price, price_change_pct, elasticity_class,
                   expected_order_count, expected_revenue_delta_yuan,
                   expected_profit_delta_yuan, confidence_pct, reasoning,
                   status, adopted_price, adopted_at, dismissed_at
            FROM dish_pricing_records
            WHERE store_id = :store_id AND period = :period
              AND status = :status
            ORDER BY expected_profit_delta_yuan DESC
            LIMIT :limit
        """)
        params = {"store_id": store_id, "period": period, "status": status, "limit": limit}
    else:
        sql = text("""
            SELECT id, dish_id, dish_name, category, bcg_quadrant,
                   current_price, order_count, revenue_yuan,
                   gross_profit_margin, food_cost_rate,
                   rec_action, suggested_price, price_change_pct, elasticity_class,
                   expected_order_count, expected_revenue_delta_yuan,
                   expected_profit_delta_yuan, confidence_pct, reasoning,
                   status, adopted_price, adopted_at, dismissed_at
            FROM dish_pricing_records
            WHERE store_id = :store_id AND period = :period
            ORDER BY expected_profit_delta_yuan DESC
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
        "current_price",
        "order_count",
        "revenue_yuan",
        "gross_profit_margin",
        "food_cost_rate",
        "rec_action",
        "suggested_price",
        "price_change_pct",
        "elasticity_class",
        "expected_order_count",
        "expected_revenue_delta_yuan",
        "expected_profit_delta_yuan",
        "confidence_pct",
        "reasoning",
        "status",
        "adopted_price",
        "adopted_at",
        "dismissed_at",
    ]
    return [dict(zip(cols, r)) for r in rows]


async def get_pricing_summary(db: AsyncSession, store_id: str, period: str) -> dict:
    """按 rec_action 和 status 聚合定价建议统计。"""
    sql = text("""
        SELECT
            rec_action,
            COUNT(*)                                       AS total,
            COUNT(*) FILTER (WHERE status = 'pending')    AS pending,
            COUNT(*) FILTER (WHERE status = 'adopted')    AS adopted,
            COUNT(*) FILTER (WHERE status = 'dismissed')  AS dismissed,
            SUM(expected_revenue_delta_yuan)               AS total_rev_delta,
            SUM(expected_profit_delta_yuan)                AS total_profit_delta,
            AVG(confidence_pct)                            AS avg_confidence
        FROM dish_pricing_records
        WHERE store_id = :store_id AND period = :period
        GROUP BY rec_action
        ORDER BY rec_action
    """)
    rows = (await db.execute(sql, {"store_id": store_id, "period": period})).fetchall()

    by_action = []
    total_rev = 0.0
    total_profit = 0.0
    total_dishes = 0
    total_adopted = 0

    for r in rows:
        item = {
            "rec_action": r[0],
            "total": int(r[1]),
            "pending": int(r[2]),
            "adopted": int(r[3]),
            "dismissed": int(r[4]),
            "total_rev_delta": float(r[5] or 0),
            "total_profit_delta": float(r[6] or 0),
            "avg_confidence": float(r[7] or 0),
        }
        by_action.append(item)
        total_rev += item["total_rev_delta"]
        total_profit += item["total_profit_delta"]
        total_dishes += item["total"]
        total_adopted += item["adopted"]

    return {
        "store_id": store_id,
        "period": period,
        "total_dishes": total_dishes,
        "total_adopted": total_adopted,
        "adoption_rate": round(total_adopted / total_dishes * 100, 1) if total_dishes else 0.0,
        "by_action": by_action,
        "total_rev_delta_yuan": round(total_rev, 2),
        "total_profit_delta_yuan": round(total_profit, 2),
    }


async def update_pricing_status(db: AsyncSession, rec_id: int, action: str, adopted_price: Optional[float] = None) -> dict:
    """
    将定价建议标记为 adopted（传 adopted_price）或 dismissed。
    只有 pending 状态的记录可以变更。
    """
    if action == "adopt":
        sql = text("""
            UPDATE dish_pricing_records
            SET status       = 'adopted',
                adopted_price = COALESCE(:adopted_price, suggested_price),
                adopted_at    = NOW(),
                updated_at    = NOW()
            WHERE id = :rec_id AND status = 'pending'
        """)
        params: dict = {"rec_id": rec_id, "adopted_price": adopted_price}
    else:
        sql = text("""
            UPDATE dish_pricing_records
            SET status       = 'dismissed',
                dismissed_at = NOW(),
                updated_at   = NOW()
            WHERE id = :rec_id AND status = 'pending'
        """)
        params = {"rec_id": rec_id}

    result = await db.execute(sql, params)
    await db.commit()
    updated = result.rowcount > 0
    return {
        "updated": updated,
        "rec_id": rec_id,
        "action": action,
        "reason": None if updated else "not_found_or_already_actioned",
    }


async def get_pricing_history(db: AsyncSession, store_id: str, dish_id: str, periods: int = 6) -> list[dict]:
    """某道菜近 N 期的定价建议历史（追踪价格调整演进）。"""
    sql = text("""
        SELECT period, current_price, suggested_price, price_change_pct,
               rec_action, elasticity_class,
               expected_revenue_delta_yuan, expected_profit_delta_yuan,
               confidence_pct, status, adopted_price
        FROM dish_pricing_records
        WHERE store_id = :store_id AND dish_id = :dish_id
        ORDER BY period DESC
        LIMIT :periods
    """)
    rows = (await db.execute(sql, {"store_id": store_id, "dish_id": dish_id, "periods": periods})).fetchall()
    cols = [
        "period",
        "current_price",
        "suggested_price",
        "price_change_pct",
        "rec_action",
        "elasticity_class",
        "expected_revenue_delta_yuan",
        "expected_profit_delta_yuan",
        "confidence_pct",
        "status",
        "adopted_price",
    ]
    return [dict(zip(cols, r)) for r in rows]
