"""
向量数据库服务 - 改进版
Vector Database Service - Enhanced Version

改进点：
1. 添加连接重试机制
2. 改进错误处理
3. 添加健康检查
4. 支持批量操作
5. 添加性能监控
6. 兼容性增强
7. 添加熔断器防止Silent Failure
"""
from typing import List, Dict, Any, Optional
import structlog
from datetime import datetime
import hashlib
import json
import asyncio
import os
from functools import wraps
import time

from ..core.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

logger = structlog.get_logger()


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """重试装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"操作失败，正在重试",
                            function=func.__name__,
                            attempt=attempt + 1,
                            error=str(e)
                        )
                        await asyncio.sleep(delay * (attempt + 1))
                    else:
                        logger.error(
                            f"操作失败，已达最大重试次数",
                            function=func.__name__,
                            error=str(e)
                        )
            raise last_exception
        return wrapper
    return decorator


class VectorDatabaseServiceEnhanced:
    """向量数据库服务 - 增强版"""

    def __init__(self):
        """初始化向量数据库服务"""
        from src.core.config import settings

        self.qdrant_url = settings.QDRANT_URL
        self.qdrant_api_key = settings.QDRANT_API_KEY
        self.client = None
        self.embedding_model = None
        self._initialized = False
        self._client_version = None

        # 初始化熔断器（防止Silent Failure）
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=int(os.getenv("VECTOR_DB_CB_FAILURE_THRESHOLD", "5")),    # 连续失败N次后熔断
            success_threshold=int(os.getenv("VECTOR_DB_CB_SUCCESS_THRESHOLD", "2")),    # 半开状态成功N次后恢复
            timeout=float(os.getenv("VECTOR_DB_CB_TIMEOUT", "60.0")),                  # 熔断N秒后尝试恢复
            expected_exception=Exception,
        )

        logger.info("VectorDatabaseServiceEnhanced初始化完成（带熔断器）")

    @retry_on_failure(max_retries=int(os.getenv("VECTOR_DB_RETRY_MAX", "3")), delay=float(os.getenv("VECTOR_DB_RETRY_DELAY_LONG", "2.0")))
    async def initialize(self):
        """初始化Qdrant客户端和嵌入模型（带重试）"""
        if self._initialized:
            logger.info("向量数据库已初始化，跳过")
            return

        try:
            # 初始化Qdrant客户端
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            # 记录客户端版本（如果可用）
            try:
                import qdrant_client
                self._client_version = getattr(qdrant_client, '__version__', 'unknown')
            except:
                self._client_version = 'unknown'

            logger.info(f"使用qdrant-client版本: {self._client_version}")

            # 创建客户端（使用gRPC协议以避免HTTP 503错误）
            self.client = QdrantClient(
                host=self.qdrant_url.replace('http://', '').replace('https://', '').split(':')[0],
                port=int(os.getenv("QDRANT_GRPC_PORT", "6334")),  # gRPC端口
                prefer_grpc=True,
                timeout=int(os.getenv("QDRANT_TIMEOUT", "30")),
            )

            # 测试连接
            await self._test_connection()

            # 初始化嵌入模型
            await self._initialize_embedding_model()

            # 创建集合
            await self._ensure_collections()

            self._initialized = True
            logger.info("向量数据库初始化成功")

        except Exception as e:
            logger.error("向量数据库初始化失败", error=str(e))
            self._initialized = False
            raise

    async def _test_connection(self):
        """测试Qdrant连接"""
        try:
            # 尝试获取集合列表
            collections = self.client.get_collections()
            logger.info(f"Qdrant连接成功，当前集合数: {len(collections.collections)}")
        except Exception as e:
            logger.error("Qdrant连接失败", error=str(e))
            raise ConnectionError(f"无法连接到Qdrant: {str(e)}")

    async def _initialize_embedding_model(self):
        """初始化嵌入模型"""
        try:
            from sentence_transformers import SentenceTransformer

            # 记录版本（如果可用）
            try:
                import sentence_transformers
                version = getattr(sentence_transformers, '__version__', 'unknown')
                logger.info(f"sentence-transformers版本: {version}")
            except:
                pass

            # 加载模型（可能需要下载）
            model_name = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
            self.embedding_model = SentenceTransformer(
                model_name,
                device='cpu'  # 使用CPU，避免GPU依赖
            )
            logger.info("嵌入模型加载成功", model=model_name)

        except Exception as e:
            logger.warning(f"嵌入模型加载失败，将使用模拟嵌入: {str(e)}")
            self.embedding_model = None

    async def _ensure_collections(self):
        """确保所有必需的集合存在"""
        from qdrant_client.models import Distance, VectorParams

        collections = [
            {
                "name": "orders",
                "description": "订单向量集合",
                "vector_size": 384,
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
                else:
                    logger.info(f"集合已存在: {collection['name']}")

            except Exception as e:
                logger.error(f"处理集合失败: {collection['name']}", error=str(e))
                # 不抛出异常，继续处理其他集合

    def generate_embedding(self, text: str) -> List[float]:
        """
        生成文本嵌入向量

        Args:
            text: 输入文本

        Returns:
            嵌入向量
        """
        if not text or not text.strip():
            # 空文本返回零向量
            return [0.0] * 384

        if self.embedding_model:
            try:
                # 使用实际的嵌入模型
                embedding = self.embedding_model.encode(text, convert_to_numpy=True)
                return embedding.tolist()
            except Exception as e:
                logger.error(f"嵌入生成失败，使用模拟嵌入: {str(e)}")
                return self._generate_mock_embedding(text)
        else:
            # 模拟嵌入
            return self._generate_mock_embedding(text)

    def _generate_mock_embedding(self, text: str) -> List[float]:
        """生成确定性哈希向量（嵌入模型不可用时的fallback，语义无意义）"""
        import random
        random.seed(hashlib.md5(text.encode()).hexdigest())
        return [random.random() for _ in range(int(os.getenv("VECTOR_EMBEDDING_DIM", "384")))]

    @retry_on_failure(max_retries=int(os.getenv("VECTOR_DB_RETRY_MAX_SHORT", "2")), delay=float(os.getenv("VECTOR_DB_RETRY_DELAY", "1.0")))
    async def index_order(self, order_data: Dict[str, Any]) -> bool:
        """
        索引订单到向量数据库（带重试和熔断器）

        Args:
            order_data: 订单数据

        Returns:
            是否成功
        """
        try:
            # 使用熔断器保护Qdrant操作
            return await self.circuit_breaker.call_async(
                self._index_order_internal,
                order_data
            )
        except CircuitBreakerOpenError as e:
            logger.warning(
                "熔断器打开，订单索引降级",
                order_id=order_data.get("order_id"),
                error=str(e),
            )
            # 降级策略：记录到日志，返回False但不抛出异常
            return False

    async def _index_order_internal(self, order_data: Dict[str, Any]) -> bool:
        """
        内部订单索引方法（被熔断器保护）

        Args:
            order_data: 订单数据

        Returns:
            是否成功
        """
        # 验证必需字段
        required_fields = ["order_id", "order_number", "order_type", "total", "created_at", "store_id"]
        for field in required_fields:
            if field not in order_data:
                logger.error(f"订单数据缺少必需字段: {field}")
                return False

        # 生成订单的文本表示
        text = self._order_to_text(order_data)

        # 生成嵌入向量
        embedding = self.generate_embedding(text)

        # 存储到Qdrant
        from qdrant_client.models import PointStruct

        # 生成唯一ID（使用order_id的哈希值转换为整数）
        point_id = int(hashlib.md5(order_data["order_id"].encode()).hexdigest()[:16], 16)

        point = PointStruct(
            id=point_id,
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

    async def index_orders_batch(self, orders: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        批量索引订单

        Args:
            orders: 订单列表

        Returns:
            批量索引结果统计
        """
        start_time = time.time()
        success_count = 0
        failure_count = 0
        errors = []

        try:
            from qdrant_client.models import PointStruct

            points = []
            for order_data in orders:
                try:
                    # 验证必需字段
                    required_fields = ["order_id", "order_number", "order_type", "total", "created_at", "store_id"]
                    if not all(field in order_data for field in required_fields):
                        failure_count += 1
                        errors.append(f"订单 {order_data.get('order_id', 'unknown')} 缺少必需字段")
                        continue

                    # 生成文本和嵌入
                    text = self._order_to_text(order_data)
                    embedding = self.generate_embedding(text)

                    # 创建点
                    point_id = int(hashlib.md5(order_data["order_id"].encode()).hexdigest()[:16], 16)
                    point = PointStruct(
                        id=point_id,
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
                    points.append(point)
                    success_count += 1

                except Exception as e:
                    failure_count += 1
                    errors.append(f"订单 {order_data.get('order_id', 'unknown')} 处理失败: {str(e)}")

            # 批量插入
            if points:
                self.client.upsert(
                    collection_name="orders",
                    points=points,
                )

            end_time = time.time()
            duration = end_time - start_time

            logger.info(
                "批量订单索引完成",
                total=len(orders),
                success=success_count,
                failure=failure_count,
                duration_seconds=duration
            )

            return {
                "total": len(orders),
                "success": success_count,
                "failure": failure_count,
                "errors": errors[:10],  # 只返回前10个错误
                "duration_seconds": duration,
            }

        except Exception as e:
            logger.error("批量订单索引失败", error=str(e))
            return {
                "total": len(orders),
                "success": 0,
                "failure": len(orders),
                "errors": [str(e)],
                "duration_seconds": time.time() - start_time,
            }

    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查（包含熔断器状态）

        Returns:
            健康状态信息
        """
        health_status = {
            "status": "unknown",
            "initialized": self._initialized,
            "client_version": self._client_version,
            "embedding_model_loaded": self.embedding_model is not None,
            "collections": [],
            "circuit_breaker": self.circuit_breaker.get_stats(),
            "error": None,
        }

        try:
            if not self._initialized:
                health_status["status"] = "not_initialized"
                return health_status

            # 检查熔断器状态
            if self.circuit_breaker.state.value == "open":
                health_status["status"] = "circuit_breaker_open"
                health_status["error"] = "熔断器已打开，服务暂时不可用"
                return health_status

            # 检查Qdrant连接
            collections = self.client.get_collections()
            health_status["collections"] = [c.name for c in collections.collections]

            # 测试嵌入生成
            test_embedding = self.generate_embedding("健康检查测试")
            if len(test_embedding) != 384:
                raise ValueError("嵌入向量维度不正确")

            health_status["status"] = "healthy"

        except Exception as e:
            health_status["status"] = "unhealthy"
            health_status["error"] = str(e)
            logger.error("健康检查失败", error=str(e))

        return health_status

    @retry_on_failure(max_retries=int(os.getenv("VECTOR_DB_RETRY_MAX_SHORT", "2")), delay=float(os.getenv("VECTOR_DB_RETRY_DELAY", "1.0")))
    async def index_dish(self, dish_data: Dict[str, Any]) -> bool:
        """
        索引菜品到向量数据库（带重试）

        Args:
            dish_data: 菜品数据

        Returns:
            是否成功
        """
        try:
            # 验证必需字段
            required_fields = ["dish_id", "name", "category", "price", "is_available", "store_id"]
            for field in required_fields:
                if field not in dish_data:
                    logger.error(f"菜品数据缺少必需字段: {field}")
                    return False

            # 生成菜品的文本表示
            text = self._dish_to_text(dish_data)

            # 生成嵌入向量
            embedding = self.generate_embedding(text)

            # 存储到Qdrant
            from qdrant_client.models import PointStruct

            point_id = int(hashlib.md5(dish_data["dish_id"].encode()).hexdigest()[:16], 16)

            point = PointStruct(
                id=point_id,
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

        except KeyError as e:
            logger.error(f"菜品数据字段错误: {str(e)}")
            return False
        except Exception as e:
            logger.error("菜品索引失败", error=str(e))
            return False

    @retry_on_failure(max_retries=int(os.getenv("VECTOR_DB_RETRY_MAX_SHORT", "2")), delay=float(os.getenv("VECTOR_DB_RETRY_DELAY", "1.0")))
    async def index_event(self, event_data: Dict[str, Any]) -> bool:
        """
        索引神经系统事件到向量数据库（带重试）

        Args:
            event_data: 事件数据

        Returns:
            是否成功
        """
        try:
            # 验证必需字段
            required_fields = ["event_id", "event_type", "event_source", "timestamp", "store_id"]
            for field in required_fields:
                if field not in event_data:
                    logger.error(f"事件数据缺少必需字段: {field}")
                    return False

            # 生成事件的文本表示
            text = self._event_to_text(event_data)

            # 生成嵌入向量
            embedding = self.generate_embedding(text)

            # 存储到Qdrant
            from qdrant_client.models import PointStruct

            point_id = int(hashlib.md5(event_data["event_id"].encode()).hexdigest()[:16], 16)

            point = PointStruct(
                id=point_id,
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

        except KeyError as e:
            logger.error(f"事件数据字段错误: {str(e)}")
            return False
        except Exception as e:
            logger.error("事件索引失败", error=str(e))
            return False

    @retry_on_failure(max_retries=int(os.getenv("VECTOR_DB_RETRY_MAX_SHORT", "2")), delay=float(os.getenv("VECTOR_DB_RETRY_DELAY", "1.0")))
    async def semantic_search(
        self,
        collection_name: str,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        语义搜索（带重试）

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
            f"{item.get('dish_name', 'unknown')} x {item.get('quantity', 0)}"
            for item in order_data.get("items", [])
        ])

        return f"订单号 {order_data.get('order_number', 'N/A')}, " \
               f"类型 {order_data.get('order_type', 'N/A')}, " \
               f"菜品: {items_text if items_text else '无'}, " \
               f"总金额 {order_data.get('total', 0)}元"

    def _dish_to_text(self, dish_data: Dict[str, Any]) -> str:
        """将菜品数据转换为文本表示"""
        tags_text = ", ".join(dish_data.get("tags", []))

        return f"菜品 {dish_data.get('name', 'N/A')}, " \
               f"分类 {dish_data.get('category', 'N/A')}, " \
               f"价格 {dish_data.get('price', 0)}元, " \
               f"描述: {dish_data.get('description', '')}, " \
               f"标签: {tags_text}"

    def _event_to_text(self, event_data: Dict[str, Any]) -> str:
        """将事件数据转换为文本表示"""
        data_text = json.dumps(event_data.get("data", {}), ensure_ascii=False)

        return f"事件类型 {event_data.get('event_type', 'N/A')}, " \
               f"来源 {event_data.get('event_source', 'N/A')}, " \
               f"数据: {data_text}"

    async def search_orders(
        self,
        query: str,
        store_id: str,
        limit: int = 10
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
        limit: int = 10
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
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """搜索事件"""
        return await self.semantic_search(
            collection_name="events",
            query=query,
            limit=limit,
            filters={"store_id": store_id}
        )

    async def index_dishes_batch(self, dishes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        批量索引菜品

        Args:
            dishes: 菜品列表

        Returns:
            批量索引结果统计
        """
        start_time = time.time()
        success_count = 0
        failure_count = 0
        errors = []

        try:
            from qdrant_client.models import PointStruct

            points = []
            for dish_data in dishes:
                try:
                    # 验证必需字段
                    required_fields = ["dish_id", "name", "category", "price", "is_available", "store_id"]
                    if not all(field in dish_data for field in required_fields):
                        failure_count += 1
                        errors.append(f"菜品 {dish_data.get('dish_id', 'unknown')} 缺少必需字段")
                        continue

                    # 生成文本和嵌入
                    text = self._dish_to_text(dish_data)
                    embedding = self.generate_embedding(text)

                    # 创建点
                    point_id = int(hashlib.md5(dish_data["dish_id"].encode()).hexdigest()[:16], 16)
                    point = PointStruct(
                        id=point_id,
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
                    points.append(point)
                    success_count += 1

                except Exception as e:
                    failure_count += 1
                    errors.append(f"菜品 {dish_data.get('dish_id', 'unknown')} 处理失败: {str(e)}")

            # 批量插入
            if points:
                self.client.upsert(
                    collection_name="dishes",
                    points=points,
                )

            end_time = time.time()
            duration = end_time - start_time

            logger.info(
                "批量菜品索引完成",
                total=len(dishes),
                success=success_count,
                failure=failure_count,
                duration_seconds=duration
            )

            return {
                "total": len(dishes),
                "success": success_count,
                "failure": failure_count,
                "errors": errors[:10],
                "duration_seconds": duration,
            }

        except Exception as e:
            logger.error("批量菜品索引失败", error=str(e))
            return {
                "total": len(dishes),
                "success": 0,
                "failure": len(dishes),
                "errors": [str(e)],
                "duration_seconds": time.time() - start_time,
            }

    async def index_events_batch(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        批量索引事件

        Args:
            events: 事件列表

        Returns:
            批量索引结果统计
        """
        start_time = time.time()
        success_count = 0
        failure_count = 0
        errors = []

        try:
            from qdrant_client.models import PointStruct

            points = []
            for event_data in events:
                try:
                    # 验证必需字段
                    required_fields = ["event_id", "event_type", "event_source", "timestamp", "store_id"]
                    if not all(field in event_data for field in required_fields):
                        failure_count += 1
                        errors.append(f"事件 {event_data.get('event_id', 'unknown')} 缺少必需字段")
                        continue

                    # 生成文本和嵌入
                    text = self._event_to_text(event_data)
                    embedding = self.generate_embedding(text)

                    # 创建点
                    point_id = int(hashlib.md5(event_data["event_id"].encode()).hexdigest()[:16], 16)
                    point = PointStruct(
                        id=point_id,
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
                    points.append(point)
                    success_count += 1

                except Exception as e:
                    failure_count += 1
                    errors.append(f"事件 {event_data.get('event_id', 'unknown')} 处理失败: {str(e)}")

            # 批量插入
            if points:
                self.client.upsert(
                    collection_name="events",
                    points=points,
                )

            end_time = time.time()
            duration = end_time - start_time

            logger.info(
                "批量事件索引完成",
                total=len(events),
                success=success_count,
                failure=failure_count,
                duration_seconds=duration
            )

            return {
                "total": len(events),
                "success": success_count,
                "failure": failure_count,
                "errors": errors[:10],
                "duration_seconds": duration,
            }

        except Exception as e:
            logger.error("批量事件索引失败", error=str(e))
            return {
                "total": len(events),
                "success": 0,
                "failure": len(events),
                "errors": [str(e)],
                "duration_seconds": time.time() - start_time,
            }


# 创建全局实例
vector_db_service_enhanced = VectorDatabaseServiceEnhanced()
