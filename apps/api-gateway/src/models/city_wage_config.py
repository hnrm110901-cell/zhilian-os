"""
City Wage Config — 城市最低工资与社保基数配置
支持多城市差异化薪酬计算
"""
import uuid
from sqlalchemy import Column, String, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class CityWageConfig(Base, TimestampMixin):
    """城市最低工资与社保基数标准"""
    __tablename__ = "city_wage_configs"
    __table_args__ = (
        UniqueConstraint("city", "year", name="uq_city_wage_year"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    city = Column(String(50), nullable=False, index=True)  # 长沙/西安/武汉/深圳/上海
    province = Column(String(50), nullable=True)
    year = Column(Integer, nullable=False, index=True)

    min_monthly_wage_fen = Column(Integer, nullable=False, default=0)  # 月最低工资（分）
    min_hourly_wage_fen = Column(Integer, nullable=False, default=0)  # 小时最低工资
    social_insurance_base_floor_fen = Column(Integer, nullable=False, default=0)  # 社保基数下限
    social_insurance_base_ceil_fen = Column(Integer, nullable=False, default=0)  # 社保基数上限
    housing_fund_base_floor_fen = Column(Integer, nullable=False, default=0)
    housing_fund_base_ceil_fen = Column(Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<CityWageConfig(city='{self.city}', year={self.year})>"
