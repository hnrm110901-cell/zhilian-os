"""
知识库雏形（P2）：损耗规则库、BOM 基准库、异常模式库。
当前为文件存储，便于后续迁入 PG/图谱。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

KNOWLEDGE_TYPES = ("waste_rule", "bom_baseline", "anomaly_pattern")
_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ontology_knowledge.json")


def _load_all(base_path: str = _DEFAULT_PATH) -> List[Dict[str, Any]]:
    path = os.path.abspath(base_path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("ontology_knowledge_load_failed", path=path, error=str(e))
        return []


def _save_all(items: List[Dict[str, Any]], base_path: str = _DEFAULT_PATH) -> None:
    path = os.path.abspath(base_path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def add_knowledge(
    tenant_id: str,
    knowledge_type: str,
    name: str,
    content: Dict[str, Any],
    store_id: Optional[str] = None,
    base_path: str = _DEFAULT_PATH,
) -> Dict[str, Any]:
    """新增一条知识库记录。"""
    if knowledge_type not in KNOWLEDGE_TYPES:
        raise ValueError(f"knowledge_type 须为 {KNOWLEDGE_TYPES} 之一")
    items = _load_all(base_path)
    import uuid
    kid = str(uuid.uuid4())
    from datetime import datetime
    now = datetime.utcnow().isoformat() + "Z"
    record = {
        "id": kid,
        "tenant_id": tenant_id,
        "store_id": store_id or "",
        "type": knowledge_type,
        "name": name,
        "content": content,
        "created_at": now,
        "updated_at": now,
    }
    items.append(record)
    _save_all(items, base_path)
    return record


def list_knowledge(
    tenant_id: str,
    knowledge_type: Optional[str] = None,
    store_id: Optional[str] = None,
    limit: int = 100,
    base_path: str = _DEFAULT_PATH,
) -> List[Dict[str, Any]]:
    """列表查询。"""
    items = _load_all(base_path)
    out = [x for x in items if x.get("tenant_id") == tenant_id]
    if knowledge_type:
        out = [x for x in out if x.get("type") == knowledge_type]
    if store_id:
        out = [x for x in out if (x.get("store_id") or "") == store_id]
    out.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return out[:limit]


def get_knowledge(knowledge_id: str, base_path: str = _DEFAULT_PATH) -> Optional[Dict[str, Any]]:
    """按 id 查询。"""
    items = _load_all(base_path)
    for x in items:
        if x.get("id") == knowledge_id:
            return x
    return None


def update_knowledge(
    knowledge_id: str,
    *,
    name: Optional[str] = None,
    content: Optional[Dict[str, Any]] = None,
    store_id: Optional[str] = None,
    base_path: str = _DEFAULT_PATH,
) -> Optional[Dict[str, Any]]:
    """更新知识库记录（仅更新传入的非 None 字段）。"""
    from datetime import datetime

    items = _load_all(base_path)
    for i, x in enumerate(items):
        if x.get("id") == knowledge_id:
            now = datetime.utcnow().isoformat() + "Z"
            if name is not None:
                items[i]["name"] = name
            if content is not None:
                items[i]["content"] = content
            if store_id is not None:
                items[i]["store_id"] = store_id or ""
            items[i]["updated_at"] = now
            _save_all(items, base_path)
            return items[i]
    return None


def delete_knowledge(knowledge_id: str, base_path: str = _DEFAULT_PATH) -> bool:
    """删除知识库记录。"""
    items = _load_all(base_path)
    for i, x in enumerate(items):
        if x.get("id") == knowledge_id:
            items.pop(i)
            _save_all(items, base_path)
            return True
    return False


def update_knowledge_accuracy(
    root_cause: str,
    effectiveness: float,
    tenant_id: str,
    base_path: str = _DEFAULT_PATH,
) -> int:
    """
    根据培训效果验证结果，更新知识库中对应根因的 waste_rule 记录精度。

    effectiveness: 0–100 的有效性分数（来自 verify_training_effectiveness）。
    accuracy_rate 使用指数移动平均：new = 0.7 * old + 0.3 * effectiveness / 100。
    返回更新的记录数。
    """
    from datetime import datetime

    items = _load_all(base_path)
    updated = 0
    now = datetime.utcnow().isoformat() + "Z"
    for i, x in enumerate(items):
        if tenant_id and x.get("tenant_id") != tenant_id:
            continue
        if x.get("type") != "waste_rule":
            continue
        # 按 content.root_cause 或 name 匹配
        content = x.get("content") or {}
        item_root_cause = content.get("root_cause") or x.get("name") or ""
        if root_cause.lower() not in item_root_cause.lower():
            continue
        old_accuracy = float(x.get("accuracy_rate") or 0.5)
        new_accuracy = round(0.7 * old_accuracy + 0.3 * (effectiveness / 100.0), 4)
        items[i]["accuracy_rate"] = new_accuracy
        items[i]["last_verified_at"] = now
        items[i]["updated_at"] = now
        updated += 1

    if updated:
        _save_all(items, base_path)
    logger.info("knowledge_accuracy_updated", root_cause=root_cause, effectiveness=effectiveness, updated=updated)
    return updated


def distribute_knowledge(
    knowledge_id: str,
    tenant_id: str,
    target_store_ids: List[str],
    base_path: str = _DEFAULT_PATH,
) -> Dict[str, Any]:
    """
    连锁下发：将一条知识复制到多个门店（按 store_id 写入多条记录，内容相同、store_id 不同）。
    若 target_store_ids 为空，则下发到「连锁级」即生成一条 store_id 为空的记录（表示全连锁通用）。
    """
    source = get_knowledge(knowledge_id, base_path)
    if not source:
        return {"ok": False, "error": "未找到该知识库条目", "distributed_count": 0}
    if source.get("tenant_id") != tenant_id:
        return {"ok": False, "error": "租户不一致", "distributed_count": 0}

    created: List[Dict[str, Any]] = []
    if not target_store_ids:
        # 下发到连锁级：一条 store_id 为空的记录（若已存在同 type+name+store_id 空则跳过或覆盖，此处简化为新增）
        rec = add_knowledge(
            tenant_id=tenant_id,
            knowledge_type=source["type"],
            name=source["name"] + "（连锁下发）",
            content=source.get("content") or {},
            store_id=None,
            base_path=base_path,
        )
        created.append(rec)
    else:
        for sid in target_store_ids:
            rec = add_knowledge(
                tenant_id=tenant_id,
                knowledge_type=source["type"],
                name=source["name"],
                content=source.get("content") or {},
                store_id=sid,
                base_path=base_path,
            )
            created.append(rec)
    return {"ok": True, "distributed_count": len(created), "created_ids": [r["id"] for r in created]}
