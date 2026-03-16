"""
审批流服务
实现Human-in-the-loop决策流程
支持企微卡片式交互和决策数据记录
"""

import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.clock import now_utc, utcnow_naive
from ..models.decision_log import DecisionLog, DecisionOutcome, DecisionStatus, DecisionType
from ..models.store import Store
from ..models.user import User
from .wechat_alert_service import WeChatAlertService

logger = structlog.get_logger()


class ApprovalService:
    """审批流服务"""

    def __init__(self):
        self.wechat_service = WeChatAlertService()

    async def create_approval_request(
        self,
        decision_type: DecisionType,
        agent_type: str,
        agent_method: str,
        store_id: str,
        ai_suggestion: Dict[str, Any],
        ai_confidence: float,
        ai_reasoning: str,
        ai_alternatives: Optional[List[Dict[str, Any]]] = None,
        context_data: Optional[Dict[str, Any]] = None,
        rag_context: Optional[Dict[str, Any]] = None,
        db: AsyncSession = None,
    ) -> DecisionLog:
        """
        创建审批请求

        Args:
            decision_type: 决策类型
            agent_type: Agent类型
            agent_method: Agent方法名
            store_id: 门店ID
            ai_suggestion: AI建议内容
            ai_confidence: AI置信度
            ai_reasoning: AI推理过程
            ai_alternatives: AI备选方案
            context_data: 决策上下文数据
            rag_context: RAG检索上下文
            db: 数据库会话

        Returns:
            DecisionLog: 决策日志对象
        """
        try:
            # 创建决策日志
            decision_log = DecisionLog(
                id=str(uuid.uuid4()),
                decision_type=decision_type,
                agent_type=agent_type,
                agent_method=agent_method,
                store_id=store_id,
                ai_suggestion=ai_suggestion,
                ai_confidence=ai_confidence,
                ai_reasoning=ai_reasoning,
                ai_alternatives=ai_alternatives or [],
                decision_status=DecisionStatus.PENDING,
                context_data=context_data,
                rag_context=rag_context,
                created_at=utcnow_naive(),
            )

            # 保存到数据库
            if db:
                db.add(decision_log)
                await db.commit()
                await db.refresh(decision_log)

            logger.info(
                "approval_request_created",
                decision_id=decision_log.id,
                decision_type=decision_type.value,
                agent_type=agent_type,
                store_id=store_id,
            )

            # 发送企微审批通知
            await self._send_approval_notification(decision_log, db)

            return decision_log

        except Exception as e:
            logger.error("create_approval_request_failed", error=str(e))
            if db:
                await db.rollback()
            raise

    async def _send_approval_notification(self, decision_log: DecisionLog, db: AsyncSession):
        """发送企微审批通知"""
        try:
            # 获取门店信息
            result = await db.execute(select(Store).where(Store.id == decision_log.store_id))
            store = result.scalar_one_or_none()
            if not store:
                logger.warning("store_not_found", store_id=decision_log.store_id)
                return

            # 获取店长信息
            result = await db.execute(
                select(User).where(
                    User.store_id == decision_log.store_id, User.role.in_(["store_manager", "assistant_manager"])
                )
            )
            managers = result.scalars().all()

            if not managers:
                logger.warning("no_managers_found", store_id=decision_log.store_id)
                return

            # 构建审批卡片消息
            message = self._build_approval_card(decision_log, store)

            # 发送给所有店长
            for manager in managers:
                await self.wechat_service.send_approval_card(
                    user_id=manager.wechat_user_id, message=message, decision_id=decision_log.id
                )

            logger.info("approval_notification_sent", decision_id=decision_log.id, recipients=len(managers))

        except Exception as e:
            logger.error("send_approval_notification_failed", error=str(e))

    def _build_approval_card(self, decision_log: DecisionLog, store: Store) -> Dict[str, Any]:
        """构建审批卡片消息"""
        # 决策类型中文映射
        type_names = {
            DecisionType.REVENUE_ANOMALY: "营收异常处理",
            DecisionType.INVENTORY_ALERT: "库存预警处理",
            DecisionType.PURCHASE_SUGGESTION: "采购建议",
            DecisionType.SCHEDULE_OPTIMIZATION: "排班优化",
            DecisionType.MENU_PRICING: "菜品定价调整",
            DecisionType.ORDER_ANOMALY: "订单异常处理",
            DecisionType.KPI_IMPROVEMENT: "KPI改进计划",
            DecisionType.COST_OPTIMIZATION: "成本优化",
        }

        type_name = type_names.get(decision_log.decision_type, "AI决策建议")

        # 构建卡片内容
        card = {
            "title": f"🤖 {type_name}",
            "store": store.name,
            "decision_id": decision_log.id,
            "confidence": f"{decision_log.ai_confidence * 100:.1f}%",
            "suggestion": decision_log.ai_suggestion,
            "reasoning": decision_log.ai_reasoning,
            "alternatives": decision_log.ai_alternatives,
            "created_at": decision_log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "actions": [
                {"label": "✅ 批准", "action": "approve"},
                {"label": "❌ 拒绝", "action": "reject"},
                {"label": "✏️ 修改", "action": "modify"},
            ],
        }

        return card

    async def approve_decision(
        self, decision_id: str, manager_id: str, manager_feedback: Optional[str] = None, db: AsyncSession = None
    ) -> DecisionLog:
        """
        批准决策

        Args:
            decision_id: 决策ID
            manager_id: 店长ID
            manager_feedback: 店长反馈
            db: 数据库会话

        Returns:
            DecisionLog: 更新后的决策日志
        """
        try:
            result = await db.execute(select(DecisionLog).where(DecisionLog.id == decision_id))
            decision_log = result.scalar_one_or_none()
            if not decision_log:
                raise ValueError(f"Decision log not found: {decision_id}")

            # 更新决策状态
            decision_log.decision_status = DecisionStatus.APPROVED
            decision_log.manager_id = manager_id
            decision_log.manager_decision = decision_log.ai_suggestion  # 采纳AI建议
            decision_log.manager_feedback = manager_feedback
            decision_log.approved_at = utcnow_naive()

            # 更新审批链
            approval_chain = decision_log.approval_chain or []
            approval_chain.append(
                {
                    "action": "approved",
                    "manager_id": manager_id,
                    "timestamp": now_utc().isoformat(),
                    "feedback": manager_feedback,
                }
            )
            decision_log.approval_chain = approval_chain

            await db.commit()
            await db.refresh(decision_log)

            logger.info("decision_approved", decision_id=decision_id, manager_id=manager_id)

            # 执行决策
            await self._execute_decision(decision_log, db)

            return decision_log

        except Exception as e:
            logger.error("approve_decision_failed", error=str(e))
            if db:
                await db.rollback()
            raise

    async def reject_decision(
        self, decision_id: str, manager_id: str, manager_feedback: str, db: AsyncSession = None
    ) -> DecisionLog:
        """
        拒绝决策

        Args:
            decision_id: 决策ID
            manager_id: 店长ID
            manager_feedback: 拒绝原因
            db: 数据库会话

        Returns:
            DecisionLog: 更新后的决策日志
        """
        try:
            result = await db.execute(select(DecisionLog).where(DecisionLog.id == decision_id))
            decision_log = result.scalar_one_or_none()
            if not decision_log:
                raise ValueError(f"Decision log not found: {decision_id}")

            # 更新决策状态
            decision_log.decision_status = DecisionStatus.REJECTED
            decision_log.manager_id = manager_id
            decision_log.manager_feedback = manager_feedback
            decision_log.approved_at = utcnow_naive()

            # 更新审批链
            approval_chain = decision_log.approval_chain or []
            approval_chain.append(
                {
                    "action": "rejected",
                    "manager_id": manager_id,
                    "timestamp": now_utc().isoformat(),
                    "feedback": manager_feedback,
                }
            )
            decision_log.approval_chain = approval_chain

            # 标记为训练数据（拒绝的决策对学习很有价值）
            decision_log.is_training_data = 1

            await db.commit()
            await db.refresh(decision_log)

            logger.info("decision_rejected", decision_id=decision_id, manager_id=manager_id, reason=manager_feedback)

            return decision_log

        except Exception as e:
            logger.error("reject_decision_failed", error=str(e))
            if db:
                await db.rollback()
            raise

    async def modify_decision(
        self,
        decision_id: str,
        manager_id: str,
        modified_decision: Dict[str, Any],
        manager_feedback: Optional[str] = None,
        db: AsyncSession = None,
    ) -> DecisionLog:
        """
        修改决策

        Args:
            decision_id: 决策ID
            manager_id: 店长ID
            modified_decision: 修改后的决策
            manager_feedback: 修改说明
            db: 数据库会话

        Returns:
            DecisionLog: 更新后的决策日志
        """
        try:
            result = await db.execute(select(DecisionLog).where(DecisionLog.id == decision_id))
            decision_log = result.scalar_one_or_none()
            if not decision_log:
                raise ValueError(f"Decision log not found: {decision_id}")

            # 更新决策状态
            decision_log.decision_status = DecisionStatus.MODIFIED
            decision_log.manager_id = manager_id
            decision_log.manager_decision = modified_decision
            decision_log.manager_feedback = manager_feedback
            decision_log.approved_at = utcnow_naive()

            # 更新审批链
            approval_chain = decision_log.approval_chain or []
            approval_chain.append(
                {
                    "action": "modified",
                    "manager_id": manager_id,
                    "timestamp": now_utc().isoformat(),
                    "original": decision_log.ai_suggestion,
                    "modified": modified_decision,
                    "feedback": manager_feedback,
                }
            )
            decision_log.approval_chain = approval_chain

            # 标记为训练数据（修改的决策对学习很有价值）
            decision_log.is_training_data = 1

            await db.commit()
            await db.refresh(decision_log)

            logger.info("decision_modified", decision_id=decision_id, manager_id=manager_id)

            # 执行修改后的决策
            await self._execute_decision(decision_log, db)

            return decision_log

        except Exception as e:
            logger.error("modify_decision_failed", error=str(e))
            if db:
                await db.rollback()
            raise

    async def _execute_decision(self, decision_log: DecisionLog, db: AsyncSession):
        """执行决策"""
        try:
            # 根据决策类型执行相应操作
            suggestion = decision_log.ai_suggestion or {}

            if decision_log.decision_type == DecisionType.PURCHASE_SUGGESTION:
                # 采购建议：创建采购通知
                from ..models.notification import Notification, NotificationPriority, NotificationType

                notif = Notification(
                    title="AI采购建议已批准",
                    message=f"采购建议已批准执行：{decision_log.ai_reasoning or ''}",
                    type=NotificationType.INFO,
                    priority=NotificationPriority.HIGH,
                    store_id=decision_log.store_id,
                    extra_data=suggestion,
                )
                db.add(notif)

            elif decision_log.decision_type == DecisionType.INVENTORY_ALERT:
                # 库存预警：记录处理通知
                from ..models.notification import Notification, NotificationPriority, NotificationType

                notif = Notification(
                    title="库存预警已处理",
                    message=f"库存预警决策已执行：{decision_log.ai_reasoning or ''}",
                    type=NotificationType.WARNING,
                    priority=NotificationPriority.HIGH,
                    store_id=decision_log.store_id,
                )
                db.add(notif)

            elif decision_log.decision_type == DecisionType.SCHEDULE_OPTIMIZATION:
                # 排班优化：记录排班通知
                from ..models.notification import Notification, NotificationPriority, NotificationType

                notif = Notification(
                    title="排班优化已执行",
                    message=f"AI排班优化方案已批准：{decision_log.ai_reasoning or ''}",
                    type=NotificationType.INFO,
                    priority=NotificationPriority.NORMAL,
                    store_id=decision_log.store_id,
                )
                db.add(notif)

            decision_log.decision_status = DecisionStatus.EXECUTED
            decision_log.executed_at = utcnow_naive()
            await db.commit()

            logger.info("decision_executed", decision_id=decision_log.id, decision_type=decision_log.decision_type.value)

        except Exception as e:
            logger.error("execute_decision_failed", error=str(e))
            raise

    async def record_decision_outcome(
        self,
        decision_id: str,
        outcome: DecisionOutcome,
        actual_result: Dict[str, Any],
        expected_result: Dict[str, Any],
        business_impact: Optional[Dict[str, Any]] = None,
        db: AsyncSession = None,
    ) -> DecisionLog:
        """
        记录决策结果

        Args:
            decision_id: 决策ID
            outcome: 决策结果
            actual_result: 实际结果
            expected_result: 预期结果
            business_impact: 业务影响
            db: 数据库会话

        Returns:
            DecisionLog: 更新后的决策日志
        """
        try:
            result = await db.execute(select(DecisionLog).where(DecisionLog.id == decision_id))
            decision_log = result.scalar_one_or_none()
            if not decision_log:
                raise ValueError(f"Decision log not found: {decision_id}")

            # 更新结果
            decision_log.outcome = outcome
            decision_log.actual_result = actual_result
            decision_log.expected_result = expected_result
            decision_log.business_impact = business_impact

            # 计算结果偏差
            if "value" in actual_result and "value" in expected_result:
                expected = expected_result["value"]
                actual = actual_result["value"]
                if expected != 0:
                    deviation = abs((actual - expected) / expected) * 100
                    decision_log.result_deviation = deviation

            # 计算信任度评分
            trust_score = self._calculate_trust_score(decision_log)
            decision_log.trust_score = trust_score

            # 标记为训练数据
            decision_log.is_training_data = 1

            await db.commit()
            await db.refresh(decision_log)

            logger.info("decision_outcome_recorded", decision_id=decision_id, outcome=outcome.value, trust_score=trust_score)

            return decision_log

        except Exception as e:
            logger.error("record_decision_outcome_failed", error=str(e))
            if db:
                await db.rollback()
            raise

    def _calculate_trust_score(self, decision_log: DecisionLog) -> float:
        """
        计算信任度评分

        评分维度:
        - AI置信度 (30%)
        - 决策采纳情况 (40%)
        - 结果偏差 (30%)
        """
        score = 0.0

        # AI置信度得分
        if decision_log.ai_confidence:
            score += decision_log.ai_confidence * float(os.getenv("APPROVAL_AI_CONFIDENCE_WEIGHT", "30"))

        # 决策采纳情况得分
        if decision_log.decision_status == DecisionStatus.APPROVED:
            score += float(os.getenv("APPROVAL_SCORE_ADOPTED", "40"))  # 完全采纳
        elif decision_log.decision_status == DecisionStatus.MODIFIED:
            score += float(os.getenv("APPROVAL_SCORE_MODIFIED", "20"))  # 部分采纳
        elif decision_log.decision_status == DecisionStatus.REJECTED:
            score += 0  # 未采纳

        # 结果偏差得分
        if decision_log.result_deviation is not None:
            if decision_log.result_deviation < float(os.getenv("APPROVAL_DEVIATION_LOW", "10")):
                score += float(os.getenv("APPROVAL_SCORE_DEV_LOW", "30"))  # 偏差<10%
            elif decision_log.result_deviation < float(os.getenv("APPROVAL_DEVIATION_MID", "20")):
                score += float(os.getenv("APPROVAL_SCORE_DEV_MID", "20"))  # 偏差<20%
            elif decision_log.result_deviation < float(os.getenv("APPROVAL_DEVIATION_HIGH", "30")):
                score += float(os.getenv("APPROVAL_SCORE_DEV_HIGH", "10"))  # 偏差<30%
            else:
                score += 0  # 偏差≥30%

        return min(score, 100.0)

    async def get_pending_approvals(
        self, store_id: Optional[str] = None, manager_id: Optional[str] = None, db: AsyncSession = None
    ) -> List[DecisionLog]:
        """
        获取待审批决策列表

        Args:
            store_id: 门店ID（可选）
            manager_id: 店长ID（可选）
            db: 数据库会话

        Returns:
            List[DecisionLog]: 待审批决策列表
        """
        try:
            stmt = select(DecisionLog).where(DecisionLog.decision_status == DecisionStatus.PENDING)

            if store_id:
                stmt = stmt.where(DecisionLog.store_id == store_id)

            if manager_id:
                # 获取店长管理的门店
                stores_result = await db.execute(select(Store.id).where(Store.manager_id == manager_id))
                store_ids = [row[0] for row in stores_result.all()]
                stmt = stmt.where(DecisionLog.store_id.in_(store_ids))

            stmt = stmt.order_by(DecisionLog.created_at.desc())
            result = await db.execute(stmt)
            return result.scalars().all()

        except Exception as e:
            logger.error("get_pending_approvals_failed", error=str(e))
            raise

    async def get_decision_statistics(
        self,
        store_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        db: AsyncSession = None,
    ) -> Dict[str, Any]:
        """
        获取决策统计数据

        Args:
            store_id: 门店ID（可选）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            db: 数据库会话

        Returns:
            Dict: 统计数据
        """
        try:
            stmt = select(DecisionLog)

            if store_id:
                stmt = stmt.where(DecisionLog.store_id == store_id)
            if start_date:
                stmt = stmt.where(DecisionLog.created_at >= start_date)
            if end_date:
                stmt = stmt.where(DecisionLog.created_at <= end_date)

            result = await db.execute(stmt)
            decisions = result.scalars().all()

            # 统计数据
            total = len(decisions)
            approved = len([d for d in decisions if d.decision_status == DecisionStatus.APPROVED])
            rejected = len([d for d in decisions if d.decision_status == DecisionStatus.REJECTED])
            modified = len([d for d in decisions if d.decision_status == DecisionStatus.MODIFIED])
            pending = len([d for d in decisions if d.decision_status == DecisionStatus.PENDING])

            # 平均信任度
            trust_scores = [d.trust_score for d in decisions if d.trust_score is not None]
            avg_trust_score = sum(trust_scores) / len(trust_scores) if trust_scores else 0

            # 按决策类型统计
            type_stats = {}
            for decision in decisions:
                type_name = decision.decision_type.value
                if type_name not in type_stats:
                    type_stats[type_name] = 0
                type_stats[type_name] += 1

            return {
                "total": total,
                "approved": approved,
                "rejected": rejected,
                "modified": modified,
                "pending": pending,
                "approval_rate": (approved / total * 100) if total > 0 else 0,
                "modification_rate": (modified / total * 100) if total > 0 else 0,
                "rejection_rate": (rejected / total * 100) if total > 0 else 0,
                "avg_trust_score": avg_trust_score,
                "by_type": type_stats,
            }

        except Exception as e:
            logger.error("get_decision_statistics_failed", error=str(e))
            raise


# 全局实例
approval_service = ApprovalService()
