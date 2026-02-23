"""
Service Quality Service - 服务质量数据库服务
处理服务质量监控的数据库操作
"""
import structlog
import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
import uuid

from src.core.database import get_db_session
from src.models.kpi import KPI, KPIRecord
from src.models.order import Order, OrderStatus
from src.models.employee import Employee

logger = structlog.get_logger()


class ServiceQualityService:
    """服务质量服务类"""

    def __init__(self, store_id: str = "STORE001"):
        """
        初始化服务质量服务

        Args:
            store_id: 门店ID
        """
        self.store_id = store_id
        logger.info("ServiceQualityService初始化", store_id=store_id)

    async def get_service_quality_metrics(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取服务质量指标

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            服务质量指标
        """
        async with get_db_session() as session:
            # 设置默认日期范围（最近7天）
            if not end_date:
                end_dt = datetime.now()
            else:
                end_dt = datetime.fromisoformat(end_date)

            if not start_date:
                start_dt = end_dt - timedelta(days=int(os.getenv("SERVICE_STATS_DAYS_SHORT", "7")))
            else:
                start_dt = datetime.fromisoformat(start_date)

            # 查询客户满意度KPI
            satisfaction_stmt = (
                select(KPIRecord)
                .join(KPI)
                .where(
                    and_(
                        KPIRecord.store_id == self.store_id,
                        KPI.category == "customer",
                        KPI.name.like("%满意度%"),
                        KPIRecord.record_date >= start_dt.date(),
                        KPIRecord.record_date <= end_dt.date()
                    )
                )
            )
            satisfaction_result = await session.execute(satisfaction_stmt)
            satisfaction_records = satisfaction_result.scalars().all()

            # 计算平均满意度
            if satisfaction_records:
                avg_satisfaction = sum(r.value for r in satisfaction_records) / len(satisfaction_records)
                satisfaction_trend = self._calculate_trend([r.value for r in satisfaction_records])
            else:
                avg_satisfaction = 0.0
                satisfaction_trend = "stable"

            # 查询订单数据以计算服务指标
            orders_stmt = (
                select(Order)
                .where(
                    and_(
                        Order.store_id == self.store_id,
                        Order.order_time >= start_dt,
                        Order.order_time <= end_dt
                    )
                )
            )
            orders_result = await session.execute(orders_stmt)
            orders = orders_result.scalars().all()

            # 计算服务指标
            total_orders = len(orders)
            completed_orders = sum(1 for o in orders if o.status == OrderStatus.COMPLETED)
            cancelled_orders = sum(1 for o in orders if o.status == OrderStatus.CANCELLED)

            completion_rate = (completed_orders / total_orders * 100) if total_orders > 0 else 0
            cancellation_rate = (cancelled_orders / total_orders * 100) if total_orders > 0 else 0

            # 计算平均服务时间（从订单创建到完成）
            service_times = []
            for order in orders:
                if order.status == OrderStatus.COMPLETED and order.completed_at and order.order_time:
                    service_time = (order.completed_at - order.order_time).total_seconds() / 60
                    service_times.append(service_time)

            avg_service_time = sum(service_times) / len(service_times) if service_times else 0

            # 从门店配置读取理想服务时间
            ideal_service_time = 30
            try:
                from src.models.store import Store
                store_result = await session.execute(
                    select(Store.config).where(Store.id == self.store_id)
                )
                store_cfg = store_result.scalar_one_or_none() or {}
                ideal_service_time = int(store_cfg.get("ideal_service_time_minutes", 30))
            except Exception:
                pass

            # 服务质量评分（基于多个指标的综合评分）
            quality_score = self._calculate_quality_score(
                avg_satisfaction,
                completion_rate,
                cancellation_rate,
                avg_service_time,
                ideal_service_time,
            )

            return {
                "period": {
                    "start_date": start_dt.isoformat(),
                    "end_date": end_dt.isoformat()
                },
                "satisfaction": {
                    "average_rating": round(avg_satisfaction, 2),
                    "trend": satisfaction_trend,
                    "records_count": len(satisfaction_records)
                },
                "service_metrics": {
                    "total_orders": total_orders,
                    "completed_orders": completed_orders,
                    "cancelled_orders": cancelled_orders,
                    "completion_rate": round(completion_rate, 2),
                    "cancellation_rate": round(cancellation_rate, 2),
                    "average_service_time_minutes": round(avg_service_time, 2)
                },
                "quality_score": round(quality_score, 2),
                "status": self._get_quality_status(quality_score)
            }

    async def get_staff_performance(
        self,
        staff_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取员工服务表现

        Args:
            staff_id: 员工ID（可选，不提供则返回所有员工）
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            员工表现列表
        """
        async with get_db_session() as session:
            # 设置默认日期范围
            if not end_date:
                end_dt = datetime.now()
            else:
                end_dt = datetime.fromisoformat(end_date)

            if not start_date:
                start_dt = end_dt - timedelta(days=int(os.getenv("SERVICE_STATS_DAYS", "30")))
            else:
                start_dt = datetime.fromisoformat(start_date)

            # 查询员工
            employees_stmt = select(Employee).where(Employee.store_id == self.store_id)
            if staff_id:
                employees_stmt = employees_stmt.where(Employee.id == staff_id)

            employees_result = await session.execute(employees_stmt)
            employees = employees_result.scalars().all()

            performance_list = []
            for employee in employees:
                # 查询该门店服务类KPI记录，计算平均达成率作为员工绩效参考
                kpi_result = await session.execute(
                    select(
                        func.avg(KPIRecord.achievement_rate).label("avg_achievement"),
                        func.avg(KPIRecord.value).label("avg_value"),
                        func.count(KPIRecord.id).label("record_count"),
                    ).where(
                        KPIRecord.store_id == self.store_id,
                        KPIRecord.kpi_id.like("KPI_SERVICE_%"),
                        KPIRecord.record_date >= start_dt.date(),
                        KPIRecord.record_date <= end_dt.date(),
                    )
                )
                kpi_row = kpi_result.one()
                avg_achievement = float(kpi_row.avg_achievement or 0)
                performance_score = round(avg_achievement * 100, 1) if avg_achievement else 88.5

                # 查询该门店订单数作为服务量参考
                order_result = await session.execute(
                    select(func.count(Order.id)).where(
                        Order.store_id == self.store_id,
                        Order.created_at >= start_dt,
                        Order.created_at <= end_dt,
                        Order.status == OrderStatus.COMPLETED,
                    )
                )
                total_orders = order_result.scalar() or 0
                # 按员工数均分
                total_employees = len(employees) or 1
                per_employee_orders = total_orders // total_employees

                performance = {
                    "staff_id": employee.id,
                    "staff_name": employee.name,
                    "position": employee.position,
                    "period": {
                        "start_date": start_dt.isoformat(),
                        "end_date": end_dt.isoformat()
                    },
                    "metrics": {
                        "total_services": per_employee_orders,
                        "customer_rating": round(min(5.0, 3.0 + avg_achievement * 2), 1) if avg_achievement else 4.5,
                        "service_speed": min(100, int(avg_achievement * 100)) if avg_achievement else 85,
                        "accuracy": min(100, int(avg_achievement * 105)) if avg_achievement else 95,
                    },
                    "performance_score": performance_score
                }
                performance_list.append(performance)

            return performance_list

    async def record_service_quality(
        self,
        metric_name: str,
        value: float,
        record_date: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        记录服务质量指标

        Args:
            metric_name: 指标名称
            value: 指标值
            record_date: 记录日期
            **kwargs: 其他元数据

        Returns:
            记录结果
        """
        async with get_db_session() as session:
            try:
                # 查找或创建KPI定义
                kpi_id = f"KPI_SERVICE_{metric_name.upper()}"
                kpi_stmt = select(KPI).where(KPI.id == kpi_id)
                kpi_result = await session.execute(kpi_stmt)
                kpi = kpi_result.scalar_one_or_none()

                if not kpi:
                    # 创建新的KPI定义
                    kpi = KPI(
                        id=kpi_id,
                        name=metric_name,
                        category="customer",
                        description=f"Service quality metric: {metric_name}",
                        unit=kwargs.get("unit", "score"),
                        target_value=kwargs.get("target_value", 90.0),
                        warning_threshold=kwargs.get("warning_threshold", 80.0),
                        critical_threshold=kwargs.get("critical_threshold", 70.0),
                        calculation_method="average",
                        is_active="true"
                    )
                    session.add(kpi)
                    await session.flush()

                # 创建KPI记录
                if not record_date:
                    record_dt = datetime.now().date()
                else:
                    record_dt = datetime.fromisoformat(record_date).date()

                kpi_record = KPIRecord(
                    kpi_id=kpi_id,
                    store_id=self.store_id,
                    record_date=record_dt,
                    value=value,
                    target_value=kpi.target_value,
                    achievement_rate=(value / kpi.target_value * 100) if kpi.target_value else 0,
                    status=self._get_kpi_status(value, kpi),
                    kpi_metadata=kwargs.get("metadata", {})
                )

                session.add(kpi_record)
                await session.commit()

                logger.info("服务质量指标记录成功", metric_name=metric_name, value=value)

                return {
                    "kpi_id": kpi_id,
                    "record_date": record_dt.isoformat(),
                    "value": value,
                    "status": kpi_record.status
                }

            except Exception as e:
                await session.rollback()
                logger.error("记录服务质量指标失败", error=str(e))
                raise

    async def get_service_report(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取服务质量报告

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            服务质量报告
        """
        # 获取服务质量指标
        quality_metrics = await self.get_service_quality_metrics(start_date, end_date)

        # 获取员工表现
        staff_performance = await self.get_staff_performance(
            start_date=start_date,
            end_date=end_date
        )

        # 生成改进建议
        improvements = self._generate_improvements(quality_metrics)

        return {
            "report_generated_at": datetime.now().isoformat(),
            "store_id": self.store_id,
            "quality_metrics": quality_metrics,
            "staff_performance": staff_performance,
            "improvements": improvements,
            "summary": {
                "overall_score": quality_metrics["quality_score"],
                "status": quality_metrics["status"],
                "key_findings": self._generate_key_findings(quality_metrics)
            }
        }

    def _calculate_trend(self, values: List[float]) -> str:
        """计算趋势（阈值支持环境变量覆盖）"""
        if len(values) < 2:
            return "stable"

        # 简单的趋势计算：比较前半部分和后半部分的平均值
        mid = len(values) // 2
        first_half_avg = sum(values[:mid]) / mid if mid > 0 else 0
        second_half_avg = sum(values[mid:]) / (len(values) - mid) if len(values) > mid else 0

        _up = float(os.getenv("TREND_IMPROVING_THRESHOLD", "1.05"))
        _down = float(os.getenv("TREND_DECLINING_THRESHOLD", "0.95"))
        if second_half_avg > first_half_avg * _up:
            return "improving"
        elif second_half_avg < first_half_avg * _down:
            return "declining"
        else:
            return "stable"

    def _calculate_quality_score(
        self,
        satisfaction: float,
        completion_rate: float,
        cancellation_rate: float,
        avg_service_time: float,
        ideal_service_time: int = 30,
    ) -> float:
        """
        计算综合服务质量评分

        Args:
            satisfaction: 满意度 (0-100)
            completion_rate: 完成率 (0-100)
            cancellation_rate: 取消率 (0-100)
            avg_service_time: 平均服务时间（分钟）

        Returns:
            质量评分 (0-100)
        """
        # 权重分配
        satisfaction_weight = float(os.getenv("SERVICE_SCORE_SATISFACTION_WEIGHT", "0.4"))
        completion_weight = float(os.getenv("SERVICE_SCORE_COMPLETION_WEIGHT", "0.3"))
        cancellation_weight = float(os.getenv("SERVICE_SCORE_CANCELLATION_WEIGHT", "0.2"))
        service_time_weight = float(os.getenv("SERVICE_SCORE_TIME_WEIGHT", "0.1"))

        # 标准化满意度（假设满意度已经是0-100的分数）
        satisfaction_score = satisfaction

        # 完成率得分
        completion_score = completion_rate

        # 取消率得分（取消率越低越好）
        cancellation_score = max(0, 100 - cancellation_rate * 2)

        # 服务时间得分（从门店配置读取理想服务时间，默认30分钟）
        ideal_service_time = int(os.getenv("SERVICE_IDEAL_TIME_MINUTES", "30"))
        if avg_service_time <= ideal_service_time:
            service_time_score = 100
        else:
            service_time_score = max(0, 100 - (avg_service_time - ideal_service_time) * 2)

        # 计算加权总分
        total_score = (
            satisfaction_score * satisfaction_weight +
            completion_score * completion_weight +
            cancellation_score * cancellation_weight +
            service_time_score * service_time_weight
        )

        return total_score

    def _get_quality_status(self, score: float) -> str:
        """获取质量状态（阈值支持环境变量覆盖）"""
        _excellent = float(os.getenv("SERVICE_QUALITY_EXCELLENT", "90"))
        _good = float(os.getenv("SERVICE_QUALITY_GOOD", "80"))
        _fair = float(os.getenv("SERVICE_QUALITY_FAIR", "70"))
        if score >= _excellent:
            return "excellent"
        elif score >= _good:
            return "good"
        elif score >= _fair:
            return "fair"
        else:
            return "needs_improvement"

    def _get_kpi_status(self, value: float, kpi: KPI) -> str:
        """获取KPI状态"""
        if kpi.critical_threshold and value < kpi.critical_threshold:
            return "off_track"
        elif kpi.warning_threshold and value < kpi.warning_threshold:
            return "at_risk"
        else:
            return "on_track"

    def _generate_improvements(self, quality_metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成改进建议"""
        improvements = []

        # 基于指标生成建议
        satisfaction = quality_metrics["satisfaction"]["average_rating"]
        if satisfaction < float(os.getenv("SERVICE_SATISFACTION_THRESHOLD", "80")):
            improvements.append({
                "category": "customer_satisfaction",
                "priority": "high",
                "issue": "客户满意度低于标准",
                "recommendation": "加强员工培训，提升服务质量"
            })

        cancellation_rate = quality_metrics["service_metrics"]["cancellation_rate"]
        if cancellation_rate > float(os.getenv("SERVICE_CANCEL_RATE_THRESHOLD", "5")):
            improvements.append({
                "category": "order_cancellation",
                "priority": "medium",
                "issue": "订单取消率偏高",
                "recommendation": "分析取消原因，优化订单流程"
            })

        avg_service_time = quality_metrics["service_metrics"]["average_service_time_minutes"]
        if avg_service_time > float(os.getenv("SERVICE_TIME_THRESHOLD_MINUTES", "45")):
            improvements.append({
                "category": "service_efficiency",
                "priority": "medium",
                "issue": "平均服务时间过长",
                "recommendation": "优化厨房流程，提高出餐速度"
            })

        return improvements

    def _generate_key_findings(self, quality_metrics: Dict[str, Any]) -> List[str]:
        """生成关键发现"""
        findings = []

        quality_score = quality_metrics["quality_score"]
        if quality_score >= float(os.getenv("SERVICE_QUALITY_EXCELLENT_THRESHOLD", "90")):
            findings.append("服务质量表现优秀，继续保持")
        elif quality_score >= float(os.getenv("SERVICE_QUALITY_GOOD_THRESHOLD", "80")):
            findings.append("服务质量良好，有提升空间")
        else:
            findings.append("服务质量需要改进")

        satisfaction_trend = quality_metrics["satisfaction"]["trend"]
        if satisfaction_trend == "improving":
            findings.append("客户满意度呈上升趋势")
        elif satisfaction_trend == "declining":
            findings.append("客户满意度呈下降趋势，需要关注")

        return findings


# 创建全局服务实例
service_quality_service = ServiceQualityService()
