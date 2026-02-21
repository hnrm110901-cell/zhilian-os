"""
Reservation Service with Database Integration
Provides reservation management using real database data
"""
from datetime import datetime, date, time, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import select, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from src.core.database import get_db_session
from src.models import Reservation, Store
from src.models.reservation import ReservationStatus, ReservationType
from src.repositories import ReservationRepository


class ReservationService:
    """Reservation service using database"""

    def __init__(self, store_id: str = "STORE001"):
        self.store_id = store_id

    async def create_reservation(
        self,
        customer_name: str,
        customer_phone: str,
        reservation_date: str,
        reservation_time: str,
        party_size: int,
        reservation_type: str = "regular",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a new reservation in database

        Args:
            customer_name: Customer name
            customer_phone: Customer phone
            reservation_date: Reservation date (YYYY-MM-DD)
            reservation_time: Reservation time (HH:MM)
            party_size: Number of guests
            reservation_type: Type of reservation
            **kwargs: Additional fields

        Returns:
            Created reservation data
        """
        async with get_db_session() as session:
            # Parse date and time
            res_date = date.fromisoformat(reservation_date)
            res_time = time.fromisoformat(reservation_time)

            # Generate reservation ID
            reservation_id = f"RES_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6].upper()}"

            # Create reservation
            reservation = Reservation(
                id=reservation_id,
                store_id=self.store_id,
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_email=kwargs.get("customer_email"),
                reservation_type=ReservationType(reservation_type),
                reservation_date=res_date,
                reservation_time=res_time,
                party_size=party_size,
                table_number=kwargs.get("table_number"),
                room_name=kwargs.get("room_name"),
                status=ReservationStatus.PENDING,
                special_requests=kwargs.get("special_requests"),
                dietary_restrictions=kwargs.get("dietary_restrictions"),
                banquet_details=kwargs.get("banquet_details", {}),
                estimated_budget=kwargs.get("estimated_budget"),
                notes=kwargs.get("notes"),
            )

            session.add(reservation)
            await session.flush()

            return {
                "reservation_id": reservation.id,
                "customer_name": reservation.customer_name,
                "customer_phone": reservation.customer_phone,
                "reservation_date": reservation.reservation_date.isoformat(),
                "reservation_time": reservation.reservation_time.isoformat(),
                "party_size": reservation.party_size,
                "status": reservation.status.value,
                "reservation_type": reservation.reservation_type.value,
                "table_number": reservation.table_number,
                "created_at": reservation.created_at.isoformat(),
            }

    async def get_reservations(
        self,
        reservation_date: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get reservations from database

        Args:
            reservation_date: Filter by date (YYYY-MM-DD)
            status: Filter by status
            limit: Maximum number of results

        Returns:
            List of reservations
        """
        async with get_db_session() as session:
            query = select(Reservation).where(Reservation.store_id == self.store_id)

            if reservation_date:
                res_date = date.fromisoformat(reservation_date)
                query = query.where(Reservation.reservation_date == res_date)

            if status:
                query = query.where(Reservation.status == status)

            query = query.order_by(
                Reservation.reservation_date,
                Reservation.reservation_time
            ).limit(limit)

            result = await session.execute(query)
            reservations = result.scalars().all()

            return [self._reservation_to_dict(r) for r in reservations]

    async def get_reservation_by_id(
        self,
        reservation_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get reservation by ID"""
        async with get_db_session() as session:
            result = await session.execute(
                select(Reservation).where(Reservation.id == reservation_id)
            )
            reservation = result.scalar_one_or_none()

            if reservation:
                return self._reservation_to_dict(reservation)
            return None

    async def update_reservation_status(
        self,
        reservation_id: str,
        status: str,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update reservation status

        Args:
            reservation_id: Reservation ID
            status: New status
            notes: Optional notes

        Returns:
            Updated reservation data
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(Reservation).where(Reservation.id == reservation_id)
            )
            reservation = result.scalar_one_or_none()

            if not reservation:
                raise ValueError(f"Reservation {reservation_id} not found")

            reservation.status = ReservationStatus(status)
            if notes:
                reservation.notes = notes

            await session.flush()

            return self._reservation_to_dict(reservation)

    async def assign_table(
        self,
        reservation_id: str,
        table_number: str
    ) -> Dict[str, Any]:
        """
        Assign table to reservation

        Args:
            reservation_id: Reservation ID
            table_number: Table number

        Returns:
            Updated reservation data
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(Reservation).where(Reservation.id == reservation_id)
            )
            reservation = result.scalar_one_or_none()

            if not reservation:
                raise ValueError(f"Reservation {reservation_id} not found")

            reservation.table_number = table_number

            await session.flush()

            return self._reservation_to_dict(reservation)

    async def get_upcoming_reservations(
        self,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Get upcoming reservations

        Args:
            days: Number of days to look ahead

        Returns:
            List of upcoming reservations
        """
        async with get_db_session() as session:
            today = date.today()
            end_date = today + timedelta(days=days)

            result = await session.execute(
                select(Reservation).where(
                    and_(
                        Reservation.store_id == self.store_id,
                        Reservation.reservation_date >= today,
                        Reservation.reservation_date <= end_date,
                        Reservation.status.in_([
                            ReservationStatus.PENDING,
                            ReservationStatus.CONFIRMED
                        ])
                    )
                ).order_by(
                    Reservation.reservation_date,
                    Reservation.reservation_time
                )
            )
            reservations = result.scalars().all()

            return [self._reservation_to_dict(r) for r in reservations]

    async def cancel_reservation(
        self,
        reservation_id: str,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel a reservation

        Args:
            reservation_id: Reservation ID
            reason: Cancellation reason

        Returns:
            Updated reservation data
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(Reservation).where(Reservation.id == reservation_id)
            )
            reservation = result.scalar_one_or_none()

            if not reservation:
                raise ValueError(f"Reservation {reservation_id} not found")

            reservation.status = ReservationStatus.CANCELLED
            if reason:
                reservation.notes = f"取消原因: {reason}"

            await session.flush()

            return self._reservation_to_dict(reservation)

    async def get_reservation_statistics(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get reservation statistics

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Statistics data
        """
        async with get_db_session() as session:
            # Parse dates
            if not end_date:
                end_dt = date.today()
            else:
                end_dt = date.fromisoformat(end_date)

            if not start_date:
                start_dt = end_dt - timedelta(days=30)
            else:
                start_dt = date.fromisoformat(start_date)

            # Get all reservations in date range
            result = await session.execute(
                select(Reservation).where(
                    and_(
                        Reservation.store_id == self.store_id,
                        Reservation.reservation_date >= start_dt,
                        Reservation.reservation_date <= end_dt
                    )
                )
            )
            reservations = result.scalars().all()

            # Calculate statistics
            total = len(reservations)
            by_status = {}
            by_type = {}
            total_guests = 0

            for res in reservations:
                # Count by status
                status = res.status.value
                by_status[status] = by_status.get(status, 0) + 1

                # Count by type
                res_type = res.reservation_type.value
                by_type[res_type] = by_type.get(res_type, 0) + 1

                # Sum guests
                total_guests += res.party_size

            return {
                "period_start": start_dt.isoformat(),
                "period_end": end_dt.isoformat(),
                "total_reservations": total,
                "total_guests": total_guests,
                "average_party_size": total_guests / total if total > 0 else 0,
                "by_status": by_status,
                "by_type": by_type,
                "confirmed_rate": by_status.get("confirmed", 0) / total if total > 0 else 0,
                "cancellation_rate": by_status.get("cancelled", 0) / total if total > 0 else 0,
            }

    def _reservation_to_dict(self, reservation: Reservation) -> Dict[str, Any]:
        """Convert reservation model to dictionary"""
        return {
            "reservation_id": reservation.id,
            "store_id": reservation.store_id,
            "customer_name": reservation.customer_name,
            "customer_phone": reservation.customer_phone,
            "customer_email": reservation.customer_email,
            "reservation_type": reservation.reservation_type.value,
            "reservation_date": reservation.reservation_date.isoformat(),
            "reservation_time": reservation.reservation_time.isoformat(),
            "party_size": reservation.party_size,
            "table_number": reservation.table_number,
            "room_name": reservation.room_name,
            "status": reservation.status.value,
            "special_requests": reservation.special_requests,
            "dietary_restrictions": reservation.dietary_restrictions,
            "banquet_details": reservation.banquet_details,
            "estimated_budget": reservation.estimated_budget,
            "notes": reservation.notes,
            "created_at": reservation.created_at.isoformat(),
            "updated_at": reservation.updated_at.isoformat(),
        }


# Create singleton instance
reservation_service = ReservationService()
