"""
飞书服务
Feishu (Lark) Service for message sending and user management
"""
from typing import Dict, Any, List, Optional
import httpx
import structlog
from datetime import datetime, timedelta

from ..core.config import settings

logger = structlog.get_logger()


class FeishuService:
    """飞书服务"""

    def __init__(self):
        self.app_id = settings.FEISHU_APP_ID
        self.app_secret = settings.FEISHU_APP_SECRET
        self.tenant_access_token: Optional[str] = None
        self.token_expire_time: Optional[datetime] = None
        self.base_url = "https://open.feishu.cn/open-apis"

    async def get_tenant_access_token(self) -> str:
        """获取tenant_access_token"""
        # 检查token是否有效
        if self.tenant_access_token and self.token_expire_time:
            if datetime.now() < self.token_expire_time:
                return self.tenant_access_token

        # 获取新token
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/auth/v3/tenant_access_token/internal",
                    json={
                        "app_id": self.app_id,
                        "app_secret": self.app_secret,
                    },
                    timeout=30.0,
                )
                data = response.json()

                if data.get("code") == 0:
                    self.tenant_access_token = data["tenant_access_token"]
                    # token有效期约2小时，提前5分钟刷新
                    expire_seconds = data.get("expire", 7200)
                    self.token_expire_time = datetime.now() + timedelta(
                        seconds=expire_seconds - 300
                    )
                    logger.info("飞书tenant_access_token获取成功")
                    return self.tenant_access_token
                else:
                    logger.error("飞书tenant_access_token获取失败", error=data)
                    raise Exception(f"获取tenant_access_token失败: {data.get('msg')}")

        except Exception as e:
            logger.error("飞书API调用失败", error=str(e))
            raise

    async def send_text_message(
        self,
        content: str,
        receive_id: str,
        receive_id_type: str = "user_id",
    ) -> Dict[str, Any]:
        """
        发送文本消息

        Args:
            content: 消息内容
            receive_id: 接收者ID
            receive_id_type: ID类型 (user_id, chat_id, open_id, union_id)
        """
        token = await self.get_tenant_access_token()

        message_data = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": '{"text":"' + content + '"}',
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/im/v1/messages",
                    params={"receive_id_type": receive_id_type},
                    headers={"Authorization": f"Bearer {token}"},
                    json=message_data,
                    timeout=30.0,
                )
                result = response.json()

                if result.get("code") == 0:
                    logger.info("飞书消息发送成功", message_id=result.get("data", {}).get("message_id"))
                    return result
                else:
                    logger.error("飞书消息发送失败", error=result)
                    raise Exception(f"发送消息失败: {result.get('msg')}")

        except Exception as e:
            logger.error("飞书消息发送异常", error=str(e))
            raise

    async def send_post_message(
        self,
        title: str,
        content: List[List[Dict[str, Any]]],
        receive_id: str,
        receive_id_type: str = "user_id",
    ) -> Dict[str, Any]:
        """
        发送富文本消息

        Args:
            title: 标题
            content: 富文本内容
            receive_id: 接收者ID
            receive_id_type: ID类型
        """
        token = await self.get_tenant_access_token()

        post_content = {
            "zh_cn": {
                "title": title,
                "content": content,
            }
        }

        message_data = {
            "receive_id": receive_id,
            "msg_type": "post",
            "content": str(post_content).replace("'", '"'),
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/im/v1/messages",
                    params={"receive_id_type": receive_id_type},
                    headers={"Authorization": f"Bearer {token}"},
                    json=message_data,
                    timeout=30.0,
                )
                result = response.json()

                if result.get("code") == 0:
                    logger.info("飞书富文本消息发送成功")
                    return result
                else:
                    logger.error("飞书富文本消息发送失败", error=result)
                    raise Exception(f"发送消息失败: {result.get('msg')}")

        except Exception as e:
            logger.error("飞书消息发送异常", error=str(e))
            raise

    async def send_interactive_card(
        self,
        card_content: Dict[str, Any],
        receive_id: str,
        receive_id_type: str = "user_id",
    ) -> Dict[str, Any]:
        """
        发送交互式卡片消息

        Args:
            card_content: 卡片内容
            receive_id: 接收者ID
            receive_id_type: ID类型
        """
        token = await self.get_tenant_access_token()

        message_data = {
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": str(card_content).replace("'", '"'),
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/im/v1/messages",
                    params={"receive_id_type": receive_id_type},
                    headers={"Authorization": f"Bearer {token}"},
                    json=message_data,
                    timeout=30.0,
                )
                result = response.json()

                if result.get("code") == 0:
                    logger.info("飞书卡片消息发送成功")
                    return result
                else:
                    logger.error("飞书卡片消息发送失败", error=result)
                    raise Exception(f"发送消息失败: {result.get('msg')}")

        except Exception as e:
            logger.error("飞书消息发送异常", error=str(e))
            raise

    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户信息

        Args:
            user_id: 用户ID
        """
        token = await self.get_tenant_access_token()

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/contact/v3/users/{user_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30.0,
                )
                result = response.json()

                if result.get("code") == 0:
                    logger.info("获取用户信息成功", user_id=user_id)
                    return result.get("data", {}).get("user", {})
                else:
                    logger.error("获取用户信息失败", error=result)
                    raise Exception(f"获取用户信息失败: {result.get('msg')}")

        except Exception as e:
            logger.error("获取用户信息异常", error=str(e))
            raise

    async def get_department_users(
        self, department_id: str = "0", page_size: int = 50
    ) -> List[Dict[str, Any]]:
        """
        获取部门用户列表

        Args:
            department_id: 部门ID，0表示根部门
            page_size: 分页大小
        """
        token = await self.get_tenant_access_token()

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/contact/v3/users",
                    params={
                        "department_id": department_id,
                        "page_size": page_size,
                    },
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30.0,
                )
                result = response.json()

                if result.get("code") == 0:
                    users = result.get("data", {}).get("items", [])
                    logger.info("获取部门用户列表成功", count=len(users))
                    return users
                else:
                    logger.error("获取部门用户列表失败", error=result)
                    raise Exception(f"获取部门用户列表失败: {result.get('msg')}")

        except Exception as e:
            logger.error("获取部门用户列表异常", error=str(e))
            raise

    async def handle_message(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理接收到的消息事件

        Args:
            event_data: 飞书推送的事件数据
        """
        event_type = event_data.get("header", {}).get("event_type")
        event = event_data.get("event", {})

        logger.info("收到飞书事件", event_type=event_type)

        if event_type == "im.message.receive_v1":
            # 处理接收消息事件
            message = event.get("message", {})
            msg_type = message.get("message_type")
            content = message.get("content", "{}")
            sender = event.get("sender", {})

            if msg_type == "text":
                # 解析文本内容
                import json
                text_content = json.loads(content).get("text", "")
                response = await self._process_text_message(
                    sender.get("sender_id", {}).get("user_id", ""),
                    text_content
                )
                return response

        return {}

    async def _process_text_message(self, user_id: str, content: str) -> Dict[str, Any]:
        """处理文本消息，调用Agent"""
        from .message_router import message_router
        from .agent_service import AgentService

        # 使用消息路由器识别意图
        agent_type, action, params = message_router.route_message(content, user_id)

        if not agent_type:
            # 无法识别意图，返回帮助信息
            return {
                "type": "text",
                "content": f"收到您的消息：{content}\n\n我可以帮您：\n1. 查询和管理排班\n2. 处理订单相关事务\n3. 查询库存和申请补货\n4. 查看培训课程\n5. 获取经营数据分析\n6. 服务质量监控\n7. 预定宴会管理\n\n请告诉我您需要什么帮助？",
            }

        try:
            # 调用Agent服务执行
            agent_service = AgentService()
            result = await agent_service.execute_agent(
                agent_type,
                {
                    "action": action,
                    "params": params,
                }
            )

            # 格式化响应
            response_text = message_router.format_agent_response(agent_type, action, result)

            return {
                "type": "text",
                "content": response_text,
            }

        except Exception as e:
            logger.error("Agent执行失败", agent_type=agent_type, action=action, error=str(e))
            return {
                "type": "text",
                "content": f"❌ 处理失败：{str(e)}\n\n请稍后重试或联系管理员。",
            }

    def is_configured(self) -> bool:
        """检查是否已配置"""
        return bool(self.app_id and self.app_secret)


# 创建全局实例
feishu_service = FeishuService()
