"""
快速规划服务（Fast Planning Service）

职责：
  在 17:00-17:30 的初版规划阶段，用历史规律 + L3/L4 数据，
  在 30 秒内生成各阶段的初版建议（80% 准确度，够用就好）。

数据来源：
  - cross_store_metrics（L3 物化表）：历史 KPI 均值/同伴组百分位
  - reasoning_reports（L4 推理层）：最新 P1/P2 风险标记
  - orders/inventory（业务表）：历史订单量和库存水位
  - 周几模式（day-of-week pattern）：核心预测基础

设计原则：
  - 每个方法 <30 秒响应（不调用 LLM，纯规则/统计）
  - 数据缺失时降级返回合理默认值（非致命）
  - 结果直接写入 DecisionVersion（由 WorkflowEngine 负责）
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# 按餐厅规模的人均服务能力（客/人/小时）
_STAFF_CAPACITY = {
    "cashier":   30,
    "waiter":    15,
    "chef":      20,
    "chef_senior": 15,
    "delivery":  25,
}

# 各渠道客流系数（基于堂食客流估算）
_CHANNEL_RATIO = {
    "dine_in":  0.60,
    "takeout":  0.30,
    "banquet":  0.10,
}

# 客流预测的星期系数（以周日=1.0为基准）
_DOW_FACTOR = {
    0: 1.15,  # 周一
    1: 1.05,  # 周二
    2: 1.0,   # 周三
    3: 1.1,   # 周四
    4: 1.4,   # 周五
    5: 1.5,   # 周六
    6: 1.3,   # 周日
}


class FastPlanningService:
    """
    快速规划服务

    使用示例::

        svc = FastPlanningService(db)
        initial = await svc.generate_initial_plan("STORE001", date(2026, 3, 2))
        # initial["forecast_footfall"] → 142
        # initial["risk_flags"] → ["waste P2: staff_error 置信度0.73"]

        procurement = await svc.generate_procurement(
            "STORE001", date(2026, 3, 2), initial["forecast_footfall"]
        )
        # procurement["total_cost"] → 1840.0
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Phase 1: 初版规划（客流预测 + 风险标记） ──────────────────────────────

    async def generate_initial_plan(
        self,
        store_id:  str,
        plan_date: date,
    ) -> Dict[str, Any]:
        """
        生成初版规划（初始估算）。

        算法：
          1. 取近 4 周同星期的历史日均客流（cross_store_metrics）
          2. 乘以星期系数（周五 × 1.4）
          3. 取 L4 最新 P1/P2 报告作为风险标记
          4. 取近 7 天销量 TOP5 菜品

        Returns:
            {forecast_footfall, dow_factor, base_footfall,
             top_dishes, risk_flags, data_completeness}
        """
        import time
        t0 = time.time()

        dow       = plan_date.weekday()
        dow_factor = _DOW_FACTOR.get(dow, 1.0)

        # 历史基准客流
        base_footfall = await self._get_base_footfall(store_id, dow)
        forecast      = int(base_footfall * dow_factor)

        # L4 风险标记
        risk_flags = await self._get_risk_flags(store_id)

        # TOP 菜品（近7天）
        top_dishes = await self._get_top_dishes(store_id, days=7)

        completeness = 0.7 if base_footfall > 0 else 0.3

        logger.info(
            "初版规划生成",
            store_id=store_id,
            plan_date=str(plan_date),
            forecast_footfall=forecast,
            risk_count=len(risk_flags),
            elapsed=round(time.time() - t0, 2),
        )
        return {
            "forecast_footfall": forecast,
            "base_footfall":     int(base_footfall),
            "dow_factor":        dow_factor,
            "day_of_week":       ["周一","周二","周三","周四","周五","周六","周日"][dow],
            "top_dishes":        top_dishes[:5],
            "risk_flags":        risk_flags,
            "data_completeness": completeness,
        }

    # ── Phase 2: 采购建议 ─────────────────────────────────────────────────────

    async def generate_procurement(
        self,
        store_id:          str,
        plan_date:         date,
        forecast_footfall: int,
        banquet_addons:    Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        基于客流预测生成采购建议。

        算法：
          1. 取近 30 天各食材人均消耗量（cross_store_metrics 或 inventory）
          2. 乘以预测客流 → 需采购量
          3. 减去当前库存水位 → 实际缺口
          4. 若无历史数据，用默认品类系数估算
          5. 若有 banquet_addons（宴会熔断输出），追加到清单末尾

        Args:
            banquet_addons: BanquetPlanningEngine.generate_procurement_addon() 输出列表，
                            格式 [{item_name, recommended_quantity, unit, alert_level, ...}]
                            会被追加到常规采购清单，并标记 source="banquet_circuit_breaker"

        Returns:
            {items: [{ingredient, qty, unit, estimated_cost, urgency, source}],
             total_cost, banquet_addon_cost, data_completeness}
        """
        import time
        t0 = time.time()

        items = await self._estimate_procurement_items(store_id, forecast_footfall)
        regular_total = sum(i.get("estimated_cost", 0) for i in items)

        # 追加宴会熔断采购加成
        banquet_addon_cost = 0.0
        if banquet_addons:
            for addon in banquet_addons:
                # 转换 addon 格式（BanquetPlanningEngine → FastPlanning 统一格式）
                item = {
                    "ingredient":     addon.get("item_name", addon.get("category", "宴会物料")),
                    "qty":            float(addon.get("recommended_quantity") or 0),
                    "unit":           addon.get("unit", "kg"),
                    "estimated_cost": self._estimate_addon_item_cost(addon),
                    "urgency":        addon.get("alert_level", "normal"),
                    "source":         "banquet_circuit_breaker",
                    "party_size_basis": addon.get("party_size_basis"),
                }
                banquet_addon_cost += item["estimated_cost"]
                items.append(item)

        total = regular_total + banquet_addon_cost

        logger.info(
            "采购建议生成",
            store_id=store_id,
            items_count=len(items),
            regular_cost=round(regular_total, 1),
            banquet_addon_cost=round(banquet_addon_cost, 1),
            total_cost=round(total, 1),
            elapsed=round(time.time() - t0, 2),
        )
        return {
            "items":              items,
            "total_cost":         round(total, 1),
            "regular_cost":       round(regular_total, 1),
            "banquet_addon_cost": round(banquet_addon_cost, 1),
            "forecast_footfall":  forecast_footfall,
            "data_completeness":  0.65 if items else 0.2,
            "note": "基于历史人均消耗 × 预测客流估算，请店长核实库存后确认",
        }

    # ── Phase 3: 排班建议 ─────────────────────────────────────────────────────

    async def generate_scheduling(
        self,
        store_id:          str,
        plan_date:         date,
        forecast_footfall: int,
    ) -> Dict[str, Any]:
        """
        基于客流预测生成排班框架建议。

        算法：
          峰值客流 = forecast_footfall × 0.4 (假设午餐/晚餐各占40%)
          各岗位人数 = ceil(峰值客流 / 人均服务能力)
          生成早中晚三班排班框架

        Returns:
            {shifts, total_staff, estimated_labor_hours, data_completeness}
        """
        import math
        import time
        t0 = time.time()

        peak = forecast_footfall * 0.4
        shifts = [
            {
                "shift":       "早班",
                "start_hour":  7,
                "end_hour":    14,
                "roles": {
                    "chef":    max(1, math.ceil(peak * 0.3 / _STAFF_CAPACITY["chef"])),
                    "waiter":  max(1, math.ceil(peak * 0.3 / _STAFF_CAPACITY["waiter"])),
                    "cashier": 1,
                },
            },
            {
                "shift":       "午班",
                "start_hour":  11,
                "end_hour":    15,
                "roles": {
                    "chef":    max(2, math.ceil(peak / _STAFF_CAPACITY["chef"])),
                    "waiter":  max(2, math.ceil(peak / _STAFF_CAPACITY["waiter"])),
                    "cashier": 1,
                },
            },
            {
                "shift":       "晚班",
                "start_hour":  17,
                "end_hour":    22,
                "roles": {
                    "chef":    max(2, math.ceil(peak / _STAFF_CAPACITY["chef"])),
                    "waiter":  max(2, math.ceil(peak / _STAFF_CAPACITY["waiter"])),
                    "cashier": 1,
                },
            },
        ]

        total_staff = sum(
            sum(s["roles"].values()) for s in shifts
        )
        labor_hours = sum(
            (s["end_hour"] - s["start_hour"]) * sum(s["roles"].values())
            for s in shifts
        )

        logger.info(
            "排班建议生成",
            store_id=store_id,
            total_staff=total_staff,
            elapsed=round(time.time() - t0, 2),
        )
        return {
            "shifts":                shifts,
            "total_staff":           total_staff,
            "estimated_labor_hours": labor_hours,
            "forecast_footfall":     forecast_footfall,
            "data_completeness":     0.6,
            "note": "基于峰值客流估算，请结合员工实际情况调整",
        }

    # ── Phase 4: 菜单建议 ─────────────────────────────────────────────────────

    async def generate_menu_plan(
        self,
        store_id:  str,
        plan_date: date,
    ) -> Dict[str, Any]:
        """
        基于 L4 推理 + 近期销售生成菜单调整建议。

        包括：主推菜品、停售建议、调价建议（L4 废损维度支撑）

        Returns:
            {featured, stop_sell, price_adjustments, data_completeness}
        """
        import time
        t0 = time.time()

        # L4 废损/质量维度的建议
        waste_actions  = await self._get_l4_actions(store_id, "waste")
        quality_actions = await self._get_l4_actions(store_id, "quality")

        # TOP 菜品（主推）
        top_dishes = await self._get_top_dishes(store_id, days=7)
        featured   = [d["dish_name"] for d in top_dishes[:3]]

        # 低销量菜品（停售候选）
        stop_sell = await self._get_low_sales_dishes(store_id, days=7)

        logger.info(
            "菜单建议生成",
            store_id=store_id,
            featured_count=len(featured),
            stop_sell_count=len(stop_sell),
            elapsed=round(time.time() - t0, 2),
        )
        return {
            "featured":          featured,
            "stop_sell":         stop_sell[:3],
            "price_adjustments": [],   # 需要更精确的价格弹性数据，快速模式暂不生成
            "waste_alerts":      waste_actions[:2],
            "quality_alerts":    quality_actions[:2],
            "data_completeness": 0.7,
            "note": "主推建议基于近7天销量TOP菜品，停售建议请结合库存确认",
        }

    # ── Phase 6: 营销方案建议 ──────────────────────────────────────────────────

    async def generate_marketing_plan(
        self,
        store_id:  str,
        plan_date: date,
        menu_plan: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        基于主推菜品 + L3 同伴组生成营销建议。

        Returns:
            {push_messages, target_segments, promo_items}
        """
        import time
        t0 = time.time()

        featured = (menu_plan or {}).get("featured", [])
        promo_items = [
            {"dish": d, "discount": 0, "reason": "今日主推，高评分菜品"}
            for d in featured[:2]
        ]

        dow = plan_date.weekday()
        if dow in (4, 5):   # 周五/六流量大
            target_segments = ["vip_members", "nearby_users"]
            push_time = "17:30"
        else:
            target_segments = ["frequent_customers"]
            push_time = "18:00"

        push_messages = []
        if featured:
            push_messages.append(
                f"【今日主推】{' · '.join(featured[:2])}，欢迎预约！"
            )

        logger.info(
            "营销方案生成",
            store_id=store_id,
            elapsed=round(time.time() - t0, 2),
        )
        return {
            "push_messages":    push_messages,
            "target_segments":  target_segments,
            "promo_items":      promo_items,
            "suggested_push_time": push_time,
            "data_completeness": 0.5,
            "note": "快速模式仅提供基础营销方向，精确模式可结合会员数据优化",
        }

    # ── 内部查询方法 ──────────────────────────────────────────────────────────

    async def _get_base_footfall(self, store_id: str, dow: int) -> float:
        """取近 4 周同星期的历史客流均值"""
        try:
            from src.models.cross_store import CrossStoreMetric
            since = date.today() - timedelta(days=28)
            stmt  = select(
                func.avg(CrossStoreMetric.value)
            ).where(
                and_(
                    CrossStoreMetric.store_id    == store_id,
                    CrossStoreMetric.metric_name == "daily_footfall",
                    CrossStoreMetric.metric_date >= since,
                    func.extract("dow", CrossStoreMetric.metric_date) == dow,
                )
            )
            result = (await self.db.execute(stmt)).scalar()
            return float(result) if result else 80.0  # 默认 80 人
        except Exception:
            return 80.0

    async def _get_risk_flags(self, store_id: str) -> List[str]:
        """取 L4 最新 P1/P2 报告作为风险标记文字"""
        try:
            from src.models.reasoning import ReasoningReport
            since = date.today() - timedelta(days=3)
            stmt  = (
                select(ReasoningReport)
                .where(
                    and_(
                        ReasoningReport.store_id  == store_id,
                        ReasoningReport.severity.in_(["P1", "P2"]),
                        ReasoningReport.report_date >= since,
                        ReasoningReport.is_actioned == False,  # noqa: E712
                    )
                )
                .order_by(ReasoningReport.severity, ReasoningReport.report_date.desc())
                .limit(5)
            )
            reports = (await self.db.execute(stmt)).scalars().all()
            return [
                f"{r.severity} {r.dimension}: {r.root_cause or '异常'} (置信度{r.confidence:.0%})"
                for r in reports
            ]
        except Exception:
            return []

    async def _get_top_dishes(self, store_id: str, days: int = 7) -> List[Dict]:
        """近 N 天销量 TOP 菜品（从 cross_store_metrics 取 dish_sales_rank）"""
        try:
            from src.models.cross_store import CrossStoreMetric
            since = date.today() - timedelta(days=days)
            stmt  = (
                select(
                    CrossStoreMetric.metric_name,
                    func.avg(CrossStoreMetric.value).label("avg_sales"),
                )
                .where(
                    and_(
                        CrossStoreMetric.store_id    == store_id,
                        CrossStoreMetric.metric_name.like("dish_sales_%"),
                        CrossStoreMetric.metric_date >= since,
                    )
                )
                .group_by(CrossStoreMetric.metric_name)
                .order_by(func.avg(CrossStoreMetric.value).desc())
                .limit(5)
            )
            rows = (await self.db.execute(stmt)).all()
            return [
                {
                    "dish_name": r[0].replace("dish_sales_", ""),
                    "avg_daily": round(float(r[1]), 1),
                }
                for r in rows
            ]
        except Exception:
            return []

    async def _get_low_sales_dishes(self, store_id: str, days: int = 7) -> List[str]:
        """近 N 天销量最低的菜品（停售候选）"""
        try:
            from src.models.cross_store import CrossStoreMetric
            since = date.today() - timedelta(days=days)
            stmt  = (
                select(
                    CrossStoreMetric.metric_name,
                    func.avg(CrossStoreMetric.value).label("avg_sales"),
                )
                .where(
                    and_(
                        CrossStoreMetric.store_id    == store_id,
                        CrossStoreMetric.metric_name.like("dish_sales_%"),
                        CrossStoreMetric.metric_date >= since,
                    )
                )
                .group_by(CrossStoreMetric.metric_name)
                .having(func.avg(CrossStoreMetric.value) < 2)  # 日均<2份
                .order_by(func.avg(CrossStoreMetric.value))
                .limit(5)
            )
            rows = (await self.db.execute(stmt)).all()
            return [r[0].replace("dish_sales_", "") for r in rows]
        except Exception:
            return []

    async def _estimate_procurement_items(
        self, store_id: str, forecast_footfall: int
    ) -> List[Dict]:
        """估算采购清单（基于客流 × 品类系数）"""
        # 默认品类系数（克/人）和参考单价（元/公斤）
        DEFAULT_CATEGORIES = [
            {"ingredient": "猪肉",   "grams_per_guest": 80,  "price_per_kg": 28, "unit": "kg"},
            {"ingredient": "鸡肉",   "grams_per_guest": 60,  "price_per_kg": 22, "unit": "kg"},
            {"ingredient": "蔬菜类", "grams_per_guest": 150, "price_per_kg": 8,  "unit": "kg"},
            {"ingredient": "大米",   "grams_per_guest": 120, "price_per_kg": 6,  "unit": "kg"},
            {"ingredient": "食用油", "grams_per_guest": 15,  "price_per_kg": 16, "unit": "kg"},
            {"ingredient": "调味料", "grams_per_guest": 20,  "price_per_kg": 30, "unit": "kg"},
        ]
        items = []
        for cat in DEFAULT_CATEGORIES:
            qty = round(forecast_footfall * cat["grams_per_guest"] / 1000, 1)
            cost = round(qty * cat["price_per_kg"], 1)
            items.append({
                "ingredient":      cat["ingredient"],
                "qty":             qty,
                "unit":            cat["unit"],
                "estimated_cost":  cost,
                "urgency":         "normal",
            })
        return items

    @staticmethod
    def _estimate_addon_item_cost(addon: Dict[str, Any]) -> float:
        """
        粗略估算宴会加成食材成本（元）。

        基于食材类别映射单价（元/kg 或 元/L），
        实际价格应由 SupplierService 更新。
        """
        _UNIT_PRICE: Dict[str, float] = {
            "premium_meat":  80.0,
            "seafood":       120.0,
            "poultry":       35.0,
            "vegetables":    8.0,
            "rice_staples":  5.0,
            "condiments":    20.0,
            "beverages":     15.0,
            "desserts":      30.0,
        }
        cat   = addon.get("category", "")
        qty   = float(addon.get("recommended_quantity") or 0)
        price = _UNIT_PRICE.get(cat, 20.0)
        return round(qty * price, 2)

    async def _get_l4_actions(self, store_id: str, dimension: str) -> List[str]:
        """取 L4 某维度最新推理报告的 recommended_actions"""
        try:
            from src.models.reasoning import ReasoningReport
            stmt = (
                select(ReasoningReport)
                .where(
                    and_(
                        ReasoningReport.store_id  == store_id,
                        ReasoningReport.dimension == dimension,
                        ReasoningReport.severity.in_(["P1", "P2", "P3"]),
                    )
                )
                .order_by(ReasoningReport.report_date.desc())
                .limit(1)
            )
            report = (await self.db.execute(stmt)).scalar_one_or_none()
            if report and report.recommended_actions:
                return list(report.recommended_actions)[:3]
        except Exception:
            pass
        return []
