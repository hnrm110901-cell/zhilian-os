"""
企微SCRM深度集成服务 — Phase 2

功能：
1. 添加外部联系人时自动绑定会员（One ID 归因）
2. 根据生命周期状态发送差异化欢迎语
3. 员工离职时批量迁移客户
4. 私域行为同步到 CDP
5. 导购助手侧边栏：客户完整画像
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.brand_consumer_profile import BrandConsumerProfile
from src.models.consumer_identity import ConsumerIdentity
from src.models.private_domain import PrivateDomainMember
from src.repositories.brand_consumer_profile_repo import BrandConsumerProfileRepo

logger = structlog.get_logger()

# ---------- 话术模板（触发时机 × 生命周期状态） ----------
# key: (trigger, lifecycle_state) → 话术文本
# trigger: new_customer / returning / re_activation / post_purchase
_WELCOME_TEMPLATES: Dict[tuple, str] = {
    ("new_customer", "registered"): (
        "您好！欢迎加入！我是您的专属顾问，有任何用餐或预订需求随时找我。"
    ),
    ("new_customer", "lead"): (
        "您好！很高兴认识您！期待为您提供更好的用餐体验。"
    ),
    ("returning", "repeat"): (
        "欢迎回来！老朋友了，有什么需要我帮忙的？最近有新菜值得一试。"
    ),
    ("returning", "vip"): (
        "尊贵的贵宾，欢迎回来！您的专属权益已经为您准备好了。"
    ),
    ("re_activation", "at_risk"): (
        "好久不见！最近有没有空来尝尝我们的新品？为您准备了专属优惠。"
    ),
    ("re_activation", "dormant"): (
        "许久未见，甚是想念！我们推出了全新菜单，诚邀您回来品鉴。"
    ),
    ("re_activation", "lost"): (
        "感谢您曾经的信任！我们一直在努力改善，希望有机会再次为您服务。"
    ),
    ("post_purchase", "repeat"): (
        "感谢您今天的光临！用餐体验如何？欢迎为我们留下宝贵意见。"
    ),
    ("post_purchase", "vip"): (
        "感谢贵宾今天的光临！您的意见对我们非常重要，期待下次再见。"
    ),
}

# 默认兜底话术
_DEFAULT_WELCOME = "您好！很高兴认识您！有任何需求欢迎随时联系我。"


class WeComSCRMService:
    """企微SCRM深度集成服务

    依赖：
    - wechat_service（发送企微消息）
    - BrandConsumerProfileRepo（品牌消费档案）
    - ConsumerIdentity / PrivateDomainMember（ORM 模型）
    """

    async def bind_member_on_add_external_contact(
        self,
        db: AsyncSession,
        wecom_userid: str,
        external_userid: str,
        store_id: str,
    ) -> Optional[str]:
        """
        企微添加外部联系人时自动绑定会员。
        触发时机：企微回调 add_external_contact 事件。

        逻辑：
        1. 通过 external_userid 获取客户详情（手机号）—— 调用企微 API
        2. 用手机号查询 ConsumerIdentity
        3. 存在则更新 PrivateDomainMember.wecom_external_userid
        4. 不存在则创建新 ConsumerIdentity + BrandConsumerProfile
        5. 返回 consumer_id（str），归因失败返回 None

        Args:
            db              : 异步数据库 Session
            wecom_userid    : 企业内员工 userid（触发添加的员工）
            external_userid : 外部联系人 userid（客户）
            store_id        : 门店 ID

        Returns:
            consumer_id（str）或 None
        """
        # 1. 从企微获取客户手机号（需要「客户联系」权限）
        phone = await self._get_external_contact_phone(external_userid)
        if not phone:
            logger.warning(
                "WeComSCRM: 无法获取外部联系人手机号，跳过会员绑定",
                external_userid=external_userid,
                store_id=store_id,
            )
            return None

        # 2. 用手机号查 ConsumerIdentity
        result = await db.execute(
            select(ConsumerIdentity).where(
                ConsumerIdentity.primary_phone == phone,
                ConsumerIdentity.is_merged.is_(False),
            )
        )
        identity = result.scalar_one_or_none()

        if identity:
            # 3. 存在：更新 PrivateDomainMember — 写入 wecom_external_userid
            await self._upsert_private_domain_wecom_id(
                db, identity.id, store_id, external_userid, wecom_userid
            )
            consumer_id = str(identity.id)
            logger.info(
                "WeComSCRM: 外部联系人已匹配到现有会员",
                consumer_id=consumer_id,
                external_userid=external_userid,
            )
        else:
            # 4. 不存在：创建新 ConsumerIdentity + PrivateDomainMember
            consumer_id = await self._create_new_consumer_from_wecom(
                db, phone, external_userid, wecom_userid, store_id
            )

        return consumer_id

    async def send_welcome_message(
        self,
        db: AsyncSession,
        consumer_id: str,
        brand_id: str,
        trigger: str,
    ) -> bool:
        """
        根据会员生命周期状态发送差异化欢迎语。

        Args:
            db          : 异步数据库 Session
            consumer_id : 统一消费者 ID
            brand_id    : 品牌 ID
            trigger     : 触发时机 new_customer / returning / re_activation / post_purchase

        Returns:
            True 表示发送成功
        """
        try:
            cid = uuid.UUID(consumer_id)
        except ValueError:
            logger.error("WeComSCRM: 无效 consumer_id", consumer_id=consumer_id)
            return False

        # 1. 查 BrandConsumerProfile 获取 lifecycle_state
        profile = await BrandConsumerProfileRepo.get_by_consumer_and_brand(
            db, cid, brand_id
        )
        lifecycle_state = profile.lifecycle_state if profile else "registered"

        # 2. 选择话术模板
        message_text = _WELCOME_TEMPLATES.get(
            (trigger, lifecycle_state), _DEFAULT_WELCOME
        )

        # 3. 查消费者 openid
        identity = await db.get(ConsumerIdentity, cid)
        if not identity:
            logger.warning("WeComSCRM: consumer_id 不存在", consumer_id=consumer_id)
            return False

        openid = identity.wechat_openid
        if not openid:
            logger.info(
                "WeComSCRM: 消费者无企微 openid，跳过欢迎语",
                consumer_id=consumer_id,
            )
            return False

        # 4. 调用 wechat_service 发送
        try:
            from src.services.wechat_service import wechat_service

            await wechat_service.send_text_message(message_text, touser=openid)
            logger.info(
                "WeComSCRM: 欢迎语发送成功",
                consumer_id=consumer_id,
                trigger=trigger,
                lifecycle_state=lifecycle_state,
            )
            return True
        except Exception as exc:
            logger.warning(
                "WeComSCRM: 欢迎语发送失败",
                consumer_id=consumer_id,
                error=str(exc),
            )
            return False

    async def transfer_customer_on_resignation(
        self,
        db: AsyncSession,
        resigned_userid: str,
        successor_userid: str,
        store_id: str,
    ) -> Dict[str, Any]:
        """
        员工离职时批量迁移客户到接替人。

        逻辑：
        1. 查询 private_domain_members 中 staff_wechat_id = resigned_userid 的客户
        2. 调用企微 API transfer_customer（批量迁移，每次最多 100 条）
        3. 更新 private_domain_members.channel_source 记录继承关系
        4. 返回迁移结果统计

        Args:
            db               : 异步数据库 Session
            resigned_userid  : 离职员工企微 userid
            successor_userid : 接替人企微 userid
            store_id         : 门店 ID

        Returns:
            {"total": N, "transferred": M, "failed": K, "failed_list": [...]}
        """
        # 1. 查询该员工名下的私域会员（通过 channel_source 记录企微绑定关系）
        # 注：PrivateDomainMember 当前无 staff_wechat_id 字段，
        #     使用 channel_source LIKE 'wecom:{resigned_userid}' 作为过渡方案。
        #     Phase 3 建议正式增加 staff_wecom_userid 字段。
        stmt = select(PrivateDomainMember).where(
            and_(
                PrivateDomainMember.store_id == store_id,
                PrivateDomainMember.is_active.is_(True),
                PrivateDomainMember.channel_source == f"wecom:{resigned_userid}",
            )
        )
        result = await db.execute(stmt)
        members = result.scalars().all()

        total = len(members)
        transferred = 0
        failed_list: List[str] = []

        if total == 0:
            logger.info(
                "WeComSCRM: 离职员工名下无私域会员",
                resigned_userid=resigned_userid,
                store_id=store_id,
            )
            return {"total": 0, "transferred": 0, "failed": 0, "failed_list": []}

        # 2. 分批调用企微 transfer_customer（每批最多100个 external_userid）
        # 注：external_userid 从 wechat_openid 字段读取（当前 PrivateDomainMember 以此存储）
        batch_size = 100
        external_ids = [m.wechat_openid for m in members if m.wechat_openid]

        for i in range(0, len(external_ids), batch_size):
            batch = external_ids[i : i + batch_size]
            transfer_result = await self._call_wecom_transfer_customer(
                batch, resigned_userid, successor_userid
            )
            batch_transferred = transfer_result.get("transferred_count", 0)
            batch_failed = transfer_result.get("failed_list", [])
            transferred += batch_transferred
            failed_list.extend(batch_failed)

        # 3. 更新 channel_source 记录接替关系
        if transferred > 0:
            await db.execute(
                update(PrivateDomainMember)
                .where(
                    and_(
                        PrivateDomainMember.store_id == store_id,
                        PrivateDomainMember.channel_source == f"wecom:{resigned_userid}",
                    )
                )
                .values(channel_source=f"wecom:{successor_userid}")
            )
            await db.flush()

        logger.info(
            "WeComSCRM: 离职客户迁移完成",
            resigned_userid=resigned_userid,
            successor_userid=successor_userid,
            total=total,
            transferred=transferred,
            failed=len(failed_list),
        )

        return {
            "total": total,
            "transferred": transferred,
            "failed": len(failed_list),
            "failed_list": failed_list,
        }

    async def sync_private_domain_behavior_to_cdp(
        self,
        db: AsyncSession,
        external_userid: str,
        behavior_type: str,
        metadata: dict,
    ) -> bool:
        """
        将私域行为（点击/回复/转发/购买意向）同步到CDP。

        behavior_type:
            click_menu / reply / share / purchase_intent / coupon_claimed

        逻辑：
        1. 用 external_userid 查找 consumer_id（通过 wechat_openid 关联）
        2. 更新 BrandConsumerProfile.lifecycle_state（根据行为类型推进状态）
        3. 发布行为事件到 signal_bus 供其他服务消费

        Args:
            db              : 异步数据库 Session
            external_userid : 企微外部联系人 userid
            behavior_type   : 行为类型
            metadata        : 附加数据（如品牌ID、门店ID、行为详情）

        Returns:
            True 表示同步成功
        """
        # 1. 通过 wechat_openid 找 ConsumerIdentity
        result = await db.execute(
            select(ConsumerIdentity).where(
                ConsumerIdentity.wechat_openid == external_userid,
                ConsumerIdentity.is_merged.is_(False),
            )
        )
        identity = result.scalar_one_or_none()

        if not identity:
            logger.info(
                "WeComSCRM: 未找到匹配会员，行为事件忽略",
                external_userid=external_userid,
                behavior_type=behavior_type,
            )
            return False

        consumer_id = str(identity.id)
        brand_id = metadata.get("brand_id", "")
        group_id = metadata.get("group_id", "")

        # 2. 根据行为类型推进 lifecycle_state
        new_state = self._infer_lifecycle_state_from_behavior(behavior_type)
        if new_state and brand_id and group_id:
            try:
                await BrandConsumerProfileRepo.upsert_profile(
                    db,
                    consumer_id=identity.id,
                    brand_id=brand_id,
                    group_id=group_id,
                    lifecycle_state=new_state,
                )
            except Exception as exc:
                logger.warning(
                    "WeComSCRM: 更新 lifecycle_state 失败",
                    consumer_id=consumer_id,
                    error=str(exc),
                )

        # 3. 发布行为事件到 signal_bus
        await self._publish_behavior_event(
            consumer_id=consumer_id,
            external_userid=external_userid,
            behavior_type=behavior_type,
            metadata=metadata,
        )

        logger.info(
            "WeComSCRM: 私域行为已同步到CDP",
            consumer_id=consumer_id,
            behavior_type=behavior_type,
        )
        return True

    async def get_customer_profile_sidebar(
        self,
        db: AsyncSession,
        external_userid: str,
        store_id: str,
    ) -> Dict[str, Any]:
        """
        导购助手侧边栏：获取客户完整画像。

        返回：基本信息 + RFM + 历史消费 + 当前权益 + 推荐话术

        Args:
            db              : 异步数据库 Session
            external_userid : 企微外部联系人 userid
            store_id        : 当前门店 ID

        Returns:
            完整画像字典，字段见下方注释
        """
        # 通过 wechat_openid 查 ConsumerIdentity
        result = await db.execute(
            select(ConsumerIdentity).where(
                ConsumerIdentity.wechat_openid == external_userid,
                ConsumerIdentity.is_merged.is_(False),
            )
        )
        identity = result.scalar_one_or_none()

        if not identity:
            return {
                "found": False,
                "external_userid": external_userid,
                "message": "未找到匹配会员，可能是新客户",
            }

        # 查 PrivateDomainMember（当前门店维度）
        member_result = await db.execute(
            select(PrivateDomainMember).where(
                and_(
                    PrivateDomainMember.store_id == store_id,
                    PrivateDomainMember.consumer_id == identity.id,
                )
            )
        )
        member = member_result.scalar_one_or_none()

        # 查品牌档案列表（跨品牌 One ID 视图）
        profile_result = await db.execute(
            select(BrandConsumerProfile).where(
                BrandConsumerProfile.consumer_id == identity.id,
                BrandConsumerProfile.is_active.is_(True),
            )
        )
        profiles = profile_result.scalars().all()

        # 聚合消费统计
        total_brand_orders = sum(p.brand_order_count or 0 for p in profiles)
        total_brand_amount_fen = sum(p.brand_order_amount_fen or 0 for p in profiles)
        lifecycle_states = [p.lifecycle_state for p in profiles]
        current_lifecycle = lifecycle_states[0] if lifecycle_states else "registered"

        # 推荐话术（基于 lifecycle_state）
        suggested_script = self._get_suggested_script(current_lifecycle, member)

        sidebar = {
            "found": True,
            "consumer_id": str(identity.id),
            # 基本信息
            "basic": {
                "display_name": identity.display_name,
                "gender": identity.gender,
                "wechat_nickname": identity.wechat_nickname,
                "tags": identity.tags or [],
                "dietary_restrictions": identity.dietary_restrictions or [],
                "anniversary": str(identity.anniversary) if identity.anniversary else None,
            },
            # RFM（门店维度）
            "rfm": {
                "rfm_level": member.rfm_level if member else None,
                "r_score": member.r_score if member else None,
                "f_score": member.f_score if member else None,
                "m_score": member.m_score if member else None,
                "recency_days": member.recency_days if member else None,
                "frequency": member.frequency if member else None,
                "monetary_yuan": round((member.monetary or 0) / 100, 2) if member else 0.0,
            },
            # 历史消费（跨品牌聚合）
            "consumption": {
                "total_order_count": identity.total_order_count or total_brand_orders,
                "total_order_amount_yuan": round(
                    (identity.total_order_amount_fen or total_brand_amount_fen) / 100, 2
                ),
                "first_order_at": (
                    str(identity.first_order_at) if identity.first_order_at else None
                ),
                "last_order_at": (
                    str(identity.last_order_at) if identity.last_order_at else None
                ),
            },
            # 当前权益（当前品牌维度）
            "benefits": [
                {
                    "brand_id": p.brand_id,
                    "brand_level": p.brand_level,
                    "brand_points": p.brand_points,
                    "brand_balance_yuan": round(p.brand_balance_fen / 100, 2),
                    "lifecycle_state": p.lifecycle_state,
                }
                for p in profiles
            ],
            # 生命周期
            "lifecycle_state": current_lifecycle,
            # 推荐话术
            "suggested_script": suggested_script,
        }

        return sidebar

    # ---------- 私有辅助方法 ----------

    async def _get_external_contact_phone(self, external_userid: str) -> Optional[str]:
        """
        调用企微 API 获取外部联系人手机号。

        注：需要企微「客户联系」API 权限及用户授权。
        实际手机号可能通过 externalcontact/getdetailinfo 接口获取，
        部分企业需用户主动授权才能获取真实手机号（字段 mobile）。
        """
        try:
            from src.services.wechat_service import wechat_service

            token = await wechat_service.get_access_token()
            import httpx
            import os

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://qyapi.weixin.qq.com/cgi-bin/externalcontact/get",
                    params={
                        "access_token": token,
                        "external_userid": external_userid,
                    },
                    timeout=float(os.getenv("WECHAT_HTTP_TIMEOUT", "30.0")),
                )
                data = resp.json()

            if data.get("errcode") == 0:
                contact_info = data.get("external_contact", {})
                phone = contact_info.get("mobile") or contact_info.get("phone")
                return phone
            else:
                logger.warning(
                    "WeComSCRM: 获取外部联系人详情失败",
                    external_userid=external_userid,
                    errcode=data.get("errcode"),
                    errmsg=data.get("errmsg"),
                )
                return None
        except Exception as exc:
            logger.warning(
                "WeComSCRM: 获取外部联系人手机号异常",
                external_userid=external_userid,
                error=str(exc),
            )
            return None

    async def _upsert_private_domain_wecom_id(
        self,
        db: AsyncSession,
        consumer_id: uuid.UUID,
        store_id: str,
        external_userid: str,
        staff_userid: str,
    ) -> None:
        """更新或创建 PrivateDomainMember，写入企微外部联系人关联"""
        result = await db.execute(
            select(PrivateDomainMember).where(
                and_(
                    PrivateDomainMember.store_id == store_id,
                    PrivateDomainMember.consumer_id == consumer_id,
                )
            )
        )
        member = result.scalar_one_or_none()

        if member:
            # 更新：写入 wechat_openid（企微 external_userid 作为 openid 存储）
            member.wechat_openid = external_userid
            member.channel_source = f"wecom:{staff_userid}"
            await db.flush()
        else:
            # 新建：最小化 PrivateDomainMember
            new_member = PrivateDomainMember(
                store_id=store_id,
                customer_id=str(consumer_id),
                consumer_id=consumer_id,
                wechat_openid=external_userid,
                channel_source=f"wecom:{staff_userid}",
            )
            db.add(new_member)
            await db.flush()

    async def _create_new_consumer_from_wecom(
        self,
        db: AsyncSession,
        phone: str,
        external_userid: str,
        staff_userid: str,
        store_id: str,
    ) -> str:
        """创建新的 ConsumerIdentity + PrivateDomainMember（企微来源）"""
        new_identity = ConsumerIdentity(
            primary_phone=phone,
            wechat_openid=external_userid,
            source="wecom",
            confidence_score=0.8,  # 企微手机号置信度（需用户授权才为 1.0）
        )
        db.add(new_identity)
        await db.flush()  # 获取 id

        new_member = PrivateDomainMember(
            store_id=store_id,
            customer_id=str(new_identity.id),
            consumer_id=new_identity.id,
            wechat_openid=external_userid,
            channel_source=f"wecom:{staff_userid}",
        )
        db.add(new_member)
        await db.flush()

        consumer_id = str(new_identity.id)
        logger.info(
            "WeComSCRM: 通过企微创建新消费者",
            consumer_id=consumer_id,
            store_id=store_id,
        )
        return consumer_id

    async def _call_wecom_transfer_customer(
        self,
        external_userid_list: List[str],
        handover_userid: str,
        takeover_userid: str,
    ) -> Dict[str, Any]:
        """
        调用企微客户迁移 API。
        API 文档：POST /cgi-bin/externalcontact/transfer_customer

        注：每次最多 100 个外部联系人；转接完成后 24 小时内接替人不可操作。
        """
        try:
            from src.services.wechat_service import wechat_service

            token = await wechat_service.get_access_token()
            import httpx
            import os

            payload = {
                "handover_userid": handover_userid,
                "takeover_userid": takeover_userid,
                "external_userid": external_userid_list,
            }

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://qyapi.weixin.qq.com/cgi-bin/externalcontact/transfer_customer",
                    params={"access_token": token},
                    json=payload,
                    timeout=float(os.getenv("WECHAT_HTTP_TIMEOUT", "30.0")),
                )
                data = resp.json()

            if data.get("errcode") == 0:
                customer_list = data.get("customer", [])
                failed = [
                    c["external_userid"]
                    for c in customer_list
                    if c.get("errcode") != 0
                ]
                transferred = len(external_userid_list) - len(failed)
                return {"transferred_count": transferred, "failed_list": failed}
            else:
                logger.error(
                    "WeComSCRM: transfer_customer API 失败",
                    errcode=data.get("errcode"),
                    errmsg=data.get("errmsg"),
                )
                return {
                    "transferred_count": 0,
                    "failed_list": external_userid_list,
                }
        except Exception as exc:
            logger.error(
                "WeComSCRM: 调用 transfer_customer 异常",
                error=str(exc),
                exc_info=True,
            )
            return {
                "transferred_count": 0,
                "failed_list": external_userid_list,
            }

    def _infer_lifecycle_state_from_behavior(
        self, behavior_type: str
    ) -> Optional[str]:
        """根据行为类型推断 lifecycle_state 变迁（仅向前推进，不回退）"""
        _behavior_to_state: Dict[str, str] = {
            "purchase_intent": "repeat",
            "coupon_claimed": "repeat",
            "click_menu": "registered",
            "reply": "registered",
            "share": "repeat",
        }
        return _behavior_to_state.get(behavior_type)

    async def _publish_behavior_event(
        self,
        consumer_id: str,
        external_userid: str,
        behavior_type: str,
        metadata: dict,
    ) -> None:
        """
        发布行为事件到 signal_bus（供 private_domain_agent 等消费）。
        当前使用日志记录，Phase 3 接入 Redis Pub/Sub 或事件总线。
        """
        logger.info(
            "WeComSCRM: 行为事件",
            event_type="wecom_behavior",
            consumer_id=consumer_id,
            external_userid=external_userid,
            behavior_type=behavior_type,
            metadata=metadata,
        )

    def _get_suggested_script(
        self,
        lifecycle_state: str,
        member: Optional[PrivateDomainMember],
    ) -> str:
        """根据生命周期状态和 RFM 推荐话术"""
        rfm_level = member.rfm_level if member else None

        if lifecycle_state in ("vip", "repeat") and rfm_level in ("S1", "S2"):
            return "这位是我们的忠实老客户，可主动介绍新菜/会员专属活动，并询问上次用餐体验。"
        elif lifecycle_state in ("at_risk", "dormant"):
            return "该客户已较久未来，建议主动关怀，可提供回流优惠或邀请体验新品。"
        elif lifecycle_state == "lost":
            return "该客户流失时间较长，建议发送诚意唤回信息，避免销售式话术。"
        elif lifecycle_state in ("lead", "registered"):
            return "新客户或潜在客户，重点介绍品牌特色和门店位置，降低首次消费门槛。"
        else:
            return "根据客户历史信息提供个性化服务推荐。"


# 全局单例
wecom_scrm_service = WeComSCRMService()
