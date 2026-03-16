"""
AI邀请函API — 管理端 + 公开端
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..middleware.public_rate_limiter import check_ip_rate_limit
from ..models.invitation import Invitation, InvitationTemplate
from ..models.user import User
from ..services.invitation_service import invitation_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["invitation"])


# ── Pydantic Models ──


class CreateInvitationRequest(BaseModel):
    store_id: str
    host_name: str = Field(..., max_length=100)
    host_phone: str = Field(..., max_length=20)
    event_type: str
    event_title: str = Field(..., max_length=200)
    event_date: datetime
    venue_name: str = Field(..., max_length=200)
    venue_address: str = ""
    template: str = "corporate_blue"
    custom_message: str = ""
    cover_image_url: str = ""
    venue_lat: Optional[float] = None
    venue_lng: Optional[float] = None


class GenerateTextRequest(BaseModel):
    genre: str = "现代诗"  # 藏头诗/现代诗/对联/文言文/古诗/口号
    mood: str = "正式"  # 简约/豪放/正式
    emotion: str = "庆祝"  # 庆祝/感恩/回忆/庄重/鼓励
    guest_name: str = ""


class RSVPRequest(BaseModel):
    guest_name: str = Field(..., max_length=100)
    guest_phone: str = ""
    party_size: int = Field(1, ge=1, le=50)
    dietary_restrictions: str = ""
    message: str = ""  # 祝福语
    status: str = "attending"


class InvitationResponse(BaseModel):
    id: str
    store_id: str
    host_name: str
    event_type: str
    event_title: str
    event_date: Optional[datetime] = None
    venue_name: str
    venue_address: str
    template: str
    custom_message: str
    ai_generated_message: str
    share_token: str
    view_count: int
    rsvp_count: int
    is_published: bool
    created_at: Optional[datetime] = None


def _to_response(inv: Invitation) -> InvitationResponse:
    return InvitationResponse(
        id=str(inv.id),
        store_id=inv.store_id,
        host_name=inv.host_name,
        event_type=inv.event_type,
        event_title=inv.event_title,
        event_date=inv.event_date,
        venue_name=inv.venue_name,
        venue_address=inv.venue_address or "",
        template=inv.template.value if hasattr(inv.template, "value") else str(inv.template),
        custom_message=inv.custom_message or "",
        ai_generated_message=inv.ai_generated_message or "",
        share_token=inv.share_token,
        view_count=inv.view_count or 0,
        rsvp_count=inv.rsvp_count or 0,
        is_published=inv.is_published or False,
        created_at=inv.created_at,
    )


def _get_public_db():
    return get_db(enable_tenant_isolation=False)


# ── 管理端（需登录） ──


@router.post("/invitations", response_model=InvitationResponse, status_code=201)
async def create_invitation(
    req: CreateInvitationRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建邀请函"""
    inv = await invitation_service.create_invitation(
        session=session,
        store_id=req.store_id,
        host_name=req.host_name,
        host_phone=req.host_phone,
        event_type=req.event_type,
        event_title=req.event_title,
        event_date=req.event_date,
        venue_name=req.venue_name,
        venue_address=req.venue_address,
        template=req.template,
        custom_message=req.custom_message,
        cover_image_url=req.cover_image_url,
        venue_lat=req.venue_lat,
        venue_lng=req.venue_lng,
    )
    return _to_response(inv)


@router.get("/invitations", response_model=List[InvitationResponse])
async def list_invitations(
    store_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取邀请函列表"""
    invs = await invitation_service.list_invitations(session, store_id)
    return [_to_response(inv) for inv in invs]


@router.post("/invitations/{invitation_id}/generate-text")
async def generate_text(
    invitation_id: str,
    req: GenerateTextRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """AI生成邀请语"""
    try:
        text = await invitation_service.generate_invitation_text(
            session=session,
            invitation_id=invitation_id,
            genre=req.genre,
            mood=req.mood,
            emotion=req.emotion,
            guest_name=req.guest_name,
        )
        return {"text": text}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/invitations/{invitation_id}/publish")
async def publish_invitation(
    invitation_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """发布邀请函 → 生成分享链接"""
    try:
        result = await invitation_service.publish(session, invitation_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/invitations/{invitation_id}/rsvps")
async def get_rsvps(
    invitation_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取RSVP统计"""
    return await invitation_service.get_rsvp_stats(session, invitation_id)


# ── 公开端（无需登录） ──


@router.get("/public/invitation/{share_token}")
async def view_invitation(
    share_token: str,
    session: AsyncSession = Depends(_get_public_db),
    _: None = Depends(check_ip_rate_limit),
):
    """查看邀请函（公开页面，+1浏览量）"""
    inv = await invitation_service.get_by_share_token(session, share_token)
    if not inv:
        raise HTTPException(status_code=404, detail="邀请函不存在或未发布")

    await invitation_service.increment_view(session, inv)

    return {
        "host_name": inv.host_name,
        "event_type": inv.event_type,
        "event_title": inv.event_title,
        "event_date": inv.event_date.isoformat() if inv.event_date else None,
        "venue_name": inv.venue_name,
        "venue_address": inv.venue_address,
        "venue_lat": inv.venue_lat,
        "venue_lng": inv.venue_lng,
        "template": inv.template.value if hasattr(inv.template, "value") else str(inv.template),
        "message": inv.ai_generated_message or inv.custom_message or "",
        "cover_image_url": inv.cover_image_url,
        "view_count": inv.view_count,
        "rsvp_count": inv.rsvp_count,
    }


@router.post("/public/invitation/{share_token}/rsvp")
async def submit_rsvp(
    share_token: str,
    req: RSVPRequest,
    session: AsyncSession = Depends(_get_public_db),
    _: None = Depends(check_ip_rate_limit),
):
    """提交RSVP回执"""
    inv = await invitation_service.get_by_share_token(session, share_token)
    if not inv:
        raise HTTPException(status_code=404, detail="邀请函不存在或未发布")

    rsvp = await invitation_service.record_rsvp(
        session=session,
        invitation_id=inv.id,
        guest_name=req.guest_name,
        guest_phone=req.guest_phone,
        party_size=req.party_size,
        dietary_restrictions=req.dietary_restrictions,
        message=req.message,
        status=req.status,
    )
    return {"success": True, "rsvp_id": str(rsvp.id)}
