"""
财务数据真实聚合引擎
从 orders / inventory_transactions / waste_events 等真实数据表计算 P&L
解决 finance 路由返回假数据 (0) 的问题

金额约定：
  - 内部计算全程使用分（int，fen）
  - 返回给 API 调用方的 *_yuan 字段为 float（分 / 100）
"""

from __future__ import annotations

import os
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# 食材成本率默认兜底（无库存出库数据时使用，可由环境变量覆盖）
DEFAULT_FOOD_COST_RATIO = float(os.getenv("DEFAULT_FOOD_COST_RATIO", "0.35"))
# 人工成本率默认兜底
DEFAULT_LABOR_COST_RATIO = float(os.getenv("DEFAULT_LABOR_COST_RATIO", "0.25"))


class FinanceAnalyticsService:
    """财务数据真实聚合引擎"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─────────────────────────────────────────────
    # 内部辅助：安全除法，防止零除
    # ─────────────────────────────────────────────

    @staticmethod
    def _safe_pct(numerator: int, denominator: int) -> float:
        """计算百分比，分母为 0 时返回 0.0"""
        if not denominator:
            return 0.0
        return round(numerator / denominator * 100, 2)

    @staticmethod
    def _fen_to_yuan(fen: int) -> float:
        """分转元，保留 2 位小数"""
        return round(fen / 100, 2)

    # ─────────────────────────────────────────────
    # 日营收汇总（真实数据）
    # ─────────────────────────────────────────────

    async def get_daily_revenue_summary(
        self, store_id: str, date_: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        日营收汇总（真实数据）
        从 orders 表聚合：
          gross_revenue_fen  = SUM(final_amount)  WHERE status='completed' AND DATE(order_time)=date_
          discount_amount_fen= SUM(discount_amount)
          net_revenue_fen    = gross - discount
          order_count        = COUNT(*)
          avg_order_fen      = net / count
          by_payment_method  = GROUP BY payment_method
        """
        if date_ is None:
            date_ = datetime.utcnow().date()

        # 主营收聚合：参数化查询，避免 SQL 注入
        revenue_sql = text(
            """
            SELECT
                COALESCE(SUM(final_amount), 0)    AS gross_revenue_fen,
                COALESCE(SUM(discount_amount), 0) AS discount_amount_fen,
                COUNT(*)                          AS order_count
            FROM orders
            WHERE store_id      = :store_id
              AND status        = 'completed'
              AND DATE(order_time) = :target_date
            """
        )
        row = (
            await self.db.execute(
                revenue_sql, {"store_id": store_id, "target_date": date_}
            )
        ).fetchone()

        gross_revenue_fen = int(row.gross_revenue_fen) if row else 0
        discount_amount_fen = int(row.discount_amount_fen) if row else 0
        order_count = int(row.order_count) if row else 0
        net_revenue_fen = gross_revenue_fen - discount_amount_fen
        avg_order_fen = net_revenue_fen // order_count if order_count else 0

        # 按支付方式分组（用于渠道分析）
        channel_sql = text(
            """
            SELECT
                COALESCE(payment_method, 'unknown') AS payment_method,
                COALESCE(SUM(final_amount), 0)      AS amount_fen,
                COUNT(*)                            AS cnt
            FROM orders
            WHERE store_id      = :store_id
              AND status        = 'completed'
              AND DATE(order_time) = :target_date
            GROUP BY payment_method
            """
        )
        channel_rows = (
            await self.db.execute(
                channel_sql, {"store_id": store_id, "target_date": date_}
            )
        ).fetchall()

        by_payment_method = {
            r.payment_method: {
                "amount_fen": int(r.amount_fen),
                "amount_yuan": self._fen_to_yuan(int(r.amount_fen)),
                "order_count": int(r.cnt),
            }
            for r in channel_rows
        }

        return {
            "store_id": store_id,
            "date": date_.isoformat(),
            "gross_revenue_fen": gross_revenue_fen,
            "gross_revenue_yuan": self._fen_to_yuan(gross_revenue_fen),
            "discount_amount_fen": discount_amount_fen,
            "discount_amount_yuan": self._fen_to_yuan(discount_amount_fen),
            "net_revenue_fen": net_revenue_fen,
            "net_revenue_yuan": self._fen_to_yuan(net_revenue_fen),
            "order_count": order_count,
            "avg_order_fen": avg_order_fen,
            "avg_order_yuan": self._fen_to_yuan(avg_order_fen),
            "by_payment_method": by_payment_method,
        }

    # ─────────────────────────────────────────────
    # 日成本汇总（从库存扣减推算）
    # ─────────────────────────────────────────────

    async def get_daily_cost_summary(
        self, store_id: str, date_: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        日成本汇总（从库存扣减推算）
          ingredient_cost_fen : 当日库存出库金额（从 inventory_transactions）
          waste_cost_fen      : 当日损耗金额（quantity × unit_cost，从 waste_events JOIN inventory_items）
        """
        if date_ is None:
            date_ = datetime.utcnow().date()

        # 食材成本：当日库存出库（transaction_type='usage'/'out'）金额加总
        ingredient_sql = text(
            """
            SELECT COALESCE(SUM(ABS(total_cost)), 0) AS ingredient_cost_fen
            FROM inventory_transactions
            WHERE store_id           = :store_id
              AND transaction_type  IN ('usage', 'out', 'adjustment')
              AND total_cost        < 0       -- 出库为负数
              AND DATE(created_at)  = :target_date
            """
        )
        ing_row = (
            await self.db.execute(
                ingredient_sql, {"store_id": store_id, "target_date": date_}
            )
        ).fetchone()
        ingredient_cost_fen = int(ing_row.ingredient_cost_fen) if ing_row else 0

        # 损耗成本：quantity × unit_cost 关联计算
        waste_sql = text(
            """
            SELECT COALESCE(SUM(
                CAST(we.quantity AS NUMERIC) * COALESCE(ii.unit_cost, 0)
            ), 0) AS waste_cost_fen
            FROM waste_events we
            JOIN inventory_items ii ON ii.id = we.ingredient_id
            WHERE we.store_id        = :store_id
              AND DATE(we.occurred_at) = :target_date
            """
        )
        waste_row = (
            await self.db.execute(
                waste_sql, {"store_id": store_id, "target_date": date_}
            )
        ).fetchone()
        waste_cost_fen = int(waste_row.waste_cost_fen) if waste_row else 0

        return {
            "store_id": store_id,
            "date": date_.isoformat(),
            "ingredient_cost_fen": ingredient_cost_fen,
            "ingredient_cost_yuan": self._fen_to_yuan(ingredient_cost_fen),
            "waste_cost_fen": waste_cost_fen,
            "waste_cost_yuan": self._fen_to_yuan(waste_cost_fen),
        }

    # ─────────────────────────────────────────────
    # 日利润（替换硬编码 0 的端点）
    # ─────────────────────────────────────────────

    async def get_real_daily_profit(
        self, store_id: str, date_: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        替换原 finance 路由中硬编码返回 0 的日利润接口。
        返回所有 *_yuan 字段（float），内部计算用分（int）。
        包含环比昨日和环比上周同日的增减幅度。
        """
        if date_ is None:
            date_ = datetime.utcnow().date()

        revenue = await self.get_daily_revenue_summary(store_id, date_)
        cost = await self.get_daily_cost_summary(store_id, date_)

        net_revenue_fen = revenue["net_revenue_fen"]
        ingredient_cost_fen = cost["ingredient_cost_fen"]
        waste_cost_fen = cost["waste_cost_fen"]

        # 劳动力成本：从 payroll_records 按日分摊，若表不存在则用默认比率估算
        labor_cost_fen = await self._get_labor_cost_fen(store_id, date_)
        if labor_cost_fen == 0 and net_revenue_fen > 0:
            # 兜底：用默认人工成本率估算
            labor_cost_fen = int(net_revenue_fen * DEFAULT_LABOR_COST_RATIO)

        # 毛利润 = 营收 - 食材成本
        gross_profit_fen = net_revenue_fen - ingredient_cost_fen
        gross_margin_pct = self._safe_pct(gross_profit_fen, net_revenue_fen)

        # 净利润 = 毛利润 - 人工成本 - 损耗
        net_profit_fen = gross_profit_fen - labor_cost_fen - waste_cost_fen
        net_margin_pct = self._safe_pct(net_profit_fen, net_revenue_fen)

        # 环比：昨日 & 上周同日
        yesterday = date_ - timedelta(days=1)
        last_week_same = date_ - timedelta(days=7)

        vs_yesterday_pct = await self._compare_net_profit_pct(
            store_id, net_profit_fen, yesterday
        )
        vs_last_week_pct = await self._compare_net_profit_pct(
            store_id, net_profit_fen, last_week_same
        )

        return {
            "store_id": store_id,
            "date": date_.isoformat(),
            "revenue_yuan": self._fen_to_yuan(net_revenue_fen),
            "ingredient_cost_yuan": self._fen_to_yuan(ingredient_cost_fen),
            "gross_profit_yuan": self._fen_to_yuan(gross_profit_fen),
            "gross_margin_pct": gross_margin_pct,
            "labor_cost_yuan": self._fen_to_yuan(labor_cost_fen),
            "waste_cost_yuan": self._fen_to_yuan(waste_cost_fen),
            "net_profit_yuan": self._fen_to_yuan(net_profit_fen),
            "net_margin_pct": net_margin_pct,
            "vs_yesterday_pct": vs_yesterday_pct,
            "vs_last_week_pct": vs_last_week_pct,
        }

    async def _get_labor_cost_fen(self, store_id: str, date_: date) -> int:
        """
        从 payroll_records 按日分摊计算人工成本（分）。
        若表不存在或无数据则返回 0（上层做兜底估算）。
        """
        try:
            labor_sql = text(
                """
                SELECT COALESCE(SUM(daily_wage_fen), 0) AS labor_cost_fen
                FROM payroll_records
                WHERE store_id        = :store_id
                  AND work_date       = :target_date
                  AND status         != 'cancelled'
                """
            )
            row = (
                await self.db.execute(
                    labor_sql, {"store_id": store_id, "target_date": date_}
                )
            ).fetchone()
            return int(row.labor_cost_fen) if row else 0
        except Exception:
            # payroll_records 表可能不存在（Phase 4 阶段）
            return 0

    async def _compare_net_profit_pct(
        self, store_id: str, current_fen: int, compare_date: date
    ) -> float:
        """
        计算当日净利润 vs 对比日净利润的环比变化百分比。
        对比日无数据时返回 0.0。
        """
        try:
            compare = await self.get_real_daily_profit(store_id, compare_date)
            compare_fen = int(compare["net_profit_yuan"] * 100)
            if compare_fen == 0:
                return 0.0
            return round((current_fen - compare_fen) / abs(compare_fen) * 100, 2)
        except Exception:
            return 0.0

    # ─────────────────────────────────────────────
    # 门店月度损益表（P&L）
    # ─────────────────────────────────────────────

    async def get_store_pnl(
        self, store_id: str, year: int, month: int
    ) -> Dict[str, Any]:
        """
        门店月度损益表（P&L）
        真实计算：revenue - cost - labor - overhead = profit
        毛利率 = (revenue - ingredient_cost) / revenue
        净利率 = profit / revenue
        """
        _, last_day = monthrange(year, month)
        start = date(year, month, 1)
        end = date(year, month, last_day)

        # 月度营收：从 orders 表聚合
        revenue_sql = text(
            """
            SELECT
                COALESCE(SUM(final_amount), 0)    AS gross_revenue_fen,
                COALESCE(SUM(discount_amount), 0) AS discount_amount_fen,
                COUNT(*)                          AS order_count
            FROM orders
            WHERE store_id    = :store_id
              AND status      = 'completed'
              AND order_time >= :start_dt
              AND order_time <  :end_dt
            """
        )
        rev_row = (
            await self.db.execute(
                revenue_sql,
                {
                    "store_id": store_id,
                    "start_dt": datetime.combine(start, datetime.min.time()),
                    "end_dt": datetime.combine(end, datetime.max.time()),
                },
            )
        ).fetchone()

        gross_revenue_fen = int(rev_row.gross_revenue_fen) if rev_row else 0
        discount_fen = int(rev_row.discount_amount_fen) if rev_row else 0
        net_revenue_fen = gross_revenue_fen - discount_fen
        order_count = int(rev_row.order_count) if rev_row else 0

        # 月度食材成本：inventory_transactions 出库汇总
        ing_sql = text(
            """
            SELECT COALESCE(SUM(ABS(total_cost)), 0) AS ingredient_cost_fen
            FROM inventory_transactions
            WHERE store_id          = :store_id
              AND transaction_type IN ('usage', 'out', 'adjustment')
              AND total_cost       < 0
              AND created_at      >= :start_dt
              AND created_at      <  :end_dt
            """
        )
        ing_row = (
            await self.db.execute(
                ing_sql,
                {
                    "store_id": store_id,
                    "start_dt": datetime.combine(start, datetime.min.time()),
                    "end_dt": datetime.combine(end, datetime.max.time()),
                },
            )
        ).fetchone()
        ingredient_cost_fen = int(ing_row.ingredient_cost_fen) if ing_row else 0

        # 月度损耗成本
        waste_sql = text(
            """
            SELECT COALESCE(SUM(
                CAST(we.quantity AS NUMERIC) * COALESCE(ii.unit_cost, 0)
            ), 0) AS waste_cost_fen
            FROM waste_events we
            JOIN inventory_items ii ON ii.id = we.ingredient_id
            WHERE we.store_id      = :store_id
              AND we.occurred_at  >= :start_dt
              AND we.occurred_at  <  :end_dt
            """
        )
        waste_row = (
            await self.db.execute(
                waste_sql,
                {
                    "store_id": store_id,
                    "start_dt": datetime.combine(start, datetime.min.time()),
                    "end_dt": datetime.combine(end, datetime.max.time()),
                },
            )
        ).fetchone()
        waste_cost_fen = int(waste_row.waste_cost_fen) if waste_row else 0

        # 月度人工成本（兜底：按默认比率估算）
        labor_cost_fen = await self._get_monthly_labor_cost_fen(store_id, year, month)
        if labor_cost_fen == 0 and net_revenue_fen > 0:
            labor_cost_fen = int(net_revenue_fen * DEFAULT_LABOR_COST_RATIO)

        # P&L 计算
        gross_profit_fen = net_revenue_fen - ingredient_cost_fen
        total_cost_fen = ingredient_cost_fen + labor_cost_fen + waste_cost_fen
        net_profit_fen = net_revenue_fen - total_cost_fen

        gross_margin_pct = self._safe_pct(gross_profit_fen, net_revenue_fen)
        net_margin_pct = self._safe_pct(net_profit_fen, net_revenue_fen)
        food_cost_rate = self._safe_pct(ingredient_cost_fen, net_revenue_fen)
        labor_cost_rate = self._safe_pct(labor_cost_fen, net_revenue_fen)
        waste_rate = self._safe_pct(waste_cost_fen, net_revenue_fen)

        return {
            "store_id": store_id,
            "year": year,
            "month": month,
            "period": f"{year}-{month:02d}",
            "revenue": {
                "gross_revenue_yuan": self._fen_to_yuan(gross_revenue_fen),
                "discount_yuan": self._fen_to_yuan(discount_fen),
                "net_revenue_yuan": self._fen_to_yuan(net_revenue_fen),
                "order_count": order_count,
            },
            "costs": {
                "ingredient_cost_yuan": self._fen_to_yuan(ingredient_cost_fen),
                "labor_cost_yuan": self._fen_to_yuan(labor_cost_fen),
                "waste_cost_yuan": self._fen_to_yuan(waste_cost_fen),
                "total_cost_yuan": self._fen_to_yuan(total_cost_fen),
            },
            "profit": {
                "gross_profit_yuan": self._fen_to_yuan(gross_profit_fen),
                "net_profit_yuan": self._fen_to_yuan(net_profit_fen),
            },
            "margins": {
                "gross_margin_pct": gross_margin_pct,
                "net_margin_pct": net_margin_pct,
                "food_cost_rate": food_cost_rate,
                "labor_cost_rate": labor_cost_rate,
                "waste_rate": waste_rate,
            },
        }

    async def _get_monthly_labor_cost_fen(
        self, store_id: str, year: int, month: int
    ) -> int:
        """从 payroll_records 汇总月度人工成本，表不存在则返回 0"""
        try:
            sql = text(
                """
                SELECT COALESCE(SUM(daily_wage_fen), 0) AS labor_cost_fen
                FROM payroll_records
                WHERE store_id  = :store_id
                  AND EXTRACT(YEAR  FROM work_date) = :year
                  AND EXTRACT(MONTH FROM work_date) = :month
                  AND status   != 'cancelled'
                """
            )
            row = (
                await self.db.execute(
                    sql, {"store_id": store_id, "year": year, "month": month}
                )
            ).fetchone()
            return int(row.labor_cost_fen) if row else 0
        except Exception:
            return 0

    # ─────────────────────────────────────────────
    # 跨店比较（品牌视角）
    # ─────────────────────────────────────────────

    async def get_multi_store_comparison(
        self, brand_id: str, year: int, month: int
    ) -> List[Dict[str, Any]]:
        """
        跨店比较（品牌视角）
        返回该品牌所有门店的：
        [store_id, store_name, revenue_fen, cost_rate, profit_fen, profit_rate]
        按 profit_rate 降序排列
        """
        _, last_day = monthrange(year, month)
        start = date(year, month, 1)
        end = date(year, month, last_day)

        # 先获取品牌下所有门店
        stores_sql = text(
            """
            SELECT id, name
            FROM stores
            WHERE brand_id = :brand_id
              AND status   = 'active'
            ORDER BY name
            """
        )
        stores = (
            await self.db.execute(stores_sql, {"brand_id": brand_id})
        ).fetchall()

        results = []
        for store in stores:
            pnl = await self.get_store_pnl(store.id, year, month)
            net_rev_fen = int(pnl["revenue"]["net_revenue_yuan"] * 100)
            net_profit_fen = int(pnl["profit"]["net_profit_yuan"] * 100)
            total_cost_fen = int(pnl["costs"]["total_cost_yuan"] * 100)
            cost_rate = self._safe_pct(total_cost_fen, net_rev_fen)
            profit_rate = pnl["margins"]["net_margin_pct"]

            results.append(
                {
                    "store_id": store.id,
                    "store_name": store.name,
                    "revenue_yuan": pnl["revenue"]["net_revenue_yuan"],
                    "cost_rate": cost_rate,
                    "profit_yuan": pnl["profit"]["net_profit_yuan"],
                    "profit_rate": profit_rate,
                    "order_count": pnl["revenue"]["order_count"],
                }
            )

        # 按利润率降序排列
        results.sort(key=lambda x: x["profit_rate"], reverse=True)
        return results

    # ─────────────────────────────────────────────
    # 营收明细（按渠道、时段、类别分解）
    # ─────────────────────────────────────────────

    async def get_revenue_breakdown(
        self, store_id: str, start_date: date, end_date: date
    ) -> Dict[str, Any]:
        """
        营收明细（按渠道、时段、类别分解）
          by_channel : {dine_in, meituan, eleme, douyin, miniprogram, unknown}
          by_hour    : {0-23 各小时营收（元）}
          by_category: {各菜品大类营收（元）}
        """
        # 按渠道分组（sales_channel 字段）
        channel_sql = text(
            """
            SELECT
                COALESCE(sales_channel, 'unknown')  AS channel,
                COALESCE(SUM(final_amount), 0)      AS revenue_fen,
                COUNT(*)                            AS order_count
            FROM orders
            WHERE store_id    = :store_id
              AND status      = 'completed'
              AND order_time >= :start_dt
              AND order_time <  :end_dt
            GROUP BY sales_channel
            """
        )
        channel_rows = (
            await self.db.execute(
                channel_sql,
                {
                    "store_id": store_id,
                    "start_dt": datetime.combine(start_date, datetime.min.time()),
                    "end_dt": datetime.combine(end_date, datetime.max.time()),
                },
            )
        ).fetchall()

        by_channel = {
            r.channel: {
                "revenue_yuan": self._fen_to_yuan(int(r.revenue_fen)),
                "order_count": int(r.order_count),
            }
            for r in channel_rows
        }

        # 按小时分组（0-23）
        hour_sql = text(
            """
            SELECT
                EXTRACT(HOUR FROM order_time)      AS hour,
                COALESCE(SUM(final_amount), 0)     AS revenue_fen
            FROM orders
            WHERE store_id    = :store_id
              AND status      = 'completed'
              AND order_time >= :start_dt
              AND order_time <  :end_dt
            GROUP BY EXTRACT(HOUR FROM order_time)
            ORDER BY hour
            """
        )
        hour_rows = (
            await self.db.execute(
                hour_sql,
                {
                    "store_id": store_id,
                    "start_dt": datetime.combine(start_date, datetime.min.time()),
                    "end_dt": datetime.combine(end_date, datetime.max.time()),
                },
            )
        ).fetchall()

        by_hour: Dict[int, float] = {h: 0.0 for h in range(24)}
        for r in hour_rows:
            by_hour[int(r.hour)] = self._fen_to_yuan(int(r.revenue_fen))

        # 按菜品大类分组（order_items JOIN dishes）
        category_sql = text(
            """
            SELECT
                COALESCE(d.category, 'unknown')     AS category,
                COALESCE(SUM(oi.subtotal), 0)       AS revenue_fen
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            JOIN dishes d  ON d.id = oi.dish_id
            WHERE o.store_id    = :store_id
              AND o.status      = 'completed'
              AND o.order_time >= :start_dt
              AND o.order_time <  :end_dt
            GROUP BY d.category
            ORDER BY revenue_fen DESC
            """
        )
        cat_rows = (
            await self.db.execute(
                category_sql,
                {
                    "store_id": store_id,
                    "start_dt": datetime.combine(start_date, datetime.min.time()),
                    "end_dt": datetime.combine(end_date, datetime.max.time()),
                },
            )
        ).fetchall()

        by_category = {
            r.category: self._fen_to_yuan(int(r.revenue_fen)) for r in cat_rows
        }

        return {
            "store_id": store_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "by_channel": by_channel,
            "by_hour": by_hour,
            "by_category": by_category,
        }

    # ─────────────────────────────────────────────
    # 月度财务报告（数据层）
    # ─────────────────────────────────────────────

    async def generate_monthly_report(
        self, store_id: str, year: int, month: int
    ) -> Dict[str, Any]:
        """
        生成月度财务报告（数据层）
        包含：P&L / 现金流概览 / 成本分析 / 与上月对比
        """
        pnl = await self.get_store_pnl(store_id, year, month)

        # 与上月对比
        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1

        prev_pnl = await self.get_store_pnl(store_id, prev_year, prev_month)

        def _delta_pct(current: float, previous: float) -> float:
            if previous == 0:
                return 0.0
            return round((current - previous) / abs(previous) * 100, 2)

        cur_rev = pnl["revenue"]["net_revenue_yuan"]
        pre_rev = prev_pnl["revenue"]["net_revenue_yuan"]
        cur_profit = pnl["profit"]["net_profit_yuan"]
        pre_profit = prev_pnl["profit"]["net_profit_yuan"]

        # 营收明细（全月）
        _, last_day = monthrange(year, month)
        breakdown = await self.get_revenue_breakdown(
            store_id, date(year, month, 1), date(year, month, last_day)
        )

        return {
            "store_id": store_id,
            "report_period": f"{year}-{month:02d}",
            "generated_at": datetime.utcnow().isoformat(),
            "pnl": pnl,
            "revenue_breakdown": breakdown,
            "mom_comparison": {
                "prev_period": f"{prev_year}-{prev_month:02d}",
                "revenue_delta_pct": _delta_pct(cur_rev, pre_rev),
                "profit_delta_pct": _delta_pct(cur_profit, pre_profit),
                "prev_revenue_yuan": pre_rev,
                "prev_profit_yuan": pre_profit,
            },
        }
