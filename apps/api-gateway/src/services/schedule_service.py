"""
Schedule Service - 排班管理数据库服务
处理排班的数据库操作
"""
import structlog
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, time
from sqlalchemy import select, func, and_, or_, delete
from sqlalchemy.orm import selectinload
import uuid

from src.core.database import get_db_session
from src.models.schedule import Schedule, Shift
from src.models.employee import Employee

logger = structlog.get_logger()


class ScheduleService:
    """排班服务类"""

    def __init__(self, store_id: str = "STORE001"):
        """
        初始化排班服务

        Args:
            store_id: 门店ID
        """
        self.store_id = store_id
        logger.info("ScheduleService初始化", store_id=store_id)

    async def create_schedule(
        self,
        schedule_date: str,
        shifts: List[Dict[str, Any]],
        **kwargs
    ) -> Dict[str, Any]:
        """
        创建排班

        Args:
            schedule_date: 排班日期
            shifts: 班次列表
            **kwargs: 其他参数

        Returns:
            排班信息
        """
        async with get_db_session() as session:
            try:
                # 检查是否已存在该日期的排班
                date_obj = datetime.fromisoformat(schedule_date).date()
                existing_stmt = (
                    select(Schedule)
                    .where(
                        and_(
                            Schedule.store_id == self.store_id,
                            Schedule.schedule_date == date_obj
                        )
                    )
                )
                existing_result = await session.execute(existing_stmt)
                existing_schedule = existing_result.scalar_one_or_none()

                if existing_schedule:
                    # 删除旧的班次
                    delete_stmt = delete(Shift).where(Shift.schedule_id == existing_schedule.id)
                    await session.execute(delete_stmt)
                    schedule = existing_schedule
                else:
                    # 创建新排班
                    schedule = Schedule(
                        store_id=self.store_id,
                        schedule_date=date_obj,
                        total_employees=str(len(shifts)),
                        is_published=kwargs.get("is_published", False),
                        published_by=kwargs.get("published_by")
                    )
                    session.add(schedule)
                    await session.flush()

                # 创建班次
                total_hours = 0
                for shift_data in shifts:
                    shift = Shift(
                        schedule_id=schedule.id,
                        employee_id=shift_data["employee_id"],
                        shift_type=shift_data["shift_type"],
                        start_time=datetime.fromisoformat(shift_data["start_time"]).time(),
                        end_time=datetime.fromisoformat(shift_data["end_time"]).time(),
                        position=shift_data.get("position"),
                        is_confirmed=shift_data.get("is_confirmed", False),
                        notes=shift_data.get("notes")
                    )
                    session.add(shift)

                    # 计算工作时长
                    start_dt = datetime.combine(date_obj, shift.start_time)
                    end_dt = datetime.combine(date_obj, shift.end_time)
                    if end_dt < start_dt:
                        end_dt += timedelta(days=1)
                    hours = (end_dt - start_dt).total_seconds() / 3600
                    total_hours += hours

                schedule.total_hours = str(round(total_hours, 1))

                await session.commit()
                await session.refresh(schedule, ["shifts"])

                logger.info("排班创建成功", schedule_id=str(schedule.id), date=schedule_date)

                return self._schedule_to_dict(schedule)

            except Exception as e:
                await session.rollback()
                logger.error("创建排班失败", error=str(e))
                raise

    async def get_schedule(
        self,
        start_date: str,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取排班

        Args:
            start_date: 开始日期
            end_date: 结束日期（可选）

        Returns:
            排班列表
        """
        async with get_db_session() as session:
            start_dt = datetime.fromisoformat(start_date).date()

            stmt = (
                select(Schedule)
                .options(selectinload(Schedule.shifts))
                .where(
                    and_(
                        Schedule.store_id == self.store_id,
                        Schedule.schedule_date >= start_dt
                    )
                )
            )

            if end_date:
                end_dt = datetime.fromisoformat(end_date).date()
                stmt = stmt.where(Schedule.schedule_date <= end_dt)

            stmt = stmt.order_by(Schedule.schedule_date)

            result = await session.execute(stmt)
            schedules = result.scalars().all()

            return [self._schedule_to_dict(schedule) for schedule in schedules]

    async def get_schedule_by_date(
        self,
        schedule_date: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取指定日期的排班

        Args:
            schedule_date: 排班日期

        Returns:
            排班信息
        """
        async with get_db_session() as session:
            date_obj = datetime.fromisoformat(schedule_date).date()

            stmt = (
                select(Schedule)
                .options(selectinload(Schedule.shifts))
                .where(
                    and_(
                        Schedule.store_id == self.store_id,
                        Schedule.schedule_date == date_obj
                    )
                )
            )

            result = await session.execute(stmt)
            schedule = result.scalar_one_or_none()

            if not schedule:
                return None

            return self._schedule_to_dict(schedule)

    async def update_schedule(
        self,
        schedule_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        更新排班

        Args:
            schedule_id: 排班ID
            **kwargs: 更新字段

        Returns:
            更新后的排班信息
        """
        async with get_db_session() as session:
            try:
                stmt = (
                    select(Schedule)
                    .options(selectinload(Schedule.shifts))
                    .where(Schedule.id == uuid.UUID(schedule_id))
                )
                result = await session.execute(stmt)
                schedule = result.scalar_one_or_none()

                if not schedule:
                    raise ValueError(f"排班不存在: {schedule_id}")

                # 更新字段
                if "is_published" in kwargs:
                    schedule.is_published = kwargs["is_published"]
                if "published_by" in kwargs:
                    schedule.published_by = kwargs["published_by"]

                await session.commit()

                logger.info("排班更新成功", schedule_id=schedule_id)

                return self._schedule_to_dict(schedule)

            except Exception as e:
                await session.rollback()
                logger.error("更新排班失败", error=str(e))
                raise

    async def delete_schedule(
        self,
        schedule_id: str
    ) -> Dict[str, Any]:
        """
        删除排班

        Args:
            schedule_id: 排班ID

        Returns:
            删除结果
        """
        async with get_db_session() as session:
            try:
                stmt = select(Schedule).where(Schedule.id == uuid.UUID(schedule_id))
                result = await session.execute(stmt)
                schedule = result.scalar_one_or_none()

                if not schedule:
                    raise ValueError(f"排班不存在: {schedule_id}")

                await session.delete(schedule)
                await session.commit()

                logger.info("排班删除成功", schedule_id=schedule_id)

                return {
                    "schedule_id": schedule_id,
                    "deleted": True
                }

            except Exception as e:
                await session.rollback()
                logger.error("删除排班失败", error=str(e))
                raise

    async def get_employee_schedules(
        self,
        employee_id: str,
        start_date: str,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取员工的排班

        Args:
            employee_id: 员工ID
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            员工排班列表
        """
        async with get_db_session() as session:
            start_dt = datetime.fromisoformat(start_date).date()

            stmt = (
                select(Shift)
                .join(Schedule)
                .where(
                    and_(
                        Shift.employee_id == employee_id,
                        Schedule.store_id == self.store_id,
                        Schedule.schedule_date >= start_dt
                    )
                )
            )

            if end_date:
                end_dt = datetime.fromisoformat(end_date).date()
                stmt = stmt.where(Schedule.schedule_date <= end_dt)

            stmt = stmt.order_by(Schedule.schedule_date)

            result = await session.execute(stmt)
            shifts = result.scalars().all()

            # 获取关联的schedule信息
            employee_schedules = []
            for shift in shifts:
                schedule_stmt = (
                    select(Schedule)
                    .where(Schedule.id == shift.schedule_id)
                )
                schedule_result = await session.execute(schedule_stmt)
                schedule = schedule_result.scalar_one()

                employee_schedules.append({
                    "schedule_date": schedule.schedule_date.isoformat(),
                    "shift_id": str(shift.id),
                    "shift_type": shift.shift_type,
                    "start_time": shift.start_time.isoformat(),
                    "end_time": shift.end_time.isoformat(),
                    "position": shift.position,
                    "is_confirmed": shift.is_confirmed,
                    "notes": shift.notes
                })

            return employee_schedules

    async def get_schedule_statistics(
        self,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """
        获取排班统计

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            统计信息
        """
        async with get_db_session() as session:
            start_dt = datetime.fromisoformat(start_date).date()
            end_dt = datetime.fromisoformat(end_date).date()

            # 查询排班
            schedules_stmt = (
                select(Schedule)
                .options(selectinload(Schedule.shifts))
                .where(
                    and_(
                        Schedule.store_id == self.store_id,
                        Schedule.schedule_date >= start_dt,
                        Schedule.schedule_date <= end_dt
                    )
                )
            )

            result = await session.execute(schedules_stmt)
            schedules = result.scalars().all()

            # 统计数据
            total_schedules = len(schedules)
            published_schedules = sum(1 for s in schedules if s.is_published)
            total_shifts = sum(len(s.shifts) for s in schedules)

            # 统计班次类型
            shift_type_counts = {}
            for schedule in schedules:
                for shift in schedule.shifts:
                    shift_type = shift.shift_type
                    shift_type_counts[shift_type] = shift_type_counts.get(shift_type, 0) + 1

            # 统计员工工作时长
            employee_hours = {}
            for schedule in schedules:
                for shift in schedule.shifts:
                    start_dt_time = datetime.combine(schedule.schedule_date, shift.start_time)
                    end_dt_time = datetime.combine(schedule.schedule_date, shift.end_time)
                    if end_dt_time < start_dt_time:
                        end_dt_time += timedelta(days=1)
                    hours = (end_dt_time - start_dt_time).total_seconds() / 3600

                    if shift.employee_id not in employee_hours:
                        employee_hours[shift.employee_id] = 0
                    employee_hours[shift.employee_id] += hours

            return {
                "period": {
                    "start_date": start_date,
                    "end_date": end_date
                },
                "total_schedules": total_schedules,
                "published_schedules": published_schedules,
                "total_shifts": total_shifts,
                "shift_type_breakdown": shift_type_counts,
                "employee_count": len(employee_hours),
                "average_hours_per_employee": round(sum(employee_hours.values()) / len(employee_hours), 2) if employee_hours else 0
            }

    def _schedule_to_dict(self, schedule: Schedule) -> Dict[str, Any]:
        """
        将排班对象转换为字典

        Args:
            schedule: 排班对象

        Returns:
            排班字典
        """
        schedule_dict = {
            "schedule_id": str(schedule.id),
            "store_id": schedule.store_id,
            "schedule_date": schedule.schedule_date.isoformat(),
            "total_employees": schedule.total_employees,
            "total_hours": schedule.total_hours,
            "is_published": schedule.is_published,
            "published_by": schedule.published_by
        }

        # 添加班次信息
        if hasattr(schedule, "shifts") and schedule.shifts:
            schedule_dict["shifts"] = [
                {
                    "shift_id": str(shift.id),
                    "employee_id": shift.employee_id,
                    "shift_type": shift.shift_type,
                    "start_time": shift.start_time.isoformat(),
                    "end_time": shift.end_time.isoformat(),
                    "position": shift.position,
                    "is_confirmed": shift.is_confirmed,
                    "is_completed": shift.is_completed,
                    "notes": shift.notes
                }
                for shift in schedule.shifts
            ]
        else:
            schedule_dict["shifts"] = []

        return schedule_dict


# 创建全局服务实例
schedule_service = ScheduleService()
