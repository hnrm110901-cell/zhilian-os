"""
压力测试脚本
Stress Testing Script

使用Locust进行API压力测试
"""
from locust import HttpUser, task, between, events
import random
import json
from datetime import datetime


class APIGatewayUser(HttpUser):
    """API Gateway压力测试用户"""

    # 等待时间：1-3秒
    wait_time = between(1, 3)

    def on_start(self):
        """测试开始时执行"""
        # 可以在这里进行登录等初始化操作
        self.store_id = "STORE001"
        self.order_counter = 0
        self.dish_counter = 0
        self.event_counter = 0

    @task(5)
    def health_check(self):
        """健康检查 - 权重5（最常见）"""
        self.client.get("/api/v1/health")

    @task(3)
    def neural_health_check(self):
        """神经系统健康检查 - 权重3"""
        self.client.get("/api/v1/neural/health")

    @task(2)
    def batch_index_orders(self):
        """批量索引订单 - 权重2"""
        # 生成10个测试订单
        orders = []
        for i in range(10):
            self.order_counter += 1
            order = {
                "order_id": f"STRESS_ORDER_{self.order_counter:06d}",
                "order_number": f"NO2024{self.order_counter:08d}",
                "order_type": random.choice(["dine_in", "takeout", "delivery"]),
                "total": round(random.uniform(50, 500), 2),
                "created_at": datetime.now().isoformat(),
                "store_id": self.store_id,
            }
            orders.append(order)

        with self.client.post(
            "/api/v1/neural/batch/index/orders",
            json={"orders": orders},
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    response.success()
                else:
                    response.failure(f"Batch indexing failed: {data.get('errors', [])}")
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(2)
    def batch_index_dishes(self):
        """批量索引菜品 - 权重2"""
        # 生成5个测试菜品
        dishes = []
        for i in range(5):
            self.dish_counter += 1
            dish = {
                "dish_id": f"STRESS_DISH_{self.dish_counter:06d}",
                "name": f"测试菜品{self.dish_counter}",
                "category": random.choice(["热菜", "凉菜", "主食", "汤品", "饮料"]),
                "price": round(random.uniform(10, 100), 2),
                "is_available": True,
                "store_id": self.store_id,
            }
            dishes.append(dish)

        with self.client.post(
            "/api/v1/neural/batch/index/dishes",
            json={"dishes": dishes},
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    response.success()
                else:
                    response.failure(f"Batch indexing failed: {data.get('errors', [])}")
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(1)
    def batch_index_events(self):
        """批量索引事件 - 权重1"""
        # 生成8个测试事件
        events = []
        for i in range(8):
            self.event_counter += 1
            event = {
                "event_id": f"STRESS_EVENT_{self.event_counter:06d}",
                "event_type": random.choice([
                    "order.created", "order.completed", "order.cancelled",
                    "dish.updated", "inventory.low", "staff.checkin"
                ]),
                "event_source": "stress_test",
                "timestamp": datetime.now().isoformat(),
                "store_id": self.store_id,
                "priority": random.randint(0, 2),
            }
            events.append(event)

        with self.client.post(
            "/api/v1/neural/batch/index/events",
            json={"events": events},
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    response.success()
                else:
                    response.failure(f"Batch indexing failed: {data.get('errors', [])}")
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(3)
    def semantic_search_orders(self):
        """语义搜索订单 - 权重3"""
        queries = [
            "查找订单",
            "今天的订单",
            "外卖订单",
            "堂食订单",
            "大额订单"
        ]
        query = random.choice(queries)

        with self.client.post(
            "/api/v1/neural/search/orders",
            json={
                "query": query,
                "store_id": self.store_id,
                "top_k": 10
            },
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(2)
    def semantic_search_dishes(self):
        """语义搜索菜品 - 权重2"""
        queries = [
            "辣的菜",
            "素菜",
            "汤",
            "主食",
            "饮料"
        ]
        query = random.choice(queries)

        with self.client.post(
            "/api/v1/neural/search/dishes",
            json={
                "query": query,
                "store_id": self.store_id,
                "top_k": 10
            },
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(1)
    def get_metrics(self):
        """获取Prometheus指标 - 权重1"""
        self.client.get("/metrics")


class HighLoadUser(HttpUser):
    """高负载压力测试用户（更激进）"""

    # 更短的等待时间：0.5-1.5秒
    wait_time = between(0.5, 1.5)

    def on_start(self):
        """测试开始时执行"""
        self.store_id = "STORE001"
        self.counter = 0

    @task(10)
    def rapid_health_checks(self):
        """快速健康检查"""
        self.client.get("/api/v1/health")

    @task(5)
    def rapid_batch_operations(self):
        """快速批量操作"""
        # 生成50个订单（更大批量）
        orders = []
        for i in range(50):
            self.counter += 1
            order = {
                "order_id": f"HIGH_LOAD_{self.counter:08d}",
                "order_number": f"HL{self.counter:010d}",
                "order_type": "dine_in",
                "total": 100.0,
                "created_at": datetime.now().isoformat(),
                "store_id": self.store_id,
            }
            orders.append(order)

        self.client.post(
            "/api/v1/neural/batch/index/orders",
            json={"orders": orders}
        )


# Locust事件处理
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """测试开始时"""
    print("=" * 60)
    print("压力测试开始")
    print(f"目标主机: {environment.host}")
    print("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """测试结束时"""
    print("=" * 60)
    print("压力测试结束")
    print("=" * 60)

    # 打印统计信息
    stats = environment.stats
    print(f"\n总请求数: {stats.total.num_requests}")
    print(f"总失败数: {stats.total.num_failures}")
    print(f"失败率: {stats.total.fail_ratio * 100:.2f}%")
    print(f"平均响应时间: {stats.total.avg_response_time:.2f}ms")
    print(f"最大响应时间: {stats.total.max_response_time:.2f}ms")
    print(f"RPS: {stats.total.total_rps:.2f}")
