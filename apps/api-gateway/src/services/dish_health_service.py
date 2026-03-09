"""菜品综合健康评分引擎 — Phase 6 Month 8

整合 4 个信号维度：
  盈利能力 (0-25) — GPM + FCR 相对门店均值
  成长性   (0-25) — 生命周期阶段基础分 + 趋势修正
  跨店对标 (0-25) — 基于 dish_benchmark_records 的 fcr_tier
  预测成熟度(0-25)— 基于 dish_forecast_records 的历史期数

综合分 0–100，分为 excellent/good/fair/poor 四级，
并输出 immediate/monitor/maintain/promote 行动优先级与¥改善估算。
"""

from __future__ import annotations

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

# ── 常量 ───────────────────────────────────────────────────────────────────────

PHASE_GROWTH_BASE: dict[str, float] = {
    'launch':  20.0,
    'growth':  22.0,
    'peak':    16.0,
    'decline':  8.0,
    'exit':     2.0,
}

BENCHMARK_TIER_SCORES: dict[str, float] = {
    'top':        25.0,
    'above_avg':  18.0,
    'below_avg':  10.0,
    'laggard':     3.0,
}

PERIODS_SCORE_MAP: dict[int, float] = {1: 13.0, 2: 15.0, 3: 17.0, 4: 19.0, 5: 22.0}

WEAKNESS_ACTIONS: dict[str, tuple[str, str]] = {
    'profitability': (
        '优化成本结构',
        '建议检查食材用量标准、减少损耗，或适当调整售价以提升毛利率',
    ),
    'growth': (
        '改善成长轨迹',
        '建议评估菜品生命周期阶段，为成长期菜品加大推广，为衰退期制定退出计划',
    ),
    'benchmark': (
        '追赶标杆门店',
        '建议参考同业 Top 门店做法，优化工艺标准和原料采购以降低食材成本率',
    ),
    'forecast': (
        '积累运营数据',
        '该菜品历史数据不足，建议至少稳定运营 3 个月后再做重大菜单调整',
    ),
}

PROMOTE_ACTION: tuple[str, str] = (
    '重点推广',
    '综合健康状况优秀，建议加大营销投入、提升陈列位置以放大收益',
)

ACTION_IMPACT_RATE: dict[str, float] = {
    'immediate': 0.25,
    'monitor':   0.10,
    'maintain':  0.03,
    'promote':   0.15,
}


# ── 纯函数 ─────────────────────────────────────────────────────────────────────

def compute_profitability_score(gpm: float, avg_gpm: float,
                                 food_cost_rate: float, avg_fcr: float) -> float:
    """
    盈利能力评分 (0–25)。
    GPM 分 + FCR 分，各 12.5。以门店同期均值为基准(=6.25)，按比例线性伸缩。
    """
    if avg_gpm > 0:
        gpm_score = min(12.5, max(0.0, 6.25 * (gpm / avg_gpm)))
    else:
        gpm_score = 6.25

    if avg_fcr > 0 and food_cost_rate > 0:
        fcr_score = min(12.5, max(0.0, 6.25 * (avg_fcr / food_cost_rate)))
    else:
        fcr_score = 6.25

    return round(gpm_score + fcr_score, 1)


def compute_growth_score(revenue_trend_pct: float, order_trend_pct: float,
                          lifecycle_phase: str) -> float:
    """
    成长性评分 (0–25)。
    生命周期阶段基础分 + 趋势均值修正 ±3。
    """
    base = PHASE_GROWTH_BASE.get(lifecycle_phase, 12.0)
    avg_trend = (revenue_trend_pct + order_trend_pct) / 2.0
    if avg_trend >= 10:
        modifier = 3.0
    elif avg_trend >= 5:
        modifier = 1.5
    elif avg_trend > -5:
        modifier = 0.0
    elif avg_trend >= -10:
        modifier = -1.5
    else:
        modifier = -3.0
    return round(max(0.0, min(25.0, base + modifier)), 1)


def compute_benchmark_score(benchmark_tier: Optional[str]) -> float:
    """
    跨店对标评分 (0–25)。
    无对标数据时返回中性值 12.5。
    """
    if benchmark_tier is None:
        return 12.5
    return BENCHMARK_TIER_SCORES.get(benchmark_tier, 12.5)


def compute_forecast_score(periods_used: Optional[int]) -> float:
    """
    预测成熟度评分 (0–25)。
    反映历史数据积累程度：6 期→25，无数据→10。
    """
    if periods_used is None:
        return 10.0
    if periods_used >= 6:
        return 25.0
    return PERIODS_SCORE_MAP.get(periods_used, 10.0)


def classify_health_tier(total_score: float) -> str:
    """excellent(≥80) / good(≥60) / fair(≥40) / poor(<40)"""
    if total_score >= 80:
        return 'excellent'
    if total_score >= 60:
        return 'good'
    if total_score >= 40:
        return 'fair'
    return 'poor'


def determine_action_priority(health_tier: str, lifecycle_phase: str) -> str:
    """
    poor                         → immediate
    fair + (decline|exit)        → immediate
    fair                         → monitor
    good                         → maintain
    excellent                    → promote
    """
    if health_tier == 'poor':
        return 'immediate'
    if health_tier == 'fair' and lifecycle_phase in ('decline', 'exit'):
        return 'immediate'
    if health_tier == 'fair':
        return 'monitor'
    if health_tier == 'good':
        return 'maintain'
    return 'promote'


def find_top_components(p: float, g: float,
                         b: float, f: float) -> tuple[str, str]:
    """返回 (top_strength, top_weakness) 维度名称。"""
    scores = {'profitability': p, 'growth': g, 'benchmark': b, 'forecast': f}
    strength = max(scores, key=lambda k: scores[k])
    weakness = min(scores, key=lambda k: scores[k])
    return strength, weakness


def compute_health_impact(revenue_yuan: float, action_priority: str) -> float:
    """按行动优先级估算¥改善空间。"""
    rate = ACTION_IMPACT_RATE.get(action_priority, 0.05)
    return round(revenue_yuan * rate, 2)


def build_health_score_record(
    store_id: str,
    period: str,
    dish_id: str,
    dish_name: str,
    category: Optional[str],
    revenue_yuan: float,
    avg_gpm: float,
    avg_fcr: float,
    gpm: float,
    fcr: float,
    revenue_trend_pct: float,
    order_trend_pct: float,
    lifecycle_phase: str,
    benchmark_tier: Optional[str],
    periods_used: Optional[int],
) -> dict:
    """构建单道菜的综合健康评分记录。"""
    p_score = compute_profitability_score(gpm, avg_gpm, fcr, avg_fcr)
    g_score = compute_growth_score(revenue_trend_pct, order_trend_pct, lifecycle_phase)
    b_score = compute_benchmark_score(benchmark_tier)
    f_score = compute_forecast_score(periods_used)

    total    = round(p_score + g_score + b_score + f_score, 1)
    tier     = classify_health_tier(total)
    priority = determine_action_priority(tier, lifecycle_phase)
    strength, weakness = find_top_components(p_score, g_score, b_score, f_score)

    if priority == 'promote':
        action_label, action_desc = PROMOTE_ACTION
    else:
        action_label, action_desc = WEAKNESS_ACTIONS.get(
            weakness, ('持续优化', '保持现有运营策略'))

    return {
        'store_id':              store_id,
        'period':                period,
        'dish_id':               dish_id,
        'dish_name':             dish_name,
        'category':              category,
        'profitability_score':   p_score,
        'growth_score':          g_score,
        'benchmark_score':       b_score,
        'forecast_score':        f_score,
        'total_score':           total,
        'health_tier':           tier,
        'top_strength':          strength,
        'top_weakness':          weakness,
        'action_priority':       priority,
        'action_label':          action_label,
        'action_description':    action_desc,
        'expected_impact_yuan':  compute_health_impact(revenue_yuan, priority),
        'lifecycle_phase':       lifecycle_phase,
        'revenue_yuan':          revenue_yuan,
    }


# ── 数据库函数 ──────────────────────────────────────────────────────────────────

async def _fetch_profitability(db: AsyncSession, store_id: str,
                                period: str) -> list:
    sql = text("""
        SELECT dish_id, dish_name, category,
               order_count, revenue_yuan, gross_profit_margin, food_cost_rate
        FROM dish_profitability_records
        WHERE store_id = :store_id AND period = :period
        ORDER BY dish_id
    """)
    return (await db.execute(sql, {'store_id': store_id,
                                    'period': period})).fetchall()


async def _fetch_lifecycle(db: AsyncSession, store_id: str,
                            period: str) -> dict[str, dict]:
    sql = text("""
        SELECT dish_id, lifecycle_phase, revenue_trend_pct, order_trend_pct
        FROM dish_lifecycle_records
        WHERE store_id = :store_id AND period = :period
    """)
    rows = (await db.execute(sql, {'store_id': store_id,
                                    'period': period})).fetchall()
    return {
        r[0]: {
            'lifecycle_phase':   r[1],
            'revenue_trend_pct': float(r[2] or 0),
            'order_trend_pct':   float(r[3] or 0),
        }
        for r in rows
    }


async def _fetch_benchmarks(db: AsyncSession, store_id: str,
                             period: str) -> dict[str, str]:
    """返回 {dish_name: fcr_tier}"""
    sql = text("""
        SELECT dish_name, fcr_tier
        FROM dish_benchmark_records
        WHERE store_id = :store_id AND period = :period
    """)
    rows = (await db.execute(sql, {'store_id': store_id,
                                    'period': period})).fetchall()
    return {r[0]: r[1] for r in rows}


async def _fetch_forecast_periods(db: AsyncSession, store_id: str,
                                   period: str) -> dict[str, int]:
    """返回 {dish_id: periods_used}，key: base_period = period"""
    sql = text("""
        SELECT dish_id, periods_used
        FROM dish_forecast_records
        WHERE store_id = :store_id AND base_period = :period
    """)
    rows = (await db.execute(sql, {'store_id': store_id,
                                    'period': period})).fetchall()
    return {r[0]: int(r[1]) for r in rows}


async def _upsert_health_record(db: AsyncSession, rec: dict) -> None:
    sql = text("""
        INSERT INTO dish_health_scores (
            store_id, period, dish_id, dish_name, category,
            profitability_score, growth_score, benchmark_score, forecast_score,
            total_score, health_tier, top_strength, top_weakness,
            action_priority, action_label, action_description,
            expected_impact_yuan, lifecycle_phase, revenue_yuan,
            computed_at, updated_at
        ) VALUES (
            :store_id, :period, :dish_id, :dish_name, :category,
            :profitability_score, :growth_score, :benchmark_score, :forecast_score,
            :total_score, :health_tier, :top_strength, :top_weakness,
            :action_priority, :action_label, :action_description,
            :expected_impact_yuan, :lifecycle_phase, :revenue_yuan,
            NOW(), NOW()
        )
        ON CONFLICT (store_id, period, dish_id) DO UPDATE SET
            dish_name             = EXCLUDED.dish_name,
            category              = EXCLUDED.category,
            profitability_score   = EXCLUDED.profitability_score,
            growth_score          = EXCLUDED.growth_score,
            benchmark_score       = EXCLUDED.benchmark_score,
            forecast_score        = EXCLUDED.forecast_score,
            total_score           = EXCLUDED.total_score,
            health_tier           = EXCLUDED.health_tier,
            top_strength          = EXCLUDED.top_strength,
            top_weakness          = EXCLUDED.top_weakness,
            action_priority       = EXCLUDED.action_priority,
            action_label          = EXCLUDED.action_label,
            action_description    = EXCLUDED.action_description,
            expected_impact_yuan  = EXCLUDED.expected_impact_yuan,
            lifecycle_phase       = EXCLUDED.lifecycle_phase,
            revenue_yuan          = EXCLUDED.revenue_yuan,
            updated_at            = NOW()
    """)
    await db.execute(sql, rec)


async def compute_health_scores(db: AsyncSession, store_id: str,
                                 period: str) -> dict:
    """
    整合盈利/生命周期/对标/预测 4 路数据，为门店所有菜品计算综合健康评分。
    幂等写入 dish_health_scores。
    返回 {dish_count, tier_counts, total_impact_yuan}
    """
    prof_rows = await _fetch_profitability(db, store_id, period)
    if not prof_rows:
        await db.commit()
        return {
            'store_id': store_id, 'period': period,
            'dish_count': 0, 'tier_counts': {}, 'total_impact_yuan': 0.0,
        }

    lc_map    = await _fetch_lifecycle(db, store_id, period)
    bench_map = await _fetch_benchmarks(db, store_id, period)
    fc_map    = await _fetch_forecast_periods(db, store_id, period)

    # 计算门店同期平均作为盈利能力基准
    avg_gpm = sum(float(r[5] or 0) for r in prof_rows) / len(prof_rows)
    avg_fcr = sum(float(r[6] or 0) for r in prof_rows) / len(prof_rows)

    tier_counts: dict[str, int] = {}
    total_impact = 0.0

    for r in prof_rows:
        dish_id   = r[0]
        dish_name = r[1]
        category  = r[2]
        revenue   = float(r[4] or 0)
        gpm       = float(r[5] or 0)
        fcr       = float(r[6] or 0)

        lc = lc_map.get(dish_id, {})
        lifecycle_phase  = lc.get('lifecycle_phase', 'peak')
        revenue_trend    = lc.get('revenue_trend_pct', 0.0)
        order_trend      = lc.get('order_trend_pct',   0.0)
        benchmark_tier   = bench_map.get(dish_name)
        periods_used     = fc_map.get(dish_id)

        rec = build_health_score_record(
            store_id, period, dish_id, dish_name, category,
            revenue, avg_gpm, avg_fcr, gpm, fcr,
            revenue_trend, order_trend, lifecycle_phase,
            benchmark_tier, periods_used,
        )
        await _upsert_health_record(db, rec)
        tier_counts[rec['health_tier']] = tier_counts.get(rec['health_tier'], 0) + 1
        total_impact += rec['expected_impact_yuan']

    await db.commit()
    return {
        'store_id':          store_id,
        'period':            period,
        'dish_count':        len(prof_rows),
        'tier_counts':       tier_counts,
        'total_impact_yuan': round(total_impact, 2),
    }


async def get_health_scores(db: AsyncSession, store_id: str, period: str,
                             health_tier: Optional[str] = None,
                             limit: int = 100) -> list[dict]:
    """查询健康评分列表。L011 两路分支。"""
    _cols = """
        id, dish_id, dish_name, category,
        profitability_score, growth_score, benchmark_score, forecast_score,
        total_score, health_tier, top_strength, top_weakness,
        action_priority, action_label, action_description,
        expected_impact_yuan, lifecycle_phase, revenue_yuan
    """
    if health_tier:
        sql = text(f"""
            SELECT {_cols}
            FROM dish_health_scores
            WHERE store_id = :store_id AND period = :period
              AND health_tier = :health_tier
            ORDER BY total_score DESC
            LIMIT :limit
        """)
        params = {'store_id': store_id, 'period': period,
                  'health_tier': health_tier, 'limit': limit}
    else:
        sql = text(f"""
            SELECT {_cols}
            FROM dish_health_scores
            WHERE store_id = :store_id AND period = :period
            ORDER BY total_score DESC
            LIMIT :limit
        """)
        params = {'store_id': store_id, 'period': period, 'limit': limit}

    rows = (await db.execute(sql, params)).fetchall()
    cols = [
        'id', 'dish_id', 'dish_name', 'category',
        'profitability_score', 'growth_score', 'benchmark_score', 'forecast_score',
        'total_score', 'health_tier', 'top_strength', 'top_weakness',
        'action_priority', 'action_label', 'action_description',
        'expected_impact_yuan', 'lifecycle_phase', 'revenue_yuan',
    ]
    return [dict(zip(cols, r)) for r in rows]


async def get_health_summary(db: AsyncSession, store_id: str,
                              period: str) -> dict:
    """按 health_tier 聚合统计。"""
    sql = text("""
        SELECT
            health_tier,
            COUNT(*)                         AS dish_count,
            AVG(total_score)                 AS avg_score,
            SUM(expected_impact_yuan)        AS total_impact,
            AVG(profitability_score)         AS avg_p,
            AVG(growth_score)                AS avg_g,
            AVG(benchmark_score)             AS avg_b,
            AVG(forecast_score)              AS avg_f
        FROM dish_health_scores
        WHERE store_id = :store_id AND period = :period
        GROUP BY health_tier
        ORDER BY avg_score DESC
    """)
    rows = (await db.execute(sql, {'store_id': store_id,
                                    'period': period})).fetchall()

    by_tier = []
    total_dishes  = 0
    total_impact  = 0.0

    for r in rows:
        item = {
            'health_tier':   r[0],
            'dish_count':    int(r[1]),
            'avg_score':     round(float(r[2] or 0), 1),
            'total_impact':  round(float(r[3] or 0), 2),
            'avg_profitability': round(float(r[4] or 0), 1),
            'avg_growth':        round(float(r[5] or 0), 1),
            'avg_benchmark':     round(float(r[6] or 0), 1),
            'avg_forecast':      round(float(r[7] or 0), 1),
        }
        by_tier.append(item)
        total_dishes += item['dish_count']
        total_impact += item['total_impact']

    return {
        'store_id':          store_id,
        'period':            period,
        'total_dishes':      total_dishes,
        'total_impact_yuan': round(total_impact, 2),
        'by_tier':           by_tier,
    }


async def get_action_priorities(db: AsyncSession, store_id: str, period: str,
                                 priority: str = 'immediate',
                                 limit: int = 20) -> list[dict]:
    """按行动优先级返回需关注菜品，按¥改善空间降序。"""
    sql = text("""
        SELECT dish_id, dish_name, category, health_tier, total_score,
               top_weakness, action_label, action_description,
               expected_impact_yuan, lifecycle_phase, revenue_yuan
        FROM dish_health_scores
        WHERE store_id = :store_id AND period = :period
          AND action_priority = :priority
        ORDER BY expected_impact_yuan DESC
        LIMIT :limit
    """)
    rows = (await db.execute(sql, {
        'store_id': store_id, 'period': period,
        'priority': priority, 'limit': limit,
    })).fetchall()
    cols = [
        'dish_id', 'dish_name', 'category', 'health_tier', 'total_score',
        'top_weakness', 'action_label', 'action_description',
        'expected_impact_yuan', 'lifecycle_phase', 'revenue_yuan',
    ]
    return [dict(zip(cols, r)) for r in rows]


async def get_dish_health_history(db: AsyncSession, store_id: str,
                                   dish_id: str, periods: int = 6) -> list[dict]:
    """某道菜近 N 期健康评分历史（追踪评分演进）。"""
    sql = text("""
        SELECT period, total_score, health_tier,
               profitability_score, growth_score, benchmark_score, forecast_score,
               action_priority, lifecycle_phase, expected_impact_yuan
        FROM dish_health_scores
        WHERE store_id = :store_id AND dish_id = :dish_id
        ORDER BY period DESC
        LIMIT :periods
    """)
    rows = (await db.execute(sql, {
        'store_id': store_id, 'dish_id': dish_id, 'periods': periods,
    })).fetchall()
    cols = [
        'period', 'total_score', 'health_tier',
        'profitability_score', 'growth_score', 'benchmark_score', 'forecast_score',
        'action_priority', 'lifecycle_phase', 'expected_impact_yuan',
    ]
    return [dict(zip(cols, r)) for r in rows]


# ── 情感维度注入（第5维） ───────────────────────────────────────────────────────

def enrich_with_sentiment(
    records: list[dict],
    dish_sentiment: "dict[str, Any]",
) -> list[dict]:
    """
    将顾客评论情感摘要注入菜品健康评分记录（纯函数，无副作用）。

    在 dish_health_service 原有 4 个评分维度（盈利/成长/对标/预测）基础上，
    追加来自 CustomerSentimentService 的第 5 个维度：顾客声音。

    Args:
        records:         build_health_score_record() 返回的 dict 列表
        dish_sentiment:  Dict[dish_name, DishSentimentSummary]，
                         由 customer_sentiment_service.aggregate_by_dish() 生成

    Returns:
        原 records 就地修改并返回，每条新增字段：
          sentiment_score        float | None  — 0.0-1.0 综合情感分
          sentiment_score_25     float | None  — 0-25 分制（与其他4维对齐）
          sentiment_label        str           — "好评为主"/"差评预警"/"口碑中性"/"暂无数据"
          top_complaints         list[str]     — 高频差评关键词（最多3个）
          top_praises            list[str]     — 高频好评关键词（最多3个）
          sentiment_review_count int           — 参与计算的评论条数

    用法示例::

        from .customer_sentiment_service import customer_sentiment_service
        reviews = [CustomerReview(text="鱼香肉丝偏咸", dish_name="鱼香肉丝"), ...]
        dish_sentiment = await customer_sentiment_service.analyze_and_aggregate(reviews)
        records = enrich_with_sentiment(health_records, dish_sentiment)
    """
    for rec in records:
        dish_name = rec.get("dish_name", "")
        summary = dish_sentiment.get(dish_name)
        if summary is not None:
            rec["sentiment_score"]        = summary.sentiment_score
            rec["sentiment_score_25"]     = summary.sentiment_score_25
            rec["sentiment_label"]        = summary.sentiment_label
            rec["top_complaints"]         = summary.top_complaints
            rec["top_praises"]            = summary.top_praises
            rec["sentiment_review_count"] = summary.total_reviews
        else:
            rec["sentiment_score"]        = None
            rec["sentiment_score_25"]     = None
            rec["sentiment_label"]        = "暂无数据"
            rec["top_complaints"]         = []
            rec["top_praises"]            = []
            rec["sentiment_review_count"] = 0
    return records
