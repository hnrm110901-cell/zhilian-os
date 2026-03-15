"""
大众点评评论监控 API 端点
评论同步、查询、回复、情感分析、统计概览
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import require_role
from src.models.user import User, UserRole
from src.services.dianping_service import DianpingService

router = APIRouter(prefix="/dianping", tags=["dianping"])

dianping_service = DianpingService()


# ── 请求体 ──────────────────────────────────────────────────────────


class SyncReviewsRequest(BaseModel):
    brand_id: str
    store_id: str


class ReplyRequest(BaseModel):
    reply_content: str


class MarkReadRequest(BaseModel):
    review_ids: List[str]


# ── 同步 ────────────────────────────────────────────────────────────


@router.post("/sync")
async def sync_reviews(
    body: SyncReviewsRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """从大众点评同步评论数据"""
    try:
        result = await dianping_service.sync_reviews(
            db=db,
            brand_id=body.brand_id,
            store_id=body.store_id,
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步失败: {str(e)}")


# ── 评论列表 ────────────────────────────────────────────────────────


@router.get("/reviews")
async def list_reviews(
    brand_id: str = Query(...),
    store_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sentiment: Optional[str] = Query(None),
    rating: Optional[int] = Query(None, ge=1, le=5),
    is_read: Optional[bool] = Query(None),
    keyword: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """查询评论列表（分页 + 筛选）"""
    result = await dianping_service.list_reviews(
        db=db,
        brand_id=brand_id,
        store_id=store_id,
        page=page,
        page_size=page_size,
        sentiment=sentiment,
        rating=rating,
        is_read=is_read,
        keyword=keyword,
    )
    return result


# ── 评论详情 ────────────────────────────────────────────────────────


@router.get("/reviews/{review_id}")
async def get_review(
    review_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """获取单条评论详情"""
    result = await dianping_service.get_review(db, review_id)
    if not result:
        raise HTTPException(status_code=404, detail="评论不存在")
    return result


# ── 商家回复 ────────────────────────────────────────────────────────


@router.post("/reviews/{review_id}/reply")
async def reply_review(
    review_id: str,
    body: ReplyRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """回复评论"""
    try:
        result = await dianping_service.reply_review(
            db=db,
            review_id=review_id,
            reply_content=body.reply_content,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── 批量标记已读 ────────────────────────────────────────────────────


@router.post("/reviews/mark-read")
async def mark_read(
    body: MarkReadRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """批量标记评论为已读"""
    count = await dianping_service.mark_read(db, body.review_ids)
    return {"success": True, "marked_count": count}


# ── 统计概览 ────────────────────────────────────────────────────────


@router.get("/stats")
async def get_stats(
    brand_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """获取品牌评论统计概览"""
    result = await dianping_service.get_stats(db, brand_id)
    return result


# ── 关键词云 ────────────────────────────────────────────────────────


@router.get("/keywords")
async def get_keyword_cloud(
    brand_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """获取品牌关键词云数据"""
    result = await dianping_service.get_keyword_cloud(db, brand_id)
    return {"keywords": result}
