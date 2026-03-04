"""
VectorDbServiceEnhanced 嵌入向量生成单元测试

覆盖：
- generate_embedding: 空文本/空白文本 → 零向量
- generate_embedding: 本地模型可用 → 调用 encode() 并返回结果
- generate_embedding: 本地模型失败 → 降级到 API（有 API key 时）
- generate_embedding: 本地模型失败 + 无 API key → 零向量
- generate_embedding: 本地模型失败 + API 失败 → 零向量
- generate_embedding: 返回向量维度受 VECTOR_EMBEDDING_DIM 控制
- _embed_via_api: 无 API key → 返回 None（不发网络请求）
"""
import os
import pytest
from unittest.mock import MagicMock, patch

from src.services.vector_db_service_enhanced import VectorDbServiceEnhanced


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

def _svc(embedding_model=None) -> VectorDbServiceEnhanced:
    """创建不连接 Qdrant 的服务实例"""
    svc = VectorDbServiceEnhanced.__new__(VectorDbServiceEnhanced)
    svc.embedding_model = embedding_model
    svc.qdrant_client = None
    svc.circuit_breaker = MagicMock()
    return svc


# ---------------------------------------------------------------------------
# 空文本守卫
# ---------------------------------------------------------------------------

class TestGenerateEmbeddingEmptyText:
    def test_empty_string_returns_zero_vector(self):
        svc = _svc()
        result = svc.generate_embedding("")
        assert all(v == 0.0 for v in result)

    def test_whitespace_string_returns_zero_vector(self):
        svc = _svc()
        result = svc.generate_embedding("   ")
        assert all(v == 0.0 for v in result)

    def test_empty_vector_has_correct_dim(self, monkeypatch):
        monkeypatch.setenv("VECTOR_EMBEDDING_DIM", "128")
        svc = _svc()
        result = svc.generate_embedding("")
        assert len(result) == 128


# ---------------------------------------------------------------------------
# 本地模型成功路径
# ---------------------------------------------------------------------------

class TestGenerateEmbeddingLocalModel:
    def test_local_model_encode_called(self):
        import numpy as np
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([0.1, 0.2, 0.3])
        svc = _svc(embedding_model=mock_model)
        result = svc.generate_embedding("测试文本")
        mock_model.encode.assert_called_once_with("测试文本", convert_to_numpy=True)

    def test_local_model_returns_list(self):
        import numpy as np
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([0.1, 0.2, 0.3])
        svc = _svc(embedding_model=mock_model)
        result = svc.generate_embedding("测试文本")
        assert isinstance(result, list)
        assert result == pytest.approx([0.1, 0.2, 0.3])

    def test_local_model_does_not_call_api(self):
        import numpy as np
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([0.1, 0.2, 0.3])
        svc = _svc(embedding_model=mock_model)
        with patch.object(svc, "_embed_via_api") as mock_api:
            svc.generate_embedding("测试文本")
        mock_api.assert_not_called()


# ---------------------------------------------------------------------------
# 本地模型失败 → API 降级
# ---------------------------------------------------------------------------

class TestGenerateEmbeddingApiFallback:
    def test_local_model_failure_falls_back_to_api(self):
        mock_model = MagicMock()
        mock_model.encode.side_effect = RuntimeError("GPU OOM")
        svc = _svc(embedding_model=mock_model)
        api_vec = [0.5] * 384
        with patch.object(svc, "_embed_via_api", return_value=api_vec) as mock_api:
            result = svc.generate_embedding("测试文本")
        mock_api.assert_called_once()
        assert result == api_vec

    def test_local_model_failure_plus_api_failure_returns_zero_vector(self, monkeypatch):
        monkeypatch.setenv("VECTOR_EMBEDDING_DIM", "384")
        mock_model = MagicMock()
        mock_model.encode.side_effect = RuntimeError("GPU OOM")
        svc = _svc(embedding_model=mock_model)
        with patch.object(svc, "_embed_via_api", return_value=None):
            result = svc.generate_embedding("测试文本")
        assert all(v == 0.0 for v in result)
        assert len(result) == 384

    def test_no_local_model_no_api_key_returns_zero_vector(self, monkeypatch):
        monkeypatch.setenv("VECTOR_EMBEDDING_DIM", "384")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        svc = _svc(embedding_model=None)
        result = svc.generate_embedding("测试文本")
        assert all(v == 0.0 for v in result)
        assert len(result) == 384


# ---------------------------------------------------------------------------
# 零向量维度受环境变量控制
# ---------------------------------------------------------------------------

class TestGenerateEmbeddingDimension:
    def test_default_dim_is_384(self, monkeypatch):
        monkeypatch.delenv("VECTOR_EMBEDDING_DIM", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        svc = _svc()
        result = svc.generate_embedding("测试")
        assert len(result) == 384

    def test_custom_dim_applied(self, monkeypatch):
        monkeypatch.setenv("VECTOR_EMBEDDING_DIM", "256")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        svc = _svc()
        result = svc.generate_embedding("测试")
        assert len(result) == 256


# ---------------------------------------------------------------------------
# _embed_via_api: 无 key → 直接返回 None
# ---------------------------------------------------------------------------

class TestEmbedViaApiNoKey:
    def test_no_api_key_returns_none(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        svc = _svc()
        result = svc._embed_via_api("测试文本", 384)
        assert result is None

    def test_no_api_key_does_not_make_network_request(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        svc = _svc()
        with patch("urllib.request.urlopen") as mock_urlopen:
            svc._embed_via_api("测试文本", 384)
        mock_urlopen.assert_not_called()
