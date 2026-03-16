"""
POS 数据同步验证接口

提供按需触发 POS 数据拉取 + 与实际 POS 后台数据对比验证的功能。
运营人员可通过此接口随时触发同步并查看同步摘要，无需等待凌晨定时任务。

路由前缀：/api/v1/integrations/pos-sync

支持适配器：
  pinzhi        — 品智收银（尝在一起 / 最黔线 / 尚宫厨，每商户独立凭证）
  tiancai       — 天财商龙（MD5 签名版）
  aoqiwei_supply — 奥琦玮供应链（采购 + 库存）
  aoqiwei_crm   — 奥琦玮微生活会员（按手机号增强会员数据）
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from ..core.database import get_db_session
from ..core.dependencies import get_current_active_user
from ..models.integration import ExternalSystem, IntegrationType
from ..models.store import Store
from ..models.user import User

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/integrations/pos-sync",
    tags=["pos-sync"],
)

# ── 动态 import 助手（因 api-adapters 目录含连字符，不能直接 Python import）────
#
# 使用 importlib 在唯一命名空间下加载适配器包，避免与 apps/api-gateway/src 包名冲突。
# 核心思路：以 "_pinzhi_pkg" / "_aoqiwei_pkg" 为包名注册到 sys.modules，
#           再加载子模块，使包内相对 import（from .signature import ...）正常解析。

import importlib.util
import types as _types


def _load_pkg_module(pkg_key: str, pkg_src_dir: str, submodules: list) -> dict:
    """
    将 pkg_src_dir 作为包 pkg_key 注册到 sys.modules，并加载 submodules 列表中的子模块。
    返回 {submodule_name: module} 字典。

    已加载则直接返回缓存，保证幂等。
    """
    if pkg_key not in sys.modules:
        pkg = _types.ModuleType(pkg_key)
        pkg.__path__ = [pkg_src_dir]
        pkg.__package__ = pkg_key
        pkg.__file__ = os.path.join(pkg_src_dir, "__init__.py")
        sys.modules[pkg_key] = pkg

        for name in submodules:
            mod_key = f"{pkg_key}.{name}"
            spec = importlib.util.spec_from_file_location(mod_key, os.path.join(pkg_src_dir, f"{name}.py"))
            if spec is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            mod.__package__ = pkg_key
            sys.modules[mod_key] = mod
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

    return {name: sys.modules[f"{pkg_key}.{name}"] for name in submodules if f"{pkg_key}.{name}" in sys.modules}


def _pinzhi_adapter_class():
    """按需加载品智适配器类（使用独立命名空间，避免与 api-gateway src/ 冲突）。"""
    _src = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../packages/api-adapters/pinzhi/src"))
    mods = _load_pkg_module("_pinzhi_pkg", _src, ["signature", "adapter"])
    return mods["adapter"].PinzhiAdapter


def _aoqiwei_supply_adapter_class():
    """按需加载奥琦玮供应链适配器类。"""
    _src = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../packages/api-adapters/aoqiwei/src"))
    mods = _load_pkg_module("_aoqiwei_pkg", _src, ["adapter", "crm_adapter"])
    return mods["adapter"].AoqiweiAdapter


def _aoqiwei_crm_adapter_class():
    """按需加载奥琦玮 CRM 适配器类。"""
    _src = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../packages/api-adapters/aoqiwei/src"))
    mods = _load_pkg_module("_aoqiwei_pkg", _src, ["adapter", "crm_adapter"])
    return mods["crm_adapter"].AoqiweiCrmAdapter


# ── 请求 / 响应模型 ────────────────────────────────────────────────────────────


class PosSyncRequest(BaseModel):
    """按需同步请求"""

    adapter: str = Field(
        ...,
        description="适配器类型：pinzhi / tiancai / aoqiwei_supply / aoqiwei_crm",
        pattern="^(pinzhi|tiancai|aoqiwei_supply|aoqiwei_crm)$",
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
    orders_in_db: int  # 数据库已有订单数（CRM 场景含义：有记录的手机号数）
    revenue_in_db: float  # 数据库已有营收（元）
    pos_orders: Optional[int]  # POS 返回订单数（CRM 场景：已增强会员数）
    pos_revenue: Optional[float]  # POS 返回营收（元）
    match: Optional[bool]  # 数据是否匹配
    diff_orders: Optional[int]  # 差异订单数
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


# ── 品智同步（多商户，per-store 凭证） ────────────────────────────────────────


async def _sync_pinzhi(sync_date: str, store_ids: Optional[List[str]]) -> PosSyncResponse:
    """
    按需拉取品智 POS 数据并与 DB 对比。

    凭证优先级（高 → 低）：
      1. store.config["pinzhi_base_url"] / ["pinzhi_token"]   ← 门店级 config 覆盖
      2. ExternalSystem 表（provider="pinzhi", store_id=sid）  ← 接入配置管理
      3. 环境变量 PINZHI_BASE_URL / PINZHI_TOKEN              ← 全局兜底

    支持三商户（尝在一起 / 最黔线 / 尚宫厨）各自独立 token。
    """
    global_base_url = os.getenv("PINZHI_BASE_URL", "")
    global_token = os.getenv("PINZHI_TOKEN", "")
    global_brand_id = os.getenv("PINZHI_BRAND_ID", "")

    PinzhiAdapter = _pinzhi_adapter_class()
    store_summaries: List[StoreSyncSummary] = []

    async with get_db_session() as session:
        stmt = select(Store).where(Store.is_active.is_(True))
        if store_ids:
            stmt = stmt.where(Store.id.in_(store_ids))
        result = await session.execute(stmt)
        stores = result.scalars().all()

        # 预加载所有 pinzhi ExternalSystem 记录，减少逐店查询
        ext_rows = await session.execute(
            select(ExternalSystem).where(
                ExternalSystem.provider == "pinzhi",
                ExternalSystem.type == IntegrationType.POS,
            )
        )
        ext_by_store: Dict[str, ExternalSystem] = {str(e.store_id): e for e in ext_rows.scalars().all() if e.store_id}

        for store in stores:
            sid = str(store.id)
            cfg = store.config if isinstance(store.config, dict) else {}
            ext = ext_by_store.get(sid)
            ext_cfg: Dict[str, Any] = ext.config if ext and isinstance(ext.config, dict) else {}

            # 凭证：store.config > ExternalSystem > 环境变量
            store_base_url = (
                cfg.get("pinzhi_base_url")
                or ext_cfg.get("pinzhi_base_url")
                or (ext.api_endpoint if ext else None)
                or global_base_url
            )
            store_token = (
                cfg.get("pinzhi_token")
                or ext_cfg.get("pinzhi_store_token")
                or (ext.api_secret if ext else None)
                or (ext.api_key if ext else None)
                or global_token
            )
            brand_id = cfg.get("pinzhi_brand_id") or ext_cfg.get("brand_id") or global_brand_id
            ognid = (
                cfg.get("pinzhi_ognid") or ext_cfg.get("pinzhi_oms_id") or ext_cfg.get("pinzhi_store_id") or store.code or sid
            )
            if ognid:
                ognid = str(ognid)

            if not store_base_url or not store_token:
                store_summaries.append(
                    StoreSyncSummary(
                        store_id=sid,
                        store_name=getattr(store, "name", sid),
                        orders_in_db=0,
                        revenue_in_db=0.0,
                        pos_orders=None,
                        pos_revenue=None,
                        match=None,
                        diff_orders=None,
                        diff_revenue=None,
                        error="品智凭证未配置（store.config.pinzhi_token 或 PINZHI_TOKEN）",
                    )
                )
                continue

            adapter = PinzhiAdapter(
                {
                    "base_url": store_base_url,
                    "token": store_token,
                    "timeout": int(os.getenv("PINZHI_TIMEOUT", "30")),
                    "retry_times": int(os.getenv("PINZHI_RETRY_TIMES", "3")),
                }
            )

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

            # 2) 从 POS 拉取当日订单（分页）
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

            match = None
            diff_orders = None
            diff_revenue = None
            if error_msg is None:
                diff_orders = pos_orders - db_orders
                diff_revenue = round(pos_revenue - db_revenue, 2)
                match = abs(diff_orders) <= 1 and abs(diff_revenue) < 1.0

            store_summaries.append(
                StoreSyncSummary(
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
                )
            )

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


# ── 天财商龙同步（MD5 签名版）─────────────────────────────────────────────────


async def _sync_tiancai(sync_date: str, store_ids: Optional[List[str]]) -> PosSyncResponse:
    """按需拉取天财商龙数据并与 DB 对比（使用 MD5 签名版适配器）"""
    app_id = os.getenv("TIANCAI_APP_ID", "")
    app_secret = os.getenv("TIANCAI_APP_SECRET", "")

    if not app_id or not app_secret:
        return PosSyncResponse(
            success=False,
            adapter="tiancai",
            sync_date=sync_date,
            triggered_at=datetime.now().isoformat(),
            stores=[],
            totals={},
            skipped_reason="TIANCAI_APP_ID 或 TIANCAI_APP_SECRET 未配置，请在环境变量中设置",
        )

    base_url = os.getenv("TIANCAI_BASE_URL", "https://api.tiancai.com")
    brand_id = os.getenv("TIANCAI_BRAND_ID", "")

    # 使用 packages/api_adapters/tiancai_shanglong（Python 可直接 import 的版本）
    from packages.api_adapters.tiancai_shanglong.src.adapter import TiancaiShanglongAdapter  # type: ignore[import]

    store_summaries: List[StoreSyncSummary] = []

    async with get_db_session() as session:
        stmt = select(Store).where(Store.is_active.is_(True))
        if store_ids:
            stmt = stmt.where(Store.id.in_(store_ids))
        result = await session.execute(stmt)
        stores = result.scalars().all()

        for store in stores:
            sid = str(store.id)
            cfg = store.config if isinstance(store.config, dict) else {}
            store_id_pos = (
                cfg.get("tiancai_store_id")
                or os.getenv(f"TIANCAI_STORE_ID_{sid}")
                or os.getenv("TIANCAI_STORE_ID", "")
                or store.code
                or sid
            )

            adapter = TiancaiShanglongAdapter(
                {
                    "base_url": base_url,
                    "app_id": app_id,
                    "app_secret": app_secret,
                    "store_id": store_id_pos,
                    "brand_id": brand_id,
                    "timeout": 30,
                    "retry_times": 2,
                }
            )

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
                    # ✅ 正确方法名：fetch_orders_by_date（非 query_orders）
                    result_page = await adapter.fetch_orders_by_date(
                        date_str=sync_date,
                        page=page,
                        page_size=100,
                        status=2,  # 2=已支付
                    )
                    items = result_page.get("items", [])
                    if not items:
                        break
                    for raw in items:
                        order_schema = adapter.to_order(raw, sid, brand_id)
                        total_cents = int(order_schema.total * 100)
                        disc_cents = int(order_schema.discount * 100)
                        pos_revenue += float(order_schema.total - order_schema.discount)
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
                    # ✅ 正确退出条件：使用 has_more
                    if not result_page.get("has_more", False):
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

            store_summaries.append(
                StoreSyncSummary(
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
                )
            )

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


# ── 奥琦玮供应链同步 ──────────────────────────────────────────────────────────


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

    AoqiweiAdapter = _aoqiwei_supply_adapter_class()

    adapter = AoqiweiAdapter(
        {
            "app_key": app_key,
            "app_secret": app_secret,
            "timeout": 30,
        }
    )

    store_summaries: List[StoreSyncSummary] = []

    async with get_db_session() as session:
        stmt = select(Store).where(Store.is_active.is_(True))
        if store_ids:
            stmt = stmt.where(Store.id.in_(store_ids))
        result = await session.execute(stmt)
        stores = result.scalars().all()

        for store in stores:
            sid = str(store.id)
            cfg = store.config if isinstance(store.config, dict) else {}
            shop_code = (
                cfg.get("aoqiwei_shop_code")
                or os.getenv(f"AOQIWEI_SHOP_CODE_{sid}")
                or os.getenv("AOQIWEI_SHOP_CODE", "")
                or store.code
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
                logger.error("pos_sync.aoqiwei_supply.store_error", store_id=sid, error=error_msg)

            match = None
            diff_orders = None
            diff_revenue = None
            if error_msg is None:
                diff_orders = pos_orders - db_orders
                diff_revenue = round(pos_revenue - db_revenue, 2)
                match = abs(diff_orders) <= 2 and abs(diff_revenue) < 10.0

            store_summaries.append(
                StoreSyncSummary(
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
                )
            )

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


# ── 奥琦玮微生活会员同步 ──────────────────────────────────────────────────────


async def _sync_aoqiwei_crm(sync_date: str, store_ids: Optional[List[str]]) -> PosSyncResponse:
    """
    奥琦玮微生活会员数据增强。

    逻辑：
      1. 查询各门店近 30 天 orders 中有消费记录的手机号（最多 200/店）
      2. 逐一调用 AoqiweiCrmAdapter.get_member_info(mobile=phone) 获取积分/余额/等级
      3. 将会员信息写入 orders.order_metadata（JSONB merge）
      4. 返回各门店增强摘要

    注意：奥琦玮 CRM 无批量导出 API，仅支持按手机号逐条查询。
    凭证读取顺序：store.config.aoqiwei_crm_appid > ExternalSystem(provider=aoqiwei) > AOQIWEI_CRM_APPID（环境变量）
    """
    global_appid = os.getenv("AOQIWEI_CRM_APPID", "")
    global_appkey = os.getenv("AOQIWEI_CRM_APPKEY", "")

    AoqiweiCrmAdapter = _aoqiwei_crm_adapter_class()
    store_summaries: List[StoreSyncSummary] = []
    total_phones = 0
    total_enriched = 0

    async with get_db_session() as session:
        stmt = select(Store).where(Store.is_active.is_(True))
        if store_ids:
            stmt = stmt.where(Store.id.in_(store_ids))
        result = await session.execute(stmt)
        stores = result.scalars().all()

        # 预加载奥琦玮 CRM ExternalSystem（品牌级，store_id 可为 None）
        crm_ext_rows = await session.execute(
            select(ExternalSystem).where(
                ExternalSystem.provider == "aoqiwei",
                ExternalSystem.type == IntegrationType.MEMBER,
            )
        )
        crm_ext_list = crm_ext_rows.scalars().all()
        # 按 brand_id 分组（config.brand_id）供门店匹配
        crm_ext_by_brand: Dict[str, ExternalSystem] = {}
        crm_ext_global: Optional[ExternalSystem] = None
        for ce in crm_ext_list:
            ce_cfg = ce.config if isinstance(ce.config, dict) else {}
            bid = ce_cfg.get("brand_id")
            if bid:
                crm_ext_by_brand[bid] = ce
            else:
                crm_ext_global = ce

        # 若全局和 ExternalSystem 都无凭证，且 store.config 也没有，则跳过
        has_any_credentials = bool(global_appid or global_appkey or crm_ext_list)
        if not has_any_credentials:
            return PosSyncResponse(
                success=False,
                adapter="aoqiwei_crm",
                sync_date=sync_date,
                triggered_at=datetime.now().isoformat(),
                stores=[],
                totals={},
                skipped_reason="奥琦玮CRM凭证未配置：请在接入配置管理中添加，或设置AOQIWEI_CRM_APPID/APPKEY环境变量",
            )

        for store in stores:
            sid = str(store.id)
            cfg = store.config if isinstance(store.config, dict) else {}
            # 匹配品牌级 ExternalSystem
            brand_id_for_store = cfg.get("pinzhi_brand_id") or getattr(store, "brand_id", None)
            crm_ext = crm_ext_by_brand.get(str(brand_id_for_store) if brand_id_for_store else "") or crm_ext_global
            ext_cfg: Dict[str, Any] = crm_ext.config if crm_ext and isinstance(crm_ext.config, dict) else {}

            # 门店级 CRM 凭证覆盖（store.config > ExternalSystem > 环境变量）
            appid = (
                cfg.get("aoqiwei_crm_appid")
                or ext_cfg.get("aoqiwei_app_id")
                or (crm_ext.api_key if crm_ext else None)
                or global_appid
            )
            appkey = (
                cfg.get("aoqiwei_crm_appkey")
                or ext_cfg.get("aoqiwei_app_key")
                or (crm_ext.api_secret if crm_ext else None)
                or global_appkey
            )
            crm_base_url = (
                ext_cfg.get("base_url")
                or (crm_ext.api_endpoint if crm_ext else None)
                or os.getenv("AOQIWEI_CRM_BASE_URL", "https://api.acewill.net")
            )
            crm_shop_id: Optional[int] = None
            raw_shop_id = cfg.get("aoqiwei_crm_shop_id") or ext_cfg.get("aoqiwei_merchant_id")
            if raw_shop_id:
                try:
                    crm_shop_id = int(raw_shop_id)
                except (ValueError, TypeError):
                    pass

            if not appid or not appkey:
                continue  # 此门店无CRM凭证，跳过

            crm = AoqiweiCrmAdapter(
                {
                    "appid": appid,
                    "appkey": appkey,
                    "base_url": crm_base_url,
                    "timeout": 20,
                    "retry_times": 2,
                }
            )

            # 查近 30 天有消费记录的唯一手机号（最多 200 条，防止超限）
            phones_row = await session.execute(
                text("""
                    SELECT DISTINCT customer_phone
                    FROM orders
                    WHERE store_id = :sid
                      AND customer_phone IS NOT NULL
                      AND customer_phone != ''
                      AND order_time >= CURRENT_DATE - INTERVAL '30 days'
                    ORDER BY customer_phone
                    LIMIT 200
                """),
                {"sid": sid},
            )
            phones = [r[0] for r in phones_row.fetchall()]
            total_phones += len(phones)

            enriched = 0
            error_msg = None
            try:
                for phone in phones:
                    member_data = await crm.get_member_info(
                        mobile=phone,
                        shop_id=crm_shop_id,
                    )
                    if not member_data:
                        continue

                    crm_payload = json.dumps(
                        {
                            "crm_member_level": member_data.get("level_name"),
                            "crm_balance_fen": member_data.get("balance"),
                            "crm_points": member_data.get("point"),
                            "crm_card_no": member_data.get("cno"),
                            "crm_synced_at": sync_date,
                        },
                        ensure_ascii=False,
                    )

                    # JSONB merge：将会员信息写入 order_metadata（PostgreSQL JSON||JSONB→JSON）
                    await session.execute(
                        text("""
                            UPDATE orders
                            SET order_metadata = (
                                    COALESCE(order_metadata, '{}')::jsonb
                                    || :crm_payload::jsonb
                                )::json,
                                updated_at = NOW()
                            WHERE store_id = :sid
                              AND customer_phone = :phone
                              AND order_time >= CURRENT_DATE - INTERVAL '30 days'
                        """),
                        {"sid": sid, "phone": phone, "crm_payload": crm_payload},
                    )
                    enriched += 1

            except Exception as e:
                error_msg = str(e)
                logger.error("pos_sync.aoqiwei_crm.store_error", store_id=sid, error=error_msg)

            await crm.aclose()
            total_enriched += enriched

            store_summaries.append(
                StoreSyncSummary(
                    store_id=sid,
                    store_name=getattr(store, "name", sid),
                    orders_in_db=len(phones),  # 有消费记录的手机号数
                    revenue_in_db=0.0,
                    pos_orders=enriched if error_msg is None else None,  # 已增强会员数
                    pos_revenue=0.0 if error_msg is None else None,
                    match=error_msg is None,
                    diff_orders=(len(phones) - enriched) if error_msg is None else None,
                    diff_revenue=0.0 if error_msg is None else None,
                    error=error_msg,
                )
            )

        await session.commit()

    return PosSyncResponse(
        success=all(s.error is None for s in store_summaries),
        adapter="aoqiwei_crm",
        sync_date=sync_date,
        triggered_at=datetime.now().isoformat(),
        stores=store_summaries,
        totals={
            "stores_processed": len(store_summaries),
            "unique_phones_found": total_phones,
            "members_enriched": total_enriched,
            "note": "奥琦玮CRM无批量API，按手机号逐条查询。diff_orders = 未能匹配到CRM信息的手机号数",
        },
    )


# ── 路由 ──────────────────────────────────────────────────────────────────────

_ADAPTER_HANDLERS = {
    "pinzhi": _sync_pinzhi,
    "tiancai": _sync_tiancai,
    "aoqiwei_supply": _sync_aoqiwei_supply,
    "aoqiwei_crm": _sync_aoqiwei_crm,
}


@router.post("", response_model=PosSyncResponse, summary="按需触发 POS 数据同步并对比")
async def trigger_pos_sync(
    body: PosSyncRequest,
    current_user: User = Depends(get_current_active_user),
) -> PosSyncResponse:
    """
    按需拉取指定 POS 适配器的数据，写入 DB，并返回与 DB 现有数据的对比摘要。

    - **pinzhi**: 品智收银 — 尝在一起 / 最黔线 / 尚宫厨（per-store token）
    - **tiancai**: 天财商龙（MD5签名版）
    - **aoqiwei_supply**: 奥琦玮供应链（采购入库 + 库存快照）
    - **aoqiwei_crm**: 奥琦玮微生活会员（手机号逐一增强积分/余额/等级）
    - **sync_date**: 要同步的日期，默认昨天（YYYY-MM-DD）
    - **store_ids**: 指定门店 ID，为空则同步所有门店
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
    adapters_status: Dict[str, Any] = {
        "pinzhi": {
            "configured": bool(os.getenv("PINZHI_BASE_URL") and os.getenv("PINZHI_TOKEN")),
            "base_url": os.getenv("PINZHI_BASE_URL", ""),
            "missing_vars": [v for v in ["PINZHI_BASE_URL", "PINZHI_TOKEN"] if not os.getenv(v)],
            "scheduled_time": "每日 01:30（订单 + 营业汇总）",
            "merchants": "尝在一起 / 最黔线 / 尚宫厨（各门店可配置独立 pinzhi_token）",
            "data_type": "POS 订单 + 营业汇总",
            "per_store_config": "store.config.pinzhi_base_url / pinzhi_token / pinzhi_ognid",
        },
        "aoqiwei_crm": {
            "configured": bool(os.getenv("AOQIWEI_CRM_APPID") and os.getenv("AOQIWEI_CRM_APPKEY")),
            "base_url": os.getenv("AOQIWEI_CRM_BASE_URL", "https://welcrm.com"),
            "missing_vars": [v for v in ["AOQIWEI_CRM_APPID", "AOQIWEI_CRM_APPKEY"] if not os.getenv(v)],
            "scheduled_time": "每日 02:25（基于近30天订单手机号增强会员积分/余额/等级）",
            "merchants": "尝在一起 / 最黔线 / 尚宫厨（共用或各自门店配置）",
            "data_type": "会员积分 / 储值余额 / 等级（单条查询，无批量导出 API）",
            "per_store_config": "store.config.aoqiwei_crm_appid / aoqiwei_crm_appkey / aoqiwei_crm_shop_id",
            "note": "奥琦玮 CRM 无批量会员列表 API，自动从 orders.customer_phone 提取近30天消费手机号逐一查询。",
        },
        "tiancai": {
            "configured": bool(os.getenv("TIANCAI_APP_ID") and os.getenv("TIANCAI_APP_SECRET")),
            "base_url": os.getenv("TIANCAI_BASE_URL", "https://api.tiancai.com"),
            "missing_vars": [v for v in ["TIANCAI_APP_ID", "TIANCAI_APP_SECRET"] if not os.getenv(v)],
            "scheduled_time": "每日 02:00（订单）",
            "merchants": "最黔线 / 尚宫厨（待确认）",
            "data_type": "POS 订单",
            "per_store_config": "store.config.tiancai_store_id",
        },
        "aoqiwei_supply": {
            "configured": bool(os.getenv("AOQIWEI_APP_KEY") and os.getenv("AOQIWEI_APP_SECRET")),
            "base_url": os.getenv("AOQIWEI_BASE_URL", "https://openapi.acescm.cn"),
            "missing_vars": [v for v in ["AOQIWEI_APP_KEY", "AOQIWEI_APP_SECRET"] if not os.getenv(v)],
            "scheduled_time": "每日 02:15",
            "data_type": "库存 + 采购",
            "per_store_config": "store.config.aoqiwei_shop_code",
            "note": "奥琦玮为供应链数据（库存+采购），POS 订单由 POS 主动推送",
        },
    }

    # 查询 ExternalSystem 表 — env 未配置时以 DB 记录补充 configured 状态
    try:
        async with get_db_session() as session:
            ext_rows = await session.execute(
                select(ExternalSystem).where(
                    ExternalSystem.status == "active",
                )
            )
            for ext in ext_rows.scalars().all():
                provider = str(ext.provider or "")
                if provider == "pinzhi":
                    adapters_status["pinzhi"]["configured"] = True
                    adapters_status["pinzhi"]["config_source"] = "ExternalSystem"
                elif provider in ("aoqiwei", "aoqiwei_crm"):
                    adapters_status["aoqiwei_crm"]["configured"] = True
                    adapters_status["aoqiwei_crm"]["config_source"] = "ExternalSystem"
                elif provider in ("tiancai", "tiancai-shanglong"):
                    adapters_status["tiancai"]["configured"] = True
                    adapters_status["tiancai"]["config_source"] = "ExternalSystem"
                elif provider in ("aoqiwei_supply",):
                    adapters_status["aoqiwei_supply"]["configured"] = True
                    adapters_status["aoqiwei_supply"]["config_source"] = "ExternalSystem"
    except Exception as exc:
        logger.warning("pos_sync.status_ext_query_failed", error=str(exc))

    # 查询 daily_summaries 中各渠道最近同步日期
    try:
        async with get_db_session() as session:
            rows = await session.execute(text("""
                    SELECT source,
                           MAX(business_date) AS last_date,
                           SUM(order_count)    AS total_orders,
                           SUM(revenue_cents)  AS total_cents
                    FROM daily_summaries
                    WHERE business_date >= CURRENT_DATE - INTERVAL '7 days'
                    GROUP BY source
                    ORDER BY source
                """))
            for row in rows.fetchall():
                src = row[0]
                key = "aoqiwei_supply" if src == "aoqiwei_supply" else src
                if key in adapters_status:
                    adapters_status[key]["last_sync_date"] = str(row[1]) if row[1] else None
                    adapters_status[key]["recent_7d_orders"] = int(row[2] or 0)
                    adapters_status[key]["recent_7d_revenue_yuan"] = round(float(row[3] or 0) / 100, 2)

            # 奥琦玮 CRM 近7天增强记录（从 orders.order_metadata 统计）
            crm_row = await session.execute(text("""
                    SELECT COUNT(DISTINCT customer_phone) AS enriched_phones,
                           MAX(updated_at) AS last_updated
                    FROM orders
                    WHERE order_metadata::text LIKE '%crm_synced_at%'
                      AND updated_at >= NOW() - INTERVAL '7 days'
                """))
            crm_data = crm_row.fetchone()
            if crm_data and crm_data[0]:
                adapters_status["aoqiwei_crm"]["recent_7d_phones_enriched"] = int(crm_data[0])
                adapters_status["aoqiwei_crm"]["last_crm_sync_at"] = str(crm_data[1]) if crm_data[1] else None
    except Exception as exc:
        logger.warning("pos_sync.status_query_failed", error=str(exc))

    return {
        "adapters": adapters_status,
        "queried_at": datetime.now().isoformat(),
    }


# ── 每门店集成健康状态 ─────────────────────────────────────────────────────────


@router.get("/status/merchants", summary="查询各商户各门店的 POS 集成健康状态")
async def get_merchants_status(
    brand_id: Optional[str] = Query(None, description="过滤指定品牌，为空返回全部"),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    基于 ExternalSystem 表返回每个门店的接入配置状态，包含：
    - 品智 POS 是否已配置（api_endpoint + api_secret 非空）
    - 奥琦玮 CRM 是否已配置（品牌级）
    - 最近同步时间 last_sync_at / 最近同步状态 last_sync_status / 最近错误 last_error
    - 近 7 天该门店在 DB 中的订单数和营收¥

    可通过 `?brand_id=BRD_CZYZ0001` 过滤单商户。
    """
    merchants: Dict[str, Any] = {}

    async with get_db_session() as session:
        # 拉取所有活跃门店
        store_stmt = select(Store).where(Store.is_active.is_(True))
        if brand_id:
            store_stmt = store_stmt.where(Store.brand_id == brand_id)
        stores_result = await session.execute(store_stmt)
        stores = {str(s.id): s for s in stores_result.scalars().all()}

        # 拉取所有 ExternalSystem（POS + MEMBER）
        ext_result = await session.execute(
            select(ExternalSystem).where(ExternalSystem.type.in_([IntegrationType.POS, IntegrationType.MEMBER]))
        )
        ext_list = ext_result.scalars().all()

        # 按 store_id + provider 组织
        pos_by_store: Dict[str, ExternalSystem] = {}
        crm_by_brand: Dict[str, ExternalSystem] = {}
        for e in ext_list:
            if e.provider == "pinzhi" and e.store_id:
                pos_by_store[str(e.store_id)] = e
            elif e.provider in ("aoqiwei", "aoqiwei_crm"):
                cfg = e.config if isinstance(e.config, dict) else {}
                bid = cfg.get("brand_id", "")
                if bid:
                    crm_by_brand[str(bid)] = e

        # 近 7 天各门店订单数
        order_rows = await session.execute(text("""
                SELECT store_id,
                       COUNT(*)                         AS order_cnt,
                       COALESCE(SUM(final_amount), 0)  AS revenue_cents
                FROM orders
                WHERE order_time >= NOW() - INTERVAL '7 days'
                  AND sales_channel = 'pinzhi'
                GROUP BY store_id
            """))
        orders_by_store: Dict[str, Dict] = {
            str(r[0]): {"order_cnt": int(r[1]), "revenue_yuan": round(float(r[2]) / 100, 2)} for r in order_rows.fetchall()
        }

        for sid, store in stores.items():
            bid = str(getattr(store, "brand_id", "") or "")
            pos_ext = pos_by_store.get(sid)
            crm_ext = crm_by_brand.get(bid)
            store_orders = orders_by_store.get(sid, {"order_cnt": 0, "revenue_yuan": 0.0})

            pos_info: Dict[str, Any] = {"configured": False}
            if pos_ext:
                pos_info = {
                    "configured": bool(pos_ext.api_endpoint and pos_ext.api_secret),
                    "status": str(pos_ext.status.value if hasattr(pos_ext.status, "value") else pos_ext.status),
                    "last_sync_at": str(pos_ext.last_sync_at) if pos_ext.last_sync_at else None,
                    "last_sync_status": (
                        str(
                            pos_ext.last_sync_status.value
                            if hasattr(pos_ext.last_sync_status, "value")
                            else pos_ext.last_sync_status
                        )
                        if pos_ext.last_sync_status
                        else None
                    ),
                    "last_error": pos_ext.last_error,
                }

            crm_info: Dict[str, Any] = {"configured": False}
            if crm_ext:
                crm_info = {
                    "configured": bool(crm_ext.api_key and crm_ext.api_secret),
                    "merchant_id": (crm_ext.config or {}).get("aoqiwei_merchant_id"),
                    "last_sync_at": str(crm_ext.last_sync_at) if crm_ext.last_sync_at else None,
                    "last_error": crm_ext.last_error,
                }

            merchants[sid] = {
                "store_name": store.name,
                "brand_id": bid,
                "city": getattr(store, "city", None),
                "pinzhi_pos": pos_info,
                "aoqiwei_crm": crm_info,
                "recent_7d_orders": store_orders["order_cnt"],
                "recent_7d_revenue_yuan": store_orders["revenue_yuan"],
                "data_flowing": store_orders["order_cnt"] > 0,
            }

    total_configured = sum(1 for m in merchants.values() if m["pinzhi_pos"]["configured"])
    total_flowing = sum(1 for m in merchants.values() if m["data_flowing"])
    return {
        "merchants": merchants,
        "summary": {
            "total_stores": len(merchants),
            "pinzhi_configured": total_configured,
            "data_flowing_stores": total_flowing,
        },
        "queried_at": datetime.now().isoformat(),
    }


# ── 历史数据回填（初次接入时批量拉取）────────────────────────────────────────────


class BackfillRequest(BaseModel):
    adapter: str = Field(
        ...,
        description="适配器类型：pinzhi / aoqiwei_crm",
        pattern="^(pinzhi|tiancai|aoqiwei_supply|aoqiwei_crm)$",
    )
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD（含）")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD（含）")
    store_ids: Optional[List[str]] = Field(None, description="指定门店，为空则全部")
    max_days: int = Field(30, ge=1, le=90, description="最多回填天数，防止误操作过大范围")


class BackfillDaySummary(BaseModel):
    date: str
    success: bool
    stores_processed: int
    total_orders: int
    total_revenue_yuan: float
    error: Optional[str] = None


class BackfillResponse(BaseModel):
    adapter: str
    start_date: str
    end_date: str
    days_requested: int
    days_processed: int
    total_orders_written: int
    total_revenue_yuan: float
    days: List[BackfillDaySummary]
    triggered_at: str


@router.post(
    "/backfill",
    response_model=BackfillResponse,
    summary="历史数据批量回填（新商户初次接入时使用）",
)
async def backfill_history(
    body: BackfillRequest,
    current_user: User = Depends(get_current_active_user),
) -> BackfillResponse:
    """
    新商户初次接入后，批量拉取指定日期范围内的历史订单并写入 DB。

    - 每天单独调用一次 POS 同步（与按需触发逻辑完全一致，幂等）
    - 支持适配器：pinzhi / aoqiwei_crm
    - 最多 90 天，防止误操作
    - 单天失败不中断其他天，在 days[].error 中记录

    **典型用法**（尝在一起接入后回填近30天）：
    ```
    POST /api/v1/integrations/pos-sync/backfill
    {
      "adapter": "pinzhi",
      "start_date": "2026-02-14",
      "end_date":   "2026-03-14",
      "store_ids": ["CZYZ-2461", "CZYZ-7269", "CZYZ-19189"]
    }
    ```
    """
    handler = _ADAPTER_HANDLERS.get(body.adapter)
    if not handler:
        raise HTTPException(status_code=400, detail=f"不支持的适配器: {body.adapter}")

    try:
        start = date.fromisoformat(body.start_date)
        end = date.fromisoformat(body.end_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"日期格式错误（YYYY-MM-DD）: {exc}") from exc

    if end < start:
        raise HTTPException(status_code=400, detail="end_date 不能早于 start_date")

    days_delta = (end - start).days + 1
    if days_delta > body.max_days:
        raise HTTPException(
            status_code=400,
            detail=f"请求天数 {days_delta} 超过 max_days={body.max_days} 限制",
        )

    logger.info(
        "pos_sync.backfill.started",
        adapter=body.adapter,
        start_date=body.start_date,
        end_date=body.end_date,
        days=days_delta,
        user_id=str(getattr(current_user, "id", "unknown")),
    )

    day_results: List[BackfillDaySummary] = []
    total_orders = 0
    total_revenue = 0.0

    current_day = start
    while current_day <= end:
        ds = current_day.strftime("%Y-%m-%d")
        try:
            resp: PosSyncResponse = await handler(ds, body.store_ids)
            day_orders = resp.totals.get("db_total_orders") or sum(s.orders_in_db for s in resp.stores)
            day_revenue = resp.totals.get("db_total_revenue") or sum(s.revenue_in_db for s in resp.stores)
            total_orders += day_orders
            total_revenue += day_revenue
            day_results.append(
                BackfillDaySummary(
                    date=ds,
                    success=resp.success,
                    stores_processed=len(resp.stores),
                    total_orders=day_orders,
                    total_revenue_yuan=round(day_revenue, 2),
                    error=None if resp.success else (resp.skipped_reason or "部分门店失败"),
                )
            )
        except Exception as exc:
            logger.error("pos_sync.backfill.day_error", date=ds, error=str(exc))
            day_results.append(
                BackfillDaySummary(
                    date=ds,
                    success=False,
                    stores_processed=0,
                    total_orders=0,
                    total_revenue_yuan=0.0,
                    error=str(exc),
                )
            )
        current_day += timedelta(days=1)

    return BackfillResponse(
        adapter=body.adapter,
        start_date=body.start_date,
        end_date=body.end_date,
        days_requested=days_delta,
        days_processed=len(day_results),
        total_orders_written=total_orders,
        total_revenue_yuan=round(total_revenue, 2),
        days=day_results,
        triggered_at=datetime.now().isoformat(),
    )
