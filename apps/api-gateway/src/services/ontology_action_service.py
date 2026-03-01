"""
L4 Action 状态机服务：创建、推送、回执、超时升级
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.ontology_action import (
    OntologyAction,
    ActionStatus,
    ActionPriority,
    ESCALATION_MINUTES,
)


def _deadline_for_priority(priority: str) -> datetime:
    mins = ESCALATION_MINUTES.get(priority, 120)
    return datetime.utcnow() + timedelta(minutes=mins)


async def create_action(
    session: AsyncSession,
    tenant_id: str,
    store_id: str,
    action_type: str,
    assignee_staff_id: str,
    assignee_wechat_id: Optional[str] = None,
    priority: str = ActionPriority.P1.value,
    title: Optional[str] = None,
    body: Optional[str] = None,
    traced_reasoning_id: Optional[str] = None,
    traced_report: Optional[Dict[str, Any]] = None,
) -> OntologyAction:
    """创建 Action，状态 CREATED，并计算 deadline。"""
    deadline = _deadline_for_priority(priority)
    action = OntologyAction(
        tenant_id=tenant_id,
        store_id=store_id,
        action_type=action_type,
        assignee_staff_id=assignee_staff_id,
        assignee_wechat_id=assignee_wechat_id,
        status=ActionStatus.CREATED.value,
        priority=priority,
        deadline_at=deadline,
        title=title or action_type,
        body=body,
        traced_reasoning_id=traced_reasoning_id,
        traced_report=traced_report,
    )
    session.add(action)
    await session.flush()
    return action


async def list_actions(
    session: AsyncSession,
    tenant_id: str,
    store_id: Optional[str] = None,
    status: Optional[str] = None,
    assignee_staff_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[OntologyAction]:
    """列表查询。"""
    q = select(OntologyAction).where(OntologyAction.tenant_id == tenant_id)
    if store_id:
        q = q.where(OntologyAction.store_id == store_id)
    if status:
        q = q.where(OntologyAction.status == status)
    if assignee_staff_id:
        q = q.where(OntologyAction.assignee_staff_id == assignee_staff_id)
    q = q.order_by(OntologyAction.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return list(result.scalars().all())


async def update_status(
    session: AsyncSession,
    action_id: str,
    status: str,
) -> Optional[OntologyAction]:
    """更新状态（SENT/ACKED/IN_PROGRESS/DONE/CLOSED）。"""
    from sqlalchemy import update
    from uuid import UUID
    now = datetime.utcnow()
    q = select(OntologyAction).where(OntologyAction.id == UUID(action_id))
    res = await session.execute(q)
    action = res.scalar_one_or_none()
    if not action:
        return None
    action.status = status
    if status == ActionStatus.SENT.value:
        action.sent_at = now
    elif status == ActionStatus.ACKED.value:
        action.acked_at = now
    elif status == ActionStatus.DONE.value or status == ActionStatus.CLOSED.value:
        action.done_at = now
    await session.flush()
    return action


async def get_actions_pending_escalation(
    session: AsyncSession,
    as_of: Optional[datetime] = None,
) -> List[OntologyAction]:
    """获取应升级的 Action：已 SENT 且超过 deadline 未 ACKED。"""
    now = as_of or datetime.utcnow()
    q = (
        select(OntologyAction)
        .where(OntologyAction.status == ActionStatus.SENT.value)
        .where(OntologyAction.deadline_at <= now)
        .where(OntologyAction.acked_at.is_(None))
    )
    result = await session.execute(q)
    return list(result.scalars().all())


# 升级目标角色名（用于记录 escalated_to）
ESCALATION_ROLE_BY_PRIORITY = {
    ActionPriority.P0.value: "督导",
    ActionPriority.P1.value: "区域",
    ActionPriority.P2.value: "店长",
    ActionPriority.P3.value: "系统",
}


async def process_escalations(session: AsyncSession) -> int:
    """
    扫描已 SENT 且超过 deadline 未回执的 Action，标记升级并推送给升级对象（企微）。
    返回本次处理的条数。
    """
    from src.core.config import settings
    from src.services.wechat_service import wechat_service

    pending = await get_actions_pending_escalation(session)
    if not pending:
        return 0
    now = datetime.utcnow()
    escalation_to_ids: List[str] = []
    if getattr(settings, "WECHAT_ESCALATION_TO", None):
        escalation_to_ids = [x.strip() for x in settings.WECHAT_ESCALATION_TO.split(",") if x.strip()]
    can_send = wechat_service.is_configured() and escalation_to_ids
    count = 0
    for action in pending:
        role = ESCALATION_ROLE_BY_PRIORITY.get(action.priority, "升级")
        action.escalation_at = now
        action.escalated_to = role
        if can_send:
            title = action.title or action.action_type
            body = (action.body or "")[:200]
            content = (
                f"【智链OS·升级】{title}\n"
                f"门店: {action.store_id} | 执行人: {action.assignee_staff_id}\n"
                f"{body}\n"
                f"原截止: {action.deadline_at.strftime('%Y-%m-%d %H:%M') if action.deadline_at else '-'} | 升级至: {role}"
            )
            for uid in escalation_to_ids:
                try:
                    await wechat_service.send_text_message(content=content, touser=uid)
                except Exception:
                    pass
        count += 1
    await session.flush()
    return count


def _action_ack_sign(action_id: str) -> str:
    """生成一键回执链接签名（HMAC-SHA256）。"""
    import hashlib
    import hmac as hm
    from src.core.config import settings
    secret = getattr(settings, "WECHAT_TOKEN", None) or getattr(settings, "ACTION_ACK_SECRET", "") or "default_ack_secret"
    return hm.new(secret.encode(), action_id.encode(), hashlib.sha256).hexdigest()


async def push_action_to_wechat(
    session: AsyncSession,
    action_id: str,
) -> Optional[OntologyAction]:
    """
    将 Action 推送到企微（文本或任务卡片）；若配置 ACTION_ACK_BASE_URL 则发卡片，点击「确认回执」跳转回执。
    需配置 wechat_service（WECHAT_CORP_ID/SECRET/AGENT_ID）。
    """
    from uuid import UUID
    from src.services.wechat_service import wechat_service
    from src.core.config import settings

    q = select(OntologyAction).where(OntologyAction.id == UUID(action_id))
    res = await session.execute(q)
    action = res.scalar_one_or_none()
    if not action or action.status != ActionStatus.CREATED.value:
        return None
    if not wechat_service.is_configured():
        return None
    touser = action.assignee_wechat_id or action.assignee_staff_id
    title = action.title or action.action_type
    body = (action.body or "")[:500]
    deadline_str = action.deadline_at.strftime("%Y-%m-%d %H:%M") if action.deadline_at else "-"
    base_url = (getattr(settings, "ACTION_ACK_BASE_URL", None) or "").rstrip("/")
    try:
        if base_url and hasattr(wechat_service, "send_card_message"):
            sign = _action_ack_sign(str(action.id))
            ack_url = f"{base_url}/api/v1/enterprise/action-ack?action_id={action.id}&sign={sign}"
            desc = f"{body}\n截止: {deadline_str}\n点击下方按钮确认收到。"
            await wechat_service.send_card_message(
                title=f"【智链OS】{title}",
                description=desc,
                url=ack_url,
                btntxt="确认回执",
                touser=touser,
            )
        else:
            content = f"【智链OS】{title}\n\n{body}\n\n截止: {deadline_str}"
            await wechat_service.send_text_message(content=content, touser=touser)
    except Exception:
        return None
    action.status = ActionStatus.SENT.value
    action.sent_at = datetime.utcnow()
    await session.flush()
    return action
