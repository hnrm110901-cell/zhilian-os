"""
领域分割向量索引服务 (Domain-Split Vector Index)

问题：所有门店数据混在同一个 Qdrant collection，搜索时靠 payload filter 全量扫描，
      跨领域数据（营收/库存/菜品/事件）互相污染 RAG 上下文。

方案：按 {domain}_{store_id} 命名 collection，每个门店每个领域独立索引。
      - 精确检索：向量搜索范围缩小到单店单领域
      - 零跨域污染：营收查询不会召回库存数据
      - 按需创建：collection 在首次写入时自动创建

领域定义：
  revenue   — 营收/订单/交易
  inventory — 库存/采购/损耗
  menu      — 菜品/定价/BOM
  staff     — 员工/排班/绩效
  events    — 神经系统事件（通用）
  decisions — AI决策日志
"""
import hashlib
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

# 支持的领域及其向量维度
DOMAINS = {
    "revenue":   384,
    "inventory": 384,
    "menu":      384,
    "staff":     384,
    "events":    384,
    "decisions": 384,
}

# 旧 collection 名称 → 新领域映射（向后兼容）
LEGACY_COLLECTION_MAP = {
    "orders": "revenue",
    "dishes": "menu",
    "staff":  "staff",
    "events": "events",
}


def collection_name(domain: str, store_id: str) -> str:
    """生成 collection 名称: {domain}_{store_id_hash8}"""
    # store_id 可能含特殊字符，用 hash 前8位保证合法
    sid = hashlib.md5(store_id.encode()).hexdigest()[:8]
    return f"{domain}_{sid}"


class DomainVectorService:
    """领域分割向量索引服务"""

    def __init__(self):
        self.qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        self.qdrant_api_key = os.getenv("QDRANT_API_KEY", "")
        self.client = None
        self.embedding_model = None
        self._ensured: set[str] = set()   # 已确认存在的 collection 缓存

    async def initialize(self):
        """初始化 Qdrant 客户端和嵌入模型"""
        from qdrant_client import QdrantClient
        self.client = QdrantClient(
            url=self.qdrant_url,
            api_key=self.qdrant_api_key or None,
        )
        rag_enabled = os.getenv("RAG_ENABLED", "true").lower() not in ("false", "0", "no")
        if not rag_enabled:
            logger.info("RAG_ENABLED=false，跳过嵌入模型加载，使用哈希向量")
            return
        try:
            from sentence_transformers import SentenceTransformer
            model_name = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
            self.embedding_model = SentenceTransformer(model_name)
            logger.info("DomainVectorService 嵌入模型加载成功", model=model_name)
        except Exception as e:
            logger.warning("嵌入模型加载失败，使用哈希向量", error=str(e))
            self.embedding_model = None

    def _embed(self, text: str) -> List[float]:
        """生成嵌入向量"""
        if self.embedding_model:
            return self.embedding_model.encode(text).tolist()
        import random
        random.seed(hashlib.md5(text.encode()).hexdigest())
        return [random.random() for _ in range(384)]

    async def _ensure_collection(self, cname: str, vector_size: int = 384):
        """按需创建 collection（带本地缓存避免重复检查）"""
        if cname in self._ensured:
            return
        from qdrant_client.models import Distance, VectorParams
        existing = {c.name for c in self.client.get_collections().collections}
        if cname not in existing:
            self.client.create_collection(
                collection_name=cname,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            logger.info("创建领域 collection", collection=cname)
        self._ensured.add(cname)

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    async def index(
        self,
        domain: str,
        store_id: str,
        doc_id: str,
        text: str,
        payload: Dict[str, Any],
    ) -> bool:
        """
        写入一条文档到指定领域的 collection

        Args:
            domain:   领域名称 (revenue/inventory/menu/staff/events/decisions)
            store_id: 门店ID
            doc_id:   文档唯一ID（用于 upsert）
            text:     用于生成嵌入的文本
            payload:  存储的结构化数据
        """
        if not self.client:
            await self.initialize()
        try:
            cname = collection_name(domain, store_id)
            await self._ensure_collection(cname, DOMAINS.get(domain, 384))

            from qdrant_client.models import PointStruct
            point_id = int(hashlib.md5(doc_id.encode()).hexdigest()[:15], 16)
            embedding = self._embed(text)

            self.client.upsert(
                collection_name=cname,
                points=[PointStruct(id=point_id, vector=embedding, payload={**payload, "store_id": store_id, "_text": text})],
            )
            logger.info("领域索引写入成功", domain=domain, store_id=store_id, doc_id=doc_id)
            return True
        except Exception as e:
            logger.error("领域索引写入失败", domain=domain, store_id=store_id, error=str(e))
            return False

    async def index_revenue_event(self, store_id: str, data: Dict[str, Any]) -> bool:
        """索引营收/订单事件"""
        doc_id = data.get("order_id") or data.get("event_id") or data.get("id", "")
        text = (
            f"订单 {data.get('order_number', '')} "
            f"类型 {data.get('order_type', '')} "
            f"金额 {data.get('total', '')}元 "
            f"状态 {data.get('order_status', '')} "
            f"菜品: {', '.join(i.get('dish_name','') for i in data.get('items', []))}"
        )
        return await self.index("revenue", store_id, doc_id, text, data)

    async def index_inventory_event(self, store_id: str, data: Dict[str, Any]) -> bool:
        """索引库存/采购事件"""
        doc_id = data.get("item_id") or data.get("event_id") or data.get("id", "")
        text = (
            f"库存 {data.get('item_name', '')} "
            f"数量 {data.get('quantity', '')} "
            f"单位 {data.get('unit', '')} "
            f"状态 {data.get('status', '')} "
            f"预警 {data.get('alert_type', '')}"
        )
        return await self.index("inventory", store_id, doc_id, text, data)

    async def index_menu_item(self, store_id: str, data: Dict[str, Any]) -> bool:
        """索引菜品/BOM"""
        doc_id = data.get("dish_id") or data.get("id", "")
        text = (
            f"菜品 {data.get('name', '')} "
            f"分类 {data.get('category', '')} "
            f"价格 {data.get('price', '')}元 "
            f"描述 {data.get('description', '')} "
            f"标签 {' '.join(data.get('tags', []))}"
        )
        return await self.index("menu", store_id, doc_id, text, data)

    async def index_neural_event(self, store_id: str, data: Dict[str, Any]) -> bool:
        """索引神经系统事件（通用）"""
        doc_id = data.get("event_id") or data.get("id", "")
        text = (
            f"事件类型 {data.get('event_type', '')} "
            f"来源 {data.get('event_source', '')} "
            f"数据 {json.dumps(data.get('data', {}), ensure_ascii=False)[:200]}"
        )
        return await self.index("events", store_id, doc_id, text, data)

    async def index_decision(self, store_id: str, data: Dict[str, Any]) -> bool:
        """索引 AI 决策日志"""
        doc_id = data.get("id") or data.get("decision_id", "")
        text = (
            f"决策类型 {data.get('decision_type', '')} "
            f"Agent {data.get('agent_type', '')} "
            f"建议 {json.dumps(data.get('ai_suggestion', {}), ensure_ascii=False)[:200]} "
            f"结果 {data.get('outcome', '')}"
        )
        return await self.index("decisions", store_id, doc_id, text, data)

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    async def search(
        self,
        domain: str,
        store_id: str,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        在指定领域内语义搜索

        Args:
            domain:          领域名称
            store_id:        门店ID
            query:           查询文本
            top_k:           返回条数
            score_threshold: 最低相似度阈值

        Returns:
            [{score, payload}, ...]
        """
        if not self.client:
            await self.initialize()
        try:
            cname = collection_name(domain, store_id)
            # collection 不存在时直接返回空（无需报错）
            existing = {c.name for c in self.client.get_collections().collections}
            if cname not in existing:
                return []

            embedding = self._embed(query)
            results = self.client.search(
                collection_name=cname,
                query_vector=embedding,
                limit=top_k,
                score_threshold=score_threshold if score_threshold > 0 else None,
            )
            return [{"score": r.score, "payload": r.payload} for r in results]
        except Exception as e:
            logger.error("领域搜索失败", domain=domain, store_id=store_id, error=str(e))
            return []

    async def search_multi_domain(
        self,
        domains: List[str],
        store_id: str,
        query: str,
        top_k_per_domain: int = 3,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """跨多领域搜索，返回按领域分组的结果"""
        import asyncio
        tasks = {d: self.search(d, store_id, query, top_k_per_domain) for d in domains}
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        return {
            domain: (res if not isinstance(res, Exception) else [])
            for domain, res in zip(tasks.keys(), results)
        }

    async def list_store_collections(self, store_id: str) -> List[str]:
        """列出门店已有的领域 collection"""
        if not self.client:
            await self.initialize()
        sid = hashlib.md5(store_id.encode()).hexdigest()[:8]
        all_cols = {c.name for c in self.client.get_collections().collections}
        return [c for c in all_cols if c.endswith(f"_{sid}")]


# Singleton
domain_vector_service = DomainVectorService()
