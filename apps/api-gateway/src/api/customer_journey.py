"""
客户旅程自动化 API — Phase 4

端点列表：
  GET    /api/v1/brand/{brand_id}/journeys/templates              列出品牌所有旅程模板
  POST   /api/v1/brand/{brand_id}/journeys/templates              创建旅程模板
  PUT    /api/v1/brand/{brand_id}/journeys/templates/{id}         更新旅程模板
  POST   /api/v1/brand/{brand_id}/journeys/seed-defaults          初始化4条预置旅程
  POST   /api/v1/journeys/instances/{instance_id}/execute         手动触发旅程步骤（调试用）
  GET    /api/v1/brand/{brand_id}/journeys/templates/{id}/stats   旅程效果统计
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.services.customer_journey_engine import customer_journey_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Customer Journey"])


# ── Request / Response Schemas ───────────────────────────────────────────────


class CreateTemplateRequest(BaseModel):
    template_name: str = Field(..., min_length=1, max_length=100)
    trigger_event: str = Field(..., description="触发事件，如 member_registered / churn_risk_high")
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    group_id: Optional[str] = None


class UpdateTemplateRequest(BaseModel):
    template_name: Optional[str] = Field(None, min_length=1, max_length=100)
    trigger_event: Optional[str] = None
    steps: Optional[List[Dict[str, Any]]] = None
    is_active: Optional[bool] = None


class ExecuteStepRequest(BaseModel):
    step_id: str = Field(..., description="要执行的步骤 ID")


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/brand/{brand_id}/journeys/templates")
async def list_journey_templates(
    brand_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出品牌的所有旅程模板（含预置和自定义）"""
    try:
        templates = await customer_journey_engine.list_templates(brand_id, db)
        return {
            "brand_id": brand_id,
            "count": len(templates),
            "templates": templates,
        }
    except Exception as e:
        logger.error("list_templates_failed", brand_id=brand_id, error=str(e))
        raise HTTPException(status_code=500, detail="查询失败")


@router.post("/brand/{brand_id}/journeys/templates", status_code=201)
async def create_journey_template(
    brand_id: str,
    req: CreateTemplateRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建新的旅程模板"""
    try:
        template_id = await customer_journey_engine.create_journey_template(
            template_data={
                "template_name": req.template_name,
                "trigger_event": req.trigger_event,
                "steps": req.steps,
            },
            brand_id=brand_id,
            session=db,
            group_id=req.group_id or brand_id,
        )
        return {"template_id": template_id, "brand_id": brand_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("create_template_failed", brand_id=brand_id, error=str(e))
        raise HTTPException(status_code=500, detail="创建失败")


@router.put("/brand/{brand_id}/journeys/templates/{template_id}")
async def update_journey_template(
    brand_id: str,
    template_id: str,
    req: UpdateTemplateRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新旅程模板（支持部分字段更新）"""
    update_data = req.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="没有提供要更新的字段")
    try:
        ok = await customer_journey_engine.update_template(template_id, update_data, db)
        if not ok:
            raise HTTPException(status_code=404, detail="模板不存在或无字段变更")
        return {"template_id": template_id, "updated": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_template_failed", template_id=template_id, error=str(e))
        raise HTTPException(status_code=500, detail="更新失败")


@router.post("/brand/{brand_id}/journeys/seed-defaults", status_code=201)
async def seed_default_journeys(
    brand_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    为品牌初始化4条预置旅程：
    1. 新客欢迎旅程
    2. 流失挽回旅程
    3. 升级激励旅程
    4. 生日关怀旅程

    幂等操作，重复调用不会重复创建。
    """
    try:
        template_ids = await customer_journey_engine.seed_default_journeys(
            brand_id=brand_id,
            session=db,
            group_id=brand_id,
        )
        return {
            "brand_id": brand_id,
            "seeded_count": len(template_ids),
            "template_ids": template_ids,
            "message": f"成功初始化 {len(template_ids)} 条预置旅程",
        }
    except Exception as e:
        logger.error("seed_journeys_failed", brand_id=brand_id, error=str(e))
        raise HTTPException(status_code=500, detail="初始化预置旅程失败")


@router.post("/journeys/instances/{instance_id}/execute")
async def execute_journey_step(
    instance_id: str,
    req: ExecuteStepRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    手动触发旅程步骤执行（调试用）。
    正常情况下由 Celery 定时任务驱动。
    """
    try:
        next_step_id = await customer_journey_engine.execute_step(
            instance_id=instance_id,
            step_id=req.step_id,
            session=db,
        )
        return {
            "instance_id": instance_id,
            "executed_step_id": req.step_id,
            "next_step_id": next_step_id,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("execute_step_failed", instance_id=instance_id, error=str(e))
        raise HTTPException(status_code=500, detail="步骤执行失败")


@router.get("/brand/{brand_id}/journeys/templates/{template_id}/stats")
async def get_journey_template_stats(
    brand_id: str,
    template_id: str,
    period_days: int = Query(default=30, ge=1, le=365, description="统计周期（天）"),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    旅程模板效果统计：
    触发次数 / 完成率 / 各状态分布
    """
    try:
        stats = await customer_journey_engine.get_journey_stats(
            template_id=template_id,
            session=db,
            period_days=period_days,
        )
        return stats
    except Exception as e:
        logger.error(
            "journey_stats_failed", template_id=template_id, error=str(e)
        )
        raise HTTPException(status_code=500, detail="统计查询失败")
