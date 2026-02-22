"""
Daily Report Service
营业日报服务
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, date, timedelta
from sqlalchemy import select, and_, func
import structlog
import uuid

from src.core.database import get_db_session
from src.models.daily_report import DailyReport
from src.models.order import Order
from src.models.task import Task, TaskStatus
from src.models.inventory import InventoryItem
from src.models.store import Store

logger = structlog.get_logger()


class DailyReportService:
    """营业日报服务"""

    async def generate_daily_report(
        self,
        store_id: str,
        report_date: Optional[date] = None
    ) -> DailyReport:
        """
        生成营业日报

        Args:
            store_id: 门店ID
            report_date: 报告日期（默认为昨天）

        Returns:
            生成的日报对象
        """
        try:
            if report_date is None:
                # 默认生成昨天的日报
                report_date = date.today() - timedelta(days=1)

            logger.info(
                "开始生成营业日报",
                store_id=store_id,
                report_date=str(report_date)
            )

            async with get_db_session() as session:
                # 检查是否已存在该日期的日报
                existing_report = await self._get_existing_report(
                    session, store_id, report_date
                )

                if existing_report:
                    logger.info(
                        "日报已存在，更新数据",
                        store_id=store_id,
                        report_date=str(report_date)
                    )
                    report = existing_report
                else:
                    report = DailyReport(
                        store_id=store_id,
                        report_date=report_date
                    )
                    session.add(report)

                # 1. 聚合营收数据
                revenue_data = await self._aggregate_revenue_data(
                    session, store_id, report_date
                )
                report.total_revenue = revenue_data["total_revenue"]
                report.order_count = revenue_data["order_count"]
                report.customer_count = revenue_data["customer_count"]
                report.avg_order_value = revenue_data["avg_order_value"]

                # 2. 计算环比数据
                comparison_data = await self._calculate_comparison(
                    session, store_id, report_date
                )
                report.revenue_change_rate = comparison_data["revenue_change_rate"]
                report.order_change_rate = comparison_data["order_change_rate"]
                report.customer_change_rate = comparison_data["customer_change_rate"]

                # 3. 聚合运营数据
                operation_data = await self._aggregate_operation_data(
                    session, store_id, report_date
                )
                report.inventory_alert_count = operation_data["inventory_alert_count"]
                report.task_completion_rate = operation_data["task_completion_rate"]
                report.service_issue_count = operation_data["service_issue_count"]

                # 4. 聚合详细数据
                detail_data = await self._aggregate_detail_data(
                    session, store_id, report_date
                )
                report.top_dishes = detail_data["top_dishes"]
                report.peak_hours = detail_data["peak_hours"]
                report.payment_methods = detail_data["payment_methods"]

                # 5. 生成报告摘要
                report.summary = self._generate_summary(report)
                report.highlights = self._generate_highlights(report)
                report.alerts = self._generate_alerts(report)

                await session.commit()
                await session.refresh(report)

                logger.info(
                    "营业日报生成成功",
                    store_id=store_id,
                    report_date=str(report_date),
                    report_id=str(report.id)
                )

                return report

        except Exception as e:
            logger.error(
                "生成营业日报失败",
                store_id=store_id,
                report_date=str(report_date) if report_date else None,
                error=str(e),
                exc_info=e
            )
            raise

    async def _get_existing_report(
        self,
        session,
        store_id: str,
        report_date: date
    ) -> Optional[DailyReport]:
        """获取已存在的日报"""
        result = await session.execute(
            select(DailyReport).where(
                and_(
                    DailyReport.store_id == store_id,
                    DailyReport.report_date == report_date
                )
            )
        )
        return result.scalar_one_or_none()

    async def _aggregate_revenue_data(
        self,
        session,
        store_id: str,
        report_date: date
    ) -> Dict[str, int]:
        """聚合营收数据"""
        try:
            # 查询当天的订单数据
            start_datetime = datetime.combine(report_date, datetime.min.time())
            end_datetime = datetime.combine(report_date, datetime.max.time())

            result = await session.execute(
                select(
                    func.count(Order.id).label("order_count"),
                    func.sum(Order.total_amount).label("total_revenue"),
                    func.count(func.distinct(Order.customer_id)).label("customer_count")
                ).where(
                    and_(
                        Order.store_id == store_id,
                        Order.created_at >= start_datetime,
                        Order.created_at <= end_datetime,
                        Order.status != "cancelled"
                    )
                )
            )

            row = result.first()

            order_count = row.order_count or 0
            total_revenue = int(row.total_revenue or 0)
            customer_count = row.customer_count or 0
            avg_order_value = int(total_revenue / order_count) if order_count > 0 else 0

            return {
                "total_revenue": total_revenue,
                "order_count": order_count,
                "customer_count": customer_count,
                "avg_order_value": avg_order_value
            }

        except Exception as e:
            logger.error("聚合营收数据失败", error=str(e))
            return {
                "total_revenue": 0,
                "order_count": 0,
                "customer_count": 0,
                "avg_order_value": 0
            }

    async def _calculate_comparison(
        self,
        session,
        store_id: str,
        report_date: date
    ) -> Dict[str, float]:
        """计算环比数据"""
        try:
            # 获取前一天的日报
            previous_date = report_date - timedelta(days=1)
            previous_report = await self._get_existing_report(
                session, store_id, previous_date
            )

            if not previous_report or previous_report.total_revenue == 0:
                return {
                    "revenue_change_rate": 0.0,
                    "order_change_rate": 0.0,
                    "customer_change_rate": 0.0
                }

            # 获取当天数据
            current_data = await self._aggregate_revenue_data(
                session, store_id, report_date
            )

            # 计算环比
            revenue_change = (
                (current_data["total_revenue"] - previous_report.total_revenue) /
                previous_report.total_revenue * 100
            ) if previous_report.total_revenue > 0 else 0.0

            order_change = (
                (current_data["order_count"] - previous_report.order_count) /
                previous_report.order_count * 100
            ) if previous_report.order_count > 0 else 0.0

            customer_change = (
                (current_data["customer_count"] - previous_report.customer_count) /
                previous_report.customer_count * 100
            ) if previous_report.customer_count > 0 else 0.0

            return {
                "revenue_change_rate": round(revenue_change, 2),
                "order_change_rate": round(order_change, 2),
                "customer_change_rate": round(customer_change, 2)
            }

        except Exception as e:
            logger.error("计算环比数据失败", error=str(e))
            return {
                "revenue_change_rate": 0.0,
                "order_change_rate": 0.0,
                "customer_change_rate": 0.0
            }

    async def _aggregate_operation_data(
        self,
        session,
        store_id: str,
        report_date: date
    ) -> Dict[str, Any]:
        """聚合运营数据"""
        try:
            start_datetime = datetime.combine(report_date, datetime.min.time())
            end_datetime = datetime.combine(report_date, datetime.max.time())

            # 1. 库存预警数
            inventory_result = await session.execute(
                select(func.count(InventoryItem.id)).where(
                    and_(
                        InventoryItem.store_id == store_id,
                        InventoryItem.quantity <= InventoryItem.min_quantity
                    )
                )
            )
            inventory_alert_count = inventory_result.scalar() or 0

            # 2. 任务完成率
            task_result = await session.execute(
                select(
                    func.count(Task.id).label("total"),
                    func.sum(
                        func.case((Task.status == TaskStatus.COMPLETED, 1), else_=0)
                    ).label("completed")
                ).where(
                    and_(
                        Task.store_id == store_id,
                        Task.created_at >= start_datetime,
                        Task.created_at <= end_datetime,
                        Task.is_deleted == "false"
                    )
                )
            )
            task_row = task_result.first()
            total_tasks = task_row.total or 0
            completed_tasks = task_row.completed or 0
            task_completion_rate = (
                (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0.0
            )

            # 3. 服务问题数（暂时返回0，后续可以从反馈系统获取）
            service_issue_count = 0

            return {
                "inventory_alert_count": inventory_alert_count,
                "task_completion_rate": round(task_completion_rate, 2),
                "service_issue_count": service_issue_count
            }

        except Exception as e:
            logger.error("聚合运营数据失败", error=str(e))
            return {
                "inventory_alert_count": 0,
                "task_completion_rate": 0.0,
                "service_issue_count": 0
            }

    async def _aggregate_detail_data(
        self,
        session,
        store_id: str,
        report_date: date
    ) -> Dict[str, Any]:
        """聚合详细数据：热销菜品、高峰时段"""
        from src.models.order import OrderItem, OrderStatus
        from sqlalchemy import extract

        # 热销菜品 Top5
        top_dishes_result = await session.execute(
            select(
                OrderItem.item_name,
                func.sum(OrderItem.quantity).label("qty"),
                func.sum(OrderItem.subtotal).label("revenue"),
            )
            .join(Order, OrderItem.order_id == Order.id)
            .where(
                Order.store_id == store_id,
                func.date(Order.order_time) == report_date,
                Order.status == OrderStatus.COMPLETED,
            )
            .group_by(OrderItem.item_name)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(5)
        )
        top_dishes = [
            {"name": row.item_name, "quantity": int(row.qty), "revenue": int(row.revenue)}
            for row in top_dishes_result.all()
        ]

        # 高峰时段（按小时统计订单数）
        peak_hours_result = await session.execute(
            select(
                extract("hour", Order.order_time).label("hour"),
                func.count(Order.id).label("order_count"),
            )
            .where(
                Order.store_id == store_id,
                func.date(Order.order_time) == report_date,
                Order.status == OrderStatus.COMPLETED,
            )
            .group_by(extract("hour", Order.order_time))
            .order_by(func.count(Order.id).desc())
            .limit(3)
        )
        peak_hours = [
            {"hour": int(row.hour), "order_count": int(row.order_count)}
            for row in peak_hours_result.all()
        ]

        return {
            "top_dishes": top_dishes,
            "peak_hours": peak_hours,
            "payment_methods": {}
        }

    def _generate_summary(self, report: DailyReport) -> str:
        """生成报告摘要"""
        revenue_yuan = report.total_revenue / 100
        avg_order_yuan = report.avg_order_value / 100

        summary = f"营业额：¥{revenue_yuan:.2f}，订单数：{report.order_count}笔，客流量：{report.customer_count}人，客单价：¥{avg_order_yuan:.2f}"

        if report.revenue_change_rate != 0:
            change_text = "增长" if report.revenue_change_rate > 0 else "下降"
            summary += f"，营收环比{change_text}{abs(report.revenue_change_rate):.1f}%"

        return summary

    def _generate_highlights(self, report: DailyReport) -> List[str]:
        """生成亮点数据"""
        highlights = []

        if report.revenue_change_rate > 10:
            highlights.append(f"营收大幅增长{report.revenue_change_rate:.1f}%")

        if report.task_completion_rate >= 90:
            highlights.append(f"任务完成率达{report.task_completion_rate:.1f}%")

        if report.order_count > 100:
            highlights.append(f"订单量突破{report.order_count}笔")

        return highlights

    def _generate_alerts(self, report: DailyReport) -> List[str]:
        """生成预警信息"""
        alerts = []

        if report.revenue_change_rate < -10:
            alerts.append(f"营收下降{abs(report.revenue_change_rate):.1f}%，需关注")

        if report.inventory_alert_count > 0:
            alerts.append(f"{report.inventory_alert_count}个商品库存不足")

        if report.task_completion_rate < 70:
            alerts.append(f"任务完成率仅{report.task_completion_rate:.1f}%")

        return alerts

    async def get_report(
        self,
        store_id: str,
        report_date: date
    ) -> Optional[DailyReport]:
        """获取指定日期的日报"""
        try:
            async with get_db_session() as session:
                return await self._get_existing_report(session, store_id, report_date)
        except Exception as e:
            logger.error("获取日报失败", error=str(e), exc_info=e)
            return None

    async def mark_as_sent(self, report_id: uuid.UUID) -> bool:
        """标记日报为已推送"""
        try:
            async with get_db_session() as session:
                result = await session.execute(
                    select(DailyReport).where(DailyReport.id == report_id)
                )
                report = result.scalar_one_or_none()

                if report:
                    report.is_sent = "true"
                    report.sent_at = datetime.now().isoformat()
                    await session.commit()
                    return True

                return False

        except Exception as e:
            logger.error("标记日报已推送失败", error=str(e), exc_info=e)
            return False


# 创建全局服务实例
daily_report_service = DailyReportService()
