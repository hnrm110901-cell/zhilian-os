"""
KPIAgent - 绩效评估Agent (Claude Tool Use 增强)
"""
from typing import Dict, Any, List, Optional
import structlog

from .llm_agent import LLMEnhancedAgent, AgentResult
from ..services.decision_validator import DecisionValidator, ValidationResult
from ..core.monitoring import error_monitor, ErrorSeverity, ErrorCategory

logger = structlog.get_logger()


class KPIAgent(LLMEnhancedAgent):
    """
    绩效评估Agent

    功能:
    - 门店绩效评估
    - 员工绩效分析
    - 改进计划生成
    - KPI趋势预测

    Tool Use 增强:
    - 基于历史绩效数据
    - 基于行业标准
    - 基于改进案例
    """

    def __init__(self):
        super().__init__(agent_type="kpi")
        self.validator = DecisionValidator()

    async def evaluate_store_performance(
        self,
        store_id: str,
        period: str = "week",
        kpi_types: Optional[List[str]] = None
    ) -> AgentResult:
        """
        评估门店绩效

        Args:
            store_id: 门店ID
            period: 评估周期 (day/week/month/quarter)
            kpi_types: KPI类型列表 (可选，如["revenue", "customer_satisfaction"])

        Returns:
            AgentResult（含 reasoning / confidence / tool_calls）
        """
        try:
            kpi_text = ", ".join(kpi_types) if kpi_types else "全部KPI"

            user_message = (
                f"评估门店 {store_id} 最近 {period} 的绩效（{kpi_text}）："
                f"请查询历史绩效数据，分析营收指标(revenue, growth_rate)、"
                f"运营指标(order_count, avg_order_value)、效率指标(table_turnover, staff_efficiency)、"
                f"质量指标(customer_satisfaction, complaint_rate)，"
                f"给出各项KPI得分和排名、优势和劣势分析、与历史对比及改进建议。"
            )

            logger.info(
                "Evaluating store performance with Tool Use",
                store_id=store_id,
                period=period,
                kpi_types=kpi_types
            )

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={"period": period, "kpi_types": kpi_types}
            )

            if not result.success:
                return result

            return self.format_response(
                success=True,
                data={
                    "evaluation": result.data,
                    "period": period,
                    "kpi_types": kpi_types,
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                },
                message="门店绩效评估完成",
                reasoning=result.reasoning or f"评估 {period} 周期内 {kpi_text}",
                confidence=result.confidence,
                source_data={"store_id": store_id, "period": period, "kpi_types": kpi_types},
            )

        except Exception as e:
            logger.error("Store performance evaluation failed", store_id=store_id, error=str(e), exc_info=e)
            error_monitor.log_error(
                message=f"Store performance evaluation failed for {store_id}",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.AGENT,
                exception=e,
                context={"store_id": store_id, "period": period}
            )
            return self.format_response(
                success=False, data=None, message=f"评估失败: {str(e)}",
                reasoning=f"评估过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )

    async def analyze_staff_performance(
        self,
        store_id: str,
        staff_id: Optional[str] = None,
        period: str = "month"
    ) -> AgentResult:
        """分析员工绩效"""
        try:
            if staff_id:
                user_message = (
                    f"分析门店 {store_id} 员工 {staff_id} 最近 {period} 的绩效："
                    f"请查询该员工历史数据，分析工作量指标(服务客户数/订单处理数)、"
                    f"质量指标(客户满意度/差评率)、效率指标(平均服务时间/错误率)、"
                    f"态度指标(出勤率/主动性)，给出绩效评分、优势和待改进点、与团队平均对比及发展建议。"
                )
            else:
                user_message = (
                    f"分析门店 {store_id} 全体员工最近 {period} 的绩效："
                    f"请查询团队历史数据，分析团队整体表现、绩效分布情况、优秀员工识别、待提升员工识别，"
                    f"给出团队绩效概况、绩效差异分析、激励建议和培训需求。"
                )

            logger.info("Analyzing staff performance with Tool Use",
                        store_id=store_id, staff_id=staff_id, period=period)

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={"staff_id": staff_id, "period": period}
            )

            if not result.success:
                return result

            scope = f"员工 {staff_id}" if staff_id else "全体员工"
            return self.format_response(
                success=True,
                data={
                    "analysis": result.data,
                    "staff_id": staff_id,
                    "period": period,
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                },
                message="员工绩效分析完成",
                reasoning=result.reasoning or f"分析 {scope} {period} 绩效",
                confidence=result.confidence,
                source_data={"store_id": store_id, "staff_id": staff_id, "period": period},
            )

        except Exception as e:
            logger.error("Staff performance analysis failed",
                         store_id=store_id, staff_id=staff_id, error=str(e), exc_info=e)
            return self.format_response(
                success=False, data=None, message=f"分析失败: {str(e)}",
                reasoning=f"分析过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )

    async def generate_improvement_plan(
        self,
        store_id: str,
        kpi_type: str,
        target_value: Optional[float] = None,
        validation_context: Optional[Dict] = None
    ) -> AgentResult:
        """生成改进计划"""
        try:
            target_text = f"目标值 {target_value}" if target_value else "提升目标"

            user_message = (
                f"为门店 {store_id} 生成 {kpi_type} 的改进计划（{target_text}）："
                f"请查询历史成功案例，分析当前状态、差距识别、根本原因，"
                f"给出具体改进措施（优先级排序）、实施步骤和时间表、资源需求、预期效果和风险。"
            )

            logger.info("Generating improvement plan with Tool Use",
                        store_id=store_id, kpi_type=kpi_type)

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={"kpi_type": kpi_type, "target_value": target_value}
            )

            if not result.success:
                return result

            # 合规性校验（预算）
            validation = None
            if validation_context:
                decision = {"action": "improvement_plan", **validation_context.get("decision_overrides", {})}
                validation = await self.validator.validate_decision(
                    decision=decision,
                    context=validation_context,
                    rules_to_apply=["budget_check"]
                )
                if validation["result"] == ValidationResult.REJECTED.value:
                    return self.format_response(
                        success=False,
                        data={"plan": result.data, "kpi_type": kpi_type},
                        message="改进计划未通过合规校验",
                        reasoning=f"预算校验拒绝: {validation.get('reason', '')}",
                        confidence=0.0,
                        source_data={"store_id": store_id, "validation": validation},
                    )

            source = {"store_id": store_id, "kpi_type": kpi_type, "target_value": target_value}
            if validation:
                source["validation"] = validation

            has_warning = validation and validation["result"] == ValidationResult.WARNING.value
            return self.format_response(
                success=True,
                data={
                    "plan": result.data,
                    "kpi_type": kpi_type,
                    "target_value": target_value,
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                    **({"validation": validation} if validation else {}),
                },
                message="改进计划生成完成" + ("（含合规警告）" if has_warning else ""),
                reasoning=result.reasoning or f"为 {kpi_type} 生成改进计划（{target_text}）",
                confidence=result.confidence,
                source_data=source,
            )

        except Exception as e:
            logger.error("Improvement plan generation failed",
                         store_id=store_id, kpi_type=kpi_type, error=str(e), exc_info=e)
            return self.format_response(
                success=False, data=None, message=f"生成失败: {str(e)}",
                reasoning=f"生成过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )

    async def predict_kpi_trend(
        self,
        store_id: str,
        kpi_name: str,
        time_range: str = "30d"
    ) -> AgentResult:
        """预测KPI趋势"""
        try:
            user_message = (
                f"预测门店 {store_id} 的 {kpi_name} 未来 {time_range} 的趋势："
                f"请查询历史数据，基于历史趋势、季节性因素、外部影响因素和已实施的改进措施，"
                f"给出趋势预测（上升/下降/稳定）、预测值和置信区间、影响因素分析及风险提示和建议。"
            )

            logger.info("Predicting KPI trend with Tool Use",
                        store_id=store_id, kpi_name=kpi_name, time_range=time_range)

            result = await self.execute_with_tools(
                user_message=user_message,
                store_id=store_id,
                context={"kpi_name": kpi_name, "time_range": time_range}
            )

            if not result.success:
                return result

            return self.format_response(
                success=True,
                data={
                    "prediction": result.data,
                    "kpi_name": kpi_name,
                    "time_range": time_range,
                    "tool_calls": len(result.tool_calls),
                    "iterations": result.iterations,
                },
                message="KPI趋势预测完成",
                reasoning=result.reasoning or f"预测 {kpi_name} 未来 {time_range} 趋势",
                confidence=result.confidence,
                source_data={"store_id": store_id, "kpi_name": kpi_name, "time_range": time_range},
            )

        except Exception as e:
            logger.error("KPI trend prediction failed",
                         store_id=store_id, kpi_name=kpi_name, error=str(e), exc_info=e)
            return self.format_response(
                success=False, data=None, message=f"预测失败: {str(e)}",
                reasoning=f"预测过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )
