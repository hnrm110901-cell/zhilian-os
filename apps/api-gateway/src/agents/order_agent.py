"""
OrderAgent - 订单分析Agent (Claude Tool Use 增强)
"""
from typing import Dict, Any, List, Optional
import structlog

from .llm_agent import LLMEnhancedAgent, AgentResult
from ..services.decision_validator import DecisionValidator, ValidationResult
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

    Tool Use 增强:
    - get_order_details: 获取订单详情
    - query_orders_by_condition: 按条件查询订单
    - get_menu_recommendations: 获取菜品推荐
    - update_order_status: 更新订单状态
    - calculate_bill: 计算账单
    """

    def __init__(self):
        super().__init__(agent_type="order")
        self.validator = DecisionValidator()

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
            order_id: 订单ID（可选，用于分析特定订单）
            time_period: 时间周期

        Returns:
            AgentResult（含 reasoning / confidence / tool_calls）
        """
        try:
            if order_id:
                user_message = (
                    f"分析门店 {store_id} 订单 {order_id} 的异常情况。"
                    f"请先获取该订单详情，再对比历史相似案例，"
                    f"判断异常类型（退单/差评/配送超时/客诉），分析根本原因，给出解决方案和预防措施。"
                )
            else:
                user_message = (
                    f"分析门店 {store_id} 在 {time_period} 的订单异常情况。"
                    f"请查询该时段订单数据，识别退单率、差评率、超时率、客诉率等异常指标，"
                    f"分析异常原因，给出改进建议和预期效果。"
                )

            logger.info(
                "Analyzing order anomaly with Tool Use",
                store_id=store_id,
                order_id=order_id,
                time_period=time_period
            )

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={"order_id": order_id, "time_period": time_period}
            )

            if not result.success:
                return result

            scope = f"订单 {order_id}" if order_id else f"{time_period} 整体"
            return self.format_response(
                success=True,
                data={
                    "analysis": result.data,
                    "order_id": order_id,
                    "time_period": time_period,
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                },
                message="订单异常分析完成",
                reasoning=result.reasoning or f"分析 {scope} 订单异常",
                confidence=result.confidence,
                source_data={"store_id": store_id, "order_id": order_id, "time_period": time_period},
            )

        except Exception as e:
            logger.error("Order anomaly analysis failed", store_id=store_id,
                         order_id=order_id, error=str(e), exc_info=e)
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
            user_message = (
                f"预测门店 {store_id} 未来 {time_range} 的订单量（按 {granularity} 粒度）。"
                f"请查询历史订单趋势，考虑星期几、节假日、天气和促销活动因素，"
                f"给出预测订单量、置信区间、影响因素分析和风险提示。"
            )

            logger.info("Predicting order volume with Tool Use",
                        store_id=store_id, time_range=time_range)

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={"time_range": time_range, "granularity": granularity}
            )

            if not result.success:
                return result

            return self.format_response(
                success=True,
                data={
                    "prediction": result.data,
                    "time_range": time_range,
                    "granularity": granularity,
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                },
                message="订单量预测完成",
                reasoning=result.reasoning or f"预测未来 {time_range}（粒度: {granularity}）订单量",
                confidence=result.confidence,
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
                user_message = (
                    f"分析门店 {store_id} 客户 {customer_id} 的行为特征。"
                    f"请查询该客户的历史订单，分析消费频次和金额、偏好菜品、下单时间规律和流失风险，"
                    f"给出客户画像、行为特征、营销建议和留存策略。"
                )
            else:
                scope = f"{segment} 群体" if segment else "整体客户"
                user_message = (
                    f"分析门店 {store_id} {scope} 的行为特征。"
                    f"请查询相关订单数据，分析消费习惯、偏好趋势变化、流失率和复购率，"
                    f"给出群体特征、行为洞察、营销策略和增长机会。"
                )

            logger.info("Analyzing customer behavior with Tool Use",
                        store_id=store_id, customer_id=customer_id, segment=segment)

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={"customer_id": customer_id, "segment": segment}
            )

            if not result.success:
                return result

            scope = f"客户 {customer_id}" if customer_id else (f"{segment} 群体" if segment else "整体客户")
            return self.format_response(
                success=True,
                data={
                    "analysis": result.data,
                    "customer_id": customer_id,
                    "segment": segment,
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                },
                message="客户行为分析完成",
                reasoning=result.reasoning or f"分析 {scope} 行为特征",
                confidence=result.confidence,
                source_data={"store_id": store_id, "customer_id": customer_id, "segment": segment},
            )

        except Exception as e:
            logger.error("Customer behavior analysis failed", store_id=store_id,
                         customer_id=customer_id, error=str(e), exc_info=e)
            return self.format_response(
                success=False, data=None, message=f"分析失败: {str(e)}",
                reasoning=f"分析过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )

    async def optimize_menu_pricing(
        self,
        store_id: str,
        dish_ids: List[str],
        validation_context: Optional[Dict] = None
    ) -> AgentResult:
        """优化菜品定价"""
        try:
            dishes_text = "、".join(dish_ids[:10]) + ("..." if len(dish_ids) > 10 else "")
            user_message = (
                f"优化门店 {store_id} 以下 {len(dish_ids)} 种菜品的定价：{dishes_text}。"
                f"请查询各菜品历史销售数据和菜品推荐信息，分析当前定价合理性、价格弹性和竞品对比，"
                f"给出提升营收和利润率的定价优化建议。"
            )

            logger.info("Optimizing menu pricing with Tool Use",
                        store_id=store_id, dish_count=len(dish_ids))

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={"dish_ids": dish_ids}
            )

            if not result.success:
                return result

            # 合规性校验（利润率）
            if validation_context:
                decision = {
                    "action": "pricing",
                    **validation_context.get("decision_overrides", {})
                }
                validation = await self.validator.validate_decision(
                    decision=decision,
                    context=validation_context,
                    rules_to_apply=["profit_margin"]
                )

                if validation["result"] == ValidationResult.REJECTED.value:
                    return self.format_response(
                        success=False,
                        data={"optimization": result.data, "dish_count": len(dish_ids)},
                        message=f"定价方案被合规校验拒绝: {validation['message']}",
                        reasoning=f"LLM 生成了定价建议，但利润率校验拒绝: {validation['message']}",
                        confidence=0.0,
                        source_data={"store_id": store_id, "dish_count": len(dish_ids),
                                     "validation": validation},
                    )

                has_warning = validation["result"] == ValidationResult.WARNING.value
                return self.format_response(
                    success=True,
                    data={
                        "optimization": result.data,
                        "dish_count": len(dish_ids),
                        "tool_calls": len(result.tool_calls),
                        "iterations": result.iterations,
                        "validation": validation,
                    },
                    message="定价优化完成" + ("（含合规警告）" if has_warning else ""),
                    reasoning=result.reasoning,
                    confidence=result.confidence,
                    source_data={"store_id": store_id, "dish_count": len(dish_ids),
                                 "validation": validation},
                )

            return self.format_response(
                success=True,
                data={
                    "optimization": result.data,
                    "dish_count": len(dish_ids),
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                },
                message="定价优化完成",
                reasoning=result.reasoning,
                confidence=result.confidence,
                source_data={"store_id": store_id, "dish_count": len(dish_ids)},
            )

        except Exception as e:
            logger.error("Menu pricing optimization failed", store_id=store_id, error=str(e), exc_info=e)
            return self.format_response(
                success=False, data=None, message=f"优化失败: {str(e)}",
                reasoning=f"优化过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )
