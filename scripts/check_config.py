#!/usr/bin/env python3
"""
配置检查脚本
Configuration Check Script

检查智链OS所有外部系统的配置状态
"""
import os
import sys
from typing import Dict, List
from datetime import datetime


def check_config() -> Dict[str, bool]:
    """检查所有配置项"""
    results = {}

    # 必需配置
    required = [
        "DATABASE_URL",
        "REDIS_URL",
        "SECRET_KEY",
        "JWT_SECRET",
    ]

    # 可选配置
    optional = {
        "企业微信": ["WECHAT_CORP_ID", "WECHAT_CORP_SECRET", "WECHAT_AGENT_ID"],
        "飞书": ["FEISHU_APP_ID", "FEISHU_APP_SECRET"],
        "奥琦韦": ["AOQIWEI_API_KEY", "AOQIWEI_BASE_URL"],
        "品智": ["PINZHI_TOKEN", "PINZHI_BASE_URL"],
    }

    print("=" * 60)
    print("智链OS 配置检查")
    print("=" * 60)
    print(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 检查必需配置
    print("【必需配置】")
    print("-" * 60)
    all_required_ok = True
    for key in required:
        value = os.getenv(key)
        status = "✅" if value else "❌"
        results[key] = bool(value)
        all_required_ok = all_required_ok and bool(value)

        # 显示部分值（隐藏敏感信息）
        if value:
            if len(value) > 20:
                display_value = f"{value[:10]}...{value[-5:]}"
            else:
                display_value = f"{value[:5]}..."
            print(f"  {status} {key:20s} = {display_value}")
        else:
            print(f"  {status} {key:20s} = 未设置")

    if all_required_ok:
        print("\n  ✅ 所有必需配置已完成")
    else:
        print("\n  ❌ 必需配置不完整，请检查缺失项")

    print()

    # 检查可选配置
    print("【可选配置】")
    print("-" * 60)

    configured_systems = 0
    total_systems = len(optional)

    for system, keys in optional.items():
        print(f"\n{system}:")
        all_configured = True
        for key in keys:
            value = os.getenv(key)
            status = "✅" if value else "⚠️ "
            results[key] = bool(value)
            all_configured = all_configured and bool(value)

            # 显示部分值（隐藏敏感信息）
            if value:
                if len(value) > 20:
                    display_value = f"{value[:10]}...{value[-5:]}"
                else:
                    display_value = f"{value[:5]}..."
                print(f"  {status} {key:25s} = {display_value}")
            else:
                print(f"  {status} {key:25s} = 未设置")

        if all_configured:
            print(f"  ✅ {system}已完整配置")
            configured_systems += 1
        else:
            print(f"  ⚠️  {system}配置不完整（可选）")

    print()
    print("=" * 60)
    print("【配置汇总】")
    print("-" * 60)
    print(f"必需配置: {'✅ 完成' if all_required_ok else '❌ 不完整'}")
    print(f"可选系统: {configured_systems}/{total_systems} 已配置")
    print()

    if all_required_ok and configured_systems == total_systems:
        print("✅ 所有配置已完成，系统可以正常运行")
        return_code = 0
    elif all_required_ok:
        print("⚠️  必需配置已完成，但部分可选系统未配置")
        print("   系统可以运行，但某些功能可能不可用")
        return_code = 0
    else:
        print("❌ 必需配置不完整，系统无法正常运行")
        print("   请设置所有必需的环境变量")
        return_code = 1

    print("=" * 60)

    return results, return_code


def print_help():
    """打印帮助信息"""
    print("""
智链OS 配置检查脚本

用法:
    python scripts/check_config.py

说明:
    检查所有必需和可选的环境变量配置状态

    必需配置:
        - DATABASE_URL: PostgreSQL数据库连接URL
        - REDIS_URL: Redis连接URL
        - SECRET_KEY: 应用密钥
        - JWT_SECRET: JWT令牌密钥

    可选配置:
        - 企业微信: WECHAT_CORP_ID, WECHAT_CORP_SECRET, WECHAT_AGENT_ID
        - 飞书: FEISHU_APP_ID, FEISHU_APP_SECRET
        - 奥琦韦: AOQIWEI_API_KEY, AOQIWEI_BASE_URL
        - 品智: PINZHI_TOKEN, PINZHI_BASE_URL

退出码:
    0 - 必需配置完成
    1 - 必需配置不完整

示例:
    # 检查配置
    python scripts/check_config.py

    # 在Docker中检查
    docker exec zhilian-api python scripts/check_config.py
""")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help", "help"]:
        print_help()
        sys.exit(0)

    try:
        results, return_code = check_config()
        sys.exit(return_code)
    except Exception as e:
        print(f"\n❌ 配置检查失败: {str(e)}")
        sys.exit(1)
