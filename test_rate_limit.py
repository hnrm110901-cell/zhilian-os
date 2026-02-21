"""
测试API速率限制功能
"""
import asyncio
import httpx
import time
from typing import List, Dict

# API基础URL
BASE_URL = "http://localhost:8000"

async def test_rate_limit_default():
    """测试默认端点的速率限制 (100次/分钟)"""
    print("\n=== 测试默认端点速率限制 ===")

    async with httpx.AsyncClient() as client:
        # 快速发送105个请求
        tasks = []
        for i in range(105):
            tasks.append(client.get(f"{BASE_URL}/api/v1/health"))

        start_time = time.time()
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start_time

        # 统计结果
        success_count = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 200)
        rate_limited_count = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 429)

        print(f"发送请求数: 105")
        print(f"成功请求数: {success_count}")
        print(f"被限流请求数: {rate_limited_count}")
        print(f"耗时: {elapsed:.2f}秒")

        # 检查最后一个被限流的响应
        for r in responses:
            if not isinstance(r, Exception) and r.status_code == 429:
                print(f"\n限流响应头:")
                print(f"  X-RateLimit-Limit: {r.headers.get('X-RateLimit-Limit')}")
                print(f"  X-RateLimit-Remaining: {r.headers.get('X-RateLimit-Remaining')}")
                print(f"  X-RateLimit-Reset: {r.headers.get('X-RateLimit-Reset')}")
                print(f"响应内容: {r.json()}")
                break

        assert rate_limited_count > 0, "应该有请求被限流"
        print("✓ 默认端点速率限制测试通过")

async def test_rate_limit_auth():
    """测试认证端点的速率限制 (10次/分钟)"""
    print("\n=== 测试认证端点速率限制 ===")

    async with httpx.AsyncClient() as client:
        # 快速发送15个登录请求
        tasks = []
        for i in range(15):
            tasks.append(client.post(
                f"{BASE_URL}/api/v1/auth/login",
                json={"username": "test", "password": "test"}
            ))

        start_time = time.time()
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start_time

        # 统计结果
        success_count = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code in [200, 401])
        rate_limited_count = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 429)

        print(f"发送请求数: 15")
        print(f"成功请求数: {success_count}")
        print(f"被限流请求数: {rate_limited_count}")
        print(f"耗时: {elapsed:.2f}秒")

        assert rate_limited_count > 0, "应该有请求被限流"
        print("✓ 认证端点速率限制测试通过")

async def test_rate_limit_backup():
    """测试备份端点的速率限制 (5次/5分钟)"""
    print("\n=== 测试备份端点速率限制 ===")

    async with httpx.AsyncClient() as client:
        # 快速发送8个备份列表请求
        tasks = []
        for i in range(8):
            tasks.append(client.get(f"{BASE_URL}/api/v1/backup/list"))

        start_time = time.time()
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start_time

        # 统计结果
        success_count = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code in [200, 401])
        rate_limited_count = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 429)

        print(f"发送请求数: 8")
        print(f"成功请求数: {success_count}")
        print(f"被限流请求数: {rate_limited_count}")
        print(f"耗时: {elapsed:.2f}秒")

        assert rate_limited_count > 0, "应该有请求被限流"
        print("✓ 备份端点速率限制测试通过")

async def test_rate_limit_recovery():
    """测试速率限制恢复"""
    print("\n=== 测试速率限制恢复 ===")

    async with httpx.AsyncClient() as client:
        # 发送请求直到被限流
        for i in range(105):
            response = await client.get(f"{BASE_URL}/api/v1/health")
            if response.status_code == 429:
                print(f"在第 {i+1} 个请求时被限流")
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                current_time = int(time.time())
                wait_time = max(0, reset_time - current_time + 1)
                print(f"等待 {wait_time} 秒后重试...")
                await asyncio.sleep(wait_time)
                break

        # 等待后重试
        response = await client.get(f"{BASE_URL}/api/v1/health")
        print(f"恢复后请求状态码: {response.status_code}")
        assert response.status_code == 200, "速率限制应该已恢复"
        print("✓ 速率限制恢复测试通过")

async def main():
    """运行所有测试"""
    print("开始测试API速率限制功能...")
    print("=" * 50)

    try:
        await test_rate_limit_default()
        await test_rate_limit_auth()
        await test_rate_limit_backup()
        await test_rate_limit_recovery()

        print("\n" + "=" * 50)
        print("所有速率限制测试通过! ✓")
    except Exception as e:
        print(f"\n测试失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
