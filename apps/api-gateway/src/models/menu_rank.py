"""
FEAT-004: 动态菜单权重引擎 — 数据模型

5因子评分：趋势30%、毛利25%、库存20%、时段匹配15%、低退单10%
"""
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class DishScore(BaseModel):
    """菜品5因子评分"""
    dish_id: str
    dish_name: str

    # 各因子原始分（0.0-1.0）
    trend_score: float = Field(0.0, ge=0, le=1, description="趋势得分（30%权重）")
    margin_score: float = Field(0.0, ge=0, le=1, description="毛利得分（25%权重）")
    stock_score: float = Field(0.0, ge=0, le=1, description="库存得分（20%权重）")
    time_slot_score: float = Field(0.0, ge=0, le=1, description="时段匹配得分（15%权重）")
    low_refund_score: float = Field(0.0, ge=0, le=1, description="低退单得分（10%权重）")

    # 综合加权总分（0.0-1.0）
    total_score: float = Field(0.0, ge=0, le=1, description="加权综合总分")

    def compute_total(self) -> "DishScore":
        """计算加权综合总分"""
        self.total_score = round(
            self.trend_score * 0.30
            + self.margin_score * 0.25
            + self.stock_score * 0.20
            + self.time_slot_score * 0.15
            + self.low_refund_score * 0.10,
            4,
        )
        return self


class RankedDish(BaseModel):
    """排名后的菜品推荐"""
    rank: int = Field(..., ge=1, description="推荐排名（从1开始）")
    dish_id: str
    dish_name: str
    category: Optional[str] = None
    image_url: Optional[str] = None
    price: Optional[Decimal] = None
    score: DishScore
    highlight: Optional[str] = None    # 推荐理由（如"今日销量上升20%"）

    class Config:
        json_encoders = {Decimal: float}
