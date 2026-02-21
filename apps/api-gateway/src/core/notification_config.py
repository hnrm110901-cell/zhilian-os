"""
Multi-Channel Notification Configuration
多渠道通知配置管理
"""
from pydantic_settings import BaseSettings
from typing import Optional


class EmailConfig(BaseSettings):
    """邮件配置"""
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = "noreply@example.com"
    SMTP_PASSWORD: str = ""
    SMTP_FROM_NAME: str = "智链OS"
    SMTP_USE_TLS: bool = True
    SMTP_TIMEOUT: int = 30

    class Config:
        env_prefix = "EMAIL_"


class SMSConfig(BaseSettings):
    """短信配置"""
    # 阿里云短信
    ALIYUN_ACCESS_KEY_ID: str = ""
    ALIYUN_ACCESS_KEY_SECRET: str = ""
    ALIYUN_SMS_SIGN_NAME: str = "智链OS"
    ALIYUN_SMS_REGION: str = "cn-hangzhou"

    # 腾讯云短信
    TENCENT_SECRET_ID: str = ""
    TENCENT_SECRET_KEY: str = ""
    TENCENT_SMS_APP_ID: str = ""
    TENCENT_SMS_SIGN: str = "智链OS"

    # 使用的SMS提供商: aliyun, tencent
    SMS_PROVIDER: str = "aliyun"

    class Config:
        env_prefix = "SMS_"


class WeChatConfig(BaseSettings):
    """微信配置"""
    # 企业微信
    WECHAT_CORP_ID: str = ""
    WECHAT_CORP_SECRET: str = ""
    WECHAT_AGENT_ID: str = ""

    # 微信公众号
    WECHAT_APP_ID: str = ""
    WECHAT_APP_SECRET: str = ""

    # 使用的微信类型: corp, official
    WECHAT_TYPE: str = "corp"

    class Config:
        env_prefix = "WECHAT_"


class FeishuConfig(BaseSettings):
    """飞书配置"""
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""
    FEISHU_WEBHOOK_URL: Optional[str] = None

    class Config:
        env_prefix = "FEISHU_"


class PushConfig(BaseSettings):
    """推送配置"""
    # 极光推送
    JPUSH_APP_KEY: str = ""
    JPUSH_MASTER_SECRET: str = ""

    # Firebase推送
    FIREBASE_SERVER_KEY: str = ""
    FIREBASE_SENDER_ID: str = ""

    # 使用的推送提供商: jpush, firebase
    PUSH_PROVIDER: str = "jpush"

    class Config:
        env_prefix = "PUSH_"


class NotificationConfig(BaseSettings):
    """通知配置"""
    # 启用的通知渠道
    ENABLED_CHANNELS: str = "email,sms,wechat,system"

    # 重试配置
    MAX_RETRY_ATTEMPTS: int = 3
    RETRY_DELAY_SECONDS: int = 5

    # 超时配置
    NOTIFICATION_TIMEOUT_SECONDS: int = 30

    # 故障转移
    ENABLE_FALLBACK: bool = True
    FALLBACK_CHANNEL: str = "email"

    class Config:
        env_prefix = "NOTIFICATION_"

    def get_enabled_channels(self) -> list:
        """获取启用的渠道列表"""
        return [ch.strip() for ch in self.ENABLED_CHANNELS.split(",")]


# 全局配置实例
email_config = EmailConfig()
sms_config = SMSConfig()
wechat_config = WeChatConfig()
feishu_config = FeishuConfig()
push_config = PushConfig()
notification_config = NotificationConfig()
