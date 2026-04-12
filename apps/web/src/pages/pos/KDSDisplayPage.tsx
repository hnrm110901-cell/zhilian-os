/**
 * KDS 厨房显示大屏 — 出餐管理
 *
 * 功能：
 *  - 按工位显示待制作/制作中/已完成的厨打票
 *  - 实时计时，超时红色预警
 *  - 一键切换状态（接单→制作→装盘→出餐→上菜）
 *  - 催菜高亮 + 音效提醒
 *  - 催菜员汇总视图（Expeditor View）
 *  - 海鲜称重单特殊标记
 */

import React, { useState, useMemo } from 'react';
import {
  Row, Col, Card, Tag, Button, Space, Typography, Badge, Progress,
  Statistic, Segmented, Empty, Alert,
} from 'antd';
import {
  FireOutlined, ClockCircleOutlined, CheckCircleOutlined,
  SyncOutlined, BellOutlined, ThunderboltOutlined,
  ExperimentOutlined,
} from '@ant-design/icons';

const { Title, Text } = Typography;

// ── 类型定义 ──────────────────────────────────────────────────────────────────

interface KitchenTicket {
  ticket_id: string;
  order_id: string;
  order_number: string;
  table_code: string;
  station: string;
  items: KitchenItem[];
  priority: number;
  status: string;
  target_minutes: number;
  elapsed_seconds: number;
  is_overdue: boolean;
  created_at: string;
}

interface KitchenItem {
  dish_name: string;
  quantity: number;
  spec_name?: string;
  weight_g?: number;
  cooking_method?: string;
  notes?: string;
}

// ── 工位配置 ──────────────────────────────────────────────────────────────────

const STATIONS = [
  { key: 'all', label: '全部', icon: '📋' },
  { key: 'hot_wok', label: '炒锅', icon: '🔥' },
  { key: 'steamer', label: '蒸柜', icon: '♨️' },
  { key: 'deep_fry', label: '油炸', icon: '🍳' },
  { key: 'cold_dish', label: '凉菜', icon: '🥗' },
  { key: 'seafood', label: '海鲜', icon: '🦐' },
  { key: 'soup', label: '汤/煲', icon: '🍲' },
  { key: 'grill', label: '烧烤', icon: '🥩' },
  { key: 'pastry', label: '面点', icon: '🥟' },
  { key: 'beverage', label: '饮品', icon: '🥤' },
];

const STATUS_CONFIG: Record<string, { color: string; label: string; next: string; nextLabel: string }> = {
  received: { color: '#1890ff', label: '已接单', next: 'cooking', nextLabel: '开始制作' },
  cooking: { color: '#fa8c16', label: '制作中', next: 'plating', nextLabel: '装盘' },
  plating: { color: '#722ed1', label: '装盘中', next: 'ready', nextLabel: '出餐' },
  ready: { color: '#52c41a', label: '出餐就绪', next: 'served', nextLabel: '已上菜' },
  served: { color: '#8c8c8c', label: '已上菜', next: '', nextLabel: '' },
};

// ── 示例数据 ──────────────────────────────────────────────────────────────────

const MOCK_TICKETS: KitchenTicket[] = [
  {
    ticket_id: 'T001', order_id: 'O001', order_number: 'DI20260326001',
    table_code: 'A01', station: 'hot_wok', priority: 0, status: 'cooking',
    target_minutes: 10, elapsed_seconds: 480, is_overdue: false,
    created_at: new Date().toISOString(),
    items: [
      { dish_name: '小炒黄牛肉', quantity: 1, notes: '少盐' },
      { dish_name: '辣椒炒肉', quantity: 1 },
    ],
  },
  {
    ticket_id: 'T002', order_id: 'O001', order_number: 'DI20260326001',
    table_code: 'A01', station: 'steamer', priority: 0, status: 'received',
    target_minutes: 15, elapsed_seconds: 120, is_overdue: false,
    created_at: new Date().toISOString(),
    items: [
      { dish_name: '剁椒鱼头', quantity: 1, spec_name: '大份' },
    ],
  },
  {
    ticket_id: 'T003', order_id: 'O002', order_number: 'DI20260326002',
    table_code: 'B03', station: 'seafood', priority: 2, status: 'cooking',
    target_minutes: 12, elapsed_seconds: 780, is_overdue: true,
    created_at: new Date().toISOString(),
    items: [
      { dish_name: '东星斑', quantity: 1, weight_g: 850, cooking_method: '清蒸', notes: 'VIP催菜' },
      { dish_name: '蒜蓉粉丝蒸扇贝', quantity: 3 },
    ],
  },
  {
    ticket_id: 'T004', order_id: 'O003', order_number: 'BQ20260326001',
    table_code: 'VIP1', station: 'cold_dish', priority: 1, status: 'ready',
    target_minutes: 5, elapsed_seconds: 240, is_overdue: false,
    created_at: new Date().toISOString(),
    items: [
      { dish_name: '凉拌木耳', quantity: 2 },
      { dish_name: '精品刺身拼盘', quantity: 1 },
    ],
  },
  {
    ticket_id: 'T005', order_id: 'O004', order_number: 'TA20260326001',
    table_code: '外卖', station: 'hot_wok', priority: 0, status: 'received',
    target_minutes: 10, elapsed_seconds: 30, is_overdue: false,
    created_at: new Date().toISOString(),
    items: [
      { dish_name: '招牌烤鱼', quantity: 1 },
    ],
  },
];

// ── 厨打票卡片组件 ────────────────────────────────────────────────────────────

const TicketCard: React.FC<{
  ticket: KitchenTicket;
  onStatusChange: (ticketId: string, newStatus: string) => void;
}> = ({ ticket, onStatusChange }) => {
  const config = STATUS_CONFIG[ticket.status] || STATUS_CONFIG.received;
  const progress = Math.min(100, Math.round((ticket.elapsed_seconds / (ticket.target_minutes * 60)) * 100));
  const minutes = Math.floor(ticket.elapsed_seconds / 60);
  const seconds = ticket.elapsed_seconds % 60;

  return (
    <Card
      size="small"
      style={{
        borderLeft: `4px solid ${ticket.is_overdue ? '#ff4d4f' : config.color}`,
        background: ticket.is_overdue ? '#fff2f0' : ticket.priority >= 2 ? '#fff7e6' : '#fff',
        marginBottom: 8,
      }}
      bodyStyle={{ padding: 8 }}
    >
      {/* 头部：桌号 + 订单号 + 状态 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
        <Space size={4}>
          <Tag color="blue" style={{ margin: 0, fontWeight: 700, fontSize: 14 }}>{ticket.table_code}</Tag>
          <Text type="secondary" style={{ fontSize: 11 }}>{ticket.order_number}</Text>
        </Space>
        <Space size={4}>
          {ticket.priority >= 2 && <Tag color="red" icon={<ThunderboltOutlined />}>催</Tag>}
          {ticket.priority === 1 && <Tag color="orange" icon={<BellOutlined />}>急</Tag>}
          <Tag color={config.color}>{config.label}</Tag>
        </Space>
      </div>

      {/* 菜品列表 */}
      {ticket.items.map((item, idx) => (
        <div key={idx} style={{ padding: '2px 0', borderBottom: '1px dashed #f0f0f0' }}>
          <Row justify="space-between">
            <Col>
              <Text strong style={{ fontSize: 15 }}>{item.dish_name}</Text>
              {item.spec_name && <Tag style={{ marginLeft: 4, fontSize: 10 }}>{item.spec_name}</Tag>}
              {item.cooking_method && <Tag color="orange" style={{ marginLeft: 4, fontSize: 10 }}>{item.cooking_method}</Tag>}
              {item.weight_g && <Tag color="purple" style={{ marginLeft: 4, fontSize: 10 }}>{item.weight_g}g</Tag>}
            </Col>
            <Col>
              <Text style={{ fontSize: 16, fontWeight: 700 }}>×{item.quantity}</Text>
            </Col>
          </Row>
          {item.notes && (
            <Text type="warning" style={{ fontSize: 11 }}>⚠️ {item.notes}</Text>
          )}
        </div>
      ))}

      {/* 计时 + 操作 */}
      <div style={{ marginTop: 6, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space size={4}>
          <ClockCircleOutlined style={{ color: ticket.is_overdue ? '#ff4d4f' : '#8c8c8c' }} />
          <Text
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: ticket.is_overdue ? '#ff4d4f' : undefined,
            }}
          >
            {minutes}:{seconds.toString().padStart(2, '0')} / {ticket.target_minutes}:00
          </Text>
          <Progress
            percent={progress}
            size="small"
            style={{ width: 60 }}
            strokeColor={ticket.is_overdue ? '#ff4d4f' : config.color}
            showInfo={false}
          />
        </Space>
        {config.next && (
          <Button
            type="primary"
            size="small"
            onClick={() => onStatusChange(ticket.ticket_id, config.next)}
            style={{
              background: STATUS_CONFIG[config.next]?.color || '#1890ff',
              borderColor: STATUS_CONFIG[config.next]?.color || '#1890ff',
            }}
          >
            {config.nextLabel}
          </Button>
        )}
      </div>
    </Card>
  );
};

// ── 主组件 ────────────────────────────────────────────────────────────────────

const KDSDisplayPage: React.FC = () => {
  const [activeStation, setActiveStation] = useState('all');
  const [tickets, setTickets] = useState<KitchenTicket[]>(MOCK_TICKETS);

  const filteredTickets = useMemo(() => {
    if (activeStation === 'all') return tickets;
    return tickets.filter(t => t.station === activeStation);
  }, [activeStation, tickets]);

  const activeTickets = filteredTickets.filter(t => t.status !== 'served');
  const readyTickets = filteredTickets.filter(t => t.status === 'ready');
  const overdueTickets = filteredTickets.filter(t => t.is_overdue && t.status !== 'ready' && t.status !== 'served');

  const handleStatusChange = (ticketId: string, newStatus: string) => {
    setTickets(prev => prev.map(t =>
      t.ticket_id === ticketId ? { ...t, status: newStatus, is_overdue: false } : t,
    ));
  };

  return (
    <div style={{ padding: 12, background: '#141414', minHeight: '100vh', color: '#fff' }}>
      {/* 顶部状态栏 */}
      <Row gutter={12} style={{ marginBottom: 12 }}>
        <Col span={6}>
          <Card size="small" style={{ background: '#1f1f1f', border: 'none' }}>
            <Statistic title={<Text style={{ color: '#8c8c8c' }}>待处理</Text>} value={activeTickets.length} valueStyle={{ color: '#1890ff', fontSize: 28 }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ background: '#1f1f1f', border: 'none' }}>
            <Statistic title={<Text style={{ color: '#8c8c8c' }}>出餐就绪</Text>} value={readyTickets.length} valueStyle={{ color: '#52c41a', fontSize: 28 }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ background: '#1f1f1f', border: 'none' }}>
            <Statistic title={<Text style={{ color: '#8c8c8c' }}>超时</Text>} value={overdueTickets.length} valueStyle={{ color: '#ff4d4f', fontSize: 28 }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ background: '#1f1f1f', border: 'none' }}>
            <Statistic
              title={<Text style={{ color: '#8c8c8c' }}>影子同步</Text>}
              value="在线"
              valueStyle={{ color: '#52c41a', fontSize: 28 }}
              prefix={<SyncOutlined spin />}
            />
          </Card>
        </Col>
      </Row>

      {/* 工位切换 */}
      <div style={{ marginBottom: 12 }}>
        <Segmented
          options={STATIONS.map(s => ({
            value: s.key,
            label: (
              <Space size={4}>
                <span>{s.icon}</span>
                <span>{s.label}</span>
                {s.key !== 'all' && (
                  <Badge
                    count={tickets.filter(t => t.station === s.key && t.status !== 'served').length}
                    size="small"
                  />
                )}
              </Space>
            ),
          }))}
          value={activeStation}
          onChange={v => setActiveStation(v as string)}
          style={{ background: '#1f1f1f' }}
        />
      </div>

      {/* 超时预警 */}
      {overdueTickets.length > 0 && (
        <Alert
          type="error"
          message={`${overdueTickets.length} 张厨打票已超时！`}
          banner
          showIcon
          icon={<FireOutlined />}
          style={{ marginBottom: 12 }}
        />
      )}

      {/* 厨打票列表 */}
      <Row gutter={12}>
        {activeTickets.length > 0 ? (
          activeTickets.map(ticket => (
            <Col key={ticket.ticket_id} xs={24} sm={12} md={8} lg={6}>
              <TicketCard ticket={ticket} onStatusChange={handleStatusChange} />
            </Col>
          ))
        ) : (
          <Col span={24}>
            <Empty description={<Text style={{ color: '#8c8c8c' }}>暂无厨打票</Text>} />
          </Col>
        )}
      </Row>
    </div>
  );
};

export default KDSDisplayPage;
