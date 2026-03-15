"""
钉钉消息服务
DingTalk Message Service for message sending and user management

功能对齐企微 WeChatService：
- 文本/Markdown/ActionCard 消息推送
- Redis 去重（TTL 24h）
- 发送失败写入告警队列（Redis List）
- retry_failed_messages() 批量重试
- send_decision_card() 决策型卡片推送
- send_templated_message() 标准化模板消息
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

TEMPLATES: Dict[str, Any] = {
    "discount_approval": lambda data: (
        f"### 折扣审批请求\n\n"
        f"**门店**：{data.get('store_name', data.get('store_id', ''))}\n\n"
        f"**申请人**：{data.get('operator_name', data.get('operator_id', ''))}\n\n"
        f"**折扣金额**：¥{data.get('amount', 0):.2f}\n\n"
        f"**原因**：{data.get('reason', '-')}\n\n"
        f"**订单号**：{data.get('order_id', '-')}\n\n"
        f"---\n\n请尽快审批处理"
    ),

    "anomaly_alert": lambda data: (
        f"### 异常告警\n\n"
        f"**门店**：{data.get('store_name', data.get('store_id', ''))}\n\n"
        f"**异常类型**：{data.get('anomaly_type', '未知')}\n\n"
        f"**描述**：{data.get('description', '-')}\n\n"
        f"**严重级别**：{data.get('severity', 'medium')}\n\n"
        f"---\n\n请及时处理"
    ),

    "shift_report": lambda data: (
        f"### 班次报表\n\n"
        f"**门店**：{data.get('store_name', data.get('store_id', ''))}\n\n"
        f"**班次**：{data.get('shift_name', data.get('date', '今日'))}\n\n"
        f"**营收**：¥{data.get('revenue', 0):.2f}\n\n"
        f"**订单数**：{data.get('order_count', 0)}\n\n"
        f"**客流量**：{data.get('customer_count', 0)}\n\n"
        f"---\n\n班次已结束，数据已汇总"
    ),

    "daily_forecast": lambda data: (
        f"### 备料建议 — 明日 {data.get('target_date', '')}\n\n"
        f"**门店**：{data.get('store_name', data.get('store_id', ''))}\n\n"
        + (f"> ⚠️ {data.get('note', '')}\n\n" if data.get('note') else "")
        + f"**预估营收**：¥{data.get('estimated_revenue', 0):.0f}\n\n"
        f"**置信度**：{data.get('confidence', 'low')}\n\n"
        f"---\n\n建议提前备料"
    ),
}

# Redis Keys
DEDUP_KEY_PREFIX = "dingtalk_dedup:"
FAILED_MSG_QUEUE_KEY = "dingtalk_failed_messages"


class DingTalkService:
    """钉钉消息服务"""

    def __init__(self, redis_client=None):
        self.app_key = settings.DINGTALK_APP_KEY
        self.app_secret = settings.DINGTALK_APP_SECRET
        self.agent_id: Optional[str] = None
        self.access_token: Optional[str] = None
        self.token_expire_time: Optional[datetime] = None
        self.base_url = "https://oapi.dingtalk.com"
        self._redis = redis_client

    def configure(
        self,
        app_key: Optional[str] = None,
        app_secret: Optional[str] = None,
        agent_id: Optional[str] = None,
    ):
        """用品牌级配置覆盖全局设置"""
        if app_key:
            self.app_key = app_key
        if app_secret:
            self.app_secret = app_secret
        if agent_id:
            self.agent_id = agent_id
        # 清空缓存 token
        self.access_token = None
        self.token_expire_time = None

    async def get_access_token(self) -> str:
        """获取钉钉access_token"""
        if self.access_token and self.token_expire_time:
            if datetime.now() < self.token_expire_time:
                return self.access_token

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/gettoken",
                    params={
                        "appkey": self.app_key,
                        "appsecret": self.app_secret,
                    },
                    timeout=float(os.getenv("DINGTALK_HTTP_TIMEOUT", "30.0")),
                )
                data = response.json()

                if data.get("errcode") == 0:
                    self.access_token = data["access_token"]
                    _token_ttl = int(os.getenv("DINGTALK_TOKEN_TTL", "7200"))
                    _refresh_buffer = int(os.getenv("DINGTALK_TOKEN_REFRESH_BUFFER", "300"))
                    self.token_expire_time = datetime.now() + timedelta(
                        seconds=_token_ttl - _refresh_buffer
                    )
                    logger.info("钉钉access_token获取成功")
                    return self.access_token
                else:
                    logger.error("钉钉access_token获取失败", error=data)
                    raise Exception(f"获取access_token失败: {data.get('errmsg')}")

        except Exception as e:
            logger.error("钉钉API调用失败", error=str(e))
            raise

    async def send_text_message(
        self,
        content: str,
        userid_list: Optional[List[str]] = None,
        dept_id_list: Optional[List[int]] = None,
        to_all_user: bool = False,
    ) -> Dict[str, Any]:
        """
        发送文本工作通知

        Args:
            content: 消息内容
            userid_list: 接收人userid列表（最多100人）
            dept_id_list: 接收部门列表
            to_all_user: 是否发送给全员
        """
        token = await self.get_access_token()

        message_data: Dict[str, Any] = {
            "agent_id": self.agent_id or "",
            "msg": {
                "msgtype": "text",
                "text": {"content": content},
            },
        }

        if to_all_user:
            message_data["to_all_user"] = True
        elif userid_list:
            message_data["userid_list"] = ",".join(userid_list)
        elif dept_id_list:
            message_data["dept_id_list"] = ",".join(str(d) for d in dept_id_list)
        else:
            message_data["to_all_user"] = True

        return await self._send_work_notification(token, message_data)

    async def send_markdown_message(
        self,
        title: str,
        content: str,
        userid_list: Optional[List[str]] = None,
        dept_id_list: Optional[List[int]] = None,
        to_all_user: bool = False,
    ) -> Dict[str, Any]:
        """
        发送Markdown工作通知

        Args:
            title: 消息标题
            content: Markdown格式的消息内容
            userid_list: 接收人userid列表
            dept_id_list: 接收部门列表
            to_all_user: 是否发送给全员
        """
        token = await self.get_access_token()

        message_data: Dict[str, Any] = {
            "agent_id": self.agent_id or "",
            "msg": {
                "msgtype": "markdown",
                "markdown": {"title": title, "text": content},
            },
        }

        if to_all_user:
            message_data["to_all_user"] = True
        elif userid_list:
            message_data["userid_list"] = ",".join(userid_list)
        elif dept_id_list:
            message_data["dept_id_list"] = ",".join(str(d) for d in dept_id_list)
        else:
            message_data["to_all_user"] = True

        return await self._send_work_notification(token, message_data)

    async def send_action_card(
        self,
        title: str,
        markdown: str,
        single_title: str = "查看详情",
        single_url: str = "",
        userid_list: Optional[List[str]] = None,
        to_all_user: bool = False,
    ) -> Dict[str, Any]:
        """
        发送ActionCard工作通知（整体跳转型）

        Args:
            title: 卡片标题
            markdown: 卡片内容（Markdown格式）
            single_title: 按钮文字
            single_url: 按钮跳转URL
            userid_list: 接收人userid列表
            to_all_user: 是否发送给全员
        """
        token = await self.get_access_token()

        message_data: Dict[str, Any] = {
            "agent_id": self.agent_id or "",
            "msg": {
                "msgtype": "action_card",
                "action_card": {
                    "title": title,
                    "markdown": markdown,
                    "single_title": single_title,
                    "single_url": single_url,
                },
            },
        }

        if to_all_user:
            message_data["to_all_user"] = True
        elif userid_list:
            message_data["userid_list"] = ",".join(userid_list)
        else:
            message_data["to_all_user"] = True

        return await self._send_work_notification(token, message_data)

    async def _send_work_notification(
        self, token: str, message_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """统一发送钉钉工作通知"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/topapi/message/corpconversation/asyncsend_v2",
                    params={"access_token": token},
                    json=message_data,
                    timeout=float(os.getenv("DINGTALK_HTTP_TIMEOUT", "30.0")),
                )
                result = response.json()

                if result.get("errcode") == 0:
                    logger.info(
                        "钉钉消息发送成功",
                        task_id=result.get("task_id"),
                    )
                    return result
                else:
                    logger.error("钉钉消息发送失败", error=result)
                    raise Exception(f"发送消息失败: {result.get('errmsg')}")

        except Exception as e:
            logger.error("钉钉消息发送异常", error=str(e))
            raise

    async def get_user_info(self, userid: str) -> Dict[str, Any]:
        """获取用户详细信息"""
        token = await self.get_access_token()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/topapi/v2/user/get",
                    params={"access_token": token},
                    json={"userid": userid},
                    timeout=float(os.getenv("DINGTALK_HTTP_TIMEOUT", "30.0")),
                )
                result = response.json()
                if result.get("errcode") == 0:
                    logger.info("获取钉钉用户信息成功", userid=userid)
                    return result.get("result", {})
                else:
                    logger.error("获取钉钉用户信息失败", error=result)
                    raise Exception(f"获取用户信息失败: {result.get('errmsg')}")
        except Exception as e:
            logger.error("获取钉钉用户信息异常", error=str(e))
            raise

    async def get_department_users(self, dept_id: int = 1) -> List[Dict[str, Any]]:
        """获取部门成员列表"""
        token = await self.get_access_token()
        members: List[Dict[str, Any]] = []
        cursor = 0

        async with httpx.AsyncClient() as client:
            while True:
                response = await client.post(
                    f"{self.base_url}/topapi/v2/user/list",
                    params={"access_token": token},
                    json={"dept_id": dept_id, "cursor": cursor, "size": 100},
                    timeout=float(os.getenv("DINGTALK_HTTP_TIMEOUT", "30.0")),
                )
                data = response.json()
                if data.get("errcode") != 0:
                    logger.error("获取钉钉部门成员失败", error=data)
                    break
                result = data.get("result", {})
                members.extend(result.get("list", []))
                if not result.get("has_more"):
                    break
                cursor = result.get("next_cursor", 0)

        logger.info("获取钉钉部门成员成功", count=len(members))
        return members

    def is_configured(self) -> bool:
        """检查是否已配置"""
        return bool(self.app_key and self.app_secret)

    # ==================== 决策型卡片推送 ====================

    async def send_decision_card(
        self,
        title: str,
        description: str,
        action_url: str,
        btntxt: str = "立即审批",
        to_user_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        发送决策型 ActionCard 消息（含¥影响+置信度+一键操作按钮）。

        带 Redis 去重保护（TTL 24h）。
        """
        if not message_id:
            message_id = hashlib.md5(
                f"decision_card:{to_user_id}:{title}:{description[:50]}".encode()
            ).hexdigest()

        if await self._is_duplicate(message_id):
            logger.info(
                "dingtalk.send_decision_card.duplicate_skipped",
                message_id=message_id,
            )
            return {"status": "skipped", "reason": "duplicate", "message_id": message_id}

        try:
            userid_list = [to_user_id] if to_user_id else None
            result = await self.send_action_card(
                title=title[:64],
                markdown=description[:512],
                single_title=btntxt[:8],
                single_url=action_url,
                userid_list=userid_list,
                to_all_user=not to_user_id,
            )
            await self._mark_sent(message_id)
            logger.info(
                "dingtalk.send_decision_card.success",
                to_user_id=to_user_id,
                message_id=message_id,
            )
            return {"status": "sent", "message_id": message_id, "result": result}

        except Exception as e:
            logger.error(
                "dingtalk.send_decision_card.failed",
                to_user_id=to_user_id,
                error=str(e),
            )
            await self._enqueue_failed_message(
                template="decision_card",
                data={
                    "title": title,
                    "description": description,
                    "action_url": action_url,
                    "btntxt": btntxt,
                },
                to_user_id=to_user_id or "@all",
                message_id=message_id,
                error=str(e),
            )
            return {"status": "failed", "message_id": message_id, "error": str(e)}

    # ==================== 标准化消息接口 ====================

    async def send_templated_message(
        self,
        template: str,
        data: Dict[str, Any],
        to_user_id: str,
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """使用模板发送标准化钉钉消息"""
        if template not in TEMPLATES:
            raise ValueError(
                f"未知模板: '{template}'。可用模板: {list(TEMPLATES.keys())}"
            )

        if not message_id:
            message_id = hashlib.md5(
                f"{template}:{to_user_id}:{json.dumps(data, sort_keys=True, default=str)}".encode()
            ).hexdigest()

        if await self._is_duplicate(message_id):
            logger.info(
                "dingtalk.send_templated.duplicate_skipped",
                template=template,
                message_id=message_id,
            )
            return {"status": "skipped", "reason": "duplicate", "message_id": message_id}

        content = TEMPLATES[template](data)

        try:
            result = await self.send_markdown_message(
                title=template,
                content=content,
                userid_list=[to_user_id],
            )
            await self._mark_sent(message_id)
            logger.info(
                "dingtalk.send_templated.success",
                template=template,
                to_user_id=to_user_id,
                message_id=message_id,
            )
            return {"status": "sent", "message_id": message_id, "result": result}

        except Exception as e:
            logger.error(
                "dingtalk.send_templated.failed",
                template=template,
                to_user_id=to_user_id,
                error=str(e),
            )
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
        """从告警队列批量重试失败的消息"""
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
                        "dingtalk.retry.max_retries_exceeded",
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
                        await self._redis.rpush(
                            FAILED_MSG_QUEUE_KEY, json.dumps(msg, default=str)
                        )
                except Exception as e:
                    logger.error("dingtalk.retry.failed", error=str(e))
                    await self._redis.rpush(
                        FAILED_MSG_QUEUE_KEY, json.dumps(msg, default=str)
                    )

            except Exception as e:
                logger.warning("dingtalk.retry.queue_error", error=str(e))
                break

        logger.info("dingtalk.retry.done", retried=retried, succeeded=succeeded)
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
            logger.warning("dingtalk.mark_sent.failed", message_id=message_id, error=str(e))

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
            logger.info("dingtalk.failed_message_enqueued", message_id=message_id)
        except Exception as e:
            logger.error("dingtalk.enqueue_failed.error", error=str(e))


# 创建全局实例
dingtalk_service = DingTalkService()
