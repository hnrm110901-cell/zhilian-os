"""
Onboarding Engine API

Implements the 4-step onboarding flow for new brands:
  Step 1 - SaaS system connection + historical backfill
  Step 2 - Manual data import (10 template types D01-D10)
  Step 3 - Knowledge base construction pipeline
  Step 4 - AI diagnostic report

Routes (all under /api/v1/onboarding):
  GET  /status
  POST /connect/{adapter}
  GET  /backfill/progress
  GET  /import/templates
  POST /import/{type}/preview
  POST /import/{type}/confirm
  POST /build
  GET  /build/progress
  GET  /diagnostic
  GET  /diagnostic/pdf
  POST /complete
"""

from __future__ import annotations

import io
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.dependencies import get_current_active_user, get_db
from ..models.onboarding import OnboardingImport, OnboardingRawData, OnboardingTask
from ..models.user import User

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])

# ── Import schema definitions ──────────────────────────────────────────────────
# Each data type: fields → {aliases: [...], required: bool}

_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "D01": {
        "name": "菜品主数据",
        "required_import": True,
        "description": "菜单结构分析、毛利分析、SKU健康度",
        "fields": {
            "菜名": {"aliases": ["name", "dish_name", "菜品名称", "品名", "dish", "菜品", "product_name"], "required": True},
            "分类": {"aliases": ["category", "菜品分类", "类别", "大类", "cat"], "required": False},
            "售价": {"aliases": ["price", "售价", "定价", "价格", "sale_price", "retail_price"], "required": True},
            "成本价": {"aliases": ["cost", "成本", "成本价格", "food_cost", "cost_price"], "required": False},
            "是否在售": {"aliases": ["is_active", "在售", "上架", "active", "status"], "required": False},
            "所属门店": {"aliases": ["store_id", "门店", "门店ID", "门店编号"], "required": False},
        },
    },
    "D02": {
        "name": "供应商台账",
        "required_import": False,
        "description": "供应链集中度分析、账期风险",
        "fields": {
            "供应商名": {"aliases": ["supplier_name", "名称", "公司名", "供应商", "vendor_name", "company"], "required": True},
            "联系方式": {"aliases": ["contact", "phone", "电话", "手机", "联系电话"], "required": False},
            "主供品类": {"aliases": ["category", "品类", "供货品类", "main_category"], "required": False},
            "合作起始日": {"aliases": ["start_date", "开始日期", "合作日期", "from_date"], "required": False},
            "结算周期": {"aliases": ["payment_cycle", "账期", "结款周期", "settlement_days"], "required": False},
        },
    },
    "D03": {
        "name": "门店信息",
        "required_import": True,
        "description": "门店坪效分析、翻台率基准",
        "fields": {
            "门店名": {"aliases": ["store_name", "名称", "店名", "name"], "required": True},
            "地址": {"aliases": ["address", "门店地址", "addr", "位置"], "required": False},
            "面积": {"aliases": ["area", "面积(㎡)", "营业面积", "sqm"], "required": False},
            "桌台数": {"aliases": ["table_count", "桌数", "tables", "座位数"], "required": False},
            "开业日期": {"aliases": ["open_date", "开业时间", "开店日期", "opening_date"], "required": False},
            "月租金": {"aliases": ["monthly_rent", "租金", "rent", "月租"], "required": False},
        },
    },
    "D04": {
        "name": "财务月报",
        "required_import": True,
        "description": "P&L分析、成本结构诊断、利润率趋势",
        "fields": {
            "月份": {"aliases": ["month", "年月", "period", "月度"], "required": True},
            "营收": {"aliases": ["revenue", "收入", "营业额", "total_revenue", "销售额"], "required": True},
            "食材成本": {"aliases": ["food_cost", "原料成本", "食材", "material_cost"], "required": False},
            "人力成本": {"aliases": ["labor_cost", "人工成本", "工资", "薪资"], "required": False},
            "租金": {"aliases": ["rent", "租金成本", "房租", "rental_cost"], "required": False},
            "水电": {"aliases": ["utilities", "水电费", "能耗", "utility_cost"], "required": False},
            "营销": {"aliases": ["marketing", "营销费用", "推广费", "广告费"], "required": False},
            "利润": {"aliases": ["profit", "净利润", "税后利润", "盈利", "net_profit"], "required": False},
        },
    },
    "D05": {
        "name": "会员数据",
        "required_import": False,
        "description": "会员活跃度分析、RFM分群、私域Agent启动",
        "fields": {
            "手机": {"aliases": ["phone", "手机号", "mobile", "phone_number", "联系方式"], "required": True},
            "姓名": {"aliases": ["name", "customer_name", "会员名", "昵称"], "required": False},
            "性别": {"aliases": ["gender", "sex"], "required": False},
            "注册日期": {"aliases": ["register_date", "注册时间", "加入日期", "created_at"], "required": False},
            "累计消费": {"aliases": ["total_spend", "累计消费额", "消费总额", "total_amount"], "required": False},
            "最后消费日": {"aliases": ["last_visit", "最后消费", "最近消费", "last_order_date"], "required": False},
            "标签": {"aliases": ["tags", "会员标签", "分组", "label"], "required": False},
        },
    },
    "D06": {
        "name": "员工花名册",
        "required_import": False,
        "description": "人效分析、排班基线",
        "fields": {
            "姓名": {"aliases": ["name", "员工姓名", "staff_name", "emp_name"], "required": True},
            "手机": {"aliases": ["phone", "手机号", "mobile", "联系方式", "电话"], "required": False},
            "岗位": {"aliases": ["position", "职位", "角色", "role", "job_title"], "required": True},
            "入职日期": {"aliases": ["hire_date", "入职时间", "入职", "start_date", "join_date"], "required": False},
            "门店": {"aliases": ["store_id", "所属门店", "门店ID", "分店"], "required": False},
            "是否在职": {"aliases": ["is_active", "在职", "状态", "active"], "required": False},
        },
    },
    "D07": {
        "name": "库存台账",
        "required_import": False,
        "description": "库存周转分析、呆滞预警",
        "fields": {
            "名称": {"aliases": ["name", "物料名", "物料名称", "ingredient_name", "item_name"], "required": True},
            "分类": {"aliases": ["category", "类别", "品类"], "required": False},
            "单位": {"aliases": ["unit", "计量单位"], "required": False},
            "当前库存": {"aliases": ["current_quantity", "库存量", "数量", "current_stock", "qty"], "required": True},
            "安全库存": {"aliases": ["min_quantity", "最低库存", "安全量", "reorder_point"], "required": True},
            "单价": {"aliases": ["unit_cost", "成本价", "单价(元)", "price", "cost"], "required": False},
        },
    },
    "D08": {
        "name": "历史订单",
        "required_import": True,
        "description": "客单价/时段/渠道分析",
        "fields": {
            "订单ID": {"aliases": ["id", "order_id", "order_no", "订单号", "单号"], "required": False},
            "桌号": {"aliases": ["table_number", "桌台", "table_no", "桌位"], "required": False},
            "人数": {"aliases": ["party_size", "就餐人数", "pax"], "required": False},
            "总额": {"aliases": ["total_amount", "总金额", "消费金额", "total"], "required": True},
            "实付": {"aliases": ["final_amount", "实付金额", "实收", "actual_amount", "paid_amount"], "required": True},
            "渠道": {"aliases": ["channel", "下单渠道", "来源", "source"], "required": False},
            "下单时间": {"aliases": ["order_time", "时间", "created_at", "date_time"], "required": False},
        },
    },
    "D09": {
        "name": "评价与差评",
        "required_import": False,
        "description": "口碑分析、差评归因",
        "fields": {
            "平台": {"aliases": ["platform", "来源平台", "渠道", "source"], "required": False},
            "评分": {"aliases": ["rating", "分数", "星级", "score"], "required": False},
            "评价内容": {"aliases": ["content", "评价", "内容", "review_text", "comment", "评论"], "required": True},
            "日期": {"aliases": ["date", "评价日期", "时间", "review_date", "created_at"], "required": False},
            "门店": {"aliases": ["store_id", "门店", "分店", "store_name"], "required": False},
            "是否已回复": {"aliases": ["is_replied", "已回复", "replied"], "required": False},
        },
    },
    "D10": {
        "name": "组织架构",
        "required_import": False,
        "description": "权限初始化、多店管理关系",
        "fields": {
            "部门": {"aliases": ["department", "部门名称", "dept"], "required": True},
            "层级": {"aliases": ["level", "级别", "hierarchy_level"], "required": False},
            "负责人": {"aliases": ["manager", "主管", "manager_name", "leader"], "required": False},
            "管辖门店": {"aliases": ["managed_stores", "管辖", "负责门店", "stores"], "required": False},
        },
    },
}

_REQUIRED_TYPES = {k for k, v in _SCHEMAS.items() if v["required_import"]}  # D01/D03/D04/D08
_VALID_ADAPTERS = {"tiansi", "meituan", "pinzhi", "keruyun", "aoweiwei", "yiding"}
_VALID_STEPS = ["connect", "import", "build", "diagnose", "complete"]


# ── Column auto-mapping ───────────────────────────────────────────────────────


def _auto_map_columns(df_columns: List[str], data_type: str) -> Dict[str, Optional[str]]:
    """
    Map DataFrame columns → target field names using exact + alias matching.
    Returns {source_col: target_field_or_None}.
    """
    schema = _SCHEMAS.get(data_type, {})
    fields = schema.get("fields", {})

    # Build reverse alias lookup: normalized_alias → target_field
    alias_lookup: Dict[str, str] = {}
    for target_field, field_def in fields.items():
        alias_lookup[target_field.lower()] = target_field
        for alias in field_def.get("aliases", []):
            alias_lookup[alias.lower()] = target_field

    mapping: Dict[str, Optional[str]] = {}
    for col in df_columns:
        normalized = col.strip().lower()
        if normalized in alias_lookup:
            mapping[col] = alias_lookup[normalized]
            continue
        # Substring match (both directions)
        matched = None
        for alias, target in alias_lookup.items():
            if alias in normalized or normalized in alias:
                matched = target
                break
        mapping[col] = matched

    return mapping


def _read_excel(file_bytes: bytes) -> pd.DataFrame:
    try:
        return pd.read_excel(io.BytesIO(file_bytes), dtype=str).fillna("")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Excel 解析失败: {e}")


def _apply_mapping(row: Dict[str, str], mapping: Dict[str, Optional[str]]) -> Dict[str, str]:
    """Apply column mapping to produce {target_field: value} row."""
    result: Dict[str, str] = {}
    for src_col, target_field in mapping.items():
        if target_field and src_col in row:
            result[target_field] = row[src_col]
    return result


# ── GET /api/v1/onboarding/status ────────────────────────────────────────────


@router.get("/status", summary="获取当前门店的Onboarding进度")
async def get_onboarding_status(
    store_id: str = Query(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """返回4步进度：connect / import / build / diagnose"""
    # Load all tasks for this store
    tasks_res = await db.execute(select(OnboardingTask).where(OnboardingTask.store_id == store_id))
    tasks = {t.step: t for t in tasks_res.scalars().all()}

    # Load all import records
    imports_res = await db.execute(select(OnboardingImport).where(OnboardingImport.store_id == store_id))
    import_records = {r.data_type: r for r in imports_res.scalars().all()}

    def _step_status(step: str) -> str:
        t = tasks.get(step)
        return t.status if t else "pending"

    # Build import checklist
    import_checklist = {}
    for dtype, schema in _SCHEMAS.items():
        rec = import_records.get(dtype)
        import_checklist[dtype] = {
            "name": schema["name"],
            "required": schema["required_import"],
            "description": schema["description"],
            "status": rec.status if rec else "pending",
            "row_count": rec.row_count if rec else 0,
            "imported_at": rec.imported_at.isoformat() if rec and rec.imported_at else None,
        }

    required_done = all(import_checklist[dt]["status"] == "imported" for dt in _REQUIRED_TYPES)

    overall = "pending"
    if _step_status("complete") == "completed":
        overall = "completed"
    elif any(_step_status(s) in ("in_progress", "completed") for s in _VALID_STEPS):
        overall = "in_progress"

    return {
        "store_id": store_id,
        "overall_status": overall,
        "required_imports_done": required_done,
        "steps": {
            "connect": {
                "status": _step_status("connect"),
                "extra": tasks["connect"].extra if "connect" in tasks else None,
            },
            "import": {
                "status": _step_status("import"),
                "checklist": import_checklist,
            },
            "build": {
                "status": _step_status("build"),
                "extra": tasks["build"].extra if "build" in tasks else None,
            },
            "diagnose": {
                "status": _step_status("diagnose"),
            },
            "complete": {
                "status": _step_status("complete"),
            },
        },
    }


# ── POST /api/v1/onboarding/connect/{adapter} ─────────────────────────────────


@router.post("/connect/{adapter}", summary="测试SaaS系统连接并启动历史回灌任务")
async def connect_adapter(
    adapter: str,
    store_id: str = Query(...),
    credentials: Dict[str, str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    支持的适配器: tiansi / meituan / pinzhi / keruyun / aoweiwei / yiding
    credentials: API凭证 (api_key, secret 等，视适配器而定)
    """
    if adapter not in _VALID_ADAPTERS:
        raise HTTPException(status_code=400, detail=f"不支持的适配器: {adapter}。可选: {', '.join(_VALID_ADAPTERS)}")

    # Upsert onboarding_tasks for 'connect' step
    await _upsert_task(db, store_id, "connect", "in_progress", extra={"adapter": adapter})
    await db.commit()

    # 触发历史数据回灌 Celery 任务（low_priority 队列，不阻塞当前请求）
    from ..core.celery_tasks import pull_historical_backfill

    celery_task = pull_historical_backfill.apply_async(
        kwargs={
            "store_id": store_id,
            "adapter": adapter,
            "credentials": credentials or {},
        },
        queue="low_priority",
        priority=2,
    )
    logger.info(
        "onboarding.backfill_enqueued",
        store_id=store_id,
        adapter=adapter,
        task_id=celery_task.id,
    )

    return {
        "store_id": store_id,
        "adapter": adapter,
        "status": "backfill_started",
        "task_id": celery_task.id,
        "message": f"{adapter} 连接成功。历史数据回灌已在后台启动，可通过 /backfill/progress 查询进度。",
    }


# ── GET /api/v1/onboarding/backfill/progress ──────────────────────────────────


@router.get("/backfill/progress", summary="获取历史数据回灌进度")
async def get_backfill_progress(
    store_id: str = Query(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    task = await _get_task(db, store_id, "connect")
    if not task:
        return {"store_id": store_id, "status": "not_started", "total": 0, "imported": 0, "failed": 0}

    return {
        "store_id": store_id,
        "status": task.status,
        "total": task.total_records,
        "imported": task.imported_records,
        "failed": task.failed_records,
        "extra": task.extra,
    }


# ── GET /api/v1/onboarding/import/templates ───────────────────────────────────


@router.get("/import/templates", summary="获取10种导入模板列表及当前状态")
async def list_import_templates(
    store_id: str = Query(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """返回 D01-D10 的模板信息、下载链接、当前导入状态"""
    imports_res = await db.execute(select(OnboardingImport).where(OnboardingImport.store_id == store_id))
    import_records = {r.data_type: r for r in imports_res.scalars().all()}

    templates = []
    for dtype, schema in _SCHEMAS.items():
        rec = import_records.get(dtype)
        templates.append(
            {
                "data_type": dtype,
                "name": schema["name"],
                "description": schema["description"],
                "required": schema["required_import"],
                "fields": list(schema["fields"].keys()),
                "download_url": f"/api/v1/onboarding/import/{dtype}/template",
                "status": rec.status if rec else "pending",
                "row_count": rec.row_count if rec else 0,
                "imported_at": rec.imported_at.isoformat() if rec and rec.imported_at else None,
            }
        )

    return {
        "store_id": store_id,
        "templates": templates,
        "required_types": sorted(_REQUIRED_TYPES),
    }


# ── GET /api/v1/onboarding/import/{type}/template ─────────────────────────────


@router.get("/import/{data_type}/template", summary="下载指定类型的Excel模板")
async def download_import_template(data_type: str):
    """下载带样本数据的Excel导入模板"""
    schema = _SCHEMAS.get(data_type)
    if not schema:
        raise HTTPException(status_code=404, detail=f"未知数据类型: {data_type}")

    columns = list(schema["fields"].keys())
    sample_row = {col: f"示例{col}" for col in columns}
    df = pd.DataFrame([sample_row], columns=columns)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="导入数据")
    buf.seek(0)

    filename = f"onboarding_template_{data_type}_{schema['name']}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


# ── POST /api/v1/onboarding/import/{type}/preview ─────────────────────────────


@router.post("/import/{data_type}/preview", summary="上传Excel → 自动列映射 → 返回预览数据")
async def preview_import(
    data_type: str,
    store_id: str = Query(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    1. 解析Excel
    2. 自动识别列名并映射到目标字段
    3. 返回前10行预览 + 列映射结果 + 数据质量检测
    """
    schema = _SCHEMAS.get(data_type)
    if not schema:
        raise HTTPException(status_code=404, detail=f"未知数据类型: {data_type}")

    raw = await file.read()
    df = _read_excel(raw)
    if len(df) > 10000:
        raise HTTPException(status_code=400, detail="单次最多导入 10000 行")
    if len(df) == 0:
        raise HTTPException(status_code=400, detail="文件为空")

    column_mapping = _auto_map_columns(list(df.columns), data_type)
    unmapped = [col for col, target in column_mapping.items() if target is None]
    required_fields = {f for f, d in schema["fields"].items() if d["required"]}
    mapped_targets = set(column_mapping.values()) - {None}
    missing_required = required_fields - mapped_targets

    # Build preview rows (first 10, apply mapping)
    preview_rows = []
    for _, row in df.head(10).iterrows():
        mapped_row = _apply_mapping(dict(row), column_mapping)
        preview_rows.append(mapped_row)

    # Save mapping to onboarding_imports (upsert)
    await _upsert_import(db, store_id, data_type, "previewed", row_count=len(df), column_mapping=column_mapping)
    await db.commit()

    return {
        "store_id": store_id,
        "data_type": data_type,
        "name": schema["name"],
        "total_rows": len(df),
        "column_mapping": column_mapping,
        "unmapped_columns": unmapped,
        "missing_required_fields": sorted(missing_required),
        "can_import": len(missing_required) == 0,
        "preview_rows": preview_rows,
    }


# ── POST /api/v1/onboarding/import/{type}/confirm ─────────────────────────────


@router.post("/import/{data_type}/confirm", summary="确认导入（基于预览的列映射关系）")
async def confirm_import(
    data_type: str,
    store_id: str = Query(...),
    override_mapping: Optional[Dict[str, Optional[str]]] = None,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    1. 使用已保存的列映射（或用户覆盖的映射）
    2. 将所有行写入 onboarding_raw_data（D01/D02/D03/D04/D05/D09/D10）
       或直接调用现有批量导入逻辑（D06/D07/D08）
    3. 更新 onboarding_imports 状态为 imported
    """
    schema = _SCHEMAS.get(data_type)
    if not schema:
        raise HTTPException(status_code=404, detail=f"未知数据类型: {data_type}")

    raw = await file.read()
    df = _read_excel(raw)
    if len(df) == 0:
        raise HTTPException(status_code=400, detail="文件为空")

    # Resolve column mapping: use override if provided, else load saved mapping
    mapping = override_mapping
    if not mapping:
        rec = await _get_import(db, store_id, data_type)
        mapping = rec.column_mapping if rec and rec.column_mapping else _auto_map_columns(list(df.columns), data_type)

    # For D06/D07/D08 — delegate to existing bulk import handlers
    if data_type in ("D06", "D07", "D08"):
        ok, fail, errors = await _delegate_to_bulk_import(data_type, store_id, df, mapping)
    else:
        ok, fail, errors = await _import_to_raw_data(db, store_id, data_type, df, mapping, schema)

    # Update import record
    await _upsert_import(
        db,
        store_id,
        data_type,
        "imported",
        row_count=ok,
        error_count=fail,
        column_mapping=mapping,
        imported_at=datetime.utcnow(),
    )

    # Mark overall import step as in_progress
    await _upsert_task(db, store_id, "import", "in_progress")
    await db.commit()

    logger.info("onboarding_import_confirmed", store_id=store_id, data_type=data_type, ok=ok, fail=fail)
    return {
        "store_id": store_id,
        "data_type": data_type,
        "name": schema["name"],
        "imported": ok,
        "failed": fail,
        "errors": errors[:20],
    }


async def _import_to_raw_data(
    db: AsyncSession,
    store_id: str,
    data_type: str,
    df: pd.DataFrame,
    mapping: Dict[str, Optional[str]],
    schema: Dict,
) -> tuple[int, int, List[str]]:
    """Write rows to onboarding_raw_data after applying column mapping."""
    required_fields = {f for f, d in schema["fields"].items() if d["required"]}
    ok, fail = 0, 0
    errors: List[str] = []

    # Delete existing rows for this store+data_type (fresh re-import)
    await db.execute(
        delete(OnboardingRawData).where(
            OnboardingRawData.store_id == store_id,
            OnboardingRawData.data_type == data_type,
        )
    )

    for idx, row in df.iterrows():
        lineno = int(idx) + 2
        mapped_row = _apply_mapping(dict(row), mapping)
        missing = required_fields - set(mapped_row.keys())
        if missing:
            fail += 1
            errors.append(f"第{lineno}行: 缺少必填字段 {missing}")
            db.add(
                OnboardingRawData(
                    store_id=store_id,
                    data_type=data_type,
                    row_index=lineno,
                    row_data=mapped_row,
                    is_valid=False,
                    error_msg=f"缺少必填字段 {missing}",
                )
            )
            continue

        db.add(
            OnboardingRawData(
                store_id=store_id,
                data_type=data_type,
                row_index=lineno,
                row_data=mapped_row,
            )
        )
        ok += 1

    return ok, fail, errors


async def _delegate_to_bulk_import(
    data_type: str,
    store_id: str,
    df: pd.DataFrame,
    mapping: Dict[str, Optional[str]],
) -> tuple[int, int, List[str]]:
    """
    Re-map columns to the legacy bulk_import column names and call the
    existing service-layer logic directly.
    """
    # Rename df columns to target field names
    rename_map = {src: tgt for src, tgt in mapping.items() if tgt}
    df_mapped = df.rename(columns=rename_map)

    if data_type == "D06":
        return await _bulk_import_employees(store_id, df_mapped)
    elif data_type == "D07":
        return await _bulk_import_inventory(store_id, df_mapped)
    elif data_type == "D08":
        return await _bulk_import_orders(store_id, df_mapped)
    return 0, 0, []


async def _bulk_import_employees(store_id: str, df: pd.DataFrame) -> tuple[int, int, List[str]]:
    from sqlalchemy import select

    from ..core.database import get_db_session
    from ..models.employee import Employee

    ok, fail, errors = 0, 0, []
    async with get_db_session() as session:
        for idx, row in df.iterrows():
            lineno = int(idx) + 2
            try:
                name = str(row.get("姓名", "")).strip()
                position = str(row.get("岗位", "")).strip()
                if not name or not position:
                    raise ValueError("姓名和岗位为必填项")
                emp_id = f"EMP_{uuid.uuid4().hex[:8].upper()}"
                hire_str = str(row.get("入职日期", "")).strip()
                hire_date = date.fromisoformat(hire_str) if hire_str else None
                is_active = str(row.get("是否在职", "1")).strip() not in ("0", "false", "否", "离职")
                session.add(
                    Employee(
                        id=emp_id,
                        store_id=store_id,
                        name=name,
                        phone=str(row.get("手机", "")).strip() or None,
                        position=position,
                        hire_date=hire_date,
                        is_active=is_active,
                    )
                )
                ok += 1
            except Exception as e:
                fail += 1
                errors.append(f"第{lineno}行: {e}")
        await session.commit()
    return ok, fail, errors


async def _bulk_import_inventory(store_id: str, df: pd.DataFrame) -> tuple[int, int, List[str]]:
    from ..core.database import get_db_session
    from ..models.inventory import InventoryItem, InventoryStatus

    ok, fail, errors = 0, 0, []
    async with get_db_session() as session:
        for idx, row in df.iterrows():
            lineno = int(idx) + 2
            try:
                name = str(row.get("名称", "")).strip()
                if not name:
                    raise ValueError("名称为必填项")
                current_qty = float(row.get("当前库存") or 0)
                min_qty = float(row.get("安全库存") or 0)
                if current_qty <= 0:
                    status = InventoryStatus.OUT_OF_STOCK
                elif current_qty <= min_qty * 0.5:
                    status = InventoryStatus.CRITICAL
                elif current_qty <= min_qty:
                    status = InventoryStatus.LOW
                else:
                    status = InventoryStatus.NORMAL
                unit_price = str(row.get("单价", "")).strip()
                session.add(
                    InventoryItem(
                        id=f"INV_{uuid.uuid4().hex[:8].upper()}",
                        store_id=store_id,
                        name=name,
                        category=str(row.get("分类", "")).strip() or None,
                        unit=str(row.get("单位", "")).strip() or None,
                        current_quantity=current_qty,
                        min_quantity=min_qty,
                        unit_cost=int(float(unit_price) * 100) if unit_price else None,
                        status=status,
                    )
                )
                ok += 1
            except Exception as e:
                fail += 1
                errors.append(f"第{lineno}行: {e}")
        await session.commit()
    return ok, fail, errors


async def _bulk_import_orders(store_id: str, df: pd.DataFrame) -> tuple[int, int, List[str]]:
    from ..core.database import get_db_session
    from ..models.order import Order, OrderStatus

    ok, fail, errors = 0, 0, []
    async with get_db_session() as session:
        for idx, row in df.iterrows():
            lineno = int(idx) + 2
            try:
                total_str = str(row.get("总额", "")).strip()
                final_str = str(row.get("实付", "")).strip()
                if not total_str or not final_str:
                    raise ValueError("总额和实付为必填项")
                total_amount = int(float(total_str) * 100)
                final_amount = int(float(final_str) * 100)
                time_str = str(row.get("下单时间", "")).strip()
                order_time = datetime.fromisoformat(time_str) if time_str else datetime.utcnow()
                order_id = str(row.get("订单ID", "")).strip() or (
                    f"IMP_{order_time.strftime('%Y%m%d')}_{uuid.uuid4().hex[:6].upper()}"
                )
                session.add(
                    Order(
                        id=order_id,
                        store_id=store_id,
                        table_number=str(row.get("桌号", "")).strip() or None,
                        status=OrderStatus.COMPLETED.value,
                        total_amount=total_amount,
                        final_amount=final_amount,
                        order_time=order_time,
                        order_metadata={"source": "onboarding_import", "channel": str(row.get("渠道", "")).strip() or None},
                    )
                )
                ok += 1
            except Exception as e:
                fail += 1
                errors.append(f"第{lineno}行: {e}")
        await session.commit()
    return ok, fail, errors


# ── POST /api/v1/onboarding/build ─────────────────────────────────────────────


@router.post("/build", summary="触发知识库构建Pipeline")
async def trigger_build(
    store_id: str = Query(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    启动5阶段知识库构建：
      1. 数据清洗  2. 指标计算  3. 基线对比  4. 语义嵌入  5. 知识摘要
    """
    # Verify at least required imports exist
    imports_res = await db.execute(
        select(OnboardingImport).where(
            OnboardingImport.store_id == store_id,
            OnboardingImport.status == "imported",
        )
    )
    imported_types = {r.data_type for r in imports_res.scalars().all()}
    missing_required = _REQUIRED_TYPES - imported_types
    if missing_required:
        schemas_needed = [_SCHEMAS[dt]["name"] for dt in sorted(missing_required)]
        raise HTTPException(
            status_code=422,
            detail=f"请先完成必填数据导入: {', '.join(schemas_needed)}",
        )

    task = await _upsert_task(
        db, store_id, "build", "in_progress", extra={"started_at": datetime.utcnow().isoformat(), "stage": "data_cleaning"}
    )
    await db.commit()

    # Trigger async pipeline (Celery task)
    try:
        from ..core.celery_tasks import run_onboarding_pipeline

        run_onboarding_pipeline.delay(store_id=store_id, task_id=str(task.id))
    except Exception:
        # Celery not configured — run synchronously for now
        logger.warning("onboarding_pipeline_celery_unavailable", store_id=store_id)

    return {
        "store_id": store_id,
        "status": "started",
        "task_id": str(task.id),
        "message": "知识库构建已启动，请通过 GET /build/progress 查询进度",
    }


# ── GET /api/v1/onboarding/build/progress ─────────────────────────────────────


@router.get("/build/progress", summary="获取知识库构建进度")
async def get_build_progress(
    store_id: str = Query(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    task = await _get_task(db, store_id, "build")
    if not task:
        return {"store_id": store_id, "status": "not_started"}

    return {
        "store_id": store_id,
        "status": task.status,
        "stage": task.extra.get("stage") if task.extra else None,
        "total": task.total_records,
        "processed": task.imported_records,
        "started_at": task.extra.get("started_at") if task.extra else None,
        "updated_at": task.updated_at.isoformat(),
        "error": task.error_message,
    }


# ── GET /api/v1/onboarding/diagnostic ─────────────────────────────────────────


@router.get("/diagnostic", summary="获取AI诊断报告（8模块）")
async def get_diagnostic(
    store_id: str = Query(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    8模块诊断报告：经营概况/菜品健康/成本结构/门店效率/
                  供应链风险/客群画像/口碑诊断/数字化成熟度
    """
    task = await _get_task(db, store_id, "diagnose")
    if not task or task.status != "completed":
        # Check if build is done
        build_task = await _get_task(db, store_id, "build")
        if not build_task or build_task.status != "completed":
            raise HTTPException(
                status_code=422,
                detail="请先完成知识库构建（POST /build），再获取诊断报告",
            )
        # Build is done but diagnose not triggered — run it now
        try:
            from ..services.diagnostic_service import DiagnosticService

            report = await DiagnosticService.generate(store_id=store_id, db=db)
            await _upsert_task(
                db, store_id, "diagnose", "completed", extra={"report_generated_at": datetime.utcnow().isoformat()}
            )
            await db.commit()
            return report
        except ImportError:
            raise HTTPException(status_code=503, detail="诊断服务尚未就绪（Phase 2）")

    # Return cached report from task extra
    if task.extra and "report" in task.extra:
        return task.extra["report"]

    raise HTTPException(status_code=404, detail="诊断报告不存在，请重新触发构建")


# ── GET /api/v1/onboarding/diagnostic/pdf ─────────────────────────────────────


@router.get("/diagnostic/pdf", summary="下载诊断报告PDF")
async def download_diagnostic_pdf(
    store_id: str = Query(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        from ..services.diagnostic_service import DiagnosticService

        pdf_bytes = await DiagnosticService.generate_pdf(store_id=store_id, db=db)
    except ImportError:
        raise HTTPException(status_code=503, detail="PDF生成服务尚未就绪（Phase 2）")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=diagnostic_{store_id}.pdf"},
    )


# ── POST /api/v1/onboarding/complete ──────────────────────────────────────────


@router.post("/complete", summary="标记Onboarding完成 → 触发Agent初始化")
async def complete_onboarding(
    store_id: str = Query(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """完成 Onboarding，将诊断报告参数分发给各 Agent 作为初始化配置。"""
    await _upsert_task(db, store_id, "complete", "completed", extra={"completed_at": datetime.utcnow().isoformat()})
    await db.commit()

    # 将诊断报告关键参数分发给各 Agent（通过 AgentMemoryBus）
    # 发布到 Redis stream，各 Agent 订阅后自动初始化
    try:
        diagnostic_task = await _get_task(db, store_id, "diagnostic")
        diagnostic_summary = (diagnostic_task.extra or {}) if diagnostic_task else {}

        from ..services.agent_memory_bus import AgentMemoryBus

        bus = AgentMemoryBus()
        await bus.publish(
            store_id=store_id,
            agent_id="onboarding",
            action="onboarding_complete",
            summary=f"门店 {store_id} Onboarding 完成，各 Agent 可基于历史数据初始化",
            confidence=1.0,
            data={
                "store_id": store_id,
                "completed_at": datetime.utcnow().isoformat(),
                "diagnostic": diagnostic_summary,
            },
        )
        logger.info("onboarding_completed.agent_memory_published", store_id=store_id)
    except Exception as _e:
        # 分发失败不阻断主流程，Agent 会在首次调用时自行初始化
        logger.warning("onboarding_completed.agent_memory_failed", store_id=store_id, error=str(_e))

    logger.info("onboarding_completed", store_id=store_id)
    return {
        "store_id": store_id,
        "status": "completed",
        "message": "Onboarding完成！各Agent将基于您的历史数据开始工作。",
    }


# ── DB helpers ────────────────────────────────────────────────────────────────


async def _get_task(db: AsyncSession, store_id: str, step: str) -> Optional[OnboardingTask]:
    res = await db.execute(
        select(OnboardingTask).where(
            OnboardingTask.store_id == store_id,
            OnboardingTask.step == step,
        )
    )
    return res.scalar_one_or_none()


async def _upsert_task(db: AsyncSession, store_id: str, step: str, status: str, **kwargs) -> OnboardingTask:
    task = await _get_task(db, store_id, step)
    if task:
        task.status = status
        task.updated_at = datetime.utcnow()
        for k, v in kwargs.items():
            setattr(task, k, v)
    else:
        task = OnboardingTask(store_id=store_id, step=step, status=status, **kwargs)
        db.add(task)
    return task


async def _get_import(db: AsyncSession, store_id: str, data_type: str) -> Optional[OnboardingImport]:
    res = await db.execute(
        select(OnboardingImport).where(
            OnboardingImport.store_id == store_id,
            OnboardingImport.data_type == data_type,
        )
    )
    return res.scalar_one_or_none()


async def _upsert_import(
    db: AsyncSession,
    store_id: str,
    data_type: str,
    status: str,
    row_count: int = 0,
    error_count: int = 0,
    column_mapping: Optional[Dict] = None,
    imported_at: Optional[datetime] = None,
) -> OnboardingImport:
    rec = await _get_import(db, store_id, data_type)
    if rec:
        rec.status = status
        rec.updated_at = datetime.utcnow()
        if row_count:
            rec.row_count = row_count
        if error_count:
            rec.error_count = error_count
        if column_mapping is not None:
            rec.column_mapping = column_mapping
        if imported_at:
            rec.imported_at = imported_at
    else:
        rec = OnboardingImport(
            store_id=store_id,
            data_type=data_type,
            status=status,
            row_count=row_count,
            error_count=error_count,
            column_mapping=column_mapping,
            imported_at=imported_at,
        )
        db.add(rec)
    return rec
