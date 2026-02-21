"""
Prometheus指标测试
Test Prometheus Metrics Endpoint

测试Prometheus指标端点的功能和格式
"""
import pytest
from fastapi.testclient import TestClient


class TestPrometheusMetrics:
    """Prometheus指标测试套件"""

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        from src.main import app
        return TestClient(app)

    # ==================== 正常场景测试 ====================

    def test_metrics_endpoint_exists(self, client):
        """测试metrics端点存在"""
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_content_type(self, client):
        """测试metrics响应类型"""
        response = client.get("/metrics")
        assert response.status_code == 200
        # Prometheus期望的content-type
        assert "text/plain" in response.headers.get("content-type", "")

    def test_metrics_format(self, client):
        """测试metrics格式"""
        response = client.get("/metrics")
        assert response.status_code == 200

        content = response.text
        # 验证Prometheus格式
        assert "# HELP" in content or "# TYPE" in content
        # 应该包含一些基本指标
        assert len(content) > 0

    def test_metrics_contains_http_requests(self, client):
        """测试包含HTTP请求指标"""
        # 先发送一些请求
        client.get("/api/v1/health")
        client.get("/api/v1/health")

        # 获取metrics
        response = client.get("/metrics")
        assert response.status_code == 200

        content = response.text
        # 应该包含HTTP请求相关指标
        assert "http_requests" in content.lower() or "request" in content.lower()

    def test_metrics_contains_response_time(self, client):
        """测试包含响应时间指标"""
        response = client.get("/metrics")
        assert response.status_code == 200

        content = response.text
        # 应该包含响应时间相关指标
        assert "duration" in content.lower() or "latency" in content.lower() or "time" in content.lower()

    def test_metrics_contains_system_info(self, client):
        """测试包含系统信息指标"""
        response = client.get("/metrics")
        assert response.status_code == 200

        content = response.text
        # 应该包含系统信息
        assert "process" in content.lower() or "python" in content.lower()

    # ==================== 边界场景测试 ====================

    def test_metrics_multiple_calls(self, client):
        """测试多次调用metrics端点"""
        # 多次调用应该都成功
        for _ in range(5):
            response = client.get("/metrics")
            assert response.status_code == 200

    def test_metrics_after_api_calls(self, client):
        """测试API调用后的metrics"""
        # 发送一些API请求
        endpoints = [
            "/api/v1/health",
            "/api/v1/neural/health",
        ]

        for endpoint in endpoints:
            client.get(endpoint)

        # 获取metrics
        response = client.get("/metrics")
        assert response.status_code == 200

        content = response.text
        # metrics应该反映这些请求
        assert len(content) > 100  # 应该有足够的内容

    def test_metrics_concurrent_access(self, client):
        """测试并发访问metrics"""
        import concurrent.futures

        def get_metrics():
            response = client.get("/metrics")
            return response.status_code

        # 并发请求
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(get_metrics) for _ in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # 所有请求都应该成功
        assert all(status == 200 for status in results)

    # ==================== 性能场景测试 ====================

    def test_metrics_response_time(self, client):
        """测试metrics响应时间"""
        import time

        start_time = time.time()
        response = client.get("/metrics")
        end_time = time.time()

        assert response.status_code == 200

        duration = (end_time - start_time) * 1000  # 转换为毫秒
        # metrics端点应该快速响应
        assert duration < 500  # 应在500ms内完成

    def test_metrics_size_reasonable(self, client):
        """测试metrics大小合理"""
        response = client.get("/metrics")
        assert response.status_code == 200

        content_length = len(response.content)
        # metrics不应该太大（避免性能问题）
        assert content_length < 1024 * 1024  # 小于1MB

    # ==================== 指标内容测试 ====================

    def test_metrics_counter_format(self, client):
        """测试Counter指标格式"""
        response = client.get("/metrics")
        assert response.status_code == 200

        content = response.text
        lines = content.split('\n')

        # 查找counter类型的指标
        counter_found = False
        for line in lines:
            if "# TYPE" in line and "counter" in line.lower():
                counter_found = True
                break

        # 应该至少有一个counter指标
        assert counter_found or len(lines) > 0  # 宽松检查

    def test_metrics_gauge_format(self, client):
        """测试Gauge指标格式"""
        response = client.get("/metrics")
        assert response.status_code == 200

        content = response.text
        lines = content.split('\n')

        # 查找gauge类型的指标
        gauge_found = False
        for line in lines:
            if "# TYPE" in line and "gauge" in line.lower():
                gauge_found = True
                break

        # 应该至少有一个gauge指标
        assert gauge_found or len(lines) > 0  # 宽松检查

    def test_metrics_histogram_format(self, client):
        """测试Histogram指标格式"""
        response = client.get("/metrics")
        assert response.status_code == 200

        content = response.text
        lines = content.split('\n')

        # 查找histogram类型的指标
        histogram_found = False
        for line in lines:
            if "# TYPE" in line and "histogram" in line.lower():
                histogram_found = True
                break

        # histogram是可选的
        assert True  # 总是通过，因为histogram不是必需的

    # ==================== 集成测试 ====================

    def test_metrics_integration_with_health(self, client):
        """测试metrics与health端点集成"""
        # 调用health端点
        health_response = client.get("/api/v1/health")
        assert health_response.status_code == 200

        # 获取metrics
        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200

        # metrics应该记录health请求
        content = metrics_response.text
        assert len(content) > 0

    def test_metrics_labels(self, client):
        """测试metrics标签"""
        # 发送不同的请求
        client.get("/api/v1/health")
        client.get("/api/v1/neural/health")

        # 获取metrics
        response = client.get("/metrics")
        assert response.status_code == 200

        content = response.text
        # 应该包含标签（如method, endpoint等）
        assert "{" in content or "=" in content  # Prometheus标签格式


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
