"""
业财税资金一体化（FCT）集成

供智链OS 其他模块在业务节点（如对账完成、日结）向 FCT 推送业财事件。
合并部署时直接调用 fct_service，避免 HTTP 自调用。
"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import structlog

from src.core.config import settings
from src.core.database import get_db_session

logger = structlog.get_logger()


def _fct_enabled() -> bool:
    return getattr(settings, "FCT_ENABLED", False)


async def push_store_daily_settlement_event(
    entity_id: str,
    biz_date: date,
    total_sales: int,
    tenant_id: str = "default",
    total_sales_tax: int = 0,
    payment_breakdown: Optional[List[Dict[str, Any]]] = None,
    discounts: int = 0,
    source_id: Optional[str] = None,
    event_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    推送门店日结业财事件到 FCT。
    若 FCT 未启用则直接返回 None；否则写入事件并返回 { event_id, voucher_id?, error? }。

    - entity_id: 门店/主体 id（与 store_id 一致）
    - biz_date: 业务日期
    - total_sales: 销售额（分）
    - total_sales_tax: 销项税（分）
    - payment_breakdown: 支付方式明细 [{"method":"wechat","amount":30000}, ...]，缺省时用 [{"method":"pos","amount": total_sales}]
    """
    if not _fct_enabled():
        return None
    payload: Dict[str, Any] = {
        "store_id": entity_id,
        "biz_date": biz_date.isoformat(),
        "total_sales": total_sales,
        "total_sales_tax": total_sales_tax,
        "discounts": discounts,
        "refunds": 0,
    }
    if payment_breakdown is not None:
        payload["payment_breakdown"] = payment_breakdown
    else:
        payload["payment_breakdown"] = [{"method": "pos", "amount": total_sales}]

    body = {
        "event_type": "store_daily_settlement",
        "event_id": event_id,
        "occurred_at": datetime.utcnow().isoformat() + "Z",
        "source_system": "zhilian_os",
        "source_id": source_id,
        "tenant_id": tenant_id,
        "entity_id": entity_id,
        "payload": payload,
    }
    try:
        from src.services.fct_service import fct_service
        async with get_db_session(enable_tenant_isolation=False) as session:
            result = await fct_service.ingest_event(session, body)
        logger.info("FCT 日结事件已推送", entity_id=entity_id, biz_date=biz_date.isoformat(), event_id=result.get("event_id"))
        return result
    except Exception as e:
        logger.warning("FCT 日结事件推送失败", entity_id=entity_id, biz_date=biz_date.isoformat(), error=str(e))
        return {"event_id": body.get("event_id"), "processed": False, "error": str(e)}


async def push_purchase_receipt_event(
    entity_id: str,
    biz_date: date,
    supplier_id: str,
    lines: List[Dict[str, Any]],
    total: int,
    tax: int = 0,
    tenant_id: str = "default",
    source_id: Optional[str] = None,
    event_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    推送采购入库业财事件到 FCT。
    lines: [{"sku":"","name":"","qty":1,"unit_price":100,"tax":0}, ...]，金额单位：分
    """
    if not _fct_enabled():
        return None
    payload = {
        "store_id": entity_id,
        "biz_date": biz_date.isoformat(),
        "supplier_id": supplier_id,
        "lines": lines,
        "total": total,
        "tax": tax,
    }
    body = {
        "event_type": "purchase_receipt",
        "event_id": event_id,
        "occurred_at": datetime.utcnow().isoformat() + "Z",
        "source_system": "zhilian_os",
        "source_id": source_id,
        "tenant_id": tenant_id,
        "entity_id": entity_id,
        "payload": payload,
    }
    try:
        from src.services.fct_service import fct_service
        async with get_db_session(enable_tenant_isolation=False) as session:
            result = await fct_service.ingest_event(session, body)
        logger.info("FCT 采购入库事件已推送", entity_id=entity_id, supplier_id=supplier_id, event_id=result.get("event_id"))
        return result
    except Exception as e:
        logger.warning("FCT 采购入库事件推送失败", entity_id=entity_id, error=str(e))
        return {"event_id": body.get("event_id"), "processed": False, "error": str(e)}
