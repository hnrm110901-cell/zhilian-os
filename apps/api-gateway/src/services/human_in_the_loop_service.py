"""
Human-in-the-Loop服务 (增强版)
"机器不可信"安全防线 - 高危操作分级审批

核心原则: 建立信任需要三年，摧毁信任只需大模型发疯一次

架构:
- Level 1: 自动执行（低风险）
- Level 2: 自动执行+事后审计（中风险）
- Level 3: 人工审批（高风险）
- Level 4: 禁止AI操作（极高风险）
"""
from datetime import datetime, date
from typing import Dict, List, Optional
from enum import Enum
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select
import structlog
import os

logger = structlog.get_logger()


class RiskLevel(str, Enum):
    """风险等级"""
    LOW = "low"  # Level 1: 自动执行
    MEDIUM = "medium"  # Level 2: 自动执行+事后审计
    HIGH = "high"  # Level 3: 人工审批
    CRITICAL = "critical"  # Level 4: 禁止AI操作


class OperationType(str, Enum):
    """操作类型"""
    # Level 1: 低风险操作
    QUERY = "query"  # 查询操作
    ANALYSIS = "analysis"  # 数据分析
    REPORT = "report"  # 报表生成
    NOTIFICATION = "notification"  # 提醒通知

    # Level 2: 中风险操作
    AUTO_SCHEDULING = "auto_scheduling"  # 自动排班
    AUTO_PURCHASE = "auto_purchase"  # 自动采购（小额）
    COUPON_DISTRIBUTION = "coupon_distribution"  # 优惠券发放

    # Level 3: 高风险操作
    LARGE_PURCHASE = "large_purchase"  # 大额采购
    STAFF_TRANSFER = "staff_transfer"  # 人员调动
    PRICE_ADJUSTMENT = "price_adjustment"  # 价格调整
    SUPPLIER_CHANGE = "supplier_change"  # 供应商变更

    # Level 4: 极高风险操作
    FUND_TRANSFER = "fund_transfer"  # 资金打款
    DATA_DELETION = "data_deletion"  # 数据删除
    PERMISSION_CHANGE = "permission_change"  # 权限变更
    CONTRACT_SIGNING = "contract_signing"  # 合同签署


class TrustPhase(str, Enum):
    """信任阶段"""
    OBSERVATION = "observation"  # 观察期（1-3个月）
    ASSISTANCE = "assistance"  # 辅助期（3-6个月）
    AUTONOMOUS = "autonomous"  # 自主期（6个月+）


class ApprovalStatus(str, Enum):
    """审批状态"""
    PENDING = "pending"  # 待审批
    APPROVED = "approved"  # 已批准
    REJECTED = "rejected"  # 已拒绝
    AUTO_APPROVED = "auto_approved"  # 自动批准
    EXPIRED = "expired"  # 已过期


class AIDecision(BaseModel):
    """AI决策"""
    decision_id: str
    store_id: str
    operation_type: OperationType
    risk_level: RiskLevel
    description: str
    reasoning: str  # AI的推理过程
    expected_impact: Dict  # 预期影响
    confidence_score: float  # 置信度（0-1）
    created_at: datetime


class ApprovalRequest(BaseModel):
    """审批请求"""
    request_id: str
    decision_id: str
    store_id: str
    operation_type: OperationType
    risk_level: RiskLevel
    description: str
    reasoning: str
    expected_impact: Dict
    approver_id: Optional[str] = None
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    approval_comment: Optional[str] = None
    created_at: datetime
    approved_at: Optional[datetime] = None
    expires_at: datetime


class HumanInTheLoopService:
    """Human-in-the-Loop服务"""

    # 风险等级阈值（支持环境变量覆盖）
    RISK_THRESHOLDS = {
        # 采购金额阈值
        "purchase_amount_threshold": float(os.getenv("HITL_PURCHASE_THRESHOLD", "5000.0")),

        # 价格调整阈值
        "price_change_threshold": float(os.getenv("HITL_PRICE_CHANGE_THRESHOLD", "0.10")),

        # 优惠券额度阈值
        "coupon_amount_threshold": float(os.getenv("HITL_COUPON_THRESHOLD", "1000.0")),
    }

    # 审批超时时间（小时，支持环境变量覆盖）
    APPROVAL_TIMEOUT_HOURS = {
        RiskLevel.HIGH: int(os.getenv("HITL_HIGH_RISK_TIMEOUT_HOURS", "24")),
        RiskLevel.CRITICAL: int(os.getenv("HITL_CRITICAL_RISK_TIMEOUT_HOURS", "2")),
    }

    def __init__(self, db: Session):
        self.db = db

    def classify_risk_level(
        self,
        operation_type: OperationType,
        operation_params: Dict,
        trust_phase: TrustPhase
    ) -> RiskLevel:
        """
        分类风险等级

        根据操作类型、参数和信任阶段，判断风险等级
        """
        # Level 4: 极高风险操作（永远禁止AI自动执行）
        if operation_type in [
            OperationType.FUND_TRANSFER,
            OperationType.DATA_DELETION,
            OperationType.PERMISSION_CHANGE,
            OperationType.CONTRACT_SIGNING
        ]:
            return RiskLevel.CRITICAL

        # Level 3: 高风险操作
        if operation_type == OperationType.LARGE_PURCHASE:
            amount = operation_params.get("amount", 0)
            if amount > self.RISK_THRESHOLDS["purchase_amount_threshold"]:
                return RiskLevel.HIGH

        if operation_type == OperationType.PRICE_ADJUSTMENT:
            change_rate = operation_params.get("change_rate", 0)
            if abs(change_rate) > self.RISK_THRESHOLDS["price_change_threshold"]:
                return RiskLevel.HIGH

        if operation_type in [
            OperationType.STAFF_TRANSFER,
            OperationType.SUPPLIER_CHANGE
        ]:
            return RiskLevel.HIGH

        # Level 2: 中风险操作
        if operation_type in [
            OperationType.AUTO_SCHEDULING,
            OperationType.AUTO_PURCHASE,
            OperationType.COUPON_DISTRIBUTION
        ]:
            # 在观察期，中风险操作也需要审批
            if trust_phase == TrustPhase.OBSERVATION:
                return RiskLevel.HIGH
            return RiskLevel.MEDIUM

        # Level 1: 低风险操作
        return RiskLevel.LOW

    async def submit_ai_decision(
        self,
        store_id: str,
        operation_type: OperationType,
        description: str,
        reasoning: str,
        expected_impact: Dict,
        confidence_score: float,
        operation_params: Dict
    ) -> Dict:
        """
        提交AI决策

        AI做出决策后，根据风险等级决定是自动执行还是提交人工审批
        """
        logger.info(
            "提交AI决策",
            store_id=store_id,
            operation_type=operation_type,
            confidence_score=confidence_score
        )

        # 获取门店的信任阶段
        trust_phase = await self.get_store_trust_phase(store_id)

        # 分类风险等级
        risk_level = self.classify_risk_level(operation_type, operation_params, trust_phase)

        # 创建AI决策记录
        decision = AIDecision(
            decision_id=f"decision_{store_id}_{int(datetime.now().timestamp())}",
            store_id=store_id,
            operation_type=operation_type,
            risk_level=risk_level,
            description=description,
            reasoning=reasoning,
            expected_impact=expected_impact,
            confidence_score=confidence_score,
            created_at=datetime.now()
        )

        # 根据风险等级决定处理方式
        if risk_level == RiskLevel.CRITICAL:
            # Level 4: 禁止AI操作
            logger.warning("极高风险操作，禁止AI自动执行", decision_id=decision.decision_id)
            return {
                "decision_id": decision.decision_id,
                "action": "blocked",
                "risk_level": risk_level,
                "message": "此操作风险等级过高，禁止AI自动执行，请人工操作"
            }

        elif risk_level == RiskLevel.HIGH:
            # Level 3: 人工审批
            approval_request = await self.create_approval_request(decision)
            logger.info("高风险操作，需要人工审批", request_id=approval_request.request_id)
            return {
                "decision_id": decision.decision_id,
                "action": "approval_required",
                "risk_level": risk_level,
                "approval_request_id": approval_request.request_id,
                "message": "此操作需要人工审批，已推送至企业微信"
            }

        elif risk_level == RiskLevel.MEDIUM:
            # Level 2: 自动执行+事后审计
            logger.info("中风险操作，自动执行并记录审计", decision_id=decision.decision_id)
            await self.log_audit(decision, "auto_executed")
            return {
                "decision_id": decision.decision_id,
                "action": "auto_executed_with_audit",
                "risk_level": risk_level,
                "message": "操作已自动执行，并记录审计日志"
            }

        else:
            # Level 1: 自动执行
            logger.info("低风险操作，自动执行", decision_id=decision.decision_id)
            return {
                "decision_id": decision.decision_id,
                "action": "auto_executed",
                "risk_level": risk_level,
                "message": "操作已自动执行"
            }

    async def create_approval_request(
        self,
        decision: AIDecision
    ) -> ApprovalRequest:
        """
        创建审批请求

        将高风险操作提交给人工审批
        """
        timeout_hours = self.APPROVAL_TIMEOUT_HOURS.get(decision.risk_level, 24)
        expires_at = datetime.now().replace(hour=datetime.now().hour + timeout_hours)

        request = ApprovalRequest(
            request_id=f"approval_{decision.decision_id}",
            decision_id=decision.decision_id,
            store_id=decision.store_id,
            operation_type=decision.operation_type,
            risk_level=decision.risk_level,
            description=decision.description,
            reasoning=decision.reasoning,
            expected_impact=decision.expected_impact,
            created_at=datetime.now(),
            expires_at=expires_at
        )

        # 推送到企业微信
        await self.send_approval_notification(request)

        # 保存到数据库
        from src.core.database import get_db_session
        from src.models.decision_log import DecisionLog, DecisionStatus, DecisionType
        import uuid

        async with get_db_session() as session:
            log = DecisionLog(
                id=decision.decision_id,
                decision_type=DecisionType.PURCHASE_SUGGESTION,
                agent_type="human_in_the_loop",
                agent_method="create_approval_request",
                store_id=decision.store_id,
                ai_suggestion={"operation_type": decision.operation_type, "expected_impact": decision.expected_impact},
                ai_confidence=decision.confidence_score,
                ai_reasoning=decision.reasoning,
                decision_status=DecisionStatus.PENDING,
            )
            session.add(log)
            await session.commit()

        return request

    async def send_approval_notification(
        self,
        request: ApprovalRequest
    ):
        """
        发送审批通知到企业微信
        """
        logger.info("发送审批通知", request_id=request.request_id)

        message = f"""【智链OS - 需要您的审批】

操作类型: {request.operation_type}
风险等级: {request.risk_level}
描述: {request.description}

AI推理: {request.reasoning}

预期影响:
{request.expected_impact}

请在{request.expires_at.strftime('%Y-%m-%d %H:%M')}前完成审批"""

        try:
            from src.services.wechat_work_message_service import WeChatWorkMessageService
            wechat_service = WeChatWorkMessageService()
            target = request.approver_id or "@all"
            await wechat_service.send_text_message(target, message)
            logger.info("审批通知已发送", request_id=request.request_id, target=target)
        except Exception as e:
            logger.error("审批通知发送失败，降级为日志记录", request_id=request.request_id, error=str(e))
            logger.info("审批通知内容", message=message)

    async def approve_request(
        self,
        request_id: str,
        approver_id: str,
        approved: bool,
        comment: Optional[str] = None
    ) -> ApprovalRequest:
        """
        审批请求
        """
        logger.info(
            "审批请求",
            request_id=request_id,
            approver_id=approver_id,
            approved=approved
        )

        from src.core.database import get_db_session
        from src.models.decision_log import DecisionLog, DecisionStatus

        decision_id = request_id.replace("approval_", "")
        now = datetime.now()

        async with get_db_session() as session:
            result = await session.execute(
                select(DecisionLog).where(DecisionLog.id == decision_id)
            )
            log = result.scalar_one_or_none()

            if log:
                log.decision_status = DecisionStatus.APPROVED if approved else DecisionStatus.REJECTED
                log.manager_id = approver_id
                log.approved_at = now
                log.manager_feedback = comment
                await session.commit()

                return ApprovalRequest(
                    request_id=request_id,
                    decision_id=decision_id,
                    store_id=log.store_id,
                    operation_type=OperationType(log.ai_suggestion.get("operation_type", OperationType.LARGE_PURCHASE)),
                    risk_level=RiskLevel.HIGH,
                    description=log.ai_reasoning or "",
                    reasoning=log.ai_reasoning or "",
                    expected_impact=log.ai_suggestion.get("expected_impact", {}),
                    approver_id=approver_id,
                    approval_status=ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED,
                    approval_comment=comment,
                    created_at=log.created_at,
                    approved_at=now,
                    expires_at=now
                )

        # fallback if not found
        return ApprovalRequest(
            request_id=request_id,
            decision_id=decision_id,
            store_id="",
            operation_type=OperationType.LARGE_PURCHASE,
            risk_level=RiskLevel.HIGH,
            description="",
            reasoning="",
            expected_impact={},
            approver_id=approver_id,
            approval_status=ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED,
            approval_comment=comment,
            created_at=now,
            approved_at=now,
            expires_at=now
        )

    async def get_store_trust_phase(
        self,
        store_id: str
    ) -> TrustPhase:
        """
        获取门店的信任阶段

        - 观察期（1-3个月）: AI只提建议，不执行
        - 辅助期（3-6个月）: AI执行低风险操作，高风险需审批
        - 自主期（6个月+）: AI自主执行大部分操作，仅极高风险需审批
        """
        from src.core.database import get_db_session
        from src.models.store import Store

        async with get_db_session() as session:
            result = await session.execute(
                select(Store.created_at).where(Store.id == store_id)
            )
            created_at = result.scalar_one_or_none()

        if created_at:
            days_since_onboarding = (date.today() - created_at.date()).days
        else:
            days_since_onboarding = 0

        if days_since_onboarding < 90:
            return TrustPhase.OBSERVATION
        elif days_since_onboarding < 180:
            return TrustPhase.ASSISTANCE
        else:
            return TrustPhase.AUTONOMOUS

    async def log_audit(
        self,
        decision: AIDecision,
        action: str
    ):
        """
        记录审计日志
        """
        logger.info(
            "记录审计日志",
            decision_id=decision.decision_id,
            action=action
        )

        # 保存到审计日志表
        from src.core.database import get_db_session
        from src.models.audit_log import AuditLog

        async with get_db_session() as session:
            audit = AuditLog(
                action=action,
                resource_type="ai_decision",
                resource_id=decision.decision_id,
                user_id="system",
                description=decision.description,
                store_id=decision.store_id,
                changes={
                    "decision_id": decision.decision_id,
                    "operation_type": decision.operation_type,
                    "risk_level": decision.risk_level,
                    "confidence_score": decision.confidence_score,
                },
            )
            session.add(audit)
            await session.commit()

    async def get_pending_approvals(
        self,
        store_id: str
    ) -> List[ApprovalRequest]:
        """
        获取待审批的请求
        """
        logger.info("获取待审批请求", store_id=store_id)

        from src.core.database import get_db_session
        from src.models.decision_log import DecisionLog, DecisionStatus
        from sqlalchemy import select

        async with get_db_session() as session:
            result = await session.execute(
                select(DecisionLog).where(
                    DecisionLog.store_id == store_id,
                    DecisionLog.decision_status == DecisionStatus.PENDING,
                ).order_by(DecisionLog.created_at.desc()).limit(20)
            )
            logs = result.scalars().all()

        requests = []
        for log in logs:
            request = ApprovalRequest(
                request_id=log.id,
                decision_id=log.id,
                risk_level=RiskLevel.HIGH,
                action_type=log.decision_type.value if log.decision_type else "unknown",
                action_description=str(log.ai_suggestion) if log.ai_suggestion else "",
                expected_impact={},
                approval_comment=None,
                created_at=log.created_at,
                approved_at=None,
                expires_at=log.created_at + timedelta(hours=24) if log.created_at else datetime.now(),
            )
            requests.append(request)

        return requests

    async def get_approval_statistics(
        self,
        store_id: str
    ) -> Dict:
        """
        获取审批统计

        用于评估AI的可信度和门店的信任阶段
        """
        logger.info("获取审批统计", store_id=store_id)

        from src.core.database import get_db_session
        from src.models.decision_log import DecisionLog, DecisionStatus
        from sqlalchemy import select, func

        async with get_db_session() as session:
            total_result = await session.execute(
                select(func.count(DecisionLog.id)).where(DecisionLog.store_id == store_id)
            )
            total_decisions = int(total_result.scalar() or 0)

            auto_result = await session.execute(
                select(func.count(DecisionLog.id)).where(
                    DecisionLog.store_id == store_id,
                    DecisionLog.decision_status == DecisionStatus.EXECUTED,
                    DecisionLog.manager_id == None,
                )
            )
            auto_executed = int(auto_result.scalar() or 0)

            approval_result = await session.execute(
                select(func.count(DecisionLog.id)).where(
                    DecisionLog.store_id == store_id,
                    DecisionLog.decision_status.in_([
                        DecisionStatus.APPROVED, DecisionStatus.REJECTED, DecisionStatus.MODIFIED
                    ])
                )
            )
            approval_required = int(approval_result.scalar() or 0)

            approved_result = await session.execute(
                select(func.count(DecisionLog.id)).where(
                    DecisionLog.store_id == store_id,
                    DecisionLog.decision_status == DecisionStatus.APPROVED,
                )
            )
            approved_count = int(approved_result.scalar() or 0)

            time_result = await session.execute(
                select(
                    func.avg(
                        func.extract("epoch", DecisionLog.approved_at) -
                        func.extract("epoch", DecisionLog.created_at)
                    )
                ).where(
                    DecisionLog.store_id == store_id,
                    DecisionLog.approved_at != None,
                )
            )
            avg_seconds = float(time_result.scalar() or 0)

            trust_result = await session.execute(
                select(func.avg(DecisionLog.trust_score)).where(
                    DecisionLog.store_id == store_id,
                    DecisionLog.trust_score != None,
                )
            )
            avg_trust = float(trust_result.scalar() or 85.0)

        approval_rate = round(approved_count / approval_required, 2) if approval_required > 0 else 0.0
        current_trust_phase = await self.get_store_trust_phase(store_id)

        stats = {
            "total_decisions": total_decisions,
            "auto_executed": auto_executed,
            "approval_required": approval_required,
            "approval_rate": approval_rate,
            "avg_approval_time_hours": round(avg_seconds / 3600, 1),
            "trust_score": round(avg_trust / 100.0, 2),
            "current_trust_phase": current_trust_phase,
        }

        return stats


# 全局服务实例
human_in_the_loop_service: Optional[HumanInTheLoopService] = None


def get_human_in_the_loop_service(db: Session) -> HumanInTheLoopService:
    """获取Human-in-the-Loop服务实例"""
    return HumanInTheLoopService(db)
