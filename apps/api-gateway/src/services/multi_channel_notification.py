"""
多渠道通知服务
支持邮件、短信、微信、App推送等多种通知方式
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
import asyncio
import structlog
from abc import ABC, abstractmethod
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

from ..core.notification_config import (
    email_config,
    sms_config,
    wechat_config,
    feishu_config,
    push_config,
    notification_config,
)

logger = structlog.get_logger()


class NotificationChannel(str, Enum):
    """通知渠道"""
    EMAIL = "email"
    SMS = "sms"
    WECHAT = "wechat"
    APP_PUSH = "app_push"
    SYSTEM = "system"


class NotificationTemplate:
    """通知模板管理"""

    # 预定义模板
    TEMPLATES = {
        "order_confirmed": {
            "title": "订单确认",
            "content": "您的订单 {order_id} 已确认，预计 {estimated_time} 送达。",
            "channels": [NotificationChannel.SMS, NotificationChannel.APP_PUSH],
            "priority": "normal",
        },
        "order_ready": {
            "title": "订单已完成",
            "content": "您的订单 {order_id} 已准备好，请尽快取餐。",
            "channels": [NotificationChannel.SMS, NotificationChannel.APP_PUSH],
            "priority": "high",
        },
        "inventory_low": {
            "title": "库存预警",
            "content": "商品 {item_name} 库存不足，当前库存: {current_stock}，请及时补货。",
            "channels": [NotificationChannel.EMAIL, NotificationChannel.SYSTEM],
            "priority": "high",
        },
        "staff_schedule": {
            "title": "排班通知",
            "content": "您的排班已更新: {schedule_date} {shift_time}，请准时到岗。",
            "channels": [NotificationChannel.SMS, NotificationChannel.APP_PUSH],
            "priority": "normal",
        },
        "payment_success": {
            "title": "支付成功",
            "content": "您的订单 {order_id} 支付成功，金额: ¥{amount}。",
            "channels": [NotificationChannel.SMS, NotificationChannel.WECHAT],
            "priority": "normal",
        },
        "backup_completed": {
            "title": "数据备份完成",
            "content": "数据备份已完成，备份文件: {backup_file}，大小: {size}。",
            "channels": [NotificationChannel.EMAIL, NotificationChannel.SYSTEM],
            "priority": "low",
        },
        "backup_failed": {
            "title": "数据备份失败",
            "content": "数据备份失败: {error_message}，请检查系统状态。",
            "channels": [NotificationChannel.EMAIL, NotificationChannel.SYSTEM],
            "priority": "urgent",
        },
        "system_alert": {
            "title": "系统告警",
            "content": "{alert_message}",
            "channels": [NotificationChannel.EMAIL, NotificationChannel.SMS, NotificationChannel.SYSTEM],
            "priority": "urgent",
        },
    }

    @classmethod
    def get_template(cls, template_name: str) -> Optional[Dict[str, Any]]:
        """获取模板"""
        return cls.TEMPLATES.get(template_name)

    @classmethod
    def render_template(cls, template_name: str, **kwargs) -> Optional[Dict[str, str]]:
        """渲染模板"""
        template = cls.get_template(template_name)
        if not template:
            return None

        return {
            "title": template["title"],
            "content": template["content"].format(**kwargs),
            "channels": template["channels"],
            "priority": template["priority"],
        }


class NotificationChannelHandler(ABC):
    """通知渠道处理器基类"""

    @abstractmethod
    async def send(
        self,
        recipient: str,
        title: str,
        content: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """发送通知"""
        pass


class EmailNotificationHandler(NotificationChannelHandler):
    """邮件通知处理器"""

    async def send(
        self,
        recipient: str,
        title: str,
        content: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        发送邮件通知

        Args:
            recipient: 收件人邮箱
            title: 邮件标题
            content: 邮件内容
            extra_data: 额外数据 (可包含html_content, attachments等)

        Returns:
            是否发送成功
        """
        try:
            # 检查配置
            if not email_config.SMTP_PASSWORD:
                logger.warning("邮件服务未配置,使用模拟发送")
                await asyncio.sleep(0.1)
                return True

            # 创建邮件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = title
            msg['From'] = formataddr((email_config.SMTP_FROM_NAME, email_config.SMTP_USER))
            msg['To'] = recipient

            # 添加文本内容
            text_part = MIMEText(content, 'plain', 'utf-8')
            msg.attach(text_part)

            # 如果提供了HTML内容,添加HTML部分
            if extra_data and 'html_content' in extra_data:
                html_part = MIMEText(extra_data['html_content'], 'html', 'utf-8')
                msg.attach(html_part)

            # 发送邮件
            await asyncio.get_event_loop().run_in_executor(
                None,
                self._send_email_sync,
                msg,
                recipient
            )

            logger.info(
                "邮件发送成功",
                recipient=recipient,
                title=title,
                channel="email"
            )
            return True

        except Exception as e:
            logger.error("邮件发送失败", recipient=recipient, error=str(e))
            return False

    def _send_email_sync(self, msg: MIMEMultipart, recipient: str):
        """同步发送邮件"""
        try:
            if email_config.SMTP_USE_TLS:
                server = smtplib.SMTP(
                    email_config.SMTP_HOST,
                    email_config.SMTP_PORT,
                    timeout=email_config.SMTP_TIMEOUT
                )
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(
                    email_config.SMTP_HOST,
                    email_config.SMTP_PORT,
                    timeout=email_config.SMTP_TIMEOUT
                )

            server.login(email_config.SMTP_USER, email_config.SMTP_PASSWORD)
            server.send_message(msg)
            server.quit()

        except Exception as e:
            logger.error("SMTP发送失败", error=str(e))
            raise


class SMSNotificationHandler(NotificationChannelHandler):
    """短信通知处理器"""

    async def send(
        self,
        recipient: str,
        title: str,
        content: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        发送短信通知

        Args:
            recipient: 收件人手机号
            title: 短信标题
            content: 短信内容
            extra_data: 额外数据 (可包含template_code, template_params等)

        Returns:
            是否发送成功
        """
        try:
            # 检查配置
            if not sms_config.ALIYUN_ACCESS_KEY_ID and not sms_config.TENCENT_SECRET_ID:
                logger.warning("短信服务未配置,使用模拟发送")
                await asyncio.sleep(0.1)
                return True

            # 根据配置选择SMS提供商
            if sms_config.SMS_PROVIDER == "aliyun":
                result = await self._send_aliyun_sms(recipient, content, extra_data)
            elif sms_config.SMS_PROVIDER == "tencent":
                result = await self._send_tencent_sms(recipient, content, extra_data)
            else:
                logger.error(f"不支持的SMS提供商: {sms_config.SMS_PROVIDER}")
                return False

            if result:
                logger.info(
                    "短信发送成功",
                    recipient=recipient,
                    provider=sms_config.SMS_PROVIDER,
                    channel="sms"
                )
            return result

        except Exception as e:
            logger.error("短信发送失败", recipient=recipient, error=str(e))
            return False

    async def _send_aliyun_sms(
        self,
        phone: str,
        content: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """发送阿里云短信"""
        try:
            # TODO: 实际集成阿里云SDK
            # from aliyunsdkcore.client import AcsClient
            # from aliyunsdkcore.request import CommonRequest
            #
            # client = AcsClient(
            #     sms_config.ALIYUN_ACCESS_KEY_ID,
            #     sms_config.ALIYUN_ACCESS_KEY_SECRET,
            #     sms_config.ALIYUN_SMS_REGION
            # )
            #
            # request = CommonRequest()
            # request.set_domain('dysmsapi.aliyuncs.com')
            # request.set_version('2017-05-25')
            # request.set_action_name('SendSms')
            # request.add_query_param('PhoneNumbers', phone)
            # request.add_query_param('SignName', sms_config.ALIYUN_SMS_SIGN_NAME)
            # request.add_query_param('TemplateCode', extra_data.get('template_code'))
            # request.add_query_param('TemplateParam', json.dumps(extra_data.get('template_params', {})))
            #
            # response = client.do_action_with_exception(request)
            # result = json.loads(response)
            # return result.get('Code') == 'OK'

            logger.info("阿里云短信模拟发送", phone=phone, content=content[:50])
            await asyncio.sleep(0.1)
            return True

        except Exception as e:
            logger.error("阿里云短信发送失败", error=str(e))
            return False

    async def _send_tencent_sms(
        self,
        phone: str,
        content: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """发送腾讯云短信"""
        try:
            # TODO: 实际集成腾讯云SDK
            # from tencentcloud.common import credential
            # from tencentcloud.sms.v20210111 import sms_client, models
            #
            # cred = credential.Credential(
            #     sms_config.TENCENT_SECRET_ID,
            #     sms_config.TENCENT_SECRET_KEY
            # )
            # client = sms_client.SmsClient(cred, "ap-guangzhou")
            #
            # req = models.SendSmsRequest()
            # req.SmsSdkAppId = sms_config.TENCENT_SMS_APP_ID
            # req.SignName = sms_config.TENCENT_SMS_SIGN
            # req.PhoneNumberSet = [phone]
            # req.TemplateId = extra_data.get('template_id')
            # req.TemplateParamSet = extra_data.get('template_params', [])
            #
            # resp = client.SendSms(req)
            # return resp.SendStatusSet[0].Code == "Ok"

            logger.info("腾讯云短信模拟发送", phone=phone, content=content[:50])
            await asyncio.sleep(0.1)
            return True

        except Exception as e:
            logger.error("腾讯云短信发送失败", error=str(e))
            return False


class WeChatNotificationHandler(NotificationChannelHandler):
    """微信通知处理器"""

    async def send(
        self,
        recipient: str,
        title: str,
        content: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        发送微信通知

        Args:
            recipient: 收件人微信UserID (企业微信) 或 OpenID (公众号)
            title: 通知标题
            content: 通知内容
            extra_data: 额外数据 (可包含url, template_id等)

        Returns:
            是否发送成功
        """
        try:
            # 检查配置
            if not wechat_config.WECHAT_CORP_ID and not wechat_config.WECHAT_APP_ID:
                logger.warning("微信服务未配置,使用模拟发送")
                await asyncio.sleep(0.1)
                return True

            # 根据配置选择微信类型
            if wechat_config.WECHAT_TYPE == "corp":
                result = await self._send_corp_wechat(recipient, title, content, extra_data)
            elif wechat_config.WECHAT_TYPE == "official":
                result = await self._send_official_wechat(recipient, title, content, extra_data)
            else:
                logger.error(f"不支持的微信类型: {wechat_config.WECHAT_TYPE}")
                return False

            if result:
                logger.info(
                    "微信通知发送成功",
                    recipient=recipient,
                    type=wechat_config.WECHAT_TYPE,
                    channel="wechat"
                )
            return result

        except Exception as e:
            logger.error("微信通知发送失败", recipient=recipient, error=str(e))
            return False

    async def _send_corp_wechat(
        self,
        user_id: str,
        title: str,
        content: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """发送企业微信消息"""
        try:
            # TODO: 实际集成企业微信API
            # import requests
            #
            # # 获取access_token
            # token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken"
            # token_params = {
            #     "corpid": wechat_config.WECHAT_CORP_ID,
            #     "corpsecret": wechat_config.WECHAT_CORP_SECRET
            # }
            # token_resp = requests.get(token_url, params=token_params)
            # access_token = token_resp.json()["access_token"]
            #
            # # 发送消息
            # send_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
            # message_data = {
            #     "touser": user_id,
            #     "msgtype": "text",
            #     "agentid": wechat_config.WECHAT_AGENT_ID,
            #     "text": {
            #         "content": f"{title}\n\n{content}"
            #     }
            # }
            # send_resp = requests.post(send_url, json=message_data)
            # return send_resp.json()["errcode"] == 0

            logger.info("企业微信消息模拟发送", user_id=user_id, title=title)
            await asyncio.sleep(0.1)
            return True

        except Exception as e:
            logger.error("企业微信消息发送失败", error=str(e))
            return False

    async def _send_official_wechat(
        self,
        openid: str,
        title: str,
        content: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """发送微信公众号模板消息"""
        try:
            # TODO: 实际集成微信公众号API
            # import requests
            #
            # # 获取access_token
            # token_url = "https://api.weixin.qq.com/cgi-bin/token"
            # token_params = {
            #     "grant_type": "client_credential",
            #     "appid": wechat_config.WECHAT_APP_ID,
            #     "secret": wechat_config.WECHAT_APP_SECRET
            # }
            # token_resp = requests.get(token_url, params=token_params)
            # access_token = token_resp.json()["access_token"]
            #
            # # 发送模板消息
            # send_url = f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}"
            # template_data = {
            #     "touser": openid,
            #     "template_id": extra_data.get("template_id"),
            #     "url": extra_data.get("url", ""),
            #     "data": {
            #         "first": {"value": title},
            #         "keyword1": {"value": content},
            #         "remark": {"value": "感谢使用智链OS"}
            #     }
            # }
            # send_resp = requests.post(send_url, json=template_data)
            # return send_resp.json()["errcode"] == 0

            logger.info("微信公众号消息模拟发送", openid=openid, title=title)
            await asyncio.sleep(0.1)
            return True

        except Exception as e:
            logger.error("微信公众号消息发送失败", error=str(e))
            return False


class AppPushNotificationHandler(NotificationChannelHandler):
    """App推送通知处理器"""

    async def send(
        self,
        recipient: str,
        title: str,
        content: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        发送App推送通知

        Args:
            recipient: 收件人设备Token
            title: 推送标题
            content: 推送内容
            extra_data: 额外数据

        Returns:
            是否发送成功
        """
        try:
            # TODO: 集成推送服务 (极光推送, Firebase等)
            logger.info(
                "发送App推送通知",
                recipient=recipient,
                title=title,
                channel="app_push"
            )

            # 模拟发送
            await asyncio.sleep(0.1)

            # 这里应该调用推送服务
            # from jpush import JPush
            # ...

            return True
        except Exception as e:
            logger.error("App推送发送失败", recipient=recipient, error=str(e))
            return False


class MultiChannelNotificationService:
    """多渠道通知服务"""

    def __init__(self):
        self.handlers = {
            NotificationChannel.EMAIL: EmailNotificationHandler(),
            NotificationChannel.SMS: SMSNotificationHandler(),
            NotificationChannel.WECHAT: WeChatNotificationHandler(),
            NotificationChannel.APP_PUSH: AppPushNotificationHandler(),
        }

    async def send_notification(
        self,
        channels: List[NotificationChannel],
        recipient: str,
        title: str,
        content: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> Dict[NotificationChannel, bool]:
        """
        通过多个渠道发送通知

        Args:
            channels: 通知渠道列表
            recipient: 收件人 (根据渠道不同可能是邮箱、手机号、OpenID等)
            title: 通知标题
            content: 通知内容
            extra_data: 额外数据

        Returns:
            各渠道发送结果
        """
        results = {}

        # 并发发送到所有渠道
        tasks = []
        for channel in channels:
            if channel in self.handlers:
                handler = self.handlers[channel]
                tasks.append(self._send_with_channel(handler, channel, recipient, title, content, extra_data))

        # 等待所有任务完成
        channel_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 整理结果
        for i, channel in enumerate(channels):
            if channel in self.handlers:
                result = channel_results[i]
                results[channel] = result if not isinstance(result, Exception) else False

        return results

    async def _send_with_channel(
        self,
        handler: NotificationChannelHandler,
        channel: NotificationChannel,
        recipient: str,
        title: str,
        content: str,
        extra_data: Optional[Dict[str, Any]]
    ) -> bool:
        """通过指定渠道发送(带重试机制)"""
        max_retries = notification_config.MAX_RETRY_ATTEMPTS
        retry_delay = notification_config.RETRY_DELAY_SECONDS

        for attempt in range(max_retries):
            try:
                result = await handler.send(recipient, title, content, extra_data)
                if result:
                    return True

                # 如果发送失败且还有重试次数,等待后重试
                if attempt < max_retries - 1:
                    logger.warning(
                        "通知发送失败,准备重试",
                        channel=channel.value,
                        attempt=attempt + 1,
                        max_retries=max_retries
                    )
                    await asyncio.sleep(retry_delay)

            except Exception as e:
                logger.error(
                    "通知发送异常",
                    channel=channel.value,
                    attempt=attempt + 1,
                    error=str(e)
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)

        # 所有重试都失败,尝试故障转移
        if notification_config.ENABLE_FALLBACK and channel.value != notification_config.FALLBACK_CHANNEL:
            logger.warning(
                "启用故障转移",
                original_channel=channel.value,
                fallback_channel=notification_config.FALLBACK_CHANNEL
            )
            return await self._send_with_fallback(recipient, title, content, extra_data)

        return False

    async def _send_with_fallback(
        self,
        recipient: str,
        title: str,
        content: str,
        extra_data: Optional[Dict[str, Any]]
    ) -> bool:
        """使用故障转移渠道发送"""
        try:
            fallback_channel = NotificationChannel(notification_config.FALLBACK_CHANNEL)
            if fallback_channel in self.handlers:
                handler = self.handlers[fallback_channel]
                return await handler.send(recipient, title, content, extra_data)
        except Exception as e:
            logger.error("故障转移发送失败", error=str(e))

        return False

    async def send_template_notification(
        self,
        template_name: str,
        recipient: str,
        **template_vars
    ) -> Dict[NotificationChannel, bool]:
        """
        使用模板发送通知

        Args:
            template_name: 模板名称
            recipient: 收件人
            **template_vars: 模板变量

        Returns:
            各渠道发送结果
        """
        rendered = NotificationTemplate.render_template(template_name, **template_vars)
        if not rendered:
            logger.error("模板不存在", template_name=template_name)
            return {}

        return await self.send_notification(
            channels=rendered["channels"],
            recipient=recipient,
            title=rendered["title"],
            content=rendered["content"],
        )


# 全局实例
multi_channel_notification_service = MultiChannelNotificationService()
