"""
e01: 新增运维监控四张表
  - ops_device_readings      (IoT设备时序读数)
  - ops_network_health       (网络探针结果)
  - ops_sys_health_checks    (业务系统心跳)
  - ops_food_safety_records  (食安合规记录)

Revision ID: e01_ops_monitoring
Revises: d01_member_birth_date
Create Date: 2026-03-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'e01_ops_monitoring'
down_revision = 'd01_member_birth_date'
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. ops_device_readings ────────────────────────────────────────────────
    op.create_table(
        'ops_device_readings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('asset_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('ops_assets.id'), nullable=True,
                  comment='关联资产台账（可为空，用于尚未登记的设备）'),
        sa.Column('device_name', sa.String(100), nullable=False, comment='设备名称/编号'),
        sa.Column('metric_type', sa.String(50), nullable=False,
                  comment='指标类型：temperature/power/online_status/tpm/clean_days'),
        sa.Column('value_float', sa.Float(), nullable=True, comment='数值型读数'),
        sa.Column('value_bool', sa.Boolean(), nullable=True, comment='布尔型读数（在线/离线）'),
        sa.Column('unit', sa.String(20), nullable=True, comment='单位：℃/W/kWh'),
        sa.Column('is_alert', sa.Boolean(), nullable=False, server_default='false',
                  comment='是否触发告警阈值'),
        sa.Column('alert_message', sa.Text(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()'), comment='采集时间'),
    )
    op.create_index('ix_odr_store_time', 'ops_device_readings',
                    ['store_id', 'recorded_at'])
    op.create_index('ix_odr_metric', 'ops_device_readings', ['metric_type'])
    op.create_index('ix_odr_alert', 'ops_device_readings', ['is_alert'],
                    postgresql_where=sa.text('is_alert = true'))

    # ── 2. ops_network_health ─────────────────────────────────────────────────
    op.create_table(
        'ops_network_health',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('probe_type', sa.String(30), nullable=False,
                  comment='探针类型：icmp/http/dns/bandwidth/wifi/vpn'),
        sa.Column('target', sa.String(200), nullable=False,
                  comment='探测目标：IP/域名/URL'),
        sa.Column('vlan', sa.String(20), nullable=True,
                  comment='所属VLAN：vlan10/vlan20/vlan30/vlan40/vlan50/wan'),
        sa.Column('latency_ms', sa.Float(), nullable=True, comment='延迟（毫秒）'),
        sa.Column('packet_loss_pct', sa.Float(), nullable=True, comment='丢包率（%）'),
        sa.Column('bandwidth_mbps', sa.Float(), nullable=True, comment='带宽（Mbps）'),
        sa.Column('is_available', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('status_code', sa.Integer(), nullable=True, comment='HTTP状态码'),
        sa.Column('is_alert', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('alert_message', sa.Text(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )
    op.create_index('ix_onh_store_time', 'ops_network_health',
                    ['store_id', 'recorded_at'])
    op.create_index('ix_onh_probe_type', 'ops_network_health', ['probe_type'])
    op.create_index('ix_onh_alert', 'ops_network_health', ['is_alert'],
                    postgresql_where=sa.text('is_alert = true'))

    # ── 3. ops_sys_health_checks ──────────────────────────────────────────────
    op.create_table(
        'ops_sys_health_checks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('system_name', sa.String(100), nullable=False,
                  comment='系统名：pos_gudao/epos_rundian/member_weisheng/wechat_work/…'),
        sa.Column('priority', sa.String(5), nullable=False, server_default='P2',
                  comment='P0/P1/P2/P3，对应文档优先级分级'),
        sa.Column('check_method', sa.String(30), nullable=False,
                  comment='检测方式：api_heartbeat/db_probe/port_check/process_check'),
        sa.Column('is_available', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('response_ms', sa.Float(), nullable=True, comment='响应时间（毫秒）'),
        sa.Column('http_status', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('is_alert', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('consecutive_failures', sa.Integer(), nullable=False,
                  server_default='0', comment='连续失败次数'),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )
    op.create_index('ix_oshc_store_time', 'ops_sys_health_checks',
                    ['store_id', 'recorded_at'])
    op.create_index('ix_oshc_system', 'ops_sys_health_checks', ['system_name'])
    op.create_index('ix_oshc_priority', 'ops_sys_health_checks', ['priority'])
    op.create_index('ix_oshc_alert', 'ops_sys_health_checks', ['is_alert'],
                    postgresql_where=sa.text('is_alert = true'))

    # ── 4. ops_food_safety_records ────────────────────────────────────────────
    op.create_table(
        'ops_food_safety_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('record_type', sa.String(30), nullable=False,
                  comment='类型：cold_chain/fridge_power/ice_machine_clean/oil_quality/safety_device'),
        sa.Column('device_name', sa.String(100), nullable=True),
        sa.Column('is_compliant', sa.Boolean(), nullable=False, server_default='true',
                  comment='是否合规'),
        sa.Column('value_float', sa.Float(), nullable=True, comment='测量值'),
        sa.Column('threshold_min', sa.Float(), nullable=True),
        sa.Column('threshold_max', sa.Float(), nullable=True),
        sa.Column('unit', sa.String(20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('requires_action', sa.Boolean(), nullable=False, server_default='false',
                  comment='是否需要立即处置'),
        sa.Column('action_taken', sa.Text(), nullable=True, comment='已采取的处置措施'),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_ofsr_store_time', 'ops_food_safety_records',
                    ['store_id', 'recorded_at'])
    op.create_index('ix_ofsr_type', 'ops_food_safety_records', ['record_type'])
    op.create_index('ix_ofsr_noncompliant', 'ops_food_safety_records',
                    ['store_id', 'is_compliant'],
                    postgresql_where=sa.text('is_compliant = false'))


def downgrade():
    op.drop_table('ops_food_safety_records')
    op.drop_table('ops_sys_health_checks')
    op.drop_table('ops_network_health')
    op.drop_table('ops_device_readings')
