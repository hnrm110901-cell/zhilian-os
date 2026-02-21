"""
测试脚本 - 验证Agent服务功能
"""
import asyncio
import sys
import os

# 设置环境变量
os.environ['DATABASE_URL'] = 'postgresql://test:test@localhost/test'
os.environ['REDIS_URL'] = 'redis://localhost:6379/0'
os.environ['OPENAI_API_KEY'] = 'test-key'
os.environ['CELERY_BROKER_URL'] = 'redis://localhost:6379/1'
os.environ['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/2'
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['JWT_SECRET'] = 'test-jwt-secret'

sys.path.insert(0, '.')

from src.services.agent_service import AgentService


async def test_schedule_agent():
    """测试排班Agent"""
    print("\n=== 测试排班Agent ===")

    service = AgentService()

    input_data = {
        "action": "run",
        "store_id": "store_001",
        "date": "2024-02-20",
        "employees": [
            {"id": "emp_001", "name": "张三", "skills": ["waiter", "cashier"]},
            {"id": "emp_002", "name": "李四", "skills": ["chef"]},
            {"id": "emp_003", "name": "王五", "skills": ["waiter"]},
        ],
    }

    try:
        result = await service.execute_agent("schedule", input_data)

        if result.get("success"):
            print(f"✓ 排班Agent执行成功")
            print(f"✓ 执行时间: {result.get('execution_time', 0):.3f}秒")
            print(f"✓ 生成排班数: {len(result.get('schedule', []))}条")
            print(f"✓ 优化建议数: {len(result.get('suggestions', []))}条")
            return True
        else:
            print(f"✗ 排班Agent执行失败: {result.get('error')}")
            return False
    except Exception as e:
        print(f"✗ 排班Agent执行异常: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_reservation_agent():
    """测试预定Agent"""
    print("\n=== 测试预定Agent ===")

    service = AgentService()

    # Use a future date
    from datetime import datetime, timedelta
    future_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    input_data = {
        "action": "create",
        "reservation_data": {
            "customer_name": "测试客户",
            "customer_phone": "13800138000",
            "party_size": 4,
            "reservation_date": future_date,
            "reservation_time": "18:00",
        },
    }

    try:
        result = await service.execute_agent("reservation", input_data)

        if result.get("success"):
            print(f"✓ 预定Agent执行成功")
            print(f"✓ 执行时间: {result.get('execution_time', 0):.3f}秒")
            print(f"✓ 预定ID: {result.get('reservation_id', 'N/A')}")
            return True
        else:
            print(f"✗ 预定Agent执行失败: {result.get('error')}")
            return False
    except Exception as e:
        print(f"✗ 预定Agent执行异常: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    print("开始测试Agent服务...")

    results = []

    # 测试排班Agent
    results.append(await test_schedule_agent())

    # 测试预定Agent
    results.append(await test_reservation_agent())

    # 总结
    print("\n=== 测试总结 ===")
    passed = sum(results)
    total = len(results)
    print(f"通过: {passed}/{total}")

    if passed == total:
        print("✓ 所有测试通过")
        return 0
    else:
        print("✗ 部分测试失败")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
