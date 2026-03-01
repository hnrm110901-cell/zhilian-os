"""
DecisionAgent - 决策分析Agent (Claude Tool Use 增强)
"""
from typing import Dict, Any, Optional
from decimal import Decimal
import structlog

from .llm_agent import LLMEnhancedAgent, AgentResult
from ..services.decision_validator import DecisionValidator, ValidationResult
from ..core.monitoring import error_monitor, ErrorSeverity, ErrorCategory

logger = structlog.get_logger()


class DecisionAgent(LLMEnhancedAgent):
    """
    决策分析Agent

    功能:
    - 营收异常分析
    - 订单趋势分析
    - 客流预测
    - 经营建议生成

    Tool Use 增强:
    - 基于历史决策案例
    - 基于历史营收数据
    - 基于历史异常事件
    """

    def __init__(self):
        super().__init__(agent_type="decision")
        self.validator = DecisionValidator()

    async def analyze_revenue_anomaly(
        self,
        store_id: str,
        current_revenue: Decimal,
        expected_revenue: Decimal,
        time_period: str = "today"
    ) -> AgentResult:
        """
        分析营收异常

        Args:
            store_id: 门店ID
            current_revenue: 当前营收（Decimal，元）
            expected_revenue: 预期营收（Decimal，元）
            time_period: 时间周期

        Returns:
            AgentResult（含 reasoning / confidence / tool_calls）
        """
        try:
            # 计算异常程度
            deviation = float((current_revenue - expected_revenue) / expected_revenue * 100)

            user_message = (
                f"门店 {store_id} 在 {time_period} 出现营收异常："
                f"当前营收 {current_revenue} 元，预期营收 {expected_revenue} 元，偏差 {deviation:.1f}%。"
                f"请查询历史异常事件，分析可能的原因（天气/竞争/运营/节假日等），"
                f"给出根本原因判断、短期应对措施和中长期改进建议。"
            )

            logger.info(
                "Analyzing revenue anomaly with Tool Use",
                store_id=store_id,
                current_revenue=str(current_revenue),
                expected_revenue=str(expected_revenue),
                deviation=deviation
            )

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={
                    "current_revenue": str(current_revenue),
                    "expected_revenue": str(expected_revenue),
                    "deviation_pct": deviation,
                    "time_period": time_period,
                }
            )

            if not result.success:
                return result

            formatted = self.format_response(
                success=True,
                data={
                    "analysis": result.data,
                    "deviation": deviation,
                    "current_revenue": str(current_revenue),
                    "expected_revenue": str(expected_revenue),
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                },
                message="营收异常分析完成",
                reasoning=result.reasoning or (
                    f"当前营收 ¥{current_revenue}，预期 ¥{expected_revenue}，偏差 {deviation:.1f}%"
                ),
                confidence=result.confidence,
                source_data={
                    "store_id": store_id,
                    "current_revenue": str(current_revenue),
                    "expected_revenue": str(expected_revenue),
                    "time_period": time_period,
                    "deviation_pct": deviation,
                },
            )

            # Publish to shared memory bus so peer agents can react
            await self.publish_finding(
                store_id=store_id,
                action="revenue_anomaly",
                summary=f"营收偏差 {deviation:.1f}%，当前 ¥{current_revenue} vs 预期 ¥{expected_revenue}",
                confidence=formatted.confidence,
                data={"deviation": deviation, "current": str(current_revenue), "expected": str(expected_revenue)},
            )

            return formatted

        except Exception as e:
            logger.error(
                "Revenue anomaly analysis failed",
                store_id=store_id,
                error=str(e),
                exc_info=e
            )
            return self.format_response(
                success=False,
                data=None,
                message=f"分析失败: {str(e)}",
                reasoning=f"分析过程中发生异常: {str(e)}",
                confidence=0.0,
                source_data={"store_id": store_id},
            )

    async def analyze_order_trend(
        self,
        store_id: str,
        time_range: str = "7d"
    ) -> AgentResult:
        """
        分析订单趋势

        Args:
            store_id: 门店ID
            time_range: 时间范围

        Returns:
            AgentResult（含 reasoning / confidence / tool_calls）
        """
        try:
            user_message = (
                f"分析门店 {store_id} 最近 {time_range} 的订单趋势："
                f"请查询历史订单数据，分析订单量变化、客单价变化、热门菜品变化和高峰时段变化，"
                f"给出趋势判断和经营建议。"
            )

            logger.info(
                "Analyzing order trend with Tool Use",
                store_id=store_id,
                time_range=time_range
            )

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={"time_range": time_range}
            )

            if not result.success:
                return result

            return self.format_response(
                success=True,
                data={
                    "analysis": result.data,
                    "time_range": time_range,
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                },
                message="订单趋势分析完成",
                reasoning=result.reasoning or f"分析 {time_range} 订单趋势",
                confidence=result.confidence,
                source_data={"store_id": store_id, "time_range": time_range},
            )

        except Exception as e:
            logger.error(
                "Order trend analysis failed",
                store_id=store_id,
                error=str(e),
                exc_info=e
            )
            return self.format_response(
                success=False,
                data=None,
                message=f"分析失败: {str(e)}",
                reasoning=f"分析过程中发生异常: {str(e)}",
                confidence=0.0,
                source_data={"store_id": store_id},
            )

    async def generate_business_recommendations(
        self,
        store_id: str,
        focus_area: Optional[str] = None,
        validation_context: Optional[Dict] = None
    ) -> AgentResult:
        """
        生成经营建议

        Args:
            store_id: 门店ID
            focus_area: 关注领域 (revenue/orders/inventory/staff)

        Returns:
            AgentResult（含 reasoning / confidence / tool_calls）
        """
        try:
            focus_text = f"重点关注{focus_area}" if focus_area else "全面分析"

            user_message = (
                f"为门店 {store_id} 生成经营建议（{focus_text}）："
                f"请查询历史数据，识别改进机会，提供可执行的建议，预测潜在风险，"
                f"给出具体的、可操作的经营改进方案。"
            )

            logger.info(
                "Generating business recommendations with Tool Use",
                store_id=store_id,
                focus_area=focus_area
            )

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={"focus_area": focus_area}
            )

            if not result.success:
                return result

            # 合规性校验（预算）
            validation = None
            if validation_context:
                decision = {"action": "recommendation", **validation_context.get("decision_overrides", {})}
                validation = await self.validator.validate_decision(
                    decision=decision,
                    context=validation_context,
                    rules_to_apply=["budget_check"]
                )
                if validation["result"] == ValidationResult.REJECTED.value:
                    return self.format_response(
                        success=False,
                        data={"recommendations": result.data, "focus_area": focus_area},
                        message=f"经营建议被合规校验拒绝: {validation['message']}",
                        reasoning=f"LLM 生成了经营建议，但预算校验拒绝: {validation['message']}",
                        confidence=0.0,
                        source_data={"store_id": store_id, "focus_area": focus_area, "validation": validation},
                    )

            source = {"store_id": store_id, "focus_area": focus_area}
            if validation:
                source["validation"] = validation

            has_warning = validation and validation["result"] == ValidationResult.WARNING.value
            return self.format_response(
                success=True,
                data={
                    "recommendations": result.data,
                    "focus_area": focus_area,
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                    **({"validation": validation} if validation else {}),
                },
                message="经营建议生成完成" + ("（含合规警告）" if has_warning else ""),
                reasoning=result.reasoning or f"{focus_text}，生成可执行经营建议",
                confidence=result.confidence,
                source_data=source,
            )

        except Exception as e:
            logger.error(
                "Business recommendations generation failed",
                store_id=store_id,
                error=str(e),
                exc_info=e
            )
            return self.format_response(
                success=False,
                data=None,
                message=f"生成失败: {str(e)}",
                reasoning=f"生成过程中发生异常: {str(e)}",
                confidence=0.0,
                source_data={"store_id": store_id},
            )
