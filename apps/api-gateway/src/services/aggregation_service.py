"""
聚合服务：从事务表聚合运营快照到 operation_snapshots 表
支持日/周/月维度聚合，降级容错
"""

import calendar
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class AggregationService:
    """从 orders/inventory_transactions/waste_events/schedules/employees 聚合到 operation_snapshots"""

    # ── 方法1: 日聚合 ──────────────────────────────────────────

    async def aggregate_daily(
        self,
        session: AsyncSession,
        store_id: str,
        brand_id: str,
        target_date: date,
    ) -> Dict[str, Any]:
        """聚合单日运营数据并 UPSERT 到 operation_snapshots"""

        completeness_issues: List[str] = []
        metrics: Dict[str, Any] = {
            "revenue_fen": 0,
            "order_count": 0,
            "customer_count": 0,
            "avg_ticket_fen": 0,
            "dine_in_order_count": 0,
            "takeout_order_count": 0,
            "delivery_order_count": 0,
            "cost_material_fen": 0,
            "cost_labor_fen": 0,
            "employee_count": 0,
            "waste_value_fen": 0,
            "gross_profit_fen": 0,
            "net_profit_fen": 0,
            "waste_rate_pct": 0.0,
        }

        # ── 子查询1: 订单聚合 ──
        try:
            order_result = await session.execute(
                text("""
                    SELECT
                        COALESCE(SUM(final_amount_fen), 0) AS revenue_fen,
                        COUNT(*) AS order_count,
                        COUNT(DISTINCT table_number) AS customer_count,
                        CASE WHEN COUNT(*) > 0
                             THEN COALESCE(SUM(final_amount_fen), 0) / COUNT(*)
                             ELSE 0
                        END AS avg_ticket_fen,
                        COUNT(*) FILTER (WHERE order_type = 'dine_in') AS dine_in_order_count,
                        COUNT(*) FILTER (WHERE order_type = 'takeout') AS takeout_order_count,
                        COUNT(*) FILTER (WHERE order_type = 'delivery') AS delivery_order_count
                    FROM orders
                    WHERE store_id = :store_id
                      AND COALESCE(order_date, DATE(order_time)) = :target_date
                      AND status NOT IN ('cancelled', 'refunded')
                """),
                {"store_id": store_id, "target_date": target_date},
            )
            row = order_result.mappings().first()
            if row:
                metrics["revenue_fen"] = int(row["revenue_fen"])
                metrics["order_count"] = int(row["order_count"])
                metrics["customer_count"] = int(row["customer_count"])
                metrics["avg_ticket_fen"] = int(row["avg_ticket_fen"])
                metrics["dine_in_order_count"] = int(row["dine_in_order_count"])
                metrics["takeout_order_count"] = int(row["takeout_order_count"])
                metrics["delivery_order_count"] = int(row["delivery_order_count"])
        except Exception:
            logger.exception(
                "aggregate_daily.orders_failed",
                store_id=store_id,
                target_date=str(target_date),
            )
            completeness_issues.append("orders")

        # ── 子查询2: 物料成本 ──
        try:
            material_result = await session.execute(
                text("""
                    SELECT COALESCE(SUM(ABS(quantity * unit_price_fen)), 0) AS cost_material_fen
                    FROM inventory_transactions
                    WHERE store_id = :store_id
                      AND DATE(created_at) = :target_date
                      AND transaction_type IN ('consume', 'waste', 'transfer_out')
                """),
                {"store_id": store_id, "target_date": target_date},
            )
            row = material_result.mappings().first()
            if row:
                metrics["cost_material_fen"] = int(row["cost_material_fen"])
        except Exception:
            logger.exception(
                "aggregate_daily.inventory_failed",
                store_id=store_id,
                target_date=str(target_date),
            )
            completeness_issues.append("inventory_transactions")

        # ── 子查询3: 人力成本 ──
        try:
            labor_result = await session.execute(
                text("""
                    SELECT
                        COALESCE(SUM(s.hours * e.hourly_rate_fen), 0) AS cost_labor_fen,
                        COUNT(DISTINCT s.employee_id) AS employee_count
                    FROM schedules s
                    JOIN employees e ON e.id = s.employee_id
                    WHERE s.store_id = :store_id
                      AND s.shift_date = :target_date
                """),
                {"store_id": store_id, "target_date": target_date},
            )
            row = labor_result.mappings().first()
            if row:
                metrics["cost_labor_fen"] = int(row["cost_labor_fen"])
                metrics["employee_count"] = int(row["employee_count"])
        except Exception:
            logger.exception(
                "aggregate_daily.labor_failed",
                store_id=store_id,
                target_date=str(target_date),
            )
            completeness_issues.append("schedules_employees")

        # ── 子查询4: 损耗 ──
        try:
            waste_result = await session.execute(
                text("""
                    SELECT COALESCE(SUM(loss_value_fen), 0) AS waste_value_fen
                    FROM waste_events
                    WHERE store_id = :store_id
                      AND DATE(created_at) = :target_date
                """),
                {"store_id": store_id, "target_date": target_date},
            )
            row = waste_result.mappings().first()
            if row:
                metrics["waste_value_fen"] = int(row["waste_value_fen"])
        except Exception:
            logger.exception(
                "aggregate_daily.waste_failed",
                store_id=store_id,
                target_date=str(target_date),
            )
            completeness_issues.append("waste_events")

        # ── 派生字段 ──
        metrics["gross_profit_fen"] = metrics["revenue_fen"] - metrics["cost_material_fen"]
        metrics["net_profit_fen"] = (
            metrics["revenue_fen"] - metrics["cost_material_fen"] - metrics["cost_labor_fen"]
        )
        if metrics["revenue_fen"] > 0:
            metrics["waste_rate_pct"] = round(
                metrics["waste_value_fen"] / metrics["revenue_fen"] * 100, 2
            )

        # ── 数据完整度 ──
        completeness = round(
            (4 - len(completeness_issues)) / 4 * 100, 1
        )

        # ── UPSERT 到 operation_snapshots ──
        try:
            await session.execute(
                text("""
                    INSERT INTO operation_snapshots (
                        store_id, brand_id, snapshot_date, period_type,
                        revenue_fen, order_count, customer_count, avg_ticket_fen,
                        dine_in_order_count, takeout_order_count, delivery_order_count,
                        cost_material_fen, cost_labor_fen, employee_count,
                        waste_value_fen, gross_profit_fen, net_profit_fen,
                        waste_rate_pct, completeness_pct, completeness_issues
                    ) VALUES (
                        :store_id, :brand_id, :snapshot_date, 'daily',
                        :revenue_fen, :order_count, :customer_count, :avg_ticket_fen,
                        :dine_in_order_count, :takeout_order_count, :delivery_order_count,
                        :cost_material_fen, :cost_labor_fen, :employee_count,
                        :waste_value_fen, :gross_profit_fen, :net_profit_fen,
                        :waste_rate_pct, :completeness_pct, :completeness_issues
                    )
                    ON CONFLICT (brand_id, store_id, snapshot_date, period_type)
                    DO UPDATE SET
                        brand_id = EXCLUDED.brand_id,
                        revenue_fen = EXCLUDED.revenue_fen,
                        order_count = EXCLUDED.order_count,
                        customer_count = EXCLUDED.customer_count,
                        avg_ticket_fen = EXCLUDED.avg_ticket_fen,
                        dine_in_order_count = EXCLUDED.dine_in_order_count,
                        takeout_order_count = EXCLUDED.takeout_order_count,
                        delivery_order_count = EXCLUDED.delivery_order_count,
                        cost_material_fen = EXCLUDED.cost_material_fen,
                        cost_labor_fen = EXCLUDED.cost_labor_fen,
                        employee_count = EXCLUDED.employee_count,
                        waste_value_fen = EXCLUDED.waste_value_fen,
                        gross_profit_fen = EXCLUDED.gross_profit_fen,
                        net_profit_fen = EXCLUDED.net_profit_fen,
                        waste_rate_pct = EXCLUDED.waste_rate_pct,
                        completeness_pct = EXCLUDED.completeness_pct,
                        completeness_issues = EXCLUDED.completeness_issues,
                        updated_at = NOW()
                """),
                {
                    "store_id": store_id,
                    "brand_id": brand_id,
                    "snapshot_date": target_date,
                    "revenue_fen": metrics["revenue_fen"],
                    "order_count": metrics["order_count"],
                    "customer_count": metrics["customer_count"],
                    "avg_ticket_fen": metrics["avg_ticket_fen"],
                    "dine_in_order_count": metrics["dine_in_order_count"],
                    "takeout_order_count": metrics["takeout_order_count"],
                    "delivery_order_count": metrics["delivery_order_count"],
                    "cost_material_fen": metrics["cost_material_fen"],
                    "cost_labor_fen": metrics["cost_labor_fen"],
                    "employee_count": metrics["employee_count"],
                    "waste_value_fen": metrics["waste_value_fen"],
                    "gross_profit_fen": metrics["gross_profit_fen"],
                    "net_profit_fen": metrics["net_profit_fen"],
                    "waste_rate_pct": metrics["waste_rate_pct"],
                    "completeness_pct": completeness,
                    "completeness_issues": ",".join(completeness_issues) if completeness_issues else None,
                },
            )
            await session.flush()
        except Exception:
            logger.exception(
                "aggregate_daily.upsert_failed",
                store_id=store_id,
                target_date=str(target_date),
            )
            raise

        logger.info(
            "aggregate_daily.done",
            store_id=store_id,
            target_date=str(target_date),
            revenue_yuan=round(metrics["revenue_fen"] / 100, 2),
            order_count=metrics["order_count"],
            gross_profit_yuan=round(metrics["gross_profit_fen"] / 100, 2),
            waste_rate_pct=metrics["waste_rate_pct"],
            completeness_pct=completeness,
        )

        return {
            "store_id": store_id,
            "target_date": str(target_date),
            "period_type": "daily",
            "metrics": metrics,
            "completeness_pct": completeness,
            "completeness_issues": completeness_issues,
        }

    # ── 方法2: 周聚合 ──────────────────────────────────────────

    async def aggregate_weekly(
        self,
        session: AsyncSession,
        store_id: str,
        brand_id: str,
        week_end_date: date,
    ) -> Dict[str, Any]:
        """从 daily snapshots 聚合7天数据，UPSERT 到 operation_snapshots(period_type='weekly')"""

        week_start_date = week_end_date - timedelta(days=6)

        result = await session.execute(
            text("""
                SELECT
                    COALESCE(SUM(revenue_fen), 0) AS revenue_fen,
                    COALESCE(SUM(order_count), 0) AS order_count,
                    COALESCE(SUM(customer_count), 0) AS customer_count,
                    CASE WHEN SUM(order_count) > 0
                         THEN COALESCE(SUM(revenue_fen), 0) / SUM(order_count)
                         ELSE 0
                    END AS avg_ticket_fen,
                    COALESCE(SUM(dine_in_order_count), 0) AS dine_in_order_count,
                    COALESCE(SUM(takeout_order_count), 0) AS takeout_order_count,
                    COALESCE(SUM(delivery_order_count), 0) AS delivery_order_count,
                    COALESCE(SUM(cost_material_fen), 0) AS cost_material_fen,
                    COALESCE(SUM(cost_labor_fen), 0) AS cost_labor_fen,
                    COALESCE(SUM(employee_count), 0) AS employee_count,
                    COALESCE(SUM(waste_value_fen), 0) AS waste_value_fen,
                    COALESCE(SUM(gross_profit_fen), 0) AS gross_profit_fen,
                    COALESCE(SUM(net_profit_fen), 0) AS net_profit_fen,
                    COALESCE(AVG(waste_rate_pct), 0) AS waste_rate_pct,
                    COALESCE(AVG(completeness_pct), 0) AS completeness_pct,
                    COUNT(*) AS day_count
                FROM operation_snapshots
                WHERE store_id = :store_id
                  AND period_type = 'daily'
                  AND snapshot_date BETWEEN :week_start AND :week_end
            """),
            {
                "store_id": store_id,
                "week_start": week_start_date,
                "week_end": week_end_date,
            },
        )
        row = result.mappings().first()

        metrics: Dict[str, Any] = {
            "revenue_fen": int(row["revenue_fen"]),
            "order_count": int(row["order_count"]),
            "customer_count": int(row["customer_count"]),
            "avg_ticket_fen": int(row["avg_ticket_fen"]),
            "dine_in_order_count": int(row["dine_in_order_count"]),
            "takeout_order_count": int(row["takeout_order_count"]),
            "delivery_order_count": int(row["delivery_order_count"]),
            "cost_material_fen": int(row["cost_material_fen"]),
            "cost_labor_fen": int(row["cost_labor_fen"]),
            "employee_count": int(row["employee_count"]),
            "waste_value_fen": int(row["waste_value_fen"]),
            "gross_profit_fen": int(row["gross_profit_fen"]),
            "net_profit_fen": int(row["net_profit_fen"]),
            "waste_rate_pct": round(float(row["waste_rate_pct"]), 2),
        }
        completeness = round(float(row["completeness_pct"]), 1)
        day_count = int(row["day_count"])

        await session.execute(
            text("""
                INSERT INTO operation_snapshots (
                    store_id, brand_id, snapshot_date, period_type,
                    revenue_fen, order_count, customer_count, avg_ticket_fen,
                    dine_in_order_count, takeout_order_count, delivery_order_count,
                    cost_material_fen, cost_labor_fen, employee_count,
                    waste_value_fen, gross_profit_fen, net_profit_fen,
                    waste_rate_pct, completeness_pct
                ) VALUES (
                    :store_id, :brand_id, :snapshot_date, 'weekly',
                    :revenue_fen, :order_count, :customer_count, :avg_ticket_fen,
                    :dine_in_order_count, :takeout_order_count, :delivery_order_count,
                    :cost_material_fen, :cost_labor_fen, :employee_count,
                    :waste_value_fen, :gross_profit_fen, :net_profit_fen,
                    :waste_rate_pct, :completeness_pct
                )
                ON CONFLICT (brand_id, store_id, snapshot_date, period_type)
                DO UPDATE SET
                    brand_id = EXCLUDED.brand_id,
                    revenue_fen = EXCLUDED.revenue_fen,
                    order_count = EXCLUDED.order_count,
                    customer_count = EXCLUDED.customer_count,
                    avg_ticket_fen = EXCLUDED.avg_ticket_fen,
                    dine_in_order_count = EXCLUDED.dine_in_order_count,
                    takeout_order_count = EXCLUDED.takeout_order_count,
                    delivery_order_count = EXCLUDED.delivery_order_count,
                    cost_material_fen = EXCLUDED.cost_material_fen,
                    cost_labor_fen = EXCLUDED.cost_labor_fen,
                    employee_count = EXCLUDED.employee_count,
                    waste_value_fen = EXCLUDED.waste_value_fen,
                    gross_profit_fen = EXCLUDED.gross_profit_fen,
                    net_profit_fen = EXCLUDED.net_profit_fen,
                    waste_rate_pct = EXCLUDED.waste_rate_pct,
                    completeness_pct = EXCLUDED.completeness_pct,
                    updated_at = NOW()
            """),
            {
                "store_id": store_id,
                "brand_id": brand_id,
                "snapshot_date": week_end_date,
                "revenue_fen": metrics["revenue_fen"],
                "order_count": metrics["order_count"],
                "customer_count": metrics["customer_count"],
                "avg_ticket_fen": metrics["avg_ticket_fen"],
                "dine_in_order_count": metrics["dine_in_order_count"],
                "takeout_order_count": metrics["takeout_order_count"],
                "delivery_order_count": metrics["delivery_order_count"],
                "cost_material_fen": metrics["cost_material_fen"],
                "cost_labor_fen": metrics["cost_labor_fen"],
                "employee_count": metrics["employee_count"],
                "waste_value_fen": metrics["waste_value_fen"],
                "gross_profit_fen": metrics["gross_profit_fen"],
                "net_profit_fen": metrics["net_profit_fen"],
                "waste_rate_pct": metrics["waste_rate_pct"],
                "completeness_pct": completeness,
            },
        )
        await session.flush()

        logger.info(
            "aggregate_weekly.done",
            store_id=store_id,
            week_end=str(week_end_date),
            revenue_yuan=round(metrics["revenue_fen"] / 100, 2),
            day_count=day_count,
            completeness_pct=completeness,
        )

        return {
            "store_id": store_id,
            "week_end_date": str(week_end_date),
            "period_type": "weekly",
            "metrics": metrics,
            "day_count": day_count,
            "completeness_pct": completeness,
        }

    # ── 方法3: 月聚合 ──────────────────────────────────────────

    async def aggregate_monthly(
        self,
        session: AsyncSession,
        store_id: str,
        brand_id: str,
        month_date: date,
    ) -> Dict[str, Any]:
        """从 daily snapshots 聚合当月数据，UPSERT 到 operation_snapshots(period_type='monthly')"""

        month_start = month_date.replace(day=1)
        last_day = calendar.monthrange(month_date.year, month_date.month)[1]
        month_end = month_date.replace(day=last_day)

        result = await session.execute(
            text("""
                SELECT
                    COALESCE(SUM(revenue_fen), 0) AS revenue_fen,
                    COALESCE(SUM(order_count), 0) AS order_count,
                    COALESCE(SUM(customer_count), 0) AS customer_count,
                    CASE WHEN SUM(order_count) > 0
                         THEN COALESCE(SUM(revenue_fen), 0) / SUM(order_count)
                         ELSE 0
                    END AS avg_ticket_fen,
                    COALESCE(SUM(dine_in_order_count), 0) AS dine_in_order_count,
                    COALESCE(SUM(takeout_order_count), 0) AS takeout_order_count,
                    COALESCE(SUM(delivery_order_count), 0) AS delivery_order_count,
                    COALESCE(SUM(cost_material_fen), 0) AS cost_material_fen,
                    COALESCE(SUM(cost_labor_fen), 0) AS cost_labor_fen,
                    COALESCE(SUM(employee_count), 0) AS employee_count,
                    COALESCE(SUM(waste_value_fen), 0) AS waste_value_fen,
                    COALESCE(SUM(gross_profit_fen), 0) AS gross_profit_fen,
                    COALESCE(SUM(net_profit_fen), 0) AS net_profit_fen,
                    COALESCE(AVG(waste_rate_pct), 0) AS waste_rate_pct,
                    COALESCE(AVG(completeness_pct), 0) AS completeness_pct,
                    COUNT(*) AS day_count
                FROM operation_snapshots
                WHERE store_id = :store_id
                  AND period_type = 'daily'
                  AND snapshot_date BETWEEN :month_start AND :month_end
            """),
            {
                "store_id": store_id,
                "month_start": month_start,
                "month_end": month_end,
            },
        )
        row = result.mappings().first()

        metrics: Dict[str, Any] = {
            "revenue_fen": int(row["revenue_fen"]),
            "order_count": int(row["order_count"]),
            "customer_count": int(row["customer_count"]),
            "avg_ticket_fen": int(row["avg_ticket_fen"]),
            "dine_in_order_count": int(row["dine_in_order_count"]),
            "takeout_order_count": int(row["takeout_order_count"]),
            "delivery_order_count": int(row["delivery_order_count"]),
            "cost_material_fen": int(row["cost_material_fen"]),
            "cost_labor_fen": int(row["cost_labor_fen"]),
            "employee_count": int(row["employee_count"]),
            "waste_value_fen": int(row["waste_value_fen"]),
            "gross_profit_fen": int(row["gross_profit_fen"]),
            "net_profit_fen": int(row["net_profit_fen"]),
            "waste_rate_pct": round(float(row["waste_rate_pct"]), 2),
        }
        completeness = round(float(row["completeness_pct"]), 1)
        day_count = int(row["day_count"])

        await session.execute(
            text("""
                INSERT INTO operation_snapshots (
                    store_id, brand_id, snapshot_date, period_type,
                    revenue_fen, order_count, customer_count, avg_ticket_fen,
                    dine_in_order_count, takeout_order_count, delivery_order_count,
                    cost_material_fen, cost_labor_fen, employee_count,
                    waste_value_fen, gross_profit_fen, net_profit_fen,
                    waste_rate_pct, completeness_pct
                ) VALUES (
                    :store_id, :brand_id, :snapshot_date, 'monthly',
                    :revenue_fen, :order_count, :customer_count, :avg_ticket_fen,
                    :dine_in_order_count, :takeout_order_count, :delivery_order_count,
                    :cost_material_fen, :cost_labor_fen, :employee_count,
                    :waste_value_fen, :gross_profit_fen, :net_profit_fen,
                    :waste_rate_pct, :completeness_pct
                )
                ON CONFLICT (brand_id, store_id, snapshot_date, period_type)
                DO UPDATE SET
                    brand_id = EXCLUDED.brand_id,
                    revenue_fen = EXCLUDED.revenue_fen,
                    order_count = EXCLUDED.order_count,
                    customer_count = EXCLUDED.customer_count,
                    avg_ticket_fen = EXCLUDED.avg_ticket_fen,
                    dine_in_order_count = EXCLUDED.dine_in_order_count,
                    takeout_order_count = EXCLUDED.takeout_order_count,
                    delivery_order_count = EXCLUDED.delivery_order_count,
                    cost_material_fen = EXCLUDED.cost_material_fen,
                    cost_labor_fen = EXCLUDED.cost_labor_fen,
                    employee_count = EXCLUDED.employee_count,
                    waste_value_fen = EXCLUDED.waste_value_fen,
                    gross_profit_fen = EXCLUDED.gross_profit_fen,
                    net_profit_fen = EXCLUDED.net_profit_fen,
                    waste_rate_pct = EXCLUDED.waste_rate_pct,
                    completeness_pct = EXCLUDED.completeness_pct,
                    updated_at = NOW()
            """),
            {
                "store_id": store_id,
                "brand_id": brand_id,
                "snapshot_date": month_start,
                "revenue_fen": metrics["revenue_fen"],
                "order_count": metrics["order_count"],
                "customer_count": metrics["customer_count"],
                "avg_ticket_fen": metrics["avg_ticket_fen"],
                "dine_in_order_count": metrics["dine_in_order_count"],
                "takeout_order_count": metrics["takeout_order_count"],
                "delivery_order_count": metrics["delivery_order_count"],
                "cost_material_fen": metrics["cost_material_fen"],
                "cost_labor_fen": metrics["cost_labor_fen"],
                "employee_count": metrics["employee_count"],
                "waste_value_fen": metrics["waste_value_fen"],
                "gross_profit_fen": metrics["gross_profit_fen"],
                "net_profit_fen": metrics["net_profit_fen"],
                "waste_rate_pct": metrics["waste_rate_pct"],
                "completeness_pct": completeness,
            },
        )
        await session.flush()

        logger.info(
            "aggregate_monthly.done",
            store_id=store_id,
            month=str(month_start),
            revenue_yuan=round(metrics["revenue_fen"] / 100, 2),
            day_count=day_count,
            completeness_pct=completeness,
        )

        return {
            "store_id": store_id,
            "month_date": str(month_start),
            "period_type": "monthly",
            "metrics": metrics,
            "day_count": day_count,
            "completeness_pct": completeness,
        }

    # ── 方法4: 全门店批量聚合 ──────────────────────────────────

    async def aggregate_all_stores(
        self,
        session: AsyncSession,
        period_type: str,
        target_date: date,
    ) -> Dict[str, Any]:
        """查询所有 active 门店，逐个调用对应聚合方法"""

        # 获取活跃门店列表
        store_result = await session.execute(
            text("""
                SELECT id AS store_id, brand_id
                FROM stores
                WHERE status = 'active'
                ORDER BY id
            """)
        )
        stores = store_result.mappings().all()

        aggregated = 0
        errors: List[Dict[str, str]] = []

        for store in stores:
            store_id = str(store["store_id"])
            brand_id = str(store["brand_id"])
            try:
                if period_type == "daily":
                    await self.aggregate_daily(session, store_id, brand_id, target_date)
                elif period_type == "weekly":
                    await self.aggregate_weekly(session, store_id, brand_id, target_date)
                elif period_type == "monthly":
                    await self.aggregate_monthly(session, store_id, brand_id, target_date)
                else:
                    errors.append({
                        "store_id": store_id,
                        "error": f"unknown period_type: {period_type}",
                    })
                    continue
                aggregated += 1
            except Exception as exc:
                logger.exception(
                    "aggregate_all_stores.store_failed",
                    store_id=store_id,
                    period_type=period_type,
                    target_date=str(target_date),
                )
                errors.append({"store_id": store_id, "error": str(exc)})

        logger.info(
            "aggregate_all_stores.done",
            period_type=period_type,
            target_date=str(target_date),
            total_stores=len(stores),
            aggregated=aggregated,
            error_count=len(errors),
        )

        return {
            "period_type": period_type,
            "target_date": str(target_date),
            "total_stores": len(stores),
            "aggregated": aggregated,
            "errors": errors,
        }
