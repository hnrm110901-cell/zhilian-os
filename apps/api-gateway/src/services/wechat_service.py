"""
企业微信服务
Enterprise WeChat Service for message sending and user management

INFRA-002 增强：
- TEMPLATES 字典：标准化消息模板（discount_approval, anomaly_alert, shift_report, daily_forecast）
- send_templated_message()：统一发送方法，支持消息去重
- Redis SET 去重（TTL 24h）：防止重复发送
- 发送失败写入告警队列（Redis List）
- retry_failed_messages()：从告警队列批量重试
"""
from typing import Dict, Any, List, Optional
import json
import hashlib
import httpx
import os
import structlog
from datetime import datetime, timedelta

from ..core.config import settings

logger = structlog.get_logger()

# ==================== 消息模板 ====================
# 格式：template_name → Callable(data) → str
# data 为业务数据字典，返回格式化的消息文本

TEMPLATES: Dict[str, Any] = {
    "discount_approval": lambda data: (
        f"【折扣审批请求】\n"
        f"门店：{data.get('store_name', data.get('store_id', ''))}\n"
        f"申请人：{data.get('operator_name', data.get('operator_id', ''))}\n"
        f"折扣金额：¥{data.get('amount', 0):.2f}\n"
        f"原因：{data.get('reason', '-')}\n"
        f"订单号：{data.get('order_id', '-')}\n"
        f"申请时间：{data.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}\n"
        f"---\n请尽快审批处理"
    ),

    "anomaly_alert": lambda data: (
        f"【异常告警】\n"
        f"门店：{data.get('store_name', data.get('store_id', ''))}\n"
        f"异常类型：{data.get('anomaly_type', '未知')}\n"
        f"描述：{data.get('description', '-')}\n"
        f"严重级别：{data.get('severity', 'medium')}\n"
        f"发生时间：{data.get('occurred_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}\n"
        f"---\n请及时处理"
    ),

    "shift_report": lambda data: (
        f"【班次报表】\n"
        f"门店：{data.get('store_name', data.get('store_id', ''))}\n"
        f"班次：{data.get('shift_name', data.get('date', '今日'))}\n"
        f"营收：¥{data.get('revenue', 0):.2f}\n"
        f"订单数：{data.get('order_count', 0)}\n"
        f"客流量：{data.get('customer_count', 0)}\n"
        f"平均客单价：¥{data.get('avg_order_value', 0):.2f}\n"
        f"---\n班次已结束，数据已汇总"
    ),

    "daily_forecast": lambda data: (
        f"【备料建议】明日 {data.get('target_date', '')}\n"
        f"门店：{data.get('store_name', data.get('store_id', ''))}\n"
        + (f"⚠️ {data.get('note', '')}\n" if data.get('note') else "")
        + f"预估营收：¥{data.get('estimated_revenue', 0):.0f}\n"
        f"置信度：{data.get('confidence', 'low')}\n"
        f"预测依据：{data.get('basis', 'rule_based')}\n"
        f"---\n建议提前备料"
    ),
}

# Redis Keys
DEDUP_KEY_PREFIX = "wechat_dedup:"
FAILED_MSG_QUEUE_KEY = "wechat_failed_messages"


class WeChatService:
    """企业微信服务"""

    def __init__(self, redis_client=None):
        self.corp_id = settings.WECHAT_CORP_ID
        self.corp_secret = settings.WECHAT_CORP_SECRET
        self.agent_id = settings.WECHAT_AGENT_ID
        self.access_token: Optional[str] = None
        self.token_expire_time: Optional[datetime] = None
        self.base_url = "https://qyapi.weixin.qq.com/cgi-bin"
        self._redis = redis_client

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

    # ==================== INFRA-002: 标准化消息接口 ====================

    async def send_templated_message(
        self,
        template: str,
        data: Dict[str, Any],
        to_user_id: str,
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        使用模板发送标准化企微消息

        Args:
            template: 模板名称（discount_approval/anomaly_alert/shift_report/daily_forecast）
            data: 业务数据字典
            to_user_id: 接收人 user_id
            message_id: 消息去重ID（None 时自动生成）

        Returns:
            发送结果字典
        """
        if template not in TEMPLATES:
            raise ValueError(
                f"未知模板: '{template}'。可用模板: {list(TEMPLATES.keys())}"
            )

        # 生成去重 ID
        if not message_id:
            message_id = hashlib.md5(
                f"{template}:{to_user_id}:{json.dumps(data, sort_keys=True, default=str)}".encode()
            ).hexdigest()

        # Redis 去重检查（TTL 24h）
        if await self._is_duplicate(message_id):
            logger.info(
                "wechat.send_templated.duplicate_skipped",
                template=template,
                message_id=message_id,
                to_user_id=to_user_id,
            )
            return {"status": "skipped", "reason": "duplicate", "message_id": message_id}

        # 渲染消息内容
        content = TEMPLATES[template](data)

        try:
            result = await self.send_text_message(content=content, touser=to_user_id)
            # 记录去重标记
            await self._mark_sent(message_id)
            logger.info(
                "wechat.send_templated.success",
                template=template,
                to_user_id=to_user_id,
                message_id=message_id,
            )
            return {"status": "sent", "message_id": message_id, "result": result}

        except Exception as e:
            logger.error(
                "wechat.send_templated.failed",
                template=template,
                to_user_id=to_user_id,
                error=str(e),
            )
            # 发送失败写入告警队列（Redis List）
            await self._enqueue_failed_message(
                template=template,
                data=data,
                to_user_id=to_user_id,
                message_id=message_id,
                error=str(e),
            )
            return {"status": "failed", "message_id": message_id, "error": str(e)}

    async def retry_failed_messages(
        self,
        max_retries: int = 3,
        batch_size: int = 10,
    ) -> Dict[str, int]:
        """
        从告警队列批量重试失败的消息

        Args:
            max_retries: 每条消息最大重试次数
            batch_size: 单次处理批量大小

        Returns:
            {"retried": int, "succeeded": int}
        """
        if not self._redis:
            return {"retried": 0, "succeeded": 0}

        retried = 0
        succeeded = 0

        for _ in range(batch_size):
            try:
                raw = await self._redis.lpop(FAILED_MSG_QUEUE_KEY)
                if not raw:
                    break

                msg = json.loads(raw)
                retry_count = msg.get("retry_count", 0)

                if retry_count >= max_retries:
                    logger.warning(
                        "wechat.retry.max_retries_exceeded",
                        message_id=msg.get("message_id"),
                    )
                    continue

                retried += 1
                msg["retry_count"] = retry_count + 1

                try:
                    result = await self.send_templated_message(
                        template=msg["template"],
                        data=msg["data"],
                        to_user_id=msg["to_user_id"],
                        message_id=msg["message_id"],
                    )
                    if result.get("status") in ("sent", "skipped"):
                        succeeded += 1
                    else:
                        # 仍然失败，重新入队
                        await self._redis.rpush(FAILED_MSG_QUEUE_KEY, json.dumps(msg, default=str))
                except Exception as e:
                    logger.error("wechat.retry.failed", error=str(e))
                    await self._redis.rpush(FAILED_MSG_QUEUE_KEY, json.dumps(msg, default=str))

            except Exception as e:
                logger.warning("wechat.retry.queue_error", error=str(e))
                break

        logger.info("wechat.retry.done", retried=retried, succeeded=succeeded)
        return {"retried": retried, "succeeded": succeeded}

    async def _is_duplicate(self, message_id: str) -> bool:
        """检查消息是否已发送（Redis SET 去重）"""
        if not self._redis:
            return False
        try:
            key = f"{DEDUP_KEY_PREFIX}{message_id}"
            return bool(await self._redis.exists(key))
        except Exception:
            return False

    async def _mark_sent(self, message_id: str, ttl: int = 86400) -> None:
        """标记消息已发送（TTL 24h）"""
        if not self._redis:
            return
        try:
            key = f"{DEDUP_KEY_PREFIX}{message_id}"
            await self._redis.set(key, "1", ex=ttl)
        except Exception as e:
            logger.warning("wechat.mark_sent.failed", message_id=message_id, error=str(e))

    async def _enqueue_failed_message(
        self,
        template: str,
        data: Dict[str, Any],
        to_user_id: str,
        message_id: str,
        error: str,
    ) -> None:
        """将失败消息写入告警队列"""
        if not self._redis:
            return
        try:
            msg = {
                "template": template,
                "data": data,
                "to_user_id": to_user_id,
                "message_id": message_id,
                "error": error,
                "retry_count": 0,
                "enqueued_at": datetime.utcnow().isoformat(),
            }
            await self._redis.rpush(FAILED_MSG_QUEUE_KEY, json.dumps(msg, default=str))
            logger.info("wechat.failed_message_enqueued", message_id=message_id)
        except Exception as e:
            logger.error("wechat.enqueue_failed.error", error=str(e))


# 创建全局实例
wechat_service = WeChatService()
