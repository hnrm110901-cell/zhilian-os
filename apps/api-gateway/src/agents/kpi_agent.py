"""
KPIAgent - 绩效评估Agent (RAG增强)
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import structlog

from .llm_agent import LLMEnhancedAgent
from ..services.rag_service import RAGService
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

    RAG增强:
    - 基于历史绩效数据
    - 基于行业标准
    - 基于改进案例
    """

    def __init__(self):
        super().__init__(agent_type="kpi")
        self.rag_service = RAGService()

    async def evaluate_store_performance(
        self,
        store_id: str,
        period: str = "week",
        kpi_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        评估门店绩效

        Args:
            store_id: 门店ID
            period: 评估周期 (day/week/month/quarter)
            kpi_types: KPI类型列表 (可选，如["revenue", "customer_satisfaction"])

        Returns:
            绩效评估结果
        """
        try:
            kpi_text = ", ".join(kpi_types) if kpi_types else "全部KPI"

            query = f"""
            评估门店{store_id}最近{period}的绩效({kpi_text}):
            - 营收指标(revenue, growth_rate)
            - 运营指标(order_count, avg_order_value)
            - 效率指标(table_turnover, staff_efficiency)
            - 质量指标(customer_satisfaction, complaint_rate)

            请基于历史数据和行业标准给出:
            1. 各项KPI得分和排名
            2. 优势和劣势分析
            3. 与历史对比
            4. 改进建议
            """

            logger.info(
                "Evaluating store performance with RAG",
                store_id=store_id,
                period=period,
                kpi_types=kpi_types
            )

            # 使用RAG检索历史绩效数据
            rag_result = await self.rag_service.analyze_with_rag(
                query=query,
                store_id=store_id,
                collection="events",
                top_k=15
            )

            return self.format_response(
                success=True,
                data={
                    "evaluation": rag_result["response"],
                    "period": period,
                    "kpi_types": kpi_types,
                    "context_used": rag_result["metadata"]["context_count"],
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="门店绩效评估完成"
            )

        except Exception as e:
            logger.error(
                "Store performance evaluation failed",
                store_id=store_id,
                error=str(e),
                exc_info=e
            )

            error_monitor.log_error(
                message=f"Store performance evaluation failed for {store_id}",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.AGENT,
                exception=e,
                context={"store_id": store_id, "period": period}
            )

            return self.format_response(
                success=False,
                data=None,
                message=f"评估失败: {str(e)}"
            )

    async def analyze_staff_performance(
        self,
        store_id: str,
        staff_id: Optional[str] = None,
        period: str = "month"
    ) -> Dict[str, Any]:
        """
        分析员工绩效

        Args:
            store_id: 门店ID
            staff_id: 员工ID (可选，分析特定员工)
            period: 评估周期

        Returns:
            员工绩效分析结果
        """
        try:
            if staff_id:
                query = f"""
                分析门店{store_id}员工{staff_id}最近{period}的绩效:
                - 工作量指标(服务客户数, 订单处理数)
                - 质量指标(客户满意度, 差评率)
                - 效率指标(平均服务时间, 错误率)
                - 态度指标(出勤率, 主动性)

                请基于历史数据给出:
                1. 绩效评分
                2. 优势和待改进点
                3. 与团队平均对比
                4. 发展建议
                """
            else:
                query = f"""
                分析门店{store_id}全体员工最近{period}的绩效:
                - 团队整体表现
                - 绩效分布情况
                - 优秀员工识别
                - 待提升员工识别

                请给出:
                1. 团队绩效概况
                2. 绩效差异分析
                3. 激励建议
                4. 培训需求
                """

            logger.info(
                "Analyzing staff performance with RAG",
                store_id=store_id,
                staff_id=staff_id,
                period=period
            )

            # 使用RAG检索历史员工绩效数据
            rag_result = await self.rag_service.analyze_with_rag(
                query=query,
                store_id=store_id,
                collection="events",
                top_k=12
            )

            return self.format_response(
                success=True,
                data={
                    "analysis": rag_result["response"],
                    "staff_id": staff_id,
                    "period": period,
                    "context_used": rag_result["metadata"]["context_count"],
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="员工绩效分析完成"
            )

        except Exception as e:
            logger.error(
                "Staff performance analysis failed",
                store_id=store_id,
                staff_id=staff_id,
                error=str(e),
                exc_info=e
            )

            return self.format_response(
                success=False,
                data=None,
                message=f"分析失败: {str(e)}"
            )

    async def generate_improvement_plan(
        self,
        store_id: str,
        kpi_type: str,
        target_value: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        生成改进计划

        Args:
            store_id: 门店ID
            kpi_type: KPI类型 (如"revenue", "customer_satisfaction")
            target_value: 目标值 (可选)

        Returns:
            改进计划
        """
        try:
            target_text = f"目标值{target_value}" if target_value else "提升目标"

            query = f"""
            为门店{store_id}生成{kpi_type}的改进计划({target_text}):
            - 当前状态分析
            - 差距识别
            - 根本原因分析
            - 改进措施

            请基于历史成功案例给出:
            1. 具体改进措施(优先级排序)
            2. 实施步骤和时间表
            3. 资源需求
            4. 预期效果和风险
            """

            logger.info(
                "Generating improvement plan with RAG",
                store_id=store_id,
                kpi_type=kpi_type,
                target_value=target_value
            )

            # 使用RAG检索历史改进案例
            rag_result = await self.rag_service.analyze_with_rag(
                query=query,
                store_id=store_id,
                collection="events",
                top_k=10
            )

            return self.format_response(
                success=True,
                data={
                    "plan": rag_result["response"],
                    "kpi_type": kpi_type,
                    "target_value": target_value,
                    "context_used": rag_result["metadata"]["context_count"],
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="改进计划生成完成"
            )

        except Exception as e:
            logger.error(
                "Improvement plan generation failed",
                store_id=store_id,
                kpi_type=kpi_type,
                error=str(e),
                exc_info=e
            )

            return self.format_response(
                success=False,
                data=None,
                message=f"生成失败: {str(e)}"
            )

    async def predict_kpi_trend(
        self,
        store_id: str,
        kpi_name: str,
        time_range: str = "30d"
    ) -> Dict[str, Any]:
        """
        预测KPI趋势

        Args:
            store_id: 门店ID
            kpi_name: KPI名称
            time_range: 预测范围

        Returns:
            KPI趋势预测
        """
        try:
            query = f"""
            预测门店{store_id}的{kpi_name}未来{time_range}的趋势:
            - 基于历史趋势分析
            - 考虑季节性因素
            - 考虑外部影响因素
            - 考虑已实施的改进措施

            请给出:
            1. 趋势预测(上升/下降/稳定)
            2. 预测值和置信区间
            3. 影响因素分析
            4. 风险提示和建议
            """

            logger.info(
                "Predicting KPI trend with RAG",
                store_id=store_id,
                kpi_name=kpi_name,
                time_range=time_range
            )

            # 使用RAG检索历史KPI数据
            rag_result = await self.rag_service.analyze_with_rag(
                query=query,
                store_id=store_id,
                collection="events",
                top_k=15
            )

            return self.format_response(
                success=True,
                data={
                    "prediction": rag_result["response"],
                    "kpi_name": kpi_name,
                    "time_range": time_range,
                    "context_used": rag_result["metadata"]["context_count"],
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="KPI趋势预测完成"
            )

        except Exception as e:
            logger.error(
                "KPI trend prediction failed",
                store_id=store_id,
                kpi_name=kpi_name,
                error=str(e),
                exc_info=e
            )

            return self.format_response(
                success=False,
                data=None,
                message=f"预测失败: {str(e)}"
            )
