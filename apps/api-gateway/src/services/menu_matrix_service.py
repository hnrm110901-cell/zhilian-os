"""菜品组合矩阵分析引擎 (BCG Menu Matrix) — Phase 6 Month 10

将门店全部菜品按两轴分类进 BCG 四象限：
  X轴：当期营收在门店内的百分位 (revenue_percentile, 0-100)
  Y轴：营收增长率在门店内的百分位 (growth_percentile, 0-100)

  revenue_pct > 50 & growth_pct > 50  → Star (明星菜)       → promote
  revenue_pct > 50 & growth_pct <= 50 → Cash Cow (现金牛菜) → maintain
  revenue_pct <= 50 & growth_pct > 50 → Question Mark (问题菜) → develop
  revenue_pct <= 50 & growth_pct <= 50 → Dog (瘦狗菜)       → retire

新菜品（无上期数据）增长百分位取 50（中性）。
"""

from __future__ import annotations

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


# ── 期间辅助 ───────────────────────────────────────────────────────────────────

def _prev_period(period: str) -> str:
    year, month = int(period[:4]), int(period[5:7])
    if month == 1:
        return f'{year - 1:04d}-12'
    return f'{year:04d}-{month - 1:02d}'


# ── 纯函数 ─────────────────────────────────────────────────────────────────────

def compute_percentile(value: float, all_values: list[float]) -> float:
    """在 all_values 中计算 value 的百分位 (0-100)。空列表或全同值返回 50.0。"""
    if not all_values:
        return 50.0
    n = len(all_values)
    rank = sum(1 for v in all_values if v < value)
    pct = rank / n * 100.0
    return round(pct, 1)


def compute_delta_pct(current: float, previous: float) -> Optional[float]:
    """营收增长率。previous=0 返回 None（无法计算）。"""
    if previous == 0:
        return None
    return round((current - previous) / abs(previous) * 100, 2)


def classify_quadrant(revenue_pct: float, growth_pct: float) -> str:
    """BCG 四象限分类。"""
    high_rev = revenue_pct > 50
    high_grow = growth_pct > 50
    if high_rev and high_grow:
        return 'star'
    if high_rev and not high_grow:
        return 'cash_cow'
    if not high_rev and high_grow:
        return 'question_mark'
    return 'dog'


# ── 行动建议 ──────────────────────────────────────────────────────────────────

_QUADRANT_ACTION = {
    'star':          'promote',
    'cash_cow':      'maintain',
    'question_mark': 'develop',
    'dog':           'retire',
}

_ACTION_IMPACT_RATE = {
    'promote':  0.15,   # 重点推广，预期营收提升 15%
    'maintain': 0.05,   # 维持现状，小幅稳定提升 5%
    'develop':  0.25,   # 潜力挖掘，若成功可提升 25%
    'retire':   0.03,   # 退出节省运营复杂度，释放约 3% 资源价值
}


def determine_action(quadrant: str) -> str:
    return _QUADRANT_ACTION[quadrant]


def determine_priority(quadrant: str, revenue_pct: float,
                        growth_pct: float) -> str:
    """
    high:   star(rev>75) | cash_cow(growth<25) | question_mark(growth>75) | dog(rev<25)
    medium: 其余 star/cash_cow/question_mark | dog(25≤rev≤50)
    low:    其他
    """
    if quadrant == 'star' and revenue_pct > 75:
        return 'high'
    if quadrant == 'cash_cow' and growth_pct < 25:
        return 'high'
    if quadrant == 'question_mark' and growth_pct > 75:
        return 'high'
    if quadrant == 'dog' and revenue_pct < 25:
        return 'high'
    if quadrant in ('star', 'cash_cow', 'question_mark'):
        return 'medium'
    if quadrant == 'dog':
        return 'medium'
    return 'low'


def compute_impact(revenue_yuan: float, action: str) -> float:
    rate = _ACTION_IMPACT_RATE.get(action, 0.05)
    return round(revenue_yuan * rate, 2)


def compute_contribution_pct(revenue_yuan: float,
                               total_revenue: float) -> Optional[float]:
    if total_revenue <= 0:
        return None
    return round(revenue_yuan / total_revenue * 100, 2)


def build_matrix_record(
    store_id: str,
    period: str,
    prev_period: str,
    dish_id: str,
    dish_name: str,
    category: Optional[str],
    revenue_yuan: float,
    order_count: int,
    prev_revenue_yuan: Optional[float],
    revenue_percentile: float,
    growth_percentile: float,
    menu_contribution_pct: Optional[float],
) -> dict:
    """构建单道菜的矩阵分析记录。"""
    delta_pct = compute_delta_pct(revenue_yuan, prev_revenue_yuan or 0.0) \
        if prev_revenue_yuan is not None else None

    quadrant = classify_quadrant(revenue_percentile, growth_percentile)
    action   = determine_action(quadrant)
    priority = determine_priority(quadrant, revenue_percentile, growth_percentile)
    impact   = compute_impact(revenue_yuan, action)

    return {
        'store_id':              store_id,
        'period':                period,
        'prev_period':           prev_period,
        'dish_id':               dish_id,
        'dish_name':             dish_name,
        'category':              category,
        'revenue_yuan':          revenue_yuan,
        'order_count':           order_count,
        'menu_contribution_pct': menu_contribution_pct,
        'prev_revenue_yuan':     prev_revenue_yuan,
        'revenue_delta_pct':     delta_pct,
        'revenue_percentile':    revenue_percentile,
        'growth_percentile':     growth_percentile,
        'matrix_quadrant':       quadrant,
        'optimization_action':   action,
        'action_priority':       priority,
        'expected_impact_yuan':  impact,
    }


# ── 数据库函数 ──────────────────────────────────────────────────────────────────

async def _fetch_profitability(db: AsyncSession, store_id: str,
                                period: str) -> list:
    sql = text("""
        SELECT dish_id, dish_name, category, order_count, revenue_yuan
        FROM dish_profitability_records
        WHERE store_id = :store_id AND period = :period
        ORDER BY dish_id
    """)
    return (await db.execute(sql, {'store_id': store_id,
                                    'period': period})).fetchall()


async def _upsert_matrix_record(db: AsyncSession, rec: dict) -> None:
    sql = text("""
        INSERT INTO menu_matrix_results (
            store_id, period, prev_period, dish_id, dish_name, category,
            revenue_yuan, order_count, menu_contribution_pct,
            prev_revenue_yuan, revenue_delta_pct,
            revenue_percentile, growth_percentile,
            matrix_quadrant, optimization_action, action_priority,
            expected_impact_yuan, computed_at, updated_at
        ) VALUES (
            :store_id, :period, :prev_period, :dish_id, :dish_name, :category,
            :revenue_yuan, :order_count, :menu_contribution_pct,
            :prev_revenue_yuan, :revenue_delta_pct,
            :revenue_percentile, :growth_percentile,
            :matrix_quadrant, :optimization_action, :action_priority,
            :expected_impact_yuan, NOW(), NOW()
        )
        ON CONFLICT (store_id, period, dish_id) DO UPDATE SET
            prev_period            = EXCLUDED.prev_period,
            dish_name              = EXCLUDED.dish_name,
            category               = EXCLUDED.category,
            revenue_yuan           = EXCLUDED.revenue_yuan,
            order_count            = EXCLUDED.order_count,
            menu_contribution_pct  = EXCLUDED.menu_contribution_pct,
            prev_revenue_yuan      = EXCLUDED.prev_revenue_yuan,
            revenue_delta_pct      = EXCLUDED.revenue_delta_pct,
            revenue_percentile     = EXCLUDED.revenue_percentile,
            growth_percentile      = EXCLUDED.growth_percentile,
            matrix_quadrant        = EXCLUDED.matrix_quadrant,
            optimization_action    = EXCLUDED.optimization_action,
            action_priority        = EXCLUDED.action_priority,
            expected_impact_yuan   = EXCLUDED.expected_impact_yuan,
            updated_at             = NOW()
    """)
    await db.execute(sql, rec)


async def compute_menu_matrix(db: AsyncSession, store_id: str,
                               period: str,
                               prev_period: Optional[str] = None) -> dict:
    """
    对门店指定期的全菜品做 BCG 矩阵分析并幂等写入。
    返回 {dish_count, quadrant_counts, high_priority_count,
          total_expected_impact_yuan, new_dishes, prev_period}
    """
    if prev_period is None:
        prev_period = _prev_period(period)

    curr_rows = await _fetch_profitability(db, store_id, period)
    prev_rows = await _fetch_profitability(db, store_id, prev_period)

    prev_map = {r[0]: float(r[4] or 0) for r in prev_rows}
    curr_list = [(r[0], r[1], r[2], int(r[3] or 0), float(r[4] or 0))
                 for r in curr_rows]

    if not curr_list:
        await db.commit()
        return {
            'store_id': store_id, 'period': period, 'prev_period': prev_period,
            'dish_count': 0, 'quadrant_counts': {},
            'high_priority_count': 0, 'total_expected_impact_yuan': 0.0,
            'new_dishes': 0,
        }

    # 计算各菜品的营收增长率
    revenues     = [item[4] for item in curr_list]
    total_rev    = sum(revenues)
    new_dish_cnt = sum(1 for item in curr_list if item[0] not in prev_map)

    delta_pcts: list[float] = []
    for dish_id, _, _, _, rev in curr_list:
        prev_rev = prev_map.get(dish_id)
        if prev_rev is not None and prev_rev > 0:
            delta_pcts.append((rev - prev_rev) / prev_rev * 100)
        else:
            delta_pcts.append(0.0)   # 新菜品 / 无上期数据

    # 计算百分位并写入
    quadrant_counts: dict[str, int] = {}
    high_cnt  = 0
    total_imp = 0.0

    for idx, (dish_id, dish_name, category, order_count, rev) in enumerate(curr_list):
        rev_pct  = compute_percentile(rev, revenues)
        grow_pct = compute_percentile(delta_pcts[idx], delta_pcts)
        # 新菜品（上期无数据）增长百分位设为中性 50
        if dish_id not in prev_map:
            grow_pct = 50.0

        prev_rev = prev_map.get(dish_id)
        contrib  = compute_contribution_pct(rev, total_rev)

        rec = build_matrix_record(
            store_id, period, prev_period,
            dish_id, dish_name, category,
            rev, order_count, prev_rev,
            rev_pct, grow_pct, contrib,
        )
        await _upsert_matrix_record(db, rec)

        q = rec['matrix_quadrant']
        quadrant_counts[q] = quadrant_counts.get(q, 0) + 1
        if rec['action_priority'] == 'high':
            high_cnt += 1
        total_imp += rec['expected_impact_yuan']

    await db.commit()
    return {
        'store_id':                 store_id,
        'period':                   period,
        'prev_period':              prev_period,
        'dish_count':               len(curr_list),
        'quadrant_counts':          quadrant_counts,
        'high_priority_count':      high_cnt,
        'total_expected_impact_yuan': round(total_imp, 2),
        'new_dishes':               new_dish_cnt,
    }


async def get_menu_matrix(db: AsyncSession, store_id: str, period: str,
                           quadrant: Optional[str] = None,
                           action: Optional[str] = None,
                           priority: Optional[str] = None,
                           limit: int = 100) -> list[dict]:
    """查询矩阵分析明细，支持象限/行动/优先级三路独立筛选 (L011)。"""
    _cols = """
        id, dish_id, dish_name, category,
        revenue_yuan, order_count, menu_contribution_pct,
        prev_revenue_yuan, revenue_delta_pct,
        revenue_percentile, growth_percentile,
        matrix_quadrant, optimization_action, action_priority,
        expected_impact_yuan
    """
    base = """
        FROM menu_matrix_results
        WHERE store_id = :store_id AND period = :period
    """
    params: dict = {'store_id': store_id, 'period': period, 'limit': limit}

    if quadrant:
        sql = text(f"SELECT {_cols} {base} AND matrix_quadrant = :quadrant "
                   "ORDER BY revenue_yuan DESC LIMIT :limit")
        params['quadrant'] = quadrant
    elif action:
        sql = text(f"SELECT {_cols} {base} AND optimization_action = :action "
                   "ORDER BY expected_impact_yuan DESC LIMIT :limit")
        params['action'] = action
    elif priority:
        sql = text(f"SELECT {_cols} {base} AND action_priority = :priority "
                   "ORDER BY expected_impact_yuan DESC LIMIT :limit")
        params['priority'] = priority
    else:
        sql = text(f"SELECT {_cols} {base} "
                   "ORDER BY revenue_yuan DESC LIMIT :limit")

    rows = (await db.execute(sql, params)).fetchall()
    cols = [
        'id', 'dish_id', 'dish_name', 'category',
        'revenue_yuan', 'order_count', 'menu_contribution_pct',
        'prev_revenue_yuan', 'revenue_delta_pct',
        'revenue_percentile', 'growth_percentile',
        'matrix_quadrant', 'optimization_action', 'action_priority',
        'expected_impact_yuan',
    ]
    return [dict(zip(cols, r)) for r in rows]


async def get_matrix_summary(db: AsyncSession, store_id: str,
                              period: str) -> dict:
    """按象限聚合统计，包含总营收贡献和预期影响。"""
    sql = text("""
        SELECT
            matrix_quadrant,
            COUNT(*)                            AS dish_count,
            SUM(revenue_yuan)                   AS total_revenue,
            AVG(revenue_percentile)             AS avg_rev_pct,
            AVG(growth_percentile)              AS avg_grow_pct,
            SUM(expected_impact_yuan)           AS total_impact,
            COUNT(CASE WHEN action_priority = 'high' THEN 1 END) AS high_cnt
        FROM menu_matrix_results
        WHERE store_id = :store_id AND period = :period
        GROUP BY matrix_quadrant
        ORDER BY SUM(revenue_yuan) DESC
    """)
    rows = (await db.execute(sql, {'store_id': store_id,
                                    'period': period})).fetchall()
    by_quadrant = []
    total_rev = 0.0
    total_imp = 0.0
    total_cnt = 0

    for r in rows:
        item = {
            'quadrant':      r[0],
            'dish_count':    int(r[1]),
            'total_revenue': round(float(r[2] or 0), 2),
            'avg_rev_pct':   round(float(r[3] or 0), 1),
            'avg_grow_pct':  round(float(r[4] or 0), 1),
            'total_impact':  round(float(r[5] or 0), 2),
            'high_priority_dishes': int(r[6]),
        }
        by_quadrant.append(item)
        total_rev += item['total_revenue']
        total_imp += item['total_impact']
        total_cnt += item['dish_count']

    return {
        'store_id':                 store_id,
        'period':                   period,
        'total_dishes':             total_cnt,
        'total_revenue':            round(total_rev, 2),
        'total_expected_impact':    round(total_imp, 2),
        'by_quadrant':              by_quadrant,
    }


async def get_top_actions(db: AsyncSession, store_id: str, period: str,
                           action: str = 'promote',
                           limit: int = 10) -> list[dict]:
    """按推荐行动类型，返回预期影响最大的菜品列表。L011 两路分支。"""
    _cols = """
        dish_id, dish_name, category,
        revenue_yuan, revenue_delta_pct,
        revenue_percentile, growth_percentile,
        matrix_quadrant, action_priority, expected_impact_yuan
    """
    sql = text(f"""
        SELECT {_cols}
        FROM menu_matrix_results
        WHERE store_id = :store_id AND period = :period
          AND optimization_action = :action
        ORDER BY expected_impact_yuan DESC
        LIMIT :limit
    """)
    rows = (await db.execute(sql, {
        'store_id': store_id, 'period': period,
        'action': action, 'limit': limit,
    })).fetchall()
    cols = [
        'dish_id', 'dish_name', 'category',
        'revenue_yuan', 'revenue_delta_pct',
        'revenue_percentile', 'growth_percentile',
        'matrix_quadrant', 'action_priority', 'expected_impact_yuan',
    ]
    return [dict(zip(cols, r)) for r in rows]


async def get_dish_quadrant_history(db: AsyncSession, store_id: str,
                                     dish_id: str,
                                     periods: int = 6) -> list[dict]:
    """某道菜近 N 期的象限变迁历史。"""
    sql = text("""
        SELECT
            period, matrix_quadrant, optimization_action, action_priority,
            revenue_yuan, revenue_delta_pct,
            revenue_percentile, growth_percentile,
            expected_impact_yuan
        FROM menu_matrix_results
        WHERE store_id = :store_id AND dish_id = :dish_id
        ORDER BY period DESC
        LIMIT :periods
    """)
    rows = (await db.execute(sql, {
        'store_id': store_id, 'dish_id': dish_id, 'periods': periods,
    })).fetchall()
    cols = [
        'period', 'matrix_quadrant', 'optimization_action', 'action_priority',
        'revenue_yuan', 'revenue_delta_pct',
        'revenue_percentile', 'growth_percentile',
        'expected_impact_yuan',
    ]
    return [dict(zip(cols, r)) for r in rows]
