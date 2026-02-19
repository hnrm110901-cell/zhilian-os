"""
性能基准测试
Performance Benchmark Tests

使用pytest-benchmark进行性能基准测试
"""
import pytest
import asyncio
import time
from typing import List, Dict, Any


class TestPerformanceBenchmarks:
    """性能基准测试套件"""

    @pytest.fixture
    def sample_orders(self) -> List[Dict[str, Any]]:
        """生成测试订单数据"""
        return [
            {
                "order_id": f"BENCH_ORDER_{i:06d}",
                "order_number": f"NO2024{i:08d}",
                "order_type": "dine_in",
                "total": 100.0 + i,
                "created_at": "2024-02-19T10:00:00",
                "store_id": "STORE001",
            }
            for i in range(100)
        ]

    @pytest.fixture
    def sample_dishes(self) -> List[Dict[str, Any]]:
        """生成测试菜品数据"""
        return [
            {
                "dish_id": f"BENCH_DISH_{i:06d}",
                "name": f"测试菜品{i}",
                "category": "热菜",
                "price": 30.0 + i,
                "is_available": True,
                "store_id": "STORE001",
            }
            for i in range(50)
        ]

    # ==================== 批量索引性能测试 ====================

    def test_batch_index_orders_performance(self, benchmark, sample_orders):
        """测试批量索引订单性能"""
        from src.services.vector_db_service_enhanced import vector_db_service_enhanced

        async def batch_index():
            if not vector_db_service_enhanced._initialized:
                await vector_db_service_enhanced.initialize()
            return await vector_db_service_enhanced.index_orders_batch(sample_orders)

        # 运行基准测试
        result = benchmark(lambda: asyncio.run(batch_index()))

        # 验证结果
        assert result["total"] == 100
        assert result["success"] >= 80  # 至少80%成功

    def test_batch_index_dishes_performance(self, benchmark, sample_dishes):
        """测试批量索引菜品性能"""
        from src.services.vector_db_service_enhanced import vector_db_service_enhanced

        async def batch_index():
            if not vector_db_service_enhanced._initialized:
                await vector_db_service_enhanced.initialize()
            return await vector_db_service_enhanced.index_dishes_batch(sample_dishes)

        result = benchmark(lambda: asyncio.run(batch_index()))

        assert result["total"] == 50
        assert result["success"] >= 40

    # ==================== 嵌入生成性能测试 ====================

    def test_embedding_generation_performance(self, benchmark):
        """测试嵌入向量生成性能"""
        from src.services.vector_db_service_enhanced import vector_db_service_enhanced

        async def init_service():
            if not vector_db_service_enhanced._initialized:
                await vector_db_service_enhanced.initialize()

        asyncio.run(init_service())

        text = "测试订单：宫保鸡丁 x2, 麻婆豆腐 x1, 米饭 x2"

        # 基准测试
        embedding = benchmark(vector_db_service_enhanced.generate_embedding, text)

        # 验证
        assert len(embedding) == 384
        assert all(isinstance(x, float) for x in embedding)

    def test_batch_embedding_generation_performance(self, benchmark):
        """测试批量嵌入向量生成性能"""
        from src.services.vector_db_service_enhanced import vector_db_service_enhanced

        async def init_service():
            if not vector_db_service_enhanced._initialized:
                await vector_db_service_enhanced.initialize()

        asyncio.run(init_service())

        texts = [f"测试文本{i}" for i in range(100)]

        def generate_batch():
            return [vector_db_service_enhanced.generate_embedding(text) for text in texts]

        embeddings = benchmark(generate_batch)

        assert len(embeddings) == 100
        assert all(len(e) == 384 for e in embeddings)

    # ==================== 语义搜索性能测试 ====================

    @pytest.mark.asyncio
    async def test_semantic_search_performance(self, benchmark):
        """测试语义搜索性能"""
        from src.services.vector_db_service_enhanced import vector_db_service_enhanced

        if not vector_db_service_enhanced._initialized:
            await vector_db_service_enhanced.initialize()

        # 先索引一些数据
        orders = [
            {
                "order_id": f"SEARCH_TEST_{i}",
                "order_number": f"NO{i:08d}",
                "order_type": "dine_in",
                "total": 100.0,
                "created_at": "2024-02-19T10:00:00",
                "store_id": "STORE001",
            }
            for i in range(10)
        ]
        await vector_db_service_enhanced.index_orders_batch(orders)

        # 等待索引完成
        await asyncio.sleep(1)

        async def search():
            return await vector_db_service_enhanced.semantic_search(
                collection_name="orders",
                query="查找订单",
                limit=10,
                filters={"store_id": "STORE001"}
            )

        # 基准测试
        results = benchmark(lambda: asyncio.run(search()))

        # 验证
        assert isinstance(results, list)

    # ==================== 健康检查性能测试 ====================

    @pytest.mark.asyncio
    async def test_health_check_performance(self, benchmark):
        """测试健康检查性能"""
        from src.services.vector_db_service_enhanced import vector_db_service_enhanced

        if not vector_db_service_enhanced._initialized:
            await vector_db_service_enhanced.initialize()

        async def health_check():
            return await vector_db_service_enhanced.health_check()

        # 基准测试
        result = benchmark(lambda: asyncio.run(health_check()))

        # 验证
        assert "status" in result
        assert result["initialized"] is True

    # ==================== 并发性能测试 ====================

    @pytest.mark.asyncio
    async def test_concurrent_indexing_performance(self, benchmark):
        """测试并发索引性能"""
        from src.services.vector_db_service_enhanced import vector_db_service_enhanced

        if not vector_db_service_enhanced._initialized:
            await vector_db_service_enhanced.initialize()

        async def concurrent_index():
            tasks = []
            for i in range(10):
                order = {
                    "order_id": f"CONCURRENT_{i}",
                    "order_number": f"NO{i:08d}",
                    "order_type": "dine_in",
                    "total": 100.0,
                    "created_at": "2024-02-19T10:00:00",
                    "store_id": "STORE001",
                }
                tasks.append(vector_db_service_enhanced.index_order(order))

            results = await asyncio.gather(*tasks)
            return results

        # 基准测试
        results = benchmark(lambda: asyncio.run(concurrent_index()))

        # 验证
        assert len(results) == 10
        assert all(r is True for r in results)


class TestAPIEndpointBenchmarks:
    """API端点性能基准测试"""

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        from fastapi.testclient import TestClient
        from src.main import app
        return TestClient(app)

    def test_health_endpoint_performance(self, benchmark, client):
        """测试健康检查端点性能"""
        def health_check():
            return client.get("/api/v1/health")

        response = benchmark(health_check)
        assert response.status_code == 200

    def test_metrics_endpoint_performance(self, benchmark, client):
        """测试metrics端点性能"""
        def get_metrics():
            return client.get("/metrics")

        response = benchmark(get_metrics)
        assert response.status_code == 200

    def test_batch_index_endpoint_performance(self, benchmark, client):
        """测试批量索引端点性能"""
        orders = [
            {
                "order_id": f"API_BENCH_{i}",
                "order_number": f"NO{i:08d}",
                "order_type": "dine_in",
                "total": 100.0,
                "created_at": "2024-02-19T10:00:00",
                "store_id": "STORE001",
            }
            for i in range(10)
        ]

        def batch_index():
            return client.post(
                "/api/v1/neural/batch/index/orders",
                json={"orders": orders}
            )

        response = benchmark(batch_index)
        assert response.status_code == 200


# 性能基准配置
def pytest_benchmark_group_stats(config, benchmarks, group_by):
    """自定义基准测试统计"""
    return {
        'min': min(b.stats['min'] for b in benchmarks),
        'max': max(b.stats['max'] for b in benchmarks),
        'mean': sum(b.stats['mean'] for b in benchmarks) / len(benchmarks),
        'median': sorted(b.stats['median'] for b in benchmarks)[len(benchmarks) // 2],
    }


if __name__ == "__main__":
    # 运行基准测试
    pytest.main([
        __file__,
        "-v",
        "--benchmark-only",
        "--benchmark-autosave",
        "--benchmark-save-data",
        "--benchmark-compare"
    ])
