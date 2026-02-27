"""
批量导入 API — Excel 导入订单 / 库存 / 员工
支持 .xlsx / .xls，返回逐行导入结果
"""
import io
import uuid
from datetime import datetime, date
from typing import Any, Dict, List

import pandas as pd
import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from src.core.database import get_db_session
from src.core.dependencies import get_current_user
from src.models.employee import Employee
from src.models.inventory import InventoryItem, InventoryStatus
from src.models.order import Order, OrderItem, OrderStatus
from src.models.user import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/bulk-import", tags=["bulk_import"])

MAX_ROWS = 5000


# ── 工具 ──────────────────────────────────────────────────────

def _read_excel(file_bytes: bytes) -> pd.DataFrame:
    try:
        return pd.read_excel(io.BytesIO(file_bytes), dtype=str).fillna("")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Excel 解析失败: {e}")


def _result(ok: int, fail: int, errors: List[str]) -> Dict[str, Any]:
    return {"success": ok, "failed": fail, "errors": errors[:50]}


# ── 员工导入 ──────────────────────────────────────────────────

@router.post("/employees/{store_id}")
async def import_employees(
    store_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Excel 列（顺序不限，列名精确匹配）：
      员工ID(可选) | 姓名* | 手机 | 邮箱 | 岗位* | 入职日期(YYYY-MM-DD) | 是否在职(1/0)
    """
    raw = await file.read()
    df = _read_excel(raw)
    if len(df) > MAX_ROWS:
        raise HTTPException(status_code=400, detail=f"单次最多导入 {MAX_ROWS} 行")

    ok, fail, errors = 0, 0, []

    async with get_db_session() as session:
        for idx, row in df.iterrows():
            lineno = idx + 2
            try:
                name = row.get("姓名", "").strip()
                position = row.get("岗位", "").strip()
                if not name or not position:
                    raise ValueError("姓名和岗位为必填项")

                emp_id = row.get("员工ID", "").strip() or f"EMP_{uuid.uuid4().hex[:8].upper()}"
                hire_date_str = row.get("入职日期", "").strip()
                hire_date = date.fromisoformat(hire_date_str) if hire_date_str else None
                is_active = str(row.get("是否在职", "1")).strip() not in ("0", "false", "否", "离职")

                from sqlalchemy import select
                existing = await session.execute(select(Employee).where(Employee.id == emp_id))
                emp = existing.scalar_one_or_none()

                if emp:
                    emp.name = name
                    emp.phone = row.get("手机", "").strip() or emp.phone
                    emp.email = row.get("邮箱", "").strip() or emp.email
                    emp.position = position
                    emp.hire_date = hire_date or emp.hire_date
                    emp.is_active = is_active
                else:
                    session.add(Employee(
                        id=emp_id,
                        store_id=store_id,
                        name=name,
                        phone=row.get("手机", "").strip() or None,
                        email=row.get("邮箱", "").strip() or None,
                        position=position,
                        hire_date=hire_date,
                        is_active=is_active,
                    ))
                ok += 1
            except Exception as e:
                fail += 1
                errors.append(f"第{lineno}行: {e}")

        await session.commit()

    logger.info("员工批量导入完成", store_id=store_id, ok=ok, fail=fail)
    return _result(ok, fail, errors)


# ── 库存导入 ──────────────────────────────────────────────────

@router.post("/inventory/{store_id}")
async def import_inventory(
    store_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Excel 列：
      物料ID(可选) | 名称* | 分类 | 单位 | 当前库存* | 最低库存* | 最高库存 | 单价(元) | 供应商 | 供应商联系方式
    """
    raw = await file.read()
    df = _read_excel(raw)
    if len(df) > MAX_ROWS:
        raise HTTPException(status_code=400, detail=f"单次最多导入 {MAX_ROWS} 行")

    ok, fail, errors = 0, 0, []

    async with get_db_session() as session:
        for idx, row in df.iterrows():
            lineno = idx + 2
            try:
                name = row.get("名称", "").strip()
                if not name:
                    raise ValueError("名称为必填项")

                current_qty = float(row.get("当前库存", 0) or 0)
                min_qty = float(row.get("最低库存", 0) or 0)
                max_qty_str = row.get("最高库存", "").strip()
                max_qty = float(max_qty_str) if max_qty_str else None
                unit_price_str = row.get("单价(元)", "").strip()
                unit_cost = int(float(unit_price_str) * 100) if unit_price_str else None

                item_id = row.get("物料ID", "").strip() or f"INV_{uuid.uuid4().hex[:8].upper()}"

                # 计算状态
                if current_qty <= 0:
                    status = InventoryStatus.OUT_OF_STOCK
                elif current_qty <= min_qty * 0.1:
                    status = InventoryStatus.CRITICAL
                elif current_qty <= min_qty:
                    status = InventoryStatus.LOW
                else:
                    status = InventoryStatus.NORMAL

                from sqlalchemy import select
                existing = await session.execute(
                    select(InventoryItem).where(InventoryItem.id == item_id)
                )
                item = existing.scalar_one_or_none()

                if item:
                    item.name = name
                    item.current_quantity = current_qty
                    item.min_quantity = min_qty
                    item.max_quantity = max_qty
                    item.unit_cost = unit_cost
                    item.status = status
                    item.category = row.get("分类", "").strip() or item.category
                    item.unit = row.get("单位", "").strip() or item.unit
                    item.supplier_name = row.get("供应商", "").strip() or item.supplier_name
                    item.supplier_contact = row.get("供应商联系方式", "").strip() or item.supplier_contact
                else:
                    session.add(InventoryItem(
                        id=item_id,
                        store_id=store_id,
                        name=name,
                        category=row.get("分类", "").strip() or None,
                        unit=row.get("单位", "").strip() or None,
                        current_quantity=current_qty,
                        min_quantity=min_qty,
                        max_quantity=max_qty,
                        unit_cost=unit_cost,
                        status=status,
                        supplier_name=row.get("供应商", "").strip() or None,
                        supplier_contact=row.get("供应商联系方式", "").strip() or None,
                    ))
                ok += 1
            except Exception as e:
                fail += 1
                errors.append(f"第{lineno}行: {e}")

        await session.commit()

    logger.info("库存批量导入完成", store_id=store_id, ok=ok, fail=fail)
    return _result(ok, fail, errors)


# ── 订单导入 ──────────────────────────────────────────────────

@router.post("/orders/{store_id}")
async def import_orders(
    store_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Excel 列：
      订单ID(可选) | 桌号 | 客户姓名 | 客户手机 | 状态(默认completed) |
      总金额(元)* | 优惠金额(元) | 实付金额(元)* | 下单时间(YYYY-MM-DD HH:MM:SS) | 备注
    """
    raw = await file.read()
    df = _read_excel(raw)
    if len(df) > MAX_ROWS:
        raise HTTPException(status_code=400, detail=f"单次最多导入 {MAX_ROWS} 行")

    ok, fail, errors = 0, 0, []

    async with get_db_session() as session:
        from sqlalchemy import select
        for idx, row in df.iterrows():
            lineno = idx + 2
            try:
                total_str = row.get("总金额(元)", "").strip()
                final_str = row.get("实付金额(元)", "").strip()
                if not total_str or not final_str:
                    raise ValueError("总金额和实付金额为必填项")

                total_amount = int(float(total_str) * 100)
                final_amount = int(float(final_str) * 100)
                discount_str = row.get("优惠金额(元)", "").strip()
                discount_amount = int(float(discount_str) * 100) if discount_str else 0

                order_time_str = row.get("下单时间", "").strip()
                order_time = (
                    datetime.fromisoformat(order_time_str)
                    if order_time_str
                    else datetime.utcnow()
                )

                status_raw = row.get("状态", "completed").strip().lower()
                valid_statuses = {s.value for s in OrderStatus}
                status = status_raw if status_raw in valid_statuses else OrderStatus.COMPLETED.value

                order_id = row.get("订单ID", "").strip() or (
                    f"IMP_{order_time.strftime('%Y%m%d')}_{uuid.uuid4().hex[:6].upper()}"
                )

                existing = await session.execute(select(Order).where(Order.id == order_id))
                if existing.scalar_one_or_none():
                    ok += 1
                    continue  # 幂等跳过

                session.add(Order(
                    id=order_id,
                    store_id=store_id,
                    table_number=row.get("桌号", "").strip() or None,
                    customer_name=row.get("客户姓名", "").strip() or None,
                    customer_phone=row.get("客户手机", "").strip() or None,
                    status=status,
                    total_amount=total_amount,
                    discount_amount=discount_amount,
                    final_amount=final_amount,
                    order_time=order_time,
                    completed_at=order_time if status == OrderStatus.COMPLETED.value else None,
                    notes=row.get("备注", "").strip() or None,
                    order_metadata={"source": "excel_import"},
                ))
                ok += 1
            except Exception as e:
                fail += 1
                errors.append(f"第{lineno}行: {e}")

        await session.commit()

    logger.info("订单批量导入完成", store_id=store_id, ok=ok, fail=fail)
    return _result(ok, fail, errors)


# ── 模板下载 ──────────────────────────────────────────────────

TEMPLATES = {
    "employees": {
        "columns": ["员工ID", "姓名", "手机", "邮箱", "岗位", "入职日期", "是否在职"],
        "sample": [["EMP001", "张三", "13800138000", "zhangsan@example.com", "服务员", "2024-01-01", "1"]],
    },
    "inventory": {
        "columns": ["物料ID", "名称", "分类", "单位", "当前库存", "最低库存", "最高库存", "单价(元)", "供应商", "供应商联系方式"],
        "sample": [["INV001", "五花肉", "肉类", "kg", "50", "20", "100", "35.5", "XX供应商", "13900139000"]],
    },
    "orders": {
        "columns": ["订单ID", "桌号", "客户姓名", "客户手机", "状态", "总金额(元)", "优惠金额(元)", "实付金额(元)", "下单时间", "备注"],
        "sample": [["", "A01", "李四", "13700137000", "completed", "288.00", "0", "288.00", "2024-01-15 12:30:00", ""]],
    },
}


@router.get("/template/{entity}")
async def download_template(entity: str):
    """下载导入模板（employees / inventory / orders）"""
    if entity not in TEMPLATES:
        raise HTTPException(status_code=404, detail=f"未知模板类型: {entity}")

    tpl = TEMPLATES[entity]
    df = pd.DataFrame(tpl["sample"], columns=tpl["columns"])

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="导入数据")
    buf.seek(0)

    filename = f"import_template_{entity}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
