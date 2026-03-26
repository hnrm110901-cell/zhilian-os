"""
活海鲜养殖管理 API

端点前缀: /api/v1/aquarium

功能:
  - 鱼缸 CRUD + 状态管理
  - 水质指标记录 + 异常预警
  - 活海鲜批次入缸登记
  - 死亡记录（自动计算损耗¥金额）
  - 每日巡检
  - 鱼缸仪表板 + 死亡率报告
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.services.aquarium_service import aquarium_service

router = APIRouter(prefix="/api/v1/aquarium", tags=["aquarium"])
logger = structlog.get_logger()


# ── Pydantic Schemas ─────────────────────────────────────────────────────────


class CreateTankRequest(BaseModel):
    store_id: str = Field(..., description="门店ID")
    name: str = Field(..., description="鱼缸名称", max_length=100)
    tank_type: str = Field(default="saltwater", description="类型: saltwater/freshwater/mixed")
    capacity_liters: float = Field(..., gt=0, description="容量（升）")
    location: Optional[str] = Field(None, description="位置描述")
    equipment_info: Optional[str] = Field(None, description="设备信息")
    notes: Optional[str] = None


class UpdateTankStatusRequest(BaseModel):
    status: str = Field(..., description="状态: active/maintenance/empty/decommissioned")
    notes: Optional[str] = None


class RecordWaterMetricsRequest(BaseModel):
    store_id: str
    temperature: Optional[float] = Field(None, description="水温 °C")
    ph: Optional[float] = Field(None, description="pH 值")
    dissolved_oxygen: Optional[float] = Field(None, description="溶解氧 mg/L")
    salinity: Optional[float] = Field(None, description="盐度 ‰")
    ammonia: Optional[float] = Field(None, description="氨氮 mg/L")
    nitrite: Optional[float] = Field(None, description="亚硝酸盐 mg/L")
    source: str = Field(default="manual", description="来源: manual/iot")
    recorded_by: Optional[str] = Field(None, description="记录人")
    notes: Optional[str] = None


class AddSeafoodBatchRequest(BaseModel):
    store_id: str
    species: str = Field(..., description="品种名", max_length=100)
    category: Optional[str] = Field(None, description="分类: 虾蟹类/贝类/鱼类")
    initial_quantity: int = Field(..., gt=0, description="入缸数量")
    initial_weight_g: Optional[int] = Field(None, description="入缸总重量（克）")
    unit: str = Field(default="只", description="计量单位")
    unit_cost_fen: int = Field(..., gt=0, description="单位成本（分）")
    cost_unit: str = Field(default="只", description="成本计量单位")
    supplier_name: Optional[str] = None
    supplier_contact: Optional[str] = None
    purchase_order_id: Optional[str] = None
    notes: Optional[str] = None


class RecordMortalityRequest(BaseModel):
    store_id: str
    dead_quantity: int = Field(..., gt=0, description="死亡数量")
    dead_weight_g: Optional[int] = Field(None, description="死亡重量（克）")
    reason: str = Field(default="unknown", description="原因: water_quality/disease/overcrowding/temperature/transport/natural/unknown")
    disposal: str = Field(default="discard", description="处理方式: discard/cook_staff/return/insurance")
    recorded_by: Optional[str] = None
    notes: Optional[str] = None


class DailyInspectionRequest(BaseModel):
    store_id: str
    inspector: str = Field(..., description="巡检人")
    inspection_date: Optional[str] = Field(None, description="巡检日期 YYYY-MM-DD")
    result: str = Field(default="normal", description="巡检结果: normal/warning/critical")
    tank_cleanliness: Optional[int] = Field(None, ge=1, le=10, description="清洁度 1-10")
    fish_activity: Optional[int] = Field(None, ge=1, le=10, description="活跃度 1-10")
    equipment_status: Optional[int] = Field(None, ge=1, le=10, description="设备状态 1-10")
    abnormal_description: Optional[str] = None
    action_taken: Optional[str] = None
    image_urls: Optional[str] = None
    notes: Optional[str] = None


# ── 鱼缸管理 ─────────────────────────────────────────────────────────────────


@router.post("/tanks", status_code=status.HTTP_201_CREATED)
async def create_tank(req: CreateTankRequest, db: AsyncSession = Depends(get_db)):
    """创建鱼缸"""
    result = await aquarium_service.create_tank(
        db,
        store_id=req.store_id,
        name=req.name,
        tank_type=req.tank_type,
        capacity_liters=req.capacity_liters,
        location=req.location,
        equipment_info=req.equipment_info,
        notes=req.notes,
    )
    await db.commit()
    return result


@router.get("/tanks")
async def list_tanks(
    store_id: str = Query(..., description="门店ID"),
    tank_status: Optional[str] = Query(None, alias="status", description="状态过滤"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """获取鱼缸列表"""
    return await aquarium_service.get_tanks(
        db, store_id=store_id, status=tank_status, skip=skip, limit=limit,
    )


@router.get("/tanks/{tank_id}")
async def get_tank(tank_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """获取单个鱼缸详情"""
    result = await aquarium_service.get_tank_by_id(db, tank_id=tank_id)
    if not result:
        raise HTTPException(status_code=404, detail="鱼缸不存在")
    return result


@router.patch("/tanks/{tank_id}/status")
async def update_tank_status(
    tank_id: uuid.UUID,
    req: UpdateTankStatusRequest,
    db: AsyncSession = Depends(get_db),
):
    """更新鱼缸状态"""
    result = await aquarium_service.update_tank_status(
        db, tank_id=tank_id, status=req.status, notes=req.notes,
    )
    if not result:
        raise HTTPException(status_code=404, detail="鱼缸不存在")
    await db.commit()
    return result


# ── 水质管理 ─────────────────────────────────────────────────────────────────


@router.post("/tanks/{tank_id}/water-metrics", status_code=status.HTTP_201_CREATED)
async def record_water_metrics(
    tank_id: uuid.UUID,
    req: RecordWaterMetricsRequest,
    db: AsyncSession = Depends(get_db),
):
    """记录水质指标（支持 IoT 自动采集和手动录入）"""
    result = await aquarium_service.record_water_metrics(
        db,
        tank_id=tank_id,
        store_id=req.store_id,
        temperature=req.temperature,
        ph=req.ph,
        dissolved_oxygen=req.dissolved_oxygen,
        salinity=req.salinity,
        ammonia=req.ammonia,
        nitrite=req.nitrite,
        source=req.source,
        recorded_by=req.recorded_by,
        notes=req.notes,
    )
    await db.commit()
    return result


@router.get("/water-alerts")
async def check_water_alerts(
    store_id: str = Query(..., description="门店ID"),
    tank_id: Optional[uuid.UUID] = Query(None, description="可选：指定鱼缸"),
    db: AsyncSession = Depends(get_db),
):
    """水质异常预警（检查所有活跃鱼缸的最新水质）"""
    alerts = await aquarium_service.check_water_alerts(
        db, store_id=store_id, tank_id=tank_id,
    )
    return {"alerts": alerts, "total": len(alerts)}


# ── 批次管理 ─────────────────────────────────────────────────────────────────


@router.post("/tanks/{tank_id}/batches", status_code=status.HTTP_201_CREATED)
async def add_seafood_batch(
    tank_id: uuid.UUID,
    req: AddSeafoodBatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """活海鲜入缸登记"""
    result = await aquarium_service.add_seafood_batch(
        db,
        tank_id=tank_id,
        store_id=req.store_id,
        species=req.species,
        category=req.category,
        initial_quantity=req.initial_quantity,
        initial_weight_g=req.initial_weight_g,
        unit=req.unit,
        unit_cost_fen=req.unit_cost_fen,
        cost_unit=req.cost_unit,
        supplier_name=req.supplier_name,
        supplier_contact=req.supplier_contact,
        purchase_order_id=req.purchase_order_id,
        notes=req.notes,
    )
    await db.commit()
    return result


# ── 死亡记录 ─────────────────────────────────────────────────────────────────


@router.post("/batches/{batch_id}/mortality", status_code=status.HTTP_201_CREATED)
async def record_mortality(
    batch_id: uuid.UUID,
    req: RecordMortalityRequest,
    db: AsyncSession = Depends(get_db),
):
    """记录海鲜死亡（自动计算损耗¥金额，更新批次存活数量）"""
    try:
        result = await aquarium_service.record_mortality(
            db,
            batch_id=batch_id,
            store_id=req.store_id,
            dead_quantity=req.dead_quantity,
            dead_weight_g=req.dead_weight_g,
            reason=req.reason,
            disposal=req.disposal,
            recorded_by=req.recorded_by,
            notes=req.notes,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/mortality-report")
async def get_mortality_report(
    store_id: str = Query(..., description="门店ID"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    species: Optional[str] = Query(None, description="品种过滤"),
    tank_id: Optional[uuid.UUID] = Query(None, description="鱼缸过滤"),
    db: AsyncSession = Depends(get_db),
):
    """死亡率报告（按品种/鱼缸/时间段）"""
    sd = date.fromisoformat(start_date) if start_date else None
    ed = date.fromisoformat(end_date) if end_date else None
    return await aquarium_service.get_mortality_report(
        db,
        store_id=store_id,
        start_date=sd,
        end_date=ed,
        species=species,
        tank_id=tank_id,
    )


# ── 巡检管理 ─────────────────────────────────────────────────────────────────


@router.post("/tanks/{tank_id}/inspections", status_code=status.HTTP_201_CREATED)
async def daily_inspection(
    tank_id: uuid.UUID,
    req: DailyInspectionRequest,
    db: AsyncSession = Depends(get_db),
):
    """每日巡检记录"""
    inspection_date_val = date.fromisoformat(req.inspection_date) if req.inspection_date else None
    result = await aquarium_service.daily_inspection(
        db,
        tank_id=tank_id,
        store_id=req.store_id,
        inspector=req.inspector,
        inspection_date=inspection_date_val,
        result=req.result,
        tank_cleanliness=req.tank_cleanliness,
        fish_activity=req.fish_activity,
        equipment_status=req.equipment_status,
        abnormal_description=req.abnormal_description,
        action_taken=req.action_taken,
        image_urls=req.image_urls,
        notes=req.notes,
    )
    await db.commit()
    return result


# ── 仪表板 ───────────────────────────────────────────────────────────────────


@router.get("/tanks/{tank_id}/dashboard")
async def get_tank_dashboard(
    tank_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """鱼缸仪表板（当前品种/数量/水质/健康度评分）"""
    return await aquarium_service.get_tank_dashboard(db, tank_id=tank_id)
