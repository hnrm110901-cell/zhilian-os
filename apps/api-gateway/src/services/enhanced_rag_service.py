"""
RAG增强服务 - 集成行业基线数据
解决AI冷启动问题
"""
from typing import Dict, List, Optional, Any
import structlog
import os

from src.services.baseline_data_service import BaselineDataService

logger = structlog.get_logger()


class EnhancedRAGService:
    """
    增强的RAG服务
    自动判断数据充足性，在数据不足时使用行业基线
    """

    # 数据充足性阈值（支持环境变量覆盖）
    DATA_SUFFICIENCY_THRESHOLDS = {
        "orders": int(os.getenv("RAG_MIN_ORDERS", "100")),
        "days": int(os.getenv("RAG_MIN_DAYS", "30")),
        "inventory_records": int(os.getenv("RAG_MIN_INVENTORY_RECORDS", "50")),
        "reservations": int(os.getenv("RAG_MIN_RESERVATIONS", "30")),
    }

    def __init__(self, store_id: str, restaurant_type: str = "正餐"):
        self.store_id = store_id
        self.restaurant_type = restaurant_type
        self.baseline_service = BaselineDataService(store_id, restaurant_type)
        logger.info(
            "EnhancedRAGService initialized",
            store_id=store_id,
            restaurant_type=restaurant_type,
        )

    async def query(
        self,
        query_text: str,
        query_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        执行增强的RAG查询

        Args:
            query_text: 查询文本
            query_type: 查询类型
            context: 上下文信息

        Returns:
            查询结果，包含数据来源标识
        """
        context = context or {}

        # 1. 检查数据充足性
        data_sufficiency = await self._check_data_sufficiency(query_type)

        # 2. 如果数据充足，使用客户自己的数据
        if data_sufficiency["is_sufficient"]:
            return await self._query_with_customer_data(
                query_text, query_type, context, data_sufficiency
            )

        # 3. 如果数据不足，使用行业基线数据
        return await self._query_with_baseline_data(
            query_text, query_type, context, data_sufficiency
        )

    async def _check_data_sufficiency(self, query_type: str) -> Dict[str, Any]:
        """
        检查特定查询类型的数据充足性

        Args:
            query_type: 查询类型

        Returns:
            数据充足性评估结果
        """
        from sqlalchemy import select, func
        from src.core.database import get_db_session
        from src.models.order import Order
        from src.models.daily_report import DailyReport
        from src.models.inventory import InventoryItem
        from src.models.reservation import Reservation

        async with get_db_session() as session:
            orders_result = await session.execute(
                select(func.count(Order.id)).where(Order.store_id == self.store_id)
            )
            days_result = await session.execute(
                select(func.count(func.distinct(DailyReport.report_date))).where(
                    DailyReport.store_id == self.store_id
                )
            )
            inventory_result = await session.execute(
                select(func.count(InventoryItem.id)).where(
                    InventoryItem.store_id == self.store_id
                )
            )
            reservation_result = await session.execute(
                select(func.count(Reservation.id)).where(
                    Reservation.store_id == self.store_id
                )
            )

        data_counts = {
            "orders": int(orders_result.scalar() or 0),
            "days": int(days_result.scalar() or 0),
            "inventory_records": int(inventory_result.scalar() or 0),
            "reservations": int(reservation_result.scalar() or 0),
        }

        missing_data = [
            {
                "dimension": key,
                "current": data_counts.get(key, 0),
                "required": threshold,
                "gap": threshold - data_counts.get(key, 0),
            }
            for key, threshold in self.DATA_SUFFICIENCY_THRESHOLDS.items()
            if data_counts.get(key, 0) < threshold
        ]

        sufficiency = {
            "query_type": query_type,
            "store_id": self.store_id,
            "data_counts": data_counts,
            "thresholds": self.DATA_SUFFICIENCY_THRESHOLDS,
            "is_sufficient": len(missing_data) == 0,
            "missing_data": missing_data,
        }

        logger.info(
            "Data sufficiency checked",
            store_id=self.store_id,
            query_type=query_type,
            is_sufficient=sufficiency["is_sufficient"],
            missing_count=len(sufficiency["missing_data"]),
        )

        return sufficiency

    async def _query_with_customer_data(
        self,
        query_text: str,
        query_type: str,
        context: Dict[str, Any],
        data_sufficiency: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        使用客户自己的数据进行查询

        Args:
            query_text: 查询文本
            query_type: 查询类型
            context: 上下文信息
            data_sufficiency: 数据充足性评估

        Returns:
            查询结果
        """
        # 根据query_type从数据库检索相关数据作为上下文
        from src.core.database import get_db_session
        from src.models.order import Order, OrderStatus
        from src.models.daily_report import DailyReport
        from src.models.inventory import InventoryItem
        from sqlalchemy import select, func
        from datetime import date, timedelta

        logger.info(
            "Querying with customer data",
            store_id=self.store_id,
            query_type=query_type,
            data_source="customer_data",
        )

        retrieved_docs = []
        answer_data = {}

        async with get_db_session() as session:
            if query_type in ("revenue", "sales", "营收", "销售"):
                # 查询最近30天营收数据
                cutoff = date.today() - timedelta(days=int(os.getenv("RAG_DATA_DAYS", "30")))
                result = await session.execute(
                    select(
                        func.sum(DailyReport.total_revenue).label("total"),
                        func.avg(DailyReport.total_revenue).label("avg_daily"),
                        func.sum(DailyReport.customer_count).label("customers"),
                        func.count(DailyReport.id).label("days"),
                    ).where(
                        DailyReport.store_id == self.store_id,
                        DailyReport.report_date >= cutoff,
                    )
                )
                row = result.one()
                answer_data = {
                    "period": "最近30天",
                    "total_revenue_fen": row.total or 0,
                    "avg_daily_revenue_fen": int(row.avg_daily or 0),
                    "total_customers": row.customers or 0,
                    "data_days": row.days or 0,
                }
                retrieved_docs = [{"type": "daily_report", "days": row.days or 0}]

            elif query_type in ("inventory", "库存"):
                result = await session.execute(
                    select(
                        func.count(InventoryItem.id).label("total"),
                        func.count(InventoryItem.id).filter(
                            InventoryItem.current_quantity <= InventoryItem.min_quantity
                        ).label("low_stock"),
                    ).where(InventoryItem.store_id == self.store_id)
                )
                row = result.one()
                answer_data = {
                    "total_items": row.total or 0,
                    "low_stock_items": row.low_stock or 0,
                }
                retrieved_docs = [{"type": "inventory", "items": row.total or 0}]

            else:
                # 通用：查询最近订单统计
                result = await session.execute(
                    select(
                        func.count(Order.id).label("count"),
                        func.sum(Order.total_amount).label("revenue"),
                    ).where(
                        Order.store_id == self.store_id,
                        Order.status == OrderStatus.COMPLETED,
                    )
                )
                row = result.one()
                answer_data = {
                    "total_orders": row.count or 0,
                    "total_revenue_fen": int(row.revenue or 0),
                }
                retrieved_docs = [{"type": "orders", "count": row.count or 0}]

        return {
            "answer": answer_data,
            "data_source": "customer_data",
            "confidence": "high",
            "data_sufficiency": data_sufficiency,
            "retrieved_documents": retrieved_docs,
            "note": "此建议基于您门店的实际运营数据，具有较高的准确性。",
        }

    async def _query_with_baseline_data(
        self,
        query_text: str,
        query_type: str,
        context: Dict[str, Any],
        data_sufficiency: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        使用行业基线数据进行查询

        Args:
            query_text: 查询文本
            query_type: 查询类型
            context: 上下文信息
            data_sufficiency: 数据充足性评估

        Returns:
            查询结果
        """
        logger.info(
            "Querying with baseline data",
            store_id=self.store_id,
            query_type=query_type,
            data_source="industry_baseline",
        )

        # 使用基线数据服务生成建议
        baseline_recommendation = self.baseline_service.get_baseline_recommendation(
            query_type, context
        )

        return {
            "answer": baseline_recommendation["recommendation"],
            "data_source": "industry_baseline",
            "confidence": "medium",
            "data_sufficiency": data_sufficiency,
            "baseline_data": baseline_recommendation["baseline_data"],
            "note": (
                f"由于您的数据积累尚不充分（{len(data_sufficiency['missing_data'])}个维度数据不足），"
                "此建议基于湖南地区同类型餐厅的行业平均数据。"
                "随着您的数据积累，系统将自动切换到基于您门店实际数据的个性化建议。"
            ),
            "data_gap_info": data_sufficiency["missing_data"],
        }

    async def get_data_accumulation_progress(self) -> Dict[str, Any]:
        """
        获取数据积累进度

        Returns:
            数据积累进度信息
        """
        sufficiency = await self._check_data_sufficiency("general")

        progress = {
            "store_id": self.store_id,
            "overall_progress": 0.0,
            "dimensions": [],
            "estimated_days_to_sufficient": 0,
        }

        total_progress = 0.0
        for key, threshold in self.DATA_SUFFICIENCY_THRESHOLDS.items():
            current = sufficiency["data_counts"].get(key, 0)
            dimension_progress = min(current / threshold * 100, 100)
            total_progress += dimension_progress

            progress["dimensions"].append({
                "name": key,
                "current": current,
                "required": threshold,
                "progress": dimension_progress,
                "status": "sufficient" if current >= threshold else "insufficient",
            })

        progress["overall_progress"] = total_progress / len(self.DATA_SUFFICIENCY_THRESHOLDS)

        # 估算达到充足所需天数：基于实际数据量和天数计算日增长率
        if progress["overall_progress"] < 100:
            # 从 sufficiency 中获取实际数据量和天数
            current_orders = sufficiency.get("current_data", {}).get("orders", 0)
            current_days = sufficiency.get("current_data", {}).get("days", 0)
            # 日均订单增长率
            daily_order_rate = (current_orders / current_days) if current_days > 0 else 1.0
            # 估算最慢维度的剩余天数
            max_days_needed = 0
            for dim in progress["dimensions"]:
                if dim["status"] == "insufficient":
                    remaining = dim["required"] - dim["current"]
                    if dim["name"] == "orders" and daily_order_rate > 0:
                        days_needed = int(remaining / daily_order_rate)
                    else:
                        days_needed = int(remaining / max(daily_order_rate, 1))
                    max_days_needed = max(max_days_needed, days_needed)
            progress["estimated_days_to_sufficient"] = max_days_needed if max_days_needed > 0 else int(
                (100 - progress["overall_progress"]) / max(daily_order_rate, 1)
            )

        logger.info(
            "Data accumulation progress calculated",
            store_id=self.store_id,
            overall_progress=progress["overall_progress"],
        )

        return progress


# 使用示例
async def example_usage():
    """使用示例"""
    # 初始化服务
    rag_service = EnhancedRAGService(
        store_id="STORE001",
        restaurant_type="正餐"
    )

    # 查询客流预测
    result = await rag_service.query(
        query_text="明天午餐时段预计有多少客流？",
        query_type="traffic_forecast",
        context={
            "day_type": "工作日",
            "meal_period": "午餐",
        }
    )

    print(f"回答: {result['answer']}")
    print(f"数据来源: {result['data_source']}")
    print(f"置信度: {result['confidence']}")

    # 查看数据积累进度
    progress = await rag_service.get_data_accumulation_progress()
    print(f"数据积累进度: {progress['overall_progress']:.1f}%")
