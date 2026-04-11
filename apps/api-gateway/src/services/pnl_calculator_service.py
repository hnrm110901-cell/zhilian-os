"""门店P&L自动核算引擎 — 每日收盘后从 operation_snapshots 生成 store_pnl

核心理念（简化阿米巴）：
  - 每日T+1自动生成，不需要财务手工
  - 店长打开手机就能看到昨天赚了多少钱
  - MTD累计让店长知道"这个月目标完成了多少"
"""

import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class PnlCalculatorService:
    """门店损益核算服务 — 从 operation_snapshots 聚合生成 store_pnl"""

    # ─── 日度 P&L ────────────────────────────────────────────────────────────

    async def generate_daily_pnl(
        self,
        session: AsyncSession,
        store_id: str,
        brand_id: str,
        target_date: date,
    ) -> Dict[str, Any]:
        """从 daily operation_snapshot 生成当日门店损益并 UPSERT 到 store_pnl。

        流程：
        1. 读取 operation_snapshots 中当日 daily 快照
        2. 计算成本比率 / 毛利率 / 营业利润率
        3. MTD 累计 + 目标达成率
        4. 坪效 / 人效
        5. UPSERT store_pnl
        6. 同步 business_objectives.actual_value
        """

        # ── 1. 读取当日快照 ──────────────────────────────────────────────────
        snap_row = (
            await session.execute(
                text(
                    """
                    SELECT *
                      FROM operation_snapshots
                     WHERE store_id    = :sid
                       AND snapshot_date = :d
                       AND period_type  = 'daily'
                    """
                ),
                {"sid": store_id, "d": target_date},
            )
        ).mappings().first()

        if not snap_row:
            logger.info(
                "pnl_no_snapshot",
                store_id=store_id,
                target_date=str(target_date),
            )
            return {"status": "no_data"}

        snap: Dict[str, Any] = dict(snap_row)

        revenue = snap.get("revenue_fen") or 0
        material = snap.get("cost_material_fen") or 0
        labor = snap.get("cost_labor_fen") or 0
        rent = snap.get("cost_rent_fen") or 0
        utility = snap.get("cost_utility_fen") or 0
        platform_fee = snap.get("cost_platform_fee_fen") or 0
        other_cost = snap.get("cost_other_fen") or 0

        total_cost = material + labor + rent + utility + platform_fee + other_cost
        gross_profit = revenue - material
        operating_profit = revenue - total_cost

        # ── 2. 关键比率 ─────────────────────────────────────────────────────
        def _ratio(num: int, denom: int) -> Optional[Decimal]:
            if denom == 0:
                return None
            return round(Decimal(num) / Decimal(denom) * 100, 2)

        material_cost_ratio = _ratio(material, revenue)
        labor_cost_ratio = _ratio(labor, revenue)
        gross_margin = _ratio(gross_profit, revenue)
        operating_margin = _ratio(operating_profit, revenue)

        # ── 3. MTD 累计 ─────────────────────────────────────────────────────
        month_start = target_date.replace(day=1)
        mtd_row = (
            await session.execute(
                text(
                    """
                    SELECT COALESCE(SUM(revenue_fen), 0)    AS mtd_revenue,
                           COALESCE(SUM(net_profit_fen), 0) AS mtd_profit
                      FROM operation_snapshots
                     WHERE store_id     = :sid
                       AND brand_id     = :bid
                       AND period_type  = 'daily'
                       AND snapshot_date BETWEEN :m_start AND :d
                    """
                ),
                {
                    "sid": store_id,
                    "bid": brand_id,
                    "m_start": month_start,
                    "d": target_date,
                },
            )
        ).mappings().first()

        mtd_revenue = int(mtd_row["mtd_revenue"]) if mtd_row else 0
        mtd_profit = int(mtd_row["mtd_profit"]) if mtd_row else 0

        # ── 4. 目标达成率 ────────────────────────────────────────────────────
        mtd_target_pct: Optional[Decimal] = None
        obj_row = (
            await session.execute(
                text(
                    """
                    SELECT target_value
                      FROM business_objectives
                     WHERE brand_id     = :bid
                       AND store_id     = :sid
                       AND metric_code  = 'revenue'
                       AND period_type  = 'monthly'
                       AND fiscal_year  = :fy
                       AND period_value = :pv
                       AND status       = 'active'
                     LIMIT 1
                    """
                ),
                {
                    "bid": brand_id,
                    "sid": store_id,
                    "fy": target_date.year,
                    "pv": target_date.month,
                },
            )
        ).mappings().first()

        if obj_row and obj_row["target_value"]:
            target_val = int(obj_row["target_value"])
            if target_val > 0:
                mtd_target_pct = round(
                    Decimal(mtd_revenue) / Decimal(target_val) * 100, 2
                )

        # ── 5. 坪效 / 人效 ──────────────────────────────────────────────────
        seats_row = (
            await session.execute(
                text("SELECT seats FROM stores WHERE id = :sid"),
                {"sid": store_id},
            )
        ).mappings().first()

        seats = int(seats_row["seats"]) if (seats_row and seats_row["seats"]) else 0
        employee_count = snap.get("employee_count") or 0

        revenue_per_seat = revenue // seats if seats > 0 else None
        revenue_per_employee = revenue // employee_count if employee_count > 0 else None

        # ── 6. UPSERT store_pnl ─────────────────────────────────────────────
        await session.execute(
            text(
                """
                INSERT INTO store_pnl (
                    brand_id, store_id, period_type, period_date,
                    dine_in_revenue_fen, takeout_revenue_fen, delivery_revenue_fen,
                    total_revenue_fen,
                    material_cost_fen, labor_cost_fen, rent_cost_fen,
                    utility_cost_fen, platform_fee_fen, other_cost_fen,
                    total_cost_fen,
                    gross_profit_fen, operating_profit_fen,
                    material_cost_ratio, labor_cost_ratio,
                    gross_margin, operating_margin,
                    revenue_per_seat_fen, revenue_per_employee_fen,
                    mtd_revenue_fen, mtd_profit_fen, mtd_target_pct,
                    is_auto_generated
                ) VALUES (
                    :bid, :sid, 'daily', :d,
                    :dine_in, :takeout, :delivery,
                    :revenue,
                    :material, :labor, :rent,
                    :utility, :platform_fee, :other_cost,
                    :total_cost,
                    :gross_profit, :operating_profit,
                    :material_ratio, :labor_ratio,
                    :gross_mg, :op_mg,
                    :rev_seat, :rev_emp,
                    :mtd_rev, :mtd_pf, :mtd_tgt,
                    TRUE
                )
                ON CONFLICT (brand_id, store_id, period_type, period_date)
                DO UPDATE SET
                    dine_in_revenue_fen     = EXCLUDED.dine_in_revenue_fen,
                    takeout_revenue_fen     = EXCLUDED.takeout_revenue_fen,
                    delivery_revenue_fen    = EXCLUDED.delivery_revenue_fen,
                    total_revenue_fen       = EXCLUDED.total_revenue_fen,
                    material_cost_fen       = EXCLUDED.material_cost_fen,
                    labor_cost_fen          = EXCLUDED.labor_cost_fen,
                    rent_cost_fen           = EXCLUDED.rent_cost_fen,
                    utility_cost_fen        = EXCLUDED.utility_cost_fen,
                    platform_fee_fen        = EXCLUDED.platform_fee_fen,
                    other_cost_fen          = EXCLUDED.other_cost_fen,
                    total_cost_fen          = EXCLUDED.total_cost_fen,
                    gross_profit_fen        = EXCLUDED.gross_profit_fen,
                    operating_profit_fen    = EXCLUDED.operating_profit_fen,
                    material_cost_ratio     = EXCLUDED.material_cost_ratio,
                    labor_cost_ratio        = EXCLUDED.labor_cost_ratio,
                    gross_margin            = EXCLUDED.gross_margin,
                    operating_margin        = EXCLUDED.operating_margin,
                    revenue_per_seat_fen    = EXCLUDED.revenue_per_seat_fen,
                    revenue_per_employee_fen = EXCLUDED.revenue_per_employee_fen,
                    mtd_revenue_fen         = EXCLUDED.mtd_revenue_fen,
                    mtd_profit_fen          = EXCLUDED.mtd_profit_fen,
                    mtd_target_pct          = EXCLUDED.mtd_target_pct,
                    is_auto_generated       = TRUE
                """
            ),
            {
                "bid": brand_id,
                "sid": store_id,
                "d": target_date,
                "dine_in": snap.get("dine_in_order_count", 0),  # 收入明细从快照取
                "takeout": snap.get("takeout_order_count", 0),
                "delivery": snap.get("delivery_order_count", 0),
                "revenue": revenue,
                "material": material,
                "labor": labor,
                "rent": rent,
                "utility": utility,
                "platform_fee": platform_fee,
                "other_cost": other_cost,
                "total_cost": total_cost,
                "gross_profit": gross_profit,
                "operating_profit": operating_profit,
                "material_ratio": material_cost_ratio,
                "labor_ratio": labor_cost_ratio,
                "gross_mg": gross_margin,
                "op_mg": operating_margin,
                "rev_seat": revenue_per_seat,
                "rev_emp": revenue_per_employee,
                "mtd_rev": mtd_revenue,
                "mtd_pf": mtd_profit,
                "mtd_tgt": mtd_target_pct,
            },
        )

        # ── 7. 同步 business_objectives.actual_value ─────────────────────────
        if obj_row:
            await session.execute(
                text(
                    """
                    UPDATE business_objectives
                       SET actual_value = :av,
                           updated_at   = NOW()
                     WHERE brand_id     = :bid
                       AND store_id     = :sid
                       AND metric_code  = 'revenue'
                       AND period_type  = 'monthly'
                       AND fiscal_year  = :fy
                       AND period_value = :pv
                       AND status       = 'active'
                    """
                ),
                {
                    "av": mtd_revenue,
                    "bid": brand_id,
                    "sid": store_id,
                    "fy": target_date.year,
                    "pv": target_date.month,
                },
            )

        await session.commit()

        # ── 8. 日志 ─────────────────────────────────────────────────────────
        logger.info(
            "pnl_daily_generated",
            store_id=store_id,
            target_date=str(target_date),
            revenue_yuan=revenue / 100,
            operating_profit_yuan=operating_profit / 100,
            material_cost_ratio=float(material_cost_ratio) if material_cost_ratio else None,
            mtd_target_pct=float(mtd_target_pct) if mtd_target_pct else None,
        )

        return {
            "status": "ok",
            "period_type": "daily",
            "period_date": str(target_date),
            "revenue_fen": revenue,
            "operating_profit_fen": operating_profit,
            "material_cost_ratio": float(material_cost_ratio) if material_cost_ratio else None,
            "gross_margin": float(gross_margin) if gross_margin else None,
            "mtd_revenue_fen": mtd_revenue,
            "mtd_target_pct": float(mtd_target_pct) if mtd_target_pct else None,
        }

    # ─── 月度 P&L ────────────────────────────────────────────────────────────

    async def generate_monthly_pnl(
        self,
        session: AsyncSession,
        store_id: str,
        brand_id: str,
        month_date: date,
    ) -> Dict[str, Any]:
        """从 monthly operation_snapshot 聚合生成月度 P&L 并计算盈亏平衡线。

        month_date 应为该月 1 日（如 2026-03-01 表示 3 月份）。

        额外产出：UPSERT breakeven_tracker 记录。
        """

        calc_month = month_date.replace(day=1)

        # ── 1. 读取月度快照 ──────────────────────────────────────────────────
        snap_row = (
            await session.execute(
                text(
                    """
                    SELECT *
                      FROM operation_snapshots
                     WHERE store_id     = :sid
                       AND brand_id     = :bid
                       AND snapshot_date = :d
                       AND period_type  = 'monthly'
                    """
                ),
                {"sid": store_id, "bid": brand_id, "d": calc_month},
            )
        ).mappings().first()

        if not snap_row:
            logger.info(
                "pnl_no_monthly_snapshot",
                store_id=store_id,
                month=str(calc_month),
            )
            return {"status": "no_data"}

        snap: Dict[str, Any] = dict(snap_row)

        revenue = snap.get("revenue_fen") or 0
        material = snap.get("cost_material_fen") or 0
        labor = snap.get("cost_labor_fen") or 0
        rent = snap.get("cost_rent_fen") or 0
        utility = snap.get("cost_utility_fen") or 0
        platform_fee = snap.get("cost_platform_fee_fen") or 0
        other_cost = snap.get("cost_other_fen") or 0

        total_cost = material + labor + rent + utility + platform_fee + other_cost
        gross_profit = revenue - material
        operating_profit = revenue - total_cost

        def _ratio(num: int, denom: int) -> Optional[Decimal]:
            if denom == 0:
                return None
            return round(Decimal(num) / Decimal(denom) * 100, 2)

        material_cost_ratio = _ratio(material, revenue)
        labor_cost_ratio = _ratio(labor, revenue)
        gross_margin = _ratio(gross_profit, revenue)
        operating_margin = _ratio(operating_profit, revenue)

        # 坪效 / 人效
        seats_row = (
            await session.execute(
                text("SELECT seats FROM stores WHERE id = :sid"),
                {"sid": store_id},
            )
        ).mappings().first()

        seats = int(seats_row["seats"]) if (seats_row and seats_row["seats"]) else 0
        employee_count = snap.get("employee_count") or 0
        revenue_per_seat = revenue // seats if seats > 0 else None
        revenue_per_employee = revenue // employee_count if employee_count > 0 else None

        # ── 2. UPSERT store_pnl (monthly) ───────────────────────────────────
        await session.execute(
            text(
                """
                INSERT INTO store_pnl (
                    brand_id, store_id, period_type, period_date,
                    total_revenue_fen,
                    material_cost_fen, labor_cost_fen, rent_cost_fen,
                    utility_cost_fen, platform_fee_fen, other_cost_fen,
                    total_cost_fen,
                    gross_profit_fen, operating_profit_fen,
                    material_cost_ratio, labor_cost_ratio,
                    gross_margin, operating_margin,
                    revenue_per_seat_fen, revenue_per_employee_fen,
                    is_auto_generated
                ) VALUES (
                    :bid, :sid, 'monthly', :d,
                    :revenue,
                    :material, :labor, :rent,
                    :utility, :platform_fee, :other_cost,
                    :total_cost,
                    :gross_profit, :operating_profit,
                    :material_ratio, :labor_ratio,
                    :gross_mg, :op_mg,
                    :rev_seat, :rev_emp,
                    TRUE
                )
                ON CONFLICT (brand_id, store_id, period_type, period_date)
                DO UPDATE SET
                    total_revenue_fen       = EXCLUDED.total_revenue_fen,
                    material_cost_fen       = EXCLUDED.material_cost_fen,
                    labor_cost_fen          = EXCLUDED.labor_cost_fen,
                    rent_cost_fen           = EXCLUDED.rent_cost_fen,
                    utility_cost_fen        = EXCLUDED.utility_cost_fen,
                    platform_fee_fen        = EXCLUDED.platform_fee_fen,
                    other_cost_fen          = EXCLUDED.other_cost_fen,
                    total_cost_fen          = EXCLUDED.total_cost_fen,
                    gross_profit_fen        = EXCLUDED.gross_profit_fen,
                    operating_profit_fen    = EXCLUDED.operating_profit_fen,
                    material_cost_ratio     = EXCLUDED.material_cost_ratio,
                    labor_cost_ratio        = EXCLUDED.labor_cost_ratio,
                    gross_margin            = EXCLUDED.gross_margin,
                    operating_margin        = EXCLUDED.operating_margin,
                    revenue_per_seat_fen    = EXCLUDED.revenue_per_seat_fen,
                    revenue_per_employee_fen = EXCLUDED.revenue_per_employee_fen,
                    is_auto_generated       = TRUE
                """
            ),
            {
                "bid": brand_id,
                "sid": store_id,
                "d": calc_month,
                "revenue": revenue,
                "material": material,
                "labor": labor,
                "rent": rent,
                "utility": utility,
                "platform_fee": platform_fee,
                "other_cost": other_cost,
                "total_cost": total_cost,
                "gross_profit": gross_profit,
                "operating_profit": operating_profit,
                "material_ratio": material_cost_ratio,
                "labor_ratio": labor_cost_ratio,
                "gross_mg": gross_margin,
                "op_mg": operating_margin,
                "rev_seat": revenue_per_seat,
                "rev_emp": revenue_per_employee,
            },
        )

        # ── 3. 盈亏平衡线计算 ───────────────────────────────────────────────
        # 固定成本 = 房租 + 基础人力(取labor的60%作为固定部分) + 折旧(暂无独立字段，用utility代替)
        depreciation = 0  # 月度快照暂无 depreciation 字段，后续可扩展
        base_labor = int(labor * 0.6)
        fixed_cost = rent + base_labor + utility + depreciation

        # 变动成本率 = (material + platform_fee) / revenue
        variable_cost_ratio: Optional[Decimal] = None
        breakeven_revenue: Optional[int] = None

        if revenue > 0:
            variable_cost_ratio = round(
                Decimal(material + platform_fee) / Decimal(revenue), 4
            )
            # breakeven = fixed / (1 - vcr)
            denominator = Decimal(1) - variable_cost_ratio
            if denominator > 0:
                breakeven_revenue = int(Decimal(fixed_cost) / denominator)

        # 盈亏平衡天数：看 MTD 哪天累计利润首次 >= 0
        breakeven_day: Optional[int] = None
        customer_count = snap.get("customer_count") or 0
        avg_ticket = snap.get("avg_ticket_fen") or 0
        breakeven_customers: Optional[int] = None
        if breakeven_revenue and avg_ticket > 0:
            breakeven_customers = int(Decimal(breakeven_revenue) / Decimal(avg_ticket)) + 1

        # 判断是否已达保本
        breakeven_reached = revenue >= breakeven_revenue if breakeven_revenue else False

        # ── 4. 门店模型评分（简化版，5维度各0-20分） ─────────────────────────
        score_details: Dict[str, float] = {}

        # 维度1: 盈利能力（operating_margin >= 15% 满分）
        op_mg_val = float(operating_margin) if operating_margin else 0.0
        score_details["profitability"] = min(20.0, round(op_mg_val / 15.0 * 20, 1))

        # 维度2: 成本控制（material_cost_ratio <= 35% 满分）
        mat_val = float(material_cost_ratio) if material_cost_ratio else 50.0
        score_details["cost_control"] = min(
            20.0, round(max(0, (50 - mat_val)) / 15.0 * 20, 1)
        )

        # 维度3: 人效（revenue_per_employee >= 50000分即500元/人 满分）
        rpe = revenue_per_employee or 0
        score_details["labor_efficiency"] = min(20.0, round(rpe / 50000 * 20, 1))

        # 维度4: 客户指标（翻台率 >= 3.0 满分）
        turnover = float(snap.get("table_turnover_rate") or 0)
        score_details["customer"] = min(20.0, round(turnover / 3.0 * 20, 1))

        # 维度5: 增长性（本月营收 vs 上月，暂用固定10分，后续接入环比）
        score_details["growth"] = 10.0

        store_model_score = round(
            sum(score_details.values()), 1
        )

        # ── 5. UPSERT breakeven_tracker ──────────────────────────────────────
        await session.execute(
            text(
                """
                INSERT INTO breakeven_tracker (
                    brand_id, store_id, calc_month,
                    fixed_cost_fen, variable_cost_ratio, breakeven_revenue_fen,
                    breakeven_customers, breakeven_day,
                    actual_revenue_fen, breakeven_reached,
                    store_model_score, score_details,
                    updated_at
                ) VALUES (
                    :bid, :sid, :cm,
                    :fc, :vcr, :br,
                    :bc, :bd,
                    :ar, :reached,
                    :sms, :sd::jsonb,
                    NOW()
                )
                ON CONFLICT (brand_id, store_id, calc_month)
                DO UPDATE SET
                    fixed_cost_fen        = EXCLUDED.fixed_cost_fen,
                    variable_cost_ratio   = EXCLUDED.variable_cost_ratio,
                    breakeven_revenue_fen = EXCLUDED.breakeven_revenue_fen,
                    breakeven_customers   = EXCLUDED.breakeven_customers,
                    breakeven_day         = EXCLUDED.breakeven_day,
                    actual_revenue_fen    = EXCLUDED.actual_revenue_fen,
                    breakeven_reached     = EXCLUDED.breakeven_reached,
                    store_model_score     = EXCLUDED.store_model_score,
                    score_details         = EXCLUDED.score_details,
                    updated_at            = NOW()
                """
            ),
            {
                "bid": brand_id,
                "sid": store_id,
                "cm": calc_month,
                "fc": fixed_cost,
                "vcr": float(variable_cost_ratio) if variable_cost_ratio else 0,
                "br": breakeven_revenue or 0,
                "bc": breakeven_customers,
                "bd": breakeven_day,
                "ar": revenue,
                "reached": breakeven_reached,
                "sms": store_model_score,
                "sd": json.dumps(score_details, ensure_ascii=False),
            },
        )

        await session.commit()

        logger.info(
            "pnl_monthly_generated",
            store_id=store_id,
            month=str(calc_month),
            revenue_yuan=revenue / 100,
            operating_profit_yuan=operating_profit / 100,
            breakeven_yuan=breakeven_revenue / 100 if breakeven_revenue else None,
            store_model_score=store_model_score,
        )

        return {
            "status": "ok",
            "period_type": "monthly",
            "period_date": str(calc_month),
            "revenue_fen": revenue,
            "operating_profit_fen": operating_profit,
            "breakeven_revenue_fen": breakeven_revenue,
            "store_model_score": store_model_score,
            "score_details": score_details,
        }


# 单例，方便外部引用
pnl_calculator_service = PnlCalculatorService()
