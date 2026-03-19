"""
SMS 验证码服务

支持阿里云 / 腾讯云短信发送，开发环境降级为固定验证码 888888。
验证码存储在 Redis，TTL 300s；发送冷却 60s。
"""

import logging
import random
import string
from typing import Optional

from ..core.config import settings

logger = logging.getLogger(__name__)

# Redis key 前缀
_VERIFY_PREFIX = "sms:verify:"  # sms:verify:{phone} → code, TTL 300s
_COOLDOWN_PREFIX = "sms:cooldown:"  # sms:cooldown:{phone} → 1, TTL 60s

# 验证码有效期（秒）
CODE_EXPIRE_SECONDS = 300
# 发送冷却（秒）
COOLDOWN_SECONDS = 60
# 开发环境固定验证码
DEV_FIXED_CODE = "888888"


class SMSService:
    """短信验证码发送 + 校验服务"""

    def __init__(self):
        self._redis = None

    async def _get_redis(self):
        """懒加载 Redis 连接（复用项目全局 RedisCacheService）"""
        if self._redis is None:
            from .redis_cache_service import RedisCacheService

            cache = RedisCacheService()
            await cache.initialize()
            self._redis = cache._redis
        return self._redis

    # ── 公开 API ──────────────────────────────────────────────

    async def send_code(self, phone: str) -> dict:
        """
        发送验证码到手机号。

        返回: {"message": "验证码已发送", "expires_in": 300}
        异常: ValueError（冷却中 / 手机号格式错误）
        """
        # 1. 校验手机号格式（中国大陆 11 位）
        if not self._validate_phone(phone):
            raise ValueError("手机号格式不正确，请输入11位手机号")

        redis = await self._get_redis()

        # 2. 检查冷却
        cooldown_key = f"{_COOLDOWN_PREFIX}{phone}"
        if await redis.exists(cooldown_key):
            ttl = await redis.ttl(cooldown_key)
            raise ValueError(f"发送过于频繁，请{ttl}秒后重试")

        # 3. 生成验证码
        code = self._generate_code()

        # 4. 存储到 Redis
        verify_key = f"{_VERIFY_PREFIX}{phone}"
        await redis.set(verify_key, code, ex=CODE_EXPIRE_SECONDS)
        await redis.set(cooldown_key, "1", ex=COOLDOWN_SECONDS)

        # 5. 发送短信（开发环境降级）
        sent = await self._dispatch_sms(phone, code)
        if not sent:
            logger.warning("SMS 发送失败，验证码已存储到 Redis: phone=%s", phone)

        return {"message": "验证码已发送", "expires_in": CODE_EXPIRE_SECONDS}

    async def verify_code(self, phone: str, code: str) -> bool:
        """校验验证码，成功后自动删除（一次性）"""
        redis = await self._get_redis()
        verify_key = f"{_VERIFY_PREFIX}{phone}"

        stored_code = await redis.get(verify_key)
        if not stored_code:
            return False

        if stored_code != code:
            return False

        # 验证成功，删除验证码（防止重放）
        await redis.delete(verify_key)
        return True

    # ── 内部方法 ──────────────────────────────────────────────

    @staticmethod
    def _validate_phone(phone: str) -> bool:
        """校验中国大陆手机号（简单规则：11位数字，1开头）"""
        return phone is not None and len(phone) == 11 and phone.isdigit() and phone.startswith("1")

    @staticmethod
    def _generate_code() -> str:
        """生成 6 位数字验证码"""
        return "".join(random.choices(string.digits, k=6))

    async def _dispatch_sms(self, phone: str, code: str) -> bool:
        """
        实际发送短信。

        优先级：阿里云 → 腾讯云 → 日志打印（开发环境降级）
        """
        # 尝试阿里云
        if settings.ALIYUN_ACCESS_KEY_ID and settings.ALIYUN_SMS_TEMPLATE_CODE:
            return await self._send_aliyun(phone, code)

        # 尝试腾讯云
        if settings.TENCENT_SECRET_ID and settings.TENCENT_SMS_TEMPLATE_ID:
            return await self._send_tencent(phone, code)

        # 开发环境降级：使用固定验证码 + 日志打印
        logger.info(
            "【开发环境】短信验证码 → phone=%s, code=%s（未配置 SMS 服务，使用日志打印）",
            phone,
            code,
        )
        return True

    async def _send_aliyun(self, phone: str, code: str) -> bool:
        """阿里云短信发送"""
        try:
            import json

            from alibabacloud_dysmsapi20170525 import models as sms_models
            from alibabacloud_dysmsapi20170525.client import Client
            from alibabacloud_tea_openapi import models as open_models

            config = open_models.Config(
                access_key_id=settings.ALIYUN_ACCESS_KEY_ID,
                access_key_secret=settings.ALIYUN_ACCESS_KEY_SECRET,
            )
            config.endpoint = "dysmsapi.aliyuncs.com"
            client = Client(config)

            request = sms_models.SendSmsRequest(
                phone_numbers=phone,
                sign_name=settings.ALIYUN_SMS_SIGN_NAME,
                template_code=settings.ALIYUN_SMS_TEMPLATE_CODE,
                template_param=json.dumps({"code": code}),
            )
            response = client.send_sms(request)
            if response.body.code == "OK":
                logger.info("阿里云短信发送成功: phone=%s", phone)
                return True
            else:
                logger.error("阿里云短信发送失败: %s", response.body.message)
                return False
        except ImportError:
            logger.warning("阿里云 SMS SDK 未安装，降级到日志打印")
            logger.info("【降级】验证码 → phone=%s, code=%s", phone, code)
            return True
        except Exception as e:
            logger.error("阿里云短信发送异常: %s", e)
            return False

    async def _send_tencent(self, phone: str, code: str) -> bool:
        """腾讯云短信发送"""
        try:
            from tencentcloud.common import credential
            from tencentcloud.sms.v20210111 import models, sms_client

            cred = credential.Credential(
                settings.TENCENT_SECRET_ID,
                settings.TENCENT_SECRET_KEY,
            )
            client = sms_client.SmsClient(cred, "ap-guangzhou")

            req = models.SendSmsRequest()
            req.SmsSdkAppId = settings.TENCENT_SMS_APP_ID
            req.SignName = settings.TENCENT_SMS_SIGN_NAME
            req.TemplateId = settings.TENCENT_SMS_TEMPLATE_ID
            req.TemplateParamSet = [code]
            req.PhoneNumberSet = [f"+86{phone}"]

            resp = client.SendSms(req)
            status_set = resp.SendStatusSet
            if status_set and status_set[0].Code == "Ok":
                logger.info("腾讯云短信发送成功: phone=%s", phone)
                return True
            else:
                msg = status_set[0].Message if status_set else "未知错误"
                logger.error("腾讯云短信发送失败: %s", msg)
                return False
        except ImportError:
            logger.warning("腾讯云 SMS SDK 未安装，降级到日志打印")
            logger.info("【降级】验证码 → phone=%s, code=%s", phone, code)
            return True
        except Exception as e:
            logger.error("腾讯云短信发送异常: %s", e)
            return False


# 单例
sms_service = SMSService()
