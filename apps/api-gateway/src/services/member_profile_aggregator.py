"""
会员画像聚合服务 — P1 核心

从多个数据源并发聚合会员画像：
- consumer_identities（身份+标签）
- 微生活CRM（资产：余额/积分/券）
- POS订单（菜品偏好）
- AI Agent（话术生成）

每个子源独立失败，降级返回 None。
"""

import asyncio
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.consumer_identity import ConsumerIdentity
from ..models.member_dish_preference import MemberDishPreference
from .identity_resolution_service import identity_resolution_service

logger = structlog.get_logger(__name__)


async def _safe(coro, *, label: str = "unknown") -> Any:
    """执行协程，失败时返回 None 并记录日志（不阻塞其他子调用）"""
    try:
        return await coro
    except Exception as exc:
        logger.warning("子源聚合失败，降级", label=label, error=str(exc))
        return None


def _mask_phone(phone: str) -> str:
    """138****1234"""
    if len(phone) >= 7:
        return phone[:3] + "****" + phone[-4:]
    return phone


def _fen_to_display(fen: Optional[int]) -> Optional[str]:
    if fen is None:
        return None
    return f"¥{fen / 100:,.2f}"


class MemberProfileAggregator:
    """会员画像聚合器"""

    async def aggregate(
        self,
        db: AsyncSession,
        phone: str,
        store_id: str,
        *,
        include_ai_script: bool = True,
    ) -> Dict[str, Any]:
        # 1. Resolve phone → consumer_id
        consumer_id = await identity_resolution_service.resolve(
            db, phone, store_id=store_id, source="member_profile",
        )

        # 2. 并发聚合（每个子源独立失败）
        identity_task = _safe(
            self._fetch_identity(db, consumer_id), label="identity",
        )
        prefs_task = _safe(
            self._fetch_preferences(db, consumer_id, store_id), label="preferences",
        )
        assets_task = _safe(
            self._fetch_crm_assets(phone), label="crm_assets",
        )

        identity, preferences, assets = await asyncio.gather(
            identity_task, prefs_task, assets_task,
        )

        # 3. 里程碑（从 identity 数据派生）
        milestones = self._derive_milestones(identity) if identity else None

        # 4. AI 话术（可选）
        ai_script = None
        if include_ai_script:
            ai_script = await _safe(
                self._generate_ai_script(identity, preferences, assets, milestones),
                label="ai_script",
            )

        return {
            "consumer_id": str(consumer_id),
            "identity": identity,
            "preferences": preferences,
            "assets": assets,
            "milestones": milestones,
            "ai_script": ai_script,
        }

    async def _fetch_identity(
        self, db: AsyncSession, consumer_id,
    ) -> Optional[Dict[str, Any]]:
        """从 consumer_identities 读取身份信息"""
        consumer = await db.get(ConsumerIdentity, consumer_id)
        if not consumer:
            return None

        return {
            "name": consumer.display_name or "未知",
            "phone": _mask_phone(consumer.primary_phone),
            "tags": consumer.tags or [],
            "lifecycle_stage": self._compute_lifecycle(consumer),
            "_birth_date": consumer.birth_date,
            "_anniversary": getattr(consumer, "anniversary", None),
            "_first_order_at": consumer.first_order_at,
            "_last_order_at": consumer.last_order_at,
            "_total_order_count": consumer.total_order_count or 0,
            "_dietary_restrictions": getattr(consumer, "dietary_restrictions", None) or [],
        }

    async def _fetch_preferences(
        self, db: AsyncSession, consumer_id, store_id: str,
    ) -> Optional[Dict[str, Any]]:
        """从 member_dish_preferences 读取菜品偏好"""
        stmt = (
            select(MemberDishPreference)
            .where(
                MemberDishPreference.consumer_id == consumer_id,
                MemberDishPreference.store_id == store_id,
            )
            .order_by(MemberDishPreference.order_count.desc())
            .limit(10)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        favorites = [
            {"name": r.dish_name, "count": r.order_count}
            for r in rows
        ]
        return {
            "favorite_dishes": favorites,
            "dietary_restrictions": [],
            "preferred_seating": None,
        }

    async def _fetch_crm_assets(self, phone: str) -> Optional[Dict[str, Any]]:
        """从微生活CRM读取资产（余额/积分/券）"""
        try:
            from ..services.member_service import member_service
            member = await member_service.query_member(mobile=phone)
        except Exception:
            logger.warning("微生活CRM不可用", phone=_mask_phone(phone))
            return None

        if not member:
            return None

        balance_fen = int(float(member.get("balance", 0)) * 100)
        points = member.get("point", 0)

        coupons: List[Dict] = []
        try:
            card_no = member.get("card_no", "")
            coupon_list = await member_service.coupon_list(card_no=card_no) if card_no else []
            for c in (coupon_list or []):
                coupons.append({
                    "id": str(c.get("coupon_id", "")),
                    "name": c.get("coupon_name", ""),
                    "expires": c.get("end_time", ""),
                })
        except Exception:
            pass

        return {
            "level": member.get("level_name", ""),
            "balance_fen": balance_fen,
            "balance_display": _fen_to_display(balance_fen),
            "points": points,
            "available_coupons": coupons,
        }

    def _derive_milestones(self, identity: Dict[str, Any]) -> Dict[str, Any]:
        """从 identity 内部字段派生里程碑"""
        today = date.today()
        birth = identity.get("_birth_date")
        birthday_upcoming = False
        birthday_str = None
        if birth:
            birthday_str = birth.isoformat()
            this_year_bday = birth.replace(year=today.year)
            if this_year_bday < today:
                this_year_bday = birth.replace(year=today.year + 1)
            birthday_upcoming = (this_year_bday - today).days <= 7

        last_order = identity.get("_last_order_at")
        first_order = identity.get("_first_order_at")

        return {
            "birthday": birthday_str,
            "birthday_upcoming": birthday_upcoming,
            "last_visit": last_order.isoformat() if last_order else None,
            "total_visits": identity.get("_total_order_count", 0),
            "member_since": first_order.isoformat() if first_order else None,
        }

    def _compute_lifecycle(self, consumer: ConsumerIdentity) -> str:
        """简易生命周期阶段判定"""
        if not consumer.last_order_at:
            return "新客"
        days_since = (date.today() - consumer.last_order_at.date()).days
        freq = consumer.total_order_count or 0
        if freq <= 1:
            return "新客"
        if days_since <= 30 and freq >= 4:
            return "活跃期"
        if days_since <= 60:
            return "稳定期"
        if days_since <= 90:
            return "预警期"
        return "沉睡期"

    async def _generate_ai_script(
        self,
        identity: Optional[Dict],
        preferences: Optional[Dict],
        assets: Optional[Dict],
        milestones: Optional[Dict],
    ) -> Optional[str]:
        """调用 LLM 生成个性化服务话术"""
        try:
            from ..agents.llm_agent import LLMAgent
            agent = LLMAgent()
            context_parts = []
            if identity:
                context_parts.append(f"顾客: {identity.get('name', '未知')}")
                if identity.get("tags"):
                    context_parts.append(f"标签: {', '.join(identity['tags'])}")
            if preferences and preferences.get("favorite_dishes"):
                top_dishes = [d["name"] for d in preferences["favorite_dishes"][:3]]
                context_parts.append(f"常点: {', '.join(top_dishes)}")
            if milestones and milestones.get("birthday_upcoming"):
                context_parts.append("本周即将生日")
            if assets:
                context_parts.append(f"会员等级: {assets.get('level', '')}")

            if not context_parts:
                return None

            prompt = (
                "你是一家中餐厅的资深服务员。根据以下顾客信息，生成一句简短的个性化迎宾话术（30字以内，亲切自然）：\n"
                + "\n".join(context_parts)
            )
            result = await agent.arun(prompt)
            return result.strip() if result else None
        except Exception:
            return None


# 全局单例
member_profile_aggregator = MemberProfileAggregator()
