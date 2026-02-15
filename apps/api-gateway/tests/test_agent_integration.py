"""
测试Agent服务集成
"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from services.agent_service import AgentService


async def test_schedule_agent():
    """测试排班Agent"""
    print("\\n=== 测试排班Agent ===")

    service = AgentService()

    # 测试数据
    input_data = {
        "action": "run",
        "store_id": "store_001",
        "date": "2024-02-20",
        "employees": [
            {
                "id": "emp_001",
                "name": "张三",
                "skills": ["waiter", "cashier"],
            },
            {
                "id": "emp_002",
                "name": "李四",
                "skills": ["chef"],
            },
            {
                "id": "emp_003",
                "name": "王五",
                "skills": ["waiter"],
            },
        ],
    }

    result = await service.execute_agent("schedule", input_data)
    print(f"执行结果: {result}")
    print(f"执行时间: {result.get('execution_time', 0):.3f}秒")

    if result.get("success"):
        print(f"排班数量: {len(result.get('schedule', []))}")
        print(f"优化建议: {result.get('suggestions', [])}")
    else:
        print(f"执行失败: {result.get('error')}")


async def main():
    """主函数"""
    print("开始测试Agent服务集成...")

    try:
        await test_schedule_agent()
        print("\\n✓ 测试完成")
    except Exception as e:
        print(f"\\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
