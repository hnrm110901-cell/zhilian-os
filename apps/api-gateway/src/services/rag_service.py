"""
RAG服务 - Retrieval-Augmented Generation
为Agent提供基于历史数据的增强决策能力

Week 2核心功能：
- 向量检索相关历史事件
- 格式化上下文注入LLM
- 生成增强的AI决策
"""
import os
from typing import List, Dict, Any, Optional
import structlog
from datetime import datetime

from .vector_db_service import vector_db_service
from ..core.llm import get_llm_client
from .rag_signal_router import classify_query, QuerySignal, route_numerical_query

logger = structlog.get_logger()


class RAGService:
    """RAG服务 - 为Agent提供记忆和学习能力"""

    def __init__(self):
        """初始化RAG服务"""
        self.vector_db = vector_db_service
        self.llm = None
        logger.info("RAGService初始化完成")

    async def initialize(self):
        """初始化RAG服务"""
        try:
            # 初始化向量数据库
            await self.vector_db.initialize()

            # 初始化LLM
            self.llm = get_llm_client()

            logger.info("RAG服务初始化成功")
        except Exception as e:
            logger.error("RAG服务初始化失败", error=str(e))
            raise

    async def search_relevant_context(
        self,
        query: str,
        store_id: str,
        collection: str = "events",
        top_k: int = int(os.getenv("RAG_TOP_K", "5"))
    ) -> List[Dict[str, Any]]:
        """
        检索相关上下文

        Args:
            query: 查询文本
            store_id: 门店ID
            collection: 集合名称（events, orders, dishes等）
            top_k: 返回前K个结果

        Returns:
            相关历史记录列表
        """
        try:
            # 根据集合类型选择搜索方法
            if collection == "events":
                results = await self.vector_db.search_events(
                    query=query,
                    store_id=store_id,
                    limit=top_k
                )
            elif collection == "orders":
                results = await self.vector_db.search_orders(
                    query=query,
                    store_id=store_id,
                    limit=top_k
                )
            elif collection == "dishes":
                results = await self.vector_db.search_dishes(
                    query=query,
                    store_id=store_id,
                    limit=top_k
                )
            else:
                logger.warning(f"未知的集合类型: {collection}")
                results = []

            logger.info(
                "检索相关上下文",
                query=query,
                collection=collection,
                results_count=len(results)
            )

            return results

        except Exception as e:
            logger.error("检索上下文失败", error=str(e))
            return []

    def format_context(
        self,
        results: List[Dict[str, Any]],
        max_length: int = int(os.getenv("RAG_MAX_CONTEXT_LENGTH", "2000"))
    ) -> str:
        """
        格式化检索结果为上下文文本

        Args:
            results: 检索结果列表
            max_length: 最大上下文长度

        Returns:
            格式化的上下文文本
        """
        if not results:
            return "暂无相关历史数据。"

        context_parts = []
        current_length = 0

        for i, result in enumerate(results, 1):
            # 提取payload中的文本
            text = result.get("text", "")
            score = result.get("score", 0.0)

            # 格式化单条记录
            formatted = f"[历史记录 {i}] (相关度: {score:.2f})\n{text}\n"

            # 检查长度限制
            if current_length + len(formatted) > max_length:
                break

            context_parts.append(formatted)
            current_length += len(formatted)

        context = "\n".join(context_parts)

        logger.debug(
            "格式化上下文",
            records_count=len(context_parts),
            context_length=len(context)
        )

        return context

    async def analyze_with_rag(
        self,
        query: str,
        store_id: str,
        collection: str = "events",
        top_k: int = int(os.getenv("RAG_TOP_K", "5")),
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        使用RAG进行增强分析

        这是核心方法，实现了完整的RAG流程：
        1. 向量检索相关历史
        2. 格式化上下文
        3. LLM生成增强决策

        Args:
            query: 查询/问题
            store_id: 门店ID
            collection: 检索的集合
            top_k: 检索前K个结果
            system_prompt: 系统提示（可选）

        Returns:
            包含分析结果和元数据的字典
        """
        try:
            signal = classify_query(query)
            route_label = signal.value

            if signal == QuerySignal.NUMERICAL:
                # --- 数值类：走 PostgreSQL 精确查询 ---
                structured = await route_numerical_query(query, store_id)
                if structured:
                    context_text = structured["summary"]
                    context_detail = structured
                    context_used = 1
                    logger.info(
                        "rag.routed_to_postgresql",
                        store_id=store_id,
                        metric=structured.get("metric"),
                    )
                else:
                    # PostgreSQL 查询失败，降级到向量检索
                    route_label = "numerical_fallback_semantic"
                    relevant_context = await self.search_relevant_context(
                        query=query, store_id=store_id,
                        collection=collection, top_k=top_k,
                    )
                    context_text = self.format_context(relevant_context)
                    context_detail = None
                    context_used = len(relevant_context)
            else:
                # --- 语义类：走 Qdrant 向量检索 ---
                relevant_context = await self.search_relevant_context(
                    query=query, store_id=store_id,
                    collection=collection, top_k=top_k,
                )
                context_text = self.format_context(relevant_context)
                context_detail = None
                context_used = len(relevant_context)
                logger.info(
                    "rag.routed_to_qdrant",
                    store_id=store_id,
                    results=context_used,
                )

            # 构建增强提示
            enhanced_prompt = self._build_enhanced_prompt(
                query=query,
                context=context_text,
                system_prompt=system_prompt,
            )

            # LLM 生成
            if self.llm:
                response = await self.llm.generate(enhanced_prompt)
            else:
                response = "LLM未初始化，无法生成响应"

            result = {
                "success": True,
                "query": query,
                "response": response,
                "context_used": context_used,
                "context_text": context_text,
                "route": route_label,
                "timestamp": datetime.now().isoformat(),
            }
            if context_detail:
                result["structured_data"] = context_detail
            return result

        except Exception as e:
            logger.error("RAG分析失败", error=str(e))
            return {
                "success": False,
                "query": query,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def _build_enhanced_prompt(
        self,
        query: str,
        context: str,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        构建增强提示

        Args:
            query: 用户查询
            context: 检索到的上下文
            system_prompt: 系统提示

        Returns:
            增强的提示文本
        """
        # 默认系统提示
        if not system_prompt:
            system_prompt = """你是智链OS的AI助手，专门帮助餐饮门店进行数据分析和决策支持。
你的任务是基于历史数据和当前问题，提供准确、可操作的建议。"""

        # 构建完整提示
        enhanced_prompt = f"""{system_prompt}

## 相关历史数据
{context}

## 当前问题
{query}

## 分析要求
1. 仔细分析历史数据中的模式和趋势
2. 结合当前问题给出具体建议
3. 如果历史数据不足，请明确说明
4. 提供可操作的下一步行动

请基于以上信息进行分析："""

        return enhanced_prompt

    async def get_similar_cases(
        self,
        query: str,
        store_id: str,
        top_k: int = int(os.getenv("RAG_TOP_K_SHORT", "3"))
    ) -> List[Dict[str, Any]]:
        """
        获取相似案例

        用于展示给用户参考的历史相似案例

        Args:
            query: 查询描述
            store_id: 门店ID
            top_k: 返回数量

        Returns:
            相似案例列表
        """
        try:
            results = await self.search_relevant_context(
                query=query,
                store_id=store_id,
                collection="events",
                top_k=top_k
            )

            # 格式化为用户友好的格式
            cases = []
            for result in results:
                cases.append({
                    "text": result.get("text", ""),
                    "score": result.get("score", 0.0),
                    "timestamp": result.get("created_at", ""),
                    "type": result.get("event_type", "unknown")
                })

            return cases

        except Exception as e:
            logger.error("获取相似案例失败", error=str(e))
            return []


# 创建全局实例
rag_service = RAGService()
