"""
InventoryAgent - 库存管理Agent (RAG增强)
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import structlog

from .llm_agent import LLMEnhancedAgent
from ..services.rag_service import RAGService
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

    RAG增强:
    - 基于历史库存数据
    - 基于历史销售数据
    - 基于历史损耗记录
    """

    def __init__(self):
        super().__init__(agent_type="inventory")
        self.rag_service = RAGService()

    async def predict_inventory_needs(
        self,
        store_id: str,
        dish_id: str,
        time_range: str = "3d"
    ) -> Dict[str, Any]:
        """
        预测库存需求

        Args:
            store_id: 门店ID
            dish_id: 菜品ID
            time_range: 预测时间范围

        Returns:
            库存需求预测
        """
        try:
            query = f"""
            预测门店{store_id}菜品{dish_id}未来{time_range}的库存需求:
            - 基于历史销售趋势
            - 考虑季节性因素
            - 考虑节假日影响
            - 考虑促销活动

            请给出:
            1. 预计销量
            2. 建议库存量
            3. 补货时间点
            4. 风险提示
            """

            logger.info(
                "Predicting inventory needs with RAG",
                store_id=store_id,
                dish_id=dish_id,
                time_range=time_range
            )

            # 使用RAG检索历史销售和库存数据
            rag_result = await self.rag_service.analyze_with_rag(
                query=query,
                store_id=store_id,
                collection="orders",
                top_k=12
            )

            return self.format_response(
                success=True,
                data={
                    "prediction": rag_result["response"],
                    "dish_id": dish_id,
                    "time_range": time_range,
                    "context_used": rag_result["metadata"]["context_count"],
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="库存需求预测完成"
            )

        except Exception as e:
            logger.error(
                "Inventory needs prediction failed",
                store_id=store_id,
                dish_id=dish_id,
                error=str(e),
                exc_info=e
            )

            error_monitor.log_error(
                message=f"Inventory needs prediction failed for {store_id}",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.AGENT,
                exception=e,
                context={"store_id": store_id, "dish_id": dish_id}
            )

            return self.format_response(
                success=False,
                data=None,
                message=f"预测失败: {str(e)}"
            )

    async def check_low_stock_alert(
        self,
        store_id: str,
        current_inventory: Dict[str, int],
        threshold_hours: int = 4
    ) -> Dict[str, Any]:
        """
        检查低库存预警

        Args:
            store_id: 门店ID
            current_inventory: 当前库存 {dish_id: quantity}
            threshold_hours: 预警阈值(小时)

        Returns:
            低库存预警结果
        """
        try:
            inventory_summary = "\n".join([
                f"- {dish_id}: {qty}份"
                for dish_id, qty in current_inventory.items()
            ])

            query = f"""
            门店{store_id}当前库存状态:
            {inventory_summary}

            请分析:
            1. 哪些菜品可能在{threshold_hours}小时内售罄
            2. 基于历史销售速度预测
            3. 考虑即将到来的高峰时段
            4. 给出紧急补货建议

            请标注风险等级(高/中/低)。
            """

            logger.info(
                "Checking low stock alert with RAG",
                store_id=store_id,
                inventory_count=len(current_inventory),
                threshold_hours=threshold_hours
            )

            # 使用RAG检索历史销售速度数据
            rag_result = await self.rag_service.analyze_with_rag(
                query=query,
                store_id=store_id,
                collection="orders",
                top_k=10
            )

            return self.format_response(
                success=True,
                data={
                    "alert": rag_result["response"],
                    "inventory_count": len(current_inventory),
                    "threshold_hours": threshold_hours,
                    "context_used": rag_result["metadata"]["context_count"],
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="低库存检查完成"
            )

        except Exception as e:
            logger.error(
                "Low stock alert check failed",
                store_id=store_id,
                error=str(e),
                exc_info=e
            )

            return self.format_response(
                success=False,
                data=None,
                message=f"检查失败: {str(e)}"
            )

    async def optimize_inventory_levels(
        self,
        store_id: str,
        dish_ids: List[str]
    ) -> Dict[str, Any]:
        """
        优化库存水平

        Args:
            store_id: 门店ID
            dish_ids: 菜品ID列表

        Returns:
            库存优化建议
        """
        try:
            dishes_text = ", ".join(dish_ids)

            query = f"""
            优化门店{store_id}以下菜品的库存水平:
            {dishes_text}

            请基于历史数据分析:
            1. 各菜品的最优库存量
            2. 安全库存水平
            3. 补货频率建议
            4. 库存周转率优化

            目标: 减少损耗，提高周转率。
            """

            logger.info(
                "Optimizing inventory levels with RAG",
                store_id=store_id,
                dish_count=len(dish_ids)
            )

            # 使用RAG检索历史库存和销售数据
            rag_result = await self.rag_service.analyze_with_rag(
                query=query,
                store_id=store_id,
                collection="orders",
                top_k=15
            )

            return self.format_response(
                success=True,
                data={
                    "optimization": rag_result["response"],
                    "dish_count": len(dish_ids),
                    "context_used": rag_result["metadata"]["context_count"],
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="库存优化完成"
            )

        except Exception as e:
            logger.error(
                "Inventory optimization failed",
                store_id=store_id,
                error=str(e),
                exc_info=e
            )

            return self.format_response(
                success=False,
                data=None,
                message=f"优化失败: {str(e)}"
            )

    async def analyze_waste(
        self,
        store_id: str,
        time_period: str = "7d"
    ) -> Dict[str, Any]:
        """
        分析库存损耗

        Args:
            store_id: 门店ID
            time_period: 分析周期

        Returns:
            损耗分析结果
        """
        try:
            query = f"""
            分析门店{store_id}最近{time_period}的库存损耗:
            - 损耗率最高的菜品
            - 损耗原因分析
            - 损耗趋势变化
            - 改进建议

            请基于历史数据给出:
            1. 损耗统计
            2. 根本原因
            3. 预防措施
            4. 预期节省成本
            """

            logger.info(
                "Analyzing waste with RAG",
                store_id=store_id,
                time_period=time_period
            )

            # 使用RAG检索历史损耗记录
            rag_result = await self.rag_service.analyze_with_rag(
                query=query,
                store_id=store_id,
                collection="events",
                top_k=10
            )

            return self.format_response(
                success=True,
                data={
                    "analysis": rag_result["response"],
                    "time_period": time_period,
                    "context_used": rag_result["metadata"]["context_count"],
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="损耗分析完成"
            )

        except Exception as e:
            logger.error(
                "Waste analysis failed",
                store_id=store_id,
                error=str(e),
                exc_info=e
            )

            return self.format_response(
                success=False,
                data=None,
                message=f"分析失败: {str(e)}"
            )

    async def generate_restock_plan(
        self,
        store_id: str,
        target_date: str
    ) -> Dict[str, Any]:
        """
        生成补货计划

        Args:
            store_id: 门店ID
            target_date: 目标日期

        Returns:
            补货计划
        """
        try:
            query = f"""
            为门店{store_id}生成{target_date}的补货计划:
            - 基于历史销售数据
            - 考虑当前库存水平
            - 考虑供应商交货时间
            - 优化补货批次

            请给出:
            1. 补货清单(菜品+数量)
            2. 补货时间点
            3. 优先级排序
            4. 成本预估
            """

            logger.info(
                "Generating restock plan with RAG",
                store_id=store_id,
                target_date=target_date
            )

            # 使用RAG检索历史补货和销售数据
            rag_result = await self.rag_service.analyze_with_rag(
                query=query,
                store_id=store_id,
                collection="orders",
                top_k=12
            )

            return self.format_response(
                success=True,
                data={
                    "plan": rag_result["response"],
                    "target_date": target_date,
                    "context_used": rag_result["metadata"]["context_count"],
                    "timestamp": rag_result["metadata"]["timestamp"]
                },
                message="补货计划生成完成"
            )

        except Exception as e:
            logger.error(
                "Restock plan generation failed",
                store_id=store_id,
                error=str(e),
                exc_info=e
            )

            return self.format_response(
                success=False,
                data=None,
                message=f"生成失败: {str(e)}"
            )
