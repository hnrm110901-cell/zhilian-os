"""
集团BI大屏数据服务 — Phase 3

提供集团总览、品牌横向对比、会员生命周期漏斗、营销ROI、区域/门店排行榜。
所有金额字段同时返回 _fen（分）和 _yuan（元字符串，¥格式）两个字段。
所有聚合查询必须用 group_id/brand_id 做范围过滤，禁止全表扫描。
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


def _fen_to_yuan(fen: Optional[int]) -> str:
    """分 → 元字符串（¥12,345.67）"""
    if fen is None:
        return "¥0.00"
    return f"¥{fen / 100:,.2f}"


def _pct_change(current: float, previous: float) -> Optional[float]:
    """计算百分比变化，previous 为 0 时返回 None"""
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 2)


class GroupBIService:
    """集团BI大屏数据服务"""

    # ------------------------------------------------------------------ #
    # 集团总览大屏
    # ------------------------------------------------------------------ #

    async def get_group_overview(
        self,
        group_id: str,
        date_range: Tuple[datetime, datetime],
        session: AsyncSession,
    ) -> Dict[str, Any]:
        """
        集团总览大屏数据。
        返回：
        - total_gmv_fen / total_gmv_yuan：集团总GMV
        - gmv_by_brand：各品牌GMV + 同比变化
        - total_members：集团总会员数（去重 by consumer_id）
        - new_members_count：期间新增
        - cross_brand_consumers：跨品牌消费人数
        - overall_repurchase_rate：复购率
        - active_stores：活跃门店数
        """
        start_dt, end_dt = date_range
        # 同比周期：往前推同等长度
        period_days = (end_dt - start_dt).days or 1
        prev_start = start_dt - timedelta(days=period_days)
        prev_end = start_dt

        # 1. GMV by brand（当期）
        gmv_sql = text("""
            SELECT
                bcp.brand_id,
                SUM(bcp.brand_order_amount_fen) AS gmv_fen,
                COUNT(DISTINCT bcp.consumer_id) AS member_count
            FROM brand_consumer_profiles bcp
            WHERE bcp.group_id = :group_id
              AND bcp.brand_last_order_at >= :start_dt
              AND bcp.brand_last_order_at < :end_dt
            GROUP BY bcp.brand_id
        """)
        rows = await session.execute(
            gmv_sql, {"group_id": group_id, "start_dt": start_dt, "end_dt": end_dt}
        )
        current_gmv = {r.brand_id: {"gmv_fen": int(r.gmv_fen or 0), "member_count": int(r.member_count or 0)}
                       for r in rows}

        # 2. GMV by brand（前期，用于计算同比）
        rows_prev = await session.execute(
            gmv_sql, {"group_id": group_id, "start_dt": prev_start, "end_dt": prev_end}
        )
        prev_gmv = {r.brand_id: int(r.gmv_fen or 0) for r in rows_prev}

        gmv_by_brand = []
        total_gmv_fen = 0
        for brand_id, data in current_gmv.items():
            fen = data["gmv_fen"]
            total_gmv_fen += fen
            gmv_change_pct = _pct_change(fen, prev_gmv.get(brand_id, 0))
            gmv_by_brand.append({
                "brand_id": brand_id,
                "gmv_fen": fen,
                "gmv_yuan": _fen_to_yuan(fen),
                "gmv_change_pct": gmv_change_pct,
                "member_count": data["member_count"],
            })
        gmv_by_brand.sort(key=lambda x: x["gmv_fen"], reverse=True)

        # 3. 集团总会员数（去重）+ 新增 + 跨品牌
        member_sql = text("""
            SELECT
                COUNT(DISTINCT consumer_id) AS total_members,
                COUNT(DISTINCT CASE WHEN brand_first_order_at >= :start_dt THEN consumer_id END)
                    AS new_members_count
            FROM brand_consumer_profiles
            WHERE group_id = :group_id
        """)
        m_row = (await session.execute(member_sql, {"group_id": group_id, "start_dt": start_dt})).first()
        total_members = int(m_row.total_members or 0) if m_row else 0
        new_members_count = int(m_row.new_members_count or 0) if m_row else 0

        cross_sql = text("""
            SELECT COUNT(*) AS cross_count
            FROM (
                SELECT consumer_id
                FROM brand_consumer_profiles
                WHERE group_id = :group_id
                  AND brand_order_count > 0
                GROUP BY consumer_id
                HAVING COUNT(DISTINCT brand_id) > 1
            ) sub
        """)
        cross_row = (await session.execute(cross_sql, {"group_id": group_id})).first()
        cross_brand_consumers = int(cross_row.cross_count or 0) if cross_row else 0

        # 4. 整体复购率（brand_order_count >= 2 / 总人数）
        repurchase_sql = text("""
            SELECT
                COUNT(DISTINCT CASE WHEN brand_order_count >= 2 THEN consumer_id END)::float
                    / NULLIF(COUNT(DISTINCT consumer_id), 0) AS repurchase_rate
            FROM brand_consumer_profiles
            WHERE group_id = :group_id
        """)
        rr_row = (await session.execute(repurchase_sql, {"group_id": group_id})).first()
        overall_repurchase_rate = round(float(rr_row.repurchase_rate or 0) * 100, 2) if rr_row else 0.0

        # 5. 活跃门店数（最近30天有消费记录）
        store_sql = text("""
            SELECT COUNT(DISTINCT store_id) AS active_stores
            FROM orders
            WHERE store_id IN (
                SELECT id FROM stores WHERE group_id = :group_id
            )
            AND created_at >= NOW() - INTERVAL '30 days'
        """)
        try:
            store_row = (await session.execute(store_sql, {"group_id": group_id})).first()
            active_stores = int(store_row.active_stores or 0) if store_row else 0
        except Exception as exc:
            logger.warning("active_stores 查询降级", error=str(exc))
            active_stores = 0

        return {
            "period": {
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
            },
            "total_gmv_fen": total_gmv_fen,
            "total_gmv_yuan": _fen_to_yuan(total_gmv_fen),
            "gmv_by_brand": gmv_by_brand,
            "total_members": total_members,
            "new_members_count": new_members_count,
            "cross_brand_consumers": cross_brand_consumers,
            "overall_repurchase_rate_pct": overall_repurchase_rate,
            "active_stores": active_stores,
        }

    # ------------------------------------------------------------------ #
    # 品牌横向对比（时序）
    # ------------------------------------------------------------------ #

    async def get_brand_comparison(
        self,
        group_id: str,
        brand_ids: List[str],
        metric: str,
        period: str,
        session: AsyncSession,
    ) -> List[Dict]:
        """
        品牌横向对比时序数据。
        metric: gmv / new_members / repurchase_rate / avg_order_fen / rfm_distribution
        period: daily / weekly / monthly
        返回：[{date_label, brand_id, value}]，支持多品牌折线图。
        """
        _valid_metrics = {"gmv", "new_members", "repurchase_rate", "avg_order_fen", "rfm_distribution"}
        _valid_periods = {"daily", "weekly", "monthly"}

        if metric not in _valid_metrics:
            raise ValueError(f"不支持的 metric: {metric!r}，合法值: {_valid_metrics}")
        if period not in _valid_periods:
            raise ValueError(f"不支持的 period: {period!r}，合法值: {_valid_periods}")
        if not brand_ids:
            return []

        # 防止 SQL 注入：brand_ids 只能是字符串列表
        clean_brand_ids = [str(b) for b in brand_ids]

        period_trunc = {
            "daily": "day",
            "weekly": "week",
            "monthly": "month",
        }[period]

        # 使用参数化绑定，不拼接 brand_id 字符串
        # 通过 ANY(:brand_ids) 传递数组
        if metric == "gmv":
            sql = text("""
                SELECT
                    date_trunc(:period_trunc, brand_last_order_at) AS date_label,
                    brand_id,
                    SUM(brand_order_amount_fen) AS value_fen
                FROM brand_consumer_profiles
                WHERE group_id = :group_id
                  AND brand_id = ANY(:brand_ids)
                  AND brand_last_order_at >= NOW() - INTERVAL '90 days'
                GROUP BY 1, 2
                ORDER BY 1, 2
            """)
            rows = await session.execute(sql, {
                "group_id": group_id,
                "brand_ids": clean_brand_ids,
                "period_trunc": period_trunc,
            })
            return [
                {
                    "date_label": str(r.date_label)[:10],
                    "brand_id": r.brand_id,
                    "value_fen": int(r.value_fen or 0),
                    "value_yuan": _fen_to_yuan(int(r.value_fen or 0)),
                }
                for r in rows
            ]

        elif metric == "new_members":
            sql = text("""
                SELECT
                    date_trunc(:period_trunc, brand_first_order_at) AS date_label,
                    brand_id,
                    COUNT(DISTINCT consumer_id) AS value
                FROM brand_consumer_profiles
                WHERE group_id = :group_id
                  AND brand_id = ANY(:brand_ids)
                  AND brand_first_order_at >= NOW() - INTERVAL '90 days'
                GROUP BY 1, 2
                ORDER BY 1, 2
            """)
            rows = await session.execute(sql, {
                "group_id": group_id,
                "brand_ids": clean_brand_ids,
                "period_trunc": period_trunc,
            })
            return [
                {
                    "date_label": str(r.date_label)[:10],
                    "brand_id": r.brand_id,
                    "value": int(r.value or 0),
                }
                for r in rows
            ]

        elif metric == "repurchase_rate":
            sql = text("""
                SELECT
                    date_trunc(:period_trunc, brand_last_order_at) AS date_label,
                    brand_id,
                    COUNT(DISTINCT CASE WHEN brand_order_count >= 2 THEN consumer_id END)::float
                        / NULLIF(COUNT(DISTINCT consumer_id), 0) AS value
                FROM brand_consumer_profiles
                WHERE group_id = :group_id
                  AND brand_id = ANY(:brand_ids)
                  AND brand_last_order_at >= NOW() - INTERVAL '90 days'
                GROUP BY 1, 2
                ORDER BY 1, 2
            """)
            rows = await session.execute(sql, {
                "group_id": group_id,
                "brand_ids": clean_brand_ids,
                "period_trunc": period_trunc,
            })
            return [
                {
                    "date_label": str(r.date_label)[:10],
                    "brand_id": r.brand_id,
                    "value_pct": round(float(r.value or 0) * 100, 2),
                }
                for r in rows
            ]

        elif metric == "avg_order_fen":
            sql = text("""
                SELECT
                    date_trunc(:period_trunc, brand_last_order_at) AS date_label,
                    brand_id,
                    CASE WHEN SUM(brand_order_count) > 0
                         THEN SUM(brand_order_amount_fen) / SUM(brand_order_count)
                         ELSE 0
                    END AS value_fen
                FROM brand_consumer_profiles
                WHERE group_id = :group_id
                  AND brand_id = ANY(:brand_ids)
                  AND brand_last_order_at >= NOW() - INTERVAL '90 days'
                GROUP BY 1, 2
                ORDER BY 1, 2
            """)
            rows = await session.execute(sql, {
                "group_id": group_id,
                "brand_ids": clean_brand_ids,
                "period_trunc": period_trunc,
            })
            return [
                {
                    "date_label": str(r.date_label)[:10],
                    "brand_id": r.brand_id,
                    "value_fen": int(r.value_fen or 0),
                    "value_yuan": _fen_to_yuan(int(r.value_fen or 0)),
                }
                for r in rows
            ]

        else:  # rfm_distribution
            # 返回各品牌的 lifecycle_state 分布（静态快照，不分时间段）
            sql = text("""
                SELECT
                    brand_id,
                    lifecycle_state,
                    COUNT(DISTINCT consumer_id) AS value
                FROM brand_consumer_profiles
                WHERE group_id = :group_id
                  AND brand_id = ANY(:brand_ids)
                GROUP BY 1, 2
                ORDER BY 1, 2
            """)
            rows = await session.execute(sql, {
                "group_id": group_id,
                "brand_ids": clean_brand_ids,
            })
            return [
                {
                    "brand_id": r.brand_id,
                    "lifecycle_state": r.lifecycle_state,
                    "value": int(r.value or 0),
                }
                for r in rows
            ]

    # ------------------------------------------------------------------ #
    # 会员生命周期漏斗
    # ------------------------------------------------------------------ #

    async def get_member_funnel(
        self,
        brand_id: str,
        group_id: str,
        session: AsyncSession,
    ) -> Dict[str, Any]:
        """
        会员生命周期漏斗。
        返回各生命周期状态的人数：lead→registered→repeat→vip→at_risk→dormant→lost
        及相邻状态的转化率。
        """
        sql = text("""
            SELECT lifecycle_state, COUNT(DISTINCT consumer_id) AS cnt
            FROM brand_consumer_profiles
            WHERE brand_id = :brand_id
              AND group_id = :group_id
            GROUP BY lifecycle_state
        """)
        rows = await session.execute(sql, {"brand_id": brand_id, "group_id": group_id})
        state_map: Dict[str, int] = {r.lifecycle_state: int(r.cnt or 0) for r in rows}

        stages = ["lead", "registered", "repeat", "vip", "at_risk", "dormant", "lost"]
        funnel: List[Dict] = []
        for stage in stages:
            funnel.append({"stage": stage, "count": state_map.get(stage, 0)})

        # 计算相邻转化率：从 registered 开始向后流转
        conversion_rates: List[Dict] = []
        for i in range(len(funnel) - 1):
            from_stage = funnel[i]
            to_stage = funnel[i + 1]
            from_count = from_stage["count"]
            to_count = to_stage["count"]
            rate = round(to_count / from_count * 100, 2) if from_count > 0 else None
            conversion_rates.append({
                "from": from_stage["stage"],
                "to": to_stage["stage"],
                "conversion_rate_pct": rate,
            })

        total = sum(f["count"] for f in funnel)

        return {
            "brand_id": brand_id,
            "funnel": funnel,
            "conversion_rates": conversion_rates,
            "total_members": total,
        }

    # ------------------------------------------------------------------ #
    # 营销ROI
    # ------------------------------------------------------------------ #

    async def get_marketing_roi(
        self,
        brand_id: str,
        group_id: str,
        period_days: int = 30,
        session: Optional[AsyncSession] = None,
    ) -> Dict[str, Any]:
        """
        营销ROI汇总。
        查询 marketing_campaigns / campaign_conversions 表（降级返回空数据）。
        返回各渠道（短信/企微/Push）的：发送量、触达率、转化率、促成GMV、成本（分）、ROI。
        金额同时返回 _fen 和 _yuan。
        """
        channels = ["sms", "wecom", "push", "mini_program", "coupon"]

        async def _fetch(s: AsyncSession) -> Dict[str, Any]:
            try:
                sql = text("""
                    SELECT
                        channel,
                        COUNT(*)                                             AS sent_count,
                        SUM(CASE WHEN delivered THEN 1 ELSE 0 END)          AS delivered_count,
                        SUM(CASE WHEN converted THEN 1 ELSE 0 END)          AS converted_count,
                        COALESCE(SUM(gmv_attributed_fen), 0)                AS gmv_fen,
                        COALESCE(SUM(cost_fen), 0)                          AS cost_fen
                    FROM marketing_campaigns
                    WHERE brand_id = :brand_id
                      AND group_id = :group_id
                      AND sent_at >= NOW() - :period_days * INTERVAL '1 day'
                    GROUP BY channel
                """)
                rows = await s.execute(sql, {
                    "brand_id": brand_id,
                    "group_id": group_id,
                    "period_days": period_days,
                })
                channel_data = []
                total_gmv_fen = 0
                total_cost_fen = 0
                for r in rows:
                    sent = int(r.sent_count or 0)
                    delivered = int(r.delivered_count or 0)
                    converted = int(r.converted_count or 0)
                    gmv = int(r.gmv_fen or 0)
                    cost = int(r.cost_fen or 0)
                    roi = round(gmv / cost, 2) if cost > 0 else None
                    total_gmv_fen += gmv
                    total_cost_fen += cost
                    channel_data.append({
                        "channel": r.channel,
                        "sent_count": sent,
                        "delivery_rate_pct": round(delivered / sent * 100, 2) if sent > 0 else 0.0,
                        "conversion_rate_pct": round(converted / delivered * 100, 2) if delivered > 0 else 0.0,
                        "gmv_fen": gmv,
                        "gmv_yuan": _fen_to_yuan(gmv),
                        "cost_fen": cost,
                        "cost_yuan": _fen_to_yuan(cost),
                        "roi": roi,
                    })

                overall_roi = round(total_gmv_fen / total_cost_fen, 2) if total_cost_fen > 0 else None
                return {
                    "brand_id": brand_id,
                    "period_days": period_days,
                    "channels": channel_data,
                    "total_gmv_fen": total_gmv_fen,
                    "total_gmv_yuan": _fen_to_yuan(total_gmv_fen),
                    "total_cost_fen": total_cost_fen,
                    "total_cost_yuan": _fen_to_yuan(total_cost_fen),
                    "overall_roi": overall_roi,
                }

            except Exception as exc:
                logger.warning("marketing_roi 查询降级", brand_id=brand_id, error=str(exc))
                # 降级：返回空骨架
                return {
                    "brand_id": brand_id,
                    "period_days": period_days,
                    "channels": [],
                    "total_gmv_fen": 0,
                    "total_gmv_yuan": "¥0.00",
                    "total_cost_fen": 0,
                    "total_cost_yuan": "¥0.00",
                    "overall_roi": None,
                    "note": "营销数据暂无（marketing_campaigns 表尚未有数据）",
                }

        if session is not None:
            return await _fetch(session)

        from ..core.database import get_db_session
        async with get_db_session() as s:
            return await _fetch(s)

    # ------------------------------------------------------------------ #
    # 区域排行榜
    # ------------------------------------------------------------------ #

    async def get_region_ranking(
        self,
        brand_id: str,
        group_id: str,
        metric: str,
        top_n: int = 10,
        session: Optional[AsyncSession] = None,
    ) -> List[Dict]:
        """
        区域排行榜（GMV / 增速 / 复购率 / 新客数）。
        metric: gmv / growth / repurchase_rate / new_members
        """
        _valid_metrics = {"gmv", "growth", "repurchase_rate", "new_members"}
        if metric not in _valid_metrics:
            raise ValueError(f"不支持的 metric: {metric!r}")

        async def _fetch(s: AsyncSession) -> List[Dict]:
            if metric == "gmv":
                sql = text("""
                    SELECT
                        st.region_id,
                        COALESCE(r.name, st.region_id) AS region_name,
                        SUM(bcp.brand_order_amount_fen) AS gmv_fen,
                        COUNT(DISTINCT bcp.consumer_id) AS member_count
                    FROM brand_consumer_profiles bcp
                    JOIN stores st ON st.brand_id = :brand_id
                        AND bcp.brand_id = :brand_id
                    LEFT JOIN regions r ON r.id::varchar = st.region_id
                    WHERE bcp.group_id = :group_id
                      AND bcp.brand_last_order_at >= NOW() - INTERVAL '30 days'
                    GROUP BY st.region_id, r.name
                    ORDER BY gmv_fen DESC
                    LIMIT :top_n
                """)
                rows = await s.execute(sql, {
                    "brand_id": brand_id, "group_id": group_id, "top_n": top_n
                })
                return [
                    {
                        "rank": i + 1,
                        "region_id": r.region_id,
                        "region_name": r.region_name,
                        "gmv_fen": int(r.gmv_fen or 0),
                        "gmv_yuan": _fen_to_yuan(int(r.gmv_fen or 0)),
                        "member_count": int(r.member_count or 0),
                    }
                    for i, r in enumerate(rows)
                ]

            elif metric == "new_members":
                sql = text("""
                    SELECT
                        st.region_id,
                        COALESCE(r.name, st.region_id) AS region_name,
                        COUNT(DISTINCT bcp.consumer_id) AS new_members
                    FROM brand_consumer_profiles bcp
                    JOIN stores st ON st.brand_id = :brand_id
                        AND bcp.brand_id = :brand_id
                    LEFT JOIN regions r ON r.id::varchar = st.region_id
                    WHERE bcp.group_id = :group_id
                      AND bcp.brand_first_order_at >= NOW() - INTERVAL '30 days'
                    GROUP BY st.region_id, r.name
                    ORDER BY new_members DESC
                    LIMIT :top_n
                """)
                rows = await s.execute(sql, {
                    "brand_id": brand_id, "group_id": group_id, "top_n": top_n
                })
                return [
                    {
                        "rank": i + 1,
                        "region_id": r.region_id,
                        "region_name": r.region_name,
                        "new_members": int(r.new_members or 0),
                    }
                    for i, r in enumerate(rows)
                ]

            elif metric in {"repurchase_rate", "growth"}:
                # 聚合 brand_consumer_profiles，按 store.region_id 分组
                sql = text("""
                    SELECT
                        st.region_id,
                        COALESCE(r.name, st.region_id) AS region_name,
                        COUNT(DISTINCT CASE WHEN bcp.brand_order_count >= 2 THEN bcp.consumer_id END)::float
                            / NULLIF(COUNT(DISTINCT bcp.consumer_id), 0) AS repurchase_rate,
                        SUM(bcp.brand_order_amount_fen) AS gmv_fen_current
                    FROM brand_consumer_profiles bcp
                    JOIN stores st ON st.brand_id = :brand_id
                        AND bcp.brand_id = :brand_id
                    LEFT JOIN regions r ON r.id::varchar = st.region_id
                    WHERE bcp.group_id = :group_id
                    GROUP BY st.region_id, r.name
                    ORDER BY repurchase_rate DESC
                    LIMIT :top_n
                """)
                rows = await s.execute(sql, {
                    "brand_id": brand_id, "group_id": group_id, "top_n": top_n
                })
                return [
                    {
                        "rank": i + 1,
                        "region_id": r.region_id,
                        "region_name": r.region_name,
                        "repurchase_rate_pct": round(float(r.repurchase_rate or 0) * 100, 2),
                        "gmv_fen": int(r.gmv_fen_current or 0),
                        "gmv_yuan": _fen_to_yuan(int(r.gmv_fen_current or 0)),
                    }
                    for i, r in enumerate(rows)
                ]

            return []

        if session is not None:
            return await _fetch(session)

        from ..core.database import get_db_session
        async with get_db_session() as s:
            return await _fetch(s)

    # ------------------------------------------------------------------ #
    # 门店排行榜
    # ------------------------------------------------------------------ #

    async def get_store_ranking(
        self,
        brand_id: str,
        group_id: str,
        metric: str,
        top_n: int = 20,
        region_id: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> List[Dict]:
        """
        门店排行榜，支持按区域筛选。
        metric: gmv / new_members / repurchase_rate / avg_order_fen
        """
        _valid_metrics = {"gmv", "new_members", "repurchase_rate", "avg_order_fen"}
        if metric not in _valid_metrics:
            raise ValueError(f"不支持的 metric: {metric!r}")

        async def _fetch(s: AsyncSession) -> List[Dict]:
            # 尝试从 orders 表聚合门店级数据
            try:
                region_filter = ""
                params: Dict[str, Any] = {
                    "brand_id": brand_id, "group_id": group_id, "top_n": top_n
                }
                if region_id:
                    region_filter = "AND st.region_id = :region_id"
                    params["region_id"] = region_id

                if metric == "gmv":
                    order_col = "SUM(o.final_amount) DESC"
                    select_extra = ", SUM(o.final_amount) AS gmv_fen"
                elif metric == "new_members":
                    order_col = "COUNT(DISTINCT o.member_id) DESC"
                    select_extra = ", COUNT(DISTINCT o.member_id) AS new_members"
                elif metric == "repurchase_rate":
                    order_col = "repurchase_rate DESC"
                    select_extra = ""
                else:  # avg_order_fen
                    order_col = "AVG(o.final_amount) DESC"
                    select_extra = ", AVG(o.final_amount) AS avg_order_fen"

                if metric == "repurchase_rate":
                    sql = text(f"""
                        SELECT
                            st.id AS store_id,
                            st.name AS store_name,
                            st.region_id,
                            COUNT(DISTINCT CASE WHEN bcp.brand_order_count >= 2 THEN bcp.consumer_id END)::float
                                / NULLIF(COUNT(DISTINCT bcp.consumer_id), 0) AS repurchase_rate
                        FROM stores st
                        JOIN brand_consumer_profiles bcp ON bcp.brand_id = :brand_id
                            AND bcp.group_id = :group_id
                        WHERE st.brand_id = :brand_id {region_filter}
                        GROUP BY st.id, st.name, st.region_id
                        ORDER BY repurchase_rate DESC
                        LIMIT :top_n
                    """)
                    rows = await s.execute(sql, params)
                    return [
                        {
                            "rank": i + 1,
                            "store_id": str(r.store_id),
                            "store_name": r.store_name,
                            "region_id": r.region_id,
                            "repurchase_rate_pct": round(float(r.repurchase_rate or 0) * 100, 2),
                        }
                        for i, r in enumerate(rows)
                    ]
                else:
                    sql = text(f"""
                        SELECT
                            st.id AS store_id,
                            st.name AS store_name,
                            st.region_id
                            {select_extra}
                        FROM stores st
                        LEFT JOIN orders o ON o.store_id = st.id::varchar
                            AND o.created_at >= NOW() - INTERVAL '30 days'
                        WHERE st.brand_id = :brand_id {region_filter}
                        GROUP BY st.id, st.name, st.region_id
                        ORDER BY {order_col}
                        LIMIT :top_n
                    """)
                    rows = await s.execute(sql, params)
                    result = []
                    for i, r in enumerate(rows):
                        item: Dict[str, Any] = {
                            "rank": i + 1,
                            "store_id": str(r.store_id),
                            "store_name": r.store_name,
                            "region_id": r.region_id,
                        }
                        if metric == "gmv":
                            fen = int(r.gmv_fen or 0)
                            item["gmv_fen"] = fen
                            item["gmv_yuan"] = _fen_to_yuan(fen)
                        elif metric == "new_members":
                            item["new_members"] = int(r.new_members or 0)
                        elif metric == "avg_order_fen":
                            fen = int(r.avg_order_fen or 0)
                            item["avg_order_fen"] = fen
                            item["avg_order_yuan"] = _fen_to_yuan(fen)
                        result.append(item)
                    return result

            except Exception as exc:
                logger.warning("store_ranking 查询降级", brand_id=brand_id, error=str(exc))
                return []

        if session is not None:
            return await _fetch(session)

        from ..core.database import get_db_session
        async with get_db_session() as s:
            return await _fetch(s)


# 全局单例
group_bi_service = GroupBIService()
