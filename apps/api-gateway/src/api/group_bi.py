"""
集团BI大屏 API — Phase 3

路由：
  GET /api/v1/group/{group_id}/bi/overview
  GET /api/v1/group/{group_id}/bi/brand-comparison
  GET /api/v1/brand/{brand_id}/bi/member-funnel
  GET /api/v1/brand/{brand_id}/bi/marketing-roi
  GET /api/v1/brand/{brand_id}/bi/region-ranking
  GET /api/v1/brand/{brand_id}/bi/store-ranking
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.dependencies import get_current_active_user, get_db
from ..models.user import User
from ..services.group_bi_service import group_bi_service

logger = structlog.get_logger(__name__)
router = APIRouter()


def _get_group_id_from_user(current_user: User, path_group_id: str) -> str:
    """优先使用路径中的 group_id；权限校验由 RLS 兜底。"""
    return path_group_id


def _parse_date_range(
    start_date: Optional[str], end_date: Optional[str], default_days: int = 30
) -> tuple:
    """解析日期范围，缺省返回最近 default_days 天。"""
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"end_date 格式错误: {end_date!r}，请用 ISO 格式")
    else:
        end_dt = datetime.utcnow()

    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"start_date 格式错误: {start_date!r}")
    else:
        start_dt = end_dt - timedelta(days=default_days)

    if start_dt >= end_dt:
        raise HTTPException(status_code=422, detail="start_date 必须早于 end_date")

    return start_dt, end_dt


# --------------------------------------------------------------------------- #
# 集团总览
# --------------------------------------------------------------------------- #

@router.get("/group/{group_id}/bi/overview", summary="集团总览大屏数据")
async def get_group_overview(
    group_id: str,
    start_date: Optional[str] = Query(None, description="起始日期 ISO 格式，默认近30天"),
    end_date: Optional[str] = Query(None, description="结束日期 ISO 格式，默认现在"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    集团总览大屏。返回：
    - 集团总GMV（_fen + _yuan）
    - 各品牌GMV分布 + 同比变化
    - 集团总会员数（去重）、新增、跨品牌消费人数
    - 整体复购率
    - 活跃门店数
    """
    date_range = _parse_date_range(start_date, end_date)
    try:
        return await group_bi_service.get_group_overview(
            group_id=group_id,
            date_range=date_range,
            session=db,
        )
    except Exception as exc:
        logger.error("group_overview_failed", group_id=group_id, error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="集团总览数据获取失败")


# --------------------------------------------------------------------------- #
# 品牌横向对比
# --------------------------------------------------------------------------- #

@router.get("/group/{group_id}/bi/brand-comparison", summary="品牌横向对比时序数据")
async def get_brand_comparison(
    group_id: str,
    brand_ids: str = Query(..., description="品牌 ID 列表，逗号分隔，如 brand_a,brand_b"),
    metric: str = Query(
        default="gmv",
        description="指标：gmv / new_members / repurchase_rate / avg_order_fen / rfm_distribution",
    ),
    period: str = Query(
        default="daily",
        description="时间粒度：daily / weekly / monthly",
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    品牌横向对比。支持 GMV / 新增会员 / 复购率 / 客单价 / 生命周期分布对比。
    返回时序数据，适合多品牌折线图渲染。
    """
    brand_id_list = [b.strip() for b in brand_ids.split(",") if b.strip()]
    if not brand_id_list:
        raise HTTPException(status_code=422, detail="brand_ids 不能为空")
    if len(brand_id_list) > 10:
        raise HTTPException(status_code=422, detail="最多支持 10 个品牌同时对比")

    try:
        data = await group_bi_service.get_brand_comparison(
            group_id=group_id,
            brand_ids=brand_id_list,
            metric=metric,
            period=period,
            session=db,
        )
        return {
            "group_id": group_id,
            "brand_ids": brand_id_list,
            "metric": metric,
            "period": period,
            "data": data,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("brand_comparison_failed", group_id=group_id, error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="品牌对比数据获取失败")


# --------------------------------------------------------------------------- #
# 会员生命周期漏斗
# --------------------------------------------------------------------------- #

@router.get("/brand/{brand_id}/bi/member-funnel", summary="会员生命周期漏斗")
async def get_member_funnel(
    brand_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    会员生命周期漏斗。
    返回 lead→registered→repeat→vip→at_risk→dormant→lost 各阶段人数及相邻转化率。
    """
    group_id = str(getattr(current_user, "group_id", "") or "")
    try:
        return await group_bi_service.get_member_funnel(
            brand_id=brand_id,
            group_id=group_id,
            session=db,
        )
    except Exception as exc:
        logger.error("member_funnel_failed", brand_id=brand_id, error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="会员漏斗数据获取失败")


# --------------------------------------------------------------------------- #
# 营销ROI
# --------------------------------------------------------------------------- #

@router.get("/brand/{brand_id}/bi/marketing-roi", summary="营销ROI汇总")
async def get_marketing_roi(
    brand_id: str,
    period_days: int = Query(default=30, ge=1, le=365, description="统计周期（天），默认30天"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    营销ROI。返回各渠道（短信/企微/Push/小程序/券）的：
    发送量、触达率、转化率、促成GMV（_fen + _yuan）、成本（_fen + _yuan）、ROI。
    若无营销数据则降级返回空骨架。
    """
    group_id = str(getattr(current_user, "group_id", "") or "")
    try:
        return await group_bi_service.get_marketing_roi(
            brand_id=brand_id,
            group_id=group_id,
            period_days=period_days,
            session=db,
        )
    except Exception as exc:
        logger.error("marketing_roi_failed", brand_id=brand_id, error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="营销ROI数据获取失败")


# --------------------------------------------------------------------------- #
# 区域排行榜
# --------------------------------------------------------------------------- #

@router.get("/brand/{brand_id}/bi/region-ranking", summary="区域排行榜")
async def get_region_ranking(
    brand_id: str,
    metric: str = Query(
        default="gmv",
        description="排行指标：gmv / growth / repurchase_rate / new_members",
    ),
    top_n: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """区域排行榜（GMV / 增速 / 复购率 / 新客数），返回 TOP N。"""
    group_id = str(getattr(current_user, "group_id", "") or "")
    try:
        data = await group_bi_service.get_region_ranking(
            brand_id=brand_id,
            group_id=group_id,
            metric=metric,
            top_n=top_n,
            session=db,
        )
        return {"brand_id": brand_id, "metric": metric, "top_n": top_n, "ranking": data}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("region_ranking_failed", brand_id=brand_id, error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="区域排行榜数据获取失败")


# --------------------------------------------------------------------------- #
# 门店排行榜
# --------------------------------------------------------------------------- #

@router.get("/brand/{brand_id}/bi/store-ranking", summary="门店排行榜")
async def get_store_ranking(
    brand_id: str,
    metric: str = Query(
        default="gmv",
        description="排行指标：gmv / new_members / repurchase_rate / avg_order_fen",
    ),
    top_n: int = Query(default=20, ge=1, le=100),
    region_id: Optional[str] = Query(None, description="按区域筛选（可选）"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    门店排行榜。支持按区域筛选，返回 TOP N。
    金额指标同时返回 _fen 和 _yuan 两字段。
    """
    group_id = str(getattr(current_user, "group_id", "") or "")
    try:
        data = await group_bi_service.get_store_ranking(
            brand_id=brand_id,
            group_id=group_id,
            metric=metric,
            top_n=top_n,
            region_id=region_id,
            session=db,
        )
        return {
            "brand_id": brand_id,
            "metric": metric,
            "top_n": top_n,
            "region_id": region_id,
            "ranking": data,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("store_ranking_failed", brand_id=brand_id, error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="门店排行榜数据获取失败")
