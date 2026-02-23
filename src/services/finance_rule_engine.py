"""
财务规则引擎
处理复杂的财务规则，包括平台抽佣、成本核算、利润计算等
"""
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
import structlog
from sqlalchemy.orm import Session

logger = structlog.get_logger()


class FinancialRule:
    """财务规则基类"""

    def __init__(self, rule_id: str, rule_name: str, rule_type: str):
        self.rule_id = rule_id
        self.rule_name = rule_name
        self.rule_type = rule_type

    def apply(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """应用规则"""
        raise NotImplementedError


class PlatformCommissionRule(FinancialRule):
    """平台抽佣规则"""

    def __init__(
        self,
        rule_id: str,
        platform: str,
        base_rate: float,
        rules: List[Dict[str, Any]]
    ):
        super().__init__(rule_id, f"{platform}抽佣规则", "platform_commission")
        self.platform = platform
        self.base_rate = base_rate
        self.rules = rules

    def apply(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算平台抽佣

        Args:
            context: {
                "order_amount": 订单金额,
                "has_discount": 是否有满减,
                "discount_amount": 满减金额,
                "is_peak_hour": 是否高峰时段,
                "customer_type": 客户类型
            }

        Returns:
            Dict: {
                "commission_rate": 抽佣率,
                "commission_amount": 抽佣金额,
                "net_amount": 净收入,
                "rule_applied": 应用的规则
            }
        """
        order_amount = context.get("order_amount", 0)
        commission_rate = self.base_rate

        # 应用规则
        applied_rules = []

        for rule in self.rules:
            rule_type = rule.get("type")

            # 满减规则
            if rule_type == "discount" and context.get("has_discount"):
                discount_amount = context.get("discount_amount", 0)
                if discount_amount >= rule.get("min_amount", 0):
                    commission_rate += rule.get("rate_adjustment", 0)
                    applied_rules.append(f"满减{discount_amount}元，抽佣率+{rule.get('rate_adjustment', 0)*100}%")

            # 高峰时段规则
            elif rule_type == "peak_hour" and context.get("is_peak_hour"):
                commission_rate += rule.get("rate_adjustment", 0)
                applied_rules.append(f"高峰时段，抽佣率+{rule.get('rate_adjustment', 0)*100}%")

            # 保底规则
            elif rule_type == "minimum":
                min_commission = rule.get("min_amount", 0)
                calculated_commission = order_amount * commission_rate
                if calculated_commission < min_commission:
                    commission_rate = min_commission / order_amount
                    applied_rules.append(f"保底抽佣{min_commission}元")

            # 动态费率规则
            elif rule_type == "dynamic":
                order_ranges = rule.get("ranges", [])
                for range_rule in order_ranges:
                    if range_rule["min"] <= order_amount < range_rule["max"]:
                        commission_rate = range_rule["rate"]
                        applied_rules.append(f"订单金额{order_amount}元，适用{commission_rate*100}%费率")
                        break

        # 计算抽佣金额
        commission_amount = order_amount * commission_rate
        net_amount = order_amount - commission_amount

        return {
            "platform": self.platform,
            "order_amount": order_amount,
            "commission_rate": round(commission_rate, 4),
            "commission_amount": round(commission_amount, 2),
            "net_amount": round(net_amount, 2),
            "rules_applied": applied_rules
        }


class CostCalculationRule(FinancialRule):
    """成本核算规则"""

    def __init__(self, rule_id: str):
        super().__init__(rule_id, "成本核算规则", "cost_calculation")

    def apply(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算订单成本

        Args:
            context: {
                "order_items": 订单项列表,
                "store_id": 门店ID,
                "labor_cost_rate": 人工成本率,
                "overhead_rate": 管理费用率
            }

        Returns:
            Dict: 成本明细
        """
        order_items = context.get("order_items", [])
        labor_cost_rate = context.get("labor_cost_rate", 0.15)  # 默认15%
        overhead_rate = context.get("overhead_rate", 0.10)  # 默认10%

        # 1. 食材成本（从BOM计算）
        food_cost = sum([item.get("food_cost", 0) for item in order_items])

        # 2. 人工成本
        revenue = sum([item.get("price", 0) * item.get("quantity", 0) for item in order_items])
        labor_cost = revenue * labor_cost_rate

        # 3. 管理费用（房租、水电等）
        overhead_cost = revenue * overhead_rate

        # 4. 总成本
        total_cost = food_cost + labor_cost + overhead_cost

        return {
            "food_cost": round(food_cost, 2),
            "labor_cost": round(labor_cost, 2),
            "overhead_cost": round(overhead_cost, 2),
            "total_cost": round(total_cost, 2),
            "cost_breakdown": {
                "food_cost_rate": round(food_cost / revenue, 4) if revenue > 0 else 0,
                "labor_cost_rate": labor_cost_rate,
                "overhead_rate": overhead_rate
            }
        }


class ProfitCalculationRule(FinancialRule):
    """利润计算规则"""

    def __init__(self, rule_id: str):
        super().__init__(rule_id, "利润计算规则", "profit_calculation")

    def apply(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算真实利润

        Args:
            context: {
                "revenue": 营收,
                "platform_commission": 平台抽佣,
                "food_cost": 食材成本,
                "labor_cost": 人工成本,
                "overhead_cost": 管理费用,
                "other_costs": 其他成本
            }

        Returns:
            Dict: 利润明细
        """
        revenue = context.get("revenue", 0)
        platform_commission = context.get("platform_commission", 0)
        food_cost = context.get("food_cost", 0)
        labor_cost = context.get("labor_cost", 0)
        overhead_cost = context.get("overhead_cost", 0)
        other_costs = context.get("other_costs", 0)

        # 净收入 = 营收 - 平台抽佣
        net_revenue = revenue - platform_commission

        # 总成本
        total_cost = food_cost + labor_cost + overhead_cost + other_costs

        # 毛利 = 营收 - 食材成本
        gross_profit = revenue - food_cost

        # 净利润 = 净收入 - 总成本
        net_profit = net_revenue - total_cost

        # 利润率
        gross_profit_margin = gross_profit / revenue if revenue > 0 else 0
        net_profit_margin = net_profit / revenue if revenue > 0 else 0

        return {
            "revenue": round(revenue, 2),
            "platform_commission": round(platform_commission, 2),
            "net_revenue": round(net_revenue, 2),
            "costs": {
                "food_cost": round(food_cost, 2),
                "labor_cost": round(labor_cost, 2),
                "overhead_cost": round(overhead_cost, 2),
                "other_costs": round(other_costs, 2),
                "total_cost": round(total_cost, 2)
            },
            "profit": {
                "gross_profit": round(gross_profit, 2),
                "net_profit": round(net_profit, 2),
                "gross_profit_margin": round(gross_profit_margin, 4),
                "net_profit_margin": round(net_profit_margin, 4)
            }
        }


class FinanceRuleEngine:
    """财务规则引擎"""

    def __init__(self):
        self.rules = {}
        self._initialize_default_rules()

    def _initialize_default_rules(self):
        """初始化默认规则"""
        # 美团抽佣规则
        self.rules["meituan_commission"] = PlatformCommissionRule(
            rule_id="meituan_001",
            platform="美团",
            base_rate=float(os.getenv("MEITUAN_COMMISSION_BASE_RATE", "0.18")),  # 基础抽佣
            rules=[
                {
                    "type": "discount",
                    "min_amount": float(os.getenv("COMMISSION_MIN_AMOUNT", "20")),
                    "rate_adjustment": 0.03  # 满减20元以上，抽佣率+3%
                },
                {
                    "type": "peak_hour",
                    "rate_adjustment": 0.02  # 高峰时段，抽佣率+2%
                },
                {
                    "type": "minimum",
                    "min_amount": 3.0  # 保底抽佣3元
                }
            ]
        )

        # 饿了么抽佣规则
        self.rules["eleme_commission"] = PlatformCommissionRule(
            rule_id="eleme_001",
            platform="饿了么",
            base_rate=float(os.getenv("ELEME_COMMISSION_BASE_RATE", "0.20")),  # 基础抽佣
            rules=[
                {
                    "type": "discount",
                    "min_amount": 15,
                    "rate_adjustment": 0.025  # 满减15元以上，抽佣率+2.5%
                },
                {
                    "type": "dynamic",
                    "ranges": [
                        {"min": 0, "max": 50, "rate": 0.22},
                        {"min": 50, "max": 100, "rate": 0.20},
                        {"min": 100, "max": float('inf'), "rate": 0.18}
                    ]
                }
            ]
        )

        # 成本核算规则
        self.rules["cost_calculation"] = CostCalculationRule("cost_001")

        # 利润计算规则
        self.rules["profit_calculation"] = ProfitCalculationRule("profit_001")

    def add_rule(self, rule: FinancialRule):
        """添加规则"""
        self.rules[rule.rule_id] = rule

    def get_rule(self, rule_id: str) -> Optional[FinancialRule]:
        """获取规则"""
        return self.rules.get(rule_id)

    async def calculate_order_profit(
        self,
        order_data: Dict[str, Any],
        store_config: Dict[str, Any],
        db: Session = None
    ) -> Dict[str, Any]:
        """
        计算订单真实利润

        Args:
            order_data: 订单数据
            store_config: 门店配置
            db: 数据库会话

        Returns:
            Dict: 利润分析结果
        """
        try:
            # 1. 计算平台抽佣
            platform = order_data.get("platform", "meituan")
            commission_rule_id = f"{platform}_commission"
            commission_rule = self.get_rule(commission_rule_id)

            if commission_rule:
                commission_result = commission_rule.apply({
                    "order_amount": order_data.get("total_amount", 0),
                    "has_discount": order_data.get("has_discount", False),
                    "discount_amount": order_data.get("discount_amount", 0),
                    "is_peak_hour": order_data.get("is_peak_hour", False)
                })
            else:
                # 默认抽佣
                commission_result = {
                    "platform": platform,
                    "commission_rate": 0.18,
                    "commission_amount": order_data.get("total_amount", 0) * 0.18,
                    "net_amount": order_data.get("total_amount", 0) * 0.82
                }

            # 2. 计算成本
            cost_rule = self.get_rule("cost_calculation")
            cost_result = cost_rule.apply({
                "order_items": order_data.get("items", []),
                "store_id": order_data.get("store_id"),
                "labor_cost_rate": store_config.get("labor_cost_rate", 0.15),
                "overhead_rate": store_config.get("overhead_rate", 0.10)
            })

            # 3. 计算利润
            profit_rule = self.get_rule("profit_calculation")
            profit_result = profit_rule.apply({
                "revenue": order_data.get("total_amount", 0),
                "platform_commission": commission_result["commission_amount"],
                "food_cost": cost_result["food_cost"],
                "labor_cost": cost_result["labor_cost"],
                "overhead_cost": cost_result["overhead_cost"],
                "other_costs": order_data.get("other_costs", 0)
            })

            return {
                "order_id": order_data.get("order_id"),
                "platform": platform,
                "commission": commission_result,
                "costs": cost_result,
                "profit": profit_result,
                "analysis": {
                    "is_profitable": profit_result["profit"]["net_profit"] > 0,
                    "profit_per_order": profit_result["profit"]["net_profit"],
                    "profit_margin": profit_result["profit"]["net_profit_margin"]
                }
            }

        except Exception as e:
            logger.error("calculate_order_profit_failed", error=str(e))
            raise

    async def analyze_menu_profitability(
        self,
        store_id: str,
        start_date: datetime,
        end_date: datetime,
        db: Session = None
    ) -> Dict[str, Any]:
        """
        分析菜品盈利能力

        Args:
            store_id: 门店ID
            start_date: 开始日期
            end_date: 结束日期
            db: 数据库会话

        Returns:
            Dict: 菜品盈利分析
        """
        try:
            if db is None:
                return {
                    "store_id": store_id,
                    "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
                    "dishes": [],
                    "error": "no_db_session"
                }

            from sqlalchemy import func
            from ..models.order import Order, OrderItem

            rows = (
                db.query(
                    OrderItem.item_id,
                    OrderItem.item_name,
                    func.sum(OrderItem.quantity).label("sales_count"),
                    func.sum(OrderItem.subtotal).label("revenue_cents"),
                )
                .join(Order, OrderItem.order_id == Order.id)
                .filter(
                    Order.store_id == store_id,
                    Order.order_time >= start_date,
                    Order.order_time <= end_date,
                    Order.status == "completed",
                )
                .group_by(OrderItem.item_id, OrderItem.item_name)
                .all()
            )

            food_cost_rate = float(os.getenv("DEFAULT_FOOD_COST_RATE", "0.30"))
            overhead_rate = float(os.getenv("DEFAULT_OVERHEAD_RATE", "0.30"))
            dishes = []
            for row in rows:
                revenue = (row.revenue_cents or 0) / 100.0
                food_cost = revenue * food_cost_rate
                gross_profit = revenue - food_cost
                gpm = gross_profit / revenue if revenue > 0 else 0
                net_profit = gross_profit - revenue * overhead_rate
                npm = net_profit / revenue if revenue > 0 else 0
                if gpm >= 0.6:
                    rec = "高利润菜品，建议推广"
                elif gpm >= 0.4:
                    rec = "利润适中，保持现状"
                else:
                    rec = "低利润菜品，考虑调整定价或成本"
                dishes.append({
                    "dish_id": row.item_id,
                    "dish_name": row.item_name,
                    "sales_count": row.sales_count,
                    "revenue": round(revenue, 2),
                    "food_cost": round(food_cost, 2),
                    "gross_profit": round(gross_profit, 2),
                    "gross_profit_margin": round(gpm, 2),
                    "net_profit": round(net_profit, 2),
                    "net_profit_margin": round(npm, 2),
                    "recommendation": rec,
                })

            return {
                "store_id": store_id,
                "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
                "dishes": sorted(dishes, key=lambda x: x["gross_profit_margin"], reverse=True),
            }

        except Exception as e:
            logger.error("analyze_menu_profitability_failed", error=str(e))
            raise


# 全局实例
finance_rule_engine = FinanceRuleEngine()
