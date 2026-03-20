"""Webhook endpoints — 聚合所有 Webhook 子路由"""
from fastapi import APIRouter

from .wechat_attendance import router as wechat_attendance_router

router = APIRouter(prefix="/api/v1/webhooks")
router.include_router(wechat_attendance_router, tags=["webhooks-wechat"])
