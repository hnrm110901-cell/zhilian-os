"""
IM 通讯录变更回调 API — 企微/钉钉实时同步

企微回调事件（通讯录变更）：
  - change_contact → create_user / update_user / delete_user

钉钉回调事件（通讯录变更）：
  - user_add_org / user_modify_org / user_leave_org

接入流程：
1. 在品牌 IM 配置中填写 callback token 和 encoding_aes_key
2. 在 IM 平台管理后台设置回调 URL：
   - 企微: https://api.zlsjos.cn/api/v1/im/callback/wechat/{brand_id}
   - 钉钉: https://api.zlsjos.cn/api/v1/im/callback/dingtalk/{brand_id}
3. 平台会先发 GET 验证请求，通过后推送事件
"""

import hashlib
import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..models.brand_im_config import BrandIMConfig, IMPlatform
from ..services.im_sync_service import IMSyncService

logger = structlog.get_logger()
router = APIRouter()


# ── 企业微信回调 ──────────────────────────────────────


@router.get("/im/callback/wechat/{brand_id}")
async def wechat_callback_verify(
    brand_id: str,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """企业微信回调 URL 验证（GET 请求）"""
    result = await db.execute(select(BrandIMConfig).where(BrandIMConfig.brand_id == brand_id))
    config = result.scalar_one_or_none()
    if not config or config.im_platform != IMPlatform.WECHAT_WORK:
        raise HTTPException(status_code=404, detail="未找到企微配置")

    token = config.wechat_token
    encoding_aes_key = config.wechat_encoding_aes_key

    if not token or not encoding_aes_key:
        raise HTTPException(status_code=400, detail="未配置回调 Token/EncodingAESKey")

    try:
        from ..utils.wechat_crypto import WeChatCrypto

        crypto = WeChatCrypto(
            token=token,
            encoding_aes_key=encoding_aes_key,
            corp_id=config.wechat_corp_id,
        )
        # 验证签名并解密 echostr
        decrypted = crypto.decrypt_message(echostr, msg_signature, timestamp, nonce)
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse(content=decrypted)
    except Exception as e:
        logger.error("wechat_callback_verify_failed", brand_id=brand_id, error=str(e))
        raise HTTPException(status_code=403, detail="签名验证失败")


@router.post("/im/callback/wechat/{brand_id}")
async def wechat_callback_event(
    brand_id: str,
    request: Request,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """企业微信通讯录变更事件回调（POST 请求）"""
    result = await db.execute(select(BrandIMConfig).where(BrandIMConfig.brand_id == brand_id))
    config = result.scalar_one_or_none()
    if not config or config.im_platform != IMPlatform.WECHAT_WORK:
        raise HTTPException(status_code=404, detail="未找到企微配置")

    body = await request.body()

    try:
        from ..utils.wechat_crypto import WeChatCrypto

        crypto = WeChatCrypto(
            token=config.wechat_token,
            encoding_aes_key=config.wechat_encoding_aes_key,
            corp_id=config.wechat_corp_id,
        )

        # 解析 XML
        msg_data = crypto.parse_xml_message(body.decode("utf-8"))
        encrypt_str = msg_data.get("Encrypt", "")

        # 验证签名并解密
        decrypted_xml = crypto.decrypt_message(encrypt_str, msg_signature, timestamp, nonce)
        event_data = crypto.parse_xml_message(decrypted_xml)

        event_type = event_data.get("Event", "")
        change_type = event_data.get("ChangeType", "")

        logger.info(
            "wechat_contact_callback",
            brand_id=brand_id,
            event=event_type,
            change_type=change_type,
        )

        # 仅处理通讯录变更事件
        if event_type == "change_contact" and change_type in ("create_user", "update_user", "delete_user"):
            service = IMSyncService(db)
            await service.handle_member_event(
                brand_id=brand_id,
                event_type=change_type,
                member_data=event_data,
            )

        # 返回 success 告知企微已接收
        response_xml = crypto.generate_response_xml("success", nonce, timestamp)
        from fastapi.responses import Response

        return Response(content=response_xml, media_type="application/xml")

    except Exception as e:
        logger.error("wechat_callback_event_failed", brand_id=brand_id, error=str(e))
        return {"status": "error", "message": str(e)}


# ── 钉钉回调 ──────────────────────────────────────────


@router.post("/im/callback/dingtalk/{brand_id}")
async def dingtalk_callback_event(
    brand_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    钉钉事件订阅回调。

    钉钉回调 JSON 格式:
    {
        "encrypt": "加密字符串"
    }

    解密后事件体:
    {
        "EventType": "user_add_org",
        "UserId": ["xxx"],
        ...
    }
    """
    result = await db.execute(select(BrandIMConfig).where(BrandIMConfig.brand_id == brand_id))
    config = result.scalar_one_or_none()
    if not config or config.im_platform != IMPlatform.DINGTALK:
        raise HTTPException(status_code=404, detail="未找到钉钉配置")

    body = await request.json()

    # 钉钉回调签名验证 + 解密
    encrypt_str = body.get("encrypt", "")

    if not config.dingtalk_token or not config.dingtalk_aes_key:
        raise HTTPException(status_code=400, detail="未配置钉钉回调 Token/AES Key")

    try:
        event_data = _dingtalk_decrypt(
            encrypt_str,
            config.dingtalk_token,
            config.dingtalk_aes_key,
            config.dingtalk_app_key,
        )

        event_type = event_data.get("EventType", "")

        logger.info(
            "dingtalk_contact_callback",
            brand_id=brand_id,
            event_type=event_type,
        )

        # 检查是否是验证请求
        if event_type == "check_url":
            # 返回加密的 success
            resp_encrypt = _dingtalk_encrypt(
                "success",
                config.dingtalk_token,
                config.dingtalk_aes_key,
                config.dingtalk_app_key,
            )
            return resp_encrypt

        # 通讯录变更事件
        if event_type in ("user_add_org", "user_modify_org", "user_leave_org"):
            # 钉钉回调中 UserId 是列表
            user_ids = event_data.get("UserId", [])
            service = IMSyncService(db)
            for uid in user_ids:
                await service.handle_member_event(
                    brand_id=brand_id,
                    event_type=event_type,
                    member_data={"userid": uid},
                )

        # 返回加密的 success
        resp_encrypt = _dingtalk_encrypt(
            "success",
            config.dingtalk_token,
            config.dingtalk_aes_key,
            config.dingtalk_app_key,
        )
        return resp_encrypt

    except Exception as e:
        logger.error("dingtalk_callback_failed", brand_id=brand_id, error=str(e))
        return {"status": "error", "message": str(e)}


# ── 钉钉加解密工具 ──────────────────────────────────


def _dingtalk_decrypt(
    encrypt_str: str,
    token: str,
    aes_key: str,
    app_key: str,
) -> dict:
    """
    钉钉回调消息解密。
    钉钉使用 AES-CBC 加密，key 为 base64decode(aes_key + "=")。
    """
    import base64

    from Crypto.Cipher import AES

    aes_key_bytes = base64.b64decode(aes_key + "=")
    iv = aes_key_bytes[:16]

    cipher = AES.new(aes_key_bytes, AES.MODE_CBC, iv)
    encrypted = base64.b64decode(encrypt_str)
    decrypted = cipher.decrypt(encrypted)

    # 去除 PKCS#7 填充
    pad = decrypted[-1]
    content = decrypted[:-pad]

    # 格式: 16bytes_random + 4bytes_msg_len + msg + app_key
    msg_len = int.from_bytes(content[16:20], byteorder="big")
    msg = content[20 : 20 + msg_len].decode("utf-8")

    return json.loads(msg)


def _dingtalk_encrypt(
    plaintext: str,
    token: str,
    aes_key: str,
    app_key: str,
) -> dict:
    """钉钉回调响应加密"""
    import base64
    import os
    import time

    from Crypto.Cipher import AES

    aes_key_bytes = base64.b64decode(aes_key + "=")
    iv = aes_key_bytes[:16]

    msg = plaintext.encode("utf-8")
    random_bytes = os.urandom(16)
    msg_len = len(msg).to_bytes(4, byteorder="big")
    content = random_bytes + msg_len + msg + app_key.encode("utf-8")

    # PKCS#7 填充
    pad_len = 32 - (len(content) % 32)
    content += bytes([pad_len] * pad_len)

    cipher = AES.new(aes_key_bytes, AES.MODE_CBC, iv)
    encrypted = base64.b64encode(cipher.encrypt(content)).decode("utf-8")

    timestamp = str(int(time.time()))
    nonce = hashlib.md5(os.urandom(16)).hexdigest()[:8]

    # 签名
    sign_list = sorted([token, timestamp, nonce, encrypted])
    sign = hashlib.sha1("".join(sign_list).encode("utf-8")).hexdigest()

    return {
        "msg_signature": sign,
        "timeStamp": timestamp,
        "nonce": nonce,
        "encrypt": encrypted,
    }
