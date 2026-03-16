"""
营销触达记录 API — P1 补齐（易订PRO 3.2 营销记录）

记录和查询每次对客户的营销触达：
- 短信/企微/电话/推送 → 记录时间、内容、渠道
- 按客户维度查触达历史（防止重复触达）
- 按门店维度汇总触达效果
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.notification import Notification
from ..models.user import User

router = APIRouter()


# ── 营销触达记录查询 ─────────────────────────────────────────────


@router.get("/api/v1/marketing-touchpoints/customer")
async def get_customer_touchpoints(
    customer_phone: str = Query(..., description="客户手机号"),
    store_id: str = Query(..., description="门店ID"),
    days: int = Query(90, description="查询最近N天"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    查询客户的营销触达历史。

    用于：
    1. 避免重复触达（同一客户短期内不重复发送）
    2. 回顾触达效果（是否有后续预订/消费）
    """
    since = datetime.utcnow() - timedelta(days=days)

    # 从通知表查询发送给该客户的营销消息
    result = await session.execute(
        select(Notification)
        .where(
            and_(
                Notification.store_id == store_id,
                Notification.created_at >= since,
                # 通过 metadata JSON 字段匹配手机号
            )
        )
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    notifications = result.scalars().all()

    # 过滤匹配手机号的通知
    touchpoints = []
    for n in notifications:
        meta = n.metadata_json if hasattr(n, "metadata_json") else {}
        if isinstance(meta, dict) and meta.get("customer_phone") == customer_phone:
            touchpoints.append(
                {
                    "id": str(n.id),
                    "type": n.type.value if hasattr(n.type, "value") else str(n.type),
                    "title": n.title,
                    "content": n.content[:100] if n.content else None,
                    "channel": meta.get("channel", "system"),
                    "sent_at": n.created_at.isoformat() if n.created_at else None,
                    "is_read": n.is_read if hasattr(n, "is_read") else None,
                }
            )

    # 计算触达频率
    recent_7d = sum(
        1
        for t in touchpoints
        if t.get("sent_at") and datetime.fromisoformat(t["sent_at"]) > datetime.utcnow() - timedelta(days=7)
    )

    return {
        "customer_phone": customer_phone[:3] + "****" + customer_phone[-4:],
        "store_id": store_id,
        "total_touchpoints": len(touchpoints),
        "recent_7d": recent_7d,
        "touchpoints": touchpoints,
        "recommendation": "建议暂缓触达" if recent_7d >= 3 else "可正常触达",
    }


@router.get("/api/v1/marketing-touchpoints/summary")
async def get_touchpoint_summary(
    store_id: str = Query(..., description="门店ID"),
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    门店营销触达汇总（按渠道统计触达量和触达率）。
    """
    # 统计各类型通知数量
    query = (
        select(
            Notification.type,
            func.count().label("count"),
        )
        .where(
            and_(
                Notification.store_id == store_id,
                func.date(Notification.created_at) >= start_date,
                func.date(Notification.created_at) <= end_date,
            )
        )
        .group_by(Notification.type)
    )
    result = await session.execute(query)
    rows = result.all()

    channels = []
    total = 0
    for r in rows:
        count = int(r.count)
        total += count
        channels.append(
            {
                "type": r.type.value if hasattr(r.type, "value") else str(r.type),
                "count": count,
            }
        )

    return {
        "store_id": store_id,
        "period": f"{start_date} ~ {end_date}",
        "total_touchpoints": total,
        "by_channel": channels,
    }
