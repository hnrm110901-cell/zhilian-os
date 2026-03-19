"""
CDP WeChat Channel — 基于 consumer_id 的企微消息触达（Sprint 2）

功能：
1. 按 consumer_id 发送企微消息（自动查找 wechat_openid）
2. 按 RFM 等级批量触达（S4/S5 流失唤醒）
3. 按标签定向推送
4. 消息发送记录归因到 consumer_id
"""

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.consumer_identity import ConsumerIdentity
from src.models.private_domain import PrivateDomainMember

logger = logging.getLogger(__name__)


class CDPWeChatChannel:
    """CDP 企微消息通道"""

    async def send_to_consumer(
        self,
        db: AsyncSession,
        consumer_id,
        message_type: str,
        content: str,
        *,
        store_id: Optional[str] = None,
    ) -> dict:
        """
        向指定 consumer_id 发送企微消息。

        流程：
        1. 查 ConsumerIdentity.wechat_openid
        2. 如无 openid，查 PrivateDomainMember.wechat_openid
        3. 调用 WeChatService 发送
        4. 记录发送日志

        返回：{"sent": bool, "channel": "wechat/sms/none", "reason": str}
        """
        # 查消费者信息
        consumer = await db.get(ConsumerIdentity, consumer_id)
        if not consumer:
            return {"sent": False, "channel": "none", "reason": "consumer_not_found"}

        # 查找 wechat_openid
        openid = consumer.wechat_openid
        if not openid:
            # 从 PrivateDomainMember 查找
            where = [PrivateDomainMember.consumer_id == consumer_id]
            if store_id:
                where.append(PrivateDomainMember.store_id == store_id)
            stmt = (
                select(PrivateDomainMember.wechat_openid)
                .where(
                    and_(*where),
                    PrivateDomainMember.wechat_openid.isnot(None),
                )
                .limit(1)
            )
            result = await db.execute(stmt)
            openid = result.scalar_one_or_none()

        if not openid:
            # 降级：记录无 openid，后续可走短信通道
            logger.info(
                "CDP WeChat: consumer=%s 无 openid，跳过企微推送",
                consumer_id,
            )
            return {"sent": False, "channel": "none", "reason": "no_wechat_openid"}

        # 调用 WeChatService（延迟导入避免循环）
        try:
            from src.services.wechat_service import wechat_service

            if message_type == "text":
                await wechat_service.send_text_message(content, touser=openid)
            elif message_type == "markdown":
                await wechat_service.send_markdown_message(content, touser=openid)
            elif message_type == "card":
                await wechat_service.send_card_message(
                    title="屯象OS通知",
                    description=content,
                    url="",
                    btntxt="查看详情",
                    touser=openid,
                )
            else:
                await wechat_service.send_text_message(content, touser=openid)

            return {"sent": True, "channel": "wechat", "reason": "ok"}
        except Exception as e:
            logger.warning("CDP WeChat send failed: consumer=%s error=%s", consumer_id, e)
            return {"sent": False, "channel": "wechat", "reason": str(e)}

    async def batch_send_by_rfm(
        self,
        db: AsyncSession,
        store_id: str,
        rfm_levels: List[str],
        message_type: str,
        content: str,
        *,
        limit: int = 100,
        dry_run: bool = True,
    ) -> dict:
        """
        按 RFM 等级批量发送企微消息。

        典型用法：向 S4/S5（流失/待挽回）客户发送唤醒消息。

        参数：
            rfm_levels: ["S4", "S5"] — 目标等级列表
            dry_run: True 时只统计不发送

        返回：{"target_count": N, "sent_count": M, "dry_run": bool}
        """
        stmt = (
            select(
                PrivateDomainMember.consumer_id,
                PrivateDomainMember.wechat_openid,
                PrivateDomainMember.customer_id,
            )
            .where(
                PrivateDomainMember.store_id == store_id,
                PrivateDomainMember.rfm_level.in_(rfm_levels),
                PrivateDomainMember.is_active.is_(True),
                PrivateDomainMember.consumer_id.isnot(None),
            )
            .limit(limit)
        )
        result = await db.execute(stmt)
        members = result.all()

        target_count = len(members)
        sent_count = 0

        if dry_run:
            return {
                "target_count": target_count,
                "sent_count": 0,
                "dry_run": True,
                "rfm_levels": rfm_levels,
            }

        for consumer_id, openid, customer_id in members:
            if not consumer_id:
                continue
            r = await self.send_to_consumer(
                db,
                consumer_id,
                message_type,
                content,
                store_id=store_id,
            )
            if r.get("sent"):
                sent_count += 1

        return {
            "target_count": target_count,
            "sent_count": sent_count,
            "dry_run": False,
            "rfm_levels": rfm_levels,
        }

    async def batch_send_by_tags(
        self,
        db: AsyncSession,
        store_id: str,
        tags: List[str],
        message_type: str,
        content: str,
        *,
        limit: int = 100,
        dry_run: bool = True,
    ) -> dict:
        """
        按标签定向推送。

        标签匹配逻辑：ConsumerIdentity.tags JSON 数组包含指定标签之一。
        """
        # 通过 PrivateDomainMember 查找有 consumer_id 的会员
        stmt = (
            select(
                PrivateDomainMember.consumer_id,
                PrivateDomainMember.dynamic_tags,
            )
            .where(
                PrivateDomainMember.store_id == store_id,
                PrivateDomainMember.is_active.is_(True),
                PrivateDomainMember.consumer_id.isnot(None),
            )
            .limit(limit * 3)  # 多取以过滤
        )
        result = await db.execute(stmt)
        rows = result.all()

        # 过滤匹配标签的会员
        target_tags = set(tags)
        matched = []
        for consumer_id, member_tags in rows:
            if not member_tags:
                continue
            if target_tags.intersection(set(member_tags)):
                matched.append(consumer_id)
            if len(matched) >= limit:
                break

        target_count = len(matched)
        sent_count = 0

        if dry_run:
            return {
                "target_count": target_count,
                "sent_count": 0,
                "dry_run": True,
                "tags": tags,
            }

        for cid in matched:
            r = await self.send_to_consumer(
                db,
                cid,
                message_type,
                content,
                store_id=store_id,
            )
            if r.get("sent"):
                sent_count += 1

        return {
            "target_count": target_count,
            "sent_count": sent_count,
            "dry_run": False,
            "tags": tags,
        }

    async def get_channel_stats(
        self,
        db: AsyncSession,
        store_id: Optional[str] = None,
    ) -> dict:
        """
        企微通道统计：有 openid 的会员数 / 总会员数 / 覆盖率
        """
        from sqlalchemy import func

        where = [PrivateDomainMember.is_active.is_(True)]
        if store_id:
            where.append(PrivateDomainMember.store_id == store_id)

        total = await db.scalar(select(func.count(PrivateDomainMember.id)).where(and_(*where))) or 0

        with_openid = (
            await db.scalar(
                select(func.count(PrivateDomainMember.id)).where(
                    and_(
                        *where,
                        PrivateDomainMember.wechat_openid.isnot(None),
                        PrivateDomainMember.wechat_openid != "",
                    )
                )
            )
            or 0
        )

        with_consumer_id = (
            await db.scalar(
                select(func.count(PrivateDomainMember.id)).where(
                    and_(
                        *where,
                        PrivateDomainMember.consumer_id.isnot(None),
                    )
                )
            )
            or 0
        )

        return {
            "total_members": total,
            "with_wechat_openid": with_openid,
            "wechat_coverage_rate": round(with_openid / total, 4) if total > 0 else 0.0,
            "with_consumer_id": with_consumer_id,
            "cdp_link_rate": round(with_consumer_id / total, 4) if total > 0 else 0.0,
        }


# 全局单例
cdp_wechat_channel = CDPWeChatChannel()
