"""
本体自然语言查询（L3）：自然语言 → 意图识别 → 图谱/推理 → 结构化答案 + 溯源
使用意图+参数方式，不直接生成 Cypher，避免注入。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog

from src.ontology import get_ontology_repository

logger = structlog.get_logger()

# 意图与预定义 Cypher / 服务映射
ONTOLOGY_SCHEMA_DESC = """
图谱节点: Store(store_id,name), Dish(dish_id,name,store_id), Ingredient(ing_id,name,unit),
BOM(bom_id,dish_id,version,effective_date), InventorySnapshot(snapshot_id,store_id,ing_id,qty,ts,source),
Order(order_id,store_id), Staff(staff_id), Supplier(sup_id), Action(action_id,status).
关系: (Dish)-[:HAS_BOM]->(BOM), (BOM)-[:REQUIRES {qty,unit}]->(Ingredient),
(Order)-[:CONTAINS]->(Dish), (InventorySnapshot)-[:LOCATED_AT]->(Ingredient).
"""

INTENT_PROMPT = """你是指令助手。根据用户关于餐厅运营的问题，输出唯一一个 JSON，不要其他文字。
可选 intent 及含义:
- list_stores: 查门店列表
- dish_bom: 某菜品的配方/用料
- list_dishes: 某门店的菜品列表
- inventory_snapshots: 某门店某时间段的库存快照
- waste_report: 损耗分析/根因（需要 store_id 和 date_start/date_end）
- unknown: 无法识别则返回 unknown

输出格式（仅一行合法JSON）: {"intent":"...", "store_id":"", "dish_id":"", "date_start":"YYYY-MM-DD", "date_end":"YYYY-MM-DD"}
若问题中没有提到门店或日期，store_id/date_start/date_end 可留空；date 默认最近7天。"""


async def _parse_intent(question: str) -> Dict[str, Any]:
    """用 LLM 解析意图与参数。"""
    try:
        from src.core.llm import get_llm_client
        client = get_llm_client()
        if not client:
            return {"intent": "unknown", "store_id": "", "dish_id": "", "date_start": "", "date_end": ""}
        prompt = f"用户问题: {question}\n\n{INTENT_PROMPT}"
        out = await client.generate(prompt, system_prompt=ONTOLOGY_SCHEMA_DESC, temperature=0.1, max_tokens=300)
        out = (out or "").strip()
        j = {}
        m = re.search(r"\{[^{}]*\}", out)
        if m:
            try:
                j = json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        if not j:
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("{"):
                    try:
                        j = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
        intent = (j.get("intent") or "unknown").strip().lower()
        return {
            "intent": intent if intent else "unknown",
            "store_id": (j.get("store_id") or "").strip(),
            "dish_id": (j.get("dish_id") or "").strip(),
            "date_start": (j.get("date_start") or "").strip(),
            "date_end": (j.get("date_end") or "").strip(),
        }
    except Exception as e:
        logger.warning("ontology_nl_parse_intent_failed", error=str(e))
        return {"intent": "unknown", "store_id": "", "dish_id": "", "date_start": "", "date_end": ""}


def _default_dates() -> tuple:
    end = datetime.now().date()
    start = end - timedelta(days=7)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


async def _execute_intent(
    intent: str,
    store_id: str,
    dish_id: str,
    date_start: str,
    date_end: str,
    tenant_id: str,
) -> tuple[List[Any], Dict[str, Any], str]:
    """执行意图，返回 (数据列表, 溯源信息, 可读摘要)。"""
    repo = get_ontology_repository()
    trace: Dict[str, Any] = {"intent": intent, "params": {"store_id": store_id, "dish_id": dish_id, "date_start": date_start, "date_end": date_end}}
    ds, de = _default_dates()
    if not date_start:
        date_start = ds
    if not date_end:
        date_end = de

    if intent == "list_stores":
        if not repo:
            return [], trace, "图谱未就绪"
        cypher = "MATCH (s:Store) RETURN s.store_id AS store_id, s.name AS name LIMIT 100"
        rows = repo.run_read_only_query(cypher)
        trace["cypher"] = cypher
        summary = f"共 {len(rows)} 个门店"
        return rows, trace, summary

    if intent == "dish_bom" and dish_id:
        if not repo:
            return [], trace, "图谱未就绪"
        rows = repo.get_dish_bom_ingredients(dish_id)
        trace["query"] = "get_dish_bom_ingredients"
        summary = f"菜品 {dish_id} 的配方共 {len(rows)} 项用料"
        return rows, trace, summary

    if intent == "list_dishes" and store_id:
        if not repo:
            return [], trace, "图谱未就绪"
        cypher = "MATCH (d:Dish { store_id: $store_id }) RETURN d.dish_id AS dish_id, d.name AS name LIMIT 200"
        rows = repo.run_read_only_query(cypher, {"store_id": store_id})
        trace["cypher"] = cypher
        summary = f"门店 {store_id} 共 {len(rows)} 个菜品"
        return rows, trace, summary

    if intent == "inventory_snapshots" and store_id:
        if not repo:
            return [], trace, "图谱未就绪"
        ts_start = date_start + "T00:00:00"
        ts_end = date_end + "T23:59:59"
        rows = repo.get_inventory_snapshots(store_id, ts_start, ts_end)
        trace["query"] = "get_inventory_snapshots"
        summary = f"门店 {store_id} 在 {date_start}～{date_end} 共 {len(rows)} 条库存快照"
        return rows, trace, summary

    if intent == "waste_report" and store_id:
        from src.core.database import get_db_session
        from src.services.waste_reasoning_service import run_waste_reasoning
        async with get_db_session() as session:
            report = await run_waste_reasoning(session, tenant_id=tenant_id, store_id=store_id, date_start=date_start, date_end=date_end)
        top3 = report.get("top3_root_causes") or []
        trace["service"] = "run_waste_reasoning"
        summary = f"损耗推理 TOP3 根因: " + "; ".join([str(c.get("reason", "")) for c in top3[:3]]) if top3 else "暂无异常根因"
        return top3, trace, summary

    return [], trace, "未识别的意图或缺少参数（如 store_id/dish_id）"


async def query_ontology_natural_language(
    question: str,
    tenant_id: str = "",
    store_id_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    自然语言查询本体：意图识别 → 执行 → 返回答案 + 溯源。
    """
    parsed = await _parse_intent(question)
    store_id = parsed.get("store_id") or store_id_hint or ""
    dish_id = parsed.get("dish_id") or ""
    date_start = parsed.get("date_start") or ""
    date_end = parsed.get("date_end") or ""

    data, trace, summary = await _execute_intent(
        parsed.get("intent", "unknown"),
        store_id,
        dish_id,
        date_start,
        date_end,
        tenant_id,
    )

    # 可选：用 LLM 把 data + summary 整理成一句自然语言答案（此处先返回结构化 + summary）
    answer_text = summary
    try:
        from src.core.llm import get_llm_client
        client = get_llm_client()
        if client and data and isinstance(data, list) and len(data) <= 20:
            prompt = f"根据以下查询结果，用一两句中文总结回答用户问题。\n用户问题: {question}\n结果摘要: {summary}\n详细条数: {len(data)}。请直接给出简短回答，不要重复问题。"
            answer_text = (await client.generate(prompt, temperature=0.3, max_tokens=150)).strip() or summary
    except Exception as e:
        logger.debug("ontology_nl_answer_format_skip", error=str(e))

    return {
        "question": question,
        "answer": answer_text,
        "trace": trace,
        "data": data[:50],
        "data_count": len(data),
    }
