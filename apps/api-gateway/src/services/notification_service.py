"""
Notification Service
通知服务 - 处理通知的创建、发送、查询等业务逻辑
"""
import os
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from ..models.notification import (
    Notification, NotificationType, NotificationPriority,
    NotificationPreference, NotificationRule,
)
from ..core.database import get_db_session
from ..core.websocket import manager
import structlog

logger = structlog.get_logger()


class NotificationService:
    """通知服务"""

    async def create_notification(
        self,
        title: str,
        message: str,
        type: NotificationType = NotificationType.INFO,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        user_id: Optional[str] = None,
        role: Optional[str] = None,
        store_id: Optional[str] = None,
        extra_data: Optional[dict] = None,
        source: Optional[str] = None,
        send_realtime: bool = True,
    ) -> Notification:
        """
        创建通知

        Args:
            title: 通知标题
            message: 通知内容
            type: 通知类型
            priority: 优先级
            user_id: 特定用户ID(如果指定,只发给该用户)
            role: 特定角色(如果指定,发给该角色的所有用户)
            store_id: 特定门店(如果指定,只发给该门店的用户)
            extra_data: 额外数据
            source: 来源
            send_realtime: 是否实时推送
        """
        async with get_db_session() as session:
            notification = Notification(
                id=uuid.uuid4(),
                title=title,
                message=message,
                type=type.value if isinstance(type, NotificationType) else type,
                priority=priority.value if isinstance(priority, NotificationPriority) else priority,
                user_id=user_id,
                role=role,
                store_id=store_id,
                extra_data=extra_data,
                source=source,
                is_read=False,
            )

            session.add(notification)
            await session.commit()
            await session.refresh(notification)

            logger.info(
                "通知创建成功",
                notification_id=str(notification.id),
                title=title,
                user_id=user_id,
                role=role,
                store_id=store_id,
            )

            # 实时推送
            if send_realtime:
                await self._send_realtime_notification(notification)

            return notification

    async def _send_realtime_notification(self, notification: Notification):
        """实时推送通知"""
        notification_data = notification.to_dict()

        try:
            if notification.user_id:
                # 发送给特定用户
                await manager.send_personal_message(notification_data, str(notification.user_id))
            elif notification.role and notification.store_id:
                # 发送给特定门店的特定角色
                await manager.send_to_role(notification_data, notification.role, notification.store_id)
            elif notification.role:
                # 发送给特定角色的所有用户
                await manager.send_to_role(notification_data, notification.role)
            elif notification.store_id:
                # 发送给特定门店的所有用户
                await manager.send_to_store(notification_data, notification.store_id)
            else:
                # 广播给所有用户
                await manager.broadcast(notification_data)

            logger.info("实时通知推送成功", notification_id=str(notification.id))
        except Exception as e:
            logger.error("实时通知推送失败", notification_id=str(notification.id), error=str(e))

    async def get_user_notifications(
        self,
        user_id: str,
        role: str,
        store_id: Optional[str] = None,
        is_read: Optional[bool] = None,
        type_filter: Optional[str] = None,
        priority_filter: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = int(os.getenv("NOTIFICATION_QUERY_LIMIT", "50")),
        offset: int = 0,
    ) -> List[Notification]:
        """
        获取用户的通知列表

        包括:
        1. 发给该用户的通知
        2. 发给该用户角色的通知
        3. 发给该用户门店的通知
        4. 广播通知
        """
        async with get_db_session() as session:
            conditions = []

            # 发给特定用户的通知
            conditions.append(Notification.user_id == user_id)

            # 发给该角色的通知
            conditions.append(
                and_(
                    Notification.role == role,
                    or_(Notification.store_id == store_id, Notification.store_id.is_(None)),
                )
            )

            # 发给该门店的通知
            if store_id:
                conditions.append(
                    and_(Notification.store_id == store_id, Notification.role.is_(None))
                )

            # 广播通知
            conditions.append(
                and_(
                    Notification.user_id.is_(None),
                    Notification.role.is_(None),
                    Notification.store_id.is_(None),
                )
            )

            # 构建查询
            stmt = select(Notification).where(or_(*conditions))

            # 是否已读过滤
            if is_read is not None:
                stmt = stmt.where(Notification.is_read == is_read)

            # 类型过滤
            if type_filter is not None:
                stmt = stmt.where(Notification.type == type_filter)

            # 优先级过滤
            if priority_filter is not None:
                stmt = stmt.where(Notification.priority == priority_filter)

            # 关键词搜索（标题或内容）
            if keyword is not None:
                kw = f"%{keyword}%"
                stmt = stmt.where(
                    or_(Notification.title.ilike(kw), Notification.message.ilike(kw))
                )

            # 排序和分页
            stmt = stmt.order_by(Notification.created_at.desc()).limit(limit).offset(offset)

            result = await session.execute(stmt)
            notifications = result.scalars().all()

            return notifications

    async def mark_as_read(self, notification_id: str, user_id: str) -> bool:
        """标记通知为已读"""
        async with get_db_session() as session:
            stmt = select(Notification).where(Notification.id == notification_id)
            result = await session.execute(stmt)
            notification = result.scalar_one_or_none()

            if not notification:
                return False

            # 验证用户权限(只能标记自己的通知)
            if notification.user_id and str(notification.user_id) != user_id:
                return False

            notification.is_read = True
            notification.read_at = datetime.utcnow().isoformat()

            await session.commit()
            logger.info("通知已标记为已读", notification_id=notification_id, user_id=user_id)

            return True

    async def mark_all_as_read(self, user_id: str, role: str, store_id: Optional[str] = None) -> int:
        """标记用户的所有未读通知为已读"""
        notifications = await self.get_user_notifications(
            user_id=user_id, role=role, store_id=store_id, is_read=False
        )

        count = 0
        for notification in notifications:
            if await self.mark_as_read(str(notification.id), user_id):
                count += 1

        logger.info("批量标记通知为已读", user_id=user_id, count=count)
        return count

    async def delete_notification(self, notification_id: str, user_id: str) -> bool:
        """删除通知"""
        async with get_db_session() as session:
            stmt = select(Notification).where(Notification.id == notification_id)
            result = await session.execute(stmt)
            notification = result.scalar_one_or_none()

            if not notification:
                return False

            # 验证用户权限
            if notification.user_id and str(notification.user_id) != user_id:
                return False

            await session.delete(notification)
            await session.commit()

            logger.info("通知已删除", notification_id=notification_id, user_id=user_id)
            return True

    async def get_unread_count(self, user_id: str, role: str, store_id: Optional[str] = None) -> int:
        """获取未读通知数量"""
        notifications = await self.get_user_notifications(
            user_id=user_id, role=role, store_id=store_id, is_read=False
        )
        return len(notifications)

    # ------------------------------------------------------------------ #
    # 通知偏好设置                                                          #
    # ------------------------------------------------------------------ #

    async def get_preferences(self, user_id: str) -> List[NotificationPreference]:
        """获取用户所有通知偏好"""
        async with get_db_session() as session:
            stmt = select(NotificationPreference).where(
                NotificationPreference.user_id == user_id
            ).order_by(NotificationPreference.notification_type)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def upsert_preference(
        self,
        user_id: str,
        notification_type: Optional[str],
        channels: List[str],
        is_enabled: bool = True,
        quiet_hours_start: Optional[str] = None,
        quiet_hours_end: Optional[str] = None,
    ) -> NotificationPreference:
        """创建或更新通知偏好（同一 user_id + notification_type 唯一）"""
        async with get_db_session() as session:
            stmt = select(NotificationPreference).where(
                and_(
                    NotificationPreference.user_id == user_id,
                    NotificationPreference.notification_type == notification_type,
                )
            )
            result = await session.execute(stmt)
            pref = result.scalar_one_or_none()

            if pref:
                pref.channels = channels
                pref.is_enabled = is_enabled
                pref.quiet_hours_start = quiet_hours_start
                pref.quiet_hours_end = quiet_hours_end
            else:
                pref = NotificationPreference(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    notification_type=notification_type,
                    channels=channels,
                    is_enabled=is_enabled,
                    quiet_hours_start=quiet_hours_start,
                    quiet_hours_end=quiet_hours_end,
                )
                session.add(pref)

            await session.commit()
            await session.refresh(pref)
            logger.info("通知偏好已更新", user_id=user_id, notification_type=notification_type)
            return pref

    async def delete_preference(self, user_id: str, notification_type: Optional[str]) -> bool:
        """删除通知偏好"""
        async with get_db_session() as session:
            stmt = select(NotificationPreference).where(
                and_(
                    NotificationPreference.user_id == user_id,
                    NotificationPreference.notification_type == notification_type,
                )
            )
            result = await session.execute(stmt)
            pref = result.scalar_one_or_none()
            if not pref:
                return False
            await session.delete(pref)
            await session.commit()
            return True

    def _is_in_quiet_hours(self, pref: NotificationPreference) -> bool:
        """判断当前时间是否在免打扰时段内"""
        if not pref.quiet_hours_start or not pref.quiet_hours_end:
            return False
        now = datetime.utcnow().strftime("%H:%M")
        start = pref.quiet_hours_start
        end = pref.quiet_hours_end
        # 跨午夜处理（如 22:00 - 08:00）
        if start <= end:
            return start <= now <= end
        else:
            return now >= start or now <= end

    # ------------------------------------------------------------------ #
    # 通知频率规则                                                          #
    # ------------------------------------------------------------------ #

    async def get_rules(self, user_id: Optional[str] = None) -> List[NotificationRule]:
        """获取规则列表（用户级 + 全局）"""
        async with get_db_session() as session:
            conditions = [NotificationRule.is_active == True]
            if user_id:
                conditions.append(
                    or_(
                        NotificationRule.user_id == user_id,
                        NotificationRule.user_id.is_(None),
                    )
                )
            else:
                conditions.append(NotificationRule.user_id.is_(None))

            stmt = select(NotificationRule).where(and_(*conditions))
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def upsert_rule(
        self,
        max_count: int,
        time_window_minutes: int,
        user_id: Optional[str] = None,
        notification_type: Optional[str] = None,
        description: Optional[str] = None,
    ) -> NotificationRule:
        """创建或更新频率规则"""
        async with get_db_session() as session:
            stmt = select(NotificationRule).where(
                and_(
                    NotificationRule.user_id == user_id,
                    NotificationRule.notification_type == notification_type,
                )
            )
            result = await session.execute(stmt)
            rule = result.scalar_one_or_none()

            if rule:
                rule.max_count = max_count
                rule.time_window_minutes = time_window_minutes
                rule.is_active = True
                if description is not None:
                    rule.description = description
            else:
                rule = NotificationRule(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    notification_type=notification_type,
                    max_count=max_count,
                    time_window_minutes=time_window_minutes,
                    is_active=True,
                    description=description,
                )
                session.add(rule)

            await session.commit()
            await session.refresh(rule)
            logger.info("通知规则已更新", user_id=user_id, notification_type=notification_type)
            return rule

    async def delete_rule(self, rule_id: str, user_id: Optional[str] = None) -> bool:
        """删除规则（用户只能删除自己的规则，管理员可删全局规则）"""
        async with get_db_session() as session:
            stmt = select(NotificationRule).where(NotificationRule.id == rule_id)
            result = await session.execute(stmt)
            rule = result.scalar_one_or_none()
            if not rule:
                return False
            # 非管理员只能删自己的规则
            if user_id and rule.user_id and str(rule.user_id) != user_id:
                return False
            await session.delete(rule)
            await session.commit()
            return True

    async def check_rate_limit(self, user_id: str, notification_type: str) -> bool:
        """
        检查是否超过频率限制。
        返回 True 表示允许发送，False 表示已超限。
        优先匹配用户级规则，其次全局规则，无规则则允许。
        """
        rules = await self.get_rules(user_id=user_id)

        # 找最匹配的规则：用户级 + 精确类型 > 用户级 + 全局类型 > 全局 + 精确类型 > 全局
        def rule_priority(r: NotificationRule) -> int:
            score = 0
            if r.user_id is not None:
                score += 2
            if r.notification_type == notification_type:
                score += 1
            return score

        matched = [
            r for r in rules
            if r.notification_type in (notification_type, None)
        ]
        if not matched:
            return True

        best_rule = max(matched, key=rule_priority)

        # 统计时间窗口内已发送数量
        async with get_db_session() as session:
            since = datetime.utcnow() - timedelta(minutes=best_rule.time_window_minutes)
            conditions = [
                Notification.created_at >= since,
                Notification.type == notification_type,
            ]
            if user_id:
                conditions.append(Notification.user_id == user_id)

            count_stmt = select(func.count(Notification.id)).where(and_(*conditions))
            result = await session.execute(count_stmt)
            count = result.scalar() or 0

        allowed = count < best_rule.max_count
        if not allowed:
            logger.warning(
                "通知频率超限，已拦截",
                user_id=user_id,
                notification_type=notification_type,
                count=count,
                max_count=best_rule.max_count,
                window_minutes=best_rule.time_window_minutes,
            )
        return allowed


# 全局通知服务实例
notification_service = NotificationService()
