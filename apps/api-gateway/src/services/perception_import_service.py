"""
感知层半自动导入（L1）：Excel/CSV → 语义标准化 → 写入本体图谱
标准化列名与单位、时间戳(UTC+8)统一，供后续推理层消费。
"""
from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import structlog

from src.ontology import get_ontology_repository, NodeLabel

logger = structlog.get_logger()

# 标准化列名（与模板一致）
COL_STORE_ID = "store_id"
COL_ING_ID = "ing_id"
COL_QTY = "qty"
COL_UNIT = "unit"
COL_TS = "ts"
COL_SOURCE = "source"

# 可选别名（兼容不同导出）
ALIASES = {
    "门店ID": COL_STORE_ID,
    "门店": COL_STORE_ID,
    "食材ID": COL_ING_ID,
    "物料ID": COL_ING_ID,
    "数量": COL_QTY,
    "单位": COL_UNIT,
    "时间": COL_TS,
    "时间戳": COL_TS,
    "来源": COL_SOURCE,
}

MAX_ROWS = 5000


def _normalize_ts(val: Any) -> str:
    """将各种时间格式统一为 ISO 字符串（本地时间视为 UTC+8）。"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    s = str(val).strip()
    if not s:
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    try:
        if re.match(r"^\d{4}-\d{2}-\d{2}", s):
            dt = pd.to_datetime(s)
        else:
            dt = pd.to_datetime(s)
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _normalize_unit(val: Any) -> str:
    """单位标准化：克、g、kg、毫升、ml、L 等保留，空则默认空。"""
    u = str(val).strip().lower() if val is not None else ""
    if not u or pd.isna(val):
        return ""
    return u[:20]


def _read_sheet(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """支持 .xlsx/.xls/.csv，返回统一 DataFrame。"""
    ext = (filename or "").lower().split(".")[-1]
    if ext == "csv":
        return pd.read_csv(io.BytesIO(file_bytes), dtype=str).fillna("")
    try:
        return pd.read_excel(io.BytesIO(file_bytes), dtype=str).fillna("")
    except Exception as e:
        logger.warning("perception_import_read_failed", ext=ext, error=str(e))
        raise ValueError(f"无法解析文件: {e}") from e


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """将中文/别名列名映射为标准列名。"""
    rename = {}
    for c in df.columns:
        c_str = str(c).strip()
        if c_str in ALIASES:
            rename[c] = ALIASES[c_str]
        elif c_str in (COL_STORE_ID, COL_ING_ID, COL_QTY, COL_UNIT, COL_TS, COL_SOURCE):
            rename[c] = c_str
    df = df.rename(columns=rename)
    return df


def import_inventory_snapshots(
    file_bytes: bytes,
    filename: str,
    tenant_id: str,
    default_store_id: str,
) -> Tuple[int, int, List[str]]:
    """
    从 Excel/CSV 导入库存快照到图谱。
    期望列：store_id(或门店ID), ing_id(或食材ID/物料ID), qty(或数量), unit(或单位), ts(或时间), source(或来源)。
    返回 (成功数, 失败数, 错误列表)。
    """
    df = _read_sheet(file_bytes, filename)
    df = _normalize_columns(df)
    if len(df) > MAX_ROWS:
        raise ValueError(f"单次最多导入 {MAX_ROWS} 行")

    repo = get_ontology_repository()
    if not repo:
        raise RuntimeError("Neo4j 本体层未启用")

    ok, fail, errors = 0, 0, []
    for idx, row in df.iterrows():
        lineno = int(idx) + 2
        try:
            store_id = str(row.get(COL_STORE_ID, "") or default_store_id).strip()
            ing_id = str(row.get(COL_ING_ID, "")).strip()
            if not ing_id:
                raise ValueError("ing_id/食材ID/物料ID 为必填")
            qty_val = row.get(COL_QTY, 0) or row.get("数量", 0)
            try:
                qty = float(qty_val)
            except (TypeError, ValueError):
                qty = 0.0
            unit = _normalize_unit(row.get(COL_UNIT) or row.get("单位"))
            ts = _normalize_ts(row.get(COL_TS) or row.get("时间") or row.get("时间戳"))
            source = str(row.get(COL_SOURCE) or row.get("来源") or "manual").strip()[:50]

            repo.merge_inventory_snapshot(
                tenant_id=tenant_id,
                store_id=store_id,
                ing_id=ing_id,
                qty=qty,
                ts=ts,
                source=source or "manual",
                unit=unit,
            )
            ok += 1
        except Exception as e:
            fail += 1
            errors.append(f"第{lineno}行: {e}")
            if len(errors) >= 50:
                break

    logger.info("perception_import_inventory_snapshots_done", ok=ok, fail=fail, tenant_id=tenant_id)
    return ok, fail, errors


def get_inventory_snapshot_template_csv() -> str:
    """返回库存快照标准化模板 CSV 内容（表头 + 一行示例）。"""
    header = "store_id,ing_id,qty,unit,ts,source"
    example = "STORE001,INV_001,100.5,g,2026-02-27T08:00:00,manual"
    return header + "\n" + example + "\n"
