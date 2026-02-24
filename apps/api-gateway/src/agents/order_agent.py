"""
OrderAgent - 订单分析Agent (RAG增强)
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import os
import structlog

from .llm_agent import LLMEnhancedAgent, AgentResult
from ..services.rag_service import RAGService
from ..core.monitoring import error_monitor, ErrorSeverity, ErrorCategory

logger = structlog.get_logger()


class OrderAgent(LLMEnhancedAgent):
    """
    订单分析Agent

    功能:
    - 订单异常检测
    - 订单量预测
    - 客户行为分析
    - 菜品定价优化

    RAG增强:
    - 基于历史订单数据
    - 基于客户行为数据
    - 基于定价历史
    """

    def __init__(self):
        super().__init__(agent_type="order")
        self.rag_service = RAGService()

    async def analyze_order_anomaly(
        self,
        store_id: str,
        order_id: Optional[str] = None,
        time_period: str = "today"
    ) -> AgentResult:
        """
        分析订单异常

        Args:
            store_id: 门店ID
            order_id: 订单ID (可选，用于分析特定订单)
            time_period: 时间周期

        Returns:
            AgentResult（含 reasoning / confidence / source_data）
        """
        try:
            if order_id:
                query = f"""
                分析门店{store_id}订单{order_id}的异常情况:
                - 退单原因分析
                - 差评原因分析
                - 配送超时原因
                - 客户投诉分析

                请基于历史相似案例给出:
                1. 异常类型判断
                2. 根本原因分析
                3. 解决方案建议
                4. 预防措施
                """
            else:
                query = f"""
                分析门店{store_id}在{time_period}的订单异常情况:
                - 退单率异常
                - 差评率异常
                - 超时率异常
                - 客诉率异常

                请基于历史数据分析:
                1. 异常指标识别
                2. 异常原因分析
                3. 改进建议
                4. 预期效果
                """

            logger.info(
                "Analyzing order anomaly with RAG",
                store_id=store_id,
                order_id=order_id,
                time_period=time_period
            )

            rag_result = await self.rag_service.analyze_with_rag(
                query=query,
                store_id=store_id,
                collection="orders",
                top_k=int(os.getenv("RAG_ORDER_TOP_K", "12"))
            )

            ctx_count = rag_result["metadata"]["context_count"]
            scope = f"订单 {order_id}" if order_id else f"{time_period} 整体"
            return self.format_response(
                success=True,
                data={
                    "analysis": rag_result["response"],
                    "order_id": order_id,
                    "time_period": time_period,
                    "context_used": ctx_count,
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="订单异常分析完成",
                reasoning=f"基于 {ctx_count} 条历史订单，分析 {scope} 异常",
                confidence=min(0.9, 0.45 + ctx_count * 0.05),
                source_data={"store_id": store_id, "order_id": order_id, "time_period": time_period},
            )

        except Exception as e:
            logger.error("Order anomaly analysis failed", store_id=store_id, order_id=order_id, error=str(e), exc_info=e)
            error_monitor.log_error(
                message=f"Order anomaly analysis failed for {store_id}",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.AGENT,
                exception=e,
                context={"store_id": store_id, "order_id": order_id}
            )
            return self.format_response(
                success=False, data=None, message=f"分析失败: {str(e)}",
                reasoning=f"分析过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )

    async def predict_order_volume(
        self,
        store_id: str,
        time_range: str = "7d",
        granularity: str = "day"
    ) -> AgentResult:
        """预测订单量"""
        try:
            query = f"""
            预测门店{store_id}未来{time_range}的订单量(按{granularity}):
            - 基于历史订单趋势
            - 考虑星期几因素
            - 考虑节假日影响
            - 考虑天气因素
            - 考虑促销活动

            请给出:
            1. 预测订单量
            2. 置信区间
            3. 影响因素分析
            4. 风险提示
            """

            logger.info("Predicting order volume with RAG", store_id=store_id, time_range=time_range)

            rag_result = await self.rag_service.analyze_with_rag(
                query=query, store_id=store_id, collection="orders",
                top_k=int(os.getenv("RAG_ORDER_TOP_K", "12"))
            )

            ctx_count = rag_result["metadata"]["context_count"]
            return self.format_response(
                success=True,
                data={
                    "prediction": rag_result["response"],
                    "time_range": time_range,
                    "granularity": granularity,
                    "context_used": ctx_count,
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="订单量预测完成",
                reasoning=f"基于 {ctx_count} 条历史订单，预测未来 {time_range}（粒度: {granularity}）",
                confidence=min(0.85, 0.4 + ctx_count * 0.05),
                source_data={"store_id": store_id, "time_range": time_range, "granularity": granularity},
            )

        except Exception as e:
            logger.error("Order volume prediction failed", store_id=store_id, error=str(e), exc_info=e)
            return self.format_response(
                success=False, data=None, message=f"预测失败: {str(e)}",
                reasoning=f"预测过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )

    async def analyze_customer_behavior(
        self,
        store_id: str,
        customer_id: Optional[str] = None,
        segment: Optional[str] = None
    ) -> AgentResult:
        """分析客户行为"""
        try:
            if customer_id:
                query = f"""
                分析门店{store_id}客户{customer_id}的行为特征:
                - 消费频次和金额
                - 偏好菜品分析
                - 下单时间规律
                - 流失风险评估

                请基于历史数据给出:
                1. 客户画像
                2. 行为特征
                3. 营销建议
                4. 留存策略
                """
            else:
                segment_text = f"{segment}群体" if segment else "整体客户"
                query = f"""
                分析门店{store_id}{segment_text}的行为特征:
                - 消费习惯分析
                - 偏好趋势变化
                - 流失率分析
                - 复购率分析

                请给出:
                1. 群体特征
                2. 行为洞察
                3. 营销策略
                4. 增长机会
                """

            logger.info("Analyzing customer behavior with RAG", store_id=store_id, customer_id=customer_id, segment=segment)

            rag_result = await self.rag_service.analyze_with_rag(
                query=query, store_id=store_id, collection="orders",
                top_k=int(os.getenv("RAG_ORDER_TOP_K", "12"))
            )

            ctx_count = rag_result["metadata"]["context_count"]
            scope = f"客户 {customer_id}" if customer_id else (f"{segment}群体" if segment else "整体客户")
            return self.format_response(
                success=True,
                data={
                    "analysis": rag_result["response"],
                    "customer_id": customer_id,
                    "segment": segment,
                    "context_used": ctx_count,
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="客户行为分析完成",
                reasoning=f"基于 {ctx_count} 条历史订单，分析 {scope} 行为特征",
                confidence=min(0.9, 0.45 + ctx_count * 0.05),
                source_data={"store_id": store_id, "customer_id": customer_id, "segment": segment},
            )

        except Exception as e:
            logger.error("Customer behavior analysis failed", store_id=store_id, customer_id=customer_id, error=str(e), exc_info=e)
            return self.format_response(
                success=False, data=None, message=f"分析失败: {str(e)}",
                reasoning=f"分析过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )

    async def optimize_menu_pricing(
        self,
        store_id: str,
        dish_ids: List[str]
    ) -> AgentResult:
        """优化菜品定价"""
        try:
            dishes_text = ", ".join(dish_ids)

            query = f"""
            优化门店{store_id}以下菜品的定价:
            {dishes_text}

            请基于历史数据分析:
            1. 当前定价合理性
            2. 价格弹性分析
            3. 竞品定价对比
            4. 优化建议

            目标: 提升营收和利润率
            """

            logger.info("Optimizing menu pricing with RAG", store_id=store_id, dish_count=len(dish_ids))

            rag_result = await self.rag_service.analyze_with_rag(
                query=query, store_id=store_id, collection="orders",
                top_k=int(os.getenv("RAG_ORDER_TOP_K", "12"))
            )

            ctx_count = rag_result["metadata"]["context_count"]
            return self.format_response(
                success=True,
                data={
                    "optimization": rag_result["response"],
                    "dish_count": len(dish_ids),
                    "context_used": ctx_count,
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="定价优化完成",
                reasoning=f"基于 {ctx_count} 条历史数据，优化 {len(dish_ids)} 种菜品定价",
                confidence=min(0.85, 0.4 + ctx_count * 0.05),
                source_data={"store_id": store_id, "dish_count": len(dish_ids)},
            )

        except Exception as e:
            logger.error("Menu pricing optimization failed", store_id=store_id, error=str(e), exc_info=e)
            return self.format_response(
                success=False, data=None, message=f"优化失败: {str(e)}",
                reasoning=f"优化过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )
