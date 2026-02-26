"""
企业微信和飞书集成API
Enterprise WeChat and Feishu Integration API
"""
import os
from fastapi import APIRouter, Depends, HTTPException, Request, Body, Query
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import structlog

from src.core.dependencies import get_current_active_user
from src.core.config import settings
from src.services.wechat_service import wechat_service
from src.services.feishu_service import feishu_service
from src.models import User
from src.utils.wechat_crypto import WeChatCrypto

logger = structlog.get_logger()

router = APIRouter()

# 初始化企业微信加解密工具
wechat_crypto = None
if settings.WECHAT_TOKEN and settings.WECHAT_ENCODING_AES_KEY and settings.WECHAT_CORP_ID:
    wechat_crypto = WeChatCrypto(
        token=settings.WECHAT_TOKEN,
        encoding_aes_key=settings.WECHAT_ENCODING_AES_KEY,
        corp_id=settings.WECHAT_CORP_ID
    )


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
@router.get("/wechat/webhook", summary="企业微信URL验证")
async def wechat_webhook(
    request: Request,
    msg_signature: str = Query(..., description="消息签名"),
    timestamp: str = Query(..., description="时间戳"),
    nonce: str = Query(..., description="随机字符串"),
    echostr: Optional[str] = Query(None, description="验证URL时的加密字符串")
):
    """
    企业微信消息回调接口

    接收企业微信推送的消息和事件
    支持GET请求用于URL验证，POST请求用于接收消息
    """
    try:
        # 检查是否配置了加解密工具
        if not wechat_crypto:
            logger.error("企业微信回调配置未完成")
            raise HTTPException(
                status_code=503,
                detail="企业微信回调配置未完成，请配置WECHAT_TOKEN和WECHAT_ENCODING_AES_KEY"
            )

        # GET请求：URL验证
        if request.method == "GET":
            if not echostr:
                raise HTTPException(status_code=400, detail="缺少echostr参数")

            # 验证签名
            if not wechat_crypto.verify_signature(msg_signature, timestamp, nonce, echostr):
                logger.error("企业微信URL验证签名失败")
                raise HTTPException(status_code=403, detail="签名验证失败")

            # 解密echostr
            decrypted_echo, error = wechat_crypto.decrypt_message(echostr)
            if error:
                logger.error("解密echostr失败", error=error)
                raise HTTPException(status_code=500, detail=f"解密失败: {error}")

            logger.info("企业微信URL验证成功")
            return decrypted_echo

        # POST请求：接收消息
        data = await request.body()

        # 解析XML消息
        xml_message = wechat_crypto.parse_xml_message(data)
        if not xml_message:
            raise HTTPException(status_code=400, detail="XML解析失败")

        # 获取加密的消息内容
        encrypt_msg = xml_message.get("Encrypt")
        if not encrypt_msg:
            raise HTTPException(status_code=400, detail="缺少加密消息")

        # 验证签名
        if not wechat_crypto.verify_signature(msg_signature, timestamp, nonce, encrypt_msg):
            logger.error("企业微信消息签名验证失败")
            raise HTTPException(status_code=403, detail="签名验证失败")

        # 解密消息
        decrypted_msg, error = wechat_crypto.decrypt_message(encrypt_msg)
        if error:
            logger.error("消息解密失败", error=error)
            raise HTTPException(status_code=500, detail=f"解密失败: {error}")

        # 解析解密后的XML消息
        message_data = wechat_crypto.parse_xml_message(decrypted_msg.encode())
        if not message_data:
            raise HTTPException(status_code=400, detail="消息解析失败")

        from_user = message_data.get("FromUserName") or ""
        msg_type = message_data.get("MsgType") or ""

        logger.info(
            "收到企业微信消息",
            msg_type=msg_type,
            from_user=from_user
        )

        # 私域运营 Agent 对话入口（P0）：文本消息 → nl_query → 企微回复
        if msg_type == "text" and from_user:
            content = (message_data.get("Content") or "").strip()
            if content and wechat_service.is_configured():
                try:
                    import sys
                    from pathlib import Path
                    from sqlalchemy import select

                    # 私域 Agent 与 base_agent 路径（与 private_domain 路由一致）
                    _api_dir = Path(__file__).resolve().parent
                    _src_dir = _api_dir.parent
                    _core_dir = _src_dir / "core"
                    _agent_src = _src_dir.parent.parent.parent / "packages" / "agents" / "private_domain" / "src"
                    for _p in (_core_dir, _agent_src):
                        if _p.exists() and str(_p) not in sys.path:
                            sys.path.insert(0, str(_p))

                    from agent import PrivateDomainAgent

                    # P1：可选从 User 表解析 store_id（企微 UserId → 智链OS User.store_id）
                    store_id = "default"
                    try:
                        from src.core.database import get_db_session
                        from src.models.user import User as UserModel
                        async with get_db_session(enable_tenant_isolation=False) as session:
                            r = await session.execute(
                                select(UserModel).where(UserModel.wechat_user_id == from_user).limit(1)
                            )
                            u = r.scalar_one_or_none()
                            if u and getattr(u, "store_id", None):
                                store_id = u.store_id or "default"
                    except Exception as db_e:
                        logger.debug("wechat_user store_id lookup skipped", from_user=from_user, error=str(db_e))

                    agent = PrivateDomainAgent(store_id=store_id)
                    result = await agent.execute("nl_query", {"query": content, "store_id": store_id})

                    if result.success and result.data:
                        answer = (
                            result.data.get("answer")
                            or result.data.get("summary")
                            or "已收到，请稍后再试。"
                        )
                        # 企微文本消息长度限制，截断并避免截断中文
                        reply_text = (answer[:2000] + "…") if len(answer) > 2000 else answer
                        await wechat_service.send_text_message(content=reply_text, touser=from_user)
                        logger.info("私域Agent回复已发送", from_user=from_user, reply_len=len(reply_text))
                    else:
                        fallback = "请稍后再试或联系管理员。"
                        await wechat_service.send_text_message(content=fallback, touser=from_user)
                except Exception as agent_e:
                    logger.warning("私域Agent回复失败，已忽略", from_user=from_user, error=str(agent_e))

        # 返回成功响应（企业微信要求返回"success"或加密的XML）
        return "success"

    except HTTPException:
        raise
    except Exception as e:
        logger.error("处理企业微信回调失败", error=str(e), exc_info=e)
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
    page_size: int = int(os.getenv("FEISHU_PAGE_SIZE", "50")),
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
