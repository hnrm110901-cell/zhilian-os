"""
桌台平面图API
- 桌台CRUD + 布局批量保存
- 实时状态（JOIN今日预订）
- 分配预订到桌
"""

import uuid
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.floor_plan import TableDefinition, TableShape, TableStatus
from ..models.reservation import Reservation, ReservationStatus
from ..models.user import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/floor-plan", tags=["floor_plan"])


# ── Pydantic Models ──


class TableResponse(BaseModel):
    id: str
    store_id: str
    table_number: str
    table_type: str
    min_capacity: int
    max_capacity: int
    pos_x: float
    pos_y: float
    width: float
    height: float
    rotation: float
    shape: str
    floor: int
    area_name: str
    status: str
    is_active: bool


class TableRealtimeResponse(TableResponse):
    current_reservation: Optional[Dict[str, Any]] = None
    realtime_status: str = "available"


class TableLayoutItem(BaseModel):
    id: Optional[str] = None  # None = 新建
    table_number: str
    table_type: str = "大厅"
    min_capacity: int = 1
    max_capacity: int = 4
    pos_x: float
    pos_y: float
    width: float = 8.0
    height: float = 8.0
    rotation: float = 0.0
    shape: str = "rect"
    floor: int = 1
    area_name: str = ""
    is_active: bool = True


class BatchLayoutRequest(BaseModel):
    tables: List[TableLayoutItem]
    deleted_ids: List[str] = []


class AssignReservationRequest(BaseModel):
    reservation_id: str


def _to_response(t: TableDefinition) -> TableResponse:
    return TableResponse(
        id=str(t.id),
        store_id=t.store_id,
        table_number=t.table_number,
        table_type=t.table_type or "大厅",
        min_capacity=t.min_capacity or 1,
        max_capacity=t.max_capacity or 4,
        pos_x=t.pos_x or 50.0,
        pos_y=t.pos_y or 50.0,
        width=t.width or 8.0,
        height=t.height or 8.0,
        rotation=t.rotation or 0.0,
        shape=t.shape.value if hasattr(t.shape, "value") else str(t.shape or "rect"),
        floor=t.floor or 1,
        area_name=t.area_name or "",
        status=t.status.value if hasattr(t.status, "value") else str(t.status or "available"),
        is_active=t.is_active if t.is_active is not None else True,
    )


# ── Endpoints ──


@router.get("/{store_id}/tables", response_model=List[TableResponse])
async def get_tables(
    store_id: str,
    floor: Optional[int] = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取门店桌台列表"""
    query = select(TableDefinition).where(
        and_(
            TableDefinition.store_id == store_id,
            TableDefinition.is_active == True,
        )
    )
    if floor is not None:
        query = query.where(TableDefinition.floor == floor)
    query = query.order_by(TableDefinition.floor, TableDefinition.table_number)

    result = await session.execute(query)
    return [_to_response(t) for t in result.scalars().all()]


@router.get("/{store_id}/tables/realtime", response_model=List[TableRealtimeResponse])
async def get_tables_realtime(
    store_id: str,
    floor: Optional[int] = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取桌台实时状态（JOIN今日预订+在座订单）"""
    # 获取所有桌台
    query = select(TableDefinition).where(
        and_(
            TableDefinition.store_id == store_id,
            TableDefinition.is_active == True,
        )
    )
    if floor is not None:
        query = query.where(TableDefinition.floor == floor)

    result = await session.execute(query)
    tables = result.scalars().all()

    # 获取今日预订
    today = date.today()
    res_result = await session.execute(
        select(Reservation).where(
            and_(
                Reservation.store_id == store_id,
                Reservation.reservation_date == today,
                Reservation.status.in_(
                    [
                        ReservationStatus.PENDING,
                        ReservationStatus.CONFIRMED,
                        ReservationStatus.ARRIVED,
                        ReservationStatus.SEATED,
                    ]
                ),
            )
        )
    )
    reservations = res_result.scalars().all()

    # 按桌号索引预订
    res_by_table: Dict[str, Reservation] = {}
    for r in reservations:
        if r.table_number:
            res_by_table[r.table_number] = r

    # 构建实时响应
    responses = []
    for t in tables:
        base = _to_response(t)
        reservation = res_by_table.get(t.table_number)

        # 计算实时状态
        if t.status == TableStatus.MAINTENANCE:
            realtime_status = "maintenance"
        elif reservation:
            if reservation.status == ReservationStatus.SEATED:
                realtime_status = "occupied"
            else:
                realtime_status = "reserved"
        else:
            realtime_status = "available"

        current_res = None
        if reservation:
            current_res = {
                "id": reservation.id,
                "customer_name": reservation.customer_name,
                "party_size": reservation.party_size,
                "time": reservation.reservation_time.strftime("%H:%M") if reservation.reservation_time else "",
                "status": reservation.status.value if hasattr(reservation.status, "value") else str(reservation.status),
            }

        responses.append(
            TableRealtimeResponse(
                **base.model_dump(),
                current_reservation=current_res,
                realtime_status=realtime_status,
            )
        )

    return responses


@router.put("/{store_id}/tables/batch")
async def batch_save_layout(
    store_id: str,
    req: BatchLayoutRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """批量保存桌台布局（拖拽后）"""
    # 删除标记的桌台
    for del_id in req.deleted_ids:
        result = await session.execute(
            select(TableDefinition).where(
                and_(
                    TableDefinition.id == del_id,
                    TableDefinition.store_id == store_id,
                )
            )
        )
        table = result.scalar_one_or_none()
        if table:
            table.is_active = False

    # 创建或更新桌台
    saved = []
    for item in req.tables:
        if item.id:
            # 更新
            result = await session.execute(
                select(TableDefinition).where(
                    and_(
                        TableDefinition.id == item.id,
                        TableDefinition.store_id == store_id,
                    )
                )
            )
            table = result.scalar_one_or_none()
            if table:
                table.table_number = item.table_number
                table.table_type = item.table_type
                table.min_capacity = item.min_capacity
                table.max_capacity = item.max_capacity
                table.pos_x = item.pos_x
                table.pos_y = item.pos_y
                table.width = item.width
                table.height = item.height
                table.rotation = item.rotation
                table.shape = TableShape(item.shape)
                table.floor = item.floor
                table.area_name = item.area_name
                table.is_active = item.is_active
                saved.append(str(table.id))
        else:
            # 新建
            table = TableDefinition(
                store_id=store_id,
                table_number=item.table_number,
                table_type=item.table_type,
                min_capacity=item.min_capacity,
                max_capacity=item.max_capacity,
                pos_x=item.pos_x,
                pos_y=item.pos_y,
                width=item.width,
                height=item.height,
                rotation=item.rotation,
                shape=TableShape(item.shape),
                floor=item.floor,
                area_name=item.area_name,
                is_active=item.is_active,
            )
            session.add(table)
            saved.append("new")

    await session.commit()
    logger.info("floor_plan_layout_saved", store_id=store_id, count=len(saved))
    return {"success": True, "saved": len(saved), "deleted": len(req.deleted_ids)}


@router.post("/{store_id}/tables/{table_id}/assign")
async def assign_reservation_to_table(
    store_id: str,
    table_id: str,
    req: AssignReservationRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """分配预订到桌"""
    # 查找桌台
    result = await session.execute(
        select(TableDefinition).where(
            and_(
                TableDefinition.id == table_id,
                TableDefinition.store_id == store_id,
            )
        )
    )
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=404, detail="桌台不存在")

    # 查找预订
    res_result = await session.execute(select(Reservation).where(Reservation.id == req.reservation_id))
    reservation = res_result.scalar_one_or_none()
    if not reservation:
        raise HTTPException(status_code=404, detail="预订不存在")

    # 分配桌号
    reservation.table_number = table.table_number
    await session.commit()

    logger.info("table_assigned", table_number=table.table_number, reservation_id=req.reservation_id)
    return {
        "success": True,
        "table_number": table.table_number,
        "reservation_id": req.reservation_id,
    }
