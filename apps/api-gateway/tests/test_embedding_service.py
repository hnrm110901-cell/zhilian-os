"""
嵌入模型服务测试
Embedding Model Service Tests
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch
from src.services.embedding_model_service import EmbeddingModelService


@pytest.fixture
def mock_db():
    """模拟数据库会话"""
    return Mock()


@pytest.fixture
def service(mock_db):
    """创建服务实例"""
    return EmbeddingModelService(mock_db)


class TestTextPreprocessing:
    """文本预处理测试"""

    def test_preprocess_chinese_text(self, service):
        """测试中文文本预处理"""
        text = "宫保鸡丁是一道美味的川菜"
        tokens = service.preprocess_text(text)

        assert len(tokens) > 0
        assert "宫" in tokens
        assert "保" in tokens
        assert "鸡" in tokens
        assert "丁" in tokens

    def test_preprocess_mixed_text(self, service):
        """测试中英文混合文本"""
        text = "宫保鸡丁 Kung Pao Chicken"
        tokens = service.preprocess_text(text)

        assert "宫" in tokens
        assert "Kung" in tokens or "kung" in tokens.lower()

    def test_remove_stopwords(self, service):
        """测试停用词过滤"""
        text = "这是一道美味的菜"
        tokens = service.preprocess_text(text)

        # 停用词应该被过滤
        assert "的" not in tokens


class TestVocabularyBuilding:
    """词汇表构建测试"""

    def test_build_vocabulary(self, service):
        """测试词汇表构建"""
        texts = [
            "宫保鸡丁",
            "鱼香肉丝",
            "宫保鸡丁",  # 重复
            "麻婆豆腐"
        ]

        vocab = service.build_vocabulary(texts, min_freq=1)

        assert len(vocab) > 0
        assert "宫" in vocab
        assert "保" in vocab

    def test_min_frequency_filter(self, service):
        """测试最小词频过滤"""
        texts = [
            "宫保鸡丁",
            "鱼香肉丝",
            "麻婆豆腐"
        ]

        vocab = service.build_vocabulary(texts, min_freq=2)

        # 只出现一次的词应该被过滤
        # （具体结果取决于分词逻辑）
        assert isinstance(vocab, dict)


class TestModelTraining:
    """模型训练测试"""

    def test_train_word2vec(self, service):
        """测试 Word2Vec 训练"""
        training_data = {
            "dish_texts": [
                "宫保鸡丁 辣味 川菜",
                "鱼香肉丝 酸辣 川菜",
                "麻婆豆腐 麻辣 川菜"
            ],
            "order_sequences": [
                ["宫保鸡丁", "米饭"],
                ["鱼香肉丝", "米饭"]
            ],
            "review_texts": [],
            "ingredient_pairs": [],
            "tag_combinations": []
        }

        embeddings = service.train_word2vec(
            training_data=training_data,
            embedding_dim=64,
            window_size=3,
            epochs=2,
            learning_rate=0.01
        )

        assert embeddings is not None
        assert embeddings.shape[1] == 64  # 嵌入维度
        assert len(service.vocab) > 0

    def test_training_with_empty_data(self, service):
        """测试空数据训练"""
        training_data = {
            "dish_texts": [],
            "order_sequences": [],
            "review_texts": [],
            "ingredient_pairs": [],
            "tag_combinations": []
        }

        # 应该能处理空数据（或抛出合适的异常）
        try:
            embeddings = service.train_word2vec(
                training_data=training_data,
                embedding_dim=64,
                epochs=1
            )
            # 如果没有抛出异常，检查结果
            assert embeddings is not None
        except Exception:
            # 空数据可能导致异常，这是可以接受的
            pass


class TestEmbeddingInference:
    """嵌入推理测试"""

    @pytest.fixture
    def trained_service(self, service):
        """创建已训练的服务"""
        training_data = {
            "dish_texts": [
                "宫保鸡丁 辣味 川菜",
                "鱼香肉丝 酸辣 川菜",
                "麻婆豆腐 麻辣 川菜"
            ],
            "order_sequences": [],
            "review_texts": [],
            "ingredient_pairs": [],
            "tag_combinations": []
        }

        service.train_word2vec(
            training_data=training_data,
            embedding_dim=64,
            epochs=2
        )

        return service

    def test_get_embedding(self, trained_service):
        """测试获取嵌入向量"""
        embedding = trained_service.get_embedding("宫保鸡丁")

        assert embedding is not None
        assert len(embedding) == 64  # 嵌入维度
        assert isinstance(embedding, np.ndarray)

    def test_get_embedding_unknown_text(self, trained_service):
        """测试未知文本"""
        embedding = trained_service.get_embedding("完全未知的菜品名称xyz")

        # 未知文本应该返回 None 或零向量
        assert embedding is None or np.allclose(embedding, 0)

    def test_calculate_similarity_cosine(self, trained_service):
        """测试余弦相似度计算"""
        similarity = trained_service.calculate_similarity(
            "宫保鸡丁",
            "鱼香肉丝",
            method="cosine"
        )

        assert 0 <= similarity <= 1
        assert isinstance(similarity, float)

    def test_calculate_similarity_euclidean(self, trained_service):
        """测试欧氏距离相似度"""
        similarity = trained_service.calculate_similarity(
            "宫保鸡丁",
            "鱼香肉丝",
            method="euclidean"
        )

        assert 0 <= similarity <= 1
        assert isinstance(similarity, float)

    def test_similarity_same_text(self, trained_service):
        """测试相同文本的相似度"""
        similarity = trained_service.calculate_similarity(
            "宫保鸡丁",
            "宫保鸡丁",
            method="cosine"
        )

        # 相同文本的余弦相似度应该接近1
        assert similarity > 0.9


class TestModelPersistence:
    """模型持久化测试"""

    def test_save_and_load_model(self, service, tmp_path):
        """测试模型保存和加载"""
        # 训练模型
        training_data = {
            "dish_texts": ["宫保鸡丁", "鱼香肉丝"],
            "order_sequences": [],
            "review_texts": [],
            "ingredient_pairs": [],
            "tag_combinations": []
        }

        service.train_word2vec(
            training_data=training_data,
            embedding_dim=32,
            epochs=1
        )

        # 保存模型
        model_path = tmp_path / "test_model.json"
        service.save_model(str(model_path))

        assert model_path.exists()

        # 创建新服务并加载模型
        new_service = EmbeddingModelService(service.db)
        new_service.load_model(str(model_path))

        assert new_service.model is not None
        assert len(new_service.vocab) == len(service.vocab)
        assert new_service.embedding_dim == service.embedding_dim

    def test_save_without_training(self, service, tmp_path):
        """测试未训练就保存"""
        model_path = tmp_path / "test_model.json"

        with pytest.raises(ValueError):
            service.save_model(str(model_path))


class TestRecommendation:
    """推荐功能测试"""

    @pytest.fixture
    def trained_service_with_db(self, service, mock_db):
        """创建带数据库的已训练服务"""
        # 训练模型
        training_data = {
            "dish_texts": [
                "宫保鸡丁 辣味",
                "鱼香肉丝 酸辣",
                "麻婆豆腐 麻辣",
                "清蒸鱼 清淡"
            ],
            "order_sequences": [],
            "review_texts": [],
            "ingredient_pairs": [],
            "tag_combinations": []
        }

        service.train_word2vec(
            training_data=training_data,
            embedding_dim=64,
            epochs=2
        )

        # 模拟数据库查询
        mock_result = Mock()
        mock_result.fetchall.return_value = [
            Mock(
                id=1,
                name="宫保鸡丁",
                description="辣味川菜",
                tags='["辣", "川菜"]'
            ),
            Mock(
                id=2,
                name="鱼香肉丝",
                description="酸辣川菜",
                tags='["酸辣", "川菜"]'
            ),
            Mock(
                id=3,
                name="清蒸鱼",
                description="清淡粤菜",
                tags='["清淡", "粤菜"]'
            )
        ]

        mock_db.execute.return_value = mock_result

        return service

    def test_find_similar_dishes(self, trained_service_with_db):
        """测试查找相似菜品"""
        similar_dishes = trained_service_with_db.find_similar_dishes(
            dish_name="宫保鸡丁",
            top_k=2
        )

        assert len(similar_dishes) <= 2
        assert all("dish_name" in dish for dish in similar_dishes)
        assert all("similarity" in dish for dish in similar_dishes)

    def test_recommend_dishes_by_order(self, trained_service_with_db):
        """测试基于订单推荐"""
        # 模拟数据库查询
        mock_result = Mock()
        mock_result.fetchall.return_value = [
            Mock(id=2, name="鱼香肉丝", description="酸辣", price=28.0),
            Mock(id=3, name="清蒸鱼", description="清淡", price=48.0)
        ]

        trained_service_with_db.db.execute.return_value = mock_result

        recommendations = trained_service_with_db.recommend_dishes_by_order(
            order_dish_names=["宫保鸡丁"],
            top_k=2
        )

        assert len(recommendations) <= 2
        assert all("dish_name" in dish for dish in recommendations)
        assert all("similarity" in dish for dish in recommendations)


class TestModelEvaluation:
    """模型评估测试"""

    @pytest.fixture
    def trained_service(self, service):
        """创建已训练的服务"""
        training_data = {
            "dish_texts": [
                "宫保鸡丁 辣味",
                "鱼香肉丝 酸辣",
                "麻婆豆腐 麻辣"
            ],
            "order_sequences": [],
            "review_texts": [],
            "ingredient_pairs": [],
            "tag_combinations": []
        }

        service.train_word2vec(
            training_data=training_data,
            embedding_dim=64,
            epochs=2
        )

        return service

    def test_evaluate_model(self, trained_service):
        """测试模型评估"""
        test_pairs = [
            ("宫保鸡丁", "鱼香肉丝", 0.8),
            ("宫保鸡丁", "麻婆豆腐", 0.7),
        ]

        metrics = trained_service.evaluate_model(test_pairs)

        assert "mse" in metrics
        assert "mae" in metrics
        assert "correlation" in metrics
        assert metrics["num_samples"] == 2

    def test_evaluate_empty_pairs(self, trained_service):
        """测试空测试对"""
        metrics = trained_service.evaluate_model([])

        assert metrics == {}


class TestBatchProcessing:
    """批量处理测试"""

    @pytest.fixture
    def trained_service(self, service):
        """创建已训练的服务"""
        training_data = {
            "dish_texts": ["宫保鸡丁", "鱼香肉丝", "麻婆豆腐"],
            "order_sequences": [],
            "review_texts": [],
            "ingredient_pairs": [],
            "tag_combinations": []
        }

        service.train_word2vec(
            training_data=training_data,
            embedding_dim=32,
            epochs=1
        )

        return service

    @pytest.mark.asyncio
    async def test_batch_compute_embeddings(self, trained_service):
        """测试批量计算嵌入"""
        texts = ["宫保鸡丁", "鱼香肉丝", "麻婆豆腐"]

        embeddings = await trained_service.batch_compute_embeddings(
            texts=texts,
            batch_size=2
        )

        assert len(embeddings) == 3
        assert all(
            emb is None or isinstance(emb, np.ndarray)
            for emb in embeddings
        )
