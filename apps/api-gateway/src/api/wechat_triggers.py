"""
企业微信推送触发管理API
WeChat Push Trigger Management API
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Optional, Dict, Any
import structlog

from ..services.wechat_trigger_service import wechat_trigger_service, send_wechat_push_task
from ..core.dependencies import get_current_user
from ..models.user import User

router = APIRouter(prefix="/api/v1/wechat/triggers", tags=["WeChat Triggers"])
logger = structlog.get_logger()


@router.get("/rules")
async def get_trigger_rules(
    current_user: User = Depends(get_current_user),
):
    """
    获取所有触发规则

    返回当前配置的所有企微推送触发规则
    """
    try:
        rules = wechat_trigger_service.trigger_rules

        return {
            "success": True,
            "data": {
                "rules": rules,
                "total": len(rules),
            },
        }

    except Exception as e:
        logger.error("获取触发规则失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"获取触发规则失败: {str(e)}")


@router.get("/rules/{event_type}")
async def get_trigger_rule(
    event_type: str,
    current_user: User = Depends(get_current_user),
):
    """
    获取指定事件的触发规则

    Args:
        event_type: 事件类型（如 order.created）
    """
    try:
        rule = wechat_trigger_service.trigger_rules.get(event_type)

        if not rule:
            raise HTTPException(status_code=404, detail=f"触发规则不存在: {event_type}")

        return {
            "success": True,
            "data": {
                "event_type": event_type,
                "rule": rule,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取触发规则失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"获取触发规则失败: {str(e)}")


@router.put("/rules/{event_type}/toggle")
async def toggle_trigger_rule(
    event_type: str,
    enabled: bool = Body(..., embed=True),
    current_user: User = Depends(get_current_user),
):
    """
    启用/禁用触发规则

    Args:
        event_type: 事件类型
        enabled: 是否启用
    """
    try:
        if event_type not in wechat_trigger_service.trigger_rules:
            raise HTTPException(status_code=404, detail=f"触发规则不存在: {event_type}")

        # 更新规则状态
        wechat_trigger_service.trigger_rules[event_type]["enabled"] = enabled

        logger.info(
            "触发规则状态已更新",
            event_type=event_type,
            enabled=enabled,
            user=current_user.username,
        )

        return {
            "success": True,
            "message": f"触发规则已{'启用' if enabled else '禁用'}",
            "data": {
                "event_type": event_type,
                "enabled": enabled,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("更新触发规则失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"更新触发规则失败: {str(e)}")


@router.post("/test")
async def test_trigger(
    event_type: str = Body(...),
    event_data: Dict[str, Any] = Body(...),
    store_id: Optional[str] = Body(None),
    current_user: User = Depends(get_current_user),
):
    """
    测试触发规则

    手动触发一次企微推送，用于测试配置是否正确

    Args:
        event_type: 事件类型
        event_data: 事件数据
        store_id: 门店ID
    """
    try:
        # 触发推送
        result = await wechat_trigger_service.trigger_push(
            event_type=event_type,
            event_data=event_data,
            store_id=store_id,
        )

        return {
            "success": True,
            "message": "测试推送已发送",
            "data": result,
        }

    except Exception as e:
        logger.error("测试触发失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"测试触发失败: {str(e)}")


@router.get("/stats")
async def get_trigger_stats(
    current_user: User = Depends(get_current_user),
):
    """
    获取触发统计

    返回各类事件的触发次数、成功率等统计信息
    """
    try:
        # TODO: 实现触发统计功能
        # 需要在触发时记录统计数据到数据库或Redis

        return {
            "success": True,
            "data": {
                "total_triggers": 0,
                "success_count": 0,
                "failure_count": 0,
                "by_event_type": {},
            },
            "message": "触发统计功能开发中",
        }

    except Exception as e:
        logger.error("获取触发统计失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"获取触发统计失败: {str(e)}")


@router.post("/manual-send")
async def manual_send_message(
    content: str = Body(...),
    touser: Optional[str] = Body(None),
    toparty: Optional[str] = Body(None),
    totag: Optional[str] = Body(None),
    current_user: User = Depends(get_current_user),
):
    """
    手动发送企微消息

    不通过触发规则，直接发送自定义消息

    Args:
        content: 消息内容
        touser: 目标用户ID（多个用|分隔）
        toparty: 目标部门ID（多个用|分隔）
        totag: 目标标签ID（多个用|分隔）
    """
    try:
        result = await wechat_trigger_service.wechat_service.send_text_message(
            content=content,
            touser=touser,
            toparty=toparty,
            totag=totag,
        )

        logger.info(
            "手动发送企微消息",
            user=current_user.username,
            result=result,
        )

        return {
            "success": True,
            "message": "消息已发送",
            "data": result,
        }

    except Exception as e:
        logger.error("手动发送消息失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"发送消息失败: {str(e)}")
