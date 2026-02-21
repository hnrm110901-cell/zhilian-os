"""
飞书消息服务
Feishu Message Service

提供飞书消息推送功能，支持文本、卡片、富文本等多种消息类型
"""
import httpx
import structlog
from typing import Dict, Any, Optional, List
from ..core.config import settings

logger = structlog.get_logger()


class FeishuMessageService:
    """飞书消息服务"""

    def __init__(self):
        self._cache_key_tenant = "feishu:tenant_access_token"
        self._cache_key_app = "feishu:app_access_token"

    async def get_tenant_access_token(self) -> str:
        """
        获取tenant_access_token（使用Redis缓存）

        tenant_access_token用于访问企业资源
        """
        from .redis_cache_service import redis_cache

        # 尝试从缓存获取
        cached_token = await redis_cache.get(self._cache_key_tenant)
        if cached_token:
            logger.debug("从缓存获取飞书tenant_access_token")
            return cached_token

        # 获取新token
        token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_url,
                json={
                    "app_id": settings.FEISHU_APP_ID,
                    "app_secret": settings.FEISHU_APP_SECRET,
                },
                timeout=30.0
            )
            data = response.json()

            if data.get("code") != 0:
                raise Exception(f"获取tenant_access_token失败: {data.get('msg')}")

            tenant_access_token = data["tenant_access_token"]
            expire = data.get("expire", 7200)

            # 缓存token，提前5分钟过期
            await redis_cache.set(
                self._cache_key_tenant,
                tenant_access_token,
                expire=expire - 300
            )

            logger.info("飞书tenant_access_token获取成功并已缓存", expire=expire)
            return tenant_access_token

    async def send_text_message(
        self,
        receive_id: str,
        content: str,
        receive_id_type: str = "open_id"
    ) -> Dict[str, Any]:
        """
        发送文本消息

        Args:
            receive_id: 接收者ID（open_id, user_id, union_id, email, chat_id）
            content: 消息内容
            receive_id_type: 接收者ID类型

        Returns:
            发送结果
        """
        try:
            tenant_access_token = await self.get_tenant_access_token()

            send_url = "https://open.feishu.cn/open-apis/im/v1/messages"
            headers = {
                "Authorization": f"Bearer {tenant_access_token}",
                "Content-Type": "application/json"
            }

            message_data = {
                "receive_id": receive_id,
                "msg_type": "text",
                "content": f'{{"text":"{content}"}}'
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    send_url,
                    headers=headers,
                    json=message_data,
                    params={"receive_id_type": receive_id_type},
                    timeout=30.0
                )
                result = response.json()

                if result.get("code") == 0:
                    logger.info(
                        "飞书文本消息发送成功",
                        receive_id=receive_id,
                        message_id=result.get("data", {}).get("message_id")
                    )
                    return {
                        "success": True,
                        "message_id": result.get("data", {}).get("message_id")
                    }
                else:
                    logger.error(
                        "飞书消息发送失败",
                        error=result.get("msg"),
                        code=result.get("code")
                    )
                    return {
                        "success": False,
                        "error": result.get("msg"),
                        "code": result.get("code")
                    }

        except Exception as e:
            logger.error("飞书消息发送异常", error=str(e), exc_info=e)
            return {
                "success": False,
                "error": str(e)
            }

    async def send_rich_text_message(
        self,
        receive_id: str,
        title: str,
        content: List[List[Dict]],
        receive_id_type: str = "open_id"
    ) -> Dict[str, Any]:
        """
        发送富文本消息

        Args:
            receive_id: 接收者ID
            title: 消息标题
            content: 富文本内容（二维数组）
            receive_id_type: 接收者ID类型

        Returns:
            发送结果

        Example:
            content = [
                [{"tag": "text", "text": "第一行文本"}],
                [{"tag": "text", "text": "第二行"}, {"tag": "a", "text": "链接", "href": "http://example.com"}]
            ]
        """
        try:
            tenant_access_token = await self.get_tenant_access_token()

            send_url = "https://open.feishu.cn/open-apis/im/v1/messages"
            headers = {
                "Authorization": f"Bearer {tenant_access_token}",
                "Content-Type": "application/json"
            }

            import json
            rich_text_content = {
                "zh_cn": {
                    "title": title,
                    "content": content
                }
            }

            message_data = {
                "receive_id": receive_id,
                "msg_type": "post",
                "content": json.dumps(rich_text_content)
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    send_url,
                    headers=headers,
                    json=message_data,
                    params={"receive_id_type": receive_id_type},
                    timeout=30.0
                )
                result = response.json()

                if result.get("code") == 0:
                    logger.info("飞书富文本消息发送成功", receive_id=receive_id)
                    return {
                        "success": True,
                        "message_id": result.get("data", {}).get("message_id")
                    }
                else:
                    logger.error(
                        "飞书富文本消息发送失败",
                        error=result.get("msg")
                    )
                    return {
                        "success": False,
                        "error": result.get("msg")
                    }

        except Exception as e:
            logger.error("飞书富文本消息发送异常", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

    async def send_card_message(
        self,
        receive_id: str,
        card_content: Dict[str, Any],
        receive_id_type: str = "open_id"
    ) -> Dict[str, Any]:
        """
        发送卡片消息

        Args:
            receive_id: 接收者ID
            card_content: 卡片内容（JSON格式）
            receive_id_type: 接收者ID类型

        Returns:
            发送结果

        Example:
            card_content = {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": "标题"}
                },
                "elements": [
                    {"tag": "div", "text": {"tag": "plain_text", "content": "内容"}}
                ]
            }
        """
        try:
            tenant_access_token = await self.get_tenant_access_token()

            send_url = "https://open.feishu.cn/open-apis/im/v1/messages"
            headers = {
                "Authorization": f"Bearer {tenant_access_token}",
                "Content-Type": "application/json"
            }

            import json
            message_data = {
                "receive_id": receive_id,
                "msg_type": "interactive",
                "content": json.dumps(card_content)
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    send_url,
                    headers=headers,
                    json=message_data,
                    params={"receive_id_type": receive_id_type},
                    timeout=30.0
                )
                result = response.json()

                if result.get("code") == 0:
                    logger.info("飞书卡片消息发送成功", receive_id=receive_id)
                    return {
                        "success": True,
                        "message_id": result.get("data", {}).get("message_id")
                    }
                else:
                    logger.error(
                        "飞书卡片消息发送失败",
                        error=result.get("msg")
                    )
                    return {
                        "success": False,
                        "error": result.get("msg")
                    }

        except Exception as e:
            logger.error("飞书卡片消息发送异常", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

    async def send_notification_card(
        self,
        receive_id: str,
        title: str,
        content: str,
        url: Optional[str] = None,
        receive_id_type: str = "open_id"
    ) -> Dict[str, Any]:
        """
        发送通知卡片（简化版）

        Args:
            receive_id: 接收者ID
            title: 通知标题
            content: 通知内容
            url: 点击跳转链接（可选）
            receive_id_type: 接收者ID类型

        Returns:
            发送结果
        """
        card_content = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                },
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": content
                    }
                }
            ]
        }

        # 如果有URL，添加按钮
        if url:
            card_content["elements"].append({
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "查看详情"
                        },
                        "type": "primary",
                        "url": url
                    }
                ]
            })

        return await self.send_card_message(receive_id, card_content, receive_id_type)

    async def send_group_message(
        self,
        chat_id: str,
        content: str,
        msg_type: str = "text"
    ) -> Dict[str, Any]:
        """
        发送群组消息

        Args:
            chat_id: 群组ID
            content: 消息内容
            msg_type: 消息类型（text, post, interactive）

        Returns:
            发送结果
        """
        return await self.send_text_message(
            receive_id=chat_id,
            content=content,
            receive_id_type="chat_id"
        )


# 创建全局实例
feishu_message_service = FeishuMessageService()
