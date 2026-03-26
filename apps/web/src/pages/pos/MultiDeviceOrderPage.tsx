/**
 * 多端点单管理 — 设备注册/购物车同步/菜单适配
 *
 * 功能：
 *  - 设备注册与会话管理
 *  - 多端共享购物车状态
 *  - 设备能力矩阵展示
 *  - 实时同步状态监控
 *  - 离线缓冲管理
 */

import React, { useState } from 'react';
import {
  Row, Col, Card, Table, Tag, Space, Typography, Badge, Tabs,
  Statistic, List, Descriptions, Progress, Button, Empty, Timeline,
} from 'antd';
import {
  MobileOutlined, TabletOutlined, DesktopOutlined, ApiOutlined,
  SyncOutlined, WifiOutlined, DisconnectOutlined, ShoppingCartOutlined,
  TeamOutlined, CheckCircleOutlined, ClockCircleOutlined,
} from '@ant-design/icons';

const { Title, Text } = Typography;

// ── 类型定义 ──────────────────────────────────────────────────────────────────

interface DeviceSession {
  session_id: string;
  device_id: string;
  device_type: string;
  device_role: string;
  table_code: string | null;
  capabilities: string[];
  is_active: boolean;
  last_activity: string;
  offline_buffer_size: number;
}

interface SharedCart {
  table_code: string;
  items: CartItem[];
  version: number;
  contributors: string[];
}

interface CartItem {
  dish_name: string;
  quantity: number;
  unit_price_fen: number;
  added_by: string;
}

// ── 设备图标映射 ──────────────────────────────────────────────────────────────

const DEVICE_ICONS: Record<string, React.ReactNode> = {
  mini_program: <MobileOutlined style={{ color: '#07c160' }} />,
  mobile: <MobileOutlined style={{ color: '#1890ff' }} />,
  tablet: <TabletOutlined style={{ color: '#722ed1' }} />,
  tv: <DesktopOutlined style={{ color: '#fa541c' }} />,
  touch_screen: <DesktopOutlined style={{ color: '#13c2c2' }} />,
  pos_terminal: <DesktopOutlined style={{ color: '#333' }} />,
  kds_screen: <DesktopOutlined style={{ color: '#fa8c16' }} />,
};

const DEVICE_LABELS: Record<string, string> = {
  mini_program: '小程序',
  mobile: '手机',
  tablet: '平板',
  tv: '电视',
  touch_screen: '触摸屏',
  pos_terminal: 'POS终端',
  kds_screen: 'KDS屏',
};

const ROLE_LABELS: Record<string, string> = {
  customer_self: '顾客自助',
  waiter: '服务员',
  cashier: '收银员',
  kitchen: '厨房',
  manager: '管理员',
  display: '展示',
};

const CAPABILITY_LABELS: Record<string, { label: string; color: string }> = {
  full_menu: { label: '完整菜单', color: 'blue' },
  compact_menu: { label: '精简菜单', color: 'cyan' },
  order_create: { label: '下单', color: 'green' },
  order_modify: { label: '改单', color: 'orange' },
  payment: { label: '收款', color: 'gold' },
  kitchen_view: { label: '厨房视图', color: 'red' },
  weight_input: { label: '称重', color: 'purple' },
  qr_scan: { label: '扫码', color: 'magenta' },
};

// ── 示例数据 ──────────────────────────────────────────────────────────────────

const MOCK_SESSIONS: DeviceSession[] = [
  {
    session_id: 'S001', device_id: 'POS-001', device_type: 'pos_terminal',
    device_role: 'cashier', table_code: null,
    capabilities: ['full_menu', 'order_create', 'order_modify', 'payment', 'weight_input', 'qr_scan'],
    is_active: true, last_activity: '2026-03-26T10:30:00', offline_buffer_size: 0,
  },
  {
    session_id: 'S002', device_id: 'TABLET-A01', device_type: 'tablet',
    device_role: 'customer_self', table_code: 'A01',
    capabilities: ['full_menu', 'order_create', 'order_modify', 'weight_input'],
    is_active: true, last_activity: '2026-03-26T10:28:00', offline_buffer_size: 0,
  },
  {
    session_id: 'S003', device_id: 'MINI-WX-001', device_type: 'mini_program',
    device_role: 'customer_self', table_code: 'A01',
    capabilities: ['compact_menu', 'order_create', 'qr_scan'],
    is_active: true, last_activity: '2026-03-26T10:29:00', offline_buffer_size: 0,
  },
  {
    session_id: 'S004', device_id: 'PHONE-W01', device_type: 'mobile',
    device_role: 'waiter', table_code: null,
    capabilities: ['compact_menu', 'order_create', 'order_modify', 'qr_scan'],
    is_active: true, last_activity: '2026-03-26T10:25:00', offline_buffer_size: 0,
  },
  {
    session_id: 'S005', device_id: 'TV-LOBBY', device_type: 'tv',
    device_role: 'display', table_code: null,
    capabilities: ['full_menu'],
    is_active: true, last_activity: '2026-03-26T10:30:00', offline_buffer_size: 0,
  },
  {
    session_id: 'S006', device_id: 'KDS-HOT-WOK', device_type: 'kds_screen',
    device_role: 'kitchen', table_code: null,
    capabilities: ['kitchen_view'],
    is_active: true, last_activity: '2026-03-26T10:30:00', offline_buffer_size: 0,
  },
  {
    session_id: 'S007', device_id: 'TOUCH-SELF-01', device_type: 'touch_screen',
    device_role: 'customer_self', table_code: null,
    capabilities: ['full_menu', 'order_create', 'payment', 'qr_scan'],
    is_active: true, last_activity: '2026-03-26T10:27:00', offline_buffer_size: 0,
  },
  {
    session_id: 'S008', device_id: 'PHONE-W02', device_type: 'mobile',
    device_role: 'waiter', table_code: 'B03',
    capabilities: ['compact_menu', 'order_create', 'order_modify', 'qr_scan'],
    is_active: false, last_activity: '2026-03-26T09:45:00', offline_buffer_size: 3,
  },
];

const MOCK_CARTS: SharedCart[] = [
  {
    table_code: 'A01', version: 5, contributors: ['S002', 'S003'],
    items: [
      { dish_name: '小炒黄牛肉', quantity: 1, unit_price_fen: 5800, added_by: 'S002' },
      { dish_name: '剁椒鱼头', quantity: 1, unit_price_fen: 8800, added_by: 'S003' },
      { dish_name: '凉拌木耳', quantity: 2, unit_price_fen: 1800, added_by: 'S002' },
    ],
  },
  {
    table_code: 'B03', version: 2, contributors: ['S008'],
    items: [
      { dish_name: '东星斑(清蒸)', quantity: 1, unit_price_fen: 28800, added_by: 'S008' },
    ],
  },
];

// ── 主组件 ────────────────────────────────────────────────────────────────────

const MultiDeviceOrderPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('devices');

  const activeSessions = MOCK_SESSIONS.filter(s => s.is_active);
  const offlineSessions = MOCK_SESSIONS.filter(s => !s.is_active);

  const deviceColumns = [
    {
      title: '设备',
      key: 'device',
      render: (_: unknown, r: DeviceSession) => (
        <Space>
          {DEVICE_ICONS[r.device_type]}
          <div>
            <Text strong>{r.device_id}</Text>
            <br />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {DEVICE_LABELS[r.device_type]} · {ROLE_LABELS[r.device_role]}
            </Text>
          </div>
        </Space>
      ),
    },
    {
      title: '桌号',
      dataIndex: 'table_code',
      key: 'table',
      render: (v: string | null) => v ? <Tag color="blue">{v}</Tag> : <Text type="secondary">-</Text>,
    },
    {
      title: '能力',
      key: 'capabilities',
      render: (_: unknown, r: DeviceSession) => (
        <Space size={2} wrap>
          {r.capabilities.map(c => {
            const cap = CAPABILITY_LABELS[c];
            return cap ? <Tag key={c} color={cap.color} style={{ fontSize: 10 }}>{cap.label}</Tag> : null;
          })}
        </Space>
      ),
    },
    {
      title: '状态',
      key: 'status',
      width: 80,
      render: (_: unknown, r: DeviceSession) => (
        r.is_active
          ? <Badge status="success" text="在线" />
          : <Badge status="error" text={`离线(${r.offline_buffer_size})`} />
      ),
    },
  ];

  return (
    <div style={{ padding: 16 }}>
      <Title level={4}>多端混合点单管理</Title>

      {/* 概览统计 */}
      <Row gutter={12} style={{ marginBottom: 16 }}>
        <Col span={4}>
          <Card size="small">
            <Statistic title="在线设备" value={activeSessions.length} suffix={`/ ${MOCK_SESSIONS.length}`} valueStyle={{ color: '#52c41a' }} prefix={<WifiOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="活跃桌台" value={MOCK_CARTS.length} valueStyle={{ color: '#1890ff' }} prefix={<ShoppingCartOutlined />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="小程序" value={MOCK_SESSIONS.filter(s => s.device_type === 'mini_program' && s.is_active).length} prefix={DEVICE_ICONS.mini_program} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="平板" value={MOCK_SESSIONS.filter(s => s.device_type === 'tablet' && s.is_active).length} prefix={DEVICE_ICONS.tablet} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="触摸屏" value={MOCK_SESSIONS.filter(s => s.device_type === 'touch_screen' && s.is_active).length} prefix={DEVICE_ICONS.touch_screen} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="离线缓冲" value={MOCK_SESSIONS.reduce((s, d) => s + d.offline_buffer_size, 0)} valueStyle={{ color: offlineSessions.length > 0 ? '#fa8c16' : '#52c41a' }} prefix={<DisconnectOutlined />} />
          </Card>
        </Col>
      </Row>

      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        {/* 设备列表 */}
        <Tabs.TabPane tab={<><ApiOutlined /> 设备管理</>} key="devices">
          <Table
            dataSource={MOCK_SESSIONS}
            columns={deviceColumns}
            rowKey="session_id"
            size="small"
            pagination={false}
          />
        </Tabs.TabPane>

        {/* 共享购物车 */}
        <Tabs.TabPane tab={<><ShoppingCartOutlined /> 共享购物车</>} key="carts">
          <Row gutter={12}>
            {MOCK_CARTS.map(cart => (
              <Col key={cart.table_code} xs={24} md={12}>
                <Card
                  title={
                    <Space>
                      <Tag color="blue" style={{ fontSize: 14 }}>{cart.table_code}</Tag>
                      <Text type="secondary">v{cart.version}</Text>
                      <Text type="secondary">
                        {cart.contributors.length} 台设备协同
                      </Text>
                    </Space>
                  }
                  size="small"
                >
                  <List
                    dataSource={cart.items}
                    renderItem={item => (
                      <List.Item>
                        <List.Item.Meta
                          title={<><Text strong>{item.dish_name}</Text> ×{item.quantity}</>}
                          description={`来自 ${item.added_by}`}
                        />
                        <Text style={{ color: '#ff6b2c', fontWeight: 600 }}>
                          ¥{(item.unit_price_fen * item.quantity / 100).toFixed(2)}
                        </Text>
                      </List.Item>
                    )}
                  />
                  <div style={{ textAlign: 'right', borderTop: '1px solid #f0f0f0', paddingTop: 8 }}>
                    <Text style={{ fontSize: 16, fontWeight: 700, color: '#ff6b2c' }}>
                      合计: ¥{(cart.items.reduce((s, i) => s + i.unit_price_fen * i.quantity, 0) / 100).toFixed(2)}
                    </Text>
                  </div>
                </Card>
              </Col>
            ))}
          </Row>
        </Tabs.TabPane>

        {/* 能力矩阵 */}
        <Tabs.TabPane tab={<><TeamOutlined /> 能力矩阵</>} key="matrix">
          <Card size="small">
            <Table
              dataSource={Object.entries(DEVICE_LABELS).map(([key, label]) => ({
                key,
                label,
                ...Object.fromEntries(
                  Object.keys(CAPABILITY_LABELS).map(cap => [
                    cap,
                    MOCK_SESSIONS.find(s => s.device_type === key)?.capabilities.includes(cap) || false,
                  ]),
                ),
              }))}
              columns={[
                { title: '设备类型', dataIndex: 'label', key: 'label', fixed: 'left', width: 100 },
                ...Object.entries(CAPABILITY_LABELS).map(([key, config]) => ({
                  title: config.label,
                  dataIndex: key,
                  key,
                  width: 80,
                  align: 'center' as const,
                  render: (v: boolean) => v ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <Text type="secondary">-</Text>,
                })),
              ]}
              size="small"
              pagination={false}
              rowKey="key"
            />
          </Card>
        </Tabs.TabPane>

        {/* 影子同步 */}
        <Tabs.TabPane tab={<><SyncOutlined /> 影子同步</>} key="shadow">
          <Row gutter={12}>
            <Col span={12}>
              <Card title="同步状态" size="small">
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="同步模式">
                    <Tag color="processing" icon={<SyncOutlined spin />}>影子双写</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="天财商龙连接">
                    <Badge status="success" text="已连接" />
                  </Descriptions.Item>
                  <Descriptions.Item label="今日同步">1,247 笔</Descriptions.Item>
                  <Descriptions.Item label="一致性">
                    <Progress percent={99.8} size="small" status="active" />
                  </Descriptions.Item>
                  <Descriptions.Item label="连续通过">18 天 / 30 天</Descriptions.Item>
                </Descriptions>
              </Card>
            </Col>
            <Col span={12}>
              <Card title="最近同步事件" size="small">
                <Timeline
                  items={[
                    { color: 'green', children: '10:30 订单 DI20260326042 同步成功' },
                    { color: 'green', children: '10:28 会员消费 M10086 同步成功' },
                    { color: 'green', children: '10:25 厨打票 T005 同步成功' },
                    { color: 'orange', children: '10:20 券核销 MT20260326001 差异 ¥0.01' },
                    { color: 'green', children: '10:15 桌台状态同步 12桌' },
                  ]}
                />
              </Card>
            </Col>
          </Row>
        </Tabs.TabPane>
      </Tabs>
    </div>
  );
};

export default MultiDeviceOrderPage;
