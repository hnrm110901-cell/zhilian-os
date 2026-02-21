"""
Locust性能测试脚本
用于测试API的性能和负载能力
"""
from locust import HttpUser, task, between, events
import random
import json
from datetime import datetime, timedelta


class APIUser(HttpUser):
    """API用户行为模拟"""
    
    # 用户等待时间（秒）
    wait_time = between(1, 3)
    
    def on_start(self):
        """用户启动时执行 - 登录获取token"""
        # 模拟登录
        response = self.client.post(
            "/api/v1/auth/login",
            json={
                "username": "testuser",
                "password": "password123"
            },
            catch_response=True
        )
        
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token", "")
            self.headers = {"Authorization": f"Bearer {self.token}"}
            response.success()
        else:
            response.failure(f"登录失败: {response.status_code}")
            self.headers = {}
    
    @task(3)
    def get_health(self):
        """健康检查 - 高频率"""
        self.client.get("/health")
    
    @task(2)
    def list_tasks(self):
        """获取任务列表"""
        self.client.get(
            "/api/v1/tasks",
            params={"status": "pending", "limit": 20},
            headers=self.headers
        )
    
    @task(1)
    def create_task(self):
        """创建任务"""
        task_data = {
            "title": f"性能测试任务 {random.randint(1000, 9999)}",
            "content": "这是一个性能测试创建的任务",
            "priority": random.choice(["low", "normal", "high", "urgent"]),
            "category": "性能测试"
        }
        
        self.client.post(
            "/api/v1/tasks",
            json=task_data,
            headers=self.headers
        )
    
    @task(1)
    def get_reconciliation_records(self):
        """获取对账记录"""
        self.client.get(
            "/api/v1/reconciliation/records",
            params={"limit": 20},
            headers=self.headers
        )
    
    @task(1)
    def get_metrics(self):
        """获取Prometheus指标"""
        self.client.get("/metrics")


class AdminUser(HttpUser):
    """管理员用户行为模拟"""
    
    wait_time = between(2, 5)
    
    def on_start(self):
        """管理员登录"""
        response = self.client.post(
            "/api/v1/auth/login",
            json={
                "username": "admin",
                "password": "admin123"
            },
            catch_response=True
        )
        
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token", "")
            self.headers = {"Authorization": f"Bearer {self.token}"}
            response.success()
        else:
            response.failure(f"管理员登录失败: {response.status_code}")
            self.headers = {}
    
    @task(2)
    def perform_reconciliation(self):
        """执行对账"""
        reconciliation_data = {
            "reconciliation_date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
            "threshold": 2.0
        }
        
        self.client.post(
            "/api/v1/reconciliation/perform",
            json=reconciliation_data,
            headers=self.headers
        )
    
    @task(1)
    def update_task_status(self):
        """更新任务状态"""
        # 这里需要先获取一个任务ID，简化处理
        task_id = "123e4567-e89b-12d3-a456-426614174000"
        
        self.client.put(
            f"/api/v1/tasks/{task_id}/status",
            json={"status": "in_progress"},
            headers=self.headers,
            catch_response=True
        )


# 性能测试事件监听
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """测试开始时执行"""
    print("=" * 50)
    print("性能测试开始")
    print(f"目标主机: {environment.host}")
    print("=" * 50)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """测试结束时执行"""
    print("=" * 50)
    print("性能测试结束")
    print(f"总请求数: {environment.stats.total.num_requests}")
    print(f"失败数: {environment.stats.total.num_failures}")
    print(f"平均响应时间: {environment.stats.total.avg_response_time:.2f}ms")
    print(f"RPS: {environment.stats.total.total_rps:.2f}")
    print("=" * 50)
