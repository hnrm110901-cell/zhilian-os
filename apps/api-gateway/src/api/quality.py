"""
Quality API - 菜品质量检测接口
前缀: /api/v1/quality
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import structlog

from ..agents.quality_agent import quality_agent

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/quality", tags=["quality"])


# ── Request / Response schemas ────────────────────────────────

class InspectRequest(BaseModel):
    store_id: str
    dish_name: str
    image_b64: str = Field(..., description="base64 编码的菜品图片")
    dish_id: Optional[str] = None
    image_url: Optional[str] = None
    media_type: str = "image/jpeg"
    recipient_ids: Optional[List[str]] = Field(
        default=None, description="企业微信告警接收人ID列表"
    )


# ── Endpoints ─────────────────────────────────────────────────

@router.post("/inspect")
async def inspect_dish(req: InspectRequest):
    """
    上传菜品图片进行质量检测。

    - 调用视觉模型评分（0-100）
    - 评分低于阈值（默认75）时推送企业微信告警
    - 返回质量评分、问题列表和改进建议
    """
    result = await quality_agent.inspect_dish(
        store_id=req.store_id,
        dish_name=req.dish_name,
        image_b64=req.image_b64,
        dish_id=req.dish_id,
        image_url=req.image_url,
        media_type=req.media_type,
        recipient_ids=req.recipient_ids,
    )
    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)
    return result.to_dict()


@router.get("/inspections/{store_id}")
async def list_inspections(
    store_id: str,
    limit: int = 20,
    status: Optional[str] = None,
):
    """获取门店历史检测记录（最新在前）"""
    result = await quality_agent.execute(
        "get_report",
        {"store_id": store_id, "limit": limit, "status": status},
    )
    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)
    return result.data


@router.get("/summary/{store_id}")
async def get_summary(store_id: str):
    """获取门店质量检测汇总统计（合格率、平均分等）"""
    result = await quality_agent.execute("get_summary", {"store_id": store_id})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)
    return result.data
