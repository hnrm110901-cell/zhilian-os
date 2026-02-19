"""
企业微信和飞书集成API
Enterprise WeChat and Feishu Integration API
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import structlog

from src.core.dependencies import get_current_active_user
from src.services.wechat_service import wechat_service
from src.services.feishu_service import feishu_service
from src.models import User

logger = structlog.get_logger()

router = APIRouter()


# ==================== Request/Response Models ====================


class SendMessageRequest(BaseModel):
    """发送消息请求"""
    content: str = Field(..., description="消息内容")
    touser: Optional[str] = Field(None, description="接收用户ID")
    message_type: str = Field("text", description="消息类型: text, markdown, card")
    title: Optional[str] = Field(None, description="消息标题（卡片消息使用）")
    url: Optional[str] = Field(None, description="跳转链接（卡片消息使用）")


class FeishuMessageRequest(BaseModel):
    """飞书消息请求"""
    content: str = Field(..., description="消息内容")
    receive_id: str = Field(..., description="接收者ID")
    receive_id_type: str = Field("user_id", description="ID类型")
    message_type: str = Field("text", description="消息类型")


# ==================== 企业微信 API ====================


@router.post("/wechat/send-message", summary="发送企业微信消息")
async def send_wechat_message(
    request: SendMessageRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    发送企业微信消息

    支持的消息类型:
    - text: 文本消息
    - markdown: Markdown消息
    - card: 卡片消息
    """
    if not wechat_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="企业微信未配置，请在环境变量中设置WECHAT_CORP_ID、WECHAT_CORP_SECRET和WECHAT_AGENT_ID"
        )

    try:
        if request.message_type == "text":
            result = await wechat_service.send_text_message(
                content=request.content,
                touser=request.touser,
            )
        elif request.message_type == "markdown":
            result = await wechat_service.send_markdown_message(
                content=request.content,
                touser=request.touser,
            )
        elif request.message_type == "card":
            if not request.title or not request.url:
                raise HTTPException(
                    status_code=400,
                    detail="卡片消息需要提供title和url"
                )
            result = await wechat_service.send_card_message(
                title=request.title,
                description=request.content,
                url=request.url,
                touser=request.touser,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的消息类型: {request.message_type}"
            )

        return {
            "success": True,
            "message": "消息发送成功",
            "data": result,
        }

    except Exception as e:
        logger.error("发送企业微信消息失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"发送消息失败: {str(e)}")


@router.post("/wechat/webhook", summary="企业微信消息回调")
async def wechat_webhook(request: Request):
    """
    企业微信消息回调接口

    接收企业微信推送的消息和事件
    """
    try:
        # 获取请求数据
        data = await request.body()

        # TODO: 验证签名
        # 企业微信会对消息进行加密，需要解密后处理

        # 解析XML数据
        # message_data = parse_wechat_xml(data)

        # 处理消息
        # response = await wechat_service.handle_message(message_data)

        # 返回响应（需要加密）
        return {"success": True}

    except Exception as e:
        logger.error("处理企业微信回调失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wechat/users", summary="获取企业微信用户列表")
async def get_wechat_users(
    department_id: int = 1,
    current_user: User = Depends(get_current_active_user),
):
    """获取企业微信部门用户列表"""
    if not wechat_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="企业微信未配置"
        )

    try:
        users = await wechat_service.get_department_users(department_id)
        return {
            "success": True,
            "data": users,
            "count": len(users),
        }

    except Exception as e:
        logger.error("获取企业微信用户列表失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wechat/user/{userid}", summary="获取企业微信用户信息")
async def get_wechat_user(
    userid: str,
    current_user: User = Depends(get_current_active_user),
):
    """获取企业微信用户详细信息"""
    if not wechat_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="企业微信未配置"
        )

    try:
        user_info = await wechat_service.get_user_info(userid)
        return {
            "success": True,
            "data": user_info,
        }

    except Exception as e:
        logger.error("获取企业微信用户信息失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wechat/status", summary="检查企业微信配置状态")
async def check_wechat_status(
    current_user: User = Depends(get_current_active_user),
):
    """检查企业微信是否已配置"""
    is_configured = wechat_service.is_configured()

    return {
        "configured": is_configured,
        "message": "企业微信已配置" if is_configured else "企业微信未配置，请设置环境变量",
    }


# ==================== 飞书 API ====================


@router.post("/feishu/send-message", summary="发送飞书消息")
async def send_feishu_message(
    request: FeishuMessageRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    发送飞书消息

    支持的消息类型:
    - text: 文本消息
    - post: 富文本消息
    - interactive: 交互式卡片
    """
    if not feishu_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="飞书未配置，请在环境变量中设置FEISHU_APP_ID和FEISHU_APP_SECRET"
        )

    try:
        if request.message_type == "text":
            result = await feishu_service.send_text_message(
                content=request.content,
                receive_id=request.receive_id,
                receive_id_type=request.receive_id_type,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的消息类型: {request.message_type}"
            )

        return {
            "success": True,
            "message": "消息发送成功",
            "data": result,
        }

    except Exception as e:
        logger.error("发送飞书消息失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"发送消息失败: {str(e)}")


@router.post("/feishu/webhook", summary="飞书事件回调")
async def feishu_webhook(request: Request):
    """
    飞书事件回调接口

    接收飞书推送的事件和消息
    """
    try:
        # 获取请求数据
        data = await request.json()

        # 处理URL验证
        if data.get("type") == "url_verification":
            return {"challenge": data.get("challenge")}

        # 处理事件
        response = await feishu_service.handle_message(data)

        return {"success": True, "data": response}

    except Exception as e:
        logger.error("处理飞书回调失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feishu/users", summary="获取飞书用户列表")
async def get_feishu_users(
    department_id: str = "0",
    page_size: int = 50,
    current_user: User = Depends(get_current_active_user),
):
    """获取飞书部门用户列表"""
    if not feishu_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="飞书未配置"
        )

    try:
        users = await feishu_service.get_department_users(department_id, page_size)
        return {
            "success": True,
            "data": users,
            "count": len(users),
        }

    except Exception as e:
        logger.error("获取飞书用户列表失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feishu/user/{user_id}", summary="获取飞书用户信息")
async def get_feishu_user(
    user_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """获取飞书用户详细信息"""
    if not feishu_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="飞书未配置"
        )

    try:
        user_info = await feishu_service.get_user_info(user_id)
        return {
            "success": True,
            "data": user_info,
        }

    except Exception as e:
        logger.error("获取飞书用户信息失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feishu/status", summary="检查飞书配置状态")
async def check_feishu_status(
    current_user: User = Depends(get_current_active_user),
):
    """检查飞书是否已配置"""
    is_configured = feishu_service.is_configured()

    return {
        "configured": is_configured,
        "message": "飞书已配置" if is_configured else "飞书未配置，请设置环境变量",
    }
