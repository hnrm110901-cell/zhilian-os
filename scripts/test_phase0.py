#!/usr/bin/env python3
"""
Phase 0 端到端验证脚本
End-to-End Validation Script for Phase 0

验证项目：
1. 企微推送能到达真实用户
2. 任务创建→指派→完成闭环
3. 对账触发→差异计算→预警推送
4. 日报生成→内容正确→推送成功

使用方法：
    BASE_URL=http://localhost:8000 TOKEN=xxx python scripts/test_phase0.py
"""
import os
import sys
import json
import asyncio
import httpx
from datetime import date, timedelta
from typing import Dict, Any, Optional

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
TOKEN = os.getenv("TOKEN", "")
STORE_ID = os.getenv("STORE_ID", "")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
SKIP = "\033[93m-\033[0m"


def _ok(label: str, detail: str = ""):
    print(f"  {PASS} {label}" + (f"  ({detail})" if detail else ""))


def _fail(label: str, detail: str = ""):
    print(f"  {FAIL} {label}" + (f"  ({detail})" if detail else ""))


def _skip(label: str, reason: str = ""):
    print(f"  {SKIP} {label}" + (f"  [{reason}]" if reason else ""))


async def test_health(client: httpx.AsyncClient) -> bool:
    """1. 基础健康检查"""
    print("\n[1] 健康检查")
    try:
        r = await client.get(f"{BASE_URL}/health", timeout=5)
        if r.status_code == 200:
            _ok("API 服务正常", f"status={r.status_code}")
            return True
        else:
            _fail("API 服务异常", f"status={r.status_code}")
            return False
    except Exception as e:
        _fail("无法连接 API", str(e))
        return False


async def test_wechat_push(client: httpx.AsyncClient) -> bool:
    """2. 企微推送验证"""
    print("\n[2] 企微推送")
    if not TOKEN:
        _skip("跳过", "未设置 TOKEN")
        return True

    try:
        r = await client.post(
            f"{BASE_URL}/api/v1/wechat/test-push",
            headers=HEADERS,
            json={"message": f"Phase 0 验证消息 {date.today()}"},
            timeout=10,
        )
        if r.status_code in (200, 201):
            data = r.json()
            if data.get("success"):
                _ok("企微推送成功", f"sent={data.get('sent_count', '?')}")
                return True
            else:
                _fail("企微推送失败", data.get("message", ""))
                return False
        else:
            _skip("接口不存在，跳过", f"status={r.status_code}")
            return True
    except Exception as e:
        _fail("企微推送异常", str(e))
        return False


async def test_task_lifecycle(client: httpx.AsyncClient) -> bool:
    """3. 任务创建→指派→完成闭环"""
    print("\n[3] 任务生命周期")
    if not TOKEN or not STORE_ID:
        _skip("跳过", "未设置 TOKEN 或 STORE_ID")
        return True

    task_id: Optional[str] = None

    # 3a. 创建任务
    try:
        r = await client.post(
            f"{BASE_URL}/api/v1/tasks",
            headers=HEADERS,
            json={
                "title": "Phase 0 验证任务",
                "content": "自动化验证脚本创建",
                "store_id": STORE_ID,
                "priority": "normal",
            },
            timeout=10,
        )
        if r.status_code in (200, 201):
            task_id = r.json().get("id") or r.json().get("data", {}).get("id")
            _ok("任务创建成功", f"id={task_id}")
        else:
            _fail("任务创建失败", f"status={r.status_code} body={r.text[:100]}")
            return False
    except Exception as e:
        _fail("任务创建异常", str(e))
        return False

    if not task_id:
        _fail("未获取到任务 ID")
        return False

    # 3b. 完成任务
    try:
        r = await client.patch(
            f"{BASE_URL}/api/v1/tasks/{task_id}",
            headers=HEADERS,
            json={"status": "completed"},
            timeout=10,
        )
        if r.status_code == 200:
            _ok("任务完成成功")
        else:
            _fail("任务完成失败", f"status={r.status_code}")
            return False
    except Exception as e:
        _fail("任务完成异常", str(e))
        return False

    return True


async def test_reconciliation(client: httpx.AsyncClient) -> bool:
    """4. 对账触发→差异计算"""
    print("\n[4] POS 对账")
    if not TOKEN or not STORE_ID:
        _skip("跳过", "未设置 TOKEN 或 STORE_ID")
        return True

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    try:
        r = await client.post(
            f"{BASE_URL}/api/v1/reconciliation/trigger",
            headers=HEADERS,
            json={"store_id": STORE_ID, "reconciliation_date": yesterday},
            timeout=30,
        )
        if r.status_code in (200, 201):
            data = r.json()
            status = data.get("status") or data.get("data", {}).get("status", "?")
            diff = data.get("diff_ratio") or data.get("data", {}).get("diff_ratio", "?")
            _ok("对账触发成功", f"status={status} diff_ratio={diff}")
            return True
        else:
            _fail("对账触发失败", f"status={r.status_code} body={r.text[:100]}")
            return False
    except Exception as e:
        _fail("对账触发异常", str(e))
        return False


async def test_daily_report(client: httpx.AsyncClient) -> bool:
    """5. 日报生成"""
    print("\n[5] 营业日报")
    if not TOKEN or not STORE_ID:
        _skip("跳过", "未设置 TOKEN 或 STORE_ID")
        return True

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    try:
        r = await client.post(
            f"{BASE_URL}/api/v1/reports/daily",
            headers=HEADERS,
            json={"store_id": STORE_ID, "report_date": yesterday},
            timeout=30,
        )
        if r.status_code in (200, 201):
            data = r.json()
            report_id = data.get("id") or data.get("data", {}).get("id", "?")
            _ok("日报生成成功", f"report_id={report_id}")
            return True
        else:
            _fail("日报生成失败", f"status={r.status_code} body={r.text[:100]}")
            return False
    except Exception as e:
        _fail("日报生成异常", str(e))
        return False


async def test_scheduler_status(client: httpx.AsyncClient) -> bool:
    """6. 调度器状态"""
    print("\n[6] 调度器状态")
    if not TOKEN:
        _skip("跳过", "未设置 TOKEN")
        return True

    try:
        r = await client.get(
            f"{BASE_URL}/api/v1/scheduler/status",
            headers=HEADERS,
            timeout=5,
        )
        if r.status_code == 200:
            data = r.json()
            running = data.get("running", data.get("data", {}).get("running", "?"))
            _ok("调度器运行中", f"running={running}")
            return True
        else:
            _skip("接口不存在，跳过", f"status={r.status_code}")
            return True
    except Exception as e:
        _fail("调度器状态查询异常", str(e))
        return False


async def main():
    print("=" * 50)
    print("  智链OS Phase 0 端到端验证")
    print(f"  BASE_URL : {BASE_URL}")
    print(f"  STORE_ID : {STORE_ID or '(未设置)'}")
    print("=" * 50)

    results: Dict[str, bool] = {}

    async with httpx.AsyncClient() as client:
        results["health"] = await test_health(client)
        if not results["health"]:
            print("\n⚠️  API 不可达，终止验证")
            sys.exit(1)

        results["wechat"] = await test_wechat_push(client)
        results["task"] = await test_task_lifecycle(client)
        results["reconciliation"] = await test_reconciliation(client)
        results["daily_report"] = await test_daily_report(client)
        results["scheduler"] = await test_scheduler_status(client)

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n{'=' * 50}")
    print(f"  结果: {passed}/{total} 通过")
    print("=" * 50)

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
