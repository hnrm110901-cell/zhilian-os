"""
QR 扫码登录服务

桌面端生成 QR 码 → 手机扫码 → 企业微信内确认 → 桌面端轮询登录。
QR 会话存储在 Redis，TTL 300s，状态机：pending → scanned → confirmed / expired。
"""

import json
import logging
import uuid
from typing import Optional

from ..core.config import settings

logger = logging.getLogger(__name__)

# Redis key 前缀
_QR_SESSION_PREFIX = "qr:session:"  # qr:session:{qr_id} → JSON, TTL 300s

# QR 会话有效期（秒）
QR_EXPIRE_SECONDS = 300

# QR 状态枚举
QR_STATUS_PENDING = "pending"
QR_STATUS_SCANNED = "scanned"
QR_STATUS_CONFIRMED = "confirmed"
QR_STATUS_EXPIRED = "expired"


class QRLoginService:
    """QR 扫码登录服务"""

    def __init__(self):
        self._redis = None

    async def _get_redis(self):
        """懒加载 Redis 连接"""
        if self._redis is None:
            from .redis_cache_service import RedisCacheService

            cache = RedisCacheService()
            await cache.initialize()
            self._redis = cache._redis
        return self._redis

    # ── 公开 API ──────────────────────────────────────────────

    async def generate_qr(self) -> dict:
        """
        生成 QR 登录会话。

        返回:
        {
            "qr_id": "uuid",
            "qr_url": "https://...",
            "expires_in": 300
        }
        """
        qr_id = str(uuid.uuid4())
        redis = await self._get_redis()

        # 构建 QR 确认 URL
        qr_url = self._build_qr_url(qr_id)

        # 存储会话到 Redis
        session_data = {
            "status": QR_STATUS_PENDING,
            "qr_id": qr_id,
            "user_id": None,
            "access_token": None,
            "refresh_token": None,
        }
        session_key = f"{_QR_SESSION_PREFIX}{qr_id}"
        await redis.set(session_key, json.dumps(session_data), ex=QR_EXPIRE_SECONDS)

        logger.info("QR 登录会话已创建: qr_id=%s", qr_id)

        return {
            "qr_id": qr_id,
            "qr_url": qr_url,
            "expires_in": QR_EXPIRE_SECONDS,
        }

    async def get_status(self, qr_id: str) -> dict:
        """
        查询 QR 会话状态。

        返回:
        - pending: {"status": "pending"}
        - scanned: {"status": "scanned"}
        - confirmed: {"status": "confirmed", "access_token": ..., "refresh_token": ..., ...}
        - expired / 不存在: {"status": "expired"}
        """
        redis = await self._get_redis()
        session_key = f"{_QR_SESSION_PREFIX}{qr_id}"
        raw = await redis.get(session_key)

        if not raw:
            return {"status": QR_STATUS_EXPIRED}

        session_data = json.loads(raw)
        result = {"status": session_data["status"]}

        # 如果已确认，返回令牌
        if session_data["status"] == QR_STATUS_CONFIRMED:
            result["access_token"] = session_data.get("access_token")
            result["refresh_token"] = session_data.get("refresh_token")
            result["token_type"] = "bearer"
            result["user"] = session_data.get("user")
            # 确认后删除会话（一次性消费）
            await redis.delete(session_key)

        return result

    async def mark_scanned(self, qr_id: str) -> bool:
        """标记 QR 已被扫描（状态：pending → scanned）"""
        return await self._update_status(qr_id, QR_STATUS_PENDING, QR_STATUS_SCANNED)

    async def confirm(self, qr_id: str, user, auth_service) -> dict:
        """
        确认 QR 登录（已登录用户扫码确认）。

        参数:
        - qr_id: QR 会话 ID
        - user: 已认证的 User 对象
        - auth_service: AuthService 实例（用于生成令牌）

        返回: {"status": "confirmed"}
        异常: ValueError（会话不存在/已过期/状态不对）
        """
        redis = await self._get_redis()
        session_key = f"{_QR_SESSION_PREFIX}{qr_id}"
        raw = await redis.get(session_key)

        if not raw:
            raise ValueError("QR 会话不存在或已过期")

        session_data = json.loads(raw)

        if session_data["status"] not in (QR_STATUS_PENDING, QR_STATUS_SCANNED):
            raise ValueError(f"QR 会话状态异常: {session_data['status']}")

        # 为扫码用户生成令牌
        token_data = await auth_service.create_tokens_for_user(user)

        # 更新会话为已确认
        session_data["status"] = QR_STATUS_CONFIRMED
        session_data["user_id"] = str(user.id)
        session_data["access_token"] = token_data["access_token"]
        session_data["refresh_token"] = token_data["refresh_token"]
        session_data["user"] = token_data["user"]

        # 确认后保留 60s 供桌面端轮询取走
        await redis.set(session_key, json.dumps(session_data), ex=60)

        logger.info("QR 登录已确认: qr_id=%s, user=%s", qr_id, user.username)

        return {"status": QR_STATUS_CONFIRMED}

    # ── 内部方法 ──────────────────────────────────────────────

    def _build_qr_url(self, qr_id: str) -> str:
        """
        构建 QR 码指向的 URL。

        生产环境：通过企业微信 OAuth 跳转到确认页
        开发环境：直接指向 H5 确认页
        """
        # 基础确认页 URL
        base_url = getattr(settings, "SITE_URL", None) or "https://zlsjos.cn"
        confirm_url = f"{base_url}/qr-confirm?qr_id={qr_id}"

        # 如果配置了企业微信，构建 OAuth 跳转链接
        corp_id = getattr(settings, "WECHAT_WORK_CORP_ID", None) or ""
        if corp_id:
            import urllib.parse

            encoded = urllib.parse.quote(confirm_url, safe="")
            return (
                f"https://open.weixin.qq.com/connect/oauth2/authorize"
                f"?appid={corp_id}"
                f"&redirect_uri={encoded}"
                f"&response_type=code"
                f"&scope=snsapi_base"
                f"&state=qr_login"
                f"#wechat_redirect"
            )

        # 开发环境：直接返回确认页 URL
        return confirm_url

    async def _update_status(self, qr_id: str, expected: str, new_status: str) -> bool:
        """原子性更新 QR 会话状态"""
        redis = await self._get_redis()
        session_key = f"{_QR_SESSION_PREFIX}{qr_id}"
        raw = await redis.get(session_key)

        if not raw:
            return False

        session_data = json.loads(raw)
        if session_data["status"] != expected:
            return False

        session_data["status"] = new_status
        ttl = await redis.ttl(session_key)
        if ttl > 0:
            await redis.set(session_key, json.dumps(session_data), ex=ttl)
        else:
            await redis.set(session_key, json.dumps(session_data), ex=QR_EXPIRE_SECONDS)

        return True


# 单例
qr_login_service = QRLoginService()
