"""
企业微信消息服务
WeChat Work Message Service
"""
import httpx
import structlog
from typing import Dict, Any, Optional
from ..core.config import settings

logger = structlog.get_logger()


class WeChatWorkMessageService:
    """企业微信消息服务"""

    def __init__(self):
        self._cache_key = "wechat_work:access_token"

    async def get_access_token(self) -> str:
        """获取企业微信access_token（使用Redis缓存）"""
        from .redis_cache_service import redis_cache

        # 尝试从缓存获取
        cached_token = await redis_cache.get(self._cache_key)
        if cached_token:
            logger.debug("从缓存获取企业微信access_token")
            return cached_token

        # 获取新token
        token_url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
        async with httpx.AsyncClient() as client:
            response = await client.get(
                token_url,
                params={
                    "corpid": settings.WECHAT_CORP_ID,
                    "corpsecret": settings.WECHAT_CORP_SECRET,
                },
                timeout=30.0
            )
            data = response.json()

            if data.get("errcode", 0) != 0:
                raise Exception(f"获取access_token失败: {data.get('errmsg')}")

            access_token = data["access_token"]
            expires_in = data.get("expires_in", 7200)

            # 缓存token，提前5分钟过期
            await redis_cache.set(
                self._cache_key,
                access_token,
                expire=expires_in - 300
            )

            logger.info("企业微信access_token获取成功并已缓存", expires_in=expires_in)
            return access_token

    async def send_text_message(
        self,
        user_id: str,
        content: str,
        safe: int = 0
    ) -> Dict[str, Any]:
        """
        发送文本消息

        Args:
            user_id: 用户ID，多个用户用|分隔，@all表示全部用户
            content: 消息内容
            safe: 是否是保密消息，0表示可对外分享，1表示不能分享

        Returns:
            发送结果
        """
        try:
            access_token = await self.get_access_token()

            send_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
            message_data = {
                "touser": user_id,
                "msgtype": "text",
                "agentid": settings.WECHAT_AGENT_ID,
                "text": {
                    "content": content
                },
                "safe": safe
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    send_url,
                    json=message_data,
                    timeout=30.0
                )
                result = response.json()

                if result.get("errcode", 0) == 0:
                    logger.info(
                        "企业微信文本消息发送成功",
                        user_id=user_id,
                        invaliduser=result.get("invaliduser", "")
                    )
                    return {
                        "success": True,
                        "invaliduser": result.get("invaliduser", ""),
                        "invalidparty": result.get("invalidparty", ""),
                        "invalidtag": result.get("invalidtag", "")
                    }
                else:
                    logger.error(
                        "企业微信消息发送失败",
                        error=result.get("errmsg"),
                        errcode=result.get("errcode")
                    )
                    return {
                        "success": False,
                        "error": result.get("errmsg"),
                        "errcode": result.get("errcode")
                    }

        except Exception as e:
            logger.error("企业微信消息发送异常", error=str(e), exc_info=e)
            return {
                "success": False,
                "error": str(e)
            }

    async def send_markdown_message(
        self,
        user_id: str,
        content: str
    ) -> Dict[str, Any]:
        """
        发送Markdown消息

        Args:
            user_id: 用户ID
            content: Markdown格式的消息内容

        Returns:
            发送结果
        """
        try:
            access_token = await self.get_access_token()

            send_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
            message_data = {
                "touser": user_id,
                "msgtype": "markdown",
                "agentid": settings.WECHAT_AGENT_ID,
                "markdown": {
                    "content": content
                }
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    send_url,
                    json=message_data,
                    timeout=30.0
                )
                result = response.json()

                if result.get("errcode", 0) == 0:
                    logger.info("企业微信Markdown消息发送成功", user_id=user_id)
                    return {"success": True}
                else:
                    logger.error(
                        "企业微信Markdown消息发送失败",
                        error=result.get("errmsg")
                    )
                    return {
                        "success": False,
                        "error": result.get("errmsg")
                    }

        except Exception as e:
            logger.error("企业微信Markdown消息发送异常", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

    async def send_card_message(
        self,
        user_id: str,
        title: str,
        description: str,
        url: str,
        btntxt: str = "详情"
    ) -> Dict[str, Any]:
        """
        发送文本卡片消息

        Args:
            user_id: 用户ID
            title: 标题
            description: 描述
            url: 点击后跳转的链接
            btntxt: 按钮文字

        Returns:
            发送结果
        """
        try:
            access_token = await self.get_access_token()

            send_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
            message_data = {
                "touser": user_id,
                "msgtype": "textcard",
                "agentid": settings.WECHAT_AGENT_ID,
                "textcard": {
                    "title": title,
                    "description": description,
                    "url": url,
                    "btntxt": btntxt
                }
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    send_url,
                    json=message_data,
                    timeout=30.0
                )
                result = response.json()

                if result.get("errcode", 0) == 0:
                    logger.info("企业微信卡片消息发送成功", user_id=user_id)
                    return {"success": True}
                else:
                    logger.error(
                        "企业微信卡片消息发送失败",
                        error=result.get("errmsg")
                    )
                    return {
                        "success": False,
                        "error": result.get("errmsg")
                    }

        except Exception as e:
            logger.error("企业微信卡片消息发送异常", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }


# 创建全局实例
wechat_work_message_service = WeChatWorkMessageService()
