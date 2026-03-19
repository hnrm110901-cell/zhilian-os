"""
邀请函服务 — AI文案生成 + RSVP管理
"""

import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.invitation import Invitation, InvitationRSVP, InvitationTemplate, RSVPStatus

logger = structlog.get_logger()


class InvitationService:
    """邀请函服务"""

    # ── 邀请函CRUD ──

    async def create_invitation(
        self,
        session: AsyncSession,
        store_id: str,
        host_name: str,
        host_phone: str,
        event_type: str,
        event_title: str,
        event_date: datetime,
        venue_name: str,
        venue_address: str = "",
        template: str = "corporate_blue",
        custom_message: str = "",
        cover_image_url: str = "",
        venue_lat: Optional[float] = None,
        venue_lng: Optional[float] = None,
    ) -> Invitation:
        """创建邀请函"""
        invitation = Invitation(
            store_id=store_id,
            host_name=host_name,
            host_phone=host_phone,
            event_type=event_type,
            event_title=event_title,
            event_date=event_date,
            venue_name=venue_name,
            venue_address=venue_address,
            template=InvitationTemplate(template),
            custom_message=custom_message,
            cover_image_url=cover_image_url,
            venue_lat=venue_lat,
            venue_lng=venue_lng,
            share_token=secrets.token_hex(16),
        )
        session.add(invitation)
        await session.commit()
        await session.refresh(invitation)
        logger.info("invitation_created", id=str(invitation.id), event_type=event_type)
        return invitation

    async def list_invitations(
        self,
        session: AsyncSession,
        store_id: str,
        limit: int = 50,
    ) -> List[Invitation]:
        """获取邀请函列表"""
        result = await session.execute(
            select(Invitation).where(Invitation.store_id == store_id).order_by(Invitation.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_id(self, session: AsyncSession, invitation_id: str) -> Optional[Invitation]:
        """按ID获取"""
        result = await session.execute(select(Invitation).where(Invitation.id == invitation_id))
        return result.scalar_one_or_none()

    async def get_by_share_token(self, session: AsyncSession, share_token: str) -> Optional[Invitation]:
        """按分享token获取（公开）"""
        result = await session.execute(
            select(Invitation).where(
                and_(
                    Invitation.share_token == share_token,
                    Invitation.is_published == True,
                )
            )
        )
        return result.scalar_one_or_none()

    # ── AI文案生成 ──

    async def generate_invitation_text(
        self,
        session: AsyncSession,
        invitation_id: str,
        genre: str = "现代诗",
        mood: str = "正式",
        emotion: str = "庆祝",
        guest_name: str = "",
    ) -> str:
        """调LLM生成邀请语"""
        invitation = await self.get_by_id(session, invitation_id)
        if not invitation:
            raise ValueError("邀请函不存在")

        # 构建提示词（参考易订AI请柬的体裁/语气/情感维度）
        prompt = (
            f"你是一位专业的中文宴会邀请函文案撰写师。\n\n"
            f"请为以下宴会生成一段优美的中文邀请语：\n"
            f"- 宴会类型：{invitation.event_type}\n"
            f"- 宴会主题：{invitation.event_title}\n"
            f"- 主人姓名：{invitation.host_name}\n"
            f"- 日期：{invitation.event_date.strftime('%Y年%m月%d日') if invitation.event_date else ''}\n"
            f"- 场所：{invitation.venue_name}\n"
        )
        if guest_name:
            prompt += f"- 宾客姓名：{guest_name}（请在文案中自然融入宾客姓名，如藏头诗则以姓名开头）\n"
        if invitation.custom_message:
            prompt += f"- 主人自定义要求：{invitation.custom_message}\n"

        prompt += (
            f"\n创作要求：\n"
            f"- 体裁：{genre}\n"
            f"- 语气：{mood}\n"
            f"- 情感基调：{emotion}\n"
            f"- 字数控制在100-200字\n"
            f"- 优雅大气，体现中华传统宴请文化\n"
            f"- 仅输出邀请语正文，不加标题和解释\n"
        )

        try:
            from ..agents.llm_agent import LLMAgent

            agent = LLMAgent()
            generated = await agent.generate_text(prompt)
            text = generated if isinstance(generated, str) else str(generated)
        except Exception as e:
            logger.warning("ai_generation_fallback", error=str(e))
            # 降级：使用模板文案
            text = (
                f"尊敬的贵宾：\n\n"
                f"{invitation.host_name}诚挚邀请您出席{invitation.event_title}。\n"
                f"时间：{invitation.event_date.strftime('%Y年%m月%d日') if invitation.event_date else ''}\n"
                f"地点：{invitation.venue_name}\n\n"
                f"恭候光临！"
            )

        # 保存AI生成结果
        invitation.ai_generated_message = text
        invitation.ai_params = {
            "genre": genre,
            "mood": mood,
            "emotion": emotion,
            "guest_name": guest_name,
        }
        await session.commit()

        logger.info("ai_invitation_generated", id=str(invitation_id))
        return text

    # ── 发布 ──

    async def publish(self, session: AsyncSession, invitation_id: str) -> Dict[str, Any]:
        """发布邀请函"""
        invitation = await self.get_by_id(session, invitation_id)
        if not invitation:
            raise ValueError("邀请函不存在")

        invitation.is_published = True
        await session.commit()

        share_url = f"https://zlsjos.cn/invitation/{invitation.share_token}"
        logger.info("invitation_published", id=str(invitation_id), token=invitation.share_token)
        return {"share_url": share_url, "share_token": invitation.share_token}

    # ── RSVP ──

    async def record_rsvp(
        self,
        session: AsyncSession,
        invitation_id,
        guest_name: str,
        guest_phone: str = "",
        party_size: int = 1,
        dietary_restrictions: str = "",
        message: str = "",
        status: str = "attending",
    ) -> InvitationRSVP:
        """记录RSVP回执"""
        rsvp = InvitationRSVP(
            invitation_id=invitation_id,
            guest_name=guest_name,
            guest_phone=guest_phone,
            party_size=party_size,
            dietary_restrictions=dietary_restrictions,
            message=message,
            status=RSVPStatus(status),
        )
        session.add(rsvp)

        # 更新计数
        invitation = await self.get_by_id(session, str(invitation_id))
        if invitation:
            invitation.rsvp_count = (invitation.rsvp_count or 0) + 1

        await session.commit()
        await session.refresh(rsvp)
        logger.info("rsvp_recorded", invitation_id=str(invitation_id), guest=guest_name)
        return rsvp

    async def get_rsvp_stats(
        self,
        session: AsyncSession,
        invitation_id: str,
    ) -> Dict[str, Any]:
        """RSVP统计"""
        result = await session.execute(select(InvitationRSVP).where(InvitationRSVP.invitation_id == invitation_id))
        rsvps = result.scalars().all()

        attending = [r for r in rsvps if r.status == RSVPStatus.ATTENDING]
        declined = [r for r in rsvps if r.status == RSVPStatus.DECLINED]

        return {
            "total": len(rsvps),
            "attending": len(attending),
            "attending_guests": sum(r.party_size or 1 for r in attending),
            "declined": len(declined),
            "rsvps": [
                {
                    "guest_name": r.guest_name,
                    "party_size": r.party_size,
                    "status": r.status.value,
                    "message": r.message,
                    "dietary_restrictions": r.dietary_restrictions,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rsvps
            ],
        }

    # ── 浏览量 ──

    async def increment_view(self, session: AsyncSession, invitation: Invitation):
        """增加浏览量"""
        invitation.view_count = (invitation.view_count or 0) + 1
        await session.commit()


# 单例
invitation_service = InvitationService()
