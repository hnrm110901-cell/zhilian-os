"""
审计日志服务
记录和查询系统操作日志
"""
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc
import structlog

from src.models.audit_log import AuditLog, AuditAction, ResourceType

logger = structlog.get_logger()


class AuditLogService:
    """审计日志服务"""

    async def log_action(
        self,
        action: str,
        resource_type: str,
        user_id: str,
        username: Optional[str] = None,
        user_role: Optional[str] = None,
        resource_id: Optional[str] = None,
        description: Optional[str] = None,
        changes: Optional[Dict[str, Any]] = None,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_method: Optional[str] = None,
        request_path: Optional[str] = None,
        status: str = "success",
        error_message: Optional[str] = None,
        store_id: Optional[str] = None,
        db: Optional[AsyncSession] = None
    ) -> AuditLog:
        """
        记录审计日志

        Args:
            action: 操作类型
            resource_type: 资源类型
            user_id: 用户ID
            username: 用户名
            user_role: 用户角色
            resource_id: 资源ID
            description: 操作描述
            changes: 变更内容
            old_value: 旧值
            new_value: 新值
            ip_address: IP地址
            user_agent: User Agent
            request_method: 请求方法
            request_path: 请求路径
            status: 操作状态
            error_message: 错误信息
            store_id: 门店ID
            db: 数据库会话

        Returns:
            审计日志对象
        """
        from src.core.database import get_db_session

        async with get_db_session() as session:
            audit_log = AuditLog(
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                user_id=user_id,
                username=username,
                user_role=user_role,
                description=description,
                changes=changes,
                old_value=old_value,
                new_value=new_value,
                ip_address=ip_address,
                user_agent=user_agent,
                request_method=request_method,
                request_path=request_path,
                status=status,
                error_message=error_message,
                store_id=store_id,
            )

            session.add(audit_log)
            await session.commit()
            await session.refresh(audit_log)

            logger.info(
                "审计日志已记录",
                audit_log_id=audit_log.id,
                action=action,
                resource_type=resource_type,
                user_id=user_id,
                status=status
            )

            return audit_log

    async def get_logs(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        status: Optional[str] = None,
        store_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        search_query: Optional[str] = None,
        skip: int = 0,
        limit: int = int(os.getenv("AUDIT_QUERY_LIMIT", "100")),
        db: Optional[AsyncSession] = None
    ) -> tuple[List[AuditLog], int]:
        """
        查询审计日志

        Args:
            user_id: 用户ID
            action: 操作类型
            resource_type: 资源类型
            resource_id: 资源ID
            status: 操作状态
            store_id: 门店ID
            start_date: 开始日期
            end_date: 结束日期
            search_query: 搜索关键词
            skip: 跳过记录数
            limit: 返回记录数
            db: 数据库会话

        Returns:
            (日志列表, 总数)
        """
        from src.core.database import get_db_session

        async with get_db_session() as session:
            # 构建查询条件
            conditions = []

            if user_id:
                conditions.append(AuditLog.user_id == user_id)

            if action:
                conditions.append(AuditLog.action == action)

            if resource_type:
                conditions.append(AuditLog.resource_type == resource_type)

            if resource_id:
                conditions.append(AuditLog.resource_id == resource_id)

            if status:
                conditions.append(AuditLog.status == status)

            if store_id:
                conditions.append(AuditLog.store_id == store_id)

            if start_date:
                conditions.append(AuditLog.created_at >= start_date)

            if end_date:
                conditions.append(AuditLog.created_at <= end_date)

            if search_query:
                search_conditions = [
                    AuditLog.description.ilike(f"%{search_query}%"),
                    AuditLog.username.ilike(f"%{search_query}%"),
                    AuditLog.action.ilike(f"%{search_query}%"),
                ]
                conditions.append(or_(*search_conditions))

            # 查询总数
            count_stmt = select(func.count(AuditLog.id))
            if conditions:
                count_stmt = count_stmt.where(and_(*conditions))

            count_result = await session.execute(count_stmt)
            total = count_result.scalar() or 0

            # 查询日志列表
            stmt = select(AuditLog)
            if conditions:
                stmt = stmt.where(and_(*conditions))

            stmt = stmt.order_by(desc(AuditLog.created_at)).offset(skip).limit(limit)

            result = await session.execute(stmt)
            logs = result.scalars().all()

            return list(logs), total

    async def get_user_activity_stats(
        self,
        user_id: str,
        days: int = int(os.getenv("AUDIT_STATS_DAYS_SHORT", "30")),
        db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        获取用户活动统计

        Args:
            user_id: 用户ID
            days: 统计天数
            db: 数据库会话

        Returns:
            统计数据
        """
        from src.core.database import get_db_session

        start_date = datetime.utcnow() - timedelta(days=days)

        async with get_db_session() as session:
            # 总操作数
            total_stmt = select(func.count(AuditLog.id)).where(
                and_(
                    AuditLog.user_id == user_id,
                    AuditLog.created_at >= start_date
                )
            )
            total_result = await session.execute(total_stmt)
            total_actions = total_result.scalar() or 0

            # 成功操作数
            success_stmt = select(func.count(AuditLog.id)).where(
                and_(
                    AuditLog.user_id == user_id,
                    AuditLog.created_at >= start_date,
                    AuditLog.status == "success"
                )
            )
            success_result = await session.execute(success_stmt)
            success_actions = success_result.scalar() or 0

            # 失败操作数
            failed_actions = total_actions - success_actions

            # 按操作类型统计
            action_stats_stmt = select(
                AuditLog.action,
                func.count(AuditLog.id).label('count')
            ).where(
                and_(
                    AuditLog.user_id == user_id,
                    AuditLog.created_at >= start_date
                )
            ).group_by(AuditLog.action)

            action_stats_result = await session.execute(action_stats_stmt)
            action_stats = {row[0]: row[1] for row in action_stats_result}

            # 最近登录时间
            last_login_stmt = select(AuditLog.created_at).where(
                and_(
                    AuditLog.user_id == user_id,
                    AuditLog.action == AuditAction.LOGIN
                )
            ).order_by(desc(AuditLog.created_at)).limit(1)

            last_login_result = await session.execute(last_login_stmt)
            last_login = last_login_result.scalar()

            return {
                "user_id": user_id,
                "period_days": days,
                "total_actions": total_actions,
                "success_actions": success_actions,
                "failed_actions": failed_actions,
                "success_rate": (success_actions / total_actions * 100) if total_actions > 0 else 0,
                "action_stats": action_stats,
                "last_login": last_login.isoformat() if last_login else None,
            }

    async def get_system_activity_stats(
        self,
        days: int = 7,
        db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        获取系统活动统计

        Args:
            days: 统计天数
            db: 数据库会话

        Returns:
            统计数据
        """
        from src.core.database import get_db_session

        start_date = datetime.utcnow() - timedelta(days=days)

        async with get_db_session() as session:
            # 总操作数
            total_stmt = select(func.count(AuditLog.id)).where(
                AuditLog.created_at >= start_date
            )
            total_result = await session.execute(total_stmt)
            total_actions = total_result.scalar() or 0

            # 活跃用户数
            active_users_stmt = select(func.count(func.distinct(AuditLog.user_id))).where(
                AuditLog.created_at >= start_date
            )
            active_users_result = await session.execute(active_users_stmt)
            active_users = active_users_result.scalar() or 0

            # 按操作类型统计
            action_stats_stmt = select(
                AuditLog.action,
                func.count(AuditLog.id).label('count')
            ).where(
                AuditLog.created_at >= start_date
            ).group_by(AuditLog.action).order_by(desc('count')).limit(int(os.getenv("AUDIT_TOP_OPS_LIMIT", "10")))

            action_stats_result = await session.execute(action_stats_stmt)
            top_actions = [{"action": row[0], "count": row[1]} for row in action_stats_result]

            # 按资源类型统计
            resource_stats_stmt = select(
                AuditLog.resource_type,
                func.count(AuditLog.id).label('count')
            ).where(
                AuditLog.created_at >= start_date
            ).group_by(AuditLog.resource_type).order_by(desc('count'))

            resource_stats_result = await session.execute(resource_stats_stmt)
            resource_stats = [{"resource_type": row[0], "count": row[1]} for row in resource_stats_result]

            # 失败操作统计
            failed_stmt = select(func.count(AuditLog.id)).where(
                and_(
                    AuditLog.created_at >= start_date,
                    AuditLog.status == "failed"
                )
            )
            failed_result = await session.execute(failed_stmt)
            failed_actions = failed_result.scalar() or 0

            return {
                "period_days": days,
                "total_actions": total_actions,
                "active_users": active_users,
                "failed_actions": failed_actions,
                "success_rate": ((total_actions - failed_actions) / total_actions * 100) if total_actions > 0 else 0,
                "top_actions": top_actions,
                "resource_stats": resource_stats,
            }

    async def delete_old_logs(
        self,
        days: int = int(os.getenv("AUDIT_STATS_DAYS_LONG", "90")),
        db: Optional[AsyncSession] = None
    ) -> int:
        """
        删除旧日志

        Args:
            days: 保留天数
            db: 数据库会话

        Returns:
            删除的记录数
        """
        from src.core.database import get_db_session

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        async with get_db_session() as session:
            stmt = select(AuditLog).where(AuditLog.created_at < cutoff_date)
            result = await session.execute(stmt)
            logs_to_delete = result.scalars().all()

            count = len(logs_to_delete)

            for log in logs_to_delete:
                await session.delete(log)

            await session.commit()

            logger.info(f"已删除 {count} 条旧审计日志", cutoff_date=cutoff_date.isoformat())

            return count


# 全局实例
audit_log_service = AuditLogService()
