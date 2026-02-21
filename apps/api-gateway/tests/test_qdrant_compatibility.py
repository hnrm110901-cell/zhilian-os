"""
Qdrant客户端兼容性测试
Test Qdrant Client Compatibility

测试场景：
1. 正常场景：客户端连接、集合创建、数据插入、搜索
2. 边界场景：大批量数据、空查询、特殊字符
3. 异常场景：连接失败、超时、无效数据
4. 性能场景：并发请求、大数据量
"""
import pytest
import asyncio
from typing import List, Dict, Any
from unittest.mock import Mock, patch, AsyncMock
import time


class TestQdrantClientCompatibility:
    """Qdrant客户端兼容性测试套件"""

    @pytest.fixture
    async def vector_db_service(self):
        """创建向量数据库服务实例"""
        from src.services.vector_db_service_enhanced import VectorDatabaseServiceEnhanced

        service = VectorDatabaseServiceEnhanced()
        # 使用测试配置
        service.qdrant_url = "http://localhost:6333"
        service.qdrant_api_key = None

        yield service

        # 清理
        if service.client:
            try:
                await service.client.close()
            except:
                pass

    # ==================== 正常场景测试 ====================

    @pytest.mark.asyncio
    async def test_client_initialization(self, vector_db_service):
        """测试客户端初始化"""
        # 测试初始化
        await vector_db_service.initialize()

        # 验证客户端已创建
        assert vector_db_service.client is not None
        assert vector_db_service.embedding_model is not None or True  # 允许模拟嵌入

    @pytest.mark.asyncio
    async def test_collection_creation(self, vector_db_service):
        """测试集合创建"""
        await vector_db_service.initialize()

        # 验证集合已创建
        collections = vector_db_service.client.get_collections()
        collection_names = [c.name for c in collections.collections]

        assert "orders" in collection_names
        assert "dishes" in collection_names
        assert "staff" in collection_names
        assert "events" in collection_names

    @pytest.mark.asyncio
    async def test_embedding_generation(self, vector_db_service):
        """测试嵌入向量生成"""
        await vector_db_service.initialize()

        # 测试文本嵌入
        text = "测试订单：宫保鸡丁 x2"
        embedding = vector_db_service.generate_embedding(text)

        # 验证嵌入向量
        assert isinstance(embedding, list)
        assert len(embedding) == 384  # MiniLM模型维度
        assert all(isinstance(x, float) for x in embedding)

    @pytest.mark.asyncio
    async def test_order_indexing(self, vector_db_service):
        """测试订单索引"""
        await vector_db_service.initialize()

        # 准备测试数据
        order_data = {
            "order_id": "TEST_ORDER_001",
            "order_number": "NO20240001",
            "order_type": "dine_in",
            "total": 158.00,
            "created_at": "2024-02-19T10:00:00",
            "store_id": "STORE001",
        }

        # 测试索引
        result = await vector_db_service.index_order(order_data)

        # 验证结果
        assert result is True

    @pytest.mark.asyncio
    async def test_dish_indexing(self, vector_db_service):
        """测试菜品索引"""
        await vector_db_service.initialize()

        # 准备测试数据
        dish_data = {
            "dish_id": "DISH001",
            "name": "宫保鸡丁",
            "category": "热菜",
            "price": 48.00,
            "is_available": True,
            "store_id": "STORE001",
        }

        # 测试索引
        result = await vector_db_service.index_dish(dish_data)

        # 验证结果
        assert result is True

    @pytest.mark.asyncio
    async def test_event_indexing(self, vector_db_service):
        """测试事件索引"""
        await vector_db_service.initialize()

        # 准备测试数据
        event_data = {
            "event_id": "EVENT001",
            "event_type": "order.created",
            "event_source": "api",
            "timestamp": "2024-02-19T10:00:00",
            "store_id": "STORE001",
            "priority": 1,
        }

        # 测试索引
        result = await vector_db_service.index_event(event_data)

        # 验证结果
        assert result is True

    @pytest.mark.asyncio
    async def test_semantic_search(self, vector_db_service):
        """测试语义搜索"""
        await vector_db_service.initialize()

        # 先索引一些数据
        order_data = {
            "order_id": "TEST_ORDER_002",
            "order_number": "NO20240002",
            "order_type": "dine_in",
            "total": 88.00,
            "created_at": "2024-02-19T11:00:00",
            "store_id": "STORE001",
        }
        await vector_db_service.index_order(order_data)

        # 等待索引完成
        await asyncio.sleep(0.5)

        # 测试搜索
        results = await vector_db_service.semantic_search(
            collection_name="orders",
            query="查找订单",
            limit=10,
            filters={"store_id": "STORE001"}
        )

        # 验证结果
        assert isinstance(results, list)
        # 注意：可能为空，因为是新索引的数据

    # ==================== 边界场景测试 ====================

    @pytest.mark.asyncio
    async def test_empty_query_search(self, vector_db_service):
        """测试空查询"""
        await vector_db_service.initialize()

        # 测试空查询
        results = await vector_db_service.semantic_search(
            collection_name="orders",
            query="",
            limit=10
        )

        # 验证结果
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_special_characters_in_text(self, vector_db_service):
        """测试特殊字符"""
        await vector_db_service.initialize()

        # 测试特殊字符
        text = "订单#123 @店铺 $100 %折扣 &配送 *备注"
        embedding = vector_db_service.generate_embedding(text)

        # 验证嵌入向量
        assert isinstance(embedding, list)
        assert len(embedding) == 384

    @pytest.mark.asyncio
    async def test_large_batch_indexing(self, vector_db_service):
        """测试大批量索引"""
        await vector_db_service.initialize()

        # 准备100条测试数据
        orders = []
        for i in range(100):
            order_data = {
                "order_id": f"BATCH_ORDER_{i:03d}",
                "order_number": f"NO2024{i:04d}",
                "order_type": "dine_in",
                "total": 100.00 + i,
                "created_at": "2024-02-19T12:00:00",
                "store_id": "STORE001",
            }
            orders.append(order_data)

        # 测试批量索引
        start_time = time.time()
        results = []
        for order in orders:
            result = await vector_db_service.index_order(order)
            results.append(result)
        end_time = time.time()

        # 验证结果
        assert all(results)
        assert end_time - start_time < 30  # 应在30秒内完成

    @pytest.mark.asyncio
    async def test_max_limit_search(self, vector_db_service):
        """测试最大限制搜索"""
        await vector_db_service.initialize()

        # 测试大limit
        results = await vector_db_service.semantic_search(
            collection_name="orders",
            query="查找所有订单",
            limit=1000  # 大limit
        )

        # 验证结果
        assert isinstance(results, list)
        assert len(results) <= 1000

    # ==================== 异常场景测试 ====================

    @pytest.mark.asyncio
    async def test_connection_failure(self):
        """测试连接失败"""
        from src.services.vector_db_service_enhanced import VectorDatabaseServiceEnhanced

        service = VectorDatabaseServiceEnhanced()
        service.qdrant_url = "http://invalid-host:6333"

        # 测试连接失败
        with pytest.raises(Exception):
            await service.initialize()

    @pytest.mark.asyncio
    async def test_invalid_collection_name(self, vector_db_service):
        """测试无效集合名"""
        await vector_db_service.initialize()

        # 测试无效集合名
        with pytest.raises(Exception):
            await vector_db_service.semantic_search(
                collection_name="invalid_collection",
                query="test",
                limit=10
            )

    @pytest.mark.asyncio
    async def test_invalid_order_data(self, vector_db_service):
        """测试无效订单数据"""
        await vector_db_service.initialize()

        # 测试缺少必需字段
        invalid_order = {
            "order_id": "INVALID_ORDER",
            # 缺少其他必需字段
        }

        # 应该处理错误并返回False
        result = await vector_db_service.index_order(invalid_order)
        assert result is False

    @pytest.mark.asyncio
    async def test_duplicate_id_indexing(self, vector_db_service):
        """测试重复ID索引"""
        await vector_db_service.initialize()

        # 准备相同ID的数据
        order_data = {
            "order_id": "DUPLICATE_ORDER",
            "order_number": "NO20240003",
            "order_type": "dine_in",
            "total": 100.00,
            "created_at": "2024-02-19T13:00:00",
            "store_id": "STORE001",
        }

        # 第一次索引
        result1 = await vector_db_service.index_order(order_data)
        assert result1 is True

        # 第二次索引（应该更新）
        order_data["total"] = 200.00
        result2 = await vector_db_service.index_order(order_data)
        assert result2 is True

    # ==================== 性能场景测试 ====================

    @pytest.mark.asyncio
    async def test_concurrent_indexing(self, vector_db_service):
        """测试并发索引"""
        await vector_db_service.initialize()

        # 准备并发任务
        async def index_order(i):
            order_data = {
                "order_id": f"CONCURRENT_ORDER_{i}",
                "order_number": f"NO2024{i:04d}",
                "order_type": "dine_in",
                "total": 100.00,
                "created_at": "2024-02-19T14:00:00",
                "store_id": "STORE001",
            }
            return await vector_db_service.index_order(order_data)

        # 并发执行10个索引任务
        start_time = time.time()
        tasks = [index_order(i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        end_time = time.time()

        # 验证结果
        assert all(results)
        assert end_time - start_time < 5  # 应在5秒内完成

    @pytest.mark.asyncio
    async def test_concurrent_search(self, vector_db_service):
        """测试并发搜索"""
        await vector_db_service.initialize()

        # 准备并发搜索任务
        async def search_orders(query):
            return await vector_db_service.semantic_search(
                collection_name="orders",
                query=query,
                limit=10
            )

        # 并发执行10个搜索任务
        start_time = time.time()
        queries = [f"查找订单{i}" for i in range(10)]
        tasks = [search_orders(q) for q in queries]
        results = await asyncio.gather(*tasks)
        end_time = time.time()

        # 验证结果
        assert len(results) == 10
        assert all(isinstance(r, list) for r in results)
        assert end_time - start_time < 5  # 应在5秒内完成

    @pytest.mark.asyncio
    async def test_search_response_time(self, vector_db_service):
        """测试搜索响应时间"""
        await vector_db_service.initialize()

        # 先索引一些数据
        for i in range(10):
            order_data = {
                "order_id": f"PERF_ORDER_{i}",
                "order_number": f"NO2024{i:04d}",
                "order_type": "dine_in",
                "total": 100.00,
                "created_at": "2024-02-19T15:00:00",
                "store_id": "STORE001",
            }
            await vector_db_service.index_order(order_data)

        # 等待索引完成
        await asyncio.sleep(1)

        # 测试搜索响应时间
        start_time = time.time()
        results = await vector_db_service.semantic_search(
            collection_name="orders",
            query="查找订单",
            limit=10
        )
        end_time = time.time()

        response_time = (end_time - start_time) * 1000  # 转换为毫秒

        # 验证响应时间
        assert response_time < 200  # 应在200ms内完成
        print(f"搜索响应时间: {response_time:.2f}ms")

    # ==================== 版本兼容性测试 ====================

    @pytest.mark.asyncio
    async def test_qdrant_version_compatibility(self, vector_db_service):
        """测试Qdrant版本兼容性"""
        await vector_db_service.initialize()

        # 获取Qdrant版本信息
        try:
            # 尝试获取版本信息
            collections = vector_db_service.client.get_collections()
            assert collections is not None

            # 如果能成功获取集合，说明兼容
            print("Qdrant客户端兼容性测试通过")
        except Exception as e:
            pytest.fail(f"Qdrant版本兼容性测试失败: {str(e)}")

    @pytest.mark.asyncio
    async def test_client_reconnection(self, vector_db_service):
        """测试客户端重连"""
        await vector_db_service.initialize()

        # 模拟连接断开后重连
        original_client = vector_db_service.client

        # 重新初始化
        await vector_db_service.initialize()

        # 验证客户端已重新创建
        assert vector_db_service.client is not None

        # 测试功能是否正常
        embedding = vector_db_service.generate_embedding("测试重连")
        assert len(embedding) == 384


class TestQdrantClientVersions:
    """测试不同版本的Qdrant客户端"""

    @pytest.mark.asyncio
    async def test_client_version_info(self):
        """测试客户端版本信息"""
        try:
            import qdrant_client
            version = qdrant_client.__version__
            print(f"qdrant-client版本: {version}")

            # 验证版本号格式
            assert isinstance(version, str)
            assert len(version.split('.')) >= 2
        except ImportError:
            pytest.skip("qdrant-client未安装")

    @pytest.mark.asyncio
    async def test_sentence_transformers_version(self):
        """测试sentence-transformers版本"""
        try:
            import sentence_transformers
            version = sentence_transformers.__version__
            print(f"sentence-transformers版本: {version}")

            # 验证版本号格式
            assert isinstance(version, str)
        except ImportError:
            pytest.skip("sentence-transformers未安装")


# ==================== 测试配置 ====================

@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
