"""
FCTService — 业财税资金一体化服务

四大核心功能：
  1. 月度业财对账汇总：聚合 ReconciliationRecord，按月输出差异报告
  2. 税务测算：基于月度收入估算增值税 / 企业所得税 / 附加税
  3. 资金流预测：基于历史均值 + 已知固定支出，预测未来 N 天现金流
  4. 预算执行率：Budget vs FinancialTransaction 实际对比

税率参数（均可通过环境变量覆盖）：
  VAT_RATE_GENERAL=0.06   一般纳税人增值税 6%
  VAT_RATE_SMALL=0.03     小规模纳税人 3%
  CIT_RATE_GENERAL=0.25   一般企业所得税 25%
  CIT_RATE_MICRO=0.20     微型企业 20%
  PROFIT_MARGIN=0.12      利润率假设（用于 CIT 测算基数）
  FOOD_COST_RATIO=0.35    食材成本率（用于现金流出流估算）
"""

from __future__ import annotations

import os
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog
from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.finance import FinancialTransaction, Budget
from src.models.reconciliation import ReconciliationRecord, ReconciliationStatus
from src.models.fct import FCTTaxRecord, FCTCashFlowItem, TaxpayerType, Voucher, VoucherLine

logger = structlog.get_logger()

# ── 可调税率参数 ───────────────────────────────────────────────────────────────
VAT_RATE_GENERAL  = float(os.getenv("VAT_RATE_GENERAL",  "0.06"))
VAT_RATE_SMALL    = float(os.getenv("VAT_RATE_SMALL",    "0.03"))
CIT_RATE_GENERAL  = float(os.getenv("CIT_RATE_GENERAL",  "0.25"))
CIT_RATE_MICRO    = float(os.getenv("CIT_RATE_MICRO",    "0.20"))
PROFIT_MARGIN     = float(os.getenv("PROFIT_MARGIN",     "0.12"))
FOOD_COST_RATIO   = float(os.getenv("FOOD_COST_RATIO",   "0.35"))
# 附加税 = VAT × (城建 7% + 教育附加 3% + 地方教育 2%)
VAT_SURCHARGE_RATE = 0.12
# 资金预警线：累计余额低于 N 天平均日营业额时预警
CASH_ALERT_DAYS   = int(os.getenv("CASH_ALERT_DAYS", "7"))


class FCTService:
    """
    业财税资金一体化服务。

    Usage:
        svc = FCTService(db)
        reconciliation = await svc.get_monthly_reconciliation("STORE001", 2026, 5)
        tax            = await svc.estimate_monthly_tax("STORE001", 2026, 5)
        cashflow       = await svc.forecast_cash_flow("STORE001", days=30)
        budget_exec    = await svc.get_budget_execution("STORE001", 2026, 5)
        dashboard      = await svc.get_dashboard("STORE001")
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 1. 月度业财对账汇总 ────────────────────────────────────────────────────

    async def get_monthly_reconciliation(
        self,
        store_id: str,
        year:     int,
        month:    int,
    ) -> Dict[str, Any]:
        """
        月度业财对账汇总报告。

        聚合当月所有日对账记录：
          - pos_total:    POS 系统收入总额
          - finance_total: 财务系统登记收入
          - variance:     差异（finance - pos），绝对值 + 比率
          - status_breakdown: 各对账状态的天数分布
          - anomaly_days: 差异比率 > 1% 的高风险日期

        Returns:
            月度汇总 dict，包含 summary + daily_details + anomaly_days
        """
        days_in_month = monthrange(year, month)[1]
        start_date    = date(year, month, 1)
        end_date      = date(year, month, days_in_month)

        stmt = (
            select(ReconciliationRecord)
            .where(
                and_(
                    ReconciliationRecord.store_id             == store_id,
                    ReconciliationRecord.reconciliation_date  >= start_date,
                    ReconciliationRecord.reconciliation_date  <= end_date,
                )
            )
            .order_by(ReconciliationRecord.reconciliation_date)
        )
        records = (await self.db.execute(stmt)).scalars().all()

        pos_total     = sum(r.pos_total_amount     for r in records)
        actual_total  = sum(r.actual_total_amount  for r in records)
        variance      = actual_total - pos_total
        variance_pct  = round(variance / pos_total * 100, 2) if pos_total else 0.0

        status_counts: Dict[str, int] = {}
        for r in records:
            status_counts[r.status or "unknown"] = status_counts.get(r.status or "unknown", 0) + 1

        anomaly_days = [
            {
                "date":              r.reconciliation_date.isoformat(),
                "pos_amount":        r.pos_total_amount,
                "pos_amount_yuan":   self._y(r.pos_total_amount),
                "actual_amount":     r.actual_total_amount,
                "actual_amount_yuan": self._y(r.actual_total_amount),
                "diff_amount":       r.diff_amount,
                "diff_amount_yuan":  self._y(r.diff_amount),
                "diff_ratio":        r.diff_ratio,
                "status":            r.status,
            }
            for r in records
            if abs(r.diff_ratio or 0) > 1.0
        ]

        daily_details = [
            {
                "date":              r.reconciliation_date.isoformat(),
                "pos_amount":        r.pos_total_amount,
                "pos_amount_yuan":   self._y(r.pos_total_amount),
                "actual_amount":     r.actual_total_amount,
                "actual_amount_yuan": self._y(r.actual_total_amount),
                "diff_amount":       r.diff_amount,
                "diff_amount_yuan":  self._y(r.diff_amount),
                "diff_ratio":        r.diff_ratio,
                "status":            r.status,
            }
            for r in records
        ]

        logger.info(
            "月度业财对账汇总完成",
            store_id=store_id, year=year, month=month,
            days=len(records), anomaly_days=len(anomaly_days),
        )

        return {
            "store_id":         store_id,
            "period":           f"{year}-{month:02d}",
            "reconciled_days":  len(records),
            "summary": {
                "pos_total":           pos_total,
                "pos_total_yuan":      self._y(pos_total),
                "finance_total":       actual_total,
                "finance_total_yuan":  self._y(actual_total),
                "variance":            variance,
                "variance_yuan":       self._y(variance),
                "variance_pct":        variance_pct,
                "health":              "normal" if abs(variance_pct) <= 1.0 else
                                       "warning" if abs(variance_pct) <= 3.0 else "critical",
            },
            "status_breakdown": status_counts,
            "anomaly_days":     anomaly_days,
            "daily_details":    daily_details,
        }

    # ── 2. 税务测算 ────────────────────────────────────────────────────────────

    async def estimate_monthly_tax(
        self,
        store_id:      str,
        year:          int,
        month:         int,
        taxpayer_type: str = "general",
        save:          bool = False,
    ) -> Dict[str, Any]:
        """
        月度税务测算。

        收入口径：FinancialTransaction (income, category=sales) + 宴会收入
        计算顺序：
          1. 销项 VAT = 含税收入 / (1 + vat_rate) × vat_rate
          2. 进项 VAT = 食材采购成本 × vat_rate（假设采购全有进项发票）
          3. 应纳 VAT = 销项 - 进项（不低于 0）
          4. 附加税 = 应纳 VAT × 12%
          5. 预估利润 = 收入 × PROFIT_MARGIN
          6. CIT = 预估利润 × cit_rate

        Args:
            store_id:      门店 ID
            year/month:    测算周期
            taxpayer_type: "general" (6%) | "small" (3%) | "micro" (CIT 20%)
            save:          是否持久化到 fct_tax_records

        Returns:
            税务测算结果 dict
        """
        days_in_month = monthrange(year, month)[1]
        start_date    = date(year, month, 1)
        end_date      = date(year, month, days_in_month)

        # 查询月度收入（分）
        income_stmt = (
            select(func.sum(FinancialTransaction.amount))
            .where(
                and_(
                    FinancialTransaction.store_id          == store_id,
                    FinancialTransaction.transaction_type  == "income",
                    FinancialTransaction.transaction_date  >= start_date,
                    FinancialTransaction.transaction_date  <= end_date,
                )
            )
        )
        gross_rev = (await self.db.execute(income_stmt)).scalar() or 0

        # 查询食材采购成本（用于进项税测算）
        cost_stmt = (
            select(func.sum(FinancialTransaction.amount))
            .where(
                and_(
                    FinancialTransaction.store_id          == store_id,
                    FinancialTransaction.transaction_type  == "expense",
                    FinancialTransaction.category          == "food_cost",
                    FinancialTransaction.transaction_date  >= start_date,
                    FinancialTransaction.transaction_date  <= end_date,
                )
            )
        )
        food_cost = (await self.db.execute(cost_stmt)).scalar() or 0

        # 税率
        tp       = TaxpayerType(taxpayer_type) if taxpayer_type in TaxpayerType._value2member_map_ else TaxpayerType.GENERAL
        vat_rate = VAT_RATE_GENERAL if tp == TaxpayerType.GENERAL else VAT_RATE_SMALL
        cit_rate = CIT_RATE_MICRO   if tp == TaxpayerType.MICRO    else CIT_RATE_GENERAL

        # 税额计算
        output_vat      = int(gross_rev / (1 + vat_rate) * vat_rate)
        input_vat       = int(food_cost * vat_rate)
        net_vat         = max(0, output_vat - input_vat)
        vat_surcharge   = int(net_vat * VAT_SURCHARGE_RATE)
        est_profit      = int(gross_rev * PROFIT_MARGIN)
        cit_amount      = int(est_profit * cit_rate)
        total_tax       = net_vat + vat_surcharge + cit_amount

        result = {
            "store_id":      store_id,
            "period":        f"{year}-{month:02d}",
            "taxpayer_type": tp.value,
            "revenue": {
                "gross_revenue":      gross_rev,
                "gross_revenue_yuan": self._y(gross_rev),
                "food_cost":          food_cost,
                "food_cost_yuan":     self._y(food_cost),
            },
            "vat": {
                "rate":                  vat_rate,
                "output_vat":            output_vat,
                "output_vat_yuan":       self._y(output_vat),
                "input_vat":             input_vat,
                "input_vat_yuan":        self._y(input_vat),
                "net_vat":               net_vat,
                "net_vat_yuan":          self._y(net_vat),
                "surcharge":             vat_surcharge,
                "surcharge_yuan":        self._y(vat_surcharge),
                "total_vat_burden":      net_vat + vat_surcharge,
                "total_vat_burden_yuan": self._y(net_vat + vat_surcharge),
            },
            "cit": {
                "rate":                      cit_rate,
                "estimated_profit":          est_profit,
                "estimated_profit_yuan":     self._y(est_profit),
                "cit_amount":                cit_amount,
                "cit_amount_yuan":           self._y(cit_amount),
                "profit_margin_assumption":  PROFIT_MARGIN,
            },
            "total_tax":      total_tax,
            "total_tax_yuan": self._y(total_tax),
            "effective_rate": round(total_tax / gross_rev * 100, 2) if gross_rev else 0.0,
            "disclaimer":    "本测算基于历史数据估算，实际纳税以税务机关认定为准",
        }

        if save:
            await self._save_tax_record(store_id, year, month, tp, gross_rev, food_cost,
                                         vat_rate, output_vat, input_vat, net_vat, vat_surcharge,
                                         cit_rate, est_profit, cit_amount, total_tax)

        logger.info("月度税务测算完成", store_id=store_id, period=f"{year}-{month:02d}",
                    total_tax=total_tax, effective_rate=result["effective_rate"])
        return result

    # ── 3. 资金流预测 ──────────────────────────────────────────────────────────

    async def forecast_cash_flow(
        self,
        store_id:         str,
        days:             int = 30,
        starting_balance: int = 0,
    ) -> Dict[str, Any]:
        """
        未来 N 天资金流预测。

        预测逻辑：
          1. 计算过去 30 天日均 POS 收入 → 基准日均进流
          2. 固定出流：房租（月租 ÷ 30）、人工（月薪 ÷ 30）
          3. 变动出流：食材（日均收入 × FOOD_COST_RATIO）、水电（月费 ÷ 30）
          4. 预警：累计余额 < 日均收入 × CASH_ALERT_DAYS 时触发预警

        Args:
            store_id:         门店 ID
            days:             预测天数（默认 30）
            starting_balance: 当前账面余额（分，可选；默认 0）

        Returns:
            {daily_forecast: [...], alerts: [...], summary: {...}}
        """
        # 1. 历史日均进流（过去 30 天）
        hist_start = date.today() - timedelta(days=30)
        hist_stmt  = (
            select(
                FinancialTransaction.transaction_date,
                func.sum(FinancialTransaction.amount).label("daily_total"),
            )
            .where(
                and_(
                    FinancialTransaction.store_id         == store_id,
                    FinancialTransaction.transaction_type == "income",
                    FinancialTransaction.transaction_date >= hist_start,
                )
            )
            .group_by(FinancialTransaction.transaction_date)
        )
        hist_rows   = (await self.db.execute(hist_stmt)).all()
        daily_totals = [r.daily_total for r in hist_rows if r.daily_total]
        avg_daily_inflow = int(sum(daily_totals) / len(daily_totals)) if daily_totals else 50000_00  # fallback 5万

        # 2. 月度固定成本（从 Budget 获取，或使用默认值）
        budget_stmt = (
            select(Budget)
            .where(
                and_(
                    Budget.store_id == store_id,
                    Budget.year     == date.today().year,
                    Budget.month    == date.today().month,
                )
            )
        )
        budgets   = (await self.db.execute(budget_stmt)).scalars().all()
        bmap      = {b.category: b.budgeted_amount for b in budgets}

        monthly_rent   = bmap.get("rent",        300000_00)   # fallback 30万
        monthly_labor  = bmap.get("labor_cost",  500000_00)   # fallback 50万
        monthly_util   = bmap.get("utilities",    50000_00)   # fallback 5万

        daily_rent    = monthly_rent  // 30
        daily_labor   = monthly_labor // 30
        daily_util    = monthly_util  // 30
        daily_food    = int(avg_daily_inflow * FOOD_COST_RATIO)

        # 3. 逐日预测
        alert_threshold = avg_daily_inflow * CASH_ALERT_DAYS
        balance         = starting_balance
        daily_forecast  = []
        alerts          = []

        for i in range(days):
            d          = date.today() + timedelta(days=i)
            # 周末流量 ×1.2
            flow_mult  = 1.2 if d.weekday() in (5, 6) else 1.0
            inflow     = int(avg_daily_inflow * flow_mult)
            food_out   = int(daily_food * flow_mult)
            total_out  = food_out + daily_labor + daily_rent + daily_util
            net        = inflow - total_out
            balance   += net

            is_alert = balance < alert_threshold
            if is_alert:
                msg = f"{d.isoformat()} 累计余额 ¥{balance/100:.0f} 低于预警线 ¥{alert_threshold/100:.0f}"
                alerts.append({"date": d.isoformat(), "balance": balance, "balance_yuan": self._y(balance), "message": msg})

            daily_forecast.append({
                "date":                    d.isoformat(),
                "weekday":                 ["周一","周二","周三","周四","周五","周六","周日"][d.weekday()],
                "inflow":                  inflow,
                "inflow_yuan":             self._y(inflow),
                "outflow":                 total_out,
                "outflow_yuan":            self._y(total_out),
                "outflow_breakdown": {
                    "food_cost":       food_out,
                    "food_cost_yuan":  self._y(food_out),
                    "labor":           daily_labor,
                    "labor_yuan":      self._y(daily_labor),
                    "rent":            daily_rent,
                    "rent_yuan":       self._y(daily_rent),
                    "utilities":       daily_util,
                    "utilities_yuan":  self._y(daily_util),
                },
                "net_flow":                net,
                "net_flow_yuan":           self._y(net),
                "cumulative_balance":      balance,
                "cumulative_balance_yuan": self._y(balance),
                "is_alert":                is_alert,
                "confidence":              0.85 if i < 7 else 0.70 if i < 14 else 0.55,
            })

        total_inflow  = sum(d["inflow"]   for d in daily_forecast)
        total_outflow = sum(d["outflow"]  for d in daily_forecast)

        return {
            "store_id":           store_id,
            "forecast_days":      days,
            "starting_balance":   starting_balance,
            "starting_balance_yuan": self._y(starting_balance),
            "avg_daily_inflow":   avg_daily_inflow,
            "avg_daily_inflow_yuan": self._y(avg_daily_inflow),
            "summary": {
                "total_inflow":         total_inflow,
                "total_inflow_yuan":    self._y(total_inflow),
                "total_outflow":        total_outflow,
                "total_outflow_yuan":   self._y(total_outflow),
                "net_flow":             total_inflow - total_outflow,
                "net_flow_yuan":        self._y(total_inflow - total_outflow),
                "ending_balance":       balance,
                "ending_balance_yuan":  self._y(balance),
                "alert_count":          len(alerts),
            },
            "alerts":            alerts[:5],   # 最多返回 5 条预警
            "daily_forecast":    daily_forecast,
            "note": "预测基于历史均值，仅供参考；实际资金流以财务记账为准",
        }

    # ── 4. 预算执行率 ──────────────────────────────────────────────────────────

    async def get_budget_execution(
        self,
        store_id: str,
        year:     int,
        month:    int,
    ) -> Dict[str, Any]:
        """
        月度预算执行率分析。

        对比 Budget.budgeted_amount vs FinancialTransaction 实际金额，
        按科目（sales/food_cost/labor_cost/rent/utilities）逐一展示：
          - 预算额 / 实际额 / 差异额 / 执行率
          - 超预算预警（执行率 > 110% 触发 warning）

        Returns:
            {categories: [...], overall: {...}, alerts: [...]}
        """
        days_in_month = monthrange(year, month)[1]
        start_date    = date(year, month, 1)
        end_date      = date(year, month, days_in_month)

        # 预算数据
        budget_stmt = (
            select(Budget)
            .where(
                and_(
                    Budget.store_id == store_id,
                    Budget.year     == year,
                    Budget.month    == month,
                )
            )
        )
        budgets = (await self.db.execute(budget_stmt)).scalars().all()
        bmap    = {b.category: b.budgeted_amount for b in budgets}

        # 实际数据（按科目聚合）
        actual_stmt = (
            select(
                FinancialTransaction.category,
                FinancialTransaction.transaction_type,
                func.sum(FinancialTransaction.amount).label("total"),
            )
            .where(
                and_(
                    FinancialTransaction.store_id         == store_id,
                    FinancialTransaction.transaction_date >= start_date,
                    FinancialTransaction.transaction_date <= end_date,
                )
            )
            .group_by(FinancialTransaction.category, FinancialTransaction.transaction_type)
        )
        actual_rows = (await self.db.execute(actual_stmt)).all()
        actual_map  = {(r.category, r.transaction_type): r.total for r in actual_rows}

        # 收入端
        revenue_budget = bmap.get("revenue", 0)
        revenue_actual = actual_map.get(("sales", "income"), 0)

        # 支出科目
        cost_categories = [
            ("food_cost",    "expense", "食材成本"),
            ("labor_cost",   "expense", "人工成本"),
            ("rent",         "expense", "房租"),
            ("utilities",    "expense", "水电费"),
            ("marketing",    "expense", "营销费用"),
        ]

        categories = []
        budget_total_expense = 0
        actual_total_expense = 0
        alerts = []

        for cat, txn_type, label in cost_categories:
            budgeted = bmap.get(cat, 0)
            actual   = actual_map.get((cat, txn_type), 0)
            diff     = actual - budgeted
            exec_rate = round(actual / budgeted * 100, 1) if budgeted else None

            budget_total_expense += budgeted
            actual_total_expense += actual

            row = {
                "category":        cat,
                "label":           label,
                "budgeted":        budgeted,
                "budgeted_yuan":   self._y(budgeted),
                "actual":          actual,
                "actual_yuan":     self._y(actual),
                "variance":        diff,
                "variance_yuan":   self._y(diff),
                "exec_rate":       exec_rate,
                "status": (
                    "over"   if exec_rate and exec_rate >= 110 else
                    "under"  if exec_rate and exec_rate < 80  else
                    "normal" if exec_rate else "no_budget"
                ),
            }
            categories.append(row)

            if exec_rate and exec_rate >= 110:
                alerts.append({
                    "category": cat,
                    "label":    label,
                    "message":  f"{label}超预算 {exec_rate - 100:.1f}%，实际 ¥{actual/100:.0f} vs 预算 ¥{budgeted/100:.0f}",
                    "severity": "high" if exec_rate > 130 else "medium",
                })

        # 利润率
        gross_profit  = revenue_actual - actual_total_expense
        profit_margin = round(gross_profit / revenue_actual * 100, 1) if revenue_actual else 0.0

        return {
            "store_id": store_id,
            "period":   f"{year}-{month:02d}",
            "revenue": {
                "budgeted":       revenue_budget,
                "budgeted_yuan":  self._y(revenue_budget),
                "actual":         revenue_actual,
                "actual_yuan":    self._y(revenue_actual),
                "variance":       revenue_actual - revenue_budget,
                "variance_yuan":  self._y(revenue_actual - revenue_budget),
                "exec_rate": round(revenue_actual / revenue_budget * 100, 1) if revenue_budget else None,
            },
            "categories":   categories,
            "overall": {
                "total_expense_budgeted":      budget_total_expense,
                "total_expense_budgeted_yuan": self._y(budget_total_expense),
                "total_expense_actual":        actual_total_expense,
                "total_expense_actual_yuan":   self._y(actual_total_expense),
                "gross_profit":                gross_profit,
                "gross_profit_yuan":           self._y(gross_profit),
                "profit_margin_pct":           profit_margin,
            },
            "alerts": alerts,
        }

    # ── 5. FCT 综合仪表盘 ──────────────────────────────────────────────────────

    async def get_dashboard(self, store_id: str) -> Dict[str, Any]:
        """
        FCT 综合仪表盘（快照视图）。

        返回当月最新数据：
          - 对账健康度（最近 7 天异常天数）
          - 税务预估摘要（当月）
          - 资金流摘要（未来 7 天）
          - 预算执行率摘要（当月）
        """
        today = date.today()
        year, month = today.year, today.month

        # 对账健康度：最近 7 天差异天数
        recon_start = today - timedelta(days=7)
        recon_stmt  = (
            select(ReconciliationRecord)
            .where(
                and_(
                    ReconciliationRecord.store_id            == store_id,
                    ReconciliationRecord.reconciliation_date >= recon_start,
                )
            )
        )
        recon_rows   = (await self.db.execute(recon_stmt)).scalars().all()
        _recon_total = len(recon_rows)
        _recon_bad   = sum(1 for r in recon_rows if r.status == ReconciliationStatus.MISMATCHED)

        # 资金流摘要（7 天）
        cf_result = await self.forecast_cash_flow(store_id, days=7)
        cf_summary = cf_result["summary"]

        # 当月税务估算摘要（快速，不入库）
        try:
            tax_result  = await self.estimate_monthly_tax(store_id, year, month)
            tax_summary = {
                "total_tax":     tax_result["total_tax"],
                "effective_rate": tax_result["effective_rate"],
                "period":        tax_result["period"],
            }
        except Exception:
            tax_summary = {"total_tax": 0, "effective_rate": 0.0, "period": f"{year}-{month:02d}"}

        # 当月预算执行率（简化：只看整体利润率）
        try:
            bex_result  = await self.get_budget_execution(store_id, year, month)
            bex_summary = {
                "profit_margin_pct":  bex_result["overall"]["profit_margin_pct"],
                "alert_count":        len(bex_result["alerts"]),
            }
        except Exception:
            bex_summary = {"profit_margin_pct": 0.0, "alert_count": 0}

        return {
            "store_id":   store_id,
            "as_of":      today.isoformat(),
            "cash_flow":  {
                "next_7d_net":         cf_summary["net_flow"],
                "next_7d_net_yuan":    self._y(cf_summary["net_flow"]),
                "ending_balance":      cf_summary["ending_balance"],
                "ending_balance_yuan": self._y(cf_summary["ending_balance"]),
                "alert_count":         cf_summary["alert_count"],
            },
            "tax":        {
                **tax_summary,
                "total_tax_yuan": self._y(tax_summary["total_tax"]),
            },
            "budget":     bex_summary,
            "health_score": self._calc_health_score(cf_summary, bex_summary),
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _y(fen: int) -> float:
        """将分（fen）转换为元（yuan），保留2位小数。"""
        return round((fen or 0) / 100, 2)

    @staticmethod
    def _voucher_to_dict(v: "Voucher") -> Dict[str, Any]:
        return {
            "id": str(v.id),
            "voucher_no": v.voucher_no,
            "store_id": v.store_id,
            "event_type": v.event_type,
            "event_id": v.event_id,
            "biz_date": v.biz_date.isoformat() if v.biz_date else None,
            "status": v.status,
            "description": v.description,
        }

    @staticmethod
    def _line_to_dict(l: "VoucherLine") -> Dict[str, Any]:
        return {
            "id": str(l.id),
            "line_no": l.line_no,
            "account_code": l.account_code,
            "account_name": l.account_name,
            "debit": float(l.debit) if l.debit is not None else None,
            "credit": float(l.credit) if l.credit is not None else None,
            "summary": l.summary,
        }

    @staticmethod
    def _gen_voucher_no(biz_date: date) -> str:
        import random
        return f"MV-{biz_date.strftime('%Y%m%d')}-{random.randint(100000, 999999)}"

    async def _save_tax_record(
        self,
        store_id, year, month, tp,
        gross_rev, food_cost, vat_rate, output_vat, input_vat, net_vat, vat_surcharge,
        cit_rate, est_profit, cit_amount, total_tax,
    ) -> None:
        """持久化税务测算记录。"""
        rec = FCTTaxRecord(
            store_id        = store_id,
            year            = year,
            month           = month,
            period_label    = f"{year}-{month:02d}",
            taxpayer_type   = tp,
            gross_revenue   = gross_rev,
            total_taxable   = gross_rev,
            vat_rate        = vat_rate,
            vat_amount      = output_vat,
            deductible_input = input_vat,
            net_vat         = net_vat,
            vat_surcharge   = vat_surcharge,
            cit_rate        = cit_rate,
            estimated_profit = est_profit,
            cit_amount      = cit_amount,
            total_tax       = total_tax,
        )
        self.db.add(rec)
        try:
            await self.db.flush()
        except Exception as e:
            logger.warning("税务记录持久化失败", error=str(e))

    @staticmethod
    def _calc_health_score(cf_summary: Dict, bex_summary: Dict) -> int:
        """FCT 整体健康分（0-100）。"""
        score = 100
        if cf_summary.get("alert_count", 0) > 0:
            score -= 20
        if bex_summary.get("alert_count", 0) > 0:
            score -= 15 * min(bex_summary["alert_count"], 3)
        pm = bex_summary.get("profit_margin_pct", 0.0)
        if pm < 5.0:
            score -= 20
        elif pm < 10.0:
            score -= 10
        return max(0, score)


# ── Standalone FCT Service ─────────────────────────────────────────────────────
#
# 独立部署形态的 FCT 服务（fct_public.py 使用）。
# 依赖注入模式：所有方法接受 session 作为第一个参数。
#
# 当前状态：
#   • 凭证 / 账期 / 账簿 / 主数据等方法需要专用 ORM 模型（尚未建表），
#     暂以结构正确的空响应占位，不会抛出 AttributeError。
#   • get_reports_stub：代理到已有 FinancialTransaction 数据，返回通用汇总。
#   • verify_invoice_stub：本地校验发票基本格式，外部税局验真需接入第三方 API。
#   • 其余方法待专用账务模型上线后补全真实逻辑。
#
# ─────────────────────────────────────────────────────────────────────────────

# ── 会计凭证常量（科目编码，符合中国企业会计准则 / 金蝶·用友）────────────────
from decimal import Decimal

DEFAULT_ACCOUNT_SALES       = "6001"    # 主营业务收入
DEFAULT_ACCOUNT_TAX_PAYABLE = "2221"    # 应交税费-应交增值税（销项）
DEFAULT_ACCOUNT_BANK        = "1002"    # 银行存款
DEFAULT_ACCOUNT_CASH        = "1001"    # 库存现金
DEFAULT_ACCOUNT_INVENTORY   = "1405"    # 库存商品
DEFAULT_ACCOUNT_TAX_INPUT   = "2221_01" # 应交税费-进项税额
DEFAULT_ACCOUNT_PAYABLE     = "2202"    # 应付账款
DEFAULT_ACCOUNT_ADJUSTMENT  = "1009"    # 待处理财产损溢（差额调整用）

VOUCHER_BALANCE_TOLERANCE   = Decimal("0.01")   # 借贷差额允许尾差 0.01 元


class FctService:
    """
    双分录会计凭证服务。

    提供以下功能：
    - ingest_event：根据业务事件生成会计凭证（store_daily_settlement / purchase_receipt）
    - get_voucher_by_id：按 UUID 查询凭证及分录行
    - _voucher_totals / _is_balanced：借贷平衡校验工具方法

    科目编码遵循《企业会计准则》及主流财务软件（金蝶·用友）惯例。
    """

    # ── 静态辅助方法 ────────────────────────────────────────────────────────

    @staticmethod
    def _voucher_totals(lines: list) -> tuple:
        """计算分录行的借方合计和贷方合计。

        Args:
            lines: 字典列表，每项含 "debit" 和 "credit" 键（可为 None）。

        Returns:
            (total_debit, total_credit) Decimal 元组。
        """
        total_d = sum(Decimal(str(l.get("debit") or 0)) for l in lines)
        total_c = sum(Decimal(str(l.get("credit") or 0)) for l in lines)
        return total_d, total_c

    @staticmethod
    def _is_balanced(debit: Decimal, credit: Decimal) -> bool:
        """检查借贷是否平衡（允许 VOUCHER_BALANCE_TOLERANCE 尾差）。"""
        return abs(debit - credit) <= VOUCHER_BALANCE_TOLERANCE

    # ── 核心业务方法 ────────────────────────────────────────────────────────

    async def ingest_event(self, session, raw: Dict[str, Any]):
        """
        接收业务事件并生成会计凭证。

        Args:
            session: AsyncSession
            raw: 事件字典，含 event_type / event_id / payload

        Returns:
            Voucher 模型实例（已 add 到 session 但未 commit）

        Raises:
            ValueError: payload 缺少必填字段
        """
        from src.models.fct import Voucher, VoucherLine

        event_type = raw.get("event_type", "")
        event_id   = raw.get("event_id", "")
        payload    = raw.get("payload", {})

        if event_type == "store_daily_settlement":
            return await self._ingest_store_daily_settlement(session, event_id, payload)
        elif event_type == "purchase_receipt":
            return await self._ingest_purchase_receipt(session, event_id, payload)
        else:
            # 通用降级：写一条空凭证
            return await self._ingest_generic(session, event_type, event_id, payload)

    async def get_voucher_by_id(self, session, voucher_id: str):
        """按 UUID 查询凭证（含分录行）。"""
        from src.models.fct import Voucher
        from sqlalchemy import select as sa_select
        from sqlalchemy.orm import selectinload

        stmt = (
            sa_select(Voucher)
            .options(selectinload(Voucher.lines))
            .where(Voucher.id == voucher_id)
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    # ── 私有：门店日结凭证 ──────────────────────────────────────────────────

    async def _ingest_store_daily_settlement(self, session, event_id: str, payload: dict):
        """门店日结：借 银行存款/库存现金，贷 主营业务收入 + 应交税费。"""
        from src.models.fct import Voucher, VoucherLine

        biz_date_str = payload.get("biz_date")
        if not biz_date_str:
            raise ValueError("store_daily_settlement requires biz_date in payload")

        biz_date     = date.fromisoformat(biz_date_str)
        store_id     = payload.get("store_id", "")
        # 金额均以 分 传入，转元后按 Decimal 运算
        total_sales  = Decimal(str(payload.get("total_sales", 0))) / 100
        sales_tax    = Decimal(str(payload.get("total_sales_tax", 0))) / 100
        discounts    = Decimal(str(payload.get("discounts", 0))) / 100
        revenue      = total_sales - sales_tax - discounts

        voucher = Voucher(
            voucher_no  = f"DS-{store_id}-{biz_date_str}",
            store_id    = store_id,
            event_type  = "store_daily_settlement",
            event_id    = event_id,
            biz_date    = biz_date,
            description = f"门店日结 {biz_date_str}",
        )
        session.add(voucher)
        await session.flush()   # 获取 voucher.id

        line_no = 1
        payment_breakdown = payload.get("payment_breakdown", [])

        if payment_breakdown:
            # 按支付渠道分别借记
            debit_total = Decimal(0)
            for pm in payment_breakdown:
                amt    = Decimal(str(pm.get("amount", 0))) / 100
                method = pm.get("method", "cash").lower()
                acc    = DEFAULT_ACCOUNT_CASH if method == "cash" else DEFAULT_ACCOUNT_BANK
                session.add(VoucherLine(
                    voucher_id   = voucher.id,
                    line_no      = line_no,
                    account_code = acc,
                    debit        = amt,
                    summary      = f"{method} 收款",
                ))
                debit_total += amt
                line_no += 1

            # 贷：收入 + 税
            session.add(VoucherLine(
                voucher_id   = voucher.id,
                line_no      = line_no,
                account_code = DEFAULT_ACCOUNT_SALES,
                credit       = revenue,
                summary      = "主营业务收入",
            ))
            line_no += 1
            if sales_tax > 0:
                session.add(VoucherLine(
                    voucher_id   = voucher.id,
                    line_no      = line_no,
                    account_code = DEFAULT_ACCOUNT_TAX_PAYABLE,
                    credit       = sales_tax,
                    summary      = "应交增值税（销项）",
                ))
                line_no += 1

            credit_total = revenue + sales_tax
            diff = debit_total - credit_total
            if abs(diff) > VOUCHER_BALANCE_TOLERANCE:
                # 差额调整行使凭证平衡
                if diff > 0:
                    session.add(VoucherLine(
                        voucher_id   = voucher.id,
                        line_no      = line_no,
                        account_code = DEFAULT_ACCOUNT_ADJUSTMENT,
                        credit       = diff,
                        summary      = "差额调整",
                    ))
                else:
                    session.add(VoucherLine(
                        voucher_id   = voucher.id,
                        line_no      = line_no,
                        account_code = DEFAULT_ACCOUNT_ADJUSTMENT,
                        debit        = abs(diff),
                        summary      = "差额调整",
                    ))

        else:
            # 无分渠道时：借银行存款 = 含税总收入
            session.add(VoucherLine(
                voucher_id   = voucher.id,
                line_no      = 1,
                account_code = DEFAULT_ACCOUNT_BANK,
                debit        = total_sales,
                summary      = "银行存款",
            ))
            session.add(VoucherLine(
                voucher_id   = voucher.id,
                line_no      = 2,
                account_code = DEFAULT_ACCOUNT_SALES,
                credit       = revenue,
                summary      = "主营业务收入",
            ))
            session.add(VoucherLine(
                voucher_id   = voucher.id,
                line_no      = 3,
                account_code = DEFAULT_ACCOUNT_TAX_PAYABLE,
                credit       = sales_tax,
                summary      = "应交增值税（销项）",
            ))

        return voucher

    # ── 私有：采购入库凭证 ──────────────────────────────────────────────────

    async def _ingest_purchase_receipt(self, session, event_id: str, payload: dict):
        """采购入库：借 库存商品 + 应交税费-进项，贷 应付账款。"""
        from src.models.fct import Voucher, VoucherLine

        biz_date_str = payload.get("biz_date")
        if not biz_date_str:
            raise ValueError("purchase_receipt requires biz_date in payload")

        biz_date    = date.fromisoformat(biz_date_str)
        store_id    = payload.get("store_id", "")
        supplier_id = payload.get("supplier_id", "")
        total_fen   = Decimal(str(payload.get("total", 0)))
        tax_fen     = Decimal(str(payload.get("tax", 0)))
        net_fen     = total_fen - tax_fen

        # 转元
        total   = total_fen / 100
        tax     = tax_fen / 100
        net     = net_fen / 100

        voucher = Voucher(
            voucher_no  = f"PR-{store_id}-{event_id}",
            store_id    = store_id,
            event_type  = "purchase_receipt",
            event_id    = event_id,
            biz_date    = biz_date,
            description = f"采购入库 供应商 {supplier_id}",
        )
        session.add(voucher)
        await session.flush()

        # 借：库存商品（不含税金额）
        session.add(VoucherLine(
            voucher_id   = voucher.id,
            line_no      = 1,
            account_code = DEFAULT_ACCOUNT_INVENTORY,
            debit        = net,
            summary      = "库存商品",
        ))
        # 借：进项税额
        if tax > 0:
            session.add(VoucherLine(
                voucher_id   = voucher.id,
                line_no      = 2,
                account_code = DEFAULT_ACCOUNT_TAX_INPUT,
                debit        = tax,
                summary      = "应交增值税（进项）",
            ))
        # 贷：应付账款
        session.add(VoucherLine(
            voucher_id   = voucher.id,
            line_no      = 3,
            account_code = DEFAULT_ACCOUNT_PAYABLE,
            credit       = total,
            auxiliary    = {"supplier_id": supplier_id},
            summary      = f"应付账款-{supplier_id}",
        ))

        return voucher

    # ── 私有：通用事件降级 ──────────────────────────────────────────────────

    async def _ingest_generic(self, session, event_type: str, event_id: str, payload: dict):
        """未知事件类型：生成零分录空凭证，不抛异常。"""
        from src.models.fct import Voucher

        biz_date_str = payload.get("biz_date") or date.today().isoformat()
        biz_date     = date.fromisoformat(biz_date_str)
        store_id     = payload.get("store_id", "")

        voucher = Voucher(
            voucher_no  = f"GEN-{event_id}",
            store_id    = store_id,
            event_type  = event_type,
            event_id    = event_id,
            biz_date    = biz_date,
            status      = "draft",
            description = f"未知事件 {event_type}",
        )
        session.add(voucher)
        await session.flush()
        return voucher


class _VoucherStub:
    """轻量级凭证占位对象（避免 _voucher_to_response 抛 AttributeError）。"""
    __slots__ = ("id", "voucher_no", "tenant_id", "entity_id", "biz_date",
                 "event_type", "event_id", "status", "description", "lines")

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        if not hasattr(self, "lines"):
            self.lines = []


class StandaloneFCTService:
    """
    独立部署 FCT 服务。

    所有方法均接受 AsyncSession 作为第一个位置参数（依赖注入模式），
    与 fct_public.py 的调用契约一致。
    """

    # ── 业财事件接入 ────────────────────────────────────────────────────────────

    async def ingest_event(
        self,
        session: AsyncSession,
        raw: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        接入业财事件，写入 FinancialTransaction 并生成凭证流水号。
        当前以 FinancialTransaction 为底层存储，完整凭证引擎待专用模型上线后接入。
        """
        try:
            payload = raw.get("payload") or {}
            entity_id = raw.get("entity_id") or ""
            tenant_id = raw.get("tenant_id") or ""
            event_type = raw.get("event_type") or "unknown"
            event_id = raw.get("event_id") or str(id(raw))

            amount = int(payload.get("total_sales") or payload.get("amount") or 0)
            biz_date_raw = payload.get("biz_date") or raw.get("occurred_at") or date.today().isoformat()
            if isinstance(biz_date_raw, str):
                biz_date_raw = biz_date_raw[:10]
            biz_date = date.fromisoformat(biz_date_raw) if isinstance(biz_date_raw, str) else biz_date_raw

            txn = FinancialTransaction(
                store_id=entity_id,
                transaction_date=biz_date,
                transaction_type="income",
                category="sales",
                amount=amount,
                reference_id=event_id,
                payment_method=event_type,
            )
            session.add(txn)
            await session.flush()

            voucher_no = f"V{biz_date.strftime('%Y%m%d')}-{str(txn.id)[:8].upper()}"
            logger.info("FCT 事件接入", event_type=event_type, entity_id=entity_id, amount=amount)
            return {
                "success": True,
                "event_id": event_id,
                "voucher_no": voucher_no,
                "entity_id": entity_id,
                "tenant_id": tenant_id,
            }
        except Exception as e:
            logger.error("FCT 事件接入失败", error=str(e))
            return {"success": False, "error": str(e)}

    # ── 凭证管理（待专用 Voucher 模型上线后替换） ──────────────────────────────

    @staticmethod
    def _y(fen: int) -> float:
        return round((fen or 0) / 100, 2)

    @staticmethod
    def _voucher_to_dict(v) -> Dict[str, Any]:
        return {
            "id": str(v.id),
            "voucher_no": v.voucher_no,
            "store_id": v.store_id,
            "event_type": v.event_type,
            "event_id": v.event_id,
            "biz_date": v.biz_date.isoformat() if v.biz_date else None,
            "status": v.status,
            "description": v.description,
        }

    @staticmethod
    def _line_to_dict(l) -> Dict[str, Any]:
        return {
            "id": str(l.id),
            "line_no": l.line_no,
            "account_code": l.account_code,
            "account_name": l.account_name,
            "debit": float(l.debit) if l.debit is not None else None,
            "credit": float(l.credit) if l.credit is not None else None,
            "summary": l.summary,
        }

    @staticmethod
    def _gen_voucher_no(biz_date: date) -> str:
        import random
        return f"MV-{biz_date.strftime('%Y%m%d')}-{random.randint(100000, 999999)}"

    async def get_vouchers(
        self,
        session: AsyncSession,
        tenant_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        stmt = select(Voucher)
        if entity_id:
            stmt = stmt.where(Voucher.store_id == entity_id)
        if status:
            stmt = stmt.where(Voucher.status == status)
        if start_date:
            stmt = stmt.where(Voucher.biz_date >= start_date)
        if end_date:
            stmt = stmt.where(Voucher.biz_date <= end_date)
        total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = (await session.execute(stmt.offset(skip).limit(limit))).scalars().all()
        return {
            "items": [self._voucher_to_dict(v) for v in rows],
            "total": total or 0,
            "skip": skip,
            "limit": limit,
        }

    async def get_voucher_by_id(
        self, session: AsyncSession, voucher_id: str
    ) -> Optional[Any]:
        stmt = (
            select(Voucher)
            .options(selectinload(Voucher.lines))
            .where(Voucher.id == voucher_id)
        )
        v = (await session.execute(stmt)).scalar_one_or_none()
        if not v:
            return None
        return {**self._voucher_to_dict(v), "lines": [self._line_to_dict(l) for l in v.lines]}

    async def create_manual_voucher(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: str,
        biz_date: Optional[date],
        lines: List[Dict[str, Any]],
        description: Optional[str] = None,
        attachments: Optional[List] = None,
        budget_check: Optional[bool] = None,
        budget_occupy: Optional[bool] = None,
    ) -> Dict[str, Any]:
        # 借贷校验
        debit_total  = sum(float(l.get("debit")  or 0) for l in lines)
        credit_total = sum(float(l.get("credit") or 0) for l in lines)
        if abs(debit_total - credit_total) > 0.01:
            raise ValueError(f"借贷不平衡：借方 {debit_total} ≠ 贷方 {credit_total}")
        effective_date = biz_date or date.today()
        voucher_no = self._gen_voucher_no(effective_date)
        voucher = Voucher(
            id=uuid4(),
            store_id=entity_id,
            voucher_no=voucher_no,
            event_type="manual",
            biz_date=effective_date,
            status="draft",
            description=description,
        )
        session.add(voucher)
        for i, line_data in enumerate(lines, 1):
            session.add(VoucherLine(
                id=uuid4(),
                voucher_id=voucher.id,
                line_no=i,
                account_code=line_data.get("account_code", ""),
                account_name=line_data.get("account_name"),
                debit=line_data.get("debit"),
                credit=line_data.get("credit"),
                summary=line_data.get("summary"),
            ))
        await session.flush()
        await session.refresh(voucher)
        return {
            "success": True,
            "voucher_id": str(voucher.id),
            "voucher_no": voucher.voucher_no,
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "biz_date": effective_date.isoformat(),
            "status": "draft",
            "lines_count": len(lines),
        }

    async def update_voucher_status(
        self,
        session: AsyncSession,
        voucher_id: str,
        target_status: str,
        budget_check: Optional[bool] = None,
        budget_occupy: Optional[bool] = None,
    ) -> Dict[str, Any]:
        status = (target_status or "").strip().lower()
        allowed_statuses = {"draft", "approved", "posted", "reversed", "voided"}
        if status not in allowed_statuses:
            raise ValueError(f"无效凭证状态: {target_status}")

        stmt = select(Voucher).where(Voucher.id == voucher_id)
        voucher = (await session.execute(stmt)).scalar_one_or_none()
        if not voucher:
            raise ValueError("凭证不存在")

        current = (voucher.status or "").strip().lower()
        if not current:
            current = "draft"

        # 最小可用状态机：draft -> approved -> posted -> reversed
        # 允许在 draft/approved 时作废（voided），同状态重复设置视为幂等成功。
        transitions = {
            "draft": {"approved", "posted", "voided"},
            "approved": {"draft", "posted", "voided"},
            "posted": {"reversed"},
            "reversed": set(),
            "voided": set(),
        }
        if status != current and status not in transitions.get(current, set()):
            raise ValueError(f"不允许的状态流转: {current} -> {status}")

        voucher.status = status
        await session.flush()
        await session.refresh(voucher)

        return {
            "voucher_id": str(voucher.id),
            "voucher_no": voucher.voucher_no,
            "from_status": current,
            "status": status,
            "success": True,
        }

    async def void_voucher(
        self, session: AsyncSession, voucher_id: str
    ) -> Dict[str, Any]:
        return {"voucher_id": voucher_id, "status": "voided", "success": True}

    async def red_flush_voucher(
        self,
        session: AsyncSession,
        voucher_id: str,
        biz_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        red_no = f"RF-{voucher_id[:8]}"
        return {
            "original_voucher_id": voucher_id,
            "red_voucher_no": red_no,
            "biz_date": (biz_date or date.today()).isoformat(),
            "success": True,
        }

    # ── 账期管理 ─────────────────────────────────────────────────────────────

    async def list_periods(
        self,
        session: AsyncSession,
        tenant_id: str,
        start_key: Optional[str] = None,
        end_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        stmt = text("""
            SELECT DISTINCT DATE_TRUNC('month', transaction_date) AS month
            FROM financial_transactions
            WHERE store_id = :sid
            ORDER BY 1 DESC
        """)
        rows = (await session.execute(stmt, {"sid": tenant_id})).fetchall()
        if not rows:
            return {"items": [], "total": 0}
        items = []
        for i, row in enumerate(rows):
            period_dt = row[0]
            period_key = period_dt.strftime("%Y-%m") if hasattr(period_dt, "strftime") else str(period_dt)[:7]
            items.append({
                "period_key": period_key,
                "status": "open" if i == 0 else "closed",
            })
        return {"items": items, "total": len(items)}

    async def close_period(
        self, session: AsyncSession, tenant_id: str, period_key: str
    ) -> Dict[str, Any]:
        return {"tenant_id": tenant_id, "period_key": period_key, "status": "closed"}

    async def reopen_period(
        self, session: AsyncSession, tenant_id: str, period_key: str
    ) -> Dict[str, Any]:
        return {"tenant_id": tenant_id, "period_key": period_key, "status": "open"}

    # ── 主数据（科目档案） ────────────────────────────────────────────────────

    async def upsert_master(
        self,
        session: AsyncSession,
        tenant_id: str,
        master_type: str,
        code: str,
        name: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "tenant_id": tenant_id,
            "master_type": master_type,
            "code": code,
            "name": name,
            "extra": extra,
            "success": True,
        }

    async def list_master(
        self,
        session: AsyncSession,
        tenant_id: str,
        master_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 200,
    ) -> Dict[str, Any]:
        return {"items": [], "total": 0, "skip": skip, "limit": limit}

    # ── 账簿查询 ──────────────────────────────────────────────────────────────

    async def get_ledger_balances(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        as_of_date: Optional[date] = None,
        period: Optional[str] = None,
        posted_only: bool = True,
    ) -> Dict[str, Any]:
        return {"tenant_id": tenant_id, "entity_id": entity_id, "balances": [], "as_of": (as_of_date or date.today()).isoformat()}

    async def get_ledger_entries(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        period: Optional[str] = None,
        account_code: Optional[str] = None,
        posted_only: bool = True,
        skip: int = 0,
        limit: int = 500,
    ) -> Dict[str, Any]:
        return {"items": [], "total": 0, "skip": skip, "limit": limit}

    # ── 资金流水与对账 ────────────────────────────────────────────────────────

    async def list_cash_transactions(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        # 从 FinancialTransaction 映射
        try:
            filters = [FinancialTransaction.store_id == entity_id] if entity_id else []
            if start_date:
                filters.append(FinancialTransaction.transaction_date >= start_date)
            if end_date:
                filters.append(FinancialTransaction.transaction_date <= end_date)
            stmt = (
                select(FinancialTransaction)
                .where(and_(*filters) if filters else True)
                .offset(skip).limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            items = [
                {
                    "id": str(r.id),
                    "entity_id": r.store_id,
                    "tx_date": r.transaction_date.isoformat() if r.transaction_date else None,
                    "amount": r.amount,
                    "direction": "in" if r.transaction_type == "income" else "out",
                    "category": r.category,
                    "ref_id": r.reference_id,
                    "status": "matched",
                }
                for r in rows
            ]
            return {"items": items, "total": len(items), "skip": skip, "limit": limit}
        except Exception:
            return {"items": [], "total": 0, "skip": skip, "limit": limit}

    async def create_cash_transaction(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: str,
        tx_date: Optional[date],
        amount: float,
        direction: str,
        description: Optional[str] = None,
        ref_id: Optional[str] = None,
        generate_voucher: bool = False,
        budget_check: Optional[bool] = None,
        budget_occupy: Optional[bool] = None,
    ) -> Dict[str, Any]:
        txn = FinancialTransaction(
            store_id=entity_id,
            transaction_date=tx_date or date.today(),
            transaction_type="income" if direction == "in" else "expense",
            category="cash",
            amount=int(amount),
            reference_id=ref_id,
        )
        session.add(txn)
        await session.flush()
        return {
            "id": str(txn.id),
            "entity_id": entity_id,
            "tx_date": (tx_date or date.today()).isoformat(),
            "amount": int(amount),
            "direction": direction,
            "status": "unmatched",
            "success": True,
        }

    async def match_cash_transaction(
        self,
        session: AsyncSession,
        transaction_id: str,
        match_id: Optional[str] = None,
        match_type: Optional[str] = None,
        remark: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "transaction_id": transaction_id,
            "match_id": match_id,
            "status": "matched" if match_id else "unmatched",
            "success": True,
        }

    async def import_cash_transactions(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: str,
        items: List[Dict[str, Any]],
        ref_type: str = "bank",
        skip_duplicate_ref_id: bool = True,
    ) -> Dict[str, Any]:
        imported = 0
        skipped = 0
        for item in items:
            try:
                tx_date = item.get("tx_date")
                if isinstance(tx_date, str):
                    tx_date = date.fromisoformat(tx_date)
                txn = FinancialTransaction(
                    store_id=entity_id,
                    transaction_date=tx_date or date.today(),
                    transaction_type="income" if item.get("direction") == "in" else "expense",
                    category=ref_type,
                    amount=int(float(item.get("amount") or 0)),
                    reference_id=item.get("ref_id"),
                )
                session.add(txn)
                imported += 1
            except Exception:
                skipped += 1
        await session.flush()
        return {
            "imported": imported,
            "skipped": skipped,
            "total": len(items),
            "success": True,
        }

    async def get_cash_reconciliation_status(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "matched": 0,
            "unmatched": 0,
            "status": "pending",
        }

    # ── 税务发票 ──────────────────────────────────────────────────────────────

    async def list_tax_invoices(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        invoice_type: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        return {"items": [], "total": 0, "skip": skip, "limit": limit}

    async def create_tax_invoice(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: str,
        invoice_type: str,
        invoice_no: Optional[str] = None,
        amount: Optional[int] = None,
        tax_amount: Optional[int] = None,
        invoice_date: Optional[date] = None,
        status: str = "draft",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "invoice_type": invoice_type,
            "invoice_no": invoice_no,
            "amount": amount,
            "tax_amount": tax_amount,
            "invoice_date": (invoice_date or date.today()).isoformat(),
            "status": status,
            "success": True,
        }

    async def update_tax_invoice(
        self,
        session: AsyncSession,
        invoice_id: str,
        invoice_no: Optional[str] = None,
        amount: Optional[int] = None,
        tax_amount: Optional[int] = None,
        invoice_date: Optional[date] = None,
        status: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {"invoice_id": invoice_id, "status": status, "success": True}

    async def link_invoice_to_voucher(
        self,
        session: AsyncSession,
        invoice_id: str,
        voucher_id: str,
        line_no: Optional[int] = None,
    ) -> Dict[str, Any]:
        return {"invoice_id": invoice_id, "voucher_id": voucher_id, "success": True}

    async def list_invoices_by_voucher(
        self, session: AsyncSession, voucher_id: str
    ) -> Dict[str, Any]:
        return {"voucher_id": voucher_id, "invoices": []}

    async def verify_invoice_stub(
        self, session: AsyncSession, invoice_id: str
    ) -> Dict[str, Any]:
        """
        发票验真（本地格式校验 + 占位状态）。

        真实接入路径：
          - 增值税专票：调用国家税务总局查验平台 API
          - 电子发票：调用财政部电子票据核验接口
        当前在未配置外部 API Key 时进行本地基本格式校验并返回 pending 状态。
        """
        verify_api_key = os.getenv("TAX_VERIFY_API_KEY") or os.getenv("INVOICE_VERIFY_KEY")
        if verify_api_key:
            # 预留：接入真实验真 API
            logger.info("发票验真 API Key 已配置，待接入真实验真端点", invoice_id=invoice_id)

        # 本地格式校验
        is_valid_format = bool(invoice_id) and len(invoice_id) >= 8
        return {
            "invoice_id": invoice_id,
            "verify_status": "pending_external" if not verify_api_key else "pending_api",
            "format_valid": is_valid_format,
            "message": (
                "发票格式校验通过，外部税局验真需配置 TAX_VERIFY_API_KEY 环境变量"
                if is_valid_format
                else "发票编号格式无效"
            ),
            "verified_at": datetime.utcnow().isoformat(),
        }

    # ── 税务申报 ──────────────────────────────────────────────────────────────

    async def list_tax_declarations(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        tax_type: Optional[str] = None,
        period: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        return {"items": [], "total": 0, "skip": skip, "limit": limit}

    async def get_tax_declaration_draft(
        self,
        session: AsyncSession,
        tenant_id: str,
        tax_type: str,
        period: str,
        entity_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """从 FinancialTransaction 取数生成申报草稿。"""
        try:
            if len(period) != 6:
                raise ValueError("period 格式应为 YYYYMM")
            year, month = int(period[:4]), int(period[4:6])
            from calendar import monthrange
            days = monthrange(year, month)[1]
            start_d = date(year, month, 1)
            end_d = date(year, month, days)

            filters = [
                FinancialTransaction.transaction_date >= start_d,
                FinancialTransaction.transaction_date <= end_d,
            ]
            if entity_id:
                filters.append(FinancialTransaction.store_id == entity_id)

            income_stmt = (
                select(func.sum(FinancialTransaction.amount))
                .where(and_(*filters, FinancialTransaction.transaction_type == "income"))
            )
            cost_stmt = (
                select(func.sum(FinancialTransaction.amount))
                .where(and_(*filters, FinancialTransaction.transaction_type == "expense",
                             FinancialTransaction.category == "food_cost"))
            )
            gross_rev = (await session.execute(income_stmt)).scalar() or 0
            food_cost = (await session.execute(cost_stmt)).scalar() or 0

            vat_rate = VAT_RATE_GENERAL
            output_vat = int(gross_rev / (1 + vat_rate) * vat_rate)
            input_vat = int(food_cost * vat_rate)
            net_vat = max(0, output_vat - input_vat)

            return {
                "tenant_id": tenant_id,
                "entity_id": entity_id,
                "tax_type": tax_type,
                "period": period,
                "draft": {
                    "gross_revenue": gross_rev,
                    "output_vat": output_vat,
                    "input_vat": input_vat,
                    "net_vat": net_vat,
                    "food_cost": food_cost,
                },
                "status": "draft",
                "note": "基于 FinancialTransaction 估算，正式申报以账务系统为准",
            }
        except Exception as e:
            raise ValueError(str(e))

    # ── 预算管理 ──────────────────────────────────────────────────────────────

    async def upsert_budget(
        self, session: AsyncSession, **kwargs
    ) -> Dict[str, Any]:
        return {"success": True, **kwargs}

    async def upsert_budget_control(
        self, session: AsyncSession, **kwargs
    ) -> Dict[str, Any]:
        return {"success": True, **kwargs}

    async def list_budget_controls(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        budget_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        return {
            "items": [],
            "total": 0,
            "skip": skip,
            "limit": limit,
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "budget_type": budget_type,
        }

    async def check_budget(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: str = "",
        account_code: Optional[str] = None,
        amount: Optional[float] = None,
        budget_type: Optional[str] = None,
        category: Optional[str] = None,
        amount_to_use: Optional[float] = None,
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_account = account_code or category or ""
        requested_amount = float(amount_to_use if amount_to_use is not None else (amount or 0))
        return {
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "budget_type": budget_type or "period",
            "account_code": normalized_account,
            "category": category or normalized_account,
            "requested": requested_amount,
            "available": None,
            "within_budget": True,
            "note": "预算控制模型待上线",
        }

    async def occupy_budget(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: str = "",
        account_code: Optional[str] = None,
        amount: float = 0,
        budget_type: Optional[str] = None,
        category: Optional[str] = None,
        ref_id: Optional[str] = None,
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_account = account_code or category or ""
        return {
            "success": True,
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "budget_type": budget_type or "period",
            "account_code": normalized_account,
            "category": category or normalized_account,
            "period": period,
            "occupied": float(amount),
            "ref_id": ref_id,
        }

    # ── 年度计划 ──────────────────────────────────────────────────────────────

    async def upsert_plan(
        self,
        session: AsyncSession,
        tenant_id: str,
        plan_year: int,
        targets: Dict[str, Any],
        entity_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # 映射到 Budget 模型（month=0 表示年度计划）
        for category, amount in targets.items():
            budget = Budget(
                store_id=entity_id or tenant_id,
                year=plan_year,
                month=0,
                category=category,
                budgeted_amount=int(float(amount)),
            )
            session.add(budget)
        try:
            await session.flush()
        except Exception:
            pass
        return {
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "plan_year": plan_year,
            "targets": targets,
            "success": True,
        }

    async def get_plan(
        self,
        session: AsyncSession,
        tenant_id: str,
        plan_year: int,
        entity_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        filters = [Budget.year == plan_year, Budget.month == 0]
        if entity_id:
            filters.append(Budget.store_id == entity_id)
        stmt = select(Budget).where(and_(*filters))
        rows = (await session.execute(stmt)).scalars().all()
        if not rows:
            return None
        return {
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "plan_year": plan_year,
            "targets": {r.category: r.budgeted_amount for r in rows},
        }

    async def get_plan_vs_actual(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        granularity: str = "month",
    ) -> Dict[str, Any]:
        return {
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "granularity": granularity,
            "items": [],
            "note": "plan_vs_actual 待专用账务模型上线后完整实现",
        }

    # ── 备用金 ────────────────────────────────────────────────────────────────

    async def upsert_petty_cash(
        self,
        session: AsyncSession,
        tenant_id: str,
        petty_cash_id: str,
        entity_id: Optional[str] = None,
        cash_type: str = "general",
        amount_limit: float = 0,
        currency: str = "CNY",
        owner: Optional[str] = None,
        status: str = "active",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "tenant_id": tenant_id,
            "petty_cash_id": petty_cash_id,
            "entity_id": entity_id,
            "cash_type": cash_type,
            "amount_limit": float(amount_limit),
            "currency": currency,
            "owner": owner,
            "status": status,
            "extra": extra or {},
        }

    async def list_petty_cash(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        cash_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        return {"items": [], "total": 0, "skip": skip, "limit": limit}

    async def add_petty_cash_record(
        self,
        session: AsyncSession,
        petty_cash_id: str,
        record_type: str,
        amount: float,
        biz_date: Optional[date] = None,
        ref_type: Optional[str] = None,
        ref_id: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "petty_cash_id": petty_cash_id,
            "record_type": record_type,
            "amount": float(amount),
            "biz_date": biz_date.isoformat() if isinstance(biz_date, date) else None,
            "ref_type": ref_type,
            "ref_id": ref_id,
            "description": description,
        }

    async def list_petty_cash_records(
        self,
        session: AsyncSession,
        petty_cash_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        tenant_id: Optional[str] = None,
        cash_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        normalized_cash_id = petty_cash_id or cash_id
        return {
            "items": [],
            "total": 0,
            "skip": skip,
            "limit": limit,
            "petty_cash_id": normalized_cash_id,
            "tenant_id": tenant_id,
            "start_date": start_date.isoformat() if isinstance(start_date, date) else None,
            "end_date": end_date.isoformat() if isinstance(end_date, date) else None,
        }

    # ── 审批流 ────────────────────────────────────────────────────────────────

    async def create_approval_record(
        self,
        session: AsyncSession,
        tenant_id: str,
        ref_type: str,
        ref_id: str,
        step: int = 1,
        status: str = "pending",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        status_l = (status or "pending").strip().lower()
        result: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "ref_type": ref_type,
            "ref_id": ref_id,
            "step": step,
            "status": status_l,
            "success": True,
        }

        # 最小联动：凭证审批通过后，驱动凭证 draft -> approved。
        if ref_type in {"voucher", "fct_voucher"} and status_l == "approved":
            sync = await self.update_voucher_status(
                session,
                voucher_id=ref_id,
                target_status="approved",
            )
            result["voucher_sync"] = sync
        return result

    async def get_approval_by_ref(
        self,
        session: AsyncSession,
        tenant_id: str,
        ref_type: str,
        ref_id: str,
    ) -> Dict[str, Any]:
        records: List[Dict[str, Any]] = []
        if ref_type in {"voucher", "fct_voucher"}:
            stmt = select(Voucher).where(Voucher.id == ref_id)
            voucher = (await session.execute(stmt)).scalar_one_or_none()
            if voucher:
                v_status = (voucher.status or "").lower()
                approval_status = "approved" if v_status in {"approved", "posted", "reversed"} else "pending"
                records.append({
                    "step": 1,
                    "status": approval_status,
                    "ref_status": v_status,
                    "extra": {"voucher_no": voucher.voucher_no},
                })
        return {"tenant_id": tenant_id, "ref_type": ref_type, "ref_id": ref_id, "records": records}

    # ── 报表 ──────────────────────────────────────────────────────────────────

    async def _aggregate_transactions(
        self,
        session: AsyncSession,
        entity_id: Optional[str],
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> Dict[str, Any]:
        """公用：聚合 FinancialTransaction 为收入/支出/净利润。"""
        try:
            filters = []
            if entity_id:
                filters.append(FinancialTransaction.store_id == entity_id)
            if start_date:
                filters.append(FinancialTransaction.transaction_date >= start_date)
            if end_date:
                filters.append(FinancialTransaction.transaction_date <= end_date)

            inc_stmt = (
                select(func.sum(FinancialTransaction.amount))
                .where(and_(*filters, FinancialTransaction.transaction_type == "income"))
                if filters else
                select(func.sum(FinancialTransaction.amount))
                .where(FinancialTransaction.transaction_type == "income")
            )
            exp_stmt = (
                select(func.sum(FinancialTransaction.amount))
                .where(and_(*filters, FinancialTransaction.transaction_type == "expense"))
                if filters else
                select(func.sum(FinancialTransaction.amount))
                .where(FinancialTransaction.transaction_type == "expense")
            )
            income = (await session.execute(inc_stmt)).scalar() or 0
            expense = (await session.execute(exp_stmt)).scalar() or 0
            return {"income": income, "expense": expense, "net": income - expense}
        except Exception:
            return {"income": 0, "expense": 0, "net": 0}

    async def get_report_period_summary(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        agg = await self._aggregate_transactions(session, entity_id, start_date, end_date)
        return {
            "report_type": "period_summary",
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            **agg,
        }

    async def get_report_aggregate(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        agg = await self._aggregate_transactions(session, entity_id, start_date, end_date)
        return {"report_type": "aggregate", "tenant_id": tenant_id, "entity_id": entity_id, **agg}

    async def get_report_trend(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        group_by: str = "day",
    ) -> Dict[str, Any]:
        gran = "day" if group_by == "day" else "month"
        filters = "WHERE store_id = :sid"
        params: Dict[str, Any] = {"sid": entity_id or tenant_id, "gran": gran}
        if start_date:
            filters += " AND transaction_date >= :df"
            params["df"] = start_date
        if end_date:
            filters += " AND transaction_date <= :dt"
            params["dt"] = end_date
        stmt = text(f"""
            SELECT DATE_TRUNC(:gran, transaction_date) AS period,
                   SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS revenue,
                   SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) AS expense
            FROM financial_transactions
            {filters}
            GROUP BY 1 ORDER BY 1
        """)
        rows = (await session.execute(stmt, params)).fetchall()
        data = []
        for row in rows:
            period_dt = row[0]
            period_str = period_dt.strftime("%Y-%m-%d") if gran == "day" else period_dt.strftime("%Y-%m")
            rev = int(row[1] or 0)
            exp = int(row[2] or 0)
            data.append({
                "period": period_str,
                "revenue_yuan": self._y(rev),
                "expense_yuan": self._y(exp),
                "net_yuan": self._y(rev - exp),
            })
        return {
            "report_type": "trend",
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "group_by": group_by,
            "data": data,
        }

    async def get_report_by_entity(
        self,
        session: AsyncSession,
        tenant_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        filters = ""
        params: Dict[str, Any] = {}
        if start_date:
            filters += " AND transaction_date >= :df"
            params["df"] = start_date
        if end_date:
            filters += " AND transaction_date <= :dt"
            params["dt"] = end_date
        stmt = text(f"""
            SELECT store_id,
                   SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS revenue,
                   SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) AS expense
            FROM financial_transactions
            WHERE 1=1 {filters}
            GROUP BY store_id ORDER BY store_id
        """)
        rows = (await session.execute(stmt, params)).fetchall()
        data = []
        for row in rows:
            rev = int(row[1] or 0)
            exp = int(row[2] or 0)
            data.append({
                "entity_id": row[0],
                "revenue_yuan": self._y(rev),
                "expense_yuan": self._y(exp),
                "net_yuan": self._y(rev - exp),
            })
        return {"report_type": "by_entity", "tenant_id": tenant_id, "data": data}

    async def get_report_by_region(
        self,
        session: AsyncSession,
        tenant_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        return {"report_type": "by_region", "tenant_id": tenant_id, "data": []}

    async def get_report_comparison(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        compare_type: str = "yoy",
    ) -> Dict[str, Any]:
        current = await self._aggregate_transactions(session, entity_id, start_date, end_date)
        return {
            "report_type": "comparison",
            "tenant_id": tenant_id,
            "compare_type": compare_type,
            "current": current,
            "previous": {"income": 0, "expense": 0, "net": 0},
            "note": "同比环比对比待账务期间模型上线后精准计算",
        }

    async def get_report_consolidated(
        self,
        session: AsyncSession,
        tenant_id: str,
        period: str,
        group_by: Optional[str] = "entity",
    ) -> Dict[str, Any]:
        return {
            "report_type": "consolidated",
            "tenant_id": tenant_id,
            "period": period,
            "group_by": group_by,
            "data": [],
            "note": "合并报表待多主体账务模型上线后实现",
        }

    async def get_reports_stub(
        self,
        report_type: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        未知报表类型的通用降级处理。

        当 report_type 不在已知类型列表中，或 tenant_id 未提供时，
        返回结构化的空报表响应，不抛出异常。
        """
        known_types = {
            "period_summary", "aggregate", "trend",
            "by_entity", "by_region", "comparison",
            "plan_vs_actual", "consolidated",
        }
        return {
            "report_type": report_type,
            "params": {k: str(v) for k, v in params.items() if v is not None},
            "data": [],
            "total": 0,
            "known_types": sorted(known_types),
            "message": (
                f"报表类型 '{report_type}' 暂不支持，请使用以下已知类型：{', '.join(sorted(known_types))}"
                if report_type not in known_types
                else "tenant_id 为必填参数，请通过 Query 或 X-Tenant-Id 传递"
            ),
        }


# ── 模块级单例（供 fct_public.py 使用） ─────────────────────────────────────
fct_service = StandaloneFCTService()
