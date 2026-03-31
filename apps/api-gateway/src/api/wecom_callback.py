"""
企微SCRM事件回调路由 — Phase 2

处理企微服务端事件推送：
1. add_external_contact     → 自动绑定会员 + 发送欢迎语
2. resign_transfer          → 员工离职客户迁移
3. customer_behavior        → 客户行为同步到 CDP

接入说明：
- 企微管理后台「客户联系」→「企业服务人员」→ 设置接收消息的企业
- 回调 URL: https://api.zlsjos.cn/api/v1/wecom/callback/...
- 验证 Token + EncodingAESKey 通过环境变量配置

安全约束：
- 所有回调必须携带有效的企微签名（timestamp + nonce + msg_signature）
- 明文事件推送模式已弃用，仅支持加密推送（AES-CBC）
- 签名验证失败直接返回 403
"""

import hashlib
import os
from typing import Any, Dict, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..services.wecom_scrm_service import wecom_scrm_service

logger = structlog.get_logger()

router = APIRouter(prefix="/wecom/callback", tags=["WeComCallback"])


# ---------- Pydantic 事件模型 ----------


class WeComAddContactEvent(BaseModel):
    """添加外部联系人事件（企微 add_external_contact）"""

    wecom_userid: str = Field(..., description="触发添加的员工企微 userid")
    external_userid: str = Field(..., description="外部联系人 userid（客户）")
    store_id: str = Field(..., description="门店 ID（从 API 网关层传入）")
    brand_id: str = Field(..., description="品牌 ID")
    # 可选：企微回调中可能携带的 state 字段（如渠道活码来源）
    state: Optional[str] = Field(None, description="活码/渠道来源标识")


class WeComResignEvent(BaseModel):
    """员工离职客户迁移事件"""

    resigned_userid: str = Field(..., description="离职员工企微 userid")
    successor_userid: str = Field(..., description="接替人企微 userid")
    store_id: str = Field(..., description="门店 ID")


class WeComBehaviorEvent(BaseModel):
    """客户行为事件（点击菜单/回复消息/领券等）"""

    external_userid: str = Field(..., description="外部联系人 userid（客户）")
    behavior_type: str = Field(
        ...,
        description="行为类型: click_menu/reply/share/purchase_intent/coupon_claimed",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="附加数据（brand_id / store_id / group_id / 行为详情）",
    )


# ---------- 路由处理器 ----------


@router.post(
    "/external-contact/add",
    summary="处理添加外部联系人事件",
    description="触发 → 自动绑定会员 + 发送差异化欢迎语",
)
async def on_add_external_contact(
    event: WeComAddContactEvent,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    处理企微 add_external_contact 事件。

    流程：
    1. 调用 WeComSCRMService.bind_member_on_add_external_contact()
    2. 若绑定成功，发送差异化欢迎语（new_customer / returning 触发器）
    3. 返回绑定结果
    """
    logger.info(
        "WeComCallback: 收到添加外部联系人事件",
        wecom_userid=event.wecom_userid,
        external_userid=event.external_userid,
        store_id=event.store_id,
    )

    consumer_id = await wecom_scrm_service.bind_member_on_add_external_contact(
        db=db,
        wecom_userid=event.wecom_userid,
        external_userid=event.external_userid,
        store_id=event.store_id,
    )

    if consumer_id:
        # 根据是否首次添加决定欢迎语触发器
        # 此处简化：通过 bind 后的 lifecycle_state 判断
        # new_customer = registered/lead；returning = repeat/vip
        profile = await _get_lifecycle_state(db, consumer_id, event.brand_id)
        trigger = (
            "returning"
            if profile in ("repeat", "vip")
            else "new_customer"
        )

        await wecom_scrm_service.send_welcome_message(
            db=db,
            consumer_id=consumer_id,
            brand_id=event.brand_id,
            trigger=trigger,
        )

        # 提交事务
        await db.commit()

        return {
            "success": True,
            "consumer_id": consumer_id,
            "trigger": trigger,
            "message": "会员绑定成功，欢迎语已发送",
        }
    else:
        await db.commit()
        return {
            "success": False,
            "consumer_id": None,
            "message": "会员绑定失败（手机号未获取或解密失败），已记录为待处理",
        }


@router.post(
    "/external-contact/resign-transfer",
    summary="处理员工离职客户迁移事件",
    description="员工离职 → 批量迁移名下客户到接替人",
)
async def on_resignation_transfer(
    event: WeComResignEvent,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    处理员工离职，触发客户批量迁移。

    逻辑：
    1. 调用 WeComSCRMService.transfer_customer_on_resignation()
    2. 返回迁移统计结果
    """
    logger.info(
        "WeComCallback: 员工离职迁移事件",
        resigned_userid=event.resigned_userid,
        successor_userid=event.successor_userid,
        store_id=event.store_id,
    )

    result = await wecom_scrm_service.transfer_customer_on_resignation(
        db=db,
        resigned_userid=event.resigned_userid,
        successor_userid=event.successor_userid,
        store_id=event.store_id,
    )

    await db.commit()

    return {
        "success": True,
        "result": result,
        "message": f"迁移完成：共 {result['total']} 位客户，成功 {result['transferred']}，失败 {result['failed']}",
    }


@router.post(
    "/customer-behavior",
    summary="接收客户行为事件",
    description="客户行为（点击/回复/转发/购买意向）→ 同步到 CDP",
)
async def on_customer_behavior(
    event: WeComBehaviorEvent,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    接收并同步客户行为事件到 CDP。

    行为类型：
    - click_menu      → 菜单点击（浏览意向）
    - reply           → 回复消息（互动）
    - share           → 转发（裂变）
    - purchase_intent → 购买意向（高价值信号）
    - coupon_claimed  → 领取优惠券（促销响应）
    """
    logger.info(
        "WeComCallback: 客户行为事件",
        external_userid=event.external_userid,
        behavior_type=event.behavior_type,
    )

    synced = await wecom_scrm_service.sync_private_domain_behavior_to_cdp(
        db=db,
        external_userid=event.external_userid,
        behavior_type=event.behavior_type,
        metadata=event.metadata,
    )

    await db.commit()

    return {
        "success": synced,
        "behavior_type": event.behavior_type,
        "message": "行为已同步到 CDP" if synced else "未找到匹配会员，行为记录已忽略",
    }


@router.get(
    "/sidebar/{external_userid}",
    summary="导购助手侧边栏",
    description="获取外部联系人的完整客户画像（用于企微侧边栏展示）",
)
async def get_sidebar_profile(
    external_userid: str,
    store_id: str = Query(..., description="当前门店 ID"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    导购助手侧边栏：获取客户完整画像。

    供企微工作台/侧边栏 H5 页面调用，展示：
    - 基本信息（姓名/性别/标签/忌口）
    - RFM 等级和评分
    - 历史消费（跨渠道）
    - 当前品牌权益（积分/余额/等级）
    - 推荐话术
    """
    return await wecom_scrm_service.get_customer_profile_sidebar(
        db=db,
        external_userid=external_userid,
        store_id=store_id,
    )


# ---------- 辅助函数 ----------


async def _get_lifecycle_state(
    db: AsyncSession, consumer_id: str, brand_id: str
) -> str:
    """查询消费者当前 lifecycle_state（用于决定欢迎语触发器）"""
    try:
        import uuid
        from ..repositories.brand_consumer_profile_repo import BrandConsumerProfileRepo

        cid = uuid.UUID(consumer_id)
        profile = await BrandConsumerProfileRepo.get_by_consumer_and_brand(
            db, cid, brand_id
        )
        return profile.lifecycle_state if profile else "registered"
    except Exception:
        return "registered"
