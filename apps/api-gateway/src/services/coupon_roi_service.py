"""发券 ROI 服务 — P2 核心：日汇总 + 查询"""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.coupon_distribution import (
    CouponDistribution,
    CouponRedemption,
    CouponRoiDaily,
)

logger = structlog.get_logger(__name__)


class CouponRoiService:
    """发券 ROI 汇总与查询"""

    async def aggregate_daily(
        self, db: AsyncSession, target_date: date, store_id: str, brand_id: str
    ) -> Dict[str, Any]:
        """汇总指定日期的发券 ROI 数据，写入 coupon_roi_daily"""
        start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end = start + timedelta(days=1)

        # 按 staff 聚合发券
        dist_stmt = (
            select(
                CouponDistribution.distributed_by,
                func.count().label("cnt"),
                func.coalesce(func.sum(CouponDistribution.coupon_value_fen), 0).label("val"),
            )
            .where(
                CouponDistribution.store_id == store_id,
                CouponDistribution.brand_id == brand_id,
                CouponDistribution.distributed_at >= start,
                CouponDistribution.distributed_at < end,
            )
            .group_by(CouponDistribution.distributed_by)
        )
        dist_rows = (await db.execute(dist_stmt)).all()

        # 按 distribution → staff 聚合核销
        redemption_stmt = (
            select(
                CouponDistribution.distributed_by,
                func.count().label("cnt"),
                func.coalesce(func.sum(CouponRedemption.order_amount_fen), 0).label("gmv"),
            )
            .select_from(CouponRedemption)
            .join(CouponDistribution, CouponRedemption.distribution_id == CouponDistribution.id)
            .where(
                CouponDistribution.store_id == store_id,
                CouponDistribution.brand_id == brand_id,
                CouponRedemption.redeemed_at >= start,
                CouponRedemption.redeemed_at < end,
            )
            .group_by(CouponDistribution.distributed_by)
        )
        redemption_rows = (await db.execute(redemption_stmt)).all()
        redemption_map = {r[0]: (r[1], r[2]) for r in redemption_rows}

        upserted = 0
        for row in dist_rows:
            staff_id = row[0]
            redeemed = redemption_map.get(staff_id, (0, 0))

            # upsert
            existing = (
                await db.execute(
                    select(CouponRoiDaily).where(
                        CouponRoiDaily.date == target_date,
                        CouponRoiDaily.store_id == store_id,
                        CouponRoiDaily.staff_id == staff_id,
                    )
                )
            ).scalar_one_or_none()

            if existing:
                existing.distributed_count = row[1]
                existing.distributed_value_fen = row[2]
                existing.redeemed_count = redeemed[0]
                existing.driven_gmv_fen = redeemed[1]
            else:
                db.add(
                    CouponRoiDaily(
                        date=target_date,
                        store_id=store_id,
                        brand_id=brand_id,
                        staff_id=staff_id,
                        distributed_count=row[1],
                        distributed_value_fen=row[2],
                        redeemed_count=redeemed[0],
                        driven_gmv_fen=redeemed[1],
                    )
                )
            upserted += 1

        await db.flush()
        logger.info(
            "ROI 日汇总完成",
            date=str(target_date),
            store_id=store_id,
            staff_count=upserted,
        )
        return {"date": str(target_date), "store_id": store_id, "upserted": upserted}

    async def query_roi(
        self,
        db: AsyncSession,
        store_id: str,
        brand_id: str,
        start_date: date,
        end_date: date,
        staff_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """查询 ROI 汇总数据"""
        conditions = [
            CouponRoiDaily.store_id == store_id,
            CouponRoiDaily.brand_id == brand_id,
            CouponRoiDaily.date >= start_date,
            CouponRoiDaily.date <= end_date,
        ]
        if staff_id:
            conditions.append(CouponRoiDaily.staff_id == staff_id)

        stmt = select(
            func.sum(CouponRoiDaily.distributed_count).label("total_distributed"),
            func.sum(CouponRoiDaily.distributed_value_fen).label("total_value_fen"),
            func.sum(CouponRoiDaily.redeemed_count).label("total_redeemed"),
            func.sum(CouponRoiDaily.driven_gmv_fen).label("total_gmv_fen"),
        ).where(and_(*conditions))

        row = (await db.execute(stmt)).one()
        total_dist = row[0] or 0
        total_val = row[1] or 0
        total_redeemed = row[2] or 0
        total_gmv = row[3] or 0

        redemption_rate = (total_redeemed / total_dist * 100) if total_dist > 0 else 0
        roi = (total_gmv / total_val) if total_val > 0 else 0

        # 按日明细
        daily_stmt = (
            select(
                CouponRoiDaily.date,
                func.sum(CouponRoiDaily.distributed_count).label("distributed"),
                func.sum(CouponRoiDaily.redeemed_count).label("redeemed"),
                func.sum(CouponRoiDaily.driven_gmv_fen).label("gmv_fen"),
            )
            .where(and_(*conditions))
            .group_by(CouponRoiDaily.date)
            .order_by(CouponRoiDaily.date)
        )
        daily_rows = (await db.execute(daily_stmt)).all()

        return {
            "summary": {
                "total_distributed": total_dist,
                "total_value_yuan": round(total_val / 100, 2),
                "total_redeemed": total_redeemed,
                "redemption_rate": round(redemption_rate, 1),
                "driven_gmv_yuan": round(total_gmv / 100, 2),
                "roi": round(roi, 2),
            },
            "daily": [
                {
                    "date": str(r[0]),
                    "distributed": r[1] or 0,
                    "redeemed": r[2] or 0,
                    "gmv_yuan": round((r[3] or 0) / 100, 2),
                }
                for r in daily_rows
            ],
        }

    async def staff_leaderboard(
        self,
        db: AsyncSession,
        store_id: str,
        brand_id: str,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        """员工发券排行榜"""
        stmt = (
            select(
                CouponRoiDaily.staff_id,
                func.sum(CouponRoiDaily.distributed_count).label("distributed"),
                func.sum(CouponRoiDaily.redeemed_count).label("redeemed"),
                func.sum(CouponRoiDaily.driven_gmv_fen).label("gmv_fen"),
            )
            .where(
                CouponRoiDaily.store_id == store_id,
                CouponRoiDaily.brand_id == brand_id,
                CouponRoiDaily.date >= start_date,
                CouponRoiDaily.date <= end_date,
                CouponRoiDaily.staff_id.isnot(None),
            )
            .group_by(CouponRoiDaily.staff_id)
            .order_by(func.sum(CouponRoiDaily.driven_gmv_fen).desc())
            .limit(20)
        )
        rows = (await db.execute(stmt)).all()
        return [
            {
                "staff_id": str(r[0]),
                "distributed": r[1] or 0,
                "redeemed": r[2] or 0,
                "gmv_yuan": round((r[3] or 0) / 100, 2),
                "redemption_rate": round(
                    ((r[2] or 0) / r[1] * 100) if r[1] else 0, 1
                ),
            }
            for r in rows
        ]


coupon_roi_service = CouponRoiService()
