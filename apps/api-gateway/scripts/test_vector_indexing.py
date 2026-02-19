"""
向量索引测试脚本
测试实际的向量索引和语义搜索功能
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.vector_db_service import VectorDatabaseService
import structlog

logger = structlog.get_logger()


# 测试数据
TEST_ORDERS = [
    {
        "order_id": "ORD001",
        "order_number": "20260219001",
        "order_type": "dine_in",
        "order_status": "completed",
        "total": 158.50,
        "created_at": datetime.now(),
        "store_id": "store_001",
        "items": [
            {"dish_name": "宫保鸡丁", "quantity": 1, "price": 48.00},
            {"dish_name": "麻婆豆腐", "quantity": 2, "price": 38.00},
            {"dish_name": "米饭", "quantity": 2, "price": 5.00}
        ]
    },
    {
        "order_id": "ORD002",
        "order_number": "20260219002",
        "order_type": "takeout",
        "order_status": "completed",
        "total": 268.00,
        "created_at": datetime.now(),
        "store_id": "store_001",
        "items": [
            {"dish_name": "北京烤鸭", "quantity": 1, "price": 198.00},
            {"dish_name": "酸辣汤", "quantity": 2, "price": 35.00}
        ]
    },
    {
        "order_id": "ORD003",
        "order_number": "20260219003",
        "order_type": "dine_in",
        "order_status": "completed",
        "total": 88.00,
        "created_at": datetime.now(),
        "store_id": "store_001",
        "items": [
            {"dish_name": "蔬菜沙拉", "quantity": 1, "price": 38.00},
            {"dish_name": "清蒸鲈鱼", "quantity": 1, "price": 50.00}
        ]
    },
]

TEST_DISHES = [
    {
        "dish_id": "DISH001",
        "name": "宫保鸡丁",
        "category": "川菜",
        "description": "经典川菜，鸡肉配花生米，香辣可口",
        "price": 48.00,
        "is_available": True,
        "calories": 450,
        "is_spicy": True,
        "is_vegetarian": False,
        "store_id": "store_001",
        "tags": ["川菜", "辣", "鸡肉"]
    },
    {
        "dish_id": "DISH002",
        "name": "蔬菜沙拉",
        "category": "凉菜",
        "description": "新鲜蔬菜，低卡路里，健康素食",
        "price": 38.00,
        "is_available": True,
        "calories": 120,
        "is_spicy": False,
        "is_vegetarian": True,
        "store_id": "store_001",
        "tags": ["素食", "健康", "低卡"]
    },
    {
        "dish_id": "DISH003",
        "name": "清蒸鲈鱼",
        "category": "海鲜",
        "description": "新鲜鲈鱼清蒸，保持原汁原味，低脂肪",
        "price": 88.00,
        "is_available": True,
        "calories": 200,
        "is_spicy": False,
        "is_vegetarian": False,
        "store_id": "store_001",
        "tags": ["海鲜", "健康", "低脂"]
    },
    {
        "dish_id": "DISH004",
        "name": "麻婆豆腐",
        "category": "川菜",
        "description": "经典川菜，豆腐配肉末，麻辣鲜香",
        "price": 38.00,
        "is_available": True,
        "calories": 350,
        "is_spicy": True,
        "is_vegetarian": False,
        "store_id": "store_001",
        "tags": ["川菜", "辣", "豆腐"]
    },
]


async def test_vector_indexing():
    """测试向量索引功能"""
    logger.info("=" * 60)
    logger.info("开始测试向量索引功能")
    logger.info("=" * 60)

    # 初始化向量数据库服务
    vector_db = VectorDatabaseService()
    await vector_db.initialize()

    # 测试订单索引
    logger.info("\n[1] 测试订单索引")
    for order in TEST_ORDERS:
        success = await vector_db.index_order(order)
        if success:
            logger.info(f"✓ 订单索引成功: {order['order_id']} - {order['total']}元")
        else:
            logger.error(f"✗ 订单索引失败: {order['order_id']}")

    # 测试菜品索引
    logger.info("\n[2] 测试菜品索引")
    for dish in TEST_DISHES:
        success = await vector_db.index_dish(dish)
        if success:
            logger.info(f"✓ 菜品索引成功: {dish['dish_id']} - {dish['dish_name']}")
        else:
            logger.error(f"✗ 菜品索引失败: {dish['dish_id']}")

    # 测试语义搜索
    logger.info("\n[3] 测试语义搜索")

    # 搜索大额订单
    logger.info("\n搜索: '大额订单'")
    results = await vector_db.search_orders(
        query="大额订单",
        store_id="store_001",
        limit=3
    )
    for i, result in enumerate(results, 1):
        logger.info(f"  {i}. 订单号: {result['payload']['order_number']}, "
                   f"金额: {result['payload']['total']}元, "
                   f"相似度: {result['score']:.3f}")

    # 搜索低卡路里菜品
    logger.info("\n搜索: '低卡路里的素食菜品'")
    results = await vector_db.search_dishes(
        query="低卡路里的素食菜品",
        store_id="store_001",
        limit=3
    )
    for i, result in enumerate(results, 1):
        logger.info(f"  {i}. 菜品: {result['payload']['dish_name']}, "
                   f"卡路里: {result['payload']['calories']}, "
                   f"相似度: {result['score']:.3f}")

    # 搜索辣菜
    logger.info("\n搜索: '辣的川菜'")
    results = await vector_db.search_dishes(
        query="辣的川菜",
        store_id="store_001",
        limit=3
    )
    for i, result in enumerate(results, 1):
        logger.info(f"  {i}. 菜品: {result['payload']['dish_name']}, "
                   f"分类: {result['payload']['category']}, "
                   f"相似度: {result['score']:.3f}")

    logger.info("\n" + "=" * 60)
    logger.info("✓ 向量索引测试完成！")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_vector_indexing())
