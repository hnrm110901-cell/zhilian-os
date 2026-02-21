"""
DecisionAgent - 决策分析Agent (RAG增强)
"""
from typing import Dict, Any, Optional
import structlog

from .llm_agent import LLMEnhancedAgent
from ..services.rag_service import RAGService
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

    async def analyze_revenue_anomaly(
        self,
        store_id: str,
        current_revenue: float,
        expected_revenue: float,
        time_period: str = "today"
    ) -> Dict[str, Any]:
        """
        分析营收异常

        Args:
            store_id: 门店ID
            current_revenue: 当前营收
            expected_revenue: 预期营收
            time_period: 时间周期

        Returns:
            分析结果和建议
        """
        try:
            # 计算异常程度
            deviation = ((current_revenue - expected_revenue) / expected_revenue) * 100

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
                current_revenue=current_revenue,
                expected_revenue=expected_revenue,
                deviation=deviation
            )

            # 使用RAG增强分析
            rag_result = await self.rag_service.analyze_with_rag(
                query=query,
                store_id=store_id,
                collection="events",
                top_k=5
            )

            return self.format_response(
                success=True,
                data={
                    "analysis": rag_result["response"],
                    "deviation": deviation,
                    "current_revenue": current_revenue,
                    "expected_revenue": expected_revenue,
                    "context_used": rag_result["metadata"]["context_count"],
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="营收异常分析完成"
            )

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
                message=f"分析失败: {str(e)}"
            )

    async def analyze_order_trend(
        self,
        store_id: str,
        time_range: str = "7d"
    ) -> Dict[str, Any]:
        """
        分析订单趋势

        Args:
            store_id: 门店ID
            time_range: 时间范围

        Returns:
            趋势分析结果
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
                top_k=10
            )

            return self.format_response(
                success=True,
                data={
                    "analysis": rag_result["response"],
                    "time_range": time_range,
                    "context_used": rag_result["metadata"]["context_count"],
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="订单趋势分析完成"
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
                message=f"分析失败: {str(e)}"
            )

    async def generate_business_recommendations(
        self,
        store_id: str,
        focus_area: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成经营建议

        Args:
            store_id: 门店ID
            focus_area: 关注领域 (revenue/orders/inventory/staff)

        Returns:
            经营建议
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
                top_k=8
            )

            return self.format_response(
                success=True,
                data={
                    "recommendations": rag_result["response"],
                    "focus_area": focus_area,
                    "context_used": rag_result["metadata"]["context_count"],
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="经营建议生成完成"
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
                message=f"生成失败: {str(e)}"
            )
