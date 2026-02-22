"""
神经/符号双规机制
Neural-Symbolic Guardrails

核心理念：
- System 1 (Neural): 大模型提出草案
- System 2 (Symbolic): 规则引擎硬性校验
- 触发红线 → 立即降级为人类审批

应用场景：
- 采购订单校验
- 排班计划审核
- 定价策略验证
- 库存调拨审批
"""

from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


class ViolationSeverity(str, Enum):
    """违规严重程度"""
    CRITICAL = "critical"  # 严重违规，必须拦截
    HIGH = "high"          # 高风险，需要审批
    MEDIUM = "medium"      # 中等风险，警告
    LOW = "low"            # 低风险，记录


class RuleCategory(str, Enum):
    """规则类别"""
    FINANCIAL = "financial"        # 财务规则
    OPERATIONAL = "operational"    # 运营规则
    SAFETY = "safety"              # 安全规则
    COMPLIANCE = "compliance"      # 合规规则
    BUSINESS = "business"          # 业务规则


class RuleViolation(BaseModel):
    """规则违规"""
    rule_id: str
    rule_name: str
    category: RuleCategory
    severity: ViolationSeverity
    description: str
    actual_value: Any
    threshold_value: Any
    recommendation: str


class AIProposal(BaseModel):
    """AI提案"""
    proposal_id: str
    proposal_type: str  # purchase_order, schedule, pricing, etc.
    content: Dict[str, Any]
    confidence: float
    reasoning: str
    created_at: datetime


class GuardrailResult(BaseModel):
    """双规校验结果"""
    approved: bool
    violations: List[RuleViolation]
    requires_human_approval: bool
    escalation_reason: Optional[str]
    modified_proposal: Optional[Dict[str, Any]]


class NeuralSymbolicGuardrails:
    """神经/符号双规机制"""

    def __init__(self):
        self.rules = self._initialize_rules()

    def _initialize_rules(self) -> Dict[str, Dict]:
        """初始化规则库"""
        return {
            # 财务规则
            "FIN_001": {
                "name": "采购金额不可超过预算",
                "category": RuleCategory.FINANCIAL,
                "severity": ViolationSeverity.CRITICAL,
                "check": lambda proposal, context: (
                    proposal.get("total_amount", 0) <=
                    context.get("monthly_budget", float('inf'))
                ),
                "threshold_key": "monthly_budget"
            },
            "FIN_002": {
                "name": "采购量不可超过历史峰值120%",
                "category": RuleCategory.FINANCIAL,
                "severity": ViolationSeverity.HIGH,
                "check": lambda proposal, context: (
                    proposal.get("quantity", 0) <=
                    context.get("historical_peak", float('inf')) * 1.2
                ),
                "threshold_key": "historical_peak"
            },
            "FIN_003": {
                "name": "不可超出供应商信用额度",
                "category": RuleCategory.FINANCIAL,
                "severity": ViolationSeverity.CRITICAL,
                "check": lambda proposal, context: (
                    proposal.get("total_amount", 0) <=
                    context.get("supplier_credit_limit", float('inf'))
                ),
                "threshold_key": "supplier_credit_limit"
            },

            # 运营规则
            "OPS_001": {
                "name": "排班人数不可低于最低要求",
                "category": RuleCategory.OPERATIONAL,
                "severity": ViolationSeverity.CRITICAL,
                "check": lambda proposal, context: (
                    proposal.get("staff_count", 0) >=
                    context.get("minimum_staff", 0)
                ),
                "threshold_key": "minimum_staff"
            },
            "OPS_002": {
                "name": "单班时长不可超过劳动法上限",
                "category": RuleCategory.OPERATIONAL,
                "severity": ViolationSeverity.CRITICAL,
                "check": lambda proposal, context: (
                    proposal.get("shift_hours", 0) <= 8
                ),
                "threshold_key": "max_shift_hours"
            },
            "OPS_003": {
                "name": "库存调拨不可导致负库存",
                "category": RuleCategory.OPERATIONAL,
                "severity": ViolationSeverity.CRITICAL,
                "check": lambda proposal, context: (
                    context.get("current_stock", 0) -
                    proposal.get("transfer_quantity", 0) >= 0
                ),
                "threshold_key": "current_stock"
            },

            # 安全规则
            "SAFE_001": {
                "name": "食材保质期必须充足",
                "category": RuleCategory.SAFETY,
                "severity": ViolationSeverity.CRITICAL,
                "check": lambda proposal, context: (
                    proposal.get("shelf_life_days", 0) >= 3
                ),
                "threshold_key": "minimum_shelf_life"
            },
            "SAFE_002": {
                "name": "冷链食材必须有温控记录",
                "category": RuleCategory.SAFETY,
                "severity": ViolationSeverity.HIGH,
                "check": lambda proposal, context: (
                    not proposal.get("requires_cold_chain", False) or
                    proposal.get("has_temperature_log", False)
                ),
                "threshold_key": "temperature_log_required"
            },

            # 合规规则
            "COMP_001": {
                "name": "必须有合法供应商资质",
                "category": RuleCategory.COMPLIANCE,
                "severity": ViolationSeverity.CRITICAL,
                "check": lambda proposal, context: (
                    proposal.get("supplier_certified", False)
                ),
                "threshold_key": "supplier_certification"
            },
            "COMP_002": {
                "name": "价格变动不可超过市场价30%",
                "category": RuleCategory.COMPLIANCE,
                "severity": ViolationSeverity.HIGH,
                "check": lambda proposal, context: (
                    abs(proposal.get("price", 0) -
                        context.get("market_price", 0)) /
                    context.get("market_price", 1) <= 0.3
                ),
                "threshold_key": "market_price"
            },

            # 业务规则
            "BIZ_001": {
                "name": "促销折扣不可低于成本价",
                "category": RuleCategory.BUSINESS,
                "severity": ViolationSeverity.HIGH,
                "check": lambda proposal, context: (
                    proposal.get("discounted_price", 0) >=
                    context.get("cost_price", 0)
                ),
                "threshold_key": "cost_price"
            },
            "BIZ_002": {
                "name": "新菜品必须有成本核算",
                "category": RuleCategory.BUSINESS,
                "severity": ViolationSeverity.MEDIUM,
                "check": lambda proposal, context: (
                    not proposal.get("is_new_dish", False) or
                    proposal.get("has_cost_breakdown", False)
                ),
                "threshold_key": "cost_breakdown_required"
            },
        }

    def validate_proposal(
        self,
        ai_proposal: AIProposal,
        context: Dict[str, Any]
    ) -> GuardrailResult:
        """
        校验AI提案

        Args:
            ai_proposal: AI生成的提案
            context: 业务上下文（预算、库存、历史数据等）

        Returns:
            校验结果
        """
        violations = []

        # 遍历所有规则进行校验
        for rule_id, rule in self.rules.items():
            try:
                # 执行规则检查
                passed = rule["check"](ai_proposal.content, context)

                if not passed:
                    # 规则违规
                    violation = RuleViolation(
                        rule_id=rule_id,
                        rule_name=rule["name"],
                        category=rule["category"],
                        severity=rule["severity"],
                        description=f"违反规则: {rule['name']}",
                        actual_value=ai_proposal.content.get(
                            rule.get("actual_key", "value")
                        ),
                        threshold_value=context.get(
                            rule["threshold_key"]
                        ),
                        recommendation=self._generate_recommendation(
                            rule_id, ai_proposal, context
                        )
                    )
                    violations.append(violation)

            except Exception as e:
                logger.error(f"Rule {rule_id} check failed: {e}")
                continue

        # 判断是否需要人类审批
        requires_approval = self._requires_human_approval(violations)

        # 判断是否批准
        approved = not requires_approval and len(violations) == 0

        # 生成升级原因
        escalation_reason = None
        if requires_approval:
            critical_violations = [
                v for v in violations
                if v.severity == ViolationSeverity.CRITICAL
            ]
            if critical_violations:
                escalation_reason = (
                    f"检测到{len(critical_violations)}个严重违规，"
                    f"必须人工审批"
                )
            else:
                escalation_reason = "检测到高风险操作，建议人工审批"

        logger.info(
            f"Proposal {ai_proposal.proposal_id} validation: "
            f"approved={approved}, violations={len(violations)}, "
            f"requires_approval={requires_approval}"
        )

        return GuardrailResult(
            approved=approved,
            violations=violations,
            requires_human_approval=requires_approval,
            escalation_reason=escalation_reason,
            modified_proposal=None
        )

    def _requires_human_approval(
        self,
        violations: List[RuleViolation]
    ) -> bool:
        """判断是否需要人类审批"""
        # 任何CRITICAL违规都需要审批
        if any(v.severity == ViolationSeverity.CRITICAL for v in violations):
            return True

        # 2个以上HIGH违规需要审批
        high_violations = [
            v for v in violations
            if v.severity == ViolationSeverity.HIGH
        ]
        if len(high_violations) >= 2:
            return True

        return False

    def _generate_recommendation(
        self,
        rule_id: str,
        ai_proposal: AIProposal,
        context: Dict[str, Any]
    ) -> str:
        """生成改进建议"""
        recommendations = {
            "FIN_001": "建议降低采购金额或申请预算追加",
            "FIN_002": "建议降低采购量至历史峰值的120%以内",
            "FIN_003": "建议联系供应商提高信用额度或分批采购",
            "OPS_001": "建议增加排班人数至最低要求",
            "OPS_002": "建议缩短单班时长或增加轮班",
            "OPS_003": "建议减少调拨数量或从其他门店调入",
            "SAFE_001": "建议选择保质期更长的食材或减少采购量",
            "SAFE_002": "建议添加温控记录或选择非冷链食材",
            "COMP_001": "建议更换有资质的供应商",
            "COMP_002": "建议调整价格至市场价±30%范围内",
            "BIZ_001": "建议提高折扣价格至成本价以上",
            "BIZ_002": "建议完成成本核算后再上架新菜品",
        }

        return recommendations.get(
            rule_id,
            "建议人工审核并调整方案"
        )

    def auto_fix_proposal(
        self,
        ai_proposal: AIProposal,
        violations: List[RuleViolation],
        context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        自动修复提案（如果可能）

        Args:
            ai_proposal: 原始提案
            violations: 违规列表
            context: 业务上下文

        Returns:
            修复后的提案，如果无法自动修复则返回None
        """
        # 只尝试修复MEDIUM和LOW级别的违规
        fixable_violations = [
            v for v in violations
            if v.severity in [ViolationSeverity.MEDIUM, ViolationSeverity.LOW]
        ]

        if not fixable_violations:
            return None

        modified = ai_proposal.content.copy()

        for violation in fixable_violations:
            if violation.rule_id == "FIN_002":
                # 自动调整采购量至历史峰值的120%
                modified["quantity"] = int(
                    context.get("historical_peak", 0) * 1.2
                )
            elif violation.rule_id == "BIZ_001":
                # 自动调整折扣价至成本价
                modified["discounted_price"] = context.get("cost_price", 0)

        logger.info(f"Auto-fixed proposal {ai_proposal.proposal_id}")
        return modified

    def get_rule_statistics(self) -> Dict[str, Any]:
        """获取规则统计信息"""
        stats = {
            "total_rules": len(self.rules),
            "by_category": {},
            "by_severity": {}
        }

        for rule in self.rules.values():
            # 按类别统计
            category = rule["category"]
            stats["by_category"][category] = (
                stats["by_category"].get(category, 0) + 1
            )

            # 按严重程度统计
            severity = rule["severity"]
            stats["by_severity"][severity] = (
                stats["by_severity"].get(severity, 0) + 1
            )

        return stats


# 全局实例
guardrails = NeuralSymbolicGuardrails()
