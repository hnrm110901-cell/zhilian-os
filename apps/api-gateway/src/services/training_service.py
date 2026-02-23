"""
Training Service - 培训管理数据库服务
处理培训的数据库操作
"""
import structlog
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
import uuid

from src.core.database import get_db_session
from src.models.kpi import KPI, KPIRecord
from src.models.employee import Employee

logger = structlog.get_logger()


class TrainingService:
    """培训服务类"""

    def __init__(self, store_id: str = "STORE001"):
        self.store_id = store_id
        self.training_config = {
            "min_passing_score": 70,
            "certificate_validity_months": 12
        }
        logger.info("TrainingService初始化", store_id=store_id)

    async def _get_training_config(self) -> Dict[str, Any]:
        """从Store配置读取培训参数，失败时使用默认值"""
        try:
            from src.models.store import Store
            async with get_db_session() as session:
                result = await session.execute(select(Store).where(Store.id == self.store_id))
                store = result.scalar_one_or_none()
                if store and store.config:
                    cfg = store.config
                    return {
                        "min_passing_score": int(cfg.get("training_min_passing_score", 70)),
                        "certificate_validity_months": int(cfg.get("training_certificate_validity_months", 12)),
                        "warning_threshold": float(cfg.get("training_warning_threshold", 60.0)),
                        "critical_threshold": float(cfg.get("training_critical_threshold", 50.0)),
                    }
        except Exception as e:
            logger.warning("读取培训配置失败，使用默认值", error=str(e))
        return {
            "min_passing_score": 70,
            "certificate_validity_months": 12,
            "warning_threshold": 60.0,
            "critical_threshold": 50.0,
        }

    async def assess_training_needs(
        self,
        staff_id: Optional[str] = None,
        position: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        评估培训需求

        Args:
            staff_id: 员工ID（可选）
            position: 岗位（可选）

        Returns:
            培训需求列表
        """
        async with get_db_session() as session:
            # 查询员工
            stmt = select(Employee).where(Employee.store_id == self.store_id)

            if staff_id:
                stmt = stmt.where(Employee.id == staff_id)

            if position:
                stmt = stmt.where(Employee.position == position)

            result = await session.execute(stmt)
            employees = result.scalars().all()

            # 生成培训需求（基于员工岗位和技能）
            training_needs = []
            for employee in employees:
                # 根据岗位确定培训需求
                needs = self._identify_training_needs(employee)
                training_needs.extend(needs)

            return training_needs

    async def record_training_completion(
        self,
        staff_id: str,
        course_name: str,
        completion_date: str,
        score: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        记录培训完成情况

        Args:
            staff_id: 员工ID
            course_name: 课程名称
            completion_date: 完成日期
            score: 分数
            **kwargs: 其他参数

        Returns:
            记录结果
        """
        async with get_db_session() as session:
            try:
                # 从Store配置读取培训参数
                training_cfg = await self._get_training_config()
                min_passing = training_cfg["min_passing_score"]
                warning_thr = training_cfg["warning_threshold"]
                critical_thr = training_cfg["critical_threshold"]

                # 创建培训完成记录（使用KPI记录）
                kpi_id = f"KPI_TRAINING_{course_name.upper().replace(' ', '_')}"

                # 查找或创建KPI定义
                kpi_stmt = select(KPI).where(KPI.id == kpi_id)
                kpi_result = await session.execute(kpi_stmt)
                kpi = kpi_result.scalar_one_or_none()

                if not kpi:
                    kpi = KPI(
                        id=kpi_id,
                        name=f"Training: {course_name}",
                        category="training",
                        description=f"Training completion for {course_name}",
                        unit="score",
                        target_value=min_passing,
                        warning_threshold=warning_thr,
                        critical_threshold=critical_thr,
                        calculation_method="average",
                        is_active="true"
                    )
                    session.add(kpi)
                    await session.flush()

                # 创建KPI记录
                completion_dt = datetime.fromisoformat(completion_date).date()

                kpi_record = KPIRecord(
                    kpi_id=kpi_id,
                    store_id=self.store_id,
                    record_date=completion_dt,
                    value=score if score else 100,
                    target_value=kpi.target_value,
                    achievement_rate=(score / kpi.target_value * 100) if score and kpi.target_value else 100,
                    status="on_track" if (score or 100) >= kpi.target_value else "off_track",
                    kpi_metadata={
                        "staff_id": staff_id,
                        "course_name": course_name,
                        "passed": (score or 100) >= min_passing,
                        **kwargs
                    }
                )

                session.add(kpi_record)
                await session.commit()

                logger.info("培训完成记录成功", staff_id=staff_id, course=course_name)

                return {
                    "record_id": str(kpi_record.id),
                    "staff_id": staff_id,
                    "course_name": course_name,
                    "completion_date": completion_date,
                    "score": score,
                    "passed": (score or 100) >= min_passing,
                    "status": kpi_record.status
                }

            except Exception as e:
                await session.rollback()
                logger.error("记录培训完成失败", error=str(e))
                raise

    async def get_training_progress(
        self,
        staff_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取培训进度

        Args:
            staff_id: 员工ID
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            培训进度列表
        """
        async with get_db_session() as session:
            # 查询培训相关的KPI记录
            stmt = (
                select(KPIRecord)
                .join(KPI)
                .where(
                    and_(
                        KPIRecord.store_id == self.store_id,
                        KPI.category == "training"
                    )
                )
            )

            if start_date:
                start_dt = datetime.fromisoformat(start_date).date()
                stmt = stmt.where(KPIRecord.record_date >= start_dt)

            if end_date:
                end_dt = datetime.fromisoformat(end_date).date()
                stmt = stmt.where(KPIRecord.record_date <= end_dt)

            result = await session.execute(stmt)
            records = result.scalars().all()

            # 过滤特定员工的记录
            progress_list = []
            for record in records:
                metadata = record.kpi_metadata or {}
                if staff_id and metadata.get("staff_id") != staff_id:
                    continue

                progress_list.append({
                    "record_id": str(record.id),
                    "staff_id": metadata.get("staff_id"),
                    "course_name": metadata.get("course_name"),
                    "completion_date": record.record_date.isoformat(),
                    "score": record.value,
                    "passed": metadata.get("passed", False),
                    "status": record.status
                })

            return progress_list

    async def get_training_statistics(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取培训统计

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            统计信息
        """
        async with get_db_session() as session:
            # 设置默认日期范围
            if not end_date:
                end_dt = datetime.now()
            else:
                end_dt = datetime.fromisoformat(end_date)

            if not start_date:
                start_dt = end_dt - timedelta(days=30)
            else:
                start_dt = datetime.fromisoformat(start_date)

            # 查询培训记录
            stmt = (
                select(KPIRecord)
                .join(KPI)
                .where(
                    and_(
                        KPIRecord.store_id == self.store_id,
                        KPI.category == "training",
                        KPIRecord.record_date >= start_dt.date(),
                        KPIRecord.record_date <= end_dt.date()
                    )
                )
            )

            result = await session.execute(stmt)
            records = result.scalars().all()

            # 统计数据
            total_trainings = len(records)
            passed_trainings = sum(
                1 for r in records
                if (r.kpi_metadata or {}).get("passed", False)
            )
            average_score = sum(r.value for r in records) / total_trainings if total_trainings > 0 else 0

            # 统计参与员工
            unique_staff = set()
            for record in records:
                metadata = record.kpi_metadata or {}
                if metadata.get("staff_id"):
                    unique_staff.add(metadata["staff_id"])

            # 统计课程
            course_counts = {}
            for record in records:
                metadata = record.kpi_metadata or {}
                course_name = metadata.get("course_name", "Unknown")
                course_counts[course_name] = course_counts.get(course_name, 0) + 1

            return {
                "period": {
                    "start_date": start_dt.isoformat(),
                    "end_date": end_dt.isoformat()
                },
                "total_trainings": total_trainings,
                "passed_trainings": passed_trainings,
                "failed_trainings": total_trainings - passed_trainings,
                "pass_rate": round((passed_trainings / total_trainings * 100), 2) if total_trainings > 0 else 0,
                "average_score": round(average_score, 2),
                "unique_staff_count": len(unique_staff),
                "course_breakdown": course_counts
            }

    async def get_training_report(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取培训报告

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            培训报告
        """
        # 获取培训统计
        statistics = await self.get_training_statistics(start_date, end_date)

        # 获取培训进度
        progress = await self.get_training_progress(start_date=start_date, end_date=end_date)

        # 评估培训需求
        training_needs = await self.assess_training_needs()

        return {
            "report_generated_at": datetime.now().isoformat(),
            "store_id": self.store_id,
            "statistics": statistics,
            "recent_completions": progress[:10],  # 最近10条记录
            "training_needs": training_needs[:5],  # 前5个培训需求
            "recommendations": self._generate_recommendations(statistics, training_needs)
        }

    async def get_employee_training_history(
        self,
        staff_id: str
    ) -> Dict[str, Any]:
        """
        获取员工培训历史

        Args:
            staff_id: 员工ID

        Returns:
            培训历史
        """
        async with get_db_session() as session:
            # 获取员工信息
            emp_stmt = select(Employee).where(Employee.id == staff_id)
            emp_result = await session.execute(emp_stmt)
            employee = emp_result.scalar_one_or_none()

            if not employee:
                raise ValueError(f"员工不存在: {staff_id}")

            # 获取培训记录
            progress = await self.get_training_progress(staff_id=staff_id)

            # 计算统计数据
            total_trainings = len(progress)
            passed_trainings = sum(1 for p in progress if p["passed"])
            average_score = sum(p["score"] for p in progress) / total_trainings if total_trainings > 0 else 0

            return {
                "staff_id": staff_id,
                "staff_name": employee.name,
                "position": employee.position,
                "training_summary": {
                    "total_trainings": total_trainings,
                    "passed_trainings": passed_trainings,
                    "pass_rate": round((passed_trainings / total_trainings * 100), 2) if total_trainings > 0 else 0,
                    "average_score": round(average_score, 2)
                },
                "training_history": progress
            }

    def _identify_training_needs(self, employee: Employee) -> List[Dict[str, Any]]:
        """识别员工培训需求"""
        needs = []

        # 基于岗位的基础培训需求
        position_training_map = {
            "waiter": ["customer_service", "product_knowledge"],
            "chef": ["food_safety", "cooking_skills"],
            "cashier": ["pos_system", "customer_service"],
            "manager": ["management", "leadership"]
        }

        position = employee.position.lower() if employee.position else ""
        required_trainings = []

        for key, trainings in position_training_map.items():
            if key in position:
                required_trainings = trainings
                break

        for training in required_trainings:
            needs.append({
                "need_id": f"NEED_{employee.id}_{training.upper()}",
                "staff_id": employee.id,
                "staff_name": employee.name,
                "position": employee.position,
                "skill_gap": training,
                "current_level": "beginner",
                "target_level": "intermediate",
                "priority": "medium",
                "recommended_courses": [training],
                "reason": f"Required for {employee.position} position",
                "identified_at": datetime.now().isoformat()
            })

        return needs

    def _generate_recommendations(
        self,
        statistics: Dict[str, Any],
        training_needs: List[Dict[str, Any]]
    ) -> List[str]:
        """生成培训建议"""
        recommendations = []

        pass_rate = statistics.get("pass_rate", 0)
        if pass_rate < 80:
            recommendations.append(f"培训通过率为{pass_rate}%，建议加强培训质量和考核标准")

        if len(training_needs) > 0:
            recommendations.append(f"有{len(training_needs)}个培训需求待满足，建议制定培训计划")

        avg_score = statistics.get("average_score", 0)
        if avg_score < 75:
            recommendations.append(f"平均培训分数为{avg_score}，建议提供更多培训资源和辅导")

        return recommendations


# 创建全局服务实例
training_service = TrainingService()
