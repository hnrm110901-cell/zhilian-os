"""
简化的向量索引测试 - 使用REST API
"""
import requests
import json
from datetime import datetime

QDRANT_URL = "http://localhost:6333"

# 模拟嵌入向量（384维）
def generate_mock_embedding(text):
    """生成模拟的嵌入向量"""
    import hashlib
    import random
    random.seed(hashlib.md5(text.encode()).hexdigest())
    return [random.random() for _ in range(384)]

# 测试数据
test_order = {
    "id": "ord001",
    "vector": generate_mock_embedding("订单号 20260219001, 类型 dine_in, 状态 completed, 菜品: 宫保鸡丁 x 1, 麻婆豆腐 x 2, 米饭 x 2, 总金额 158.5元"),
    "payload": {
        "order_id": "ORD001",
        "order_number": "20260219001",
        "order_type": "dine_in",
        "total": 158.50,
        "store_id": "store_001",
        "text": "订单号 20260219001, 类型 dine_in, 状态 completed, 菜品: 宫保鸡丁 x 1, 麻婆豆腐 x 2, 米饭 x 2, 总金额 158.5元"
    }
}

test_dish = {
    "id": "dish001",
    "vector": generate_mock_embedding("菜品 宫保鸡丁, 分类 川菜, 价格 48.0元, 描述: 经典川菜，鸡肉配花生米，香辣可口, 标签: 川菜, 辣, 鸡肉"),
    "payload": {
        "dish_id": "DISH001",
        "name": "宫保鸡丁",
        "category": "川菜",
        "price": 48.00,
        "store_id": "store_001",
        "text": "菜品 宫保鸡丁, 分类 川菜, 价格 48.0元, 描述: 经典川菜，鸡肉配花生米，香辣可口, 标签: 川菜, 辣, 鸡肉"
    }
}

print("=" * 60)
print("开始测试向量索引（REST API）")
print("=" * 60)

# 1. 索引订单
print("\n[1] 索引订单")
response = requests.put(
    f"{QDRANT_URL}/collections/orders/points",
    json={"points": [test_order]}
)
if response.status_code == 200:
    print(f"✓ 订单索引成功: {test_order['payload']['order_id']}")
else:
    print(f"✗ 订单索引失败: {response.status_code} - {response.text}")

# 2. 索引菜品
print("\n[2] 索引菜品")
response = requests.put(
    f"{QDRANT_URL}/collections/dishes/points",
    json={"points": [test_dish]}
)
if response.status_code == 200:
    print(f"✓ 菜品索引成功: {test_dish['payload']['dish_id']}")
else:
    print(f"✗ 菜品索引失败: {response.status_code} - {response.text}")

# 3. 搜索订单
print("\n[3] 搜索订单")
query_vector = generate_mock_embedding("大额订单")
response = requests.post(
    f"{QDRANT_URL}/collections/orders/points/search",
    json={
        "vector": query_vector,
        "limit": 3,
        "with_payload": True
    }
)
if response.status_code == 200:
    results = response.json()["result"]
    print(f"找到 {len(results)} 个结果:")
    for i, result in enumerate(results, 1):
        print(f"  {i}. 订单号: {result['payload']['order_number']}, "
              f"金额: {result['payload']['total']}元, "
              f"相似度: {result['score']:.3f}")
else:
    print(f"✗ 搜索失败: {response.status_code} - {response.text}")

# 4. 搜索菜品
print("\n[4] 搜索菜品")
query_vector = generate_mock_embedding("辣的川菜")
response = requests.post(
    f"{QDRANT_URL}/collections/dishes/points/search",
    json={
        "vector": query_vector,
        "limit": 3,
        "with_payload": True
    }
)
if response.status_code == 200:
    results = response.json()["result"]
    print(f"找到 {len(results)} 个结果:")
    for i, result in enumerate(results, 1):
        print(f"  {i}. 菜品: {result['payload']['name']}, "
              f"分类: {result['payload']['category']}, "
              f"相似度: {result['score']:.3f}")
else:
    print(f"✗ 搜索失败: {response.status_code} - {response.text}")

print("\n" + "=" * 60)
print("✓ 测试完成！")
print("=" * 60)
