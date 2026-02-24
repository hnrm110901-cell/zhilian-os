"""
ScheduleAgent - 排班优化Agent (RAG增强)
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import os
import structlog

from .llm_agent import LLMEnhancedAgent, AgentResult
from ..services.rag_service import RAGService
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

    RAG增强:
    - 基于历史排班数据
    - 基于历史客流数据
    - 基于员工绩效数据
    """

    def __init__(self):
        super().__init__(agent_type="schedule")
        self.rag_service = RAGService()
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
            AgentResult（含 reasoning / confidence / source_data）
        """
        try:
            query = f"""
            为门店{store_id}优化{date}的排班:
            - 当前排班人数: {current_staff_count}人
            - 预期客流: {expected_customer_flow or '未知'}人

            请基于历史数据分析:
            1. 该日期的客流特征
            2. 建议的排班人数
            3. 各时段人力配置
            4. 注意事项

            给出具体的排班建议。
            """

            logger.info(
                "Optimizing schedule with RAG",
                store_id=store_id,
                date=date,
                current_staff_count=current_staff_count
            )

            rag_result = await self.rag_service.analyze_with_rag(
                query=query,
                store_id=store_id,
                collection="events",
                top_k=int(os.getenv("RAG_SCHEDULE_TOP_K", "10"))
            )

            ctx_count = rag_result["metadata"]["context_count"]

            # 步骤4：合规性校验（人力成本预算）
            validation = None
            if validation_context:
                decision = {"action": "schedule_optimization", **validation_context.get("decision_overrides", {})}
                validation = await self.validator.validate_decision(
                    decision=decision,
                    context=validation_context,
                    rules_to_apply=["budget_check"]
                )
                if validation["result"] == ValidationResult.REJECTED.value:
                    return self.format_response(
                        success=False,
                        data={"optimization": rag_result["response"], "date": date},
                        message="排班方案未通过合规校验",
                        reasoning=f"预算校验拒绝: {validation.get('reason', '')}",
                        confidence=0.0,
                        source_data={"store_id": store_id, "validation": validation},
                    )

            source = {"store_id": store_id, "date": date, "current_staff_count": current_staff_count}
            if validation:
                source["validation"] = validation
            return self.format_response(
                success=True,
                data={
                    "optimization": rag_result["response"],
                    "date": date,
                    "current_staff_count": current_staff_count,
                    "expected_customer_flow": expected_customer_flow,
                    "context_used": ctx_count,
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="排班优化完成" + ("（含合规警告）" if validation and validation["result"] == ValidationResult.WARNING.value else ""),
                reasoning=f"基于 {ctx_count} 条历史数据，为 {date} 优化排班（当前 {current_staff_count} 人）",
                confidence=min(0.9, 0.45 + ctx_count * 0.05),
                source_data=source,
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
            query = f"""
            预测门店{store_id}未来{date_range}的人力需求:
            - 基于历史客流趋势
            - 考虑节假日因素
            - 考虑季节性变化
            - 考虑特殊事件

            请给出:
            1. 每日建议人数
            2. 高峰时段配置
            3. 弹性调整建议
            """

            logger.info("Predicting staffing needs with RAG", store_id=store_id, date_range=date_range)

            rag_result = await self.rag_service.analyze_with_rag(
                query=query, store_id=store_id, collection="events",
                top_k=int(os.getenv("RAG_SCHEDULE_TOP_K", "10"))
            )

            ctx_count = rag_result["metadata"]["context_count"]
            return self.format_response(
                success=True,
                data={
                    "prediction": rag_result["response"],
                    "date_range": date_range,
                    "context_used": ctx_count,
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="人力需求预测完成",
                reasoning=f"基于 {ctx_count} 条历史数据，预测未来 {date_range} 人力需求",
                confidence=min(0.85, 0.4 + ctx_count * 0.05),
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
            query = f"""
            分析门店{store_id}班次{shift_id}的效率:
            - 人均服务客户数
            - 订单处理速度
            - 客户满意度
            - 员工工作负荷

            请基于历史数据给出:
            1. 效率评估
            2. 改进建议
            3. 最佳实践参考
            """

            logger.info("Analyzing shift efficiency with RAG", store_id=store_id, shift_id=shift_id)

            rag_result = await self.rag_service.analyze_with_rag(
                query=query, store_id=store_id, collection="events",
                top_k=int(os.getenv("RAG_SCHEDULE_TOP_K", "10"))
            )

            ctx_count = rag_result["metadata"]["context_count"]
            return self.format_response(
                success=True,
                data={
                    "analysis": rag_result["response"],
                    "shift_id": shift_id,
                    "context_used": ctx_count,
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="班次效率分析完成",
                reasoning=f"基于 {ctx_count} 条历史数据，分析班次 {shift_id} 效率",
                confidence=min(0.9, 0.45 + ctx_count * 0.05),
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
            query = f"""
            为门店{store_id}平衡{len(staff_ids)}名员工的工作量({time_period}):
            - 分析当前工作量分布
            - 识别过载和空闲员工
            - 考虑员工技能和偏好
            - 确保公平性

            请给出:
            1. 当前工作量评估
            2. 调整建议
            3. 预期效果
            """

            logger.info("Balancing workload with RAG", store_id=store_id, staff_count=len(staff_ids), time_period=time_period)

            rag_result = await self.rag_service.analyze_with_rag(
                query=query, store_id=store_id, collection="events",
                top_k=int(os.getenv("RAG_SCHEDULE_TOP_K", "10"))
            )

            ctx_count = rag_result["metadata"]["context_count"]
            return self.format_response(
                success=True,
                data={
                    "balance_plan": rag_result["response"],
                    "staff_count": len(staff_ids),
                    "time_period": time_period,
                    "context_used": ctx_count,
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="工作量平衡完成",
                reasoning=f"基于 {ctx_count} 条历史数据，平衡 {len(staff_ids)} 名员工 {time_period} 工作量",
                confidence=min(0.9, 0.45 + ctx_count * 0.05),
                source_data={"store_id": store_id, "staff_count": len(staff_ids), "time_period": time_period},
            )

        except Exception as e:
            logger.error("Workload balancing failed", store_id=store_id, error=str(e), exc_info=e)
            return self.format_response(
                success=False, data=None, message=f"平衡失败: {str(e)}",
                reasoning=f"平衡过程中发生异常: {str(e)}", confidence=0.0,
                source_data={"store_id": store_id},
            )
