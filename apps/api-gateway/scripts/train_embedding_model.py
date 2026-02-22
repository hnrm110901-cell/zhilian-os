"""
嵌入模型训练脚本
Embedding Model Training Script

用法：
    python scripts/train_embedding_model.py --tenant-id <tenant_id> --days 90

功能：
1. 收集训练数据
2. 训练 Word2Vec 模型
3. 评估模型性能
4. 保存模型文件
"""

import asyncio
import argparse
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.services.embedding_model_service import EmbeddingModelService
from src.core.config import settings
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def train_model(
    tenant_id: str,
    days: int = 90,
    embedding_dim: int = 128,
    window_size: int = 5,
    epochs: int = 10,
    learning_rate: float = 0.025,
    output_dir: str = "./models"
):
    """
    训练嵌入模型

    Args:
        tenant_id: 租户ID
        days: 训练数据天数
        embedding_dim: 嵌入维度
        window_size: 上下文窗口大小
        epochs: 训练轮数
        learning_rate: 学习率
        output_dir: 模型输出目录
    """
    # 创建数据库连接
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        logger.info("=" * 60)
        logger.info("嵌入模型训练开始")
        logger.info("=" * 60)
        logger.info(f"租户ID: {tenant_id}")
        logger.info(f"训练数据天数: {days}")
        logger.info(f"嵌入维度: {embedding_dim}")
        logger.info(f"训练轮数: {epochs}")
        logger.info("=" * 60)

        # 初始化服务
        service = EmbeddingModelService(db)

        # 步骤1: 收集训练数据
        logger.info("\n[步骤 1/4] 收集训练数据...")
        training_data = await service.collect_training_data(
            tenant_id=tenant_id,
            days=days
        )

        logger.info(f"✓ 菜品文本: {len(training_data['dish_texts'])} 条")
        logger.info(f"✓ 订单序列: {len(training_data['order_sequences'])} 条")
        logger.info(f"✓ 食材配对: {len(training_data['ingredient_pairs'])} 对")
        logger.info(f"✓ 标签组合: {len(training_data['tag_combinations'])} 组")

        # 步骤2: 训练模型
        logger.info("\n[步骤 2/4] 训练 Word2Vec 模型...")
        embeddings = service.train_word2vec(
            training_data=training_data,
            embedding_dim=embedding_dim,
            window_size=window_size,
            epochs=epochs,
            learning_rate=learning_rate
        )

        logger.info(f"✓ 词汇表大小: {len(service.vocab)}")
        logger.info(f"✓ 嵌入矩阵形状: {embeddings.shape}")

        # 步骤3: 评估模型
        logger.info("\n[步骤 3/4] 评估模型性能...")

        # 创建测试对（示例）
        test_pairs = [
            ("宫保鸡丁", "鱼香肉丝", 0.8),  # 相似菜品
            ("宫保鸡丁", "冰淇淋", 0.2),    # 不相似菜品
            ("红烧肉", "东坡肉", 0.9),      # 非常相似
            ("青菜", "肉类", 0.3),          # 不太相似
        ]

        metrics = service.evaluate_model(test_pairs)

        if metrics:
            logger.info(f"✓ MSE: {metrics['mse']:.4f}")
            logger.info(f"✓ MAE: {metrics['mae']:.4f}")
            logger.info(f"✓ 相关系数: {metrics['correlation']:.4f}")

        # 步骤4: 保存模型
        logger.info("\n[步骤 4/4] 保存模型...")

        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)

        model_path = os.path.join(
            output_dir,
            f"embedding_model_{tenant_id}.json"
        )

        service.save_model(model_path)
        logger.info(f"✓ 模型已保存到: {model_path}")

        # 训练完成
        logger.info("\n" + "=" * 60)
        logger.info("✓ 训练完成！")
        logger.info("=" * 60)

        # 显示示例用法
        logger.info("\n示例用法：")
        logger.info("1. 计算相似度:")
        logger.info('   service.calculate_similarity("宫保鸡丁", "鱼香肉丝")')
        logger.info("\n2. 查找相似菜品:")
        logger.info('   service.find_similar_dishes("宫保鸡丁", top_k=5)')
        logger.info("\n3. 推荐菜品:")
        logger.info('   service.recommend_dishes_by_order(["宫保鸡丁", "米饭"], top_k=3)')

    except Exception as e:
        logger.error(f"\n✗ 训练失败: {e}")
        raise

    finally:
        db.close()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="训练餐饮行业嵌入模型"
    )

    parser.add_argument(
        "--tenant-id",
        type=str,
        required=True,
        help="租户ID"
    )

    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="训练数据天数（默认: 90）"
    )

    parser.add_argument(
        "--embedding-dim",
        type=int,
        default=128,
        help="嵌入维度（默认: 128）"
    )

    parser.add_argument(
        "--window-size",
        type=int,
        default=5,
        help="上下文窗口大小（默认: 5）"
    )

    parser.add_argument(
        "--epochs",
        type=int,
        default=10,
        help="训练轮数（默认: 10）"
    )

    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.025,
        help="学习率（默认: 0.025）"
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="./models",
        help="模型输出目录（默认: ./models）"
    )

    args = parser.parse_args()

    # 运行训练
    asyncio.run(train_model(
        tenant_id=args.tenant_id,
        days=args.days,
        embedding_dim=args.embedding_dim,
        window_size=args.window_size,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        output_dir=args.output_dir
    ))


if __name__ == "__main__":
    main()
