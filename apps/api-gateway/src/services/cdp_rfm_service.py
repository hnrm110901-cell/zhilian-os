"""
CDP RFM Service — 基于 consumer_id 的统一 RFM 重算（Sprint 2）

Sprint 2 KPI: RFM 偏差 < 5%

核心改进：
1. 基于 consumer_id 而非 customer_id（手机号），跨门店统一计算
2. 标准化 R/F/M 1-5 评分 + S1-S5 等级
3. 同步更新 ConsumerIdentity + PrivateDomainMember 两侧 RFM
4. 偏差校验：对比 CDP RFM 与旧 RFM 的差异率
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy import text as _text
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.consumer_identity import ConsumerIdentity
from src.models.order import Order
from src.models.private_domain import PrivateDomainMember

logger = logging.getLogger(__name__)


# ── 纯函数：RFM 评分逻辑 ─────────────────────────────────────────


def score_recency(days: int) -> int:
    """R评分：距最近消费天数 → 1-5（越近越高）"""
    if days <= 7:
        return 5
    if days <= 14:
        return 4
    if days <= 30:
        return 3
    if days <= 60:
        return 2
    return 1


def score_frequency(count: int) -> int:
    """F评分：消费频次 → 1-5（越多越高）"""
    if count >= 20:
        return 5
    if count >= 10:
        return 4
    if count >= 5:
        return 3
    if count >= 2:
        return 2
    return 1


def score_monetary(amount_fen: int) -> int:
    """M评分：消费金额（分）→ 1-5（越多越高）"""
    yuan = amount_fen / 100
    if yuan >= 5000:
        return 5
    if yuan >= 2000:
        return 4
    if yuan >= 800:
        return 3
    if yuan >= 200:
        return 2
    return 1


def classify_rfm_level(r: int, f: int, m: int) -> str:
    """
    RFM → S1-S5 等级

    S1 = 核心客户（高R+高F+高M）
    S2 = 成长客户（中高频）
    S3 = 普通客户
    S4 = 待挽回客户（低R）
    S5 = 流失客户（低R+低F+低M）
    """
    total = r + f + m
    if total >= 13:
        return "S1"
    if total >= 10:
        return "S2"
    if total >= 7:
        return "S3"
    if total >= 4:
        return "S4"
    return "S5"


def compute_risk_score(r: int, f: int, m: int) -> float:
    """
    流失风险分（0-1，越高越危险）

    基于 R 为主因子（占 60%），F 和 M 为辅（各 20%）
    """
    # 反转：R=1 → risk 高，R=5 → risk 低
    r_risk = (5 - r) / 4  # 0-1
    f_risk = (5 - f) / 4
    m_risk = (5 - m) / 4
    return round(0.6 * r_risk + 0.2 * f_risk + 0.2 * m_risk, 4)


class CDPRFMService:
    """CDP 统一 RFM 重算服务"""

    async def recalculate_all(
        self,
        db: AsyncSession,
        store_id: Optional[str] = None,
    ) -> dict:
        """
        基于 consumer_id 重算全量 RFM。

        步骤：
        1. 从 orders 表按 consumer_id 聚合 R/F/M 原始值
        2. 用纯函数计算 1-5 评分 + S1-S5 等级
        3. 同步更新 ConsumerIdentity 和 PrivateDomainMember

        返回：{"consumers_updated": N, "members_updated": M}
        """
        # Step 1: 聚合 orders 中有 consumer_id 的记录
        where_clause = "WHERE o.consumer_id IS NOT NULL AND o.status != 'cancelled'"
        params = {}
        if store_id:
            where_clause += " AND o.store_id = :store_id"
            params["store_id"] = store_id

        agg_sql = _text(f"""
            SELECT
                o.consumer_id,
                EXTRACT(DAY FROM (NOW() - MAX(o.order_time)))::int AS recency_days,
                COUNT(*)::int AS frequency,
                COALESCE(SUM(
                    CASE
                        WHEN o.total_amount > 1000 THEN o.total_amount
                        ELSE o.total_amount * 100
                    END
                ), 0)::bigint AS monetary_fen
            FROM orders o
            {where_clause}
            GROUP BY o.consumer_id
        """)

        result = await db.execute(agg_sql, params)
        rows = result.all()

        consumers_updated = 0
        members_updated = 0

        for row in rows:
            cid = row[0]
            recency = row[1] or 0
            freq = row[2] or 0
            monetary = int(row[3] or 0)

            r = score_recency(recency)
            f = score_frequency(freq)
            m = score_monetary(monetary)
            level = classify_rfm_level(r, f, m)
            risk = compute_risk_score(r, f, m)

            # Update ConsumerIdentity
            await db.execute(
                update(ConsumerIdentity)
                .where(ConsumerIdentity.id == cid)
                .values(
                    rfm_recency_days=recency,
                    rfm_frequency=freq,
                    rfm_monetary_fen=monetary,
                    total_order_count=freq,
                    total_order_amount_fen=monetary,
                )
            )
            consumers_updated += 1

            # Update PrivateDomainMember（所有关联门店的记录）
            member_where = [PrivateDomainMember.consumer_id == cid]
            if store_id:
                member_where.append(PrivateDomainMember.store_id == store_id)

            r2 = await db.execute(
                update(PrivateDomainMember)
                .where(and_(*member_where))
                .values(
                    recency_days=recency,
                    frequency=freq,
                    monetary=monetary,
                    r_score=r,
                    f_score=f,
                    m_score=m,
                    rfm_level=level,
                    risk_score=risk,
                    rfm_updated_at=datetime.utcnow(),
                )
            )
            members_updated += r2.rowcount

        await db.flush()
        logger.info(
            "CDP RFM recalculated: consumers=%d members=%d",
            consumers_updated,
            members_updated,
        )
        return {
            "consumers_updated": consumers_updated,
            "members_updated": members_updated,
        }

    async def compute_deviation(
        self,
        db: AsyncSession,
        store_id: Optional[str] = None,
    ) -> dict:
        """
        计算 CDP RFM 与 ConsumerIdentity RFM 的偏差率。

        Sprint 2 KPI: 偏差 < 5%

        偏差定义：PrivateDomainMember.rfm_level 与基于 consumer_id 重算的
        rfm_level 不一致的比例。
        """
        where = ""
        params = {}
        if store_id:
            where = "AND m.store_id = :store_id"
            params["store_id"] = store_id

        sql = _text(f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN m.rfm_level != c.rfm_level_computed THEN 1 ELSE 0 END) AS deviated
            FROM (
                SELECT
                    consumer_id,
                    CASE
                        WHEN rfm_recency_days IS NULL THEN 'S3'
                        WHEN (
                            CASE WHEN rfm_recency_days <= 7 THEN 5
                                 WHEN rfm_recency_days <= 14 THEN 4
                                 WHEN rfm_recency_days <= 30 THEN 3
                                 WHEN rfm_recency_days <= 60 THEN 2
                                 ELSE 1 END
                            +
                            CASE WHEN rfm_frequency >= 20 THEN 5
                                 WHEN rfm_frequency >= 10 THEN 4
                                 WHEN rfm_frequency >= 5 THEN 3
                                 WHEN rfm_frequency >= 2 THEN 2
                                 ELSE 1 END
                            +
                            CASE WHEN rfm_monetary_fen >= 500000 THEN 5
                                 WHEN rfm_monetary_fen >= 200000 THEN 4
                                 WHEN rfm_monetary_fen >= 80000 THEN 3
                                 WHEN rfm_monetary_fen >= 20000 THEN 2
                                 ELSE 1 END
                        ) >= 13 THEN 'S1'
                        WHEN (
                            CASE WHEN rfm_recency_days <= 7 THEN 5
                                 WHEN rfm_recency_days <= 14 THEN 4
                                 WHEN rfm_recency_days <= 30 THEN 3
                                 WHEN rfm_recency_days <= 60 THEN 2
                                 ELSE 1 END
                            +
                            CASE WHEN rfm_frequency >= 20 THEN 5
                                 WHEN rfm_frequency >= 10 THEN 4
                                 WHEN rfm_frequency >= 5 THEN 3
                                 WHEN rfm_frequency >= 2 THEN 2
                                 ELSE 1 END
                            +
                            CASE WHEN rfm_monetary_fen >= 500000 THEN 5
                                 WHEN rfm_monetary_fen >= 200000 THEN 4
                                 WHEN rfm_monetary_fen >= 80000 THEN 3
                                 WHEN rfm_monetary_fen >= 20000 THEN 2
                                 ELSE 1 END
                        ) >= 10 THEN 'S2'
                        WHEN (
                            CASE WHEN rfm_recency_days <= 7 THEN 5
                                 WHEN rfm_recency_days <= 14 THEN 4
                                 WHEN rfm_recency_days <= 30 THEN 3
                                 WHEN rfm_recency_days <= 60 THEN 2
                                 ELSE 1 END
                            +
                            CASE WHEN rfm_frequency >= 20 THEN 5
                                 WHEN rfm_frequency >= 10 THEN 4
                                 WHEN rfm_frequency >= 5 THEN 3
                                 WHEN rfm_frequency >= 2 THEN 2
                                 ELSE 1 END
                            +
                            CASE WHEN rfm_monetary_fen >= 500000 THEN 5
                                 WHEN rfm_monetary_fen >= 200000 THEN 4
                                 WHEN rfm_monetary_fen >= 80000 THEN 3
                                 WHEN rfm_monetary_fen >= 20000 THEN 2
                                 ELSE 1 END
                        ) >= 7 THEN 'S3'
                        WHEN (
                            CASE WHEN rfm_recency_days <= 7 THEN 5
                                 WHEN rfm_recency_days <= 14 THEN 4
                                 WHEN rfm_recency_days <= 30 THEN 3
                                 WHEN rfm_recency_days <= 60 THEN 2
                                 ELSE 1 END
                            +
                            CASE WHEN rfm_frequency >= 20 THEN 5
                                 WHEN rfm_frequency >= 10 THEN 4
                                 WHEN rfm_frequency >= 5 THEN 3
                                 WHEN rfm_frequency >= 2 THEN 2
                                 ELSE 1 END
                            +
                            CASE WHEN rfm_monetary_fen >= 500000 THEN 5
                                 WHEN rfm_monetary_fen >= 200000 THEN 4
                                 WHEN rfm_monetary_fen >= 80000 THEN 3
                                 WHEN rfm_monetary_fen >= 20000 THEN 2
                                 ELSE 1 END
                        ) >= 4 THEN 'S4'
                        ELSE 'S5'
                    END AS rfm_level_computed
                FROM consumer_identities
                WHERE is_merged = false
            ) c
            JOIN private_domain_members m ON m.consumer_id = c.consumer_id
            WHERE m.is_active = true {where}
        """)

        result = await db.execute(sql, params)
        row = result.one_or_none()
        if not row or not row[0]:
            return {"total": 0, "deviated": 0, "deviation_rate": 0.0}

        total = row[0]
        deviated = row[1] or 0
        rate = round(deviated / total, 4) if total > 0 else 0.0

        return {
            "total": total,
            "deviated": deviated,
            "deviation_rate": rate,
            "kpi_met": rate < 0.05,  # Sprint 2 KPI: < 5%
        }

    async def backfill_members(
        self,
        db: AsyncSession,
        store_id: Optional[str] = None,
        batch_size: int = 500,
    ) -> dict:
        """
        将 PrivateDomainMember 链接到 ConsumerIdentity。

        策略：customer_id 当作手机号 → 查 ConsumerIdentity.primary_phone
        """
        from src.services.identity_resolution_service import identity_resolution_service

        where_clause = [
            PrivateDomainMember.consumer_id.is_(None),
            PrivateDomainMember.is_active.is_(True),
        ]
        if store_id:
            where_clause.append(PrivateDomainMember.store_id == store_id)

        stmt = (
            select(
                PrivateDomainMember.id,
                PrivateDomainMember.customer_id,
                PrivateDomainMember.store_id,
                PrivateDomainMember.wechat_openid,
            )
            .where(and_(*where_clause))
            .limit(batch_size)
        )
        result = await db.execute(stmt)
        rows = result.all()

        total = len(rows)
        linked = 0
        failed = 0

        for member_id, customer_id, sid, openid in rows:
            try:
                # customer_id 视为手机号
                phone = customer_id.strip() if customer_id else ""
                if not phone:
                    failed += 1
                    continue

                consumer_id = await identity_resolution_service.resolve(
                    db,
                    phone,
                    store_id=sid,
                    wechat_openid=openid,
                    source="private_domain_backfill",
                )

                await db.execute(
                    update(PrivateDomainMember).where(PrivateDomainMember.id == member_id).values(consumer_id=consumer_id)
                )
                linked += 1
            except Exception as e:
                logger.warning("CDP member backfill id=%s failed: %s", member_id, e)
                failed += 1

        await db.flush()
        logger.info(
            "CDP member backfill: total=%d linked=%d failed=%d",
            total,
            linked,
            failed,
        )
        return {"total": total, "linked": linked, "failed": failed}


# 全局单例
cdp_rfm_service = CDPRFMService()
