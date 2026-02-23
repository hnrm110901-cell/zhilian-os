"""
向量数据库服务
Vector Database Service

使用Qdrant实现语义搜索和AI能力
支持餐饮业务标准Schema的向量化存储和检索
"""
from typing import List, Dict, Any, Optional
import structlog
import os
from datetime import datetime
import hashlib
import json

logger = structlog.get_logger()


class VectorDatabaseService:
    """向量数据库服务"""

    def __init__(self):
        """初始化向量数据库服务"""
        from src.core.config import settings

        self.qdrant_url = settings.QDRANT_URL
        self.qdrant_api_key = settings.QDRANT_API_KEY
        self.client = None
        self.embedding_model = None

        logger.info("VectorDatabaseService初始化完成")

    async def initialize(self):
        """初始化Qdrant客户端和嵌入模型"""
        try:
            # 初始化Qdrant客户端
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            self.client = QdrantClient(
                url=self.qdrant_url,
                api_key=self.qdrant_api_key if self.qdrant_api_key else None,
            )

            # 初始化嵌入模型（使用sentence-transformers，可通过EMBEDDING_MODEL环境变量替换）
            try:
                from sentence_transformers import SentenceTransformer
                model_name = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
                self.embedding_model = SentenceTransformer(model_name)
                logger.info("嵌入模型加载成功", model=model_name)
            except Exception as e:
                logger.warning("嵌入模型加载失败，将使用模拟嵌入", error=str(e))
                self.embedding_model = None

            # 创建集合（如果不存在）
            await self._ensure_collections()

            logger.info("向量数据库初始化成功")

        except Exception as e:
            logger.error("向量数据库初始化失败", error=str(e))
            raise

    async def _ensure_collections(self):
        """确保所有必需的集合存在"""
        from qdrant_client.models import Distance, VectorParams

        collections = [
            {
                "name": "orders",
                "description": "订单向量集合",
                "vector_size": 384,  # MiniLM模型的维度
            },
            {
                "name": "dishes",
                "description": "菜品向量集合",
                "vector_size": 384,
            },
            {
                "name": "staff",
                "description": "员工向量集合",
                "vector_size": 384,
            },
            {
                "name": "events",
                "description": "神经系统事件向量集合",
                "vector_size": 384,
            },
        ]

        for collection in collections:
            try:
                # 检查集合是否存在
                collections_list = self.client.get_collections()
                exists = any(c.name == collection["name"] for c in collections_list.collections)

                if not exists:
                    # 创建集合
                    self.client.create_collection(
                        collection_name=collection["name"],
                        vectors_config=VectorParams(
                            size=collection["vector_size"],
                            distance=Distance.COSINE,
                        ),
                    )
                    logger.info(f"创建集合: {collection['name']}")

            except Exception as e:
                logger.error(f"创建集合失败: {collection['name']}", error=str(e))

    def generate_embedding(self, text: str) -> List[float]:
        """
        生成文本嵌入向量

        Args:
            text: 输入文本

        Returns:
            嵌入向量
        """
        if self.embedding_model:
            # 使用实际的嵌入模型
            embedding = self.embedding_model.encode(text)
            return embedding.tolist()
        else:
            # 嵌入模型不可用时，使用确定性哈希向量（语义无意义，仅保证服务不崩溃）
            import random
            random.seed(hashlib.md5(text.encode()).hexdigest())
            return [random.random() for _ in range(int(os.getenv("VECTOR_EMBEDDING_DIM", "384")))]

    async def index_order(self, order_data: Dict[str, Any]) -> bool:
        """
        索引订单到向量数据库

        Args:
            order_data: 订单数据（符合OrderSchema）

        Returns:
            是否成功
        """
        try:
            # 生成订单的文本表示
            text = self._order_to_text(order_data)

            # 生成嵌入向量
            embedding = self.generate_embedding(text)

            # 存储到Qdrant
            from qdrant_client.models import PointStruct

            point = PointStruct(
                id=hashlib.md5(order_data["order_id"].encode()).hexdigest()[:16],
                vector=embedding,
                payload={
                    "order_id": order_data["order_id"],
                    "order_number": order_data["order_number"],
                    "order_type": order_data["order_type"],
                    "total": float(order_data["total"]),
                    "created_at": order_data["created_at"].isoformat() if isinstance(order_data["created_at"], datetime) else order_data["created_at"],
                    "store_id": order_data["store_id"],
                    "text": text,
                },
            )

            self.client.upsert(
                collection_name="orders",
                points=[point],
            )

            logger.info("订单索引成功", order_id=order_data["order_id"])
            return True

        except Exception as e:
            logger.error("订单索引失败", error=str(e))
            return False

    async def index_dish(self, dish_data: Dict[str, Any]) -> bool:
        """
        索引菜品到向量数据库

        Args:
            dish_data: 菜品数据（符合DishSchema）

        Returns:
            是否成功
        """
        try:
            # 生成菜品的文本表示
            text = self._dish_to_text(dish_data)

            # 生成嵌入向量
            embedding = self.generate_embedding(text)

            # 存储到Qdrant
            from qdrant_client.models import PointStruct

            point = PointStruct(
                id=hashlib.md5(dish_data["dish_id"].encode()).hexdigest()[:16],
                vector=embedding,
                payload={
                    "dish_id": dish_data["dish_id"],
                    "name": dish_data["name"],
                    "category": dish_data["category"],
                    "price": float(dish_data["price"]),
                    "is_available": dish_data["is_available"],
                    "store_id": dish_data["store_id"],
                    "text": text,
                },
            )

            self.client.upsert(
                collection_name="dishes",
                points=[point],
            )

            logger.info("菜品索引成功", dish_id=dish_data["dish_id"])
            return True

        except Exception as e:
            logger.error("菜品索引失败", error=str(e))
            return False

    async def index_event(self, event_data: Dict[str, Any]) -> bool:
        """
        索引神经系统事件到向量数据库

        Args:
            event_data: 事件数据（符合NeuralEventSchema）

        Returns:
            是否成功
        """
        try:
            # 生成事件的文本表示
            text = self._event_to_text(event_data)

            # 生成嵌入向量
            embedding = self.generate_embedding(text)

            # 存储到Qdrant
            from qdrant_client.models import PointStruct

            point = PointStruct(
                id=hashlib.md5(event_data["event_id"].encode()).hexdigest()[:16],
                vector=embedding,
                payload={
                    "event_id": event_data["event_id"],
                    "event_type": event_data["event_type"],
                    "event_source": event_data["event_source"],
                    "timestamp": event_data["timestamp"].isoformat() if isinstance(event_data["timestamp"], datetime) else event_data["timestamp"],
                    "store_id": event_data["store_id"],
                    "priority": event_data.get("priority", 0),
                    "text": text,
                },
            )

            self.client.upsert(
                collection_name="events",
                points=[point],
            )

            logger.info("事件索引成功", event_id=event_data["event_id"])
            return True

        except Exception as e:
            logger.error("事件索引失败", error=str(e))
            return False

    async def semantic_search(
        self,
        collection_name: str,
        query: str,
        limit: int = int(os.getenv("VECTOR_DB_SEARCH_LIMIT", "10")),
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        语义搜索

        Args:
            collection_name: 集合名称
            query: 查询文本
            limit: 返回结果数量
            filters: 过滤条件

        Returns:
            搜索结果列表
        """
        try:
            # 生成查询嵌入
            query_embedding = self.generate_embedding(query)

            # 构建过滤条件
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            qdrant_filter = None
            if filters:
                conditions = []
                for key, value in filters.items():
                    conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=value),
                        )
                    )
                if conditions:
                    qdrant_filter = Filter(must=conditions)

            # 执行搜索
            results = self.client.search(
                collection_name=collection_name,
                query_vector=query_embedding,
                limit=limit,
                query_filter=qdrant_filter,
            )

            # 格式化结果
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "score": result.score,
                    "payload": result.payload,
                })

            logger.info(
                "语义搜索完成",
                collection=collection_name,
                query=query,
                results_count=len(formatted_results),
            )

            return formatted_results

        except Exception as e:
            logger.error("语义搜索失败", error=str(e))
            return []

    def _order_to_text(self, order_data: Dict[str, Any]) -> str:
        """将订单数据转换为文本表示"""
        items_text = ", ".join([
            f"{item['dish_name']} x {item['quantity']}"
            for item in order_data.get("items", [])
        ])

        return f"订单号 {order_data['order_number']}, " \
               f"类型 {order_data['order_type']}, " \
               f"状态 {order_data['order_status']}, " \
               f"菜品: {items_text}, " \
               f"总金额 {order_data['total']}元"

    def _dish_to_text(self, dish_data: Dict[str, Any]) -> str:
        """将菜品数据转换为文本表示"""
        tags_text = ", ".join(dish_data.get("tags", []))

        return f"菜品 {dish_data['name']}, " \
               f"分类 {dish_data['category']}, " \
               f"价格 {dish_data['price']}元, " \
               f"描述: {dish_data.get('description', '')}, " \
               f"标签: {tags_text}"

    def _event_to_text(self, event_data: Dict[str, Any]) -> str:
        """将事件数据转换为文本表示"""
        data_text = json.dumps(event_data.get("data", {}), ensure_ascii=False)

        return f"事件类型 {event_data['event_type']}, " \
               f"来源 {event_data['event_source']}, " \
               f"数据: {data_text}"

    async def search_orders(
        self,
        query: str,
        store_id: str,
        limit: int = int(os.getenv("VECTOR_DB_SEARCH_LIMIT", "10"))
    ) -> List[Dict[str, Any]]:
        """搜索订单"""
        return await self.semantic_search(
            collection_name="orders",
            query=query,
            limit=limit,
            filters={"store_id": store_id}
        )

    async def search_dishes(
        self,
        query: str,
        store_id: str,
        limit: int = int(os.getenv("VECTOR_DB_SEARCH_LIMIT", "10"))
    ) -> List[Dict[str, Any]]:
        """搜索菜品"""
        return await self.semantic_search(
            collection_name="dishes",
            query=query,
            limit=limit,
            filters={"store_id": store_id}
        )

    async def search_events(
        self,
        query: str,
        store_id: str,
        limit: int = int(os.getenv("VECTOR_DB_SEARCH_LIMIT", "10"))
    ) -> List[Dict[str, Any]]:
        """搜索事件"""
        return await self.semantic_search(
            collection_name="events",
            query=query,
            limit=limit,
            filters={"store_id": store_id}
        )


# 创建全局实例
vector_db_service = VectorDatabaseService()
