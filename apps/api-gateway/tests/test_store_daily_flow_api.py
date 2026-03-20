"""门店全天流程 API 端到端测试（独立进程，不依赖全局 conftest）"""
import subprocess
import sys

def test_all():
    """通过子进程运行测试，避免 conftest 模型注册冲突"""
    result = subprocess.run(
        [sys.executable, "-c", TEST_CODE],
        capture_output=True, text=True,
        cwd="/Users/lichun/tunxiang/apps/api-gateway",
        env={
            **__import__("os").environ,
            "DATABASE_URL": "postgresql+asyncpg://x:x@localhost/x",
            "REDIS_URL": "redis://localhost:6379/0",
            "CELERY_BROKER_URL": "redis://localhost:6379/1",
            "CELERY_RESULT_BACKEND": "redis://localhost:6379/2",
            "JWT_SECRET_KEY": "test-secret",
        },
        timeout=30,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
    assert "ALL" in result.stdout and "PASSED" in result.stdout, f"Tests failed: {result.stderr[-500:]}"


TEST_CODE = '''
import asyncio, sys, os
# Prevent global model registration conflicts
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
app = FastAPI()
from src.api.store_daily_flow import router
app.include_router(router)

async def test():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        p = 0
        r = await c.get("/api/v1/daily-flow/config/standard-nodes")
        assert r.status_code==200 and r.json()["total"]==11; p+=1
        r = await c.get("/api/v1/daily-flow/config/standard-tasks/opening_prep")
        assert r.status_code==200 and r.json()["total"]==5; p+=1
        r = await c.get("/api/v1/daily-flow/config/standard-tasks")
        assert r.status_code==200; p+=1
        r = await c.post("/api/v1/daily-flow/mobile/init-flow", json={"store_id":"S1","brand_id":"B1","biz_date":"2026-03-20","business_mode":"lunch_dinner"})
        assert r.status_code==200; fd=r.json(); assert fd["progress"]["total_nodes"]==9; p+=1
        r = await c.get("/api/v1/daily-flow/mobile/workspace/S1?biz_date=2026-03-20")
        assert r.status_code==200; p+=1
        n0=fd["nodes"][0]; r = await c.get(f"/api/v1/daily-flow/mobile/node/{n0['id']}")
        assert r.status_code==200; nd=r.json(); p+=1
        t0=nd["tasks"][0]; r = await c.post("/api/v1/daily-flow/mobile/task/submit", json={"task_instance_id":t0["id"],"submitted_by":"u1"})
        assert r.status_code==200 and r.json()["task"]["status"]=="done"; p+=1
        r = await c.post("/api/v1/daily-flow/mobile/incident/create", json={"store_id":"S1","brand_id":"B1","biz_date":"2026-03-20","incident_type":"equip","severity":"medium","title":"蒸柜坏了","reporter_id":"u1"})
        assert r.status_code==200; inc=r.json()["incident"]; p+=1
        r = await c.get("/api/v1/daily-flow/manager/dashboard/S1?biz_date=2026-03-20")
        assert r.status_code==200; p+=1
        r = await c.post(f"/api/v1/daily-flow/manager/incident/{inc['id']}/update", json={"action":"accept","assignee_id":"repair"})
        assert r.status_code==200 and r.json()["incident"]["status"]=="accepted"; p+=1
        pn=[n for n in fd["nodes"] if n["status"]=="pending"]
        if pn:
            r=await c.post(f"/api/v1/daily-flow/manager/node/{pn[-1]['id']}/skip?reason=test")
            assert r.status_code==200; p+=1
        r = await c.get("/api/v1/daily-flow/hq/inspection?biz_date=2026-03-20")
        assert r.status_code==200 and r.json()["total_stores"]>=1; p+=1
        r = await c.get("/api/v1/daily-flow/hq/store/S1/detail?biz_date=2026-03-20")
        assert r.status_code==200; p+=1
        r = await c.post("/api/v1/daily-flow/mobile/incident/create", json={"store_id":"S1","brand_id":"B1","biz_date":"2026-03-20","incident_type":"food_safety","severity":"critical","title":"食材变质","reporter_id":"u2"})
        assert r.status_code==200 and r.json()["incident"]["status"]=="escalated"; p+=1
        print(f"ALL {p} TESTS PASSED")

asyncio.run(test())
'''

if __name__ == "__main__":
    test_all()
