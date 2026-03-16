"""
Food Safety Models — 食品安全追溯
食材溯源记录 + 食品安全检查记录
"""

import uuid

from sqlalchemy import Column, Date, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID

from .base import Base, TimestampMixin


class FoodTraceRecord(Base, TimestampMixin):
    """
    食材溯源记录。
    记录每批食材的来源、批次、保质期、检验信息。
    """

    __tablename__ = "food_trace_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)

    # 食材信息
    ingredient_name = Column(String(100), nullable=False)
    ingredient_id = Column(String(50), nullable=True)  # 关联 IngredientMaster

    # 批次
    batch_number = Column(String(50), nullable=False)

    # 供应商
    supplier_name = Column(String(100), nullable=False)
    supplier_id = Column(String(50), nullable=True)

    # 日期
    production_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)
    receive_date = Column(Date, nullable=False)  # 收货日期

    # 数量
    quantity = Column(Numeric(10, 2), nullable=False)
    unit = Column(String(20), nullable=False)  # kg / 箱 / 份

    # 来源与认证
    origin = Column(String(200), nullable=True)  # 产地
    certificate_url = Column(String(500), nullable=True)  # 检验证书URL
    qr_code = Column(String(200), nullable=True)  # 追溯码

    # 收货温度（冷链管控）
    temperature_on_receive = Column(Numeric(5, 2), nullable=True)

    # 状态: normal / warning / recalled / expired
    status = Column(String(20), nullable=False, default="normal", index=True)

    notes = Column(Text, nullable=True)


class FoodSafetyInspection(Base, TimestampMixin):
    """
    食品安全检查记录。
    支持日常/周检/月检/政府/第三方多种检查类型。
    """

    __tablename__ = "food_safety_inspections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)

    # 检查类型: daily / weekly / monthly / government / third_party
    inspection_type = Column(String(30), nullable=False)

    inspector_name = Column(String(50), nullable=False)
    inspection_date = Column(Date, nullable=False)

    # 评分 0-100
    score = Column(Integer, nullable=True)

    # 状态: passed / failed / pending / needs_improvement
    status = Column(String(20), nullable=False, default="pending")

    # 检查项明细 [{item, result, notes}]
    items = Column(JSON, nullable=False, default=list)

    # 照片 [url strings]
    photos = Column(JSON, nullable=True)

    # 整改措施
    corrective_actions = Column(Text, nullable=True)

    # 下次检查日期
    next_inspection_date = Column(Date, nullable=True)
