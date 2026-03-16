"""
CDP Monitor Service — 消费者数据平台监控仪表盘

核心能力：
1. 综合仪表盘（填充率 + 消费者统计 + RFM分布 + 偏差率）
2. 全量回填编排（orders → members → RFM重算 → 偏差校验）
3. RFM等级分布统计
4. KPI达标检查（填充率≥80% + 偏差<5%）

定位：CDP数据治理的运营监控台
"""

import logging
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.consumer_identity import ConsumerIdentity
from src.models.order import Order
from src.models.private_domain import PrivateDomainMember

logger = logging.getLogger(__name__)


# ── 纯函数 ──────────────────────────────────────────────────────


def classify_fill_rate_health(rate: float) -> str:
    """
    填充率健康度

    excellent: ≥ 90%
    good: ≥ 80%（KPI达标线）
    warning: ≥ 60%
    critical: < 60%
    """
    if rate >= 0.90:
        return "excellent"
    if rate >= 0.80:
        return "good"
    if rate >= 0.60:
        return "warning"
    return "critical"


def compute_kpi_summary(
    order_fill_rate: float,
    deviation_rate: float,
) -> dict:
    """
    KPI达标汇总

    两个硬指标：
    1. consumer_id 填充率 ≥ 80%
    2. RFM 偏差率 < 5%
    """
    fill_met = order_fill_rate >= 0.80
    dev_met = deviation_rate < 0.05
    return {
        "fill_rate_kpi": {
            "target": ">=80%",
            "actual": round(order_fill_rate * 100, 2),
            "met": fill_met,
        },
        "deviation_kpi": {
            "target": "<5%",
            "actual": round(deviation_rate * 100, 2),
            "met": dev_met,
        },
        "all_met": fill_met and dev_met,
    }


class CDPMonitorService:
    """CDP 监控仪表盘服务"""

    async def get_dashboard(
        self,
        db: AsyncSession,
        store_id: Optional[str] = None,
    ) -> dict:
        """
        CDP 综合仪表盘

        聚合：消费者统计 + 填充率 + RFM分布 + 偏差率 + KPI达标
        """
        from src.services.cdp_rfm_service import cdp_rfm_service
        from src.services.cdp_sync_service import cdp_sync_service
        from src.services.identity_resolution_service import identity_resolution_service

        # 1. 消费者基础统计
        stats = await identity_resolution_service.get_stats(db)

        # 2. 填充率
        fill_rate = await cdp_sync_service.get_fill_rate(db, store_id=store_id)

        # 3. RFM 分布
        rfm_dist = await self.get_rfm_distribution(db, store_id=store_id)

        # 4. RFM 偏差
        deviation = await cdp_rfm_service.compute_deviation(db, store_id=store_id)

        # 5. KPI 汇总
        order_rate = fill_rate.get("orders", {}).get("rate", 0.0)
        dev_rate = deviation.get("deviation_rate", 0.0)
        kpi = compute_kpi_summary(order_rate, dev_rate)

        # 6. 待回填统计
        pending = await self._get_pending_counts(db, store_id=store_id)

        return {
            "consumer_stats": stats,
            "fill_rate": fill_rate,
            "fill_rate_health": classify_fill_rate_health(order_rate),
            "rfm_distribution": rfm_dist,
            "deviation": deviation,
            "kpi_summary": kpi,
            "pending_backfill": pending,
        }

    async def get_rfm_distribution(
        self,
        db: AsyncSession,
        store_id: Optional[str] = None,
    ) -> dict:
        """
        RFM 等级分布

        返回：S1-S5 各等级人数 + 占比
        """
        where = [
            PrivateDomainMember.is_active.is_(True),
            PrivateDomainMember.rfm_level.isnot(None),
        ]
        if store_id:
            where.append(PrivateDomainMember.store_id == store_id)

        stmt = (
            select(
                PrivateDomainMember.rfm_level,
                func.count(PrivateDomainMember.id),
            )
            .where(*where)
            .group_by(PrivateDomainMember.rfm_level)
        )
        result = await db.execute(stmt)
        rows = result.all()

        dist = {f"S{i}": 0 for i in range(1, 6)}
        total = 0
        for level, count in rows:
            if level in dist:
                dist[level] = count
                total += count

        # 添加占比
        distribution = {}
        for level, count in dist.items():
            distribution[level] = {
                "count": count,
                "rate": round(count / total, 4) if total > 0 else 0.0,
            }
        distribution["total"] = total

        return distribution

    async def _get_pending_counts(
        self,
        db: AsyncSession,
        store_id: Optional[str] = None,
    ) -> dict:
        """待回填记录数"""
        # 订单：有手机号但没consumer_id
        order_where = [
            Order.consumer_id.is_(None),
            Order.customer_phone.isnot(None),
            Order.customer_phone != "",
        ]
        if store_id:
            order_where.append(Order.store_id == store_id)
        pending_orders = await db.scalar(select(func.count(Order.id)).where(*order_where)) or 0

        # 会员：没有consumer_id
        member_where = [
            PrivateDomainMember.consumer_id.is_(None),
            PrivateDomainMember.is_active.is_(True),
        ]
        if store_id:
            member_where.append(PrivateDomainMember.store_id == store_id)
        pending_members = await db.scalar(select(func.count(PrivateDomainMember.id)).where(*member_where)) or 0

        return {
            "orders": pending_orders,
            "members": pending_members,
            "total": pending_orders + pending_members,
        }

    async def run_full_backfill(
        self,
        db: AsyncSession,
        store_id: Optional[str] = None,
        batch_size: int = 500,
    ) -> dict:
        """
        全量回填管道（同步执行）

        步骤：
        1. 回填订单 consumer_id
        2. 回填会员 consumer_id
        3. 重算 RFM
        4. 校验偏差

        返回：各步骤结果 + 最终KPI
        """
        from src.services.cdp_rfm_service import cdp_rfm_service
        from src.services.cdp_sync_service import cdp_sync_service

        results = {"steps": {}}

        # Step 1: 回填订单
        if store_id:
            order_result = await cdp_sync_service.sync_store_orders(
                db,
                store_id,
                batch_size=batch_size,
            )
        else:
            order_result = await cdp_sync_service.sync_all_stores(
                db,
                batch_size=batch_size,
            )
        await db.commit()
        results["steps"]["backfill_orders"] = order_result

        # Step 2: 回填会员
        member_result = await cdp_rfm_service.backfill_members(
            db,
            store_id=store_id,
            batch_size=batch_size,
        )
        await db.commit()
        results["steps"]["backfill_members"] = member_result

        # Step 3: 重算 RFM
        rfm_result = await cdp_rfm_service.recalculate_all(
            db,
            store_id=store_id,
        )
        await db.commit()
        results["steps"]["rfm_recalculate"] = rfm_result

        # Step 4: 偏差校验
        deviation = await cdp_rfm_service.compute_deviation(
            db,
            store_id=store_id,
        )
        results["steps"]["deviation_check"] = deviation

        # 最终填充率
        fill_rate = await cdp_sync_service.get_fill_rate(db, store_id=store_id)
        order_rate = fill_rate.get("orders", {}).get("rate", 0.0)
        dev_rate = deviation.get("deviation_rate", 0.0)

        results["final_fill_rate"] = fill_rate
        results["kpi_summary"] = compute_kpi_summary(order_rate, dev_rate)

        return results


# 全局单例
cdp_monitor_service = CDPMonitorService()
