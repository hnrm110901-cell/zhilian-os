"""
经营目标管理 API — OKR + BSC 四维度目标体系

端点：
  POST /api/v1/objectives                    — 创建经营目标
  GET  /api/v1/objectives/{store_id}         — 门店目标列表
  GET  /api/v1/objectives/{store_id}/dashboard — BSC四维度看板
  PUT  /api/v1/objectives/{objective_id}     — 更新目标
  POST /api/v1/objectives/cascade            — 集团目标级联分解
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user, validate_store_brand
from ..models.user import User

logger = structlog.get_logger()
router = APIRouter()


# ── Pydantic Schemas ──────────────────────────────────────────────────────────


class CreateObjectiveRequest(BaseModel):
    brand_id: str
    store_id: Optional[str] = None
    parent_id: Optional[str] = None
    level: str = "store"
    fiscal_year: int
    period_type: str  # annual | quarter | month
    period_value: int = 0
    objective_name: str
    metric_code: str  # revenue | gross_margin | nps | ...
    target_value: int  # 分
    floor_value: Optional[int] = None
    stretch_value: Optional[int] = None
    unit: str = "fen"
    bsc_dimension: str = "financial"
    owner_id: Optional[str] = None


class UpdateObjectiveRequest(BaseModel):
    objective_name: Optional[str] = None
    target_value: Optional[int] = None
    floor_value: Optional[int] = None
    stretch_value: Optional[int] = None
    actual_value: Optional[int] = None
    status: Optional[str] = None


class CreateKeyResultRequest(BaseModel):
    objective_id: str
    brand_id: str
    kr_name: str
    metric_code: str
    target_value: int
    unit: str = "fen"
    weight: float = 1.0
    owner_id: Optional[str] = None


class CascadeRequest(BaseModel):
    """集团目标级联分解请求"""
    brand_id: str
    source_objective_id: str
    target_store_ids: List[str]
    split_method: str = "equal"  # equal | by_seats | by_revenue


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/objectives", summary="创建经营目标", tags=["objectives"])
async def create_objective(
    req: CreateObjectiveRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """创建经营目标（支持年/季/月，支持集团/区域/门店级别）"""
    # 品牌归属校验：非平台管理员只能为自己品牌创建目标
    if current_user.brand_id and req.brand_id != current_user.brand_id:
        raise HTTPException(status_code=403, detail="无权为其他品牌创建目标")
    if req.store_id:
        await validate_store_brand(req.store_id, current_user)

    result = await db.execute(
        text("""
            INSERT INTO business_objectives (
                brand_id, store_id, parent_id, level,
                fiscal_year, period_type, period_value,
                objective_name, metric_code, target_value, floor_value, stretch_value,
                unit, bsc_dimension, owner_id
            ) VALUES (
                :brand_id, :store_id, :parent_id::uuid, :level,
                :fiscal_year, :period_type, :period_value,
                :name, :metric, :target, :floor, :stretch,
                :unit, :bsc, :owner::uuid
            )
            RETURNING id, created_at
        """),
        {
            "brand_id": req.brand_id,
            "store_id": req.store_id,
            "parent_id": req.parent_id,
            "level": req.level,
            "fiscal_year": req.fiscal_year,
            "period_type": req.period_type,
            "period_value": req.period_value,
            "name": req.objective_name,
            "metric": req.metric_code,
            "target": req.target_value,
            "floor": req.floor_value,
            "stretch": req.stretch_value,
            "unit": req.unit,
            "bsc": req.bsc_dimension,
            "owner": req.owner_id,
        },
    )
    row = result.mappings().first()
    await db.commit()

    logger.info(
        "objective_created",
        objective_id=str(row["id"]),
        brand_id=req.brand_id,
        metric=req.metric_code,
        target_yuan=req.target_value / 100 if req.unit == "fen" else req.target_value,
    )

    return {
        "id": str(row["id"]),
        "status": "created",
        "objective_name": req.objective_name,
        "target_yuan": req.target_value / 100 if req.unit == "fen" else req.target_value,
    }


@router.get("/objectives/{store_id}", summary="门店目标列表", tags=["objectives"])
async def list_objectives(
    store_id: str,
    fiscal_year: int = Query(default=2026),
    period_type: Optional[str] = Query(default=None),
    bsc_dimension: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """获取门店经营目标列表（支持按周期/BSC维度筛选）"""
    await validate_store_brand(store_id, current_user)

    conditions = ["store_id = :sid", "fiscal_year = :year", "status = 'active'"]
    params: Dict[str, Any] = {"sid": store_id, "year": fiscal_year}

    if period_type:
        conditions.append("period_type = :pt")
        params["pt"] = period_type
    if bsc_dimension:
        conditions.append("bsc_dimension = :bsc")
        params["bsc"] = bsc_dimension

    where_clause = " AND ".join(conditions)
    result = await db.execute(
        text(f"""
            SELECT
                id, objective_name, metric_code,
                period_type, period_value, bsc_dimension,
                target_value, floor_value, stretch_value, actual_value, unit,
                CASE WHEN target_value > 0
                    THEN ROUND(actual_value::numeric / target_value * 100, 1)
                    ELSE 0
                END AS achievement_pct,
                owner_id, created_at
            FROM business_objectives
            WHERE {where_clause}
            ORDER BY bsc_dimension, period_type, period_value
        """),
        params,
    )

    rows = []
    for r in result.mappings():
        row = dict(r)
        row["id"] = str(row["id"])
        if row["unit"] == "fen":
            row["target_yuan"] = row["target_value"] / 100
            row["actual_yuan"] = row["actual_value"] / 100
        if row.get("owner_id"):
            row["owner_id"] = str(row["owner_id"])
        rows.append(row)

    return {"store_id": store_id, "fiscal_year": fiscal_year, "objectives": rows}


@router.get(
    "/objectives/{store_id}/dashboard",
    summary="BSC四维度目标达成看板",
    tags=["objectives"],
)
async def objective_dashboard(
    store_id: str,
    fiscal_year: int = Query(default=2026),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    BSC四维度目标达成看板

    返回按 financial/customer/process/learning 分组的目标达成数据，
    包含总体达成率和各维度达成率。
    """
    await validate_store_brand(store_id, current_user)

    result = await db.execute(
        text("""
            SELECT
                bsc_dimension,
                objective_name,
                metric_code,
                target_value,
                actual_value,
                unit,
                period_type,
                period_value,
                CASE WHEN target_value > 0
                    THEN ROUND(actual_value::numeric / target_value * 100, 1)
                    ELSE 0
                END AS achievement_pct
            FROM business_objectives
            WHERE store_id = :sid AND fiscal_year = :year AND status = 'active'
            ORDER BY bsc_dimension, period_type, period_value
        """),
        {"sid": store_id, "year": fiscal_year},
    )

    rows = [dict(r) for r in result.mappings()]

    # 按BSC维度分组
    dashboard: Dict[str, list] = {
        "financial": [],
        "customer": [],
        "process": [],
        "learning": [],
    }
    for r in rows:
        dim = r.get("bsc_dimension", "financial")
        if r["unit"] == "fen":
            r["target_yuan"] = r["target_value"] / 100
            r["actual_yuan"] = r["actual_value"] / 100
        if dim in dashboard:
            dashboard[dim].append(r)

    # 各维度达成率
    dimension_scores = {}
    for dim, items in dashboard.items():
        if items:
            avg_pct = sum(float(i["achievement_pct"]) for i in items) / len(items)
            dimension_scores[dim] = round(avg_pct, 1)
        else:
            dimension_scores[dim] = 0.0

    overall = (
        round(sum(float(r["achievement_pct"]) for r in rows) / len(rows), 1)
        if rows
        else 0.0
    )

    return {
        "store_id": store_id,
        "fiscal_year": fiscal_year,
        "bsc_dashboard": dashboard,
        "dimension_scores": dimension_scores,
        "overall_achievement_pct": overall,
    }


@router.put("/objectives/{objective_id}", summary="更新经营目标", tags=["objectives"])
async def update_objective(
    objective_id: str,
    req: UpdateObjectiveRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """更新经营目标字段"""
    # 归属校验：确认目标属于当前用户品牌
    check = await db.execute(
        text("SELECT brand_id, store_id FROM business_objectives WHERE id = :oid::uuid"),
        {"oid": objective_id},
    )
    obj_row = check.mappings().first()
    if not obj_row:
        raise HTTPException(status_code=404, detail="目标不存在")
    if current_user.brand_id and obj_row["brand_id"] != current_user.brand_id:
        raise HTTPException(status_code=403, detail="无权修改其他品牌的目标")

    updates = []
    params: Dict[str, Any] = {"oid": objective_id}

    if req.objective_name is not None:
        updates.append("objective_name = :name")
        params["name"] = req.objective_name
    if req.target_value is not None:
        updates.append("target_value = :target")
        params["target"] = req.target_value
    if req.floor_value is not None:
        updates.append("floor_value = :floor")
        params["floor"] = req.floor_value
    if req.stretch_value is not None:
        updates.append("stretch_value = :stretch")
        params["stretch"] = req.stretch_value
    if req.actual_value is not None:
        updates.append("actual_value = :actual")
        params["actual"] = req.actual_value
    if req.status is not None:
        updates.append("status = :status")
        params["status"] = req.status

    if not updates:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")

    updates.append("updated_at = NOW()")

    # 白名单列名拼接（列名来自硬编码，非用户输入，安全）
    allowed_columns = {
        "objective_name", "target_value", "floor_value",
        "stretch_value", "actual_value", "status", "updated_at",
    }
    for clause in updates:
        col = clause.split("=")[0].strip()
        if col not in allowed_columns:
            raise HTTPException(status_code=400, detail=f"不允许更新的字段: {col}")

    set_clause = ", ".join(updates)
    sql = "UPDATE business_objectives SET " + set_clause + " WHERE id = :oid::uuid"

    await db.execute(text(sql), params)
    await db.commit()

    return {"id": objective_id, "status": "updated"}


@router.post("/objectives/cascade", summary="集团目标级联分解", tags=["objectives"])
async def cascade_objectives(
    req: CascadeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    将集团/品牌级目标自动分解到多个门店

    分解方式：
      - equal: 平均分配
      - by_seats: 按座位数加权
      - by_revenue: 按历史营收加权
    """
    # 品牌归属校验
    if current_user.brand_id and req.brand_id != current_user.brand_id:
        raise HTTPException(status_code=403, detail="无权操作其他品牌的目标")

    # 读取源目标
    src = await db.execute(
        text("SELECT * FROM business_objectives WHERE id = :oid::uuid"),
        {"oid": req.source_objective_id},
    )
    source = src.mappings().first()
    if not source:
        raise HTTPException(status_code=404, detail="源目标不存在")

    total_target = source["target_value"]
    store_count = len(req.target_store_ids)

    if store_count == 0:
        raise HTTPException(status_code=400, detail="目标门店列表不能为空")

    # 计算分配权重
    if req.split_method == "by_seats":
        seats_result = await db.execute(
            text("""
                SELECT id, COALESCE(seats, 50) AS seats
                FROM stores WHERE id = ANY(:sids) AND is_active = TRUE
            """),
            {"sids": req.target_store_ids},
        )
        store_seats = {str(r["id"]): r["seats"] for r in seats_result.mappings()}
        total_seats = sum(store_seats.values()) or 1
        weights = {sid: store_seats.get(sid, 50) / total_seats for sid in req.target_store_ids}
    elif req.split_method == "by_revenue":
        rev_result = await db.execute(
            text("""
                SELECT store_id, COALESCE(SUM(revenue_fen), 0) AS rev
                FROM operation_snapshots
                WHERE store_id = ANY(:sids) AND period_type = 'monthly'
                GROUP BY store_id
            """),
            {"sids": req.target_store_ids},
        )
        store_rev = {r["store_id"]: r["rev"] for r in rev_result.mappings()}
        total_rev = sum(store_rev.values()) or 1
        weights = {sid: store_rev.get(sid, 0) / total_rev for sid in req.target_store_ids}
    else:
        weights = {sid: 1.0 / store_count for sid in req.target_store_ids}

    # 创建子目标
    created = []
    for sid in req.target_store_ids:
        store_target = int(total_target * weights[sid])
        await db.execute(
            text("""
                INSERT INTO business_objectives (
                    brand_id, store_id, parent_id, level,
                    fiscal_year, period_type, period_value,
                    objective_name, metric_code, target_value, unit, bsc_dimension
                ) VALUES (
                    :brand, :sid, :parent::uuid, 'store',
                    :year, :ptype, :pval,
                    :name, :metric, :target, :unit, :bsc
                )
            """),
            {
                "brand": req.brand_id,
                "sid": sid,
                "parent": req.source_objective_id,
                "year": source["fiscal_year"],
                "ptype": source["period_type"],
                "pval": source["period_value"],
                "name": source["objective_name"],
                "metric": source["metric_code"],
                "target": store_target,
                "unit": source["unit"],
                "bsc": source["bsc_dimension"],
            },
        )
        created.append({
            "store_id": sid,
            "target_value": store_target,
            "target_yuan": store_target / 100 if source["unit"] == "fen" else store_target,
            "weight_pct": round(weights[sid] * 100, 1),
        })

    await db.commit()

    logger.info(
        "objectives_cascaded",
        source_id=req.source_objective_id,
        store_count=len(created),
        method=req.split_method,
    )

    return {
        "source_objective_id": req.source_objective_id,
        "split_method": req.split_method,
        "stores": created,
    }


# ── Key Results 端点 ──────────────────────────────────────────────────────────


@router.post("/objectives/kr", summary="添加关键结果(KR)", tags=["objectives"])
async def create_key_result(
    req: CreateKeyResultRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """为目标添加关键结果"""
    # 品牌归属校验
    if current_user.brand_id and req.brand_id != current_user.brand_id:
        raise HTTPException(status_code=403, detail="无权操作其他品牌的目标")

    result = await db.execute(
        text("""
            INSERT INTO objective_key_results (
                objective_id, brand_id, kr_name, metric_code,
                target_value, unit, weight, owner_id
            ) VALUES (
                :oid::uuid, :brand, :name, :metric,
                :target, :unit, :weight, :owner::uuid
            )
            RETURNING id
        """),
        {
            "oid": req.objective_id,
            "brand": req.brand_id,
            "name": req.kr_name,
            "metric": req.metric_code,
            "target": req.target_value,
            "unit": req.unit,
            "weight": req.weight,
            "owner": req.owner_id,
        },
    )
    row = result.mappings().first()
    await db.commit()

    return {"id": str(row["id"]), "status": "created", "kr_name": req.kr_name}


@router.get("/objectives/{store_id}/kr/{objective_id}", summary="目标的KR列表", tags=["objectives"])
async def list_key_results(
    store_id: str,
    objective_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """获取某个目标的所有关键结果"""
    await validate_store_brand(store_id, current_user)

    result = await db.execute(
        text("""
            SELECT
                id, kr_name, metric_code,
                target_value, actual_value, unit, weight,
                CASE WHEN target_value > 0
                    THEN ROUND(actual_value::numeric / target_value * 100, 1)
                    ELSE 0
                END AS achievement_pct,
                status, owner_id
            FROM objective_key_results
            WHERE objective_id = :oid::uuid
            ORDER BY weight DESC
        """),
        {"oid": objective_id},
    )

    rows = []
    for r in result.mappings():
        row = dict(r)
        row["id"] = str(row["id"])
        if row["unit"] == "fen":
            row["target_yuan"] = row["target_value"] / 100
            row["actual_yuan"] = row["actual_value"] / 100
        rows.append(row)

    return {"objective_id": objective_id, "key_results": rows}
