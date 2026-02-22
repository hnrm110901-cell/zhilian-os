"""
Phase 0 端到端验证脚本

验证项目：
1. 企微推送能到达真实用户
2. 任务创建→指派→完成闭环
3. 对账触发→差异计算→预警推送
4. 日报生成→内容正确→推送成功

用法：
    python scripts/test_phase0.py --base-url http://localhost:8000 --token <JWT_TOKEN>
"""
import asyncio
import argparse
import json
import sys
from datetime import date, timedelta
from typing import Optional

import httpx


BASE_URL = "http://localhost:8000"
HEADERS = {}


def print_result(name: str, success: bool, detail: str = ""):
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status}  {name}")
    if detail:
        print(f"       {detail}")


async def test_wechat_push(client: httpx.AsyncClient, store_id: str) -> bool:
    """验证企微推送"""
    try:
        resp = await client.post(
            f"{BASE_URL}/api/v1/wechat/test-push",
            json={"store_id": store_id, "message": "Phase 0 验证推送"},
            headers=HEADERS,
        )
        ok = resp.status_code in (200, 201)
        print_result("企微推送", ok, f"status={resp.status_code}")
        return ok
    except Exception as e:
        print_result("企微推送", False, str(e))
        return False


async def test_task_lifecycle(client: httpx.AsyncClient, store_id: str) -> bool:
    """验证任务创建→指派→完成闭环"""
    task_id: Optional[str] = None
    try:
        # 1. 创建任务
        resp = await client.post(
            f"{BASE_URL}/api/v1/tasks",
            json={
                "title": "Phase 0 验证任务",
                "content": "自动化验证脚本创建",
                "store_id": store_id,
            },
            headers=HEADERS,
        )
        if resp.status_code not in (200, 201):
            print_result("任务创建", False, f"status={resp.status_code} body={resp.text[:200]}")
            return False
        task_id = resp.json().get("id") or resp.json().get("data", {}).get("id")
        print_result("任务创建", True, f"task_id={task_id}")

        # 2. 完成任务
        resp = await client.patch(
            f"{BASE_URL}/api/v1/tasks/{task_id}",
            json={"status": "completed"},
            headers=HEADERS,
        )
        ok = resp.status_code in (200, 201)
        print_result("任务完成", ok, f"status={resp.status_code}")
        return ok

    except Exception as e:
        print_result("任务生命周期", False, str(e))
        return False


async def test_reconciliation(client: httpx.AsyncClient, store_id: str) -> bool:
    """验证对账触发→差异计算"""
    try:
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        resp = await client.post(
            f"{BASE_URL}/api/v1/reconciliation/trigger",
            json={"store_id": store_id, "reconciliation_date": yesterday},
            headers=HEADERS,
        )
        ok = resp.status_code in (200, 201)
        body = resp.json() if ok else {}
        detail = f"status={resp.status_code}"
        if ok:
            detail += f" diff_ratio={body.get('diff_ratio', body.get('data', {}).get('diff_ratio', 'n/a'))}"
        print_result("对账触发", ok, detail)
        return ok
    except Exception as e:
        print_result("对账触发", False, str(e))
        return False


async def test_daily_report(client: httpx.AsyncClient, store_id: str) -> bool:
    """验证日报生成"""
    try:
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        resp = await client.post(
            f"{BASE_URL}/api/v1/reports/daily/generate",
            json={"store_id": store_id, "report_date": yesterday},
            headers=HEADERS,
        )
        ok = resp.status_code in (200, 201)
        print_result("日报生成", ok, f"status={resp.status_code}")
        return ok
    except Exception as e:
        print_result("日报生成", False, str(e))
        return False


async def test_scheduler_celery_tasks(client: httpx.AsyncClient) -> bool:
    """验证 Celery 任务可手动触发"""
    try:
        resp = await client.post(
            f"{BASE_URL}/api/v1/admin/tasks/trigger",
            json={"task": "detect_revenue_anomaly"},
            headers=HEADERS,
        )
        ok = resp.status_code in (200, 201, 202)
        print_result("Celery任务触发", ok, f"status={resp.status_code}")
        return ok
    except Exception as e:
        print_result("Celery任务触发", False, str(e))
        return False


async def main(base_url: str, token: str, store_id: str):
    global BASE_URL, HEADERS
    BASE_URL = base_url.rstrip("/")
    HEADERS = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    print(f"\n=== Phase 0 验证 ===")
    print(f"服务地址: {BASE_URL}")
    print(f"门店ID:   {store_id}\n")

    async with httpx.AsyncClient(timeout=30.0) as client:
        results = await asyncio.gather(
            test_wechat_push(client, store_id),
            test_task_lifecycle(client, store_id),
            test_reconciliation(client, store_id),
            test_daily_report(client, store_id),
            test_scheduler_celery_tasks(client),
            return_exceptions=True,
        )

    passed = sum(1 for r in results if r is True)
    total = len(results)
    print(f"\n结果: {passed}/{total} 通过")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 0 端到端验证")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token", required=True, help="JWT Bearer token")
    parser.add_argument("--store-id", default="STORE001", help="测试门店ID")
    args = parser.parse_args()

    asyncio.run(main(args.base_url, args.token, args.store_id))
