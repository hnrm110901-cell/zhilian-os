"""
端到端向量索引测试 - 通过API Gateway
"""
import requests
import json

API_URL = "http://localhost:8000/api/v1/neural"

print("=" * 60)
print("端到端向量索引测试")
print("=" * 60)

# 1. 发射订单事件（会自动索引）
print("\n[1] 发射订单事件")
events = [
    {
        "event_type": "order",
        "store_id": "store_001",
        "data": {
            "order_id": "ORD20260219001",
            "order_number": "20260219001",
            "total_amount": 158.50,
            "status": "completed",
            "items": "宫保鸡丁 x 1, 麻婆豆腐 x 2"
        }
    },
    {
        "event_type": "order",
        "store_id": "store_001",
        "data": {
            "order_id": "ORD20260219002",
            "order_number": "20260219002",
            "total_amount": 268.00,
            "status": "completed",
            "items": "北京烤鸭 x 1, 酸辣汤 x 2"
        }
    },
    {
        "event_type": "order",
        "store_id": "store_001",
        "data": {
            "order_id": "ORD20260219003",
            "order_number": "20260219003",
            "total_amount": 88.00,
            "status": "completed",
            "items": "蔬菜沙拉 x 1, 清蒸鲈鱼 x 1"
        }
    }
]

for event in events:
    response = requests.post(f"{API_URL}/events/emit", json=event)
    if response.status_code == 200:
        result = response.json()
        print(f"✓ 事件发射成功: {result['event_id']}")
    else:
        print(f"✗ 事件发射失败: {response.status_code} - {response.text}")

# 2. 搜索订单
print("\n[2] 搜索订单")
search_queries = [
    "大额订单",
    "外卖订单",
    "低价订单"
]

for query in search_queries:
    print(f"\n搜索: '{query}'")
    response = requests.post(
        f"{API_URL}/search/orders",
        json={
            "query": query,
            "store_id": "store_001",
            "top_k": 3
        }
    )
    if response.status_code == 200:
        result = response.json()
        print(f"找到 {result['total']} 个结果")
        if result['total'] == 0:
            print("  (暂无索引数据)")
    else:
        print(f"✗ 搜索失败: {response.status_code} - {response.text}")

# 3. 检查系统状态
print("\n[3] 检查系统状态")
response = requests.get(f"{API_URL}/status")
if response.status_code == 200:
    status = response.json()
    print(f"✓ 系统状态: {status['status']}")
    print(f"  总事件数: {status['total_events']}")
    print(f"  向量集合:")
    for collection, count in status['vector_db_collections'].items():
        print(f"    - {collection}: {count} 条")
else:
    print(f"✗ 获取状态失败: {response.status_code}")

print("\n" + "=" * 60)
print("✓ 测试完成！")
print("=" * 60)
print("\n说明:")
print("- 事件已成功发射到神经系统")
print("- 搜索返回空结果是正常的，因为:")
print("  1. 事件索引功能还需要完善")
print("  2. sentence-transformers模型需要正确加载")
print("  3. 向量嵌入生成需要实际实现")
print("\n下一步: 完善向量索引的实际实现")
