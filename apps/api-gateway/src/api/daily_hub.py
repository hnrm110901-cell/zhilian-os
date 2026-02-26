"""
Daily Hub API - T+1 经营统筹控制台
"""
from datetime import date, datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.core.dependencies import get_current_user
from src.models.user import User
from src.services.daily_hub_service import daily_hub_service

router = APIRouter(prefix="/api/v1/daily-hub", tags=["daily_hub"])


class ApproveRequest(BaseModel):
    target_date: str  # YYYY-MM-DD
    adjustments: Optional[Dict[str, Any]] = None


@router.get("/{store_id}")
async def get_battle_board(
    store_id: str,
    target_date: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """
    获取/生成备战板（幂等：Redis 有缓存直接返回，无缓存同步生成）
    """
    try:
        td = (
            datetime.strptime(target_date, "%Y-%m-%d").date()
            if target_date
            else None
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="target_date 格式应为 YYYY-MM-DD")

    board = await daily_hub_service.generate_battle_board(
        store_id=store_id, target_date=td
    )
    return board


@router.post("/{store_id}/approve")
async def approve_battle_board(
    store_id: str,
    body: ApproveRequest,
    current_user: User = Depends(get_current_user),
):
    """一键审批备战板"""
    try:
        td = datetime.strptime(body.target_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="target_date 格式应为 YYYY-MM-DD")

    board = await daily_hub_service.approve_battle_board(
        store_id=store_id,
        target_date=td,
        approver_id=str(current_user.id),
        adjustments=body.adjustments,
    )
    return board
