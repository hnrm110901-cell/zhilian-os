"""
任务管理完整流程集成测试
"""
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_complete_task_workflow():
    """测试完整的任务工作流"""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        # 1. 登录
        login_response = await client.post("/api/v1/auth/login", json={
            "username": "testuser",
            "password": "password123"
        })
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. 创建任务
        task_response = await client.post("/api/v1/tasks", json={
            "title": "集成测试任务",
            "content": "测试内容",
            "priority": "high"
        }, headers=headers)
        assert task_response.status_code == 200
        task_id = task_response.json()["data"]["id"]
        
        # 3. 更新任务状态
        status_response = await client.put(
            f"/api/v1/tasks/{task_id}/status",
            json={"status": "in_progress"},
            headers=headers
        )
        assert status_response.status_code == 200
        
        # 4. 完成任务
        complete_response = await client.post(
            f"/api/v1/tasks/{task_id}/complete",
            json={"result": "任务完成"},
            headers=headers
        )
        assert complete_response.status_code == 200
