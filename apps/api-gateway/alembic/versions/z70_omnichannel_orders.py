"""z70: 多渠道消费记录表 — Phase 2 外卖订单会员归因

新增：
1. CREATE TABLE omnichannel_order_records（多渠道统一消费记录）
2. 索引：consumer / brand_date / store_channel / channel
3. RLS 策略：通过 is_store_accessible() 函数实现门店级隔离

设计原则：
- external_order_no + channel 作为幂等键（UNIQUE NULLS NOT DISTINCT）
- raw_platform_data JSONB 保留原始平台数据供复查
- consumer_id 可为 NULL（匿名订单）
- 金额单位：分（amount_fen）

Revision ID: z70_omnichannel_orders
Revises: z69_group_hierarchy_upgrade
Create Date: 2026-03-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "z70_omnichannel_orders"
down_revision = "z69_group_hierarchy_upgrade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. 创建多渠道消费记录表
    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS omnichannel_order_records (
                id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                consumer_id         UUID        REFERENCES consumer_identities(id),
                brand_id            VARCHAR(50) NOT NULL,
                store_id            VARCHAR(50) NOT NULL,
                group_id            VARCHAR(50) NOT NULL,

                -- 订单信息
                channel             VARCHAR(30) NOT NULL,
                -- 渠道枚举: pos / meituan / eleme / wechat_mp / manual
                external_order_no   VARCHAR(100),
                -- 平台侧订单号（NULL 表示无平台单号，如堂食手工录入）
                amount_fen          INTEGER     NOT NULL,
                -- 实付金额（分），禁止存储负数
                item_count          INTEGER,

                order_at            TIMESTAMP   NOT NULL,
                -- 实际下单时间（非入库时间）

                -- 归因状态
                attribution_status  VARCHAR(20) NOT NULL DEFAULT 'attributed',
                -- 枚举: attributed / anonymous / failed
                attribution_method  VARCHAR(30),
                -- 归因方式: phone_match / openid_match / manual

                -- 原始数据（用于复查和审计）
                raw_platform_data   JSONB,

                created_at          TIMESTAMP   NOT NULL DEFAULT NOW(),

                -- 幂等约束：同一渠道的同一平台订单号只存一条
                -- NULLS NOT DISTINCT 确保 NULL 值也参与唯一判断
                CONSTRAINT uq_omni_channel_order
                    UNIQUE NULLS NOT DISTINCT (channel, external_order_no)
            )
            """
        )
    )

    # 2. 消费者维度索引（查询指定消费者的所有渠道订单）
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_omni_consumer
                ON omnichannel_order_records(consumer_id)
            """
        )
    )

    # 3. 品牌 + 时间维度索引（品牌营销分析）
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_omni_brand_date
                ON omnichannel_order_records(brand_id, order_at)
            """
        )
    )

    # 4. 门店 + 渠道维度索引（门店级渠道分析）
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_omni_store_channel
                ON omnichannel_order_records(store_id, channel)
            """
        )
    )

    # 5. 渠道 + 时间维度索引（全平台渠道趋势分析）
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_omni_channel
                ON omnichannel_order_records(channel, order_at)
            """
        )
    )

    # 6. 启用 RLS（行级安全）
    conn.execute(
        sa.text(
            """
            ALTER TABLE omnichannel_order_records ENABLE ROW LEVEL SECURITY
            """
        )
    )

    # 7. 创建 RLS 策略：通过 is_store_accessible() 函数实现门店级隔离
    # is_store_accessible() 由 z69 迁移创建，使用 app.current_store_ids 等 session 变量
    conn.execute(
        sa.text(
            """
            CREATE POLICY omni_isolation ON omnichannel_order_records
                USING (is_store_accessible(store_id))
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    # 删除 RLS 策略
    conn.execute(
        sa.text(
            "DROP POLICY IF EXISTS omni_isolation ON omnichannel_order_records"
        )
    )

    # 删除索引
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_omni_channel"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_omni_store_channel"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_omni_brand_date"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_omni_consumer"))

    # 删除表
    conn.execute(sa.text("DROP TABLE IF EXISTS omnichannel_order_records"))
