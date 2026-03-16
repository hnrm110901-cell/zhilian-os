"""菜品经营综合月报引擎 — Phase 6 Month 12（收官）

从 5 个菜品分析数据源聚合月度汇总，生成规则驱动的经营洞察文本。

数据源优先级（缺失时降级为 None，不阻塞整体生成）：
  1. dish_profitability_records  ← 必须，营收/成本基线
  2. dish_health_scores          ← 可选
  3. menu_matrix_results         ← 可选
  4. dish_revenue_attribution    ← 可选
  5. dish_cost_compression       ← 可选
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ── 期间辅助 ───────────────────────────────────────────────────────────────────


def _prev_period(period: str) -> str:
    year, month = int(period[:4]), int(period[5:7])
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


# ── 纯函数 ─────────────────────────────────────────────────────────────────────


def compute_revenue_delta_pct(current: float, previous: float) -> Optional[float]:
    if previous == 0:
        return None
    return round((current - previous) / abs(previous) * 100, 2)


def compute_data_sources_available(*values: object) -> int:
    """统计非 None 的数据源数量。"""
    return sum(1 for v in values if v is not None)


def generate_insight_text(
    total_dishes: int,
    revenue_delta_pct: Optional[float],
    avg_health_score: Optional[float],
    star_count: Optional[int],
    dog_count: Optional[int],
    total_expected_saving: Optional[float],
    dominant_driver: Optional[str],
    worsening_fcr_count: Optional[int],
) -> str:
    """
    规则驱动的经营洞察文本（最多 4 条）。
    每条以"；"分隔，无命中规则则返回默认文案。
    """
    parts: list[str] = []

    # 营收趋势
    if revenue_delta_pct is not None:
        if revenue_delta_pct >= 10:
            parts.append(f"营收大幅增长 {revenue_delta_pct:.1f}%，势头强劲，建议乘势扩大明星菜投入")
        elif revenue_delta_pct >= 3:
            parts.append(f"营收稳健增长 {revenue_delta_pct:.1f}%，整体经营向好")
        elif revenue_delta_pct <= -10:
            parts.append(f"营收大幅下滑 {abs(revenue_delta_pct):.1f}%，需紧急排查原因")
        elif revenue_delta_pct <= -3:
            parts.append(f"营收小幅下滑 {abs(revenue_delta_pct):.1f}%，建议重点关注销量驱动类菜品")

    # 菜品健康状况
    if avg_health_score is not None:
        if avg_health_score >= 75:
            parts.append(f"菜品综合健康评分 {avg_health_score:.0f} 分，结构优质")
        elif avg_health_score < 50:
            parts.append(f"菜品综合健康评分偏低（{avg_health_score:.0f} 分），建议优先改善 poor 类菜品")

    # BCG 结构
    if star_count is not None and dog_count is not None and total_dishes > 0:
        star_pct = star_count / total_dishes * 100
        dog_pct = dog_count / total_dishes * 100
        if star_pct >= 30:
            parts.append(f"明星菜占比 {star_pct:.0f}%，菜品组合结构健康")
        if dog_pct >= 35:
            parts.append(f"瘦狗菜占比 {dog_pct:.0f}%，建议精简菜单，淘汰低效菜品")

    # 成本压缩
    if total_expected_saving is not None and total_expected_saving > 0:
        if total_expected_saving >= 50000:
            parts.append(
                f"年化成本压缩空间达 ¥{total_expected_saving:,.0f}，"
                f'{"建议优先与供应商重新谈判" if worsening_fcr_count and worsening_fcr_count >= 3 else "建议推进配方与份量标准化"}'
            )
        elif total_expected_saving >= 10000:
            parts.append(f"年化成本压缩空间 ¥{total_expected_saving:,.0f}，持续推进成本优化")

    # PVM 主要驱动
    _driver_labels = {
        "price": "价格变动",
        "volume": "销量变动",
        "interaction": "价量联动",
        "mixed": "多重因素",
    }
    if dominant_driver and dominant_driver in _driver_labels:
        parts.append(f"本期营收变化主要由【{_driver_labels[dominant_driver]}】驱动")

    if not parts:
        return "本期各项菜品经营指标较为平稳，请持续监控核心 KPI。"
    return "；".join(parts[:4])  # 最多输出 4 条


# ── DB 数据抓取层 ──────────────────────────────────────────────────────────────


async def _fetch_profitability_summary(db: AsyncSession, store_id: str, period: str, prev_period: str) -> Optional[dict]:
    """营收基线：当期总营收 + 上期总营收。"""
    sql = text("""
        SELECT
            COUNT(*)         AS total_dishes,
            SUM(revenue_yuan) AS total_revenue
        FROM dish_profitability_records
        WHERE store_id = :store_id AND period = :period
    """)
    row = (await db.execute(sql, {"store_id": store_id, "period": period})).fetchone()
    if not row or not row[0]:
        return None

    sql_prev = text("""
        SELECT SUM(revenue_yuan)
        FROM dish_profitability_records
        WHERE store_id = :store_id AND period = :period
    """)
    prev_row = (await db.execute(sql_prev, {"store_id": store_id, "period": prev_period})).fetchone()
    prev_rev = float(prev_row[0] or 0) if prev_row and prev_row[0] else None

    return {
        "total_dishes": int(row[0]),
        "total_revenue": round(float(row[1] or 0), 2),
        "prev_revenue": prev_rev,
    }


async def _fetch_health_summary(db: AsyncSession, store_id: str, period: str) -> Optional[dict]:
    sql = text("""
        SELECT
            AVG(total_score)                                        AS avg_score,
            COUNT(CASE WHEN health_tier='excellent' THEN 1 END)     AS excellent,
            COUNT(CASE WHEN health_tier='good'      THEN 1 END)     AS good,
            COUNT(CASE WHEN health_tier='fair'      THEN 1 END)     AS fair,
            COUNT(CASE WHEN health_tier='poor'      THEN 1 END)     AS poor,
            COUNT(CASE WHEN action_priority='immediate' THEN 1 END) AS immediate
        FROM dish_health_scores
        WHERE store_id = :store_id AND period = :period
    """)
    row = (await db.execute(sql, {"store_id": store_id, "period": period})).fetchone()
    if not row or row[0] is None:
        return None
    return {
        "avg_health_score": round(float(row[0]), 1),
        "excellent_count": int(row[1]),
        "good_count": int(row[2]),
        "fair_count": int(row[3]),
        "poor_count": int(row[4]),
        "immediate_action_count": int(row[5]),
    }


async def _fetch_matrix_summary(db: AsyncSession, store_id: str, period: str) -> Optional[dict]:
    sql = text("""
        SELECT
            COUNT(CASE WHEN matrix_quadrant='star'          THEN 1 END) AS star,
            COUNT(CASE WHEN matrix_quadrant='cash_cow'      THEN 1 END) AS cash_cow,
            COUNT(CASE WHEN matrix_quadrant='question_mark' THEN 1 END) AS question_mark,
            COUNT(CASE WHEN matrix_quadrant='dog'           THEN 1 END) AS dog,
            SUM(expected_impact_yuan)                                    AS total_impact
        FROM menu_matrix_results
        WHERE store_id = :store_id AND period = :period
    """)
    row = (await db.execute(sql, {"store_id": store_id, "period": period})).fetchone()
    if not row or (row[0] == 0 and row[1] == 0 and row[2] == 0 and row[3] == 0):
        return None
    return {
        "star_count": int(row[0]),
        "cash_cow_count": int(row[1]),
        "question_mark_count": int(row[2]),
        "dog_count": int(row[3]),
        "matrix_total_impact_yuan": round(float(row[4] or 0), 2),
    }


async def _fetch_attribution_summary(db: AsyncSession, store_id: str, period: str) -> Optional[dict]:
    sql = text("""
        SELECT
            COUNT(*)                   AS dish_count,
            SUM(revenue_delta)         AS total_delta,
            SUM(price_effect_yuan)     AS price_effect,
            SUM(volume_effect_yuan)    AS volume_effect
        FROM dish_revenue_attribution
        WHERE store_id = :store_id AND period = :period
    """)
    row = (await db.execute(sql, {"store_id": store_id, "period": period})).fetchone()
    if not row or not row[0]:
        return None

    # 找主导驱动因子（菜品数最多的）
    sql_driver = text("""
        SELECT primary_driver, COUNT(*) AS cnt
        FROM dish_revenue_attribution
        WHERE store_id = :store_id AND period = :period
          AND primary_driver NOT IN ('stable', 'mixed')
        GROUP BY primary_driver
        ORDER BY cnt DESC
        LIMIT 1
    """)
    dr = (await db.execute(sql_driver, {"store_id": store_id, "period": period})).fetchone()
    return {
        "pvm_dish_count": int(row[0]),
        "total_pvm_delta": round(float(row[1] or 0), 2),
        "total_price_effect": round(float(row[2] or 0), 2),
        "total_volume_effect": round(float(row[3] or 0), 2),
        "dominant_driver": dr[0] if dr else None,
    }


async def _fetch_compression_summary(db: AsyncSession, store_id: str, period: str) -> Optional[dict]:
    sql = text("""
        SELECT
            COUNT(*)                                              AS dish_count,
            SUM(compression_opportunity_yuan)                     AS total_opp,
            SUM(expected_saving_yuan)                             AS total_saving,
            COUNT(CASE WHEN compression_action='renegotiate' THEN 1 END) AS renegotiate_cnt,
            COUNT(CASE WHEN fcr_trend='worsening'            THEN 1 END) AS worsening_cnt
        FROM dish_cost_compression
        WHERE store_id = :store_id AND period = :period
    """)
    row = (await db.execute(sql, {"store_id": store_id, "period": period})).fetchone()
    if not row or not row[0]:
        return None
    return {
        "compression_dish_count": int(row[0]),
        "total_compression_opportunity": round(float(row[1] or 0), 2),
        "total_expected_saving": round(float(row[2] or 0), 2),
        "renegotiate_count": int(row[3]),
        "worsening_fcr_count": int(row[4]),
    }


# ── 主汇总函数 ─────────────────────────────────────────────────────────────────


async def _upsert_summary(db: AsyncSession, rec: dict) -> None:
    sql = text("""
        INSERT INTO dish_monthly_summaries (
            store_id, period, prev_period,
            total_dishes, total_revenue, prev_revenue, revenue_delta_pct,
            avg_health_score, excellent_count, good_count, fair_count, poor_count,
            immediate_action_count,
            star_count, cash_cow_count, question_mark_count, dog_count,
            matrix_total_impact_yuan,
            pvm_dish_count, total_pvm_delta, total_price_effect, total_volume_effect,
            dominant_driver,
            compression_dish_count, total_compression_opportunity,
            total_expected_saving, renegotiate_count, worsening_fcr_count,
            data_sources_available, insight_text,
            generated_at, updated_at
        ) VALUES (
            :store_id, :period, :prev_period,
            :total_dishes, :total_revenue, :prev_revenue, :revenue_delta_pct,
            :avg_health_score, :excellent_count, :good_count, :fair_count, :poor_count,
            :immediate_action_count,
            :star_count, :cash_cow_count, :question_mark_count, :dog_count,
            :matrix_total_impact_yuan,
            :pvm_dish_count, :total_pvm_delta, :total_price_effect, :total_volume_effect,
            :dominant_driver,
            :compression_dish_count, :total_compression_opportunity,
            :total_expected_saving, :renegotiate_count, :worsening_fcr_count,
            :data_sources_available, :insight_text,
            NOW(), NOW()
        )
        ON CONFLICT (store_id, period) DO UPDATE SET
            prev_period               = EXCLUDED.prev_period,
            total_dishes              = EXCLUDED.total_dishes,
            total_revenue             = EXCLUDED.total_revenue,
            prev_revenue              = EXCLUDED.prev_revenue,
            revenue_delta_pct         = EXCLUDED.revenue_delta_pct,
            avg_health_score          = EXCLUDED.avg_health_score,
            excellent_count           = EXCLUDED.excellent_count,
            good_count                = EXCLUDED.good_count,
            fair_count                = EXCLUDED.fair_count,
            poor_count                = EXCLUDED.poor_count,
            immediate_action_count    = EXCLUDED.immediate_action_count,
            star_count                = EXCLUDED.star_count,
            cash_cow_count            = EXCLUDED.cash_cow_count,
            question_mark_count       = EXCLUDED.question_mark_count,
            dog_count                 = EXCLUDED.dog_count,
            matrix_total_impact_yuan  = EXCLUDED.matrix_total_impact_yuan,
            pvm_dish_count            = EXCLUDED.pvm_dish_count,
            total_pvm_delta           = EXCLUDED.total_pvm_delta,
            total_price_effect        = EXCLUDED.total_price_effect,
            total_volume_effect       = EXCLUDED.total_volume_effect,
            dominant_driver           = EXCLUDED.dominant_driver,
            compression_dish_count    = EXCLUDED.compression_dish_count,
            total_compression_opportunity = EXCLUDED.total_compression_opportunity,
            total_expected_saving     = EXCLUDED.total_expected_saving,
            renegotiate_count         = EXCLUDED.renegotiate_count,
            worsening_fcr_count       = EXCLUDED.worsening_fcr_count,
            data_sources_available    = EXCLUDED.data_sources_available,
            insight_text              = EXCLUDED.insight_text,
            updated_at                = NOW()
    """)
    await db.execute(sql, rec)


async def build_dish_monthly_summary(db: AsyncSession, store_id: str, period: str) -> dict:
    """
    聚合 5 个菜品分析数据源，生成并幂等写入月度汇总。
    返回完整的汇总 dict。
    """
    prev_period = _prev_period(period)

    prof = await _fetch_profitability_summary(db, store_id, period, prev_period)
    health = await _fetch_health_summary(db, store_id, period)
    matrix = await _fetch_matrix_summary(db, store_id, period)
    attrib = await _fetch_attribution_summary(db, store_id, period)
    compr = await _fetch_compression_summary(db, store_id, period)

    if prof is None:
        await db.commit()
        return {
            "store_id": store_id,
            "period": period,
            "error": "无法获取营收基线数据（dish_profitability_records），请先写入本期盈利数据",
        }

    total_dishes = prof["total_dishes"]
    total_revenue = prof["total_revenue"]
    prev_revenue = prof.get("prev_revenue")
    rev_delta_pct = compute_revenue_delta_pct(total_revenue, prev_revenue or 0) if prev_revenue else None

    data_src = compute_data_sources_available(prof, health, matrix, attrib, compr)

    insight = generate_insight_text(
        total_dishes=total_dishes,
        revenue_delta_pct=rev_delta_pct,
        avg_health_score=health["avg_health_score"] if health else None,
        star_count=matrix["star_count"] if matrix else None,
        dog_count=matrix["dog_count"] if matrix else None,
        total_expected_saving=compr["total_expected_saving"] if compr else None,
        dominant_driver=attrib["dominant_driver"] if attrib else None,
        worsening_fcr_count=compr["worsening_fcr_count"] if compr else None,
    )

    rec: dict = {
        "store_id": store_id,
        "period": period,
        "prev_period": prev_period,
        "total_dishes": total_dishes,
        "total_revenue": total_revenue,
        "prev_revenue": prev_revenue,
        "revenue_delta_pct": rev_delta_pct,
        # health
        "avg_health_score": health["avg_health_score"] if health else None,
        "excellent_count": health["excellent_count"] if health else None,
        "good_count": health["good_count"] if health else None,
        "fair_count": health["fair_count"] if health else None,
        "poor_count": health["poor_count"] if health else None,
        "immediate_action_count": health["immediate_action_count"] if health else None,
        # matrix
        "star_count": matrix["star_count"] if matrix else None,
        "cash_cow_count": matrix["cash_cow_count"] if matrix else None,
        "question_mark_count": matrix["question_mark_count"] if matrix else None,
        "dog_count": matrix["dog_count"] if matrix else None,
        "matrix_total_impact_yuan": matrix["matrix_total_impact_yuan"] if matrix else None,
        # attribution
        "pvm_dish_count": attrib["pvm_dish_count"] if attrib else None,
        "total_pvm_delta": attrib["total_pvm_delta"] if attrib else None,
        "total_price_effect": attrib["total_price_effect"] if attrib else None,
        "total_volume_effect": attrib["total_volume_effect"] if attrib else None,
        "dominant_driver": attrib["dominant_driver"] if attrib else None,
        # compression
        "compression_dish_count": compr["compression_dish_count"] if compr else None,
        "total_compression_opportunity": compr["total_compression_opportunity"] if compr else None,
        "total_expected_saving": compr["total_expected_saving"] if compr else None,
        "renegotiate_count": compr["renegotiate_count"] if compr else None,
        "worsening_fcr_count": compr["worsening_fcr_count"] if compr else None,
        # meta
        "data_sources_available": data_src,
        "insight_text": insight,
    }

    await _upsert_summary(db, rec)
    await db.commit()
    return rec


async def get_dish_monthly_summary(db: AsyncSession, store_id: str, period: str) -> Optional[dict]:
    """查询单期月度汇总。"""
    sql = text("""
        SELECT
            store_id, period, prev_period,
            total_dishes, total_revenue, prev_revenue, revenue_delta_pct,
            avg_health_score, excellent_count, good_count, fair_count, poor_count,
            immediate_action_count,
            star_count, cash_cow_count, question_mark_count, dog_count,
            matrix_total_impact_yuan,
            pvm_dish_count, total_pvm_delta, total_price_effect, total_volume_effect,
            dominant_driver,
            compression_dish_count, total_compression_opportunity,
            total_expected_saving, renegotiate_count, worsening_fcr_count,
            data_sources_available, insight_text, generated_at
        FROM dish_monthly_summaries
        WHERE store_id = :store_id AND period = :period
    """)
    row = (await db.execute(sql, {"store_id": store_id, "period": period})).fetchone()
    if not row:
        return None
    cols = [
        "store_id",
        "period",
        "prev_period",
        "total_dishes",
        "total_revenue",
        "prev_revenue",
        "revenue_delta_pct",
        "avg_health_score",
        "excellent_count",
        "good_count",
        "fair_count",
        "poor_count",
        "immediate_action_count",
        "star_count",
        "cash_cow_count",
        "question_mark_count",
        "dog_count",
        "matrix_total_impact_yuan",
        "pvm_dish_count",
        "total_pvm_delta",
        "total_price_effect",
        "total_volume_effect",
        "dominant_driver",
        "compression_dish_count",
        "total_compression_opportunity",
        "total_expected_saving",
        "renegotiate_count",
        "worsening_fcr_count",
        "data_sources_available",
        "insight_text",
        "generated_at",
    ]
    return dict(zip(cols, row))


async def get_summary_history(db: AsyncSession, store_id: str, periods: int = 6) -> list[dict]:
    """查询近 N 期月度汇总（用于趋势对比）。"""
    sql = text("""
        SELECT
            period,
            total_dishes, total_revenue, revenue_delta_pct,
            avg_health_score,
            star_count, dog_count,
            total_compression_opportunity, total_expected_saving,
            total_pvm_delta, dominant_driver,
            data_sources_available, insight_text
        FROM dish_monthly_summaries
        WHERE store_id = :store_id
        ORDER BY period DESC
        LIMIT :periods
    """)
    rows = (await db.execute(sql, {"store_id": store_id, "periods": periods})).fetchall()
    cols = [
        "period",
        "total_dishes",
        "total_revenue",
        "revenue_delta_pct",
        "avg_health_score",
        "star_count",
        "dog_count",
        "total_compression_opportunity",
        "total_expected_saving",
        "total_pvm_delta",
        "dominant_driver",
        "data_sources_available",
        "insight_text",
    ]
    return [dict(zip(cols, r)) for r in rows]
