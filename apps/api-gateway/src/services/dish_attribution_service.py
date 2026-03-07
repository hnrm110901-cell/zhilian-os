"""菜品营收归因引擎 (Price-Volume-Mix) — Phase 6 Month 9

将相邻两期的营收变化拆解为三个效应：
  价格效应 (Price Effect) = 上期销量 × (当期均价 - 上期均价)
  销量效应 (Volume Effect) = 上期均价 × (当期销量 - 上期销量)
  交互效应 (Interaction)  = (均价变化) × (销量变化)

验证：price_effect + volume_effect + interaction = revenue_delta ✓
"""

from __future__ import annotations

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


# ── 期间辅助 ───────────────────────────────────────────────────────────────────

def _prev_period(period: str) -> str:
    """返回上一个 YYYY-MM。"""
    year, month = int(period[:4]), int(period[5:7])
    if month == 1:
        return f'{year - 1:04d}-12'
    return f'{year:04d}-{month - 1:02d}'


# ── 纯函数 ─────────────────────────────────────────────────────────────────────

def compute_avg_price(revenue_yuan: float, order_count: int) -> float:
    """计算每单均价。order_count=0 返回 0.0。"""
    if order_count <= 0:
        return 0.0
    return round(revenue_yuan / order_count, 2)


def compute_price_effect(prev_orders: int, price_delta: float) -> float:
    """价格效应：固定销量不变，衡量定价变化带来的营收影响。"""
    return round(float(prev_orders) * price_delta, 2)


def compute_volume_effect(prev_avg_price: float, order_delta: int) -> float:
    """销量效应：固定均价不变，衡量销量变化带来的营收影响。"""
    return round(prev_avg_price * float(order_delta), 2)


def compute_interaction(price_delta: float, order_delta: int) -> float:
    """交互效应：价格与销量同时变化产生的联合影响。"""
    return round(price_delta * float(order_delta), 2)


def compute_delta_pct(current: float, previous: float) -> float:
    """百分比变化，previous=0 返回 0.0。"""
    if previous == 0:
        return 0.0
    return round((current - previous) / abs(previous) * 100, 2)


def classify_driver(price_effect: float, volume_effect: float,
                     interaction: float, revenue_delta: float) -> str:
    """
    识别营收变化的主要驱动因子。
    某效应占绝对值合计 ≥ 60% → 视为主要驱动；否则 'mixed'。
    revenue_delta 绝对值 < 1 → 'stable'。
    """
    if abs(revenue_delta) < 1.0:
        return 'stable'
    effects = {
        'price':       abs(price_effect),
        'volume':      abs(volume_effect),
        'interaction': abs(interaction),
    }
    total = sum(effects.values())
    if total == 0:
        return 'stable'
    dominant = max(effects, key=lambda k: effects[k])
    if effects[dominant] / total >= 0.60:
        return dominant
    return 'mixed'


def build_attribution_record(
    store_id: str,
    period: str,
    prev_period: str,
    dish_id: str,
    dish_name: str,
    category: Optional[str],
    current_orders: int,
    current_revenue: float,
    prev_orders: int,
    prev_revenue: float,
) -> dict:
    """构建单道菜的 PVM 归因记录。"""
    current_avg = compute_avg_price(current_revenue, current_orders)
    prev_avg    = compute_avg_price(prev_revenue,    prev_orders)

    revenue_delta = round(current_revenue - prev_revenue, 2)
    order_delta   = current_orders - prev_orders
    price_delta   = round(current_avg - prev_avg, 2)

    pe = compute_price_effect(prev_orders, price_delta)
    ve = compute_volume_effect(prev_avg,   order_delta)
    ie = compute_interaction(price_delta,  order_delta)

    driver = classify_driver(pe, ve, ie, revenue_delta)

    return {
        'store_id':           store_id,
        'period':             period,
        'prev_period':        prev_period,
        'dish_id':            dish_id,
        'dish_name':          dish_name,
        'category':           category,
        'current_revenue':    current_revenue,
        'prev_revenue':       prev_revenue,
        'revenue_delta':      revenue_delta,
        'revenue_delta_pct':  compute_delta_pct(current_revenue, prev_revenue),
        'current_orders':     current_orders,
        'prev_orders':        prev_orders,
        'order_delta':        order_delta,
        'order_delta_pct':    compute_delta_pct(current_orders, prev_orders),
        'current_avg_price':  current_avg,
        'prev_avg_price':     prev_avg,
        'price_delta':        price_delta,
        'price_delta_pct':    compute_delta_pct(current_avg, prev_avg),
        'price_effect_yuan':  pe,
        'volume_effect_yuan': ve,
        'interaction_yuan':   ie,
        'primary_driver':     driver,
    }


# ── 数据库函数 ──────────────────────────────────────────────────────────────────

async def _fetch_period_data(db: AsyncSession, store_id: str,
                              period: str) -> list:
    """拉取指定期的所有菜品盈利数据。"""
    sql = text("""
        SELECT dish_id, dish_name, category, order_count, revenue_yuan
        FROM dish_profitability_records
        WHERE store_id = :store_id AND period = :period
        ORDER BY dish_id
    """)
    return (await db.execute(sql, {'store_id': store_id,
                                    'period': period})).fetchall()


async def _upsert_attribution_record(db: AsyncSession, rec: dict) -> None:
    sql = text("""
        INSERT INTO dish_revenue_attribution (
            store_id, period, prev_period, dish_id, dish_name, category,
            current_revenue, prev_revenue, revenue_delta, revenue_delta_pct,
            current_orders, prev_orders, order_delta, order_delta_pct,
            current_avg_price, prev_avg_price, price_delta, price_delta_pct,
            price_effect_yuan, volume_effect_yuan, interaction_yuan,
            primary_driver, computed_at, updated_at
        ) VALUES (
            :store_id, :period, :prev_period, :dish_id, :dish_name, :category,
            :current_revenue, :prev_revenue, :revenue_delta, :revenue_delta_pct,
            :current_orders, :prev_orders, :order_delta, :order_delta_pct,
            :current_avg_price, :prev_avg_price, :price_delta, :price_delta_pct,
            :price_effect_yuan, :volume_effect_yuan, :interaction_yuan,
            :primary_driver, NOW(), NOW()
        )
        ON CONFLICT (store_id, period, dish_id) DO UPDATE SET
            prev_period        = EXCLUDED.prev_period,
            dish_name          = EXCLUDED.dish_name,
            category           = EXCLUDED.category,
            current_revenue    = EXCLUDED.current_revenue,
            prev_revenue       = EXCLUDED.prev_revenue,
            revenue_delta      = EXCLUDED.revenue_delta,
            revenue_delta_pct  = EXCLUDED.revenue_delta_pct,
            current_orders     = EXCLUDED.current_orders,
            prev_orders        = EXCLUDED.prev_orders,
            order_delta        = EXCLUDED.order_delta,
            order_delta_pct    = EXCLUDED.order_delta_pct,
            current_avg_price  = EXCLUDED.current_avg_price,
            prev_avg_price     = EXCLUDED.prev_avg_price,
            price_delta        = EXCLUDED.price_delta,
            price_delta_pct    = EXCLUDED.price_delta_pct,
            price_effect_yuan  = EXCLUDED.price_effect_yuan,
            volume_effect_yuan = EXCLUDED.volume_effect_yuan,
            interaction_yuan   = EXCLUDED.interaction_yuan,
            primary_driver     = EXCLUDED.primary_driver,
            updated_at         = NOW()
    """)
    await db.execute(sql, rec)


async def compute_revenue_attribution(db: AsyncSession, store_id: str,
                                       period: str,
                                       prev_period: Optional[str] = None) -> dict:
    """
    对比 period 与 prev_period（默认为上月），为每道出现在两期的菜品
    计算 PVM 归因并幂等写入。
    返回 {dish_count, new_dishes, discontinued_dishes, total_revenue_delta,
          total_price_effect, total_volume_effect, driver_counts}
    """
    if prev_period is None:
        prev_period = _prev_period(period)

    curr_rows = await _fetch_period_data(db, store_id, period)
    prev_rows = await _fetch_period_data(db, store_id, prev_period)

    curr_map = {r[0]: r for r in curr_rows}
    prev_map = {r[0]: r for r in prev_rows}

    both    = set(curr_map) & set(prev_map)
    new_cnt  = len(set(curr_map) - set(prev_map))
    disc_cnt = len(set(prev_map) - set(curr_map))

    total_delta   = 0.0
    total_price_e = 0.0
    total_vol_e   = 0.0
    driver_counts: dict[str, int] = {}

    for dish_id in sorted(both):
        c = curr_map[dish_id]
        p = prev_map[dish_id]
        rec = build_attribution_record(
            store_id, period, prev_period,
            dish_id, c[1], c[2],
            int(c[3] or 0), float(c[4] or 0),
            int(p[3] or 0), float(p[4] or 0),
        )
        await _upsert_attribution_record(db, rec)
        total_delta   += rec['revenue_delta']
        total_price_e += rec['price_effect_yuan']
        total_vol_e   += rec['volume_effect_yuan']
        driver_counts[rec['primary_driver']] = \
            driver_counts.get(rec['primary_driver'], 0) + 1

    await db.commit()
    return {
        'store_id':             store_id,
        'period':               period,
        'prev_period':          prev_period,
        'dish_count':           len(both),
        'new_dishes':           new_cnt,
        'discontinued_dishes':  disc_cnt,
        'total_revenue_delta':  round(total_delta,   2),
        'total_price_effect':   round(total_price_e, 2),
        'total_volume_effect':  round(total_vol_e,   2),
        'driver_counts':        driver_counts,
    }


async def get_revenue_attribution(db: AsyncSession, store_id: str,
                                   period: str,
                                   driver: Optional[str] = None,
                                   limit: int = 100) -> list[dict]:
    """查询归因明细列表。L011 两路分支。"""
    _cols = """
        id, dish_id, dish_name, category,
        current_revenue, prev_revenue, revenue_delta, revenue_delta_pct,
        current_orders, prev_orders, order_delta,
        current_avg_price, prev_avg_price, price_delta,
        price_effect_yuan, volume_effect_yuan, interaction_yuan,
        primary_driver, prev_period
    """
    if driver:
        sql = text(f"""
            SELECT {_cols}
            FROM dish_revenue_attribution
            WHERE store_id = :store_id AND period = :period
              AND primary_driver = :driver
            ORDER BY ABS(revenue_delta) DESC
            LIMIT :limit
        """)
        params = {'store_id': store_id, 'period': period,
                  'driver': driver, 'limit': limit}
    else:
        sql = text(f"""
            SELECT {_cols}
            FROM dish_revenue_attribution
            WHERE store_id = :store_id AND period = :period
            ORDER BY ABS(revenue_delta) DESC
            LIMIT :limit
        """)
        params = {'store_id': store_id, 'period': period, 'limit': limit}

    rows = (await db.execute(sql, params)).fetchall()
    cols = [
        'id', 'dish_id', 'dish_name', 'category',
        'current_revenue', 'prev_revenue', 'revenue_delta', 'revenue_delta_pct',
        'current_orders', 'prev_orders', 'order_delta',
        'current_avg_price', 'prev_avg_price', 'price_delta',
        'price_effect_yuan', 'volume_effect_yuan', 'interaction_yuan',
        'primary_driver', 'prev_period',
    ]
    return [dict(zip(cols, r)) for r in rows]


async def get_attribution_summary(db: AsyncSession, store_id: str,
                                   period: str) -> dict:
    """按主要驱动因子聚合统计。"""
    sql = text("""
        SELECT
            primary_driver,
            COUNT(*)                                           AS dish_count,
            SUM(revenue_delta)                                 AS total_delta,
            SUM(price_effect_yuan)                             AS price_effect,
            SUM(volume_effect_yuan)                            AS volume_effect,
            SUM(interaction_yuan)                              AS interaction,
            COUNT(CASE WHEN revenue_delta > 0 THEN 1 END)      AS gainers,
            COUNT(CASE WHEN revenue_delta < 0 THEN 1 END)      AS losers
        FROM dish_revenue_attribution
        WHERE store_id = :store_id AND period = :period
        GROUP BY primary_driver
        ORDER BY ABS(SUM(revenue_delta)) DESC
    """)
    rows = (await db.execute(sql, {'store_id': store_id,
                                    'period': period})).fetchall()

    by_driver = []
    total_delta    = 0.0
    total_price_e  = 0.0
    total_vol_e    = 0.0
    total_interact = 0.0

    for r in rows:
        item = {
            'primary_driver':  r[0],
            'dish_count':      int(r[1]),
            'total_delta':     round(float(r[2] or 0), 2),
            'price_effect':    round(float(r[3] or 0), 2),
            'volume_effect':   round(float(r[4] or 0), 2),
            'interaction':     round(float(r[5] or 0), 2),
            'gainers':         int(r[6]),
            'losers':          int(r[7]),
        }
        by_driver.append(item)
        total_delta    += item['total_delta']
        total_price_e  += item['price_effect']
        total_vol_e    += item['volume_effect']
        total_interact += item['interaction']

    return {
        'store_id':            store_id,
        'period':              period,
        'total_delta':         round(total_delta,    2),
        'total_price_effect':  round(total_price_e,  2),
        'total_volume_effect': round(total_vol_e,    2),
        'total_interaction':   round(total_interact, 2),
        'by_driver':           by_driver,
    }


async def get_top_movers(db: AsyncSession, store_id: str, period: str,
                          direction: str = 'gain',
                          limit: int = 10) -> list[dict]:
    """
    营收变化最大的菜品。direction='gain' → 增幅最大；'loss' → 降幅最大。
    L011 两路分支。
    """
    _cols = """
        dish_id, dish_name, category,
        current_revenue, prev_revenue, revenue_delta, revenue_delta_pct,
        price_effect_yuan, volume_effect_yuan, interaction_yuan, primary_driver
    """
    if direction == 'gain':
        sql = text(f"""
            SELECT {_cols}
            FROM dish_revenue_attribution
            WHERE store_id = :store_id AND period = :period
            ORDER BY revenue_delta DESC
            LIMIT :limit
        """)
    else:
        sql = text(f"""
            SELECT {_cols}
            FROM dish_revenue_attribution
            WHERE store_id = :store_id AND period = :period
            ORDER BY revenue_delta ASC
            LIMIT :limit
        """)
    rows = (await db.execute(sql, {
        'store_id': store_id, 'period': period, 'limit': limit,
    })).fetchall()
    cols = [
        'dish_id', 'dish_name', 'category',
        'current_revenue', 'prev_revenue', 'revenue_delta', 'revenue_delta_pct',
        'price_effect_yuan', 'volume_effect_yuan', 'interaction_yuan', 'primary_driver',
    ]
    return [dict(zip(cols, r)) for r in rows]


async def get_dish_attribution_history(db: AsyncSession, store_id: str,
                                        dish_id: str,
                                        periods: int = 6) -> list[dict]:
    """某道菜近 N 期的 PVM 归因历史。"""
    sql = text("""
        SELECT
            period, prev_period,
            revenue_delta, revenue_delta_pct,
            price_effect_yuan, volume_effect_yuan, interaction_yuan,
            order_delta, price_delta, primary_driver
        FROM dish_revenue_attribution
        WHERE store_id = :store_id AND dish_id = :dish_id
        ORDER BY period DESC
        LIMIT :periods
    """)
    rows = (await db.execute(sql, {
        'store_id': store_id, 'dish_id': dish_id, 'periods': periods,
    })).fetchall()
    cols = [
        'period', 'prev_period',
        'revenue_delta', 'revenue_delta_pct',
        'price_effect_yuan', 'volume_effect_yuan', 'interaction_yuan',
        'order_delta', 'price_delta', 'primary_driver',
    ]
    return [dict(zip(cols, r)) for r in rows]
