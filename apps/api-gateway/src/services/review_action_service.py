"""
评论行动引擎服务
ReviewActionService: 评论自动处理规则引擎

核心流程：
  评论进入 → 遍历规则 → 匹配条件 → 执行行动 → 记录日志
  支持5种行动: auto_reply / alert_manager / create_task / signal_bus / wechat_notify
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.dianping_review import DianpingReview
from src.models.review_action import ReviewActionLog, ReviewActionRule

logger = structlog.get_logger()


class ReviewActionService:
    """评论行动引擎：将评论自动路由到对应处理行动"""

    # ── 核心处理 ──────────────────────────────────────────────────────

    async def process_review(
        self,
        db: AsyncSession,
        review: DianpingReview,
    ) -> List[Dict[str, Any]]:
        """
        主入口：对单条评论评估所有启用规则，执行匹配的行动。

        Returns:
            执行结果列表，每项包含 rule_name / action_type / status / detail
        """
        # 查询该品牌下所有启用的规则，按优先级降序
        result = await db.execute(
            select(ReviewActionRule)
            .where(
                and_(
                    ReviewActionRule.brand_id == review.brand_id,
                    ReviewActionRule.is_enabled.is_(True),
                )
            )
            .order_by(desc(ReviewActionRule.priority))
        )
        rules = result.scalars().all()

        results: List[Dict[str, Any]] = []
        for rule in rules:
            if self.evaluate_rule(rule, review):
                action_result = await self.execute_action(db, rule, review)
                results.append(action_result)

        return results

    def evaluate_rule(
        self,
        rule: ReviewActionRule,
        review: DianpingReview,
    ) -> bool:
        """
        检查评论是否匹配规则的触发条件。

        支持条件:
          - sentiment: 情感类型精确匹配
          - rating_lte: 评分 <= 阈值
          - rating_gte: 评分 >= 阈值
          - keywords: 评论内容包含任一关键词
        """
        cond = rule.trigger_condition or {}

        # 情感匹配
        if "sentiment" in cond:
            if review.sentiment != cond["sentiment"]:
                return False

        # 评分上限
        if "rating_lte" in cond:
            if review.rating > cond["rating_lte"]:
                return False

        # 评分下限
        if "rating_gte" in cond:
            if review.rating < cond["rating_gte"]:
                return False

        # 关键词匹配（任一命中即可）
        if "keywords" in cond and cond["keywords"]:
            content = review.content or ""
            if not any(kw in content for kw in cond["keywords"]):
                return False

        return True

    async def execute_action(
        self,
        db: AsyncSession,
        rule: ReviewActionRule,
        review: DianpingReview,
    ) -> Dict[str, Any]:
        """
        按 action_type 分发执行行动，记录日志并更新触发计数。
        """
        action_result: Dict[str, Any] = {
            "rule_name": rule.rule_name,
            "action_type": rule.action_type,
            "status": "pending",
            "detail": {},
        }

        try:
            if rule.action_type == "auto_reply":
                detail = await self._action_auto_reply(db, rule, review)
            elif rule.action_type == "alert_manager":
                detail = await self._action_alert_manager(db, rule, review)
            elif rule.action_type == "create_task":
                detail = await self._action_create_task(db, rule, review)
            elif rule.action_type == "signal_bus":
                detail = await self._action_signal_bus(db, rule, review)
            elif rule.action_type == "wechat_notify":
                detail = await self._action_wechat_notify(rule, review)
            else:
                detail = {"message": f"未知行动类型: {rule.action_type}"}
                action_result["status"] = "failed"
                action_result["detail"] = detail
                await self._log_action(db, rule, review, "failed", detail, f"未知行动类型: {rule.action_type}")
                return action_result

            action_result["status"] = "success"
            action_result["detail"] = detail
            await self._log_action(db, rule, review, "success", detail)

            # 更新规则触发计数
            await db.execute(
                update(ReviewActionRule)
                .where(ReviewActionRule.id == rule.id)
                .values(trigger_count=ReviewActionRule.trigger_count + 1)
            )
            await db.commit()

        except Exception as exc:
            logger.error(
                "review_action.execute_failed",
                rule_id=str(rule.id),
                review_id=str(review.id),
                error=str(exc),
            )
            action_result["status"] = "failed"
            action_result["detail"] = {"error": str(exc)}
            await self._log_action(db, rule, review, "failed", {}, str(exc))
            await db.rollback()

        return action_result

    # ── 行动实现 ──────────────────────────────────────────────────────

    async def _action_auto_reply(
        self,
        db: AsyncSession,
        rule: ReviewActionRule,
        review: DianpingReview,
    ) -> Dict[str, Any]:
        """自动回复：用模板生成回复内容，写入评论记录"""
        config = rule.action_config or {}
        template = config.get("reply_template", "感谢您的反馈，我们会认真改进！")

        # 模板变量替换
        reply_text = template.replace("{author}", review.author_name or "顾客")
        reply_text = reply_text.replace("{store_id}", review.store_id or "")

        await db.execute(
            update(DianpingReview)
            .where(DianpingReview.id == review.id)
            .values(
                reply_content=reply_text,
                reply_date=datetime.datetime.utcnow(),
            )
        )
        await db.commit()

        logger.info("review_action.auto_reply", review_id=str(review.id))
        return {"reply_content": reply_text, "review_id": str(review.id)}

    async def _action_alert_manager(
        self,
        db: AsyncSession,
        rule: ReviewActionRule,
        review: DianpingReview,
    ) -> Dict[str, Any]:
        """通知管理者：创建高优先级通知"""
        config = rule.action_config or {}
        alert_level = config.get("alert_level", "high")

        from src.models.notification import Notification

        notification = Notification(
            title=f"差评预警: {review.author_name} {review.rating}星",
            message=f"评论内容: {(review.content or '')[:200]}",
            type="alert",
            priority=alert_level,
            store_id=review.store_id,
            source="review_action_engine",
            extra_data={
                "review_id": str(review.id),
                "rating": review.rating,
                "sentiment": review.sentiment,
                "rule_name": rule.rule_name,
            },
        )
        db.add(notification)
        await db.commit()

        logger.info("review_action.alert_manager", review_id=str(review.id))
        return {
            "notification_id": str(notification.id),
            "alert_level": alert_level,
        }

    async def _action_create_task(
        self,
        db: AsyncSession,
        rule: ReviewActionRule,
        review: DianpingReview,
    ) -> Dict[str, Any]:
        """创建任务：为门店管理者创建处理任务"""
        config = rule.action_config or {}
        assignee_role = config.get("task_assignee", "store_manager")

        from src.models.task import Task

        task = Task(
            title=f"处理差评: {review.author_name} {review.rating}星评论",
            content=(f"评论内容：{(review.content or '')[:300]}\n" f"来源：{review.source}\n" f"规则：{rule.rule_name}"),
            category="review_handling",
            store_id=review.store_id,
            creator_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),  # 系统创建
            priority="high",
            status="pending",
        )
        db.add(task)
        await db.commit()

        logger.info("review_action.create_task", review_id=str(review.id))
        return {
            "task_id": str(task.id),
            "assignee_role": assignee_role,
        }

    async def _action_signal_bus(
        self,
        db: AsyncSession,
        rule: ReviewActionRule,
        review: DianpingReview,
    ) -> Dict[str, Any]:
        """信号总线：发送差评信号到 Signal Bus 触发私域修复旅程"""
        from src.services.signal_bus import _write_signal, route_bad_review

        signal_id = await _write_signal(
            store_id=review.store_id,
            signal_type="bad_review",
            description=f"rating:{review.rating} {(review.content or '')[:100]}",
            severity="high" if review.rating <= 2 else "medium",
            db=db,
        )

        result = await route_bad_review(
            store_id=review.store_id,
            signal_id=signal_id,
            customer_id=None,
            rating=review.rating,
            content=review.content or "",
            db=db,
        )

        logger.info("review_action.signal_bus", review_id=str(review.id), signal_id=signal_id)
        return {
            "signal_id": signal_id,
            "routed": result.get("routed", False),
            "journey_id": result.get("journey_id"),
        }

    async def _action_wechat_notify(
        self,
        rule: ReviewActionRule,
        review: DianpingReview,
    ) -> Dict[str, Any]:
        """企业微信通知（mock）：发送差评提醒到企微群"""
        config = rule.action_config or {}
        webhook_url = config.get("webhook_url", "")

        message_body = (
            f"【评论行动引擎】差评提醒\n"
            f"门店: {review.store_id}\n"
            f"评分: {review.rating}星\n"
            f"作者: {review.author_name}\n"
            f"内容: {(review.content or '')[:150]}\n"
            f"规则: {rule.rule_name}"
        )

        # 生产环境接入企微 Webhook，当前 mock 记录
        logger.info(
            "review_action.wechat_notify",
            review_id=str(review.id),
            webhook_url=webhook_url,
            message_length=len(message_body),
        )
        return {
            "message": message_body,
            "webhook_url": webhook_url,
            "sent": False,  # mock
        }

    # ── 日志记录 ──────────────────────────────────────────────────────

    async def _log_action(
        self,
        db: AsyncSession,
        rule: ReviewActionRule,
        review: DianpingReview,
        status: str,
        detail: Dict[str, Any],
        error_message: Optional[str] = None,
    ) -> None:
        """写入行动执行日志"""
        try:
            log = ReviewActionLog(
                rule_id=rule.id,
                review_id=review.id,
                brand_id=review.brand_id,
                store_id=review.store_id,
                action_type=rule.action_type,
                action_detail=detail,
                status=status,
                error_message=error_message,
                executed_at=datetime.datetime.utcnow(),
            )
            db.add(log)
            await db.commit()
        except Exception as exc:
            logger.warning("review_action.log_failed", error=str(exc))
            await db.rollback()

    # ── CRUD 操作 ─────────────────────────────────────────────────────

    async def create_rule(
        self,
        db: AsyncSession,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """创建规则"""
        rule = ReviewActionRule(
            brand_id=data["brand_id"],
            rule_name=data["rule_name"],
            trigger_condition=data.get("trigger_condition", {}),
            action_type=data["action_type"],
            action_config=data.get("action_config", {}),
            is_enabled=data.get("is_enabled", True),
            priority=data.get("priority", 0),
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        logger.info("review_action.rule_created", rule_id=str(rule.id))
        return rule.to_dict()

    async def list_rules(
        self,
        db: AsyncSession,
        brand_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """分页查询规则列表"""
        base_filter = ReviewActionRule.brand_id == brand_id

        total_result = await db.execute(select(func.count(ReviewActionRule.id)).where(base_filter))
        total = total_result.scalar() or 0

        result = await db.execute(
            select(ReviewActionRule)
            .where(base_filter)
            .order_by(desc(ReviewActionRule.priority), desc(ReviewActionRule.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rules = result.scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "rules": [r.to_dict() for r in rules],
        }

    async def update_rule(
        self,
        db: AsyncSession,
        rule_id: str,
        data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """更新规则"""
        result = await db.execute(select(ReviewActionRule).where(ReviewActionRule.id == uuid.UUID(rule_id)))
        rule = result.scalar_one_or_none()
        if not rule:
            return None

        updatable = [
            "rule_name",
            "trigger_condition",
            "action_type",
            "action_config",
            "is_enabled",
            "priority",
        ]
        for field in updatable:
            if field in data:
                setattr(rule, field, data[field])

        await db.commit()
        await db.refresh(rule)
        logger.info("review_action.rule_updated", rule_id=rule_id)
        return rule.to_dict()

    async def delete_rule(
        self,
        db: AsyncSession,
        rule_id: str,
    ) -> bool:
        """删除规则"""
        result = await db.execute(delete(ReviewActionRule).where(ReviewActionRule.id == uuid.UUID(rule_id)))
        await db.commit()
        deleted = result.rowcount > 0
        if deleted:
            logger.info("review_action.rule_deleted", rule_id=rule_id)
        return deleted

    # ── 日志查询 ──────────────────────────────────────────────────────

    async def get_action_logs(
        self,
        db: AsyncSession,
        brand_id: str,
        page: int = 1,
        page_size: int = 20,
        action_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分页查询行动执行日志"""
        filters = [ReviewActionLog.brand_id == brand_id]
        if action_type:
            filters.append(ReviewActionLog.action_type == action_type)

        total_result = await db.execute(select(func.count(ReviewActionLog.id)).where(and_(*filters)))
        total = total_result.scalar() or 0

        result = await db.execute(
            select(ReviewActionLog)
            .where(and_(*filters))
            .order_by(desc(ReviewActionLog.executed_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        logs = result.scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "logs": [log.to_dict() for log in logs],
        }

    # ── 统计 ──────────────────────────────────────────────────────────

    async def get_stats(
        self,
        db: AsyncSession,
        brand_id: str,
    ) -> Dict[str, Any]:
        """获取行动引擎统计数据"""
        # 规则总数 & 启用数
        total_rules_result = await db.execute(
            select(func.count(ReviewActionRule.id)).where(ReviewActionRule.brand_id == brand_id)
        )
        total_rules = total_rules_result.scalar() or 0

        active_rules_result = await db.execute(
            select(func.count(ReviewActionRule.id)).where(
                and_(
                    ReviewActionRule.brand_id == brand_id,
                    ReviewActionRule.is_enabled.is_(True),
                )
            )
        )
        active_rules = active_rules_result.scalar() or 0

        # 今日触发数
        today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        triggered_today_result = await db.execute(
            select(func.count(ReviewActionLog.id)).where(
                and_(
                    ReviewActionLog.brand_id == brand_id,
                    ReviewActionLog.executed_at >= today_start,
                )
            )
        )
        triggered_today = triggered_today_result.scalar() or 0

        # 成功率
        success_count_result = await db.execute(
            select(func.count(ReviewActionLog.id)).where(
                and_(
                    ReviewActionLog.brand_id == brand_id,
                    ReviewActionLog.status == "success",
                )
            )
        )
        success_count = success_count_result.scalar() or 0

        total_logs_result = await db.execute(
            select(func.count(ReviewActionLog.id)).where(ReviewActionLog.brand_id == brand_id)
        )
        total_logs = total_logs_result.scalar() or 0

        success_rate = round((success_count / total_logs * 100), 1) if total_logs > 0 else 0.0

        # 触发次数最多的规则 Top 5
        top_rules_result = await db.execute(
            select(ReviewActionRule.rule_name, ReviewActionRule.trigger_count)
            .where(ReviewActionRule.brand_id == brand_id)
            .order_by(desc(ReviewActionRule.trigger_count))
            .limit(5)
        )
        top_rules = [{"rule_name": row[0], "trigger_count": row[1]} for row in top_rules_result.fetchall()]

        return {
            "total_rules": total_rules,
            "active_rules": active_rules,
            "triggered_today": triggered_today,
            "success_rate": success_rate,
            "total_logs": total_logs,
            "top_triggered_rules": top_rules,
        }

    # ── 批量处理 ──────────────────────────────────────────────────────

    async def batch_process_unread(
        self,
        db: AsyncSession,
        brand_id: str,
    ) -> Dict[str, Any]:
        """批量处理该品牌下所有未读评论"""
        result = await db.execute(
            select(DianpingReview)
            .where(
                and_(
                    DianpingReview.brand_id == brand_id,
                    DianpingReview.is_read.is_(False),
                )
            )
            .order_by(desc(DianpingReview.review_date))
            .limit(100)
        )
        reviews = result.scalars().all()

        processed = 0
        actions_taken = 0
        errors = 0

        for review in reviews:
            try:
                results = await self.process_review(db, review)
                actions_taken += len(results)
                processed += 1

                # 标记已读
                await db.execute(update(DianpingReview).where(DianpingReview.id == review.id).values(is_read=True))
                await db.commit()
            except Exception as exc:
                errors += 1
                logger.warning(
                    "review_action.batch_process_error",
                    review_id=str(review.id),
                    error=str(exc),
                )
                await db.rollback()

        logger.info(
            "review_action.batch_process_done",
            brand_id=brand_id,
            processed=processed,
            actions_taken=actions_taken,
            errors=errors,
        )
        return {
            "processed": processed,
            "actions_taken": actions_taken,
            "errors": errors,
            "total_unread": len(reviews),
        }


# 单例
review_action_service = ReviewActionService()
