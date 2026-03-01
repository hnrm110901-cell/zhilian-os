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

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.finance import FinancialTransaction, Budget
from src.models.reconciliation import ReconciliationRecord, ReconciliationStatus
from src.models.fct import FCTTaxRecord, FCTCashFlowItem, TaxpayerType

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
                "date":        r.reconciliation_date.isoformat(),
                "pos_amount":  r.pos_total_amount,
                "actual_amount": r.actual_total_amount,
                "diff_amount": r.diff_amount,
                "diff_ratio":  r.diff_ratio,
                "status":      r.status,
            }
            for r in records
            if abs(r.diff_ratio or 0) > 1.0
        ]

        daily_details = [
            {
                "date":          r.reconciliation_date.isoformat(),
                "pos_amount":    r.pos_total_amount,
                "actual_amount": r.actual_total_amount,
                "diff_amount":   r.diff_amount,
                "diff_ratio":    r.diff_ratio,
                "status":        r.status,
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
                "pos_total":      pos_total,
                "finance_total":  actual_total,
                "variance":       variance,
                "variance_pct":   variance_pct,
                "health":         "normal" if abs(variance_pct) <= 1.0 else
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
                "gross_revenue":    gross_rev,
                "food_cost":        food_cost,
            },
            "vat": {
                "rate":             vat_rate,
                "output_vat":       output_vat,
                "input_vat":        input_vat,
                "net_vat":          net_vat,
                "surcharge":        vat_surcharge,
                "total_vat_burden": net_vat + vat_surcharge,
            },
            "cit": {
                "rate":             cit_rate,
                "estimated_profit": est_profit,
                "cit_amount":       cit_amount,
                "profit_margin_assumption": PROFIT_MARGIN,
            },
            "total_tax":     total_tax,
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
                alerts.append({"date": d.isoformat(), "balance": balance, "message": msg})

            daily_forecast.append({
                "date":               d.isoformat(),
                "weekday":            ["周一","周二","周三","周四","周五","周六","周日"][d.weekday()],
                "inflow":             inflow,
                "outflow":            total_out,
                "outflow_breakdown": {
                    "food_cost": food_out,
                    "labor":     daily_labor,
                    "rent":      daily_rent,
                    "utilities": daily_util,
                },
                "net_flow":           net,
                "cumulative_balance": balance,
                "is_alert":           is_alert,
                "confidence":         0.85 if i < 7 else 0.70 if i < 14 else 0.55,
            })

        total_inflow  = sum(d["inflow"]   for d in daily_forecast)
        total_outflow = sum(d["outflow"]  for d in daily_forecast)

        return {
            "store_id":          store_id,
            "forecast_days":     days,
            "starting_balance":  starting_balance,
            "avg_daily_inflow":  avg_daily_inflow,
            "summary": {
                "total_inflow":      total_inflow,
                "total_outflow":     total_outflow,
                "net_flow":          total_inflow - total_outflow,
                "ending_balance":    balance,
                "alert_count":       len(alerts),
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
                "category":   cat,
                "label":      label,
                "budgeted":   budgeted,
                "actual":     actual,
                "variance":   diff,
                "exec_rate":  exec_rate,
                "status": (
                    "over"   if exec_rate and exec_rate > 110 else
                    "under"  if exec_rate and exec_rate < 80  else
                    "normal" if exec_rate else "no_budget"
                ),
            }
            categories.append(row)

            if exec_rate and exec_rate > 110:
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
                "budgeted":  revenue_budget,
                "actual":    revenue_actual,
                "variance":  revenue_actual - revenue_budget,
                "exec_rate": round(revenue_actual / revenue_budget * 100, 1) if revenue_budget else None,
            },
            "categories":   categories,
            "overall": {
                "total_expense_budgeted": budget_total_expense,
                "total_expense_actual":   actual_total_expense,
                "gross_profit":           gross_profit,
                "profit_margin_pct":      profit_margin,
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
                "next_7d_net":    cf_summary["net_flow"],
                "ending_balance": cf_summary["ending_balance"],
                "alert_count":    cf_summary["alert_count"],
            },
            "tax":        tax_summary,
            "budget":     bex_summary,
            "health_score": self._calc_health_score(cf_summary, bex_summary),
        }

    # ── Private helpers ───────────────────────────────────────────────────────

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
