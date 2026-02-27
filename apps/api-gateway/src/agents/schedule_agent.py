"""
ScheduleAgent - 排班优化Agent (Claude Tool Use 增强)
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import structlog

from .llm_agent import LLMEnhancedAgent, AgentResult
from ..services.decision_validator import DecisionValidator, ValidationResult
from ..core.monitoring import error_monitor, ErrorSeverity, ErrorCategory

logger = structlog.get_logger()


class ScheduleAgent(LLMEnhancedAgent):
    """
    排班优化Agent

    功能:
    - 智能排班建议
    - 人力需求预测
    - 班次优化
    - 员工工作量平衡

    Tool Use 增强:
    - query_staff_availability: 查询员工可用性
    - get_customer_flow_forecast: 获取客流预测
    - get_historical_schedule: 获取历史排班
    - create_schedule_recommendation: 生成排班建议
    """

    def __init__(self):
        super().__init__(agent_type="schedule")
        self.validator = DecisionValidator()

    async def optimize_schedule(
        self,
        store_id: str,
        date: str,
        current_staff_count: int,
        expected_customer_flow: Optional[int] = None,
        validation_context: Optional[Dict] = None
    ) -> AgentResult:
        """
        优化排班

        Args:
            store_id: 门店ID
            date: 日期
            current_staff_count: 当前排班人数
            expected_customer_flow: 预期客流
            validation_context: 合规校验上下文（可选）

        Returns:
            AgentResult（含 reasoning / confidence / tool_calls）
        """
        try:
            user_message = (
                f"为门店 {store_id} 优化 {date} 的排班方案。"
                f"当前排班人数：{current_staff_count} 人，"
                f"预期客流：{expected_customer_flow or '未知'} 人。"
                f"请先查询员工可用性和客流预测，再参考历史排班数据，"
                f"最终给出各时段人力配置建议和注意事项。"
            )

            logger.info(
                "Optimizing schedule with Tool Use",
                store_id=store_id,
                date=date,
                current_staff_count=current_staff_count
            )

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={"date": date, "current_staff_count": current_staff_count,
                         "expected_customer_flow": expected_customer_flow}
            )

            if not result.success:
                return result

            # 合规性校验（人力成本预算）
            if validation_context:
                decision = {
                    "action": "schedule_optimization",
                    **validation_context.get("decision_overrides", {})
                }
                validation = await self.validator.validate_decision(
                    decision=decision,
                    context=validation_context,
                    rules_to_apply=["budget_check"]
                )

                if validation["result"] == ValidationResult.REJECTED.value:
                    return self.format_response(
                        success=False,
                        data={"optimization": result.data, "date": date},
                        message="排班方案未通过合规校验",
                        reasoning=f"预算校验拒绝: {validation.get('reason', '')}",
                        confidence=0.0,
                        source_data={"store_id": store_id, "validation": validation},
                    )

                has_warning = validation["result"] == ValidationResult.WARNING.value
                return self.format_response(
                    success=True,
                    data={
                        "optimization": result.data,
                        "date": date,
                        "current_staff_count": current_staff_count,
                        "expected_customer_flow": expected_customer_flow,
                        "tool_calls": len(result.tool_calls),
                        "iterations": result.iterations,
                        "validation": validation,
                    },
                    message="排班优化完成" + ("（含合规警告）" if has_warning else ""),
                    reasoning=result.reasoning,
                    confidence=result.confidence,
                    source_data={"store_id": store_id, "date": date,
                                 "current_staff_count": current_staff_count,
                                 "validation": validation},
                )

            return self.format_response(
                success=True,
                data={
                    "optimization": result.data,
                    "date": date,
                    "current_staff_count": current_staff_count,
                    "expected_customer_flow": expected_customer_flow,
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                },
                message="排班优化完成",
                reasoning=result.reasoning,
                confidence=result.confidence,
                source_data={"store_id": store_id, "date": date,
                             "current_staff_count": current_staff_count},
            )

        except Exception as e:
            logger.error("Schedule optimization failed", store_id=store_id, error=str(e), exc_info=e)
            error_monitor.log_error(
                message=f"Schedule optimization failed for {store_id}",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.AGENT,
                exception=e,
                context={"store_id": store_id, "date": date}
            )
            return self.format_response(
                success=False, data=None, message=f"优化失败: {str(e)}",
                reasoning=f"优化过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )

    async def predict_staffing_needs(
        self,
        store_id: str,
        date_range: str = "7d"
    ) -> AgentResult:
        """预测人力需求"""
        try:
            user_message = (
                f"预测门店 {store_id} 未来 {date_range} 的人力需求。"
                f"请查询历史客流趋势，考虑节假日、季节性和特殊事件因素，"
                f"给出每日建议人数、高峰时段配置和弹性调整建议。"
            )

            logger.info("Predicting staffing needs with Tool Use",
                        store_id=store_id, date_range=date_range)

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={"date_range": date_range}
            )

            if not result.success:
                return result

            return self.format_response(
                success=True,
                data={
                    "prediction": result.data,
                    "date_range": date_range,
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                },
                message="人力需求预测完成",
                reasoning=result.reasoning,
                confidence=result.confidence,
                source_data={"store_id": store_id, "date_range": date_range},
            )

        except Exception as e:
            logger.error("Staffing needs prediction failed", store_id=store_id, error=str(e), exc_info=e)
            return self.format_response(
                success=False, data=None, message=f"预测失败: {str(e)}",
                reasoning=f"预测过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )

    async def analyze_shift_efficiency(
        self,
        store_id: str,
        shift_id: str
    ) -> AgentResult:
        """分析班次效率"""
        try:
            user_message = (
                f"分析门店 {store_id} 班次 {shift_id} 的效率。"
                f"请查询该班次的历史数据，评估人均服务客户数、订单处理速度、"
                f"客户满意度和员工工作负荷，给出效率评估、改进建议和最佳实践参考。"
            )

            logger.info("Analyzing shift efficiency with Tool Use",
                        store_id=store_id, shift_id=shift_id)

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={"shift_id": shift_id}
            )

            if not result.success:
                return result

            return self.format_response(
                success=True,
                data={
                    "analysis": result.data,
                    "shift_id": shift_id,
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                },
                message="班次效率分析完成",
                reasoning=result.reasoning,
                confidence=result.confidence,
                source_data={"store_id": store_id, "shift_id": shift_id},
            )

        except Exception as e:
            logger.error("Shift efficiency analysis failed", store_id=store_id, error=str(e), exc_info=e)
            return self.format_response(
                success=False, data=None, message=f"分析失败: {str(e)}",
                reasoning=f"分析过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )

    async def balance_workload(
        self,
        store_id: str,
        staff_ids: List[str],
        time_period: str = "week"
    ) -> AgentResult:
        """平衡员工工作量"""
        try:
            user_message = (
                f"为门店 {store_id} 平衡 {len(staff_ids)} 名员工（{', '.join(staff_ids[:5])}{'...' if len(staff_ids) > 5 else ''}）"
                f"的 {time_period} 工作量。"
                f"请查询员工可用性和历史排班，分析当前工作量分布，"
                f"识别过载和空闲员工，考虑技能和偏好，给出公平的调整建议和预期效果。"
            )

            logger.info("Balancing workload with Tool Use",
                        store_id=store_id, staff_count=len(staff_ids), time_period=time_period)

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={"staff_ids": staff_ids, "time_period": time_period}
            )

            if not result.success:
                return result

            return self.format_response(
                success=True,
                data={
                    "balance_plan": result.data,
                    "staff_count": len(staff_ids),
                    "time_period": time_period,
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                },
                message="工作量平衡完成",
                reasoning=result.reasoning,
                confidence=result.confidence,
                source_data={"store_id": store_id, "staff_count": len(staff_ids),
                             "time_period": time_period},
            )

        except Exception as e:
            logger.error("Workload balancing failed", store_id=store_id, error=str(e), exc_info=e)
            return self.format_response(
                success=False, data=None, message=f"平衡失败: {str(e)}",
                reasoning=f"平衡过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )
