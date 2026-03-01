"""
InventoryAgent - 库存管理Agent (Claude Tool Use 增强)
"""
from typing import Dict, Any, List, Optional
import os
import structlog

from .llm_agent import LLMEnhancedAgent, AgentResult
from ..services.decision_validator import DecisionValidator, ValidationResult
from ..core.monitoring import error_monitor, ErrorSeverity, ErrorCategory

logger = structlog.get_logger()


class InventoryAgent(LLMEnhancedAgent):
    """
    库存管理Agent

    功能:
    - 库存预警
    - 补货建议
    - 库存优化
    - 损耗分析

    Tool Use 增强:
    - get_inventory_status: 查询当前库存状态
    - get_consumption_trend: 获取消耗趋势
    - create_purchase_order: 创建采购订单
    - check_expiry_alerts: 检查临期预警
    """

    def __init__(self):
        super().__init__(agent_type="inventory")
        self.validator = DecisionValidator()

    async def predict_inventory_needs(
        self,
        store_id: str,
        dish_id: str,
        time_range: str = "3d"
    ) -> AgentResult:
        """
        预测库存需求

        Args:
            store_id: 门店ID
            dish_id: 菜品ID
            time_range: 预测时间范围

        Returns:
            AgentResult（含 reasoning / confidence / tool_calls）
        """
        try:
            user_message = (
                f"预测门店 {store_id} 菜品 {dish_id} 未来 {time_range} 的库存需求。"
                f"请查询该菜品的消耗趋势和当前库存状态，考虑季节性、节假日和促销活动因素，"
                f"给出预计销量、建议库存量、补货时间点和风险提示。"
            )

            logger.info(
                "Predicting inventory needs with Tool Use",
                store_id=store_id,
                dish_id=dish_id,
                time_range=time_range
            )

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={"dish_id": dish_id, "time_range": time_range}
            )

            if not result.success:
                return result

            return self.format_response(
                success=True,
                data={
                    "prediction": result.data,
                    "dish_id": dish_id,
                    "time_range": time_range,
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                },
                message="库存需求预测完成",
                reasoning=result.reasoning or f"预测菜品 {dish_id} 未来 {time_range} 需求",
                confidence=result.confidence,
                source_data={"store_id": store_id, "dish_id": dish_id, "time_range": time_range},
            )

        except Exception as e:
            logger.error("Inventory needs prediction failed", store_id=store_id,
                         dish_id=dish_id, error=str(e), exc_info=e)
            error_monitor.log_error(
                message=f"Inventory needs prediction failed for {store_id}",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.AGENT,
                exception=e,
                context={"store_id": store_id, "dish_id": dish_id}
            )
            return self.format_response(
                success=False, data=None, message=f"预测失败: {str(e)}",
                reasoning=f"预测过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )

    async def check_low_stock_alert(
        self,
        store_id: str,
        current_inventory: Dict[str, int],
        threshold_hours: int = int(os.getenv("INVENTORY_ALERT_THRESHOLD_HOURS", "4"))
    ) -> AgentResult:
        """检查低库存预警"""
        try:
            inventory_summary = "\n".join([
                f"- {dish_id}: {qty}份"
                for dish_id, qty in current_inventory.items()
            ])
            user_message = (
                f"检查门店 {store_id} 的低库存预警。当前库存状态：\n{inventory_summary}\n"
                f"请查询历史消耗趋势，判断哪些菜品可能在 {threshold_hours} 小时内售罄，"
                f"考虑即将到来的高峰时段，给出各菜品风险等级（高/中/低）和紧急补货建议。"
            )

            logger.info("Checking low stock alert with Tool Use", store_id=store_id,
                        inventory_count=len(current_inventory), threshold_hours=threshold_hours)

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={"current_inventory": current_inventory, "threshold_hours": threshold_hours}
            )

            if not result.success:
                return result

            alert_result = self.format_response(
                success=True,
                data={
                    "alert": result.data,
                    "inventory_count": len(current_inventory),
                    "threshold_hours": threshold_hours,
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                },
                message="低库存检查完成",
                reasoning=result.reasoning or f"检查 {len(current_inventory)} 种菜品 {threshold_hours}h 内风险",
                confidence=result.confidence,
                source_data={"store_id": store_id, "inventory_count": len(current_inventory),
                             "threshold_hours": threshold_hours},
            )

            # 发布到共享内存总线，供 DecisionAgent 等 peer agent 响应
            await self.publish_finding(
                store_id=store_id,
                action="low_stock_alert",
                summary=f"{len(current_inventory)} 种菜品库存不足，{threshold_hours}h 内存在售罄风险",
                confidence=alert_result.confidence,
                data={"inventory_count": len(current_inventory), "threshold_hours": threshold_hours},
            )

            return alert_result

        except Exception as e:
            logger.error("Low stock alert check failed", store_id=store_id, error=str(e), exc_info=e)
            return self.format_response(
                success=False, data=None, message=f"检查失败: {str(e)}",
                reasoning=f"检查过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )

    async def optimize_inventory_levels(
        self,
        store_id: str,
        dish_ids: List[str]
    ) -> AgentResult:
        """优化库存水平"""
        try:
            dishes_text = "、".join(dish_ids[:10]) + ("..." if len(dish_ids) > 10 else "")
            user_message = (
                f"优化门店 {store_id} 以下 {len(dish_ids)} 种菜品的库存水平：{dishes_text}。"
                f"请查询各菜品的消耗趋势和当前库存状态，分析最优库存量、安全库存水平、"
                f"补货频率，目标是减少损耗、提高周转率。"
            )

            logger.info("Optimizing inventory levels with Tool Use",
                        store_id=store_id, dish_count=len(dish_ids))

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={"dish_ids": dish_ids}
            )

            if not result.success:
                return result

            return self.format_response(
                success=True,
                data={
                    "optimization": result.data,
                    "dish_count": len(dish_ids),
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                },
                message="库存优化完成",
                reasoning=result.reasoning or f"优化 {len(dish_ids)} 种菜品库存水平",
                confidence=result.confidence,
                source_data={"store_id": store_id, "dish_count": len(dish_ids)},
            )

        except Exception as e:
            logger.error("Inventory optimization failed", store_id=store_id, error=str(e), exc_info=e)
            return self.format_response(
                success=False, data=None, message=f"优化失败: {str(e)}",
                reasoning=f"优化过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )

    async def analyze_waste(
        self,
        store_id: str,
        time_period: str = "7d"
    ) -> AgentResult:
        """分析库存损耗"""
        try:
            user_message = (
                f"分析门店 {store_id} 最近 {time_period} 的库存损耗。"
                f"请查询消耗趋势和临期预警记录，找出损耗率最高的菜品，"
                f"分析损耗原因和趋势变化，给出损耗统计、根本原因、预防措施和预期节省成本。"
            )

            logger.info("Analyzing waste with Tool Use", store_id=store_id, time_period=time_period)

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={"time_period": time_period}
            )

            if not result.success:
                return result

            return self.format_response(
                success=True,
                data={
                    "analysis": result.data,
                    "time_period": time_period,
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                },
                message="损耗分析完成",
                reasoning=result.reasoning or f"分析 {time_period} 内库存损耗",
                confidence=result.confidence,
                source_data={"store_id": store_id, "time_period": time_period},
            )

        except Exception as e:
            logger.error("Waste analysis failed", store_id=store_id, error=str(e), exc_info=e)
            return self.format_response(
                success=False, data=None, message=f"分析失败: {str(e)}",
                reasoning=f"分析过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )

    async def generate_restock_plan(
        self,
        store_id: str,
        target_date: str,
        validation_context: Optional[Dict] = None
    ) -> AgentResult:
        """生成补货计划"""
        try:
            user_message = (
                f"为门店 {store_id} 生成 {target_date} 的补货计划。"
                f"请查询当前库存状态和历史消耗趋势，考虑供应商交货时间，"
                f"给出补货清单（菜品+数量）、补货时间点、优先级排序和成本预估。"
            )

            logger.info("Generating restock plan with Tool Use",
                        store_id=store_id, target_date=target_date)

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={"target_date": target_date}
            )

            if not result.success:
                return result

            # 合规性校验（预算/库存容量/历史消耗/供应商）
            if validation_context:
                decision = {
                    "action": "purchase",
                    **validation_context.get("decision_overrides", {})
                }
                validation = await self.validator.validate_decision(
                    decision=decision,
                    context=validation_context,
                    rules_to_apply=[
                        "budget_check",
                        "inventory_capacity",
                        "historical_consumption",
                        "supplier_availability"
                    ]
                )

                if validation["result"] == ValidationResult.REJECTED.value:
                    return self.format_response(
                        success=False,
                        data={"plan": result.data, "target_date": target_date},
                        message=f"补货计划被合规校验拒绝: {validation['message']}",
                        reasoning=f"LLM 生成了补货计划，但合规校验拒绝: {validation['message']}",
                        confidence=0.0,
                        source_data={"store_id": store_id, "target_date": target_date,
                                     "validation": validation},
                    )

                has_warning = validation["result"] == ValidationResult.WARNING.value
                return self.format_response(
                    success=True,
                    data={
                        "plan": result.data,
                        "target_date": target_date,
                        "tool_calls": len(result.tool_calls),
                        "iterations": result.iterations,
                        "validation": validation,
                    },
                    message="补货计划生成完成" + ("（含合规警告）" if has_warning else ""),
                    reasoning=result.reasoning,
                    confidence=result.confidence,
                    source_data={"store_id": store_id, "target_date": target_date,
                                 "validation": validation},
                )

            return self.format_response(
                success=True,
                data={
                    "plan": result.data,
                    "target_date": target_date,
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                },
                message="补货计划生成完成",
                reasoning=result.reasoning,
                confidence=result.confidence,
                source_data={"store_id": store_id, "target_date": target_date},
            )

        except Exception as e:
            logger.error("Restock plan generation failed", store_id=store_id, error=str(e), exc_info=e)
            return self.format_response(
                success=False, data=None, message=f"生成失败: {str(e)}",
                reasoning=f"生成过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )
