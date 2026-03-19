"""
IM 员工自助服务 API

提供两个入口：
1. /im/self-service — 直接 API 调用（前端/测试用）
2. 被 im_callback 中的消息路由调用（员工通过企微/钉钉发消息触发）
"""

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..services.im_employee_self_service import IMEmployeeSelfService

logger = structlog.get_logger()
router = APIRouter()


class SelfServiceRequest(BaseModel):
    im_userid: str
    command: str
    platform: str = "wechat_work"  # wechat_work / dingtalk


@router.post("/im/self-service")
async def handle_self_service(
    body: SelfServiceRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    处理员工自助服务命令。

    支持命令：排班、请假、调班、工资条、考勤、个人信息
    """
    service = IMEmployeeSelfService(db)
    result = await service.handle_command(
        im_userid=body.im_userid,
        command=body.command,
        platform=body.platform,
    )
    return result


@router.get("/im/self-service/commands")
async def list_commands():
    """返回支持的自助命令列表"""
    return {
        "commands": [
            {"keyword": "排班", "aliases": ["班次", "上班"], "description": "查看本周排班"},
            {"keyword": "请假", "aliases": ["休假", "病假", "事假", "年假"], "description": "请假申请引导"},
            {"keyword": "调班", "aliases": ["换班", "代班"], "description": "调班申请引导"},
            {"keyword": "工资条", "aliases": ["薪资", "薪酬", "工资"], "description": "工资条查询"},
            {"keyword": "考勤", "aliases": ["打卡", "出勤", "迟到"], "description": "本月考勤统计"},
            {"keyword": "个人信息", "aliases": ["我的信息", "我是谁"], "description": "个人档案查看"},
        ],
    }
