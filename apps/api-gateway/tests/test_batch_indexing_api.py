"""
批量索引API测试
Test Batch Indexing API

测试批量索引API端点的功能和性能
"""
import pytest
from fastapi.testclient import TestClient
from typing import List, Dict, Any


class TestBatchIndexingAPI:
    """批量索引API测试套件"""

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        from src.main import app
        return TestClient(app)

    # ==================== 正常场景测试 ====================

    def test_batch_index_orders_success(self, client):
        """测试批量索引订单成功"""
        orders = [
            {
                "order_id": f"BATCH_ORDER_{i:03d}",
                "order_number": f"NO2024{i:04d}",
                "order_type": "dine_in",
                "total": 100.00 + i,
                "created_at": "2024-02-19T10:00:00",
                "store_id": "STORE001",
            }
            for i in range(10)
        ]

        response = client.post(
            "/api/v1/neural/batch/index/orders",
            json={"orders": orders}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total"] == 10
        assert data["indexed"] >= 8  # 至少80%成功
        assert "duration_seconds" in data

    def test_batch_index_dishes_success(self, client):
        """测试批量索引菜品成功"""
        dishes = [
            {
                "dish_id": f"DISH{i:03d}",
                "name": f"测试菜品{i}",
                "category": "热菜",
                "price": 30.00 + i,
                "is_available": True,
                "store_id": "STORE001",
            }
            for i in range(5)
        ]

        response = client.post(
            "/api/v1/neural/batch/index/dishes",
            json={"dishes": dishes}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total"] == 5
        assert data["indexed"] >= 4

    def test_batch_index_events_success(self, client):
        """测试批量索引事件成功"""
        events = [
            {
                "event_id": f"EVENT{i:03d}",
                "event_type": "order.created",
                "event_source": "api",
                "timestamp": "2024-02-19T10:00:00",
                "store_id": "STORE001",
                "priority": 1,
            }
            for i in range(8)
        ]

        response = client.post(
            "/api/v1/neural/batch/index/events",
            json={"events": events}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total"] == 8
        assert data["indexed"] >= 6

    # ==================== 边界场景测试 ====================

    def test_batch_index_empty_list(self, client):
        """测试空列表"""
        response = client.post(
            "/api/v1/neural/batch/index/orders",
            json={"orders": []}
        )

        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_batch_index_large_batch(self, client):
        """测试大批量索引"""
        orders = [
            {
                "order_id": f"LARGE_BATCH_{i:04d}",
                "order_number": f"NO2024{i:05d}",
                "order_type": "dine_in",
                "total": 100.00,
                "created_at": "2024-02-19T10:00:00",
                "store_id": "STORE001",
            }
            for i in range(100)
        ]

        response = client.post(
            "/api/v1/neural/batch/index/orders",
            json={"orders": orders}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 100
        assert data["duration_seconds"] < 30  # 应在30秒内完成

    def test_batch_index_max_limit(self, client):
        """测试超过最大限制"""
        orders = [
            {
                "order_id": f"MAX_LIMIT_{i:05d}",
                "order_number": f"NO2024{i:06d}",
                "order_type": "dine_in",
                "total": 100.00,
                "created_at": "2024-02-19T10:00:00",
                "store_id": "STORE001",
            }
            for i in range(1001)  # 超过1000的限制
        ]

        response = client.post(
            "/api/v1/neural/batch/index/orders",
            json={"orders": orders}
        )

        assert response.status_code == 400
        assert "limit" in response.json()["detail"].lower()

    # ==================== 异常场景测试 ====================

    def test_batch_index_invalid_data(self, client):
        """测试无效数据"""
        orders = [
            {
                "order_id": "INVALID_ORDER",
                # 缺少必需字段
            }
        ]

        response = client.post(
            "/api/v1/neural/batch/index/orders",
            json={"orders": orders}
        )

        # 应该返回部分成功的结果
        assert response.status_code == 200
        data = response.json()
        assert data["failed"] > 0
        assert len(data["errors"]) > 0

    def test_batch_index_mixed_valid_invalid(self, client):
        """测试混合有效和无效数据"""
        orders = [
            # 有效订单
            {
                "order_id": "VALID_ORDER_001",
                "order_number": "NO20240001",
                "order_type": "dine_in",
                "total": 100.00,
                "created_at": "2024-02-19T10:00:00",
                "store_id": "STORE001",
            },
            # 无效订单（缺少字段）
            {
                "order_id": "INVALID_ORDER_001",
            },
            # 有效订单
            {
                "order_id": "VALID_ORDER_002",
                "order_number": "NO20240002",
                "order_type": "takeout",
                "total": 150.00,
                "created_at": "2024-02-19T11:00:00",
                "store_id": "STORE001",
            },
        ]

        response = client.post(
            "/api/v1/neural/batch/index/orders",
            json={"orders": orders}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert data["indexed"] == 2
        assert data["failed"] == 1

    def test_batch_index_missing_request_body(self, client):
        """测试缺少请求体"""
        response = client.post(
            "/api/v1/neural/batch/index/orders",
            json={}
        )

        assert response.status_code == 422  # Validation error

    # ==================== 性能场景测试 ====================

    def test_batch_index_performance(self, client):
        """测试批量索引性能"""
        import time

        orders = [
            {
                "order_id": f"PERF_ORDER_{i:04d}",
                "order_number": f"NO2024{i:05d}",
                "order_type": "dine_in",
                "total": 100.00,
                "created_at": "2024-02-19T10:00:00",
                "store_id": "STORE001",
            }
            for i in range(50)
        ]

        start_time = time.time()
        response = client.post(
            "/api/v1/neural/batch/index/orders",
            json={"orders": orders}
        )
        end_time = time.time()

        assert response.status_code == 200
        duration = end_time - start_time
        assert duration < 10  # 应在10秒内完成

        data = response.json()
        throughput = data["total"] / data["duration_seconds"]
        assert throughput > 5  # 每秒至少处理5个订单

    def test_batch_index_response_format(self, client):
        """测试响应格式"""
        orders = [
            {
                "order_id": "FORMAT_TEST_001",
                "order_number": "NO20240001",
                "order_type": "dine_in",
                "total": 100.00,
                "created_at": "2024-02-19T10:00:00",
                "store_id": "STORE001",
            }
        ]

        response = client.post(
            "/api/v1/neural/batch/index/orders",
            json={"orders": orders}
        )

        assert response.status_code == 200
        data = response.json()

        # 验证响应格式
        assert "success" in data
        assert "total" in data
        assert "indexed" in data
        assert "failed" in data
        assert "errors" in data
        assert "duration_seconds" in data
        assert isinstance(data["errors"], list)


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
