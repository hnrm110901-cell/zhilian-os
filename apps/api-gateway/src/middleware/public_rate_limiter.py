"""
公开接口限流中间件
- IP: 30次/分钟
- 手机号短信: 5条/小时
"""

import time
from typing import Optional

import structlog
from fastapi import HTTPException, Request

logger = structlog.get_logger()

# In-memory rate limit store (production should use Redis)
_ip_requests: dict = {}  # ip -> [(timestamp, ...)]
_sms_requests: dict = {}  # phone -> [(timestamp, ...)]

IP_LIMIT = 30
IP_WINDOW = 60  # seconds
SMS_LIMIT = 5
SMS_WINDOW = 3600  # seconds


def _cleanup(store: dict, window: int):
    """Remove expired entries"""
    now = time.time()
    for key in list(store.keys()):
        store[key] = [t for t in store[key] if now - t < window]
        if not store[key]:
            del store[key]


async def check_ip_rate_limit(request: Request):
    """Check IP-based rate limit for public APIs"""
    ip = request.client.host if request.client else "unknown"
    now = time.time()

    _cleanup(_ip_requests, IP_WINDOW)

    if ip not in _ip_requests:
        _ip_requests[ip] = []

    # Filter to current window
    _ip_requests[ip] = [t for t in _ip_requests[ip] if now - t < IP_WINDOW]

    if len(_ip_requests[ip]) >= IP_LIMIT:
        logger.warning("public_rate_limit_ip", ip=ip, count=len(_ip_requests[ip]))
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后重试")

    _ip_requests[ip].append(now)


async def check_sms_rate_limit(phone: str):
    """Check SMS rate limit per phone number (5/hour)"""
    now = time.time()

    _cleanup(_sms_requests, SMS_WINDOW)

    if phone not in _sms_requests:
        _sms_requests[phone] = []

    _sms_requests[phone] = [t for t in _sms_requests[phone] if now - t < SMS_WINDOW]

    if len(_sms_requests[phone]) >= SMS_LIMIT:
        logger.warning("public_rate_limit_sms", phone=phone[-4:], count=len(_sms_requests[phone]))
        raise HTTPException(status_code=429, detail="短信发送过于频繁，请1小时后重试")

    _sms_requests[phone].append(now)
