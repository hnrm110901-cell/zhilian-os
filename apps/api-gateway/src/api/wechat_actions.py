"""
企业微信 Action 状态机 API

端点：
  POST  /api/v1/wechat-actions/                  创建并推送 Action
  GET   /api/v1/wechat-actions/{action_id}        查询 Action 详情
  POST  /api/v1/wechat-actions/{action_id}/ack    手动确认
  POST  /api/v1/wechat-actions/{action_id}/resolve  手动解决
  POST  /api/v1/wechat-actions/{action_id}/escalate  手动升级
  GET   /api/v1/wechat-actions/store/{store_id}   查询门店 Action 列表
  GET   /api/v1/wechat-actions/store/{store_id}/stats  Action 统计
  POST  /api/v1/wechat-actions/webhook/callback   企微 Webhook 回调（验签）
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from src.core.dependencies import get_current_user
from src.models.user import User
from src.services.wechat_action_fsm import (
    ActionCategory,
    ActionPriority,
    ActionState,
    WeChatActionFSM,
    get_wechat_fsm,
)

router = APIRouter(prefix="/api/v1/wechat-actions", tags=["wechat_actions"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ActionCreateIn(BaseModel):
    store_id: str
    category: ActionCategory
    priority: ActionPriority
    title: str = Field(..., max_length=100)
    content: str = Field(..., max_length=2000)
    receiver_user_id: str = Field(..., description="企微员工 ID")
    escalation_user_id: str = Field("", description="升级收件人企微 ID")
    source_event_id: Optional[str] = None
    evidence: dict = Field(default_factory=dict)
    auto_push: bool = Field(True, description="创建后立即推送企微")


class ResolveIn(BaseModel):
    resolution_notes: str = Field("", max_length=500)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_action(
    payload: ActionCreateIn,
    current_user: User = Depends(get_current_user),
):
    """创建 Action 并（可选）立即推送企微"""
    fsm: WeChatActionFSM = get_wechat_fsm()
    action = await fsm.create_action(
        store_id=payload.store_id,
        category=payload.category,
        priority=payload.priority,
        title=payload.title,
        content=payload.content,
        receiver_user_id=payload.receiver_user_id,
        escalation_user_id=payload.escalation_user_id,
        source_event_id=payload.source_event_id,
        evidence=payload.evidence,
    )
    if payload.auto_push:
        await fsm.push_to_wechat(action.action_id)
    return action.to_dict()


@router.get("/{action_id}")
async def get_action(
    action_id: str,
    current_user: User = Depends(get_current_user),
):
    """查询 Action 详情"""
    fsm = get_wechat_fsm()
    action = fsm.get_action(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action 不存在")
    return action


@router.post("/{action_id}/ack")
async def acknowledge_action(
    action_id: str,
    current_user: User = Depends(get_current_user),
):
    """手动确认 Action"""
    fsm = get_wechat_fsm()
    ok = await fsm.acknowledge(action_id, str(current_user.id))
    if not ok:
        raise HTTPException(status_code=400, detail="Action 状态不允许确认")
    return {"message": "已确认", "action_id": action_id}


@router.post("/{action_id}/resolve")
async def resolve_action(
    action_id: str,
    payload: ResolveIn,
    current_user: User = Depends(get_current_user),
):
    """手动解决 Action"""
    fsm = get_wechat_fsm()
    ok = await fsm.resolve(action_id, resolution_notes=payload.resolution_notes)
    if not ok:
        raise HTTPException(status_code=400, detail="Action 已解决或已关闭")
    return {"message": "已解决", "action_id": action_id}


@router.post("/{action_id}/escalate")
async def escalate_action(
    action_id: str,
    current_user: User = Depends(get_current_user),
):
    """手动触发 Action 升级"""
    fsm = get_wechat_fsm()
    ok = await fsm.escalate(action_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Action 无法升级（已解决/已关闭）")
    return {"message": "升级已触发", "action_id": action_id}


@router.get("/store/{store_id}")
async def list_store_actions(
    store_id: str,
    state: Optional[ActionState] = Query(None),
    priority: Optional[ActionPriority] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    """查询门店 Action 列表"""
    fsm = get_wechat_fsm()
    return fsm.list_actions(store_id=store_id, state=state, priority=priority, limit=limit)


@router.get("/store/{store_id}/stats")
async def get_store_action_stats(
    store_id: str,
    current_user: User = Depends(get_current_user),
):
    """获取门店 Action 统计（状态/优先级分布、平均处理时长）"""
    fsm = get_wechat_fsm()
    return fsm.get_stats(store_id)


@router.post("/webhook/callback", include_in_schema=False)
async def wechat_webhook(request: Request):
    """
    企业微信 Webhook 回调端点（无需 JWT 认证）

    企微服务器回调验签后调用此接口通知消息已读/操作事件。
    """
    import os
    token = os.getenv("WECHAT_WEBHOOK_TOKEN", "")
    timestamp = request.query_params.get("timestamp", "")
    nonce = request.query_params.get("nonce", "")
    signature = request.query_params.get("msg_signature", "")

    fsm = get_wechat_fsm()

    # GET 请求 = 企微服务器验证
    if request.method == "GET":
        echostr = request.query_params.get("echostr", "")
        if token and not fsm.verify_webhook_signature(token, timestamp, nonce, signature):
            raise HTTPException(status_code=403, detail="企微签名验证失败")
        return {"echostr": echostr}

    # POST 请求 = 消息回调
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    result = fsm.handle_webhook_callback(payload)
    return result
