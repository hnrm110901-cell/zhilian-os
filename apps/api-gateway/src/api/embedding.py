"""
嵌入模型 API
Embedding Model API

功能：
1. 模型训练
2. 相似度计算
3. 菜品推荐
4. 模型评估
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field

from ..core.database import get_db
from ..core.tenant_context import get_current_tenant
from ..services.embedding_model_service import EmbeddingModelService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/embedding", tags=["embedding"])


# ==================== 请求模型 ====================

class TrainModelRequest(BaseModel):
    """训练模型请求"""
    days: int = Field(90, description="训练数据天数")
    embedding_dim: int = Field(128, description="嵌入维度")
    window_size: int = Field(5, description="上下文窗口大小")
    epochs: int = Field(10, description="训练轮数")
    learning_rate: float = Field(0.025, description="学习率")


class SimilarityRequest(BaseModel):
    """相似度计算请求"""
    text1: str = Field(..., description="文本1")
    text2: str = Field(..., description="文本2")
    method: str = Field("cosine", description="相似度方法")


class FindSimilarDishesRequest(BaseModel):
    """查找相似菜品请求"""
    dish_name: str = Field(..., description="菜品名称")
    top_k: int = Field(10, description="返回数量")


class RecommendDishesRequest(BaseModel):
    """推荐菜品请求"""
    order_dish_names: List[str] = Field(..., description="订单菜品列表")
    top_k: int = Field(5, description="推荐数量")


class EmbeddingRequest(BaseModel):
    """获取嵌入向量请求"""
    text: str = Field(..., description="输入文本")


# ==================== 响应模型 ====================

class TrainModelResponse(BaseModel):
    """训练模型响应"""
    status: str
    message: str
    vocab_size: int
    embedding_dim: int
    training_samples: int


class SimilarityResponse(BaseModel):
    """相似度响应"""
    similarity: float
    method: str


class SimilarDish(BaseModel):
    """相似菜品"""
    dish_id: int
    dish_name: str
    similarity: float
    tags: List[str]


class RecommendedDish(BaseModel):
    """推荐菜品"""
    dish_id: int
    dish_name: str
    price: float
    similarity: float
    reason: str


class EmbeddingResponse(BaseModel):
    """嵌入向量响应"""
    embedding: List[float]
    dimension: int


# ==================== API 端点 ====================

@router.post("/train", response_model=TrainModelResponse)
async def train_model(
    request: TrainModelRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant)
):
    """
    训练嵌入模型

    训练过程：
    1. 收集训练数据（菜品、订单、评价）
    2. 数据预处理（分词、构建词汇表）
    3. Word2Vec 训练（Skip-gram）
    4. 保存模型

    注意：训练是异步任务，可能需要几分钟
    """
    try:
        service = EmbeddingModelService(db)

        # 收集训练数据
        logger.info(f"Collecting training data for tenant {tenant_id}")
        training_data = await service.collect_training_data(
            tenant_id=tenant_id,
            days=request.days
        )

        # 训练模型
        logger.info("Starting model training")
        embeddings = service.train_word2vec(
            training_data=training_data,
            embedding_dim=request.embedding_dim,
            window_size=request.window_size,
            epochs=request.epochs,
            learning_rate=request.learning_rate
        )

        # 保存模型
        model_path = f"/tmp/embedding_model_{tenant_id}.json"
        service.save_model(model_path)

        # 计算训练样本数
        total_samples = (
            len(training_data["dish_texts"]) +
            len(training_data["order_sequences"])
        )

        return TrainModelResponse(
            status="success",
            message="模型训练完成",
            vocab_size=len(service.vocab),
            embedding_dim=request.embedding_dim,
            training_samples=total_samples
        )

    except Exception as e:
        logger.error(f"Error training model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/similarity", response_model=SimilarityResponse)
async def calculate_similarity(
    request: SimilarityRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant)
):
    """
    计算两个文本的相似度

    支持的方法：
    - cosine: 余弦相似度（推荐）
    - euclidean: 欧氏距离
    """
    try:
        service = EmbeddingModelService(db)

        # 加载模型
        model_path = f"/tmp/embedding_model_{tenant_id}.json"
        service.load_model(model_path)

        # 计算相似度
        similarity = service.calculate_similarity(
            text1=request.text1,
            text2=request.text2,
            method=request.method
        )

        return SimilarityResponse(
            similarity=similarity,
            method=request.method
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="模型未找到，请先训练模型"
        )
    except Exception as e:
        logger.error(f"Error calculating similarity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/similar-dishes", response_model=List[SimilarDish])
async def find_similar_dishes(
    request: FindSimilarDishesRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant)
):
    """
    查找相似菜品

    应用场景：
    - 菜品替代推荐
    - 相似菜品分析
    - 菜单优化建议
    """
    try:
        service = EmbeddingModelService(db)

        # 加载模型
        model_path = f"/tmp/embedding_model_{tenant_id}.json"
        service.load_model(model_path)

        # 查找相似菜品
        similar_dishes = service.find_similar_dishes(
            dish_name=request.dish_name,
            top_k=request.top_k,
            tenant_id=tenant_id
        )

        return [SimilarDish(**dish) for dish in similar_dishes]

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="模型未找到，请先训练模型"
        )
    except Exception as e:
        logger.error(f"Error finding similar dishes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recommend", response_model=List[RecommendedDish])
async def recommend_dishes(
    request: RecommendDishesRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant)
):
    """
    基于订单推荐菜品

    推荐逻辑：
    1. 计算订单菜品的平均嵌入
    2. 查找与平均嵌入最相似的菜品
    3. 排除已点菜品
    4. 返回 top_k 推荐

    应用场景：
    - 点餐推荐
    - 套餐组合建议
    - 交叉销售
    """
    try:
        service = EmbeddingModelService(db)

        # 加载模型
        model_path = f"/tmp/embedding_model_{tenant_id}.json"
        service.load_model(model_path)

        # 推荐菜品
        recommendations = service.recommend_dishes_by_order(
            order_dish_names=request.order_dish_names,
            top_k=request.top_k,
            tenant_id=tenant_id
        )

        return [RecommendedDish(**dish) for dish in recommendations]

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="模型未找到，请先训练模型"
        )
    except Exception as e:
        logger.error(f"Error recommending dishes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/embedding", response_model=EmbeddingResponse)
async def get_embedding(
    request: EmbeddingRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant)
):
    """
    获取文本的嵌入向量

    返回：
    - embedding: 嵌入向量（浮点数列表）
    - dimension: 向量维度
    """
    try:
        service = EmbeddingModelService(db)

        # 加载模型
        model_path = f"/tmp/embedding_model_{tenant_id}.json"
        service.load_model(model_path)

        # 获取嵌入
        embedding = service.get_embedding(request.text)

        if embedding is None:
            raise HTTPException(
                status_code=400,
                detail="无法生成嵌入向量，文本可能不在词汇表中"
            )

        return EmbeddingResponse(
            embedding=embedding.tolist(),
            dimension=len(embedding)
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="模型未找到，请先训练模型"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting embedding: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/model/status")
async def get_model_status(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant)
):
    """
    获取模型状态

    返回：
    - exists: 模型是否存在
    - vocab_size: 词汇表大小
    - embedding_dim: 嵌入维度
    - created_at: 创建时间
    """
    try:
        import os
        import json

        model_path = f"/tmp/embedding_model_{tenant_id}.json"

        if not os.path.exists(model_path):
            return {
                "exists": False,
                "message": "模型未训练"
            }

        # 读取模型元数据
        with open(model_path, 'r') as f:
            model_data = json.load(f)

        return {
            "exists": True,
            "vocab_size": len(model_data["vocab"]),
            "embedding_dim": model_data["embedding_dim"],
            "created_at": model_data["created_at"]
        }

    except Exception as e:
        logger.error(f"Error getting model status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
