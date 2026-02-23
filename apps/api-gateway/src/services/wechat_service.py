"""
企业微信服务
Enterprise WeChat Service for message sending and user management
"""
from typing import Dict, Any, List, Optional
import httpx
import os
import structlog
from datetime import datetime, timedelta

from ..core.config import settings

logger = structlog.get_logger()


class WeChatService:
    """企业微信服务"""

    def __init__(self):
        self.corp_id = settings.WECHAT_CORP_ID
        self.corp_secret = settings.WECHAT_CORP_SECRET
        self.agent_id = settings.WECHAT_AGENT_ID
        self.access_token: Optional[str] = None
        self.token_expire_time: Optional[datetime] = None
        self.base_url = "https://qyapi.weixin.qq.com/cgi-bin"

    async def get_access_token(self) -> str:
        """获取企业微信access_token"""
        # 检查token是否有效
        if self.access_token and self.token_expire_time:
            if datetime.now() < self.token_expire_time:
                return self.access_token

        # 获取新token
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/gettoken",
                    params={
                        "corpid": self.corp_id,
                        "corpsecret": self.corp_secret,
                    },
                    timeout=float(os.getenv("WECHAT_HTTP_TIMEOUT", "30.0")),
                )
                data = response.json()

                if data.get("errcode") == 0:
                    self.access_token = data["access_token"]
                    # token有效期7200秒，提前N秒刷新
                    _token_ttl = int(os.getenv("WECHAT_TOKEN_TTL", "7200"))
                    _token_refresh_buffer = int(os.getenv("WECHAT_TOKEN_REFRESH_BUFFER", "300"))
                    self.token_expire_time = datetime.now() + timedelta(seconds=_token_ttl - _token_refresh_buffer)
                    logger.info("企业微信access_token获取成功")
                    return self.access_token
                else:
                    logger.error("企业微信access_token获取失败", error=data)
                    raise Exception(f"获取access_token失败: {data.get('errmsg')}")

        except Exception as e:
            logger.error("企业微信API调用失败", error=str(e))
            raise

    async def send_text_message(
        self,
        content: str,
        touser: Optional[str] = None,
        toparty: Optional[str] = None,
        totag: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        发送文本消息

        Args:
            content: 消息内容
            touser: 成员ID列表（多个用|分隔），@all表示全部成员
            toparty: 部门ID列表（多个用|分隔）
            totag: 标签ID列表（多个用|分隔）
        """
        token = await self.get_access_token()

        message_data = {
            "touser": touser or "@all",
            "toparty": toparty or "",
            "totag": totag or "",
            "msgtype": "text",
            "agentid": self.agent_id,
            "text": {"content": content},
            "safe": 0,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/message/send",
                    params={"access_token": token},
                    json=message_data,
                    timeout=float(os.getenv("WECHAT_HTTP_TIMEOUT", "30.0")),
                )
                result = response.json()

                if result.get("errcode") == 0:
                    logger.info("企业微信消息发送成功", invaliduser=result.get("invaliduser"))
                    return result
                else:
                    logger.error("企业微信消息发送失败", error=result)
                    raise Exception(f"发送消息失败: {result.get('errmsg')}")

        except Exception as e:
            logger.error("企业微信消息发送异常", error=str(e))
            raise

    async def send_markdown_message(
        self,
        content: str,
        touser: Optional[str] = None,
        toparty: Optional[str] = None,
        totag: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        发送Markdown消息

        Args:
            content: Markdown格式的消息内容
            touser: 成员ID列表
            toparty: 部门ID列表
            totag: 标签ID列表
        """
        token = await self.get_access_token()

        message_data = {
            "touser": touser or "@all",
            "toparty": toparty or "",
            "totag": totag or "",
            "msgtype": "markdown",
            "agentid": self.agent_id,
            "markdown": {"content": content},
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/message/send",
                    params={"access_token": token},
                    json=message_data,
                    timeout=float(os.getenv("WECHAT_HTTP_TIMEOUT", "30.0")),
                )
                result = response.json()

                if result.get("errcode") == 0:
                    logger.info("企业微信Markdown消息发送成功")
                    return result
                else:
                    logger.error("企业微信Markdown消息发送失败", error=result)
                    raise Exception(f"发送消息失败: {result.get('errmsg')}")

        except Exception as e:
            logger.error("企业微信消息发送异常", error=str(e))
            raise

    async def send_card_message(
        self,
        title: str,
        description: str,
        url: str,
        btntxt: str = "详情",
        touser: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        发送文本卡片消息

        Args:
            title: 标题
            description: 描述
            url: 点击后跳转的链接
            btntxt: 按钮文字
            touser: 成员ID列表
        """
        token = await self.get_access_token()

        message_data = {
            "touser": touser or "@all",
            "msgtype": "textcard",
            "agentid": self.agent_id,
            "textcard": {
                "title": title,
                "description": description,
                "url": url,
                "btntxt": btntxt,
            },
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/message/send",
                    params={"access_token": token},
                    json=message_data,
                    timeout=float(os.getenv("WECHAT_HTTP_TIMEOUT", "30.0")),
                )
                result = response.json()

                if result.get("errcode") == 0:
                    logger.info("企业微信卡片消息发送成功")
                    return result
                else:
                    logger.error("企业微信卡片消息发送失败", error=result)
                    raise Exception(f"发送消息失败: {result.get('errmsg')}")

        except Exception as e:
            logger.error("企业微信消息发送异常", error=str(e))
            raise

    async def get_user_info(self, userid: str) -> Dict[str, Any]:
        """
        获取用户详细信息

        Args:
            userid: 成员UserID
        """
        token = await self.get_access_token()

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/user/get",
                    params={"access_token": token, "userid": userid},
                    timeout=float(os.getenv("WECHAT_HTTP_TIMEOUT", "30.0")),
                )
                result = response.json()

                if result.get("errcode") == 0:
                    logger.info("获取用户信息成功", userid=userid)
                    return result
                else:
                    logger.error("获取用户信息失败", error=result)
                    raise Exception(f"获取用户信息失败: {result.get('errmsg')}")

        except Exception as e:
            logger.error("获取用户信息异常", error=str(e))
            raise

    async def get_department_users(self, department_id: int = 1) -> List[Dict[str, Any]]:
        """
        获取部门成员列表

        Args:
            department_id: 部门ID，默认为根部门
        """
        token = await self.get_access_token()

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/user/simplelist",
                    params={
                        "access_token": token,
                        "department_id": department_id,
                        "fetch_child": 1,
                    },
                    timeout=float(os.getenv("WECHAT_HTTP_TIMEOUT", "30.0")),
                )
                result = response.json()

                if result.get("errcode") == 0:
                    logger.info("获取部门成员列表成功", count=len(result.get("userlist", [])))
                    return result.get("userlist", [])
                else:
                    logger.error("获取部门成员列表失败", error=result)
                    raise Exception(f"获取部门成员列表失败: {result.get('errmsg')}")

        except Exception as e:
            logger.error("获取部门成员列表异常", error=str(e))
            raise

    async def handle_message(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理接收到的消息

        Args:
            message_data: 企业微信推送的消息数据
        """
        msg_type = message_data.get("MsgType")
        from_user = message_data.get("FromUserName")
        content = message_data.get("Content", "")

        logger.info("收到企业微信消息", msg_type=msg_type, from_user=from_user)

        # 根据消息类型处理
        if msg_type == "text":
            # 调用Agent处理文本消息
            response = await self._process_text_message(from_user, content)
            return response
        elif msg_type == "event":
            # 处理事件消息
            event = message_data.get("Event")
            return await self._process_event(event, message_data)
        else:
            return {"type": "text", "content": "暂不支持该消息类型"}

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

    async def _process_event(self, event: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理事件消息"""
        if event == "subscribe":
            return {
                "type": "text",
                "content": "欢迎使用智链OS！\n\n我是您的智能助手，可以帮您：\n✅ 智能排班管理\n✅ 订单协同处理\n✅ 库存预警提醒\n✅ 服务质量监控\n✅ 培训辅导支持\n✅ 决策数据分析\n✅ 预定宴会管理\n\n发送关键词即可开始使用！",
            }
        elif event == "unsubscribe":
            logger.info("用户取消关注", data=data)
            return {}
        else:
            return {"type": "text", "content": "收到事件通知"}

    def is_configured(self) -> bool:
        """检查是否已配置"""
        return bool(self.corp_id and self.corp_secret and self.agent_id)


# 创建全局实例
wechat_service = WeChatService()
