"""
POS 数据同步验证接口

提供按需触发 POS 数据拉取 + 与实际 POS 后台数据对比验证的功能。
运营人员可通过此接口随时触发同步并查看同步摘要，无需等待凌晨定时任务。

路由前缀：/api/v1/integrations/pos-sync
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from ..core.database import get_db_session
from ..core.dependencies import get_current_active_user
from ..models.store import Store
from ..models.user import User

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/integrations/pos-sync",
    tags=["pos-sync"],
)


# ── 请求 / 响应模型 ────────────────────────────────────────────────────────────

class PosSyncRequest(BaseModel):
    """按需同步请求"""
    adapter: str = Field(
        ...,
        description="适配器类型：pinzhi / tiancai / aoqiwei_supply",
        pattern="^(pinzhi|tiancai|aoqiwei_supply)$",
    )
    sync_date: Optional[str] = Field(
        None,
        description="要同步的日期 YYYY-MM-DD，默认昨天",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    store_ids: Optional[List[str]] = Field(
        None,
        description="指定门店 ID 列表，为空则同步所有活跃门店",
    )


class StoreSyncSummary(BaseModel):
    store_id: str
    store_name: str
    orders_in_db: int              # 数据库已有订单数
    revenue_in_db: float           # 数据库已有营收（元）
    pos_orders: Optional[int]      # POS 返回订单数（None 表示未拉取）
    pos_revenue: Optional[float]   # POS 返回营收（元）
    match: Optional[bool]          # 数据是否匹配
    diff_orders: Optional[int]     # 差异订单数
    diff_revenue: Optional[float]  # 差异营收（元）
    error: Optional[str]


class PosSyncResponse(BaseModel):
    success: bool
    adapter: str
    sync_date: str
    triggered_at: str
    stores: List[StoreSyncSummary]
    totals: Dict[str, Any]
    skipped_reason: Optional[str] = None


# ── 内部 Celery 任务调用 ──────────────────────────────────────────────────────

def _trigger_celery_task(task_name: str) -> Optional[str]:
    """触发 Celery 任务并返回 task_id（如果 Celery 不可用则返回 None）"""
    try:
        from ..core.celery_app import celery_app
        result = celery_app.send_task(f"src.core.celery_tasks.{task_name}")
        return result.id
    except Exception as exc:
        logger.warning("pos_sync.celery_trigger_failed", task=task_name, error=str(exc))
        return None


# ── 核心同步逻辑 ──────────────────────────────────────────────────────────────

async def _sync_pinzhi(sync_date: str, store_ids: Optional[List[str]]) -> PosSyncResponse:
    """按需拉取品智 POS 数据并与 DB 对比"""
    base_url = os.getenv("PINZHI_BASE_URL", "")
    token = os.getenv("PINZHI_TOKEN", "")

    if not base_url or not token:
        return PosSyncResponse(
            success=False,
            adapter="pinzhi",
            sync_date=sync_date,
            triggered_at=datetime.now().isoformat(),
            stores=[],
            totals={},
            skipped_reason="PINZHI_BASE_URL 或 PINZHI_TOKEN 未配置，请在环境变量中设置",
        )

    brand_id = os.getenv("PINZHI_BRAND_ID", "")
    from packages.api_adapters.pinzhi.src.adapter import PinzhiAdapter

    adapter = PinzhiAdapter({
        "base_url": base_url,
        "token": token,
        "timeout": int(os.getenv("PINZHI_TIMEOUT", "30")),
        "retry_times": int(os.getenv("PINZHI_RETRY_TIMES", "3")),
    })

    store_summaries: List[StoreSyncSummary] = []

    async with get_db_session() as session:
        stmt = select(Store).where(Store.is_active.is_(True))
        if store_ids:
            stmt = stmt.where(Store.id.in_(store_ids))
        result = await session.execute(stmt)
        stores = result.scalars().all()

        for store in stores:
            sid = str(store.id)
            ognid = ""
            if store.config and isinstance(store.config, dict):
                ognid = store.config.get("pinzhi_ognid", "")
            if not ognid:
                ognid = store.code or sid

            # 1) 查 DB 已有数据
            db_row = await session.execute(
                text("""
                    SELECT COUNT(*) AS cnt,
                           COALESCE(SUM(final_amount), 0) AS total_cents
                    FROM orders
                    WHERE store_id = :sid
                      AND DATE(order_time) = :dt
                      AND sales_channel = 'pinzhi'
                """),
                {"sid": sid, "dt": sync_date},
            )
            db_data = db_row.fetchone()
            db_orders = int(db_data[0]) if db_data else 0
            db_revenue = float(db_data[1] or 0) / 100 if db_data else 0.0

            # 2) 从 POS 拉取当日汇总（逐页计数）
            pos_orders = 0
            pos_revenue = 0.0
            error_msg = None
            try:
                page = 1
                while True:
                    raw_orders = await adapter.query_orders(
                        ognid=ognid,
                        begin_date=sync_date,
                        end_date=sync_date,
                        page_index=page,
                        page_size=100,
                    )
                    if not raw_orders:
                        break
                    for raw in raw_orders:
                        order_schema = adapter.to_order(raw, sid, brand_id)
                        final = float(order_schema.total) - float(order_schema.discount)
                        pos_revenue += final
                        pos_orders += 1
                        # 顺便 upsert 到 DB（与定时任务相同逻辑）
                        total_cents = int(order_schema.total * 100)
                        disc_cents = int(order_schema.discount * 100)
                        vip_phone = raw.get("vipMobile") or raw.get("mobile") or ""
                        vip_name = raw.get("vipName") or ""
                        await session.execute(
                            text("""
                                INSERT INTO orders
                                    (id, store_id, table_number, status,
                                     total_amount, discount_amount, final_amount,
                                     order_time, waiter_id, sales_channel, notes,
                                     customer_phone, customer_name,
                                     order_metadata, created_at, updated_at)
                                VALUES
                                    (:id, :store_id, :table_number, :status,
                                     :total_amount, :discount_amount, :final_amount,
                                     :order_time, :waiter_id, 'pinzhi', :notes,
                                     :customer_phone, :customer_name,
                                     '{}', NOW(), NOW())
                                ON CONFLICT (id) DO UPDATE SET
                                    status          = EXCLUDED.status,
                                    total_amount    = EXCLUDED.total_amount,
                                    discount_amount = EXCLUDED.discount_amount,
                                    final_amount    = EXCLUDED.final_amount,
                                    customer_phone  = COALESCE(NULLIF(EXCLUDED.customer_phone, ''), orders.customer_phone),
                                    customer_name   = COALESCE(NULLIF(EXCLUDED.customer_name, ''), orders.customer_name),
                                    updated_at      = NOW()
                            """),
                            {
                                "id": order_schema.order_id,
                                "store_id": sid,
                                "table_number": order_schema.table_number,
                                "status": order_schema.order_status.value,
                                "total_amount": total_cents,
                                "discount_amount": disc_cents,
                                "final_amount": total_cents - disc_cents,
                                "order_time": order_schema.created_at,
                                "waiter_id": order_schema.waiter_id,
                                "notes": order_schema.notes,
                                "customer_phone": vip_phone,
                                "customer_name": vip_name,
                            },
                        )
                    if len(raw_orders) < 100:
                        break
                    page += 1
            except Exception as e:
                error_msg = str(e)
                logger.error("pos_sync.pinzhi.store_error", store_id=sid, error=error_msg)

            # 对比
            match = None
            diff_orders = None
            diff_revenue = None
            if error_msg is None:
                diff_orders = pos_orders - db_orders
                diff_revenue = round(pos_revenue - db_revenue, 2)
                match = abs(diff_orders) <= 1 and abs(diff_revenue) < 1.0

            store_summaries.append(StoreSyncSummary(
                store_id=sid,
                store_name=getattr(store, "name", sid),
                orders_in_db=db_orders,
                revenue_in_db=round(db_revenue, 2),
                pos_orders=pos_orders if error_msg is None else None,
                pos_revenue=round(pos_revenue, 2) if error_msg is None else None,
                match=match,
                diff_orders=diff_orders,
                diff_revenue=diff_revenue,
                error=error_msg,
            ))

        await session.commit()

    total_db = sum(s.orders_in_db for s in store_summaries)
    total_pos = sum(s.pos_orders or 0 for s in store_summaries)
    return PosSyncResponse(
        success=all(s.error is None for s in store_summaries),
        adapter="pinzhi",
        sync_date=sync_date,
        triggered_at=datetime.now().isoformat(),
        stores=store_summaries,
        totals={
            "stores_processed": len(store_summaries),
            "db_total_orders": total_db,
            "pos_total_orders": total_pos,
            "db_total_revenue": round(sum(s.revenue_in_db for s in store_summaries), 2),
            "pos_total_revenue": round(sum(s.pos_revenue or 0 for s in store_summaries), 2),
            "all_matched": all(s.match is True for s in store_summaries),
        },
    )


async def _sync_tiancai(sync_date: str, store_ids: Optional[List[str]]) -> PosSyncResponse:
    """按需拉取天财商龙数据并与 DB 对比"""
    appid = os.getenv("TIANCAI_APPID", "")
    accessid = os.getenv("TIANCAI_ACCESSID", "")

    if not appid or not accessid:
        return PosSyncResponse(
            success=False,
            adapter="tiancai",
            sync_date=sync_date,
            triggered_at=datetime.now().isoformat(),
            stores=[],
            totals={},
            skipped_reason="TIANCAI_APPID 或 TIANCAI_ACCESSID 未配置，请在环境变量中设置",
        )

    base_url = os.getenv("TIANCAI_BASE_URL", "https://cysms.wuuxiang.com")
    center_id = os.getenv("TIANCAI_CENTER_ID", "")
    brand_id = os.getenv("TIANCAI_BRAND_ID", "")

    from packages.api_adapters.tiancai_shanglong.src.adapter import TiancaiShanglongAdapter  # noqa

    store_summaries: List[StoreSyncSummary] = []

    async with get_db_session() as session:
        stmt = select(Store).where(Store.is_active.is_(True))
        if store_ids:
            stmt = stmt.where(Store.id.in_(store_ids))
        result = await session.execute(stmt)
        stores = result.scalars().all()

        for store in stores:
            sid = str(store.id)
            shop_id = (
                os.getenv(f"TIANCAI_SHOP_ID_{sid}")
                or os.getenv("TIANCAI_SHOP_ID", "")
                or getattr(store, "code", None)
                or sid
            )

            adapter = TiancaiShanglongAdapter({
                "base_url": base_url,
                "appid": appid,
                "accessid": accessid,
                "center_id": center_id,
                "shop_id": shop_id,
                "timeout": 30,
                "retry_times": 2,
            })

            # DB 已有数据
            db_row = await session.execute(
                text("""
                    SELECT COUNT(*) AS cnt,
                           COALESCE(SUM(final_amount), 0) AS total_cents
                    FROM orders
                    WHERE store_id = :sid
                      AND DATE(order_time) = :dt
                      AND sales_channel = 'tiancai'
                """),
                {"sid": sid, "dt": sync_date},
            )
            db_data = db_row.fetchone()
            db_orders = int(db_data[0]) if db_data else 0
            db_revenue = float(db_data[1] or 0) / 100 if db_data else 0.0

            pos_orders = 0
            pos_revenue = 0.0
            error_msg = None
            try:
                page = 1
                while True:
                    raw_orders = await adapter.query_orders(
                        start_date=sync_date,
                        end_date=sync_date,
                        page=page,
                        page_size=50,
                        status="paid",
                    )
                    if not raw_orders:
                        break
                    for raw in raw_orders:
                        order_schema = adapter.to_order(raw, sid, brand_id)
                        total_cents = int(order_schema.total * 100)
                        disc_cents = int(order_schema.discount * 100)
                        pos_revenue += (order_schema.total - order_schema.discount)
                        pos_orders += 1
                        await session.execute(
                            text("""
                                INSERT INTO orders
                                    (id, store_id, table_number, status,
                                     total_amount, discount_amount, final_amount,
                                     order_time, waiter_id, sales_channel, notes,
                                     order_metadata, created_at, updated_at)
                                VALUES
                                    (:id, :store_id, :table_number, :status,
                                     :total_amount, :discount_amount, :final_amount,
                                     :order_time, :waiter_id, 'tiancai', :notes,
                                     '{}', NOW(), NOW())
                                ON CONFLICT (id) DO UPDATE SET
                                    status          = EXCLUDED.status,
                                    total_amount    = EXCLUDED.total_amount,
                                    discount_amount = EXCLUDED.discount_amount,
                                    final_amount    = EXCLUDED.final_amount,
                                    updated_at      = NOW()
                            """),
                            {
                                "id": order_schema.order_id,
                                "store_id": sid,
                                "table_number": order_schema.table_number,
                                "status": order_schema.order_status.value,
                                "total_amount": total_cents,
                                "discount_amount": disc_cents,
                                "final_amount": total_cents - disc_cents,
                                "order_time": order_schema.created_at,
                                "waiter_id": order_schema.waiter_id,
                                "notes": order_schema.notes,
                            },
                        )
                    if len(raw_orders) < 50:
                        break
                    page += 1
            except Exception as e:
                error_msg = str(e)
                logger.error("pos_sync.tiancai.store_error", store_id=sid, error=error_msg)

            match = None
            diff_orders = None
            diff_revenue = None
            if error_msg is None:
                diff_orders = pos_orders - db_orders
                diff_revenue = round(pos_revenue - db_revenue, 2)
                match = abs(diff_orders) <= 1 and abs(diff_revenue) < 1.0

            store_summaries.append(StoreSyncSummary(
                store_id=sid,
                store_name=getattr(store, "name", sid),
                orders_in_db=db_orders,
                revenue_in_db=round(db_revenue, 2),
                pos_orders=pos_orders if error_msg is None else None,
                pos_revenue=round(pos_revenue, 2) if error_msg is None else None,
                match=match,
                diff_orders=diff_orders,
                diff_revenue=diff_revenue,
                error=error_msg,
            ))

        await session.commit()

    return PosSyncResponse(
        success=all(s.error is None for s in store_summaries),
        adapter="tiancai",
        sync_date=sync_date,
        triggered_at=datetime.now().isoformat(),
        stores=store_summaries,
        totals={
            "stores_processed": len(store_summaries),
            "db_total_orders": sum(s.orders_in_db for s in store_summaries),
            "pos_total_orders": sum(s.pos_orders or 0 for s in store_summaries),
            "db_total_revenue": round(sum(s.revenue_in_db for s in store_summaries), 2),
            "pos_total_revenue": round(sum(s.pos_revenue or 0 for s in store_summaries), 2),
            "all_matched": all(s.match is True for s in store_summaries),
        },
    )


async def _sync_aoqiwei_supply(sync_date: str, store_ids: Optional[List[str]]) -> PosSyncResponse:
    """按需拉取奥琦玮供应链数据（采购 + 库存）"""
    app_key = os.getenv("AOQIWEI_APP_KEY", "")
    app_secret = os.getenv("AOQIWEI_APP_SECRET", "")

    if not app_key or not app_secret:
        return PosSyncResponse(
            success=False,
            adapter="aoqiwei_supply",
            sync_date=sync_date,
            triggered_at=datetime.now().isoformat(),
            stores=[],
            totals={},
            skipped_reason="AOQIWEI_APP_KEY 或 AOQIWEI_APP_SECRET 未配置，请在环境变量中设置",
        )

    from packages.api_adapters.aoqiwei.src.adapter import AoqiweiAdapter

    adapter = AoqiweiAdapter({
        "app_key": app_key,
        "app_secret": app_secret,
        "timeout": 30,
    })

    store_summaries: List[StoreSyncSummary] = []

    async with get_db_session() as session:
        stmt = select(Store).where(Store.is_active.is_(True))
        if store_ids:
            stmt = stmt.where(Store.id.in_(store_ids))
        result = await session.execute(stmt)
        stores = result.scalars().all()

        for store in stores:
            sid = str(store.id)
            shop_code = (
                os.getenv(f"AOQIWEI_SHOP_CODE_{sid}")
                or os.getenv("AOQIWEI_SHOP_CODE", "")
                or getattr(store, "code", None)
                or sid
            )

            # DB 中已有的采购记录数（daily_summaries 表）
            db_row = await session.execute(
                text("""
                    SELECT order_count,
                           COALESCE(revenue_cents, 0) AS revenue_cents
                    FROM daily_summaries
                    WHERE store_id = :sid
                      AND business_date = :dt
                      AND source = 'aoqiwei_supply'
                    LIMIT 1
                """),
                {"sid": sid, "dt": sync_date},
            )
            db_data = db_row.fetchone()
            db_orders = int(db_data[0]) if db_data else 0
            db_revenue = float(db_data[1] or 0) / 100 if db_data else 0.0

            pos_orders = 0
            pos_revenue = 0.0
            stock_count = 0
            error_msg = None
            try:
                # 采购入库单
                po_resp = await adapter.query_purchase_orders(
                    start_date=sync_date,
                    end_date=sync_date,
                    page=1,
                    page_size=500,
                )
                po_list = po_resp.get("list", []) if isinstance(po_resp, dict) else []
                for po in po_list:
                    pos_orders += 1
                    pos_revenue += float(po.get("totalAmount") or po.get("amount") or 0)

                # 库存快照
                stock_list = await adapter.query_stock(shop_code=shop_code)
                stock_count = len(stock_list) if stock_list else 0
            except Exception as e:
                error_msg = str(e)
                logger.error("pos_sync.aoqiwei.store_error", store_id=sid, error=error_msg)

            match = None
            diff_orders = None
            diff_revenue = None
            if error_msg is None:
                diff_orders = pos_orders - db_orders
                diff_revenue = round(pos_revenue - db_revenue, 2)
                match = abs(diff_orders) <= 2 and abs(diff_revenue) < 10.0

            store_summaries.append(StoreSyncSummary(
                store_id=sid,
                store_name=getattr(store, "name", sid),
                orders_in_db=db_orders,
                revenue_in_db=round(db_revenue, 2),
                pos_orders=pos_orders if error_msg is None else None,
                pos_revenue=round(pos_revenue, 2) if error_msg is None else None,
                match=match,
                diff_orders=diff_orders,
                diff_revenue=diff_revenue,
                error=error_msg,
            ))

    return PosSyncResponse(
        success=all(s.error is None for s in store_summaries),
        adapter="aoqiwei_supply",
        sync_date=sync_date,
        triggered_at=datetime.now().isoformat(),
        stores=store_summaries,
        totals={
            "stores_processed": len(store_summaries),
            "db_purchase_orders": sum(s.orders_in_db for s in store_summaries),
            "pos_purchase_orders": sum(s.pos_orders or 0 for s in store_summaries),
            "db_total_amount": round(sum(s.revenue_in_db for s in store_summaries), 2),
            "pos_total_amount": round(sum(s.pos_revenue or 0 for s in store_summaries), 2),
            "all_matched": all(s.match is True for s in store_summaries),
        },
    )


# ── 路由 ──────────────────────────────────────────────────────────────────────

_ADAPTER_HANDLERS = {
    "pinzhi": _sync_pinzhi,
    "tiancai": _sync_tiancai,
    "aoqiwei_supply": _sync_aoqiwei_supply,
}


@router.post("", response_model=PosSyncResponse, summary="按需触发 POS 数据同步并对比")
async def trigger_pos_sync(
    body: PosSyncRequest,
    current_user: User = Depends(get_current_active_user),
) -> PosSyncResponse:
    """
    按需拉取指定 POS 适配器的数据，写入 DB，并返回与 DB 现有数据的对比摘要。

    - **adapter**: `pinzhi`（品智）/ `tiancai`（天财商龙）/ `aoqiwei_supply`（奥琦玮供应链）
    - **sync_date**: 要同步的日期，默认昨天（YYYY-MM-DD）
    - **store_ids**: 指定门店 ID，为空则同步所有门店

    返回每个门店的 DB 数据 vs POS 数据对比，帮助运营人员快速发现差异。
    """
    sync_date = body.sync_date or (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    handler = _ADAPTER_HANDLERS.get(body.adapter)
    if not handler:
        raise HTTPException(status_code=400, detail=f"不支持的适配器类型: {body.adapter}")

    logger.info(
        "pos_sync.triggered",
        adapter=body.adapter,
        sync_date=sync_date,
        store_ids=body.store_ids,
        user_id=str(getattr(current_user, "id", "unknown")),
    )

    try:
        return await handler(sync_date, body.store_ids)
    except Exception as exc:
        logger.error("pos_sync.fatal", adapter=body.adapter, error=str(exc))
        raise HTTPException(status_code=500, detail=f"同步失败: {exc}") from exc


@router.get("/status", summary="查询各适配器配置状态")
async def get_sync_status(
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    返回各 POS 适配器的环境变量配置状态和最近同步时间，
    帮助运营人员快速判断哪些适配器已配置、哪些需要补充。
    """
    adapters_status = {
        "pinzhi": {
            "configured": bool(os.getenv("PINZHI_BASE_URL") and os.getenv("PINZHI_TOKEN")),
            "base_url": os.getenv("PINZHI_BASE_URL", ""),
            "missing_vars": [v for v in ["PINZHI_BASE_URL", "PINZHI_TOKEN"] if not os.getenv(v)],
            "scheduled_time": "每日 01:30",
        },
        "tiancai": {
            "configured": bool(os.getenv("TIANCAI_APPID") and os.getenv("TIANCAI_ACCESSID")),
            "base_url": os.getenv("TIANCAI_BASE_URL", "https://cysms.wuuxiang.com"),
            "missing_vars": [v for v in ["TIANCAI_APPID", "TIANCAI_ACCESSID"] if not os.getenv(v)],
            "scheduled_time": "每日 02:00",
        },
        "aoqiwei_supply": {
            "configured": bool(os.getenv("AOQIWEI_APP_KEY") and os.getenv("AOQIWEI_APP_SECRET")),
            "base_url": os.getenv("AOQIWEI_BASE_URL", "https://openapi.acescm.cn"),
            "missing_vars": [v for v in ["AOQIWEI_APP_KEY", "AOQIWEI_APP_SECRET"] if not os.getenv(v)],
            "scheduled_time": "每日 02:15",
            "note": "奥琦玮为供应链数据（库存+采购），POS 订单由 POS 主动推送",
        },
    }

    # 查询 daily_summaries 中各渠道最近同步日期
    try:
        async with get_db_session() as session:
            rows = await session.execute(
                text("""
                    SELECT source,
                           MAX(business_date) AS last_date,
                           SUM(order_count)    AS total_orders,
                           SUM(revenue_cents)  AS total_cents
                    FROM daily_summaries
                    WHERE business_date >= CURRENT_DATE - INTERVAL '7 days'
                    GROUP BY source
                    ORDER BY source
                """)
            )
            for row in rows.fetchall():
                src = row[0]
                key = "aoqiwei_supply" if src == "aoqiwei_supply" else src
                if key in adapters_status:
                    adapters_status[key]["last_sync_date"] = str(row[1]) if row[1] else None
                    adapters_status[key]["recent_7d_orders"] = int(row[2] or 0)
                    adapters_status[key]["recent_7d_revenue_yuan"] = round(float(row[3] or 0) / 100, 2)
    except Exception as exc:
        logger.warning("pos_sync.status_query_failed", error=str(exc))

    return {
        "adapters": adapters_status,
        "queried_at": datetime.now().isoformat(),
    }
