"""
Database Repository Layer
Provides convenient methods for querying database models
"""

import os
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models import (
    KPI,
    InventoryItem,
    InventoryTransaction,
    KPIRecord,
    Order,
    OrderItem,
    Reservation,
    Schedule,
    Shift,
    Store,
    User,
)
from src.models.hr.person import Person
from src.models.hr.employment_assignment import EmploymentAssignment
from src.models.reservation import ReservationStatus


class UserRepository:
    """User repository"""

    @staticmethod
    async def get_by_username(session: AsyncSession, username: str) -> Optional[User]:
        """Get user by username"""
        result = await session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_email(session: AsyncSession, email: str) -> Optional[User]:
        """Get user by email"""
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()


class StoreRepository:
    """Store repository"""

    @staticmethod
    async def get_by_id(session: AsyncSession, store_id: str) -> Optional[Store]:
        """Get store by ID"""
        result = await session.execute(select(Store).where(Store.id == store_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_active(session: AsyncSession) -> List[Store]:
        """Get all active stores"""
        result = await session.execute(select(Store).where(Store.is_active == True))
        return list(result.scalars().all())


class EmployeeRepository:
    """Employee repository — 已迁移到 Person + EmploymentAssignment

    get_by_store / get_by_id 现在查询 Person 表（通过 legacy_employee_id 桥接）。
    返回 Person 对象；需要 position 等字段时，调用方应 outerjoin EmploymentAssignment。
    """

    @staticmethod
    async def get_by_store(session: AsyncSession, store_id: str) -> List[Person]:
        """获取门店在职人员（返回 Person 列表）"""
        result = await session.execute(
            select(Person).where(
                and_(Person.store_id == store_id, Person.is_active.is_(True))
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(session: AsyncSession, employee_id: str) -> Optional[Person]:
        """按 legacy_employee_id 查找人员（返回 Person 或 None）"""
        result = await session.execute(
            select(Person).where(Person.legacy_employee_id == employee_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_with_assignment(
        session: AsyncSession, employee_id: str,
    ) -> Optional[tuple]:
        """按 legacy_employee_id 查找人员及在岗关系，返回 (Person, EmploymentAssignment|None)"""
        result = await session.execute(
            select(Person, EmploymentAssignment)
            .outerjoin(
                EmploymentAssignment,
                and_(
                    EmploymentAssignment.person_id == Person.id,
                    EmploymentAssignment.status == "active",
                ),
            )
            .where(Person.legacy_employee_id == employee_id)
        )
        return result.first()  # Row(Person, EA|None) or None


class InventoryRepository:
    """Inventory repository"""

    @staticmethod
    async def get_by_store(session: AsyncSession, store_id: str) -> List[InventoryItem]:
        """Get all inventory items for a store"""
        result = await session.execute(select(InventoryItem).where(InventoryItem.store_id == store_id))
        return list(result.scalars().all())

    @staticmethod
    async def get_low_stock(session: AsyncSession, store_id: str) -> List[InventoryItem]:
        """Get low stock items"""
        result = await session.execute(
            select(InventoryItem).where(
                and_(InventoryItem.store_id == store_id, InventoryItem.current_quantity <= InventoryItem.min_quantity)
            )
        )
        return list(result.scalars().all())


class KPIRepository:
    """KPI repository"""

    @staticmethod
    async def get_all_active(session: AsyncSession) -> List[KPI]:
        """Get all active KPIs"""
        result = await session.execute(select(KPI).where(KPI.is_active == "true"))
        return list(result.scalars().all())

    @staticmethod
    async def get_records_by_date_range(
        session: AsyncSession, store_id: str, start_date: date, end_date: date
    ) -> List[KPIRecord]:
        """Get KPI records for a date range"""
        result = await session.execute(
            select(KPIRecord)
            .where(
                and_(KPIRecord.store_id == store_id, KPIRecord.record_date >= start_date, KPIRecord.record_date <= end_date)
            )
            .order_by(KPIRecord.record_date)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_latest_records(
        session: AsyncSession, store_id: str, limit: int = int(os.getenv("REPO_KPI_LIMIT", "30"))
    ) -> List[KPIRecord]:
        """Get latest KPI records"""
        result = await session.execute(
            select(KPIRecord).where(KPIRecord.store_id == store_id).order_by(desc(KPIRecord.record_date)).limit(limit)
        )
        return list(result.scalars().all())


class OrderRepository:
    """Order repository"""

    @staticmethod
    async def get_by_store(
        session: AsyncSession, store_id: str, limit: int = int(os.getenv("REPO_ORDER_LIMIT", "100"))
    ) -> List[Order]:
        """Get orders for a store"""
        result = await session.execute(
            select(Order).where(Order.store_id == store_id).order_by(desc(Order.order_time)).limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_status(session: AsyncSession, store_id: str, status: str) -> List[Order]:
        """Get orders by status"""
        result = await session.execute(
            select(Order).where(and_(Order.store_id == store_id, Order.status == status)).order_by(desc(Order.order_time))
        )
        return list(result.scalars().all())


class ScheduleRepository:
    """Schedule repository"""

    @staticmethod
    async def get_by_date(session: AsyncSession, store_id: str, schedule_date: date) -> Optional[Schedule]:
        """Get schedule for a specific date"""
        result = await session.execute(
            select(Schedule).where(and_(Schedule.store_id == store_id, Schedule.schedule_date == schedule_date))
        )
        return result.scalar_one_or_none()


class ReservationRepository:
    """Reservation repository"""

    @staticmethod
    async def get_by_date(session: AsyncSession, store_id: str, reservation_date: date) -> List[Reservation]:
        """Get reservations for a specific date"""
        result = await session.execute(
            select(Reservation)
            .where(and_(Reservation.store_id == store_id, Reservation.reservation_date == reservation_date))
            .order_by(Reservation.reservation_time)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_upcoming(session: AsyncSession, store_id: str, days: int = 7) -> List[Reservation]:
        """Get upcoming reservations"""
        today = date.today()
        result = await session.execute(
            select(Reservation)
            .where(
                and_(
                    Reservation.store_id == store_id,
                    Reservation.reservation_date >= today,
                    Reservation.status.in_([ReservationStatus.PENDING, ReservationStatus.CONFIRMED]),
                )
            )
            .order_by(Reservation.reservation_date, Reservation.reservation_time)
        )
        return list(result.scalars().all())
