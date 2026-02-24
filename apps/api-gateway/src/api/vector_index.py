"""
领域分割向量索引 API
提供按领域的语义搜索和索引管理接口
"""
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from ..services.domain_vector_service import domain_vector_service, DOMAINS

router = APIRouter(prefix="/api/v1/vector", tags=["vector_index"])


class IndexRequest(BaseModel):
    domain: str
    store_id: str
    doc_id: str
    text: str
    payload: Dict[str, Any] = {}


@router.post("/index")
async def index_document(req: IndexRequest):
    """手动写入一条文档到指定领域索引"""
    if req.domain not in DOMAINS:
        raise HTTPException(status_code=400, detail=f"未知领域: {req.domain}，支持: {list(DOMAINS)}")
    ok = await domain_vector_service.index(req.domain, req.store_id, req.doc_id, req.text, req.payload)
    return {"success": ok, "domain": req.domain, "store_id": req.store_id, "doc_id": req.doc_id}


@router.get("/search/{store_id}")
async def search(
    store_id: str,
    query: str = Query(..., description="查询文本"),
    domain: str = Query("events", description=f"领域: {list(DOMAINS.keys())}"),
    top_k: int = Query(5, ge=1, le=20),
    score_threshold: float = Query(0.0, ge=0.0, le=1.0),
):
    """在指定领域内语义搜索"""
    if domain not in DOMAINS:
        raise HTTPException(status_code=400, detail=f"未知领域: {domain}")
    results = await domain_vector_service.search(
        domain=domain,
        store_id=store_id,
        query=query,
        top_k=top_k,
        score_threshold=score_threshold,
    )
    return {"store_id": store_id, "domain": domain, "query": query, "total": len(results), "results": results}


@router.get("/search-multi/{store_id}")
async def search_multi(
    store_id: str,
    query: str = Query(...),
    domains: str = Query("revenue,inventory,menu,events", description="逗号分隔的领域列表"),
    top_k_per_domain: int = Query(3, ge=1, le=10),
):
    """跨多领域并行搜索"""
    domain_list = [d.strip() for d in domains.split(",") if d.strip() in DOMAINS]
    if not domain_list:
        raise HTTPException(status_code=400, detail="没有有效的领域")
    results = await domain_vector_service.search_multi_domain(
        domains=domain_list,
        store_id=store_id,
        query=query,
        top_k_per_domain=top_k_per_domain,
    )
    return {"store_id": store_id, "query": query, "results": results}


@router.get("/collections/{store_id}")
async def list_collections(store_id: str):
    """列出门店已有的领域 collection"""
    cols = await domain_vector_service.list_store_collections(store_id)
    return {"store_id": store_id, "collections": cols, "total": len(cols)}
