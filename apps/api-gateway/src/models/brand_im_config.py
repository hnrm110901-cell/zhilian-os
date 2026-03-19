"""
Brand IM Platform Config — 品牌 IM 平台（企微/钉钉）配置
每个品牌绑定一个 IM 平台，用于通讯录同步和消息推送。
"""

import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID

from .base import Base, TimestampMixin


class IMPlatform(str, enum.Enum):
    """IM 平台类型"""

    WECHAT_WORK = "wechat_work"  # 企业微信
    DINGTALK = "dingtalk"  # 钉钉


class BrandIMConfig(Base, TimestampMixin):
    """
    品牌 IM 平台配置。
    每个品牌只绑定一个 IM 平台，所有门店共用。
    """

    __tablename__ = "brand_im_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, unique=True, index=True)

    # 平台类型
    im_platform = Column(
        SAEnum(IMPlatform, name="im_platform_enum", create_constraint=False),
        nullable=False,
    )

    # ── 企业微信配置 ──
    wechat_corp_id = Column(String(100), nullable=True)
    wechat_corp_secret = Column(String(200), nullable=True)
    wechat_agent_id = Column(String(50), nullable=True)
    wechat_token = Column(String(200), nullable=True)  # 回调验证 Token
    wechat_encoding_aes_key = Column(String(200), nullable=True)

    # ── 钉钉配置 ──
    dingtalk_app_key = Column(String(100), nullable=True)
    dingtalk_app_secret = Column(String(200), nullable=True)
    dingtalk_agent_id = Column(String(50), nullable=True)
    dingtalk_aes_key = Column(String(200), nullable=True)  # 回调加密 Key
    dingtalk_token = Column(String(200), nullable=True)  # 回调签名 Token

    # ── 同步配置 ──
    sync_enabled = Column(Boolean, default=True, nullable=False)  # 是否启用自动同步
    sync_interval_minutes = Column(Integer, default=1440)  # 自动同步间隔（默认24h）
    auto_create_user = Column(Boolean, default=True)  # 同步时自动创建系统账号
    auto_disable_user = Column(Boolean, default=True)  # 离职时自动禁用账号
    default_store_id = Column(String(50), nullable=True)  # 新员工默认门店
    department_store_mapping = Column(JSON, nullable=True)  # {"部门名": "STORE_ID", "门店A": "S001"}

    # ── 同步状态 ──
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(20), nullable=True)  # success/failed/partial
    last_sync_message = Column(Text, nullable=True)
    last_sync_stats = Column(JSON, nullable=True)  # {"added":3,"updated":1,"disabled":0}

    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<BrandIMConfig(brand='{self.brand_id}', platform='{self.im_platform}')>"


class IMSyncLog(Base, TimestampMixin):
    """
    IM 通讯录同步日志。
    每次同步（手动/定时）记录一条。
    """

    __tablename__ = "im_sync_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    im_platform = Column(String(20), nullable=False)

    # 同步结果
    trigger = Column(String(20), nullable=False)  # manual / scheduled / callback
    status = Column(String(20), nullable=False)  # success / failed / partial
    message = Column(Text, nullable=True)

    # 统计
    total_platform_members = Column(Integer, default=0)
    added_count = Column(Integer, default=0)
    updated_count = Column(Integer, default=0)
    disabled_count = Column(Integer, default=0)
    user_created_count = Column(Integer, default=0)
    user_disabled_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    errors = Column(JSON, nullable=True)  # [{"userid":"xxx","error":"..."}]

    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<IMSyncLog(brand='{self.brand_id}', status='{self.status}')>"
