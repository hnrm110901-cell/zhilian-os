"""
决策校验器
实现AI决策的双规校验，防止AI幻觉导致的业务灾难
结合AI的直觉判断和规则引擎的逻辑校验
"""
import os
from typing import Dict, List, Optional, Any
import structlog
from datetime import datetime
from enum import Enum

logger = structlog.get_logger()


class ValidationResult(str, Enum):
    """校验结果"""
    APPROVED = "approved"  # 通过
    REJECTED = "rejected"  # 拒绝
    WARNING = "warning"  # 警告（需人工审核）


class ValidationRule:
    """校验规则基类"""

    def __init__(self, rule_id: str, rule_name: str):
        self.rule_id = rule_id
        self.rule_name = rule_name

    def validate(self, decision: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        校验决策

        Args:
            decision: AI决策
            context: 决策上下文

        Returns:
            Dict: 校验结果
        """
        raise NotImplementedError


class BudgetCheckRule(ValidationRule):
    """预算检查规则"""

    def __init__(self):
        super().__init__("budget_check", "预算检查")

    def validate(self, decision: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """检查决策是否超出预算"""
        try:
            decision_cost = decision.get("cost", 0)
            available_budget = context.get("available_budget", 0)
            budget_threshold = context.get("budget_threshold", 0.9)  # 默认90%预算阈值

            if decision_cost > available_budget:
                return {
                    "passed": False,
                    "rule": self.rule_name,
                    "reason": f"决策成本{decision_cost}元超出可用预算{available_budget}元",
                    "severity": "critical"
                }

            if decision_cost > available_budget * budget_threshold:
                return {
                    "passed": True,
                    "rule": self.rule_name,
                    "reason": f"决策成本{decision_cost}元接近预算上限（{budget_threshold*100}%）",
                    "severity": "warning"
                }

            return {
                "passed": True,
                "rule": self.rule_name,
                "reason": "预算检查通过",
                "severity": "info"
            }

        except Exception as e:
            logger.error("budget_check_failed", error=str(e))
            return {
                "passed": False,
                "rule": self.rule_name,
                "reason": f"预算检查失败: {str(e)}",
                "severity": "error"
            }


class InventoryCapacityRule(ValidationRule):
    """库存容量检查规则"""

    def __init__(self):
        super().__init__("inventory_capacity", "库存容量检查")

    def validate(self, decision: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """检查库存容量是否足够"""
        try:
            if decision.get("action") != "purchase":
                return {
                    "passed": True,
                    "rule": self.rule_name,
                    "reason": "非采购决策，跳过库存容量检查",
                    "severity": "info"
                }

            purchase_quantity = decision.get("quantity", 0)
            current_inventory = context.get("current_inventory", 0)
            max_capacity = context.get("max_capacity", 0)

            if max_capacity == 0:
                return {
                    "passed": True,
                    "rule": self.rule_name,
                    "reason": "未设置库存容量上限",
                    "severity": "warning"
                }

            total_after_purchase = current_inventory + purchase_quantity

            if total_after_purchase > max_capacity:
                return {
                    "passed": False,
                    "rule": self.rule_name,
                    "reason": f"采购后库存{total_after_purchase}超出容量上限{max_capacity}",
                    "severity": "critical"
                }

            if total_after_purchase > max_capacity * 0.9:
                return {
                    "passed": True,
                    "rule": self.rule_name,
                    "reason": f"采购后库存{total_after_purchase}接近容量上限（90%）",
                    "severity": "warning"
                }

            return {
                "passed": True,
                "rule": self.rule_name,
                "reason": "库存容量检查通过",
                "severity": "info"
            }

        except Exception as e:
            logger.error("inventory_capacity_check_failed", error=str(e))
            return {
                "passed": False,
                "rule": self.rule_name,
                "reason": f"库存容量检查失败: {str(e)}",
                "severity": "error"
            }


class HistoricalConsumptionRule(ValidationRule):
    """历史消耗检查规则"""

    def __init__(self):
        super().__init__("historical_consumption", "历史消耗检查")

    def validate(self, decision: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """检查决策是否符合历史消耗模式"""
        try:
            if decision.get("action") != "purchase":
                return {
                    "passed": True,
                    "rule": self.rule_name,
                    "reason": "非采购决策，跳过历史消耗检查",
                    "severity": "info"
                }

            purchase_quantity = decision.get("quantity", 0)
            avg_daily_consumption = context.get("avg_daily_consumption", 0)
            days_to_cover = context.get("days_to_cover", 7)  # 默认覆盖7天

            if avg_daily_consumption == 0:
                return {
                    "passed": True,
                    "rule": self.rule_name,
                    "reason": "无历史消耗数据",
                    "severity": "warning"
                }

            expected_quantity = avg_daily_consumption * days_to_cover
            deviation = abs(purchase_quantity - expected_quantity) / expected_quantity if expected_quantity > 0 else 0

            # 偏差超过3σ（99.7%置信区间）认为是异常
            if deviation > 3.0:
                return {
                    "passed": False,
                    "rule": self.rule_name,
                    "reason": f"采购量{purchase_quantity}与历史消耗偏差{deviation*100:.1f}%，超出3σ范围",
                    "severity": "critical"
                }

            # 偏差超过2σ（95%置信区间）给出警告
            if deviation > 2.0:
                return {
                    "passed": True,
                    "rule": self.rule_name,
                    "reason": f"采购量{purchase_quantity}与历史消耗偏差{deviation*100:.1f}%，超出2σ范围",
                    "severity": "warning"
                }

            return {
                "passed": True,
                "rule": self.rule_name,
                "reason": f"采购量{purchase_quantity}符合历史消耗模式（偏差{deviation*100:.1f}%）",
                "severity": "info"
            }

        except Exception as e:
            logger.error("historical_consumption_check_failed", error=str(e))
            return {
                "passed": False,
                "rule": self.rule_name,
                "reason": f"历史消耗检查失败: {str(e)}",
                "severity": "error"
            }


class SupplierAvailabilityRule(ValidationRule):
    """供应商可用性检查规则"""

    def __init__(self):
        super().__init__("supplier_availability", "供应商可用性检查")

    def validate(self, decision: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """检查供应商是否可用"""
        try:
            if decision.get("action") != "purchase":
                return {
                    "passed": True,
                    "rule": self.rule_name,
                    "reason": "非采购决策，跳过供应商检查",
                    "severity": "info"
                }

            supplier_id = decision.get("supplier_id")
            available_suppliers = context.get("available_suppliers", [])

            if not supplier_id:
                return {
                    "passed": False,
                    "rule": self.rule_name,
                    "reason": "未指定供应商",
                    "severity": "critical"
                }

            if supplier_id not in available_suppliers:
                return {
                    "passed": False,
                    "rule": self.rule_name,
                    "reason": f"供应商{supplier_id}不可用",
                    "severity": "critical"
                }

            return {
                "passed": True,
                "rule": self.rule_name,
                "reason": "供应商可用性检查通过",
                "severity": "info"
            }

        except Exception as e:
            logger.error("supplier_availability_check_failed", error=str(e))
            return {
                "passed": False,
                "rule": self.rule_name,
                "reason": f"供应商可用性检查失败: {str(e)}",
                "severity": "error"
            }


class ProfitMarginRule(ValidationRule):
    """利润率检查规则"""

    def __init__(self):
        super().__init__("profit_margin", "利润率检查")

    def validate(self, decision: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """检查决策是否会导致利润率过低"""
        try:
            if decision.get("action") not in ["pricing", "discount"]:
                return {
                    "passed": True,
                    "rule": self.rule_name,
                    "reason": "非定价决策，跳过利润率检查",
                    "severity": "info"
                }

            new_price = decision.get("price", 0)
            cost = context.get("cost", 0)
            min_profit_margin = context.get("min_profit_margin", 0.2)  # 默认最低20%利润率

            if cost == 0:
                return {
                    "passed": True,
                    "rule": self.rule_name,
                    "reason": "无成本数据",
                    "severity": "warning"
                }

            profit_margin = (new_price - cost) / new_price if new_price > 0 else 0

            if profit_margin < 0:
                return {
                    "passed": False,
                    "rule": self.rule_name,
                    "reason": f"定价{new_price}元低于成本{cost}元，利润率为负",
                    "severity": "critical"
                }

            if profit_margin < min_profit_margin:
                return {
                    "passed": False,
                    "rule": self.rule_name,
                    "reason": f"利润率{profit_margin*100:.1f}%低于最低要求{min_profit_margin*100:.1f}%",
                    "severity": "critical"
                }

            if profit_margin < min_profit_margin * float(os.getenv("DECISION_PROFIT_WARNING_FACTOR", "1.2")):
                return {
                    "passed": True,
                    "rule": self.rule_name,
                    "reason": f"利润率{profit_margin*100:.1f}%接近最低要求",
                    "severity": "warning"
                }

            return {
                "passed": True,
                "rule": self.rule_name,
                "reason": f"利润率{profit_margin*100:.1f}%符合要求",
                "severity": "info"
            }

        except Exception as e:
            logger.error("profit_margin_check_failed", error=str(e))
            return {
                "passed": False,
                "rule": self.rule_name,
                "reason": f"利润率检查失败: {str(e)}",
                "severity": "error"
            }


class DecisionValidator:
    """决策校验器"""

    def __init__(self):
        self.rules = {
            "budget_check": BudgetCheckRule(),
            "inventory_capacity": InventoryCapacityRule(),
            "historical_consumption": HistoricalConsumptionRule(),
            "supplier_availability": SupplierAvailabilityRule(),
            "profit_margin": ProfitMarginRule()
        }

    def add_rule(self, rule: ValidationRule):
        """添加校验规则"""
        self.rules[rule.rule_id] = rule

    async def validate_decision(
        self,
        decision: Dict[str, Any],
        context: Dict[str, Any],
        rules_to_apply: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        校验AI决策

        Args:
            decision: AI决策
            context: 决策上下文
            rules_to_apply: 要应用的规则列表（None表示应用所有规则）

        Returns:
            Dict: 校验结果
        """
        try:
            # 确定要应用的规则
            if rules_to_apply is None:
                rules_to_apply = list(self.rules.keys())

            # 执行所有规则
            validation_results = []
            critical_failures = []
            warnings = []

            for rule_id in rules_to_apply:
                rule = self.rules.get(rule_id)
                if not rule:
                    logger.warning("rule_not_found", rule_id=rule_id)
                    continue

                result = rule.validate(decision, context)
                validation_results.append(result)

                if not result["passed"]:
                    if result["severity"] == "critical":
                        critical_failures.append(result)
                    elif result["severity"] == "error":
                        critical_failures.append(result)

                if result["severity"] == "warning":
                    warnings.append(result)

            # 判断最终结果
            if critical_failures:
                final_result = ValidationResult.REJECTED
                message = "决策被拒绝：" + "; ".join([f["reason"] for f in critical_failures])
            elif warnings:
                final_result = ValidationResult.WARNING
                message = "决策需要人工审核：" + "; ".join([w["reason"] for w in warnings])
            else:
                final_result = ValidationResult.APPROVED
                message = "决策通过所有校验"

            return {
                "result": final_result.value,
                "message": message,
                "validation_results": validation_results,
                "critical_failures": critical_failures,
                "warnings": warnings,
                "rules_applied": len(validation_results),
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error("validate_decision_failed", error=str(e))
            return {
                "result": ValidationResult.REJECTED.value,
                "message": f"校验过程失败: {str(e)}",
                "validation_results": [],
                "critical_failures": [{"reason": str(e), "severity": "error"}],
                "warnings": [],
                "rules_applied": 0,
                "timestamp": datetime.utcnow().isoformat()
            }

    async def validate_purchase_decision(
        self,
        ai_suggestion: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        校验采购决策

        Args:
            ai_suggestion: AI采购建议
            context: 决策上下文

        Returns:
            Dict: 校验结果
        """
        rules_to_apply = [
            "budget_check",
            "inventory_capacity",
            "historical_consumption",
            "supplier_availability"
        ]

        return await self.validate_decision(ai_suggestion, context, rules_to_apply)

    async def validate_pricing_decision(
        self,
        ai_suggestion: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        校验定价决策

        Args:
            ai_suggestion: AI定价建议
            context: 决策上下文

        Returns:
            Dict: 校验结果
        """
        rules_to_apply = [
            "profit_margin"
        ]

        return await self.validate_decision(ai_suggestion, context, rules_to_apply)

    async def detect_anomaly_decision(
        self,
        decision: Dict[str, Any],
        historical_decisions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        检测离群决策

        Args:
            decision: 当前决策
            historical_decisions: 历史决策列表

        Returns:
            Dict: 异常检测结果
        """
        try:
            if not historical_decisions:
                return {
                    "is_anomaly": False,
                    "reason": "无历史决策数据",
                    "confidence": 0.0
                }

            # 简化实现：检查决策值是否偏离历史平均值超过3σ
            decision_value = decision.get("value", 0)
            historical_values = [d.get("value", 0) for d in historical_decisions]

            if not historical_values:
                return {
                    "is_anomaly": False,
                    "reason": "无有效历史数据",
                    "confidence": 0.0
                }

            mean = sum(historical_values) / len(historical_values)
            variance = sum((x - mean) ** 2 for x in historical_values) / len(historical_values)
            std_dev = variance ** 0.5

            if std_dev == 0:
                return {
                    "is_anomaly": False,
                    "reason": "历史数据无变化",
                    "confidence": 0.0
                }

            z_score = abs((decision_value - mean) / std_dev)

            if z_score > 3.0:
                return {
                    "is_anomaly": True,
                    "reason": f"决策值{decision_value}偏离历史平均值{mean:.2f}超过3σ（z-score={z_score:.2f}）",
                    "confidence": min(z_score / 5.0, 1.0),
                    "z_score": z_score
                }

            return {
                "is_anomaly": False,
                "reason": f"决策值{decision_value}在正常范围内（z-score={z_score:.2f}）",
                "confidence": 0.0,
                "z_score": z_score
            }

        except Exception as e:
            logger.error("detect_anomaly_decision_failed", error=str(e))
            return {
                "is_anomaly": False,
                "reason": f"异常检测失败: {str(e)}",
                "confidence": 0.0
            }


# 全局实例
decision_validator = DecisionValidator()
