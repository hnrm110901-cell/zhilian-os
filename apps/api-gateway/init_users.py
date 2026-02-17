#!/usr/bin/env python3
"""
初始化测试用户
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.models.user import User, UserRole
from src.core.security import get_password_hash
from src.core.database import get_db_session
import uuid


async def init_test_users():
    """初始化测试用户"""
    print("开始初始化测试用户...")

    test_users = [
        {
            "username": "admin",
            "email": "admin@zhilian.com",
            "password": "admin123",
            "full_name": "系统管理员",
            "role": UserRole.ADMIN,
            "store_id": None,
        },
        {
            "username": "manager001",
            "email": "manager001@zhilian.com",
            "password": "manager123",
            "full_name": "张店长",
            "role": UserRole.STORE_MANAGER,
            "store_id": "STORE001",
        },
        {
            "username": "assistant001",
            "email": "assistant001@zhilian.com",
            "password": "assistant123",
            "full_name": "李助理",
            "role": UserRole.ASSISTANT_MANAGER,
            "store_id": "STORE001",
        },
        {
            "username": "floor001",
            "email": "floor001@zhilian.com",
            "password": "floor123",
            "full_name": "王楼面",
            "role": UserRole.FLOOR_MANAGER,
            "store_id": "STORE001",
        },
        {
            "username": "customer001",
            "email": "customer001@zhilian.com",
            "password": "customer123",
            "full_name": "赵客户经理",
            "role": UserRole.CUSTOMER_MANAGER,
            "store_id": "STORE001",
        },
        {
            "username": "leader001",
            "email": "leader001@zhilian.com",
            "password": "leader123",
            "full_name": "刘领班",
            "role": UserRole.TEAM_LEADER,
            "store_id": "STORE001",
        },
        {
            "username": "waiter001",
            "email": "waiter001@zhilian.com",
            "password": "waiter123",
            "full_name": "陈服务员",
            "role": UserRole.WAITER,
            "store_id": "STORE001",
        },
        {
            "username": "headchef001",
            "email": "headchef001@zhilian.com",
            "password": "chef123",
            "full_name": "杨厨师长",
            "role": UserRole.HEAD_CHEF,
            "store_id": "STORE001",
        },
        {
            "username": "station001",
            "email": "station001@zhilian.com",
            "password": "station123",
            "full_name": "周档口",
            "role": UserRole.STATION_MANAGER,
            "store_id": "STORE001",
        },
        {
            "username": "chef001",
            "email": "chef001@zhilian.com",
            "password": "chef123",
            "full_name": "吴厨师",
            "role": UserRole.CHEF,
            "store_id": "STORE001",
        },
        {
            "username": "warehouse001",
            "email": "warehouse001@zhilian.com",
            "password": "warehouse123",
            "full_name": "郑库管",
            "role": UserRole.WAREHOUSE_MANAGER,
            "store_id": "STORE001",
        },
        {
            "username": "finance001",
            "email": "finance001@zhilian.com",
            "password": "finance123",
            "full_name": "孙财务",
            "role": UserRole.FINANCE,
            "store_id": "STORE001",
        },
        {
            "username": "procurement001",
            "email": "procurement001@zhilian.com",
            "password": "procurement123",
            "full_name": "马采购",
            "role": UserRole.PROCUREMENT,
            "store_id": "STORE001",
        },
    ]

    async with get_db_session() as session:
        for user_data in test_users:
            # Check if user already exists
            from sqlalchemy import select

            stmt = select(User).where(User.username == user_data["username"])
            result = await session.execute(stmt)
            existing_user = result.scalar_one_or_none()

            if existing_user:
                print(f"用户 {user_data['username']} 已存在,跳过")
                continue

            # Create new user
            user = User(
                id=uuid.uuid4(),
                username=user_data["username"],
                email=user_data["email"],
                hashed_password=get_password_hash(user_data["password"]),
                full_name=user_data["full_name"],
                role=user_data["role"],
                store_id=user_data["store_id"],
                is_active=True,
            )

            session.add(user)
            print(f"创建用户: {user_data['username']} ({user_data['full_name']}) - {user_data['role'].value}")

        await session.commit()

    print("\n测试用户初始化完成!")
    print("\n可用的测试账号:")
    print("=" * 60)
    for user_data in test_users:
        print(f"用户名: {user_data['username']:<20} 密码: {user_data['password']:<15} 角色: {user_data['full_name']}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(init_test_users())
