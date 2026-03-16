"""
ReferralEngine Service — CDP驱动的裂变追踪（Sprint 4）

9-Agent 终态中的裂变能力，核心功能：
1. 裂变场景识别（大桌≥6人、生日宴、商务宴请、超级粉丝聚会）
2. 推荐人→被推荐人关系追踪（基于 consumer_id）
3. K-Factor 计算（病毒系数）
4. 裂变 ROI 追踪（推荐带来的新客营收）

Sprint 4 KPI: 裂变新客占比 ≥ 5%
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.consumer_identity import ConsumerIdentity
from src.models.order import Order
from src.models.private_domain import PrivateDomainMember
from src.models.reservation import Reservation

logger = logging.getLogger(__name__)


# ── 纯函数 ──────────────────────────────────────────────────────


def compute_k_factor(
    invites_sent: int,
    conversion_rate: float,
) -> float:
    """
    病毒系数 K = 邀请数 × 转化率

    K > 1 → 自增长（每个用户带来 > 1 个新用户）
    K = 0.3~1.0 → 健康裂变
    K < 0.3 → 裂变乏力
    """
    if invites_sent <= 0:
        return 0.0
    return round(invites_sent * conversion_rate, 4)


def classify_referral_scene(
    party_size: int,
    customer_name: str = "",
) -> dict:
    """
    识别裂变场景（4类高K值场景）

    返回：{scene, k_estimate, suggestion}
    """
    name = customer_name or ""
    if party_size >= 10:
        return {
            "scene": "banquet",
            "k_estimate": 2.5,
            "suggestion": "宴会后发送感谢卡+拼桌优惠券给每位来宾",
        }
    if any(kw in name for kw in ("生日", "birthday", "寿")):
        return {
            "scene": "birthday",
            "k_estimate": 2.0,
            "suggestion": "生日寿星专属朋友圈模板+「带朋友来享8折」裂变券",
        }
    if party_size >= 8:
        return {
            "scene": "business_dinner",
            "k_estimate": 1.5,
            "suggestion": "商务宴请结束发送定制电子感谢函+下次预订优惠",
        }
    if party_size >= 6:
        return {
            "scene": "fan_gathering",
            "k_estimate": 1.8,
            "suggestion": "超级粉丝聚餐感谢卡+「老带新双方各享优惠」裂变券",
        }
    return {
        "scene": "regular",
        "k_estimate": 0.0,
        "suggestion": "",
    }


def estimate_referral_value(
    avg_order_yuan: float,
    k_factor: float,
    referrer_count: int,
) -> dict:
    """
    估算裂变带来的预期营收

    公式：预期新客数 = referrer_count × K
          预期营收 = 新客数 × 客均消费 × 首次消费折扣(0.8)
    """
    expected_new = round(referrer_count * k_factor, 1)
    expected_revenue = round(expected_new * avg_order_yuan * 0.8, 2)
    return {
        "expected_new_customers": expected_new,
        "expected_revenue_yuan": expected_revenue,
        "avg_order_yuan": avg_order_yuan,
        "k_factor": k_factor,
    }


class ReferralEngineService:
    """裂变引擎 — CDP驱动的推荐追踪"""

    async def get_referral_metrics(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 30,
    ) -> dict:
        """
        裂变效果指标

        返回：大桌预订数 + 裂变场景分布 + 预估K值 + 新客占比
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        # 大桌预订（≥6人）
        large_reservations = await db.execute(
            select(
                Reservation.id,
                Reservation.party_size,
                Reservation.customer_name,
                Reservation.consumer_id,
            ).where(
                Reservation.store_id == store_id,
                Reservation.party_size >= 6,
                Reservation.created_at >= cutoff,
                Reservation.status != "cancelled",
            )
        )
        rows = large_reservations.all()

        scene_counts = {"banquet": 0, "birthday": 0, "business_dinner": 0, "fan_gathering": 0, "regular": 0}
        total_k = 0.0
        for row in rows:
            scene = classify_referral_scene(row[1], row[2] or "")
            scene_name = scene["scene"]
            scene_counts[scene_name] = scene_counts.get(scene_name, 0) + 1
            total_k += scene["k_estimate"]

        # 新客占比（本期新 consumer vs 总 consumer）
        new_consumers = (
            await db.scalar(
                select(func.count(ConsumerIdentity.id)).where(
                    ConsumerIdentity.created_at >= cutoff,
                    ConsumerIdentity.is_merged.is_(False),
                )
            )
            or 0
        )

        total_consumers = (
            await db.scalar(
                select(func.count(ConsumerIdentity.id)).where(
                    ConsumerIdentity.is_merged.is_(False),
                )
            )
            or 0
        )

        # 平均客单价
        avg_result = await db.execute(
            select(func.avg(Order.total_amount)).where(
                Order.store_id == store_id,
                Order.order_time >= cutoff,
                Order.status != "cancelled",
            )
        )
        avg_order = float(avg_result.scalar() or 0)

        avg_k = round(total_k / len(rows), 2) if rows else 0.0
        new_customer_rate = round(new_consumers / total_consumers, 4) if total_consumers > 0 else 0.0

        return {
            "period_days": days,
            "large_table_count": len(rows),
            "scene_distribution": scene_counts,
            "avg_k_factor": avg_k,
            "new_customers": new_consumers,
            "total_customers": total_consumers,
            "new_customer_rate": new_customer_rate,
            "avg_order_yuan": round(avg_order, 2),
            "estimated_value": estimate_referral_value(avg_order, avg_k, len(rows)),
        }

    async def get_top_referrers(
        self,
        db: AsyncSession,
        store_id: str,
        limit: int = 20,
    ) -> List[dict]:
        """
        高价值推荐人排名（大桌预订次数最多的消费者）

        基于 consumer_id 聚合大桌预订频次
        """
        stmt = (
            select(
                Reservation.consumer_id,
                func.count(Reservation.id).label("large_table_count"),
                func.sum(Reservation.party_size).label("total_guests"),
                func.max(Reservation.customer_name).label("name"),
            )
            .where(
                Reservation.store_id == store_id,
                Reservation.party_size >= 6,
                Reservation.consumer_id.isnot(None),
                Reservation.status != "cancelled",
            )
            .group_by(Reservation.consumer_id)
            .order_by(func.count(Reservation.id).desc())
            .limit(limit)
        )
        result = await db.execute(stmt)

        referrers = []
        for row in result.all():
            referrers.append(
                {
                    "consumer_id": str(row[0]) if row[0] else None,
                    "customer_name": row[3],
                    "large_table_count": row[1],
                    "total_guests_brought": row[2] or 0,
                    "avg_party_size": round((row[2] or 0) / row[1], 1) if row[1] > 0 else 0,
                }
            )
        return referrers


# 全局单例
referral_engine_service = ReferralEngineService()
