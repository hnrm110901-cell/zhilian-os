"""
DecisionAgent - 决策分析Agent (RAG增强)
"""
from typing import Dict, Any, Optional
from decimal import Decimal
import os
import structlog

from .llm_agent import LLMEnhancedAgent, AgentResult
from ..services.rag_service import RAGService
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

    RAG增强:
    - 基于历史决策案例
    - 基于历史营收数据
    - 基于历史异常事件
    """

    def __init__(self):
        super().__init__(agent_type="decision")
        self.rag_service = RAGService()
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
            AgentResult（含 reasoning / confidence / source_data）
        """
        try:
            # 计算异常程度
            deviation = float((current_revenue - expected_revenue) / expected_revenue * 100)

            # 构建查询
            query = f"""
            门店{store_id}在{time_period}出现营收异常:
            - 当前营收: {current_revenue}元
            - 预期营收: {expected_revenue}元
            - 偏差: {deviation:.1f}%

            请分析可能的原因并给出建议。
            """

            logger.info(
                "Analyzing revenue anomaly with RAG",
                store_id=store_id,
                current_revenue=str(current_revenue),
                expected_revenue=str(expected_revenue),
                deviation=deviation
            )

            # 使用RAG增强分析
            rag_result = await self.rag_service.analyze_with_rag(
                query=query,
                store_id=store_id,
                collection="events",
                top_k=int(os.getenv("RAG_DECISION_TOP_K", "8"))
            )

            result = self.format_response(
                success=True,
                data={
                    "analysis": rag_result["response"],
                    "deviation": deviation,
                    "current_revenue": str(current_revenue),
                    "expected_revenue": str(expected_revenue),
                    "context_used": rag_result["metadata"]["context_count"],
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="营收异常分析完成",
                reasoning=f"当前营收 ¥{current_revenue}，预期 ¥{expected_revenue}，偏差 {deviation:.1f}%，"
                          f"基于 {rag_result['metadata']['context_count']} 条历史事件分析",
                confidence=min(0.95, 0.5 + rag_result["metadata"]["context_count"] * 0.05),
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
                confidence=result.confidence,
                data={"deviation": deviation, "current": str(current_revenue), "expected": str(expected_revenue)},
            )

            return result

        except Exception as e:
            logger.error(
                "Revenue anomaly analysis failed",
                store_id=store_id,
                error=str(e),
                exc_info=e
            )

            error_monitor.log_error(
                message=f"Revenue anomaly analysis failed for {store_id}",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.AGENT,
                exception=e,
                context={"store_id": store_id}
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
            AgentResult（含 reasoning / confidence / source_data）
        """
        try:
            query = f"""
            分析门店{store_id}最近{time_range}的订单趋势:
            - 订单量变化
            - 客单价变化
            - 热门菜品变化
            - 高峰时段变化

            请给出趋势分析和经营建议。
            """

            logger.info(
                "Analyzing order trend with RAG",
                store_id=store_id,
                time_range=time_range
            )

            # 使用RAG检索历史订单数据
            rag_result = await self.rag_service.analyze_with_rag(
                query=query,
                store_id=store_id,
                collection="orders",
                top_k=int(os.getenv("RAG_DECISION_TOP_K", "8"))
            )

            return self.format_response(
                success=True,
                data={
                    "analysis": rag_result["response"],
                    "time_range": time_range,
                    "context_used": rag_result["metadata"]["context_count"],
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="订单趋势分析完成",
                reasoning=f"基于 {rag_result['metadata']['context_count']} 条历史订单数据，分析 {time_range} 趋势",
                confidence=min(0.9, 0.4 + rag_result["metadata"]["context_count"] * 0.05),
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
            AgentResult（含 reasoning / confidence / source_data）
        """
        try:
            focus_text = f"重点关注{focus_area}" if focus_area else "全面分析"

            query = f"""
            为门店{store_id}生成经营建议({focus_text}):
            - 基于历史数据分析
            - 识别改进机会
            - 提供可执行的建议
            - 预测潜在风险

            请给出具体的、可操作的建议。
            """

            logger.info(
                "Generating business recommendations with RAG",
                store_id=store_id,
                focus_area=focus_area
            )

            # 使用RAG检索多个集合
            rag_result = await self.rag_service.analyze_with_rag(
                query=query,
                store_id=store_id,
                collection="events",
                top_k=int(os.getenv("RAG_DECISION_TOP_K", "8"))
            )

            ctx_count = rag_result["metadata"]["context_count"]

            # 步骤4：合规性校验（预算）
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
                        data={"recommendations": rag_result["response"], "focus_area": focus_area},
                        message=f"经营建议被合规校验拒绝: {validation['message']}",
                        reasoning=f"LLM 生成了经营建议，但预算校验拒绝: {validation['message']}",
                        confidence=0.0,
                        source_data={"store_id": store_id, "focus_area": focus_area, "validation": validation},
                    )

            source = {"store_id": store_id, "focus_area": focus_area}
            if validation:
                source["validation"] = validation

            return self.format_response(
                success=True,
                data={
                    "recommendations": rag_result["response"],
                    "focus_area": focus_area,
                    "context_used": ctx_count,
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="经营建议生成完成" + ("（含合规警告）" if validation and validation["result"] == ValidationResult.WARNING.value else ""),
                reasoning=f"基于 {ctx_count} 条历史事件，{focus_text}，生成可执行经营建议",
                confidence=min(0.9, 0.45 + ctx_count * 0.05),
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
