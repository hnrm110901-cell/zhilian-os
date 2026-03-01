"""
本体层 API — Palantir Ontology / Reasoning Layer

端点：
  POST  /api/v1/ontology/waste/{event_id}/infer   触发损耗五步推理
  GET   /api/v1/ontology/waste/{event_id}/explain 读取推理证据链（XAI）
  GET   /api/v1/ontology/store/{store_id}/summary 门店知识图谱摘要
  GET   /api/v1/ontology/dish/{dish_id}/bom       查询菜品 BOM（Neo4j 本体）
  GET   /api/v1/ontology/dish/{dish_id}/waste     查询菜品损耗历史（Neo4j）

  POST  /api/v1/ontology/import/bom/excel         Excel BOM 批量导入
  POST  /api/v1/ontology/query/natural            自然语言→Cypher 查询（LLM）
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.models.user import User

router = APIRouter(prefix="/api/v1/ontology", tags=["ontology"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class WasteInferResult(BaseModel):
    event_id: str
    root_cause: str
    confidence: float
    evidence_chain: dict
    scores: dict
    message: str


class KnowledgeSummary(BaseModel):
    store_id: str
    dish_count: int
    bom_count: int
    ingredient_count: int
    waste_event_count: int


class NaturalQueryIn(BaseModel):
    question: str = Field(..., description="自然语言问题，如：徐记海鲜上周损耗最高的菜品是什么？")
    store_id: Optional[str] = None
    limit: int = Field(20, ge=1, le=100)


class NaturalQueryOut(BaseModel):
    question: str
    cypher: str
    results: List[dict]
    explanation: str


# ── 损耗推理 ──────────────────────────────────────────────────────────────────

@router.post("/waste/{event_id}/infer", response_model=WasteInferResult)
async def infer_waste_root_cause(
    event_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    触发损耗事件的五步推理分析。

    五步：
      1. 理论消耗计算（BOM × 销量）
      2. 库存差异分析
      3. 多维评分（人员/食材/设备/流程）
      4. 加权融合根因
      5. 写回 WasteEvent 节点
    """
    try:
        from src.ontology.reasoning import WasteReasoningEngine
        engine = WasteReasoningEngine()
        result = engine.infer_root_cause(event_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"推理引擎错误: {e}")

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "推理失败"))

    import json
    evidence = result.get("evidence_chain", {})
    scores = result.get("scores", {})
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except Exception:
            evidence = {}
    if isinstance(scores, str):
        try:
            scores = json.loads(scores)
        except Exception:
            scores = {}

    return WasteInferResult(
        event_id=event_id,
        root_cause=result.get("root_cause", "unknown"),
        confidence=result.get("confidence", 0.0),
        evidence_chain=evidence,
        scores=scores,
        message="损耗根因推理完成，证据链已写回本体",
    )


@router.get("/waste/{event_id}/explain")
async def explain_waste_event(
    event_id: str,
    current_user: User = Depends(get_current_user),
):
    """读取已推理的损耗事件证据链（XAI 可解释性输出）"""
    from src.agents.ontology_adapter import KnowledgeAwareAgent
    agent = KnowledgeAwareAgent("explain")
    result = agent.explain_reasoning(event_id)
    agent.close()
    if not result:
        raise HTTPException(status_code=404, detail="损耗事件不存在或尚未推理")
    return result


# ── 知识图谱摘要 ──────────────────────────────────────────────────────────────

@router.get("/store/{store_id}/summary", response_model=KnowledgeSummary)
async def get_store_knowledge_summary(
    store_id: str,
    current_user: User = Depends(get_current_user),
):
    """查询门店知识图谱本体节点数量摘要"""
    from src.agents.ontology_adapter import KnowledgeAwareAgent
    agent = KnowledgeAwareAgent("summary")
    summary = agent.get_store_knowledge_summary(store_id)
    agent.close()
    return KnowledgeSummary(store_id=store_id, **summary)


# ── 菜品 BOM / 损耗历史 ───────────────────────────────────────────────────────

@router.get("/dish/{dish_id}/bom")
async def get_dish_bom_from_ontology(
    dish_id: str,
    current_user: User = Depends(get_current_user),
):
    """从 Neo4j 本体层查询菜品当前激活 BOM（含食材清单）"""
    from src.agents.ontology_adapter import KnowledgeAwareAgent
    agent = KnowledgeAwareAgent("bom_query")
    bom = agent.get_dish_bom(f"DISH-{dish_id}")
    agent.close()
    if not bom:
        raise HTTPException(status_code=404, detail="本体层无此菜品 BOM，请先同步")
    return bom


@router.get("/dish/{dish_id}/waste")
async def get_dish_waste_events(
    dish_id: str,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
):
    """从 Neo4j 查询菜品损耗事件历史"""
    from src.agents.ontology_adapter import KnowledgeAwareAgent
    agent = KnowledgeAwareAgent("waste_query")
    events = agent.get_waste_events(f"DISH-{dish_id}", limit=limit)
    agent.close()
    return {"dish_id": dish_id, "events": events, "count": len(events)}


# ── Excel BOM 批量导入 ────────────────────────────────────────────────────────

@router.post("/import/bom/excel", status_code=status.HTTP_201_CREATED)
async def import_bom_excel(
    file: UploadFile = File(..., description="Excel 文件（.xlsx / .xls）"),
    store_id: str = Form(..., description="门店 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Excel BOM 批量导入（徐记海鲜 POC 配方录入）

    Excel 必须包含列：菜品编码、菜品名称、食材名称、标准用量、单位

    可选列：版本、出成率、食材分类、核心食材、毛料用量、加工说明、备注
    """
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls 格式")

    excel_bytes = await file.read()
    if len(excel_bytes) > 10 * 1024 * 1024:  # 10MB 限制
        raise HTTPException(status_code=400, detail="文件超过 10MB 限制")

    from src.services.excel_bom_importer import ExcelBOMImporter
    importer = ExcelBOMImporter(
        db=db,
        store_id=store_id,
        created_by=str(current_user.id),
    )

    try:
        report = await importer.import_from_bytes(excel_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "message": "BOM 导入完成",
        "total_rows": report.total_rows,
        "total_dishes": report.total_dishes,
        "total_boms_created": report.total_boms_created,
        "total_items_created": report.total_items_created,
        "errors": report.errors,
        "warnings": report.warnings,
        "results": report.dish_results,
    }


# ── 自然语言→Cypher 查询 ──────────────────────────────────────────────────────

@router.post("/query/natural", response_model=NaturalQueryOut)
async def natural_language_query(
    payload: NaturalQueryIn,
    current_user: User = Depends(get_current_user),
):
    """
    自然语言→Cypher 查询（Phase 2-M2.3）

    示例问题：
      - "徐记海鲜上周损耗最高的前3道菜是什么？"
      - "海鲜粥的当前配方用了哪些食材？"
      - "上个月发生了多少次因人员操作导致的损耗？"
    """
    try:
        from src.services.llm_cypher_service import LLMCypherService
        svc = LLMCypherService()
        result = await svc.query(
            question=payload.question,
            store_id=payload.store_id,
            limit=payload.limit,
        )
        return NaturalQueryOut(
            question=payload.question,
            cypher=result["cypher"],
            results=result["results"],
            explanation=result["explanation"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM 查询失败: {e}")
