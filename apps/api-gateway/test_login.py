#!/usr/bin/env python3
"""
智链OS - 简单登录测试脚本
"""
import requests
import json

# API地址
API_URL = "http://localhost:8000"

# 超级管理员账号
USERNAME = "admin"
PASSWORD = "admin123"

print("=" * 60)
print("智链OS - 超级管理员登录测试")
print("=" * 60)
print()

# 发送登录请求
print(f"正在登录... 用户名: {USERNAME}")
try:
    response = requests.post(
        f"{API_URL}/api/v1/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
        headers={"Content-Type": "application/json"}
    )

    if response.status_code == 200:
        data = response.json()
        print()
        print("✅ 登录成功!")
        print("=" * 60)
        print(f"用户名: {data['user']['username']}")
        print(f"姓名: {data['user']['full_name']}")
        print(f"角色: {data['user']['role']}")
        print(f"邮箱: {data['user']['email']}")
        print()
        print("访问令牌 (Access Token):")
        print(data['access_token'])
        print()
        print("刷新令牌 (Refresh Token):")
        print(data['refresh_token'])
        print("=" * 60)
        print()
        print("🎉 登录成功！你现在可以使用这个token访问所有API")
        print()
        print("使用方法:")
        print("1. 复制上面的 Access Token")
        print("2. 在API请求的Header中添加:")
        print(f"   Authorization: Bearer <你的token>")
        print()

        # 保存token到文件
        with open("/tmp/zhilian_token.txt", "w") as f:
            f.write(data['access_token'])
        print("✅ Token已保存到: /tmp/zhilian_token.txt")

    else:
        print(f"❌ 登录失败! 状态码: {response.status_code}")
        print(f"错误信息: {response.text}")

except Exception as e:
    print(f"❌ 连接失败: {str(e)}")
    print()
    print("请确保:")
    print("1. API服务正在运行 (http://localhost:8000)")
    print("2. 数据库已初始化")
    print("3. 用户已创建 (运行 python3 init_users.py)")

print()
