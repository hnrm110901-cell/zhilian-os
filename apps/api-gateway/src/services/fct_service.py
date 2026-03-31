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

import inspect
import os
import re
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import structlog
from sqlalchemy import and_, case, exc as sa_exc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.models.fct import (
    FCTApprovalRecord,
    FCTBudgetControl,
    FCTCashFlowItem,
    FCTPettyCash,
    FCTPettyCashRecord,
    FCTTaxRecord,
    TaxpayerType,
    Voucher,
    VoucherLine,
)
from src.models.finance import Budget, FinancialTransaction, Invoice
from src.models.reconciliation import ReconciliationRecord, ReconciliationStatus
from src.models.store import Store

logger = structlog.get_logger()

# ── 可调税率参数 ───────────────────────────────────────────────────────────────
VAT_RATE_GENERAL = float(os.getenv("VAT_RATE_GENERAL", "0.06"))
VAT_RATE_SMALL = float(os.getenv("VAT_RATE_SMALL", "0.03"))
CIT_RATE_GENERAL = float(os.getenv("CIT_RATE_GENERAL", "0.25"))
CIT_RATE_MICRO = float(os.getenv("CIT_RATE_MICRO", "0.20"))
PROFIT_MARGIN = float(os.getenv("PROFIT_MARGIN", "0.12"))
FOOD_COST_RATIO = float(os.getenv("FOOD_COST_RATIO", "0.35"))
# 附加税 = VAT × (城建 7% + 教育附加 3% + 地方教育 2%)
VAT_SURCHARGE_RATE = 0.12
# 资金预警线：累计余额低于 N 天平均日营业额时预警
CASH_ALERT_DAYS = int(os.getenv("CASH_ALERT_DAYS", "7"))


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
        year: int,
        month: int,
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
        start_date = date(year, month, 1)
        end_date = date(year, month, days_in_month)

        stmt = (
            select(ReconciliationRecord)
            .where(
                and_(
                    ReconciliationRecord.store_id == store_id,
                    ReconciliationRecord.reconciliation_date >= start_date,
                    ReconciliationRecord.reconciliation_date <= end_date,
                )
            )
            .order_by(ReconciliationRecord.reconciliation_date)
        )
        records = (await self.db.execute(stmt)).scalars().all()

        pos_total = sum(r.pos_total_amount for r in records)
        actual_total = sum(r.actual_total_amount for r in records)
        variance = actual_total - pos_total
        variance_pct = round(variance / pos_total * 100, 2) if pos_total else 0.0

        status_counts: Dict[str, int] = {}
        for r in records:
            status_counts[r.status or "unknown"] = status_counts.get(r.status or "unknown", 0) + 1

        anomaly_days = [
            {
                "date": r.reconciliation_date.isoformat(),
                "pos_amount": r.pos_total_amount,
                "pos_amount_yuan": self._y(r.pos_total_amount),
                "actual_amount": r.actual_total_amount,
                "actual_amount_yuan": self._y(r.actual_total_amount),
                "diff_amount": r.diff_amount,
                "diff_amount_yuan": self._y(r.diff_amount),
                "diff_ratio": r.diff_ratio,
                "status": r.status,
            }
            for r in records
            if abs(r.diff_ratio or 0) > 1.0
        ]

        daily_details = [
            {
                "date": r.reconciliation_date.isoformat(),
                "pos_amount": r.pos_total_amount,
                "pos_amount_yuan": self._y(r.pos_total_amount),
                "actual_amount": r.actual_total_amount,
                "actual_amount_yuan": self._y(r.actual_total_amount),
                "diff_amount": r.diff_amount,
                "diff_amount_yuan": self._y(r.diff_amount),
                "diff_ratio": r.diff_ratio,
                "status": r.status,
            }
            for r in records
        ]

        logger.info(
            "月度业财对账汇总完成",
            store_id=store_id,
            year=year,
            month=month,
            days=len(records),
            anomaly_days=len(anomaly_days),
        )

        return {
            "store_id": store_id,
            "period": f"{year}-{month:02d}",
            "reconciled_days": len(records),
            "summary": {
                "pos_total": pos_total,
                "pos_total_yuan": self._y(pos_total),
                "finance_total": actual_total,
                "finance_total_yuan": self._y(actual_total),
                "variance": variance,
                "variance_yuan": self._y(variance),
                "variance_pct": variance_pct,
                "health": "normal" if abs(variance_pct) <= 1.0 else "warning" if abs(variance_pct) <= 3.0 else "critical",
            },
            "status_breakdown": status_counts,
            "anomaly_days": anomaly_days,
            "daily_details": daily_details,
        }

    # ── 2. 税务测算 ────────────────────────────────────────────────────────────

    async def estimate_monthly_tax(
        self,
        store_id: str,
        year: int,
        month: int,
        taxpayer_type: str = "general",
        save: bool = False,
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
        start_date = date(year, month, 1)
        end_date = date(year, month, days_in_month)

        # 查询月度收入（分）
        income_stmt = select(func.sum(FinancialTransaction.amount)).where(
            and_(
                FinancialTransaction.store_id == store_id,
                FinancialTransaction.transaction_type == "income",
                FinancialTransaction.transaction_date >= start_date,
                FinancialTransaction.transaction_date <= end_date,
            )
        )
        gross_rev = (await self.db.execute(income_stmt)).scalar() or 0

        # 查询食材采购成本（用于进项税测算）
        cost_stmt = select(func.sum(FinancialTransaction.amount)).where(
            and_(
                FinancialTransaction.store_id == store_id,
                FinancialTransaction.transaction_type == "expense",
                FinancialTransaction.category == "food_cost",
                FinancialTransaction.transaction_date >= start_date,
                FinancialTransaction.transaction_date <= end_date,
            )
        )
        food_cost = (await self.db.execute(cost_stmt)).scalar() or 0

        # 税率
        tp = TaxpayerType(taxpayer_type) if taxpayer_type in TaxpayerType._value2member_map_ else TaxpayerType.GENERAL
        vat_rate = VAT_RATE_GENERAL if tp == TaxpayerType.GENERAL else VAT_RATE_SMALL
        cit_rate = CIT_RATE_MICRO if tp == TaxpayerType.MICRO else CIT_RATE_GENERAL

        # 税额计算
        output_vat = int(gross_rev / (1 + vat_rate) * vat_rate)
        input_vat = int(food_cost * vat_rate)
        net_vat = max(0, output_vat - input_vat)
        vat_surcharge = int(net_vat * VAT_SURCHARGE_RATE)
        est_profit = int(gross_rev * PROFIT_MARGIN)
        cit_amount = int(est_profit * cit_rate)
        total_tax = net_vat + vat_surcharge + cit_amount

        result = {
            "store_id": store_id,
            "period": f"{year}-{month:02d}",
            "taxpayer_type": tp.value,
            "revenue": {
                "gross_revenue": gross_rev,
                "gross_revenue_yuan": self._y(gross_rev),
                "food_cost": food_cost,
                "food_cost_yuan": self._y(food_cost),
            },
            "vat": {
                "rate": vat_rate,
                "output_vat": output_vat,
                "output_vat_yuan": self._y(output_vat),
                "input_vat": input_vat,
                "input_vat_yuan": self._y(input_vat),
                "net_vat": net_vat,
                "net_vat_yuan": self._y(net_vat),
                "surcharge": vat_surcharge,
                "surcharge_yuan": self._y(vat_surcharge),
                "total_vat_burden": net_vat + vat_surcharge,
                "total_vat_burden_yuan": self._y(net_vat + vat_surcharge),
            },
            "cit": {
                "rate": cit_rate,
                "estimated_profit": est_profit,
                "estimated_profit_yuan": self._y(est_profit),
                "cit_amount": cit_amount,
                "cit_amount_yuan": self._y(cit_amount),
                "profit_margin_assumption": PROFIT_MARGIN,
            },
            "total_tax": total_tax,
            "total_tax_yuan": self._y(total_tax),
            "effective_rate": round(total_tax / gross_rev * 100, 2) if gross_rev else 0.0,
            "disclaimer": "本测算基于历史数据估算，实际纳税以税务机关认定为准",
        }

        if save:
            await self._save_tax_record(
                store_id,
                year,
                month,
                tp,
                gross_rev,
                food_cost,
                vat_rate,
                output_vat,
                input_vat,
                net_vat,
                vat_surcharge,
                cit_rate,
                est_profit,
                cit_amount,
                total_tax,
            )

        logger.info(
            "月度税务测算完成",
            store_id=store_id,
            period=f"{year}-{month:02d}",
            total_tax=total_tax,
            effective_rate=result["effective_rate"],
        )
        return result

    # ── 3. 资金流预测 ──────────────────────────────────────────────────────────

    async def forecast_cash_flow(
        self,
        store_id: str,
        days: int = 30,
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
        hist_stmt = (
            select(
                FinancialTransaction.transaction_date,
                func.sum(FinancialTransaction.amount).label("daily_total"),
            )
            .where(
                and_(
                    FinancialTransaction.store_id == store_id,
                    FinancialTransaction.transaction_type == "income",
                    FinancialTransaction.transaction_date >= hist_start,
                )
            )
            .group_by(FinancialTransaction.transaction_date)
        )
        hist_rows = (await self.db.execute(hist_stmt)).all()
        daily_totals = [r.daily_total for r in hist_rows if r.daily_total]
        avg_daily_inflow = int(sum(daily_totals) / len(daily_totals)) if daily_totals else 50000_00  # fallback 5万

        # 2. 月度固定成本（从 Budget 获取，或使用默认值）
        budget_stmt = select(Budget).where(
            and_(
                Budget.store_id == store_id,
                Budget.year == date.today().year,
                Budget.month == date.today().month,
            )
        )
        budgets = (await self.db.execute(budget_stmt)).scalars().all()
        bmap = {b.category: b.budgeted_amount for b in budgets}

        monthly_rent = bmap.get("rent", 300000_00)  # fallback 30万
        monthly_labor = bmap.get("labor_cost", 500000_00)  # fallback 50万
        monthly_util = bmap.get("utilities", 50000_00)  # fallback 5万

        daily_rent = monthly_rent // 30
        daily_labor = monthly_labor // 30
        daily_util = monthly_util // 30
        daily_food = int(avg_daily_inflow * FOOD_COST_RATIO)

        # 3. 逐日预测
        alert_threshold = avg_daily_inflow * CASH_ALERT_DAYS
        balance = starting_balance
        daily_forecast = []
        alerts = []

        for i in range(days):
            d = date.today() + timedelta(days=i)
            # 周末流量 ×1.2
            flow_mult = 1.2 if d.weekday() in (5, 6) else 1.0
            inflow = int(avg_daily_inflow * flow_mult)
            food_out = int(daily_food * flow_mult)
            total_out = food_out + daily_labor + daily_rent + daily_util
            net = inflow - total_out
            balance += net

            is_alert = balance < alert_threshold
            if is_alert:
                msg = f"{d.isoformat()} 累计余额 ¥{balance/100:.0f} 低于预警线 ¥{alert_threshold/100:.0f}"
                alerts.append({"date": d.isoformat(), "balance": balance, "balance_yuan": self._y(balance), "message": msg})

            daily_forecast.append(
                {
                    "date": d.isoformat(),
                    "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][d.weekday()],
                    "inflow": inflow,
                    "inflow_yuan": self._y(inflow),
                    "outflow": total_out,
                    "outflow_yuan": self._y(total_out),
                    "outflow_breakdown": {
                        "food_cost": food_out,
                        "food_cost_yuan": self._y(food_out),
                        "labor": daily_labor,
                        "labor_yuan": self._y(daily_labor),
                        "rent": daily_rent,
                        "rent_yuan": self._y(daily_rent),
                        "utilities": daily_util,
                        "utilities_yuan": self._y(daily_util),
                    },
                    "net_flow": net,
                    "net_flow_yuan": self._y(net),
                    "cumulative_balance": balance,
                    "cumulative_balance_yuan": self._y(balance),
                    "is_alert": is_alert,
                    "confidence": 0.85 if i < 7 else 0.70 if i < 14 else 0.55,
                }
            )

        total_inflow = sum(d["inflow"] for d in daily_forecast)
        total_outflow = sum(d["outflow"] for d in daily_forecast)

        return {
            "store_id": store_id,
            "forecast_days": days,
            "starting_balance": starting_balance,
            "starting_balance_yuan": self._y(starting_balance),
            "avg_daily_inflow": avg_daily_inflow,
            "avg_daily_inflow_yuan": self._y(avg_daily_inflow),
            "summary": {
                "total_inflow": total_inflow,
                "total_inflow_yuan": self._y(total_inflow),
                "total_outflow": total_outflow,
                "total_outflow_yuan": self._y(total_outflow),
                "net_flow": total_inflow - total_outflow,
                "net_flow_yuan": self._y(total_inflow - total_outflow),
                "ending_balance": balance,
                "ending_balance_yuan": self._y(balance),
                "alert_count": len(alerts),
            },
            "alerts": alerts[:5],  # 最多返回 5 条预警
            "daily_forecast": daily_forecast,
            "note": "预测基于历史均值，仅供参考；实际资金流以财务记账为准",
        }

    # ── 4. 预算执行率 ──────────────────────────────────────────────────────────

    async def get_budget_execution(
        self,
        store_id: str,
        year: int,
        month: int,
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
        start_date = date(year, month, 1)
        end_date = date(year, month, days_in_month)

        # 预算数据
        budget_stmt = select(Budget).where(
            and_(
                Budget.store_id == store_id,
                Budget.year == year,
                Budget.month == month,
            )
        )
        budgets = (await self.db.execute(budget_stmt)).scalars().all()
        bmap = {b.category: b.budgeted_amount for b in budgets}

        # 实际数据（按科目聚合）
        actual_stmt = (
            select(
                FinancialTransaction.category,
                FinancialTransaction.transaction_type,
                func.sum(FinancialTransaction.amount).label("total"),
            )
            .where(
                and_(
                    FinancialTransaction.store_id == store_id,
                    FinancialTransaction.transaction_date >= start_date,
                    FinancialTransaction.transaction_date <= end_date,
                )
            )
            .group_by(FinancialTransaction.category, FinancialTransaction.transaction_type)
        )
        actual_rows = (await self.db.execute(actual_stmt)).all()
        actual_map = {(r.category, r.transaction_type): r.total for r in actual_rows}

        # 收入端
        revenue_budget = bmap.get("revenue", 0)
        revenue_actual = actual_map.get(("sales", "income"), 0)

        # 支出科目
        cost_categories = [
            ("food_cost", "expense", "食材成本"),
            ("labor_cost", "expense", "人工成本"),
            ("rent", "expense", "房租"),
            ("utilities", "expense", "水电费"),
            ("marketing", "expense", "营销费用"),
        ]

        categories = []
        budget_total_expense = 0
        actual_total_expense = 0
        alerts = []

        for cat, txn_type, label in cost_categories:
            budgeted = bmap.get(cat, 0)
            actual = actual_map.get((cat, txn_type), 0)
            diff = actual - budgeted
            exec_rate = round(actual / budgeted * 100, 1) if budgeted else None

            budget_total_expense += budgeted
            actual_total_expense += actual

            row = {
                "category": cat,
                "label": label,
                "budgeted": budgeted,
                "budgeted_yuan": self._y(budgeted),
                "actual": actual,
                "actual_yuan": self._y(actual),
                "variance": diff,
                "variance_yuan": self._y(diff),
                "exec_rate": exec_rate,
                "status": (
                    "over"
                    if exec_rate and exec_rate >= 110
                    else "under" if exec_rate and exec_rate < 80 else "normal" if exec_rate else "no_budget"
                ),
            }
            categories.append(row)

            if exec_rate and exec_rate >= 110:
                alerts.append(
                    {
                        "category": cat,
                        "label": label,
                        "message": f"{label}超预算 {exec_rate - 100:.1f}%，实际 ¥{actual/100:.0f} vs 预算 ¥{budgeted/100:.0f}",
                        "severity": "high" if exec_rate > 130 else "medium",
                    }
                )

        # 利润率
        gross_profit = revenue_actual - actual_total_expense
        profit_margin = round(gross_profit / revenue_actual * 100, 1) if revenue_actual else 0.0

        return {
            "store_id": store_id,
            "period": f"{year}-{month:02d}",
            "revenue": {
                "budgeted": revenue_budget,
                "budgeted_yuan": self._y(revenue_budget),
                "actual": revenue_actual,
                "actual_yuan": self._y(revenue_actual),
                "variance": revenue_actual - revenue_budget,
                "variance_yuan": self._y(revenue_actual - revenue_budget),
                "exec_rate": round(revenue_actual / revenue_budget * 100, 1) if revenue_budget else None,
            },
            "categories": categories,
            "overall": {
                "total_expense_budgeted": budget_total_expense,
                "total_expense_budgeted_yuan": self._y(budget_total_expense),
                "total_expense_actual": actual_total_expense,
                "total_expense_actual_yuan": self._y(actual_total_expense),
                "gross_profit": gross_profit,
                "gross_profit_yuan": self._y(gross_profit),
                "profit_margin_pct": profit_margin,
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
        recon_stmt = select(ReconciliationRecord).where(
            and_(
                ReconciliationRecord.store_id == store_id,
                ReconciliationRecord.reconciliation_date >= recon_start,
            )
        )
        recon_rows = (await self.db.execute(recon_stmt)).scalars().all()
        _recon_total = len(recon_rows)
        _recon_bad = sum(1 for r in recon_rows if r.status == ReconciliationStatus.MISMATCHED)

        # 资金流摘要（7 天）
        cf_result = await self.forecast_cash_flow(store_id, days=7)
        cf_summary = cf_result["summary"]

        # 当月税务估算摘要（快速，不入库）
        try:
            tax_result = await self.estimate_monthly_tax(store_id, year, month)
            tax_summary = {
                "total_tax": tax_result["total_tax"],
                "effective_rate": tax_result["effective_rate"],
                "period": tax_result["period"],
            }
        except (sa_exc.SQLAlchemyError, ValueError, KeyError):
            tax_summary = {"total_tax": 0, "effective_rate": 0.0, "period": f"{year}-{month:02d}"}

        # 当月预算执行率（简化：只看整体利润率）
        try:
            bex_result = await self.get_budget_execution(store_id, year, month)
            bex_summary = {
                "profit_margin_pct": bex_result["overall"]["profit_margin_pct"],
                "alert_count": len(bex_result["alerts"]),
            }
        except (sa_exc.SQLAlchemyError, ValueError, KeyError):
            bex_summary = {"profit_margin_pct": 0.0, "alert_count": 0}

        return {
            "store_id": store_id,
            "as_of": today.isoformat(),
            "cash_flow": {
                "next_7d_net": cf_summary["net_flow"],
                "next_7d_net_yuan": self._y(cf_summary["net_flow"]),
                "ending_balance": cf_summary["ending_balance"],
                "ending_balance_yuan": self._y(cf_summary["ending_balance"]),
                "alert_count": cf_summary["alert_count"],
            },
            "tax": {
                **tax_summary,
                "total_tax_yuan": self._y(tax_summary["total_tax"]),
            },
            "budget": bex_summary,
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
        store_id,
        year,
        month,
        tp,
        gross_rev,
        food_cost,
        vat_rate,
        output_vat,
        input_vat,
        net_vat,
        vat_surcharge,
        cit_rate,
        est_profit,
        cit_amount,
        total_tax,
    ) -> None:
        """持久化税务测算记录。"""
        rec = FCTTaxRecord(
            store_id=store_id,
            year=year,
            month=month,
            period_label=f"{year}-{month:02d}",
            taxpayer_type=tp,
            gross_revenue=gross_rev,
            total_taxable=gross_rev,
            vat_rate=vat_rate,
            vat_amount=output_vat,
            deductible_input=input_vat,
            net_vat=net_vat,
            vat_surcharge=vat_surcharge,
            cit_rate=cit_rate,
            estimated_profit=est_profit,
            cit_amount=cit_amount,
            total_tax=total_tax,
        )
        self.db.add(rec)
        try:
            await self.db.flush()
        except sa_exc.SQLAlchemyError as e:
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

DEFAULT_ACCOUNT_SALES = "6001"  # 主营业务收入
DEFAULT_ACCOUNT_TAX_PAYABLE = "2221"  # 应交税费-应交增值税（销项）
DEFAULT_ACCOUNT_BANK = "1002"  # 银行存款
DEFAULT_ACCOUNT_CASH = "1001"  # 库存现金
DEFAULT_ACCOUNT_INVENTORY = "1405"  # 库存商品
DEFAULT_ACCOUNT_TAX_INPUT = "2221_01"  # 应交税费-进项税额
DEFAULT_ACCOUNT_PAYABLE = "2202"  # 应付账款
DEFAULT_ACCOUNT_ADJUSTMENT = "1009"  # 待处理财产损溢（差额调整用）

VOUCHER_BALANCE_TOLERANCE = Decimal("0.01")  # 借贷差额允许尾差 0.01 元


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
        event_id = raw.get("event_id", "")
        payload = raw.get("payload", {})

        if event_type == "store_daily_settlement":
            return await self._ingest_store_daily_settlement(session, event_id, payload)
        elif event_type == "purchase_receipt":
            return await self._ingest_purchase_receipt(session, event_id, payload)
        else:
            # 通用降级：写一条空凭证
            return await self._ingest_generic(session, event_type, event_id, payload)

    async def get_voucher_by_id(self, session, voucher_id: str):
        """按 UUID 查询凭证（含分录行）。"""
        from sqlalchemy import select as sa_select
        from sqlalchemy.orm import selectinload
        from src.models.fct import Voucher

        stmt = sa_select(Voucher).options(selectinload(Voucher.lines)).where(Voucher.id == voucher_id)
        result = await session.execute(stmt)
        return result.scalars().first()

    # ── 私有：门店日结凭证 ──────────────────────────────────────────────────

    async def _ingest_store_daily_settlement(self, session, event_id: str, payload: dict):
        """门店日结：借 银行存款/库存现金，贷 主营业务收入 + 应交税费。"""
        from src.models.fct import Voucher, VoucherLine

        biz_date_str = payload.get("biz_date")
        if not biz_date_str:
            raise ValueError("store_daily_settlement requires biz_date in payload")

        biz_date = date.fromisoformat(biz_date_str)
        store_id = payload.get("store_id", "")
        # 金额均以 分 传入，转元后按 Decimal 运算
        total_sales = Decimal(str(payload.get("total_sales", 0))) / 100
        sales_tax = Decimal(str(payload.get("total_sales_tax", 0))) / 100
        discounts = Decimal(str(payload.get("discounts", 0))) / 100
        revenue = total_sales - sales_tax - discounts

        voucher = Voucher(
            voucher_no=f"DS-{store_id}-{biz_date_str}",
            store_id=store_id,
            event_type="store_daily_settlement",
            event_id=event_id,
            biz_date=biz_date,
            description=f"门店日结 {biz_date_str}",
        )
        session.add(voucher)
        await session.flush()  # 获取 voucher.id

        line_no = 1
        payment_breakdown = payload.get("payment_breakdown", [])

        if payment_breakdown:
            # 按支付渠道分别借记
            debit_total = Decimal(0)
            for pm in payment_breakdown:
                amt = Decimal(str(pm.get("amount", 0))) / 100
                method = pm.get("method", "cash").lower()
                acc = DEFAULT_ACCOUNT_CASH if method == "cash" else DEFAULT_ACCOUNT_BANK
                session.add(
                    VoucherLine(
                        voucher_id=voucher.id,
                        line_no=line_no,
                        account_code=acc,
                        debit=amt,
                        summary=f"{method} 收款",
                    )
                )
                debit_total += amt
                line_no += 1

            # 贷：收入 + 税
            session.add(
                VoucherLine(
                    voucher_id=voucher.id,
                    line_no=line_no,
                    account_code=DEFAULT_ACCOUNT_SALES,
                    credit=revenue,
                    summary="主营业务收入",
                )
            )
            line_no += 1
            if sales_tax > 0:
                session.add(
                    VoucherLine(
                        voucher_id=voucher.id,
                        line_no=line_no,
                        account_code=DEFAULT_ACCOUNT_TAX_PAYABLE,
                        credit=sales_tax,
                        summary="应交增值税（销项）",
                    )
                )
                line_no += 1

            credit_total = revenue + sales_tax
            diff = debit_total - credit_total
            if abs(diff) > VOUCHER_BALANCE_TOLERANCE:
                # 差额调整行使凭证平衡
                if diff > 0:
                    session.add(
                        VoucherLine(
                            voucher_id=voucher.id,
                            line_no=line_no,
                            account_code=DEFAULT_ACCOUNT_ADJUSTMENT,
                            credit=diff,
                            summary="差额调整",
                        )
                    )
                else:
                    session.add(
                        VoucherLine(
                            voucher_id=voucher.id,
                            line_no=line_no,
                            account_code=DEFAULT_ACCOUNT_ADJUSTMENT,
                            debit=abs(diff),
                            summary="差额调整",
                        )
                    )

        else:
            # 无分渠道时：借银行存款 = 含税总收入
            session.add(
                VoucherLine(
                    voucher_id=voucher.id,
                    line_no=1,
                    account_code=DEFAULT_ACCOUNT_BANK,
                    debit=total_sales,
                    summary="银行存款",
                )
            )
            session.add(
                VoucherLine(
                    voucher_id=voucher.id,
                    line_no=2,
                    account_code=DEFAULT_ACCOUNT_SALES,
                    credit=revenue,
                    summary="主营业务收入",
                )
            )
            session.add(
                VoucherLine(
                    voucher_id=voucher.id,
                    line_no=3,
                    account_code=DEFAULT_ACCOUNT_TAX_PAYABLE,
                    credit=sales_tax,
                    summary="应交增值税（销项）",
                )
            )

        return voucher

    # ── 私有：采购入库凭证 ──────────────────────────────────────────────────

    async def _ingest_purchase_receipt(self, session, event_id: str, payload: dict):
        """采购入库：借 库存商品 + 应交税费-进项，贷 应付账款。"""
        from src.models.fct import Voucher, VoucherLine

        biz_date_str = payload.get("biz_date")
        if not biz_date_str:
            raise ValueError("purchase_receipt requires biz_date in payload")

        biz_date = date.fromisoformat(biz_date_str)
        store_id = payload.get("store_id", "")
        supplier_id = payload.get("supplier_id", "")
        total_fen = Decimal(str(payload.get("total", 0)))
        tax_fen = Decimal(str(payload.get("tax", 0)))
        net_fen = total_fen - tax_fen

        # 转元
        total = total_fen / 100
        tax = tax_fen / 100
        net = net_fen / 100

        voucher = Voucher(
            voucher_no=f"PR-{store_id}-{event_id}",
            store_id=store_id,
            event_type="purchase_receipt",
            event_id=event_id,
            biz_date=biz_date,
            description=f"采购入库 供应商 {supplier_id}",
        )
        session.add(voucher)
        await session.flush()

        # 借：库存商品（不含税金额）
        session.add(
            VoucherLine(
                voucher_id=voucher.id,
                line_no=1,
                account_code=DEFAULT_ACCOUNT_INVENTORY,
                debit=net,
                summary="库存商品",
            )
        )
        # 借：进项税额
        if tax > 0:
            session.add(
                VoucherLine(
                    voucher_id=voucher.id,
                    line_no=2,
                    account_code=DEFAULT_ACCOUNT_TAX_INPUT,
                    debit=tax,
                    summary="应交增值税（进项）",
                )
            )
        # 贷：应付账款
        session.add(
            VoucherLine(
                voucher_id=voucher.id,
                line_no=3,
                account_code=DEFAULT_ACCOUNT_PAYABLE,
                credit=total,
                auxiliary={"supplier_id": supplier_id},
                summary=f"应付账款-{supplier_id}",
            )
        )

        return voucher

    # ── 私有：通用事件降级 ──────────────────────────────────────────────────

    async def _ingest_generic(self, session, event_type: str, event_id: str, payload: dict):
        """未知事件类型：生成零分录空凭证，不抛异常。"""
        from src.models.fct import Voucher

        biz_date_str = payload.get("biz_date") or date.today().isoformat()
        biz_date = date.fromisoformat(biz_date_str)
        store_id = payload.get("store_id", "")

        voucher = Voucher(
            voucher_no=f"GEN-{event_id}",
            store_id=store_id,
            event_type=event_type,
            event_id=event_id,
            biz_date=biz_date,
            status="draft",
            description=f"未知事件 {event_type}",
        )
        session.add(voucher)
        await session.flush()
        return voucher


class _VoucherStub:
    """轻量级凭证占位对象（避免 _voucher_to_response 抛 AttributeError）。"""

    __slots__ = (
        "id",
        "voucher_no",
        "tenant_id",
        "entity_id",
        "biz_date",
        "event_type",
        "event_id",
        "status",
        "description",
        "lines",
    )

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

    PERIOD_KEY_RE = re.compile(r"^\d{4}-\d{2}$")
    PERIOD_STATUS_VALUES = {"open", "closed"}

    def __init__(self):
        # 账期状态覆盖（运行时）：默认“最新 open，其余 closed”
        self._period_status_overrides: Dict[tuple[str, str], str] = {}

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
        except (sa_exc.SQLAlchemyError, ValueError, KeyError, TypeError) as e:
            logger.error("FCT 事件接入失败", error=str(e))
            return {"success": False, "error": str(e)}

    # ── 凭证管理（待专用 Voucher 模型上线后替换） ──────────────────────────────

    @staticmethod
    def _y(fen: int) -> float:
        return round((fen or 0) / 100, 2)

    @staticmethod
    def _as_flag(value: Any) -> str:
        return "true" if str(value).strip().lower() in {"1", "true", "yes", "on"} else "false"

    @staticmethod
    def _flag_to_bool(value: Any) -> bool:
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _parse_uuid_or_none(value: Optional[str]) -> Optional[UUID]:
        if not value:
            return None
        try:
            return UUID(str(value))
        except (ValueError, AttributeError):
            return None

    async def _resolve_budget_policy(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: str,
        budget_type: str,
        category: str,
    ) -> Dict[str, bool]:
        candidates = [
            (entity_id or "", category or ""),
            (entity_id or "", ""),
            ("", category or ""),
            ("", ""),
        ]
        for cand_entity, cand_category in candidates:
            stmt = select(FCTBudgetControl).where(
                and_(
                    FCTBudgetControl.tenant_id == tenant_id,
                    FCTBudgetControl.entity_id == cand_entity,
                    FCTBudgetControl.budget_type == budget_type,
                    FCTBudgetControl.category == cand_category,
                )
            )
            try:
                result = await session.execute(stmt)
                scalars = None
                if hasattr(result, "scalars"):
                    maybe_scalars = result.scalars()
                    scalars = await maybe_scalars if inspect.isawaitable(maybe_scalars) else maybe_scalars
                row = None
                if scalars is not None and hasattr(scalars, "first"):
                    maybe_row = scalars.first()
                    row = await maybe_row if inspect.isawaitable(maybe_row) else maybe_row
                if inspect.isawaitable(row):
                    row = await row
            except sa_exc.SQLAlchemyError:
                row = None
            if isinstance(row, FCTBudgetControl):
                return {
                    "enforce_check": self._flag_to_bool(row.enforce_check),
                    "auto_occupy": self._flag_to_bool(row.auto_occupy),
                }
        return {"enforce_check": False, "auto_occupy": False}

    @staticmethod
    def _shift_month(dt: date, months: int) -> date:
        total = (dt.year * 12 + (dt.month - 1)) + months
        year = total // 12
        month = total % 12 + 1
        day = min(dt.day, monthrange(year, month)[1])
        return date(year, month, day)

    @staticmethod
    def _shift_year(dt: date, years: int) -> date:
        target_year = dt.year + years
        day = min(dt.day, monthrange(target_year, dt.month)[1])
        return date(target_year, dt.month, day)

    @staticmethod
    def _period_key(dt: date) -> str:
        return dt.strftime("%Y-%m")

    @staticmethod
    async def _resolve_maybe_await(value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    async def _is_period_explicitly_closed(
        self,
        session: AsyncSession,
        tenant_id: str,
        period_key: str,
    ) -> bool:
        # 先读进程内覆盖（当前进程 close/reopen 后立即生效）
        mem = self._period_status_overrides.get((tenant_id, period_key))
        if mem is not None:
            return mem == "closed"
        # 再读数据库持久化状态（跨进程/重启生效）
        try:
            execute_result = await session.execute(
                text("""
                    SELECT status
                    FROM fct_periods
                    WHERE tenant_id = :sid AND period_key = :pkey
                    LIMIT 1
                """),
                {"sid": tenant_id, "pkey": period_key},
            )
            row = await self._resolve_maybe_await(execute_result.fetchone())
        except sa_exc.SQLAlchemyError:
            return False
        if not row:
            return False
        status = row[0] if isinstance(row, (tuple, list)) else getattr(row, "status", None)
        return str(status or "").strip().lower() == "closed"

    async def _ensure_period_open_for_voucher(
        self,
        session: AsyncSession,
        tenant_id: str,
        effective_date: date,
    ) -> None:
        period_key = self._period_key(effective_date)
        if await self._is_period_explicitly_closed(session, tenant_id, period_key):
            raise ValueError(f"会计期间 {period_key} 已结账，禁止新增或过账凭证")

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

    async def get_voucher_by_id(self, session: AsyncSession, voucher_id: str) -> Optional[Any]:
        stmt = select(Voucher).options(selectinload(Voucher.lines)).where(Voucher.id == voucher_id)
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
        debit_total = sum(float(l.get("debit") or 0) for l in lines)
        credit_total = sum(float(l.get("credit") or 0) for l in lines)
        if abs(debit_total - credit_total) > 0.01:
            raise ValueError(f"借贷不平衡：借方 {debit_total} ≠ 贷方 {credit_total}")
        effective_date = biz_date or date.today()
        await self._ensure_period_open_for_voucher(session, tenant_id, effective_date)
        period = effective_date.strftime("%Y%m")
        policy = {"enforce_check": False, "auto_occupy": False}
        if budget_check is None or budget_occupy is None:
            policy = await self._resolve_budget_policy(
                session=session,
                tenant_id=tenant_id,
                entity_id=entity_id,
                budget_type="period",
                category="voucher",
            )
        use_budget_check = policy["enforce_check"] if budget_check is None else bool(budget_check)
        use_budget_occupy = policy["auto_occupy"] if budget_occupy is None else bool(budget_occupy)
        voucher_amount = float(debit_total)
        if use_budget_check:
            check = await self.check_budget(
                session=session,
                tenant_id=tenant_id,
                entity_id=entity_id,
                budget_type="period",
                period=period,
                category="voucher",
                amount_to_use=voucher_amount,
            )
            if not check.get("within_budget", True):
                raise ValueError("预算不足，凭证创建被拦截")
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
            session.add(
                VoucherLine(
                    id=uuid4(),
                    voucher_id=voucher.id,
                    line_no=i,
                    account_code=line_data.get("account_code", ""),
                    account_name=line_data.get("account_name"),
                    debit=line_data.get("debit"),
                    credit=line_data.get("credit"),
                    summary=line_data.get("summary"),
                )
            )
        await session.flush()
        await session.refresh(voucher)
        if use_budget_occupy:
            occupy = await self.occupy_budget(
                session=session,
                tenant_id=tenant_id,
                entity_id=entity_id,
                budget_type="period",
                period=period,
                category="voucher",
                amount=voucher_amount,
                ref_id=voucher.voucher_no,
            )
            if not occupy.get("success", False):
                raise ValueError("预算占用失败，凭证创建被拦截")
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

        voucher_amount = 0.0
        period = (voucher.biz_date or date.today()).strftime("%Y%m")
        if status == "posted" and current != "posted":
            await self._ensure_period_open_for_voucher(session, voucher.store_id, voucher.biz_date or date.today())
            policy = {"enforce_check": False, "auto_occupy": False}
            if budget_check is None or budget_occupy is None:
                policy = await self._resolve_budget_policy(
                    session=session,
                    tenant_id=voucher.store_id,
                    entity_id=voucher.store_id,
                    budget_type="period",
                    category="voucher",
                )
            use_budget_check = policy["enforce_check"] if budget_check is None else bool(budget_check)
            use_budget_occupy = policy["auto_occupy"] if budget_occupy is None else bool(budget_occupy)
            amount_stmt = select(func.sum(func.coalesce(VoucherLine.debit, 0))).where(VoucherLine.voucher_id == voucher.id)
            voucher_amount = float((await session.execute(amount_stmt)).scalar() or 0)
            if use_budget_check and voucher_amount > 0:
                check = await self.check_budget(
                    session=session,
                    tenant_id=voucher.store_id,
                    entity_id=voucher.store_id,
                    budget_type="period",
                    period=period,
                    category="voucher",
                    amount_to_use=voucher_amount,
                )
                if not check.get("within_budget", True):
                    raise ValueError("预算不足，凭证过账被拦截")

        voucher.status = status
        await session.flush()
        await session.refresh(voucher)

        if status == "posted" and current != "posted":
            policy = {"enforce_check": False, "auto_occupy": False}
            if budget_check is None or budget_occupy is None:
                policy = await self._resolve_budget_policy(
                    session=session,
                    tenant_id=voucher.store_id,
                    entity_id=voucher.store_id,
                    budget_type="period",
                    category="voucher",
                )
            use_budget_occupy = policy["auto_occupy"] if budget_occupy is None else bool(budget_occupy)
            if use_budget_occupy and voucher_amount > 0:
                occupy = await self.occupy_budget(
                    session=session,
                    tenant_id=voucher.store_id,
                    entity_id=voucher.store_id,
                    budget_type="period",
                    period=period,
                    category="voucher",
                    amount=voucher_amount,
                    ref_id=voucher.voucher_no,
                )
                if not occupy.get("success", False):
                    raise ValueError("预算占用失败，凭证过账被拦截")

        return {
            "voucher_id": str(voucher.id),
            "voucher_no": voucher.voucher_no,
            "from_status": current,
            "status": status,
            "success": True,
        }

    async def void_voucher(self, session: AsyncSession, voucher_id: str) -> Dict[str, Any]:
        stmt = select(Voucher).where(Voucher.id == voucher_id)
        voucher = (await session.execute(stmt)).scalar_one_or_none()
        if not voucher:
            raise ValueError("凭证不存在")

        current = (voucher.status or "").lower()
        if current == "posted":
            raise ValueError("已过账凭证不允许直接作废，请使用红冲")
        if current == "reversed":
            raise ValueError("已红冲凭证不允许作废")

        voucher.status = "voided"
        await session.flush()
        await session.refresh(voucher)
        return {
            "voucher_id": str(voucher.id),
            "voucher_no": voucher.voucher_no,
            "from_status": current,
            "status": "voided",
            "success": True,
        }

    async def red_flush_voucher(
        self,
        session: AsyncSession,
        voucher_id: str,
        biz_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        stmt = select(Voucher).where(Voucher.id == voucher_id).options(selectinload(Voucher.lines))
        original = (await session.execute(stmt)).scalar_one_or_none()
        if not original:
            raise ValueError("原凭证不存在")

        original_status = (original.status or "").lower()
        if original_status != "posted":
            raise ValueError("仅已过账凭证支持红冲")

        red_biz_date = biz_date or date.today()
        await self._ensure_period_open_for_voucher(session, original.store_id, red_biz_date)

        red_no = f"RF-{red_biz_date.strftime('%Y%m%d')}-{str(uuid4())[:8].upper()}"
        red_voucher = Voucher(
            voucher_no=red_no,
            store_id=original.store_id,
            event_type="red_flush",
            event_id=str(original.id),
            biz_date=red_biz_date,
            status="posted",
            description=f"红冲凭证，冲销原凭证 {original.voucher_no}",
        )
        session.add(red_voucher)
        await session.flush()

        for idx, line in enumerate(original.lines or [], start=1):
            red_line = VoucherLine(
                voucher_id=red_voucher.id,
                line_no=idx,
                account_code=line.account_code,
                account_name=line.account_name,
                debit=line.credit,
                credit=line.debit,
                auxiliary=line.auxiliary,
                summary=f"红冲：{line.summary or ''}".strip(),
            )
            session.add(red_line)

        original.status = "reversed"
        await session.flush()
        await session.refresh(original)

        return {
            "original_voucher_id": str(original.id),
            "original_voucher_no": original.voucher_no,
            "red_voucher_id": str(red_voucher.id),
            "red_voucher_no": red_no,
            "biz_date": red_biz_date.isoformat(),
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
        tx_stmt = text("""
            SELECT DISTINCT DATE_TRUNC('month', transaction_date) AS month
            FROM financial_transactions
            WHERE store_id = :sid
            ORDER BY 1 DESC
        """)
        tx_result = await session.execute(tx_stmt, {"sid": tenant_id})
        rows = await self._resolve_maybe_await(tx_result.fetchall())

        # 交易月份
        tx_keys: List[str] = []
        for row in rows:
            period_dt = row[0]
            period_key = period_dt.strftime("%Y-%m") if hasattr(period_dt, "strftime") else str(period_dt)[:7]
            tx_keys.append(period_key)

        # 持久化月份状态（fct_periods）
        persisted_stmt = text("""
            SELECT period_key, status
            FROM fct_periods
            WHERE tenant_id = :sid
        """)
        try:
            persisted_result = await session.execute(persisted_stmt, {"sid": tenant_id})
            persisted_rows = await self._resolve_maybe_await(persisted_result.fetchall())
        except sa_exc.SQLAlchemyError:
            persisted_rows = []
        persisted_status: Dict[str, str] = {}
        for row in persisted_rows:
            pkey = ""
            status = ""
            try:
                if isinstance(row, (tuple, list)):
                    if len(row) >= 1:
                        pkey = row[0]
                    if len(row) >= 2:
                        status = row[1]
                else:
                    pkey = getattr(row, "period_key", "")
                    status = getattr(row, "status", "")
            except (ValueError, TypeError, AttributeError):
                continue
            pkey_str = str(pkey or "").strip()
            status_str = str(status or "").strip().lower()
            if not self.PERIOD_KEY_RE.match(pkey_str):
                continue
            if status_str not in self.PERIOD_STATUS_VALUES:
                continue
            persisted_status[pkey_str] = status_str

        all_keys = sorted(set(tx_keys) | set(persisted_status.keys()), reverse=True)
        if start_key:
            all_keys = [k for k in all_keys if k >= start_key]
        if end_key:
            all_keys = [k for k in all_keys if k <= end_key]
        if not all_keys:
            return {"items": [], "total": 0}

        items = []
        for i, period_key in enumerate(all_keys):
            # 默认规则：最新月份 open，其余 closed
            status = "open" if i == 0 else "closed"
            if period_key in persisted_status:
                status = "open" if persisted_status[period_key] == "open" else "closed"
            override = self._period_status_overrides.get((tenant_id, period_key))
            if override:
                status = override
            items.append({"period_key": period_key, "status": status})
        return {"items": items, "total": len(items)}

    async def close_period(self, session: AsyncSession, tenant_id: str, period_key: str) -> Dict[str, Any]:
        if not self.PERIOD_KEY_RE.match(period_key):
            raise ValueError("period_key 格式应为 YYYY-MM")
        periods = await self.list_periods(session, tenant_id=tenant_id)
        target = next((p for p in periods["items"] if p["period_key"] == period_key), None)
        if not target:
            raise ValueError("period_key 不存在")
        if target["status"] == "closed":
            raise ValueError("该期间已结账")

        y, m = int(period_key[:4]), int(period_key[5:7])
        start_date = date(y, m, 1)
        end_date = date(y, m, monthrange(y, m)[1])
        now = datetime.utcnow()
        await session.execute(
            text("""
                INSERT INTO fct_periods
                (id, tenant_id, period_key, start_date, end_date, status, closed_at, extra, created_at, updated_at)
                VALUES
                (:id, :sid, :pkey, :start_date, :end_date, 'closed', :closed_at, :extra, :created_at, :updated_at)
                ON CONFLICT (tenant_id, period_key)
                DO UPDATE SET
                    status = 'closed',
                    closed_at = EXCLUDED.closed_at,
                    updated_at = EXCLUDED.updated_at
            """),
            {
                "id": str(uuid4()),
                "sid": tenant_id,
                "pkey": period_key,
                "start_date": start_date,
                "end_date": end_date,
                "closed_at": now.isoformat(),
                "extra": None,
                "created_at": now,
                "updated_at": now,
            },
        )
        self._period_status_overrides[(tenant_id, period_key)] = "closed"
        return {"tenant_id": tenant_id, "period_key": period_key, "status": "closed"}

    async def reopen_period(self, session: AsyncSession, tenant_id: str, period_key: str) -> Dict[str, Any]:
        if not self.PERIOD_KEY_RE.match(period_key):
            raise ValueError("period_key 格式应为 YYYY-MM")
        periods = await self.list_periods(session, tenant_id=tenant_id)
        keys = [p["period_key"] for p in periods["items"]]
        if period_key not in keys:
            raise ValueError("period_key 不存在")
        target = next((p for p in periods["items"] if p["period_key"] == period_key), None)
        if target and target["status"] == "open":
            raise ValueError("该期间已是打开状态")

        now = datetime.utcnow()
        for key in keys:
            y, m = int(key[:4]), int(key[5:7])
            start_date = date(y, m, 1)
            end_date = date(y, m, monthrange(y, m)[1])
            status = "open" if key == period_key else "closed"
            closed_at = None if status == "open" else now.isoformat()
            await session.execute(
                text("""
                    INSERT INTO fct_periods
                    (id, tenant_id, period_key, start_date, end_date, status, closed_at, extra, created_at, updated_at)
                    VALUES
                    (:id, :sid, :pkey, :start_date, :end_date, :status, :closed_at, :extra, :created_at, :updated_at)
                    ON CONFLICT (tenant_id, period_key)
                    DO UPDATE SET
                        status = EXCLUDED.status,
                        closed_at = EXCLUDED.closed_at,
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    "id": str(uuid4()),
                    "sid": tenant_id,
                    "pkey": key,
                    "start_date": start_date,
                    "end_date": end_date,
                    "status": status,
                    "closed_at": closed_at,
                    "extra": None,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            self._period_status_overrides[(tenant_id, key)] = "open" if key == period_key else "closed"
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
        target_entity = entity_id or tenant_id
        effective_as_of = as_of_date
        if period and len(period) == 6 and period.isdigit():
            p_year, p_month = int(period[:4]), int(period[4:6])
            effective_as_of = date(p_year, p_month, monthrange(p_year, p_month)[1])

        filters = [Voucher.store_id == target_entity]
        if effective_as_of:
            filters.append(Voucher.biz_date <= effective_as_of)
        if posted_only:
            filters.append(Voucher.status == "posted")

        stmt = (
            select(
                VoucherLine.account_code,
                func.max(VoucherLine.account_name),
                func.sum(func.coalesce(VoucherLine.debit, 0)),
                func.sum(func.coalesce(VoucherLine.credit, 0)),
            )
            .select_from(VoucherLine)
            .join(Voucher, Voucher.id == VoucherLine.voucher_id)
            .where(and_(*filters))
            .group_by(VoucherLine.account_code)
            .order_by(VoucherLine.account_code)
        )
        rows = (await session.execute(stmt)).fetchall()
        balances: List[Dict[str, Any]] = []
        for row in rows:
            debit_total = float(row[2] or 0)
            credit_total = float(row[3] or 0)
            balances.append(
                {
                    "account_code": row[0],
                    "account_name": row[1],
                    "debit_total": debit_total,
                    "credit_total": credit_total,
                    "balance": round(debit_total - credit_total, 2),
                }
            )

        return {
            "tenant_id": tenant_id,
            "entity_id": target_entity,
            "as_of": (effective_as_of or date.today()).isoformat(),
            "period": period,
            "posted_only": posted_only,
            "balances": balances,
        }

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
        target_entity = entity_id or tenant_id
        effective_start = start_date
        effective_end = end_date
        if period and len(period) == 6 and period.isdigit():
            p_year, p_month = int(period[:4]), int(period[4:6])
            effective_start = date(p_year, p_month, 1)
            effective_end = date(p_year, p_month, monthrange(p_year, p_month)[1])

        filters = [Voucher.store_id == target_entity]
        if effective_start:
            filters.append(Voucher.biz_date >= effective_start)
        if effective_end:
            filters.append(Voucher.biz_date <= effective_end)
        if posted_only:
            filters.append(Voucher.status == "posted")
        if account_code:
            filters.append(VoucherLine.account_code == account_code)

        count_stmt = (
            select(func.count(VoucherLine.id))
            .select_from(VoucherLine)
            .join(Voucher, Voucher.id == VoucherLine.voucher_id)
            .where(and_(*filters))
        )
        total = int((await session.execute(count_stmt)).scalar() or 0)

        stmt = (
            select(Voucher, VoucherLine)
            .select_from(VoucherLine)
            .join(Voucher, Voucher.id == VoucherLine.voucher_id)
            .where(and_(*filters))
            .order_by(Voucher.biz_date.desc(), Voucher.voucher_no.desc(), VoucherLine.line_no.asc())
            .offset(skip)
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()
        items: List[Dict[str, Any]] = []
        for voucher, line in rows:
            debit = float(line.debit) if line.debit is not None else 0.0
            credit = float(line.credit) if line.credit is not None else 0.0
            items.append(
                {
                    "voucher_id": str(voucher.id),
                    "voucher_no": voucher.voucher_no,
                    "biz_date": voucher.biz_date.isoformat() if voucher.biz_date else None,
                    "voucher_status": voucher.status,
                    "line_no": line.line_no,
                    "account_code": line.account_code,
                    "account_name": line.account_name,
                    "debit": debit,
                    "credit": credit,
                    "summary": line.summary,
                }
            )
        return {"items": items, "total": total, "skip": skip, "limit": limit}

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
            stmt = select(FinancialTransaction).where(and_(*filters) if filters else True).offset(skip).limit(limit)
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
        except sa_exc.SQLAlchemyError:
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
        effective_date = tx_date or date.today()
        period = effective_date.strftime("%Y%m")
        policy = {"enforce_check": False, "auto_occupy": False}
        if budget_check is None or budget_occupy is None:
            policy = await self._resolve_budget_policy(
                session=session,
                tenant_id=tenant_id,
                entity_id=entity_id,
                budget_type="period",
                category="cash",
            )
        use_budget_check = policy["enforce_check"] if budget_check is None else bool(budget_check)
        use_budget_occupy = policy["auto_occupy"] if budget_occupy is None else bool(budget_occupy)
        is_expense = direction != "in"
        if is_expense and use_budget_check:
            check = await self.check_budget(
                session=session,
                tenant_id=tenant_id,
                entity_id=entity_id,
                budget_type="period",
                period=period,
                category="cash",
                amount_to_use=float(amount),
            )
            if not check.get("within_budget", True):
                raise ValueError("预算不足，资金交易创建被拦截")

        txn = FinancialTransaction(
            store_id=entity_id,
            transaction_date=effective_date,
            transaction_type="income" if direction == "in" else "expense",
            category="cash",
            amount=int(amount),
            reference_id=ref_id,
        )
        session.add(txn)
        await session.flush()
        if is_expense and use_budget_occupy:
            occupy = await self.occupy_budget(
                session=session,
                tenant_id=tenant_id,
                entity_id=entity_id,
                budget_type="period",
                period=period,
                category="cash",
                amount=float(amount),
                ref_id=ref_id or str(txn.id),
            )
            if not occupy.get("success", False):
                raise ValueError("预算占用失败，资金交易创建被拦截")
        return {
            "id": str(txn.id),
            "entity_id": entity_id,
            "tx_date": effective_date.isoformat(),
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
            except (ValueError, TypeError, KeyError):
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
        target_entity = entity_id or tenant_id
        filters = [Invoice.store_id == target_entity]
        if invoice_type:
            filters.append(Invoice.invoice_type == invoice_type)
        if start_date:
            filters.append(Invoice.invoice_date >= start_date)
        if end_date:
            filters.append(Invoice.invoice_date <= end_date)

        total_stmt = select(func.count(Invoice.id)).where(and_(*filters))
        total = int((await session.execute(total_stmt)).scalar() or 0)
        stmt = (
            select(Invoice)
            .where(and_(*filters))
            .order_by(Invoice.invoice_date.desc(), Invoice.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        rows = (await session.execute(stmt)).scalars().all()
        items: List[Dict[str, Any]] = []
        for r in rows:
            items.append(
                {
                    "id": str(r.id),
                    "entity_id": r.store_id,
                    "invoice_type": r.invoice_type,
                    "invoice_no": r.invoice_number,
                    "amount": int(r.total_amount or 0),
                    "tax_amount": int(r.tax_amount or 0),
                    "net_amount": int(r.net_amount or 0),
                    "invoice_date": r.invoice_date.isoformat() if r.invoice_date else None,
                    "status": r.status,
                }
            )
        return {"items": items, "total": total, "skip": skip, "limit": limit}

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
        inv_date = invoice_date or date.today()
        total_amt = int(amount or 0)
        tax_amt = int(tax_amount or 0)
        if not invoice_no:
            invoice_no = f"INV-{inv_date.strftime('%Y%m%d')}-{str(uuid4())[:8].upper()}"
        row = Invoice(
            store_id=entity_id,
            invoice_type=invoice_type,
            invoice_number=invoice_no,
            invoice_date=inv_date,
            total_amount=total_amt,
            tax_amount=tax_amt,
            net_amount=max(0, total_amt - tax_amt),
            status=status,
            items=extra or {},
        )
        session.add(row)
        await session.flush()
        return {
            "id": str(row.id),
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "invoice_type": invoice_type,
            "invoice_no": invoice_no,
            "amount": total_amt,
            "tax_amount": tax_amt,
            "invoice_date": inv_date.isoformat(),
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
        stmt = select(Invoice).where(Invoice.id == invoice_id)
        row = (await session.execute(stmt)).scalar_one_or_none()
        if not row:
            raise ValueError("发票不存在")

        if invoice_no is not None:
            row.invoice_number = invoice_no
        if amount is not None:
            row.total_amount = int(amount)
        if tax_amount is not None:
            row.tax_amount = int(tax_amount)
        if amount is not None or tax_amount is not None:
            row.net_amount = max(0, int(row.total_amount or 0) - int(row.tax_amount or 0))
        if invoice_date is not None:
            row.invoice_date = invoice_date
        if status is not None:
            row.status = status
        if extra is not None:
            row.items = extra

        await session.flush()
        return {
            "invoice_id": str(row.id),
            "invoice_no": row.invoice_number,
            "status": row.status,
            "success": True,
        }

    async def link_invoice_to_voucher(
        self,
        session: AsyncSession,
        invoice_id: str,
        voucher_id: str,
        line_no: Optional[int] = None,
    ) -> Dict[str, Any]:
        stmt = select(Invoice).where(Invoice.id == invoice_id)
        row = (await session.execute(stmt)).scalar_one_or_none()
        if not row:
            raise ValueError("发票不存在")

        payload: Dict[str, Any] = {}
        if isinstance(row.items, dict):
            payload = dict(row.items)
        elif isinstance(row.items, list):
            payload = {"lines": row.items}

        links = payload.get("linked_vouchers")
        if not isinstance(links, list):
            links = []
        exists = any(str(i.get("voucher_id")) == str(voucher_id) for i in links if isinstance(i, dict))
        if not exists:
            links.append({"voucher_id": str(voucher_id), "line_no": line_no})
        payload["linked_vouchers"] = links
        row.items = payload
        await session.flush()
        return {"invoice_id": invoice_id, "voucher_id": voucher_id, "success": True}

    async def list_invoices_by_voucher(self, session: AsyncSession, voucher_id: str) -> Dict[str, Any]:
        stmt = select(Invoice).order_by(Invoice.invoice_date.desc(), Invoice.created_at.desc())
        rows = (await session.execute(stmt)).scalars().all()
        invoices: List[Dict[str, Any]] = []
        for r in rows:
            links = []
            if isinstance(r.items, dict) and isinstance(r.items.get("linked_vouchers"), list):
                links = r.items.get("linked_vouchers") or []
            if any(str(i.get("voucher_id")) == str(voucher_id) for i in links if isinstance(i, dict)):
                invoices.append(
                    {
                        "invoice_id": str(r.id),
                        "invoice_no": r.invoice_number,
                        "invoice_type": r.invoice_type,
                        "amount": int(r.total_amount or 0),
                        "tax_amount": int(r.tax_amount or 0),
                        "status": r.status,
                    }
                )
        return {"voucher_id": voucher_id, "invoices": invoices}

    async def verify_invoice(self, session: AsyncSession, invoice_id: str) -> Dict[str, Any]:
        """
        发票验真：数据库查询 + 本地格式校验 + 外部税局 API 接入（可选）。

        验真流程：
          1. 从数据库查询发票记录，获取真实发票号码和类型
          2. 按中国发票标准校验格式（发票代码10/12位 + 发票号码8位）
          3. 若配置 TAX_VERIFY_API_KEY，调用外部查验接口
          4. 返回完整验真结果
        """
        import httpx

        # 1. 查询数据库
        stmt = select(Invoice).where(Invoice.id == invoice_id)
        row = (await session.execute(stmt)).scalar_one_or_none()
        if not row:
            return {
                "invoice_id": invoice_id,
                "verify_status": "not_found",
                "format_valid": False,
                "message": "发票记录不存在，请确认发票ID",
                "verified_at": datetime.utcnow().isoformat(),
            }

        invoice_no: str = row.invoice_number or ""
        invoice_type: str = row.invoice_type or ""

        # 2. 本地格式校验（中国增值税发票规范）
        # 发票号码：8位纯数字
        # 发票代码：10位（增值税普通发票）或 12位（增值税专用发票/电子发票）
        invoice_no_valid = bool(re.match(r"^\d{8}$", invoice_no))
        # 税号（纳税人识别号）：15/17/18/20位
        tax_no: str = row.tax_number or ""
        tax_no_valid = not tax_no or bool(re.match(r"^\d{15,20}$", tax_no))
        format_valid = invoice_no_valid and tax_no_valid

        # 3. 外部税局 API 验真（有 Key 时调用）
        verify_api_key = os.getenv("TAX_VERIFY_API_KEY") or os.getenv("INVOICE_VERIFY_KEY")
        api_result: Optional[Dict[str, Any]] = None
        if verify_api_key and format_valid:
            verify_url = os.getenv(
                "TAX_VERIFY_URL",
                "https://inv-veri.chinatax.gov.cn/api/v1/verify",
            )
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        verify_url,
                        json={
                            "invoiceNo": invoice_no,
                            "invoiceType": invoice_type,
                            "taxNo": tax_no,
                            "amount": str(row.total_amount or 0),
                        },
                        headers={"X-Api-Key": verify_api_key},
                    )
                    if resp.status_code == 200:
                        api_result = resp.json()
                        verify_status = "verified" if api_result.get("valid") else "rejected"
                    else:
                        verify_status = "api_error"
                        logger.warning(
                            "发票验真 API 响应异常",
                            invoice_id=invoice_id,
                            status_code=resp.status_code,
                        )
            except httpx.TimeoutException:
                verify_status = "api_timeout"
                logger.warning("发票验真 API 超时", invoice_id=invoice_id)
            except (httpx.HTTPError, ConnectionError, ValueError) as exc:
                verify_status = "api_error"
                logger.error("发票验真 API 调用失败", invoice_id=invoice_id, error=str(exc))
        elif not format_valid:
            verify_status = "format_invalid"
        else:
            verify_status = "local_only"  # 格式校验通过，但未配置外部 API

        return {
            "invoice_id": invoice_id,
            "invoice_no": invoice_no,
            "invoice_type": invoice_type,
            "amount": int(row.total_amount or 0),
            "amount_yuan": self._y(int(row.total_amount or 0)),
            "tax_amount": int(row.tax_amount or 0),
            "tax_amount_yuan": self._y(int(row.tax_amount or 0)),
            "status": row.status,
            "verify_status": verify_status,
            "format_valid": format_valid,
            "invoice_no_valid": invoice_no_valid,
            "tax_no_valid": tax_no_valid,
            "api_result": api_result,
            "message": {
                "verified": "发票验真通过",
                "rejected": "发票验真不通过，请核实发票信息",
                "local_only": "本地格式校验通过，外部税局验真需配置 TAX_VERIFY_API_KEY",
                "format_invalid": f"发票格式校验失败：号码{'有效' if invoice_no_valid else '无效'}，税号{'有效' if tax_no_valid else '无效'}",
                "api_timeout": "税局验真接口超时，请稍后重试",
                "api_error": "税局验真接口异常，请稍后重试",
                "not_found": "发票记录不存在",
            }.get(verify_status, verify_status),
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
        target_entity = entity_id or tenant_id
        filters = [FCTTaxRecord.store_id == target_entity]

        if period and len(period) == 6 and period.isdigit():
            filters.append(FCTTaxRecord.year == int(period[:4]))
            filters.append(FCTTaxRecord.month == int(period[4:6]))

        stmt = (
            select(FCTTaxRecord)
            .where(and_(*filters))
            .order_by(FCTTaxRecord.year.desc(), FCTTaxRecord.month.desc(), FCTTaxRecord.id.desc())
        )
        rows = (await session.execute(stmt)).scalars().all()
        wanted = (tax_type or "total").lower()
        allowed_types = {"vat", "cit", "surcharge", "total", "all"}
        if wanted not in allowed_types:
            wanted = "total"

        expanded: List[Dict[str, Any]] = []
        for r in rows:
            period_key = f"{int(r.year):04d}{int(r.month):02d}"
            taxpayer = r.taxpayer_type.value if hasattr(r.taxpayer_type, "value") else str(r.taxpayer_type)
            per_type_rows = [
                ("vat", int(r.net_vat or r.vat_amount or 0)),
                ("cit", int(r.cit_amount or 0)),
                ("surcharge", int(r.vat_surcharge or 0)),
                ("total", int(r.total_tax or 0)),
            ]
            for t, amount in per_type_rows:
                if wanted != "all" and t != wanted:
                    continue
                expanded.append(
                    {
                        "id": str(r.id),
                        "entity_id": r.store_id,
                        "period": period_key,
                        "tax_type": t,
                        "taxpayer_type": taxpayer,
                        "amount": amount,
                        "amount_yuan": self._y(amount),
                        "is_finalized": bool(r.is_finalized),
                        "generated_by": r.generated_by,
                    }
                )

        total = len(expanded)
        items = expanded[skip : skip + limit]
        return {"items": items, "total": total, "skip": skip, "limit": limit}

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

            income_stmt = select(func.sum(FinancialTransaction.amount)).where(
                and_(*filters, FinancialTransaction.transaction_type == "income")
            )
            cost_stmt = select(func.sum(FinancialTransaction.amount)).where(
                and_(
                    *filters, FinancialTransaction.transaction_type == "expense", FinancialTransaction.category == "food_cost"
                )
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
        except (sa_exc.SQLAlchemyError, KeyError, TypeError) as e:
            raise ValueError(str(e)) from e

    # ── 预算管理 ──────────────────────────────────────────────────────────────

    async def upsert_budget(self, session: AsyncSession, **kwargs) -> Dict[str, Any]:
        tenant_id = kwargs.get("tenant_id")
        entity_id = kwargs.get("entity_id") or ""
        period = str(kwargs.get("period") or "")
        category = str(kwargs.get("category") or "")
        amount = int(float(kwargs.get("amount") or 0))
        if len(period) != 6 or (not period.isdigit()):
            raise ValueError("period 格式应为 YYYYMM")
        year, month = int(period[:4]), int(period[4:6])
        store_id = entity_id or tenant_id

        stmt = select(Budget).where(
            and_(
                Budget.store_id == store_id,
                Budget.year == year,
                Budget.month == month,
                Budget.category == category,
            )
        )
        existing = (await session.execute(stmt)).scalars().first()
        if existing:
            existing.budgeted_amount = amount
            budget_id = str(existing.id)
        else:
            row = Budget(
                store_id=store_id,
                year=year,
                month=month,
                category=category,
                budgeted_amount=amount,
            )
            session.add(row)
            budget_id = str(row.id) if getattr(row, "id", None) else ""
        await session.flush()
        return {
            "success": True,
            **kwargs,
            "budget_id": budget_id,
            "year": year,
            "month": month,
        }

    async def upsert_budget_control(self, session: AsyncSession, **kwargs) -> Dict[str, Any]:
        tenant_id = str(kwargs.get("tenant_id") or "")
        entity_id = str(kwargs.get("entity_id") or "")
        budget_type = str(kwargs.get("budget_type") or "period")
        category = str(kwargs.get("category") or "")
        enforce_flag = self._as_flag(kwargs.get("enforce_check", False))
        auto_flag = self._as_flag(kwargs.get("auto_occupy", False))
        extra = kwargs.get("extra")

        stmt = select(FCTBudgetControl).where(
            and_(
                FCTBudgetControl.tenant_id == tenant_id,
                FCTBudgetControl.entity_id == entity_id,
                FCTBudgetControl.budget_type == budget_type,
                FCTBudgetControl.category == category,
            )
        )
        existing = (await session.execute(stmt)).scalars().first()
        if existing:
            existing.enforce_check = enforce_flag
            existing.auto_occupy = auto_flag
            existing.extra = extra
            control_id = str(existing.id)
        else:
            row = FCTBudgetControl(
                tenant_id=tenant_id,
                entity_id=entity_id,
                budget_type=budget_type,
                category=category,
                enforce_check=enforce_flag,
                auto_occupy=auto_flag,
                extra=extra,
            )
            session.add(row)
            control_id = str(row.id) if getattr(row, "id", None) else ""
        await session.flush()

        return {
            "success": True,
            "id": control_id,
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "budget_type": budget_type,
            "category": category,
            "enforce_check": self._flag_to_bool(enforce_flag),
            "auto_occupy": self._flag_to_bool(auto_flag),
            "extra": extra,
        }

    async def list_budget_controls(
        self,
        session: AsyncSession,
        tenant_id: str,
        entity_id: Optional[str] = None,
        budget_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        filters = [FCTBudgetControl.tenant_id == tenant_id]
        if entity_id is not None:
            filters.append(FCTBudgetControl.entity_id == entity_id)
        if budget_type:
            filters.append(FCTBudgetControl.budget_type == budget_type)

        total_stmt = select(func.count(FCTBudgetControl.id)).where(and_(*filters))
        total = int((await session.execute(total_stmt)).scalar() or 0)

        list_stmt = (
            select(FCTBudgetControl)
            .where(and_(*filters))
            .order_by(FCTBudgetControl.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        rows = (await session.execute(list_stmt)).scalars().all()
        items = [
            {
                "id": str(r.id),
                "tenant_id": r.tenant_id,
                "entity_id": r.entity_id,
                "budget_type": r.budget_type,
                "category": r.category,
                "enforce_check": self._flag_to_bool(r.enforce_check),
                "auto_occupy": self._flag_to_bool(r.auto_occupy),
                "extra": r.extra,
            }
            for r in rows
        ]
        return {
            "items": items,
            "total": total,
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
        target_entity = entity_id or tenant_id
        target_category = category or normalized_account
        y, m = date.today().year, date.today().month
        if period and len(period) == 6 and period.isdigit():
            y, m = int(period[:4]), int(period[4:6])
        month_start = date(y, m, 1)
        month_end = date(y, m, monthrange(y, m)[1])

        budget_stmt = select(func.sum(Budget.budgeted_amount)).where(
            and_(
                Budget.store_id == target_entity,
                Budget.year == y,
                Budget.month == m,
                Budget.category == target_category,
            )
        )
        actual_stmt = select(func.sum(FinancialTransaction.amount)).where(
            and_(
                FinancialTransaction.store_id == target_entity,
                FinancialTransaction.transaction_type == "expense",
                FinancialTransaction.category == target_category,
                FinancialTransaction.transaction_date >= month_start,
                FinancialTransaction.transaction_date <= month_end,
            )
        )
        planned = float((await session.execute(budget_stmt)).scalar() or 0)
        actual = float((await session.execute(actual_stmt)).scalar() or 0)
        available = planned - actual
        return {
            "tenant_id": tenant_id,
            "entity_id": target_entity,
            "budget_type": budget_type or "period",
            "account_code": normalized_account,
            "category": target_category,
            "requested": requested_amount,
            "planned": planned,
            "actual": actual,
            "available": available,
            "within_budget": requested_amount <= available,
            "period": f"{y:04d}{m:02d}",
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
        target_category = category or normalized_account
        check = await self.check_budget(
            session,
            tenant_id=tenant_id,
            entity_id=entity_id,
            account_code=account_code,
            amount=amount,
            budget_type=budget_type,
            category=target_category,
            period=period,
        )
        if not check["within_budget"]:
            return {
                "success": False,
                "tenant_id": tenant_id,
                "entity_id": entity_id or tenant_id,
                "budget_type": budget_type or "period",
                "account_code": normalized_account,
                "category": target_category,
                "period": check.get("period") or period,
                "occupied": float(amount),
                "ref_id": ref_id,
                "reason": "budget_exceeded",
                "available": check.get("available"),
            }

        txn_date = date.today()
        if check.get("period") and len(str(check["period"])) == 6 and str(check["period"]).isdigit():
            py, pm = int(str(check["period"])[:4]), int(str(check["period"])[4:6])
            txn_date = date(py, pm, 1)
        row = FinancialTransaction(
            store_id=entity_id or tenant_id,
            transaction_date=txn_date,
            transaction_type="expense",
            category=target_category,
            amount=int(float(amount)),
            description=f"budget occupy {ref_id or ''}".strip(),
            reference_id=ref_id,
            created_by="budget_control",
        )
        session.add(row)
        await session.flush()
        return {
            "success": True,
            "tenant_id": tenant_id,
            "entity_id": entity_id or tenant_id,
            "budget_type": budget_type or "period",
            "account_code": normalized_account,
            "category": target_category,
            "period": check.get("period") or period,
            "occupied": float(amount),
            "ref_id": ref_id,
            "available_after": float(check.get("available") or 0) - float(amount or 0),
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
        store_id = entity_id or tenant_id
        normalized_targets = {str(category): int(float(amount)) for category, amount in (targets or {}).items()}
        if normalized_targets:
            stmt = select(Budget).where(
                and_(
                    Budget.store_id == store_id,
                    Budget.year == plan_year,
                    Budget.month == 0,
                    Budget.category.in_(list(normalized_targets.keys())),
                )
            )
            existing_rows = (await session.execute(stmt)).scalars().all()
            existing_by_category: Dict[str, Budget] = {}
            for row in existing_rows:
                existing_by_category.setdefault(row.category, row)

            for category, amount in normalized_targets.items():
                existing = existing_by_category.get(category)
                if existing:
                    existing.budgeted_amount = amount
                else:
                    session.add(
                        Budget(
                            store_id=store_id,
                            year=plan_year,
                            month=0,
                            category=category,
                            budgeted_amount=amount,
                        )
                    )
            await session.flush()
        return {
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "plan_year": plan_year,
            "targets": normalized_targets,
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
        # 当前仅支持月粒度，其他粒度降级为 month。
        if granularity != "month":
            granularity = "month"

        store_key = entity_id or tenant_id
        filters = "WHERE store_id = :sid"
        params: Dict[str, Any] = {"sid": store_key}
        if start_date:
            filters += " AND transaction_date >= :df"
            params["df"] = start_date
        if end_date:
            filters += " AND transaction_date <= :dt"
            params["dt"] = end_date

        actual_stmt = text(f"""
            SELECT DATE_TRUNC('month', transaction_date) AS period,
                   SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE 0 END) AS income,
                   SUM(CASE WHEN transaction_type = 'expense' THEN amount ELSE 0 END) AS expense
            FROM financial_transactions
            {filters}
            GROUP BY 1
            ORDER BY 1
        """)
        actual_rows = (await session.execute(actual_stmt, params)).fetchall()
        actual_map: Dict[str, int] = {}
        for row in actual_rows:
            period_dt = row[0]
            period_key = period_dt.strftime("%Y-%m")
            income = int(row[1] or 0)
            expense = int(row[2] or 0)
            actual_map[period_key] = income - expense

        budget_stmt = select(Budget).where(
            and_(
                Budget.store_id == store_key,
                Budget.month >= 1,
                Budget.month <= 12,
            )
        )
        budget_rows = (await session.execute(budget_stmt)).scalars().all()

        start_month = date(start_date.year, start_date.month, 1) if start_date else None
        end_month = date(end_date.year, end_date.month, 1) if end_date else None

        budget_map: Dict[str, int] = {}
        for b in budget_rows:
            if not b.year or not b.month:
                continue
            try:
                month_dt = date(int(b.year), int(b.month), 1)
            except ValueError:
                continue
            if start_month and month_dt < start_month:
                continue
            if end_month and month_dt > end_month:
                continue
            period_key = month_dt.strftime("%Y-%m")
            budget_map[period_key] = budget_map.get(period_key, 0) + int(b.budgeted_amount or 0)

        periods = sorted(set(actual_map.keys()) | set(budget_map.keys()))
        items: List[Dict[str, Any]] = []
        for p in periods:
            plan_cents = int(budget_map.get(p, 0))
            actual_cents = int(actual_map.get(p, 0))
            variance_cents = actual_cents - plan_cents
            variance_pct = round((variance_cents / plan_cents) * 100, 2) if plan_cents else None
            items.append(
                {
                    "period": p,
                    "planned_amount": plan_cents,
                    "planned_amount_yuan": self._y(plan_cents),
                    "actual_amount": actual_cents,
                    "actual_amount_yuan": self._y(actual_cents),
                    "variance": variance_cents,
                    "variance_yuan": self._y(variance_cents),
                    "variance_pct": variance_pct,
                }
            )

        planned_total = sum(x["planned_amount"] for x in items)
        actual_total = sum(x["actual_amount"] for x in items)
        total_variance = actual_total - planned_total

        return {
            "report_type": "plan_vs_actual",
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "granularity": granularity,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "items": items,
            "summary": {
                "planned_total": planned_total,
                "planned_total_yuan": self._y(planned_total),
                "actual_total": actual_total,
                "actual_total_yuan": self._y(actual_total),
                "variance_total": total_variance,
                "variance_total_yuan": self._y(total_variance),
                "variance_total_pct": round((total_variance / planned_total) * 100, 2) if planned_total else None,
            },
        }

    # ── 备用金 ────────────────────────────────────────────────────────────────

    async def upsert_petty_cash(
        self,
        session: AsyncSession,
        tenant_id: str,
        petty_cash_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        cash_type: str = "general",
        amount_limit: float = 0,
        currency: str = "CNY",
        owner: Optional[str] = None,
        status: str = "active",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        target_entity = entity_id or tenant_id
        parsed_id = self._parse_uuid_or_none(petty_cash_id)
        row = None
        if parsed_id:
            row = (
                await session.execute(
                    select(FCTPettyCash).where(
                        and_(
                            FCTPettyCash.id == parsed_id,
                            FCTPettyCash.tenant_id == tenant_id,
                        )
                    )
                )
            ).scalar_one_or_none()
        if row is None:
            row = (
                await session.execute(
                    select(FCTPettyCash).where(
                        and_(
                            FCTPettyCash.tenant_id == tenant_id,
                            FCTPettyCash.entity_id == target_entity,
                            FCTPettyCash.cash_type == cash_type,
                        )
                    )
                )
            ).scalar_one_or_none()

        payload = dict(extra or {})
        payload["currency"] = currency
        if owner is not None:
            payload["owner"] = owner

        if row:
            row.entity_id = target_entity
            row.cash_type = cash_type
            row.amount_limit = float(amount_limit)
            row.status = status
            row.extra = payload
        else:
            row = FCTPettyCash(
                id=parsed_id or uuid4(),
                tenant_id=tenant_id,
                entity_id=target_entity,
                cash_type=cash_type,
                amount_limit=float(amount_limit),
                current_balance=float(amount_limit),
                status=status,
                extra=payload,
            )
            session.add(row)
        await session.flush()
        return {
            "success": True,
            "tenant_id": tenant_id,
            "petty_cash_id": str(row.id),
            "entity_id": row.entity_id,
            "cash_type": row.cash_type,
            "amount_limit": float(row.amount_limit or 0),
            "current_balance": float(row.current_balance or 0),
            "currency": payload.get("currency"),
            "owner": payload.get("owner"),
            "status": row.status,
            "extra": row.extra or {},
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
        filters = [FCTPettyCash.tenant_id == tenant_id]
        if entity_id:
            filters.append(FCTPettyCash.entity_id == entity_id)
        if cash_type:
            filters.append(FCTPettyCash.cash_type == cash_type)

        total_stmt = select(func.count(FCTPettyCash.id)).where(and_(*filters))
        total = int((await session.execute(total_stmt)).scalar() or 0)
        stmt = select(FCTPettyCash).where(and_(*filters)).order_by(FCTPettyCash.updated_at.desc()).offset(skip).limit(limit)
        rows = (await session.execute(stmt)).scalars().all()
        items = [
            {
                "petty_cash_id": str(r.id),
                "tenant_id": r.tenant_id,
                "entity_id": r.entity_id,
                "cash_type": r.cash_type,
                "amount_limit": float(r.amount_limit or 0),
                "current_balance": float(r.current_balance or 0),
                "status": r.status,
                "extra": r.extra or {},
            }
            for r in rows
        ]
        return {"items": items, "total": total, "skip": skip, "limit": limit}

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
        parsed_id = self._parse_uuid_or_none(petty_cash_id)
        if not parsed_id:
            raise ValueError("petty_cash_id 无效")
        petty_cash = (await session.execute(select(FCTPettyCash).where(FCTPettyCash.id == parsed_id))).scalar_one_or_none()
        if not petty_cash:
            raise ValueError("备用金主档不存在")

        normalized_type = (record_type or "").strip().lower()
        delta = float(amount)
        if normalized_type in {"expense", "out", "payment"}:
            delta = -abs(delta)
        else:
            delta = abs(delta)

        petty_cash.current_balance = float(petty_cash.current_balance or 0) + delta
        row = FCTPettyCashRecord(
            petty_cash_id=petty_cash.id,
            record_type=normalized_type or "expense",
            amount=float(amount),
            biz_date=biz_date or date.today(),
            ref_type=ref_type,
            ref_id=ref_id,
            description=description,
            extra=None,
        )
        session.add(row)
        await session.flush()
        return {
            "success": True,
            "record_id": str(row.id),
            "petty_cash_id": str(petty_cash.id),
            "record_type": row.record_type,
            "amount": float(row.amount or 0),
            "biz_date": row.biz_date.isoformat() if row.biz_date else None,
            "ref_type": row.ref_type,
            "ref_id": row.ref_id,
            "description": row.description,
            "balance_after": float(petty_cash.current_balance or 0),
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
        filters = []
        parsed_id = self._parse_uuid_or_none(normalized_cash_id)
        if parsed_id:
            filters.append(FCTPettyCashRecord.petty_cash_id == parsed_id)
        if start_date:
            filters.append(FCTPettyCashRecord.biz_date >= start_date)
        if end_date:
            filters.append(FCTPettyCashRecord.biz_date <= end_date)

        stmt = (
            select(FCTPettyCashRecord, FCTPettyCash)
            .join(FCTPettyCash, FCTPettyCash.id == FCTPettyCashRecord.petty_cash_id)
            .where(and_(*filters) if filters else text("1=1"))
        )
        if tenant_id:
            stmt = stmt.where(FCTPettyCash.tenant_id == tenant_id)

        count_stmt = (
            select(func.count(FCTPettyCashRecord.id))
            .select_from(FCTPettyCashRecord)
            .join(FCTPettyCash, FCTPettyCash.id == FCTPettyCashRecord.petty_cash_id)
            .where(and_(*filters) if filters else text("1=1"))
        )
        if tenant_id:
            count_stmt = count_stmt.where(FCTPettyCash.tenant_id == tenant_id)
        total = int((await session.execute(count_stmt)).scalar() or 0)

        rows = (
            await session.execute(
                stmt.order_by(FCTPettyCashRecord.biz_date.desc(), FCTPettyCashRecord.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
        ).all()
        items = [
            {
                "record_id": str(r.id),
                "petty_cash_id": str(pc.id),
                "tenant_id": pc.tenant_id,
                "entity_id": pc.entity_id,
                "record_type": r.record_type,
                "amount": float(r.amount or 0),
                "biz_date": r.biz_date.isoformat() if r.biz_date else None,
                "ref_type": r.ref_type,
                "ref_id": r.ref_id,
                "description": r.description,
            }
            for r, pc in rows
        ]
        return {
            "items": items,
            "total": total,
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
        approved_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S") if status_l == "approved" else None
        approved_by = (extra or {}).get("approved_by") if isinstance(extra, dict) else None
        comment = (extra or {}).get("comment") if isinstance(extra, dict) else None
        row = FCTApprovalRecord(
            tenant_id=tenant_id,
            ref_type=ref_type,
            ref_id=ref_id,
            step=int(step or 1),
            status=status_l,
            approved_at=approved_at,
            approved_by=approved_by,
            comment=comment,
            extra=extra or {},
        )
        session.add(row)
        await session.flush()
        result: Dict[str, Any] = {
            "approval_id": str(row.id),
            "tenant_id": tenant_id,
            "ref_type": ref_type,
            "ref_id": ref_id,
            "step": int(step or 1),
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
        stmt = (
            select(FCTApprovalRecord)
            .where(
                and_(
                    FCTApprovalRecord.tenant_id == tenant_id,
                    FCTApprovalRecord.ref_type == ref_type,
                    FCTApprovalRecord.ref_id == ref_id,
                )
            )
            .order_by(FCTApprovalRecord.step.asc(), FCTApprovalRecord.created_at.asc())
        )
        rows = (await session.execute(stmt)).scalars().all()
        records: List[Dict[str, Any]] = [
            {
                "approval_id": str(r.id),
                "step": int(r.step or 1),
                "status": (r.status or "").lower(),
                "approved_at": r.approved_at,
                "approved_by": r.approved_by,
                "comment": r.comment,
                "extra": r.extra or {},
            }
            for r in rows
        ]

        if records:
            return {"tenant_id": tenant_id, "ref_type": ref_type, "ref_id": ref_id, "records": records}

    async def update_approval_status(
        self,
        session: AsyncSession,
        approval_id: str,
        new_status: str,
        approved_by: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        更新审批记录状态（pending → approved / rejected）。

        审批通过时：
          - 若 ref_type=voucher，联动凭证状态 draft → approved
          - 记录 approved_at / approved_by / comment
        """
        from src.models.fct import FCTApprovalRecord

        stmt = select(FCTApprovalRecord).where(FCTApprovalRecord.id == approval_id)
        row = (await session.execute(stmt)).scalar_one_or_none()
        if not row:
            raise ValueError(f"审批记录 {approval_id} 不存在")

        allowed_statuses = {"pending", "approved", "rejected", "withdrawn"}
        new_status_l = new_status.strip().lower()
        if new_status_l not in allowed_statuses:
            raise ValueError(f"无效状态 '{new_status}'，允许值：{', '.join(sorted(allowed_statuses))}")

        row.status = new_status_l
        if new_status_l == "approved":
            row.approved_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
            if approved_by:
                row.approved_by = approved_by
        if comment:
            row.comment = comment

        await session.flush()

        result: Dict[str, Any] = {
            "approval_id": str(row.id),
            "ref_type": row.ref_type,
            "ref_id": row.ref_id,
            "step": int(row.step or 1),
            "status": new_status_l,
            "approved_at": row.approved_at,
            "approved_by": row.approved_by,
            "success": True,
        }

        # 凭证联动：approved → voucher draft→approved
        if row.ref_type in {"voucher", "fct_voucher"} and new_status_l == "approved":
            sync = await self.update_voucher_status(session, voucher_id=row.ref_id, target_status="approved")
            result["voucher_sync"] = sync

        return result

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
                select(func.sum(FinancialTransaction.amount)).where(
                    and_(*filters, FinancialTransaction.transaction_type == "income")
                )
                if filters
                else select(func.sum(FinancialTransaction.amount)).where(FinancialTransaction.transaction_type == "income")
            )
            exp_stmt = (
                select(func.sum(FinancialTransaction.amount)).where(
                    and_(*filters, FinancialTransaction.transaction_type == "expense")
                )
                if filters
                else select(func.sum(FinancialTransaction.amount)).where(FinancialTransaction.transaction_type == "expense")
            )
            income = (await session.execute(inc_stmt)).scalar() or 0
            expense = (await session.execute(exp_stmt)).scalar() or 0
            return {"income": income, "expense": expense, "net": income - expense}
        except sa_exc.SQLAlchemyError:
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
            data.append(
                {
                    "period": period_str,
                    "revenue_yuan": self._y(rev),
                    "expense_yuan": self._y(exp),
                    "net_yuan": self._y(rev - exp),
                }
            )
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
            data.append(
                {
                    "entity_id": row[0],
                    "revenue_yuan": self._y(rev),
                    "expense_yuan": self._y(exp),
                    "net_yuan": self._y(rev - exp),
                }
            )
        return {"report_type": "by_entity", "tenant_id": tenant_id, "data": data}

    async def get_report_by_region(
        self,
        session: AsyncSession,
        tenant_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        filters = []
        if start_date:
            filters.append(FinancialTransaction.transaction_date >= start_date)
        if end_date:
            filters.append(FinancialTransaction.transaction_date <= end_date)

        stmt = (
            select(
                func.coalesce(Store.region, "unknown").label("region"),
                func.sum(
                    case(
                        (FinancialTransaction.transaction_type == "income", FinancialTransaction.amount),
                        else_=0,
                    )
                ).label("income"),
                func.sum(
                    case(
                        (FinancialTransaction.transaction_type == "expense", FinancialTransaction.amount),
                        else_=0,
                    )
                ).label("expense"),
            )
            .select_from(FinancialTransaction)
            .join(Store, Store.id == FinancialTransaction.store_id, isouter=True)
            .where(and_(*filters) if filters else text("1=1"))
            .group_by(func.coalesce(Store.region, "unknown"))
            .order_by(func.coalesce(Store.region, "unknown"))
        )
        rows = (await session.execute(stmt)).fetchall()
        data: List[Dict[str, Any]] = []
        for row in rows:
            income = int(row[1] or 0)
            expense = int(row[2] or 0)
            net = income - expense
            data.append(
                {
                    "region": row[0],
                    "income": income,
                    "income_yuan": self._y(income),
                    "expense": expense,
                    "expense_yuan": self._y(expense),
                    "net": net,
                    "net_yuan": self._y(net),
                }
            )
        return {"report_type": "by_region", "tenant_id": tenant_id, "data": data}

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
        previous = {"income": 0, "expense": 0, "net": 0}

        if start_date and end_date:
            compare_t = (compare_type or "yoy").lower()
            if compare_t == "mom":
                prev_start = self._shift_month(start_date, -1)
                prev_end = self._shift_month(end_date, -1)
            else:
                compare_t = "yoy"
                prev_start = self._shift_year(start_date, -1)
                prev_end = self._shift_year(end_date, -1)
            previous = await self._aggregate_transactions(session, entity_id, prev_start, prev_end)
            compare_type = compare_t

        def _pct(curr: int, prev: int) -> Optional[float]:
            if prev == 0:
                return None
            return round((curr - prev) / prev * 100, 2)

        return {
            "report_type": "comparison",
            "tenant_id": tenant_id,
            "compare_type": compare_type,
            "current": current,
            "previous": previous,
            "changes": {
                "income_pct": _pct(int(current.get("income") or 0), int(previous.get("income") or 0)),
                "expense_pct": _pct(int(current.get("expense") or 0), int(previous.get("expense") or 0)),
                "net_pct": _pct(int(current.get("net") or 0), int(previous.get("net") or 0)),
            },
        }

    async def get_report_consolidated(
        self,
        session: AsyncSession,
        tenant_id: str,
        period: str,
        group_by: Optional[str] = "entity",
    ) -> Dict[str, Any]:
        if not period or len(period) != 6 or not period.isdigit():
            raise ValueError("period 格式应为 YYYYMM")

        year, month = int(period[:4]), int(period[4:6])
        start_d = date(year, month, 1)
        end_d = date(year, month, monthrange(year, month)[1])

        stmt = text("""
            SELECT store_id,
                   SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE 0 END) AS income,
                   SUM(CASE WHEN transaction_type = 'expense' THEN amount ELSE 0 END) AS expense
            FROM financial_transactions
            WHERE transaction_date >= :df AND transaction_date <= :dt
            GROUP BY store_id
            ORDER BY store_id
        """)
        rows = (await session.execute(stmt, {"df": start_d, "dt": end_d})).fetchall()

        by_entity: List[Dict[str, Any]] = []
        total_income = 0
        total_expense = 0
        for row in rows:
            income = int(row[1] or 0)
            expense = int(row[2] or 0)
            net = income - expense
            total_income += income
            total_expense += expense
            by_entity.append(
                {
                    "entity_id": row[0],
                    "income": income,
                    "income_yuan": self._y(income),
                    "expense": expense,
                    "expense_yuan": self._y(expense),
                    "net": net,
                    "net_yuan": self._y(net),
                }
            )

        total_net = total_income - total_expense
        result: Dict[str, Any] = {
            "report_type": "consolidated",
            "tenant_id": tenant_id,
            "period": period,
            "group_by": group_by or "entity",
            "balances": {
                "income": total_income,
                "income_yuan": self._y(total_income),
                "expense": total_expense,
                "expense_yuan": self._y(total_expense),
                "net": total_net,
                "net_yuan": self._y(total_net),
            },
        }
        if (group_by or "entity") == "entity":
            result["by_entity"] = by_entity
        return result

    KNOWN_REPORT_TYPES = frozenset(
        {
            "period_summary",
            "aggregate",
            "trend",
            "by_entity",
            "by_region",
            "comparison",
            "plan_vs_actual",
            "consolidated",
        }
    )

    def get_supported_report_types(self) -> List[str]:
        """返回所有已支持的报表类型列表（升序）。"""
        return sorted(self.KNOWN_REPORT_TYPES)


# ── 模块级单例（供 fct_public.py 使用） ─────────────────────────────────────
fct_service = StandaloneFCTService()
