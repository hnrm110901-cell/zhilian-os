"""
餐饮行业嵌入模型训练服务
Restaurant Industry Embedding Model Training Service

功能：
1. 数据收集与预处理
2. 模型训练（Word2Vec/BERT）
3. 向量存储与检索
4. 相似度计算
"""

import os
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import json
import logging

logger = logging.getLogger(__name__)


class EmbeddingModelService:
    """嵌入模型训练与推理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.model = None
        self.vocab = {}
        self.embedding_dim = int(os.getenv("EMBEDDING_DIM", "128"))

    # ==================== 数据收集 ====================

    async def collect_training_data(
        self,
        tenant_id: Optional[str] = None,
        days: int = int(os.getenv("EMBEDDING_TRAIN_DATA_DAYS", "90"))
    ) -> Dict[str, List]:
        """
        收集训练数据

        数据源：
        1. 菜品名称、描述、标签
        2. 订单序列（菜品共现）
        3. 用户评价文本
        4. 食材关联关系
        5. 口味标签组合
        """
        start_date = datetime.now() - timedelta(days=days)

        training_data = {
            "dish_texts": [],      # 菜品文本
            "order_sequences": [], # 订单序列
            "review_texts": [],    # 评价文本
            "ingredient_pairs": [], # 食材配对
            "tag_combinations": []  # 标签组合
        }

        try:
            # 1. 收集菜品文本数据
            dish_query = """
                SELECT
                    name,
                    description,
                    tags,
                    main_ingredients,
                    flavor_tags
                FROM dishes
                WHERE created_at >= :start_date
            """
            if tenant_id:
                dish_query += " AND tenant_id = :tenant_id"

            params = {"start_date": start_date}
            if tenant_id:
                params["tenant_id"] = tenant_id

            result = await self.db.execute(text(dish_query), params)
            dishes = result.fetchall()

            for dish in dishes:
                # 组合菜品文本
                text_parts = [dish.name]
                if dish.description:
                    text_parts.append(dish.description)
                if dish.tags:
                    text_parts.extend(json.loads(dish.tags))
                if dish.main_ingredients:
                    text_parts.extend(json.loads(dish.main_ingredients))

                training_data["dish_texts"].append(" ".join(text_parts))

                # 收集标签组合
                if dish.tags and dish.flavor_tags:
                    tags = json.loads(dish.tags)
                    flavors = json.loads(dish.flavor_tags)
                    training_data["tag_combinations"].append(tags + flavors)

            # 2. 收集订单序列（菜品共现）
            order_query = """
                SELECT
                    o.id,
                    array_agg(d.name ORDER BY oi.created_at) as dish_sequence
                FROM orders o
                JOIN order_items oi ON o.id = oi.order_id
                JOIN dishes d ON oi.dish_id = d.id
                WHERE o.created_at >= :start_date
            """
            if tenant_id:
                order_query += " AND o.tenant_id = :tenant_id"
            order_query += " GROUP BY o.id"

            result = await self.db.execute(text(order_query), params)
            orders = result.fetchall()

            for order in orders:
                if order.dish_sequence:
                    training_data["order_sequences"].append(order.dish_sequence)

            # 3. 收集食材配对关系
            ingredient_query = """
                SELECT DISTINCT
                    d1.main_ingredients as ing1,
                    d2.main_ingredients as ing2
                FROM dishes d1
                JOIN dishes d2 ON d1.category = d2.category
                WHERE d1.id < d2.id
                AND d1.created_at >= :start_date
            """
            if tenant_id:
                ingredient_query += " AND d1.tenant_id = :tenant_id"

            result = await self.db.execute(text(ingredient_query), params)
            ingredient_pairs = result.fetchall()

            for pair in ingredient_pairs:
                if pair.ing1 and pair.ing2:
                    ing1_list = json.loads(pair.ing1)
                    ing2_list = json.loads(pair.ing2)
                    training_data["ingredient_pairs"].append((ing1_list, ing2_list))

            logger.info(
                f"Collected training data: "
                f"{len(training_data['dish_texts'])} dishes, "
                f"{len(training_data['order_sequences'])} orders"
            )

            return training_data

        except Exception as e:
            logger.error(f"Error collecting training data: {e}")
            raise

    # ==================== 数据预处理 ====================

    def preprocess_text(self, text: str) -> List[str]:
        """
        文本预处理

        步骤：
        1. 分词（中文）
        2. 去除停用词
        3. 标准化
        """
        # 简单的中文分词（生产环境应使用 jieba）
        # 这里使用字符级分词作为示例
        tokens = []
        current_word = ""

        for char in text:
            if '\u4e00' <= char <= '\u9fff':  # 中文字符
                if current_word:
                    tokens.append(current_word)
                    current_word = ""
                tokens.append(char)
            elif char.isalnum():
                current_word += char
            else:
                if current_word:
                    tokens.append(current_word)
                    current_word = ""

        if current_word:
            tokens.append(current_word)

        # 去除停用词（简化版）
        stopwords = {"的", "了", "和", "与", "及", "等"}
        tokens = [t for t in tokens if t not in stopwords]

        return tokens

    def build_vocabulary(self, texts: List[str], min_freq: int = 2) -> Dict[str, int]:
        """
        构建词汇表

        Args:
            texts: 文本列表
            min_freq: 最小词频

        Returns:
            词汇表 {word: index}
        """
        word_freq = {}

        # 统计词频
        for text in texts:
            tokens = self.preprocess_text(text)
            for token in tokens:
                word_freq[token] = word_freq.get(token, 0) + 1

        # 过滤低频词
        vocab = {
            word: idx
            for idx, (word, freq) in enumerate(
                sorted(
                    [(w, f) for w, f in word_freq.items() if f >= min_freq],
                    key=lambda x: x[1],
                    reverse=True
                )
            )
        }

        logger.info(f"Built vocabulary with {len(vocab)} words")
        return vocab

    # ==================== 模型训练 ====================

    def train_word2vec(
        self,
        training_data: Dict[str, List],
        embedding_dim: int = int(os.getenv("EMBEDDING_DIM", "128")),
        window_size: int = int(os.getenv("EMBEDDING_WINDOW_SIZE", "5")),
        epochs: int = int(os.getenv("EMBEDDING_EPOCHS", "10")),
        learning_rate: float = float(os.getenv("EMBEDDING_LEARNING_RATE", "0.025"))
    ) -> np.ndarray:
        """
        训练 Word2Vec 模型（Skip-gram）

        Args:
            training_data: 训练数据
            embedding_dim: 嵌入维度
            window_size: 上下文窗口大小
            epochs: 训练轮数
            learning_rate: 学习率

        Returns:
            嵌入矩阵 [vocab_size, embedding_dim]
        """
        # 准备训练语料
        corpus = []
        corpus.extend(training_data["dish_texts"])
        for seq in training_data["order_sequences"]:
            corpus.append(" ".join(seq))

        # 构建词汇表
        self.vocab = self.build_vocabulary(corpus)
        vocab_size = len(self.vocab)
        self.embedding_dim = embedding_dim

        # 初始化嵌入矩阵
        embeddings = np.random.randn(vocab_size, embedding_dim) * 0.01

        # 准备训练对（中心词，上下文词）
        training_pairs = []
        for text in corpus:
            tokens = self.preprocess_text(text)
            token_ids = [self.vocab.get(t) for t in tokens if t in self.vocab]

            for i, center_id in enumerate(token_ids):
                # 获取上下文窗口
                start = max(0, i - window_size)
                end = min(len(token_ids), i + window_size + 1)

                for j in range(start, end):
                    if j != i and token_ids[j] is not None:
                        training_pairs.append((center_id, token_ids[j]))

        logger.info(f"Generated {len(training_pairs)} training pairs")

        # 训练（简化版 Skip-gram）
        for epoch in range(epochs):
            np.random.shuffle(training_pairs)
            total_loss = 0

            for center_id, context_id in training_pairs:
                # 前向传播
                center_vec = embeddings[center_id]
                context_vec = embeddings[context_id]

                # 计算相似度
                similarity = np.dot(center_vec, context_vec)
                prob = 1 / (1 + np.exp(-similarity))  # Sigmoid

                # 反向传播（简化版）
                error = prob - 1  # 目标是1（正样本）
                grad = error * context_vec

                # 更新嵌入
                embeddings[center_id] -= learning_rate * grad
                embeddings[context_id] -= learning_rate * error * center_vec

                total_loss += -np.log(prob + 1e-10)

            avg_loss = total_loss / len(training_pairs)
            logger.info(f"Epoch {epoch + 1}/{epochs}, Loss: {avg_loss:.4f}")

            # 学习率衰减
            learning_rate *= float(os.getenv("EMBEDDING_LR_DECAY", "0.95"))

        self.model = embeddings
        logger.info(f"Training completed. Embedding shape: {embeddings.shape}")

        return embeddings

    # ==================== 模型保存与加载 ====================

    def save_model(self, model_path: str):
        """保存模型到文件"""
        if self.model is None:
            raise ValueError("No model to save")

        model_data = {
            "embeddings": self.model.tolist(),
            "vocab": self.vocab,
            "embedding_dim": self.embedding_dim,
            "created_at": datetime.now().isoformat()
        }

        with open(model_path, 'w', encoding='utf-8') as f:
            json.dump(model_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Model saved to {model_path}")

    def load_model(self, model_path: str):
        """从文件加载模型"""
        with open(model_path, 'r', encoding='utf-8') as f:
            model_data = json.load(f)

        self.model = np.array(model_data["embeddings"])
        self.vocab = model_data["vocab"]
        self.embedding_dim = model_data["embedding_dim"]

        logger.info(f"Model loaded from {model_path}")

    # ==================== 推理方法 ====================

    def get_embedding(self, text: str) -> Optional[np.ndarray]:
        """
        获取文本的嵌入向量

        Args:
            text: 输入文本

        Returns:
            嵌入向量 [embedding_dim]
        """
        if self.model is None:
            raise ValueError("Model not trained or loaded")

        tokens = self.preprocess_text(text)
        token_ids = [self.vocab.get(t) for t in tokens if t in self.vocab]

        if not token_ids:
            return None

        # 平均池化
        embeddings = [self.model[tid] for tid in token_ids]
        return np.mean(embeddings, axis=0)

    def calculate_similarity(
        self,
        text1: str,
        text2: str,
        method: str = "cosine"
    ) -> float:
        """
        计算两个文本的相似度

        Args:
            text1: 文本1
            text2: 文本2
            method: 相似度计算方法 (cosine/euclidean)

        Returns:
            相似度分数
        """
        emb1 = self.get_embedding(text1)
        emb2 = self.get_embedding(text2)

        if emb1 is None or emb2 is None:
            return 0.0

        if method == "cosine":
            # 余弦相似度
            norm1 = np.linalg.norm(emb1)
            norm2 = np.linalg.norm(emb2)
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return float(np.dot(emb1, emb2) / (norm1 * norm2))

        elif method == "euclidean":
            # 欧氏距离（转换为相似度）
            distance = np.linalg.norm(emb1 - emb2)
            return float(1 / (1 + distance))

        else:
            raise ValueError(f"Unknown similarity method: {method}")

    async def find_similar_dishes(
        self,
        dish_name: str,
        top_k: int = int(os.getenv("EMBEDDING_SEARCH_TOP_K", "10")),
        tenant_id: Optional[str] = None
    ) -> List[Dict]:
        """
        查找相似菜品

        Args:
            dish_name: 菜品名称
            top_k: 返回前K个相似菜品
            tenant_id: 租户ID

        Returns:
            相似菜品列表
        """
        if self.model is None:
            raise ValueError("Model not trained or loaded")

        # 获取目标菜品的嵌入
        target_embedding = self.get_embedding(dish_name)
        if target_embedding is None:
            return []

        # 查询所有菜品
        query = "SELECT id, name, description, tags FROM dishes"
        params = {}

        if tenant_id:
            query += " WHERE tenant_id = :tenant_id"
            params["tenant_id"] = tenant_id

        result = await self.db.execute(text(query), params)
        dishes = result.fetchall()

        # 计算相似度
        for dish in dishes:
            if dish.name == dish_name:
                continue

            dish_text = dish.name
            if dish.description:
                dish_text += " " + dish.description

            similarity = self.calculate_similarity(dish_name, dish_text)
            similarities.append({
                "dish_id": dish.id,
                "dish_name": dish.name,
                "similarity": similarity,
                "tags": json.loads(dish.tags) if dish.tags else []
            })

        # 排序并返回 top_k
        similarities.sort(key=lambda x: x["similarity"], reverse=True)
        return similarities[:top_k]

    async def recommend_dishes_by_order(
        self,
        order_dish_names: List[str],
        top_k: int = int(os.getenv("EMBEDDING_RECOMMEND_TOP_K", "5")),
        tenant_id: Optional[str] = None
    ) -> List[Dict]:
        """
        基于订单中的菜品推荐其他菜品

        Args:
            order_dish_names: 订单中的菜品名称列表
            top_k: 推荐数量
            tenant_id: 租户ID

        Returns:
            推荐菜品列表
        """
        if not order_dish_names:
            return []

        # 获取订单菜品的平均嵌入
        order_embeddings = []
        for dish_name in order_dish_names:
            emb = self.get_embedding(dish_name)
            if emb is not None:
                order_embeddings.append(emb)

        if not order_embeddings:
            return []

        avg_embedding = np.mean(order_embeddings, axis=0)

        # 查询所有菜品
        query = "SELECT id, name, description, price FROM dishes"
        params = {}

        if tenant_id:
            query += " WHERE tenant_id = :tenant_id"
            params["tenant_id"] = tenant_id

        result = await self.db.execute(text(query), params)
        dishes = result.fetchall()

        # 计算相似度
        recommendations = []
        for dish in dishes:
            if dish.name in order_dish_names:
                continue

            dish_embedding = self.get_embedding(dish.name)
            if dish_embedding is None:
                continue

            # 计算余弦相似度
            similarity = float(
                np.dot(avg_embedding, dish_embedding) /
                (np.linalg.norm(avg_embedding) * np.linalg.norm(dish_embedding))
            )

            recommendations.append({
                "dish_id": dish.id,
                "dish_name": dish.name,
                "price": float(dish.price),
                "similarity": similarity,
                "reason": "基于您的订单偏好推荐"
            })

        # 排序并返回 top_k
        recommendations.sort(key=lambda x: x["similarity"], reverse=True)
        return recommendations[:top_k]

    # ==================== 模型评估 ====================

    def evaluate_model(
        self,
        test_pairs: List[Tuple[str, str, float]]
    ) -> Dict[str, float]:
        """
        评估模型性能

        Args:
            test_pairs: 测试对 [(text1, text2, ground_truth_similarity), ...]

        Returns:
            评估指标
        """
        if not test_pairs:
            return {}

        predictions = []
        ground_truths = []

        for text1, text2, gt_sim in test_pairs:
            pred_sim = self.calculate_similarity(text1, text2)
            predictions.append(pred_sim)
            ground_truths.append(gt_sim)

        predictions = np.array(predictions)
        ground_truths = np.array(ground_truths)

        # 计算评估指标
        mse = np.mean((predictions - ground_truths) ** 2)
        mae = np.mean(np.abs(predictions - ground_truths))
        correlation = np.corrcoef(predictions, ground_truths)[0, 1]

        return {
            "mse": float(mse),
            "mae": float(mae),
            "correlation": float(correlation),
            "num_samples": len(test_pairs)
        }

    # ==================== 批量处理 ====================

    async def batch_compute_embeddings(
        self,
        texts: List[str],
        batch_size: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "100"))
    ) -> List[Optional[np.ndarray]]:
        """
        批量计算嵌入向量

        Args:
            texts: 文本列表
            batch_size: 批次大小

        Returns:
            嵌入向量列表
        """
        embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = [self.get_embedding(text) for text in batch]
            embeddings.extend(batch_embeddings)

            logger.info(f"Processed {min(i + batch_size, len(texts))}/{len(texts)} texts")

        return embeddings
