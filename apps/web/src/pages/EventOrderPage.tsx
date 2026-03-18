/**
 * EO执行引擎 — Phase P3 (宴小猪能力)
 * EO单管理 · AI自动生成 · 演职人员调度 · 履约时间线 · 宴会厅展示
 */
import React, { useEffect, useState } from 'react';
import {
  Card, Row, Col, Table, Statistic, Tabs, Tag, Button, Modal, Form,
  Input, Select, InputNumber, DatePicker, Spin, Typography, Space,
  message, Timeline, Badge, Descriptions, Drawer, List, Avatar, Steps,
  Tooltip, Progress, Empty,
} from 'antd';
import {
  FileTextOutlined, TeamOutlined, EnvironmentOutlined,
  PlusOutlined, CheckCircleOutlined, ClockCircleOutlined,
  ExclamationCircleOutlined, RocketOutlined, CameraOutlined,
  SoundOutlined, PlayCircleOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';
import dayjs from 'dayjs';

const { Title, Text } = Typography;

interface EventOrder {
  id: string;
  store_id: string;
  reservation_id: string;
  event_date: string;
  version: number;
  status: string;
  party_size: number;
  estimated_budget_yuan: number;
  event_type: string;
  table_count: number;
  menu_package: string;
  service_staff_count: number;
  fulfillment_timeline: Record<string, any>;
  ai_generated: boolean;
  ai_confidence: number;
  approved_by: string | null;
  approved_at: string | null;
  generated_by: string | null;
  change_summary: string | null;
  created_at: string;
  staff?: StaffMember[];
}

interface StaffMember {
  id: string;
  event_order_id: string;
  role: string;
  staff_name: string;
  staff_phone: string | null;
  company: string | null;
  fee_yuan: number;
  confirm_status: string;
  confirmed_at: string | null;
  notes: string | null;
}

interface Hall {
  id: string;
  store_id: string;
  hall_name: string;
  description: string | null;
  capacity_min: number | null;
  capacity_max: number | null;
  table_count_max: number | null;
  area_sqm: number | null;
  ceiling_height: number | null;
  has_led_screen: boolean;
  has_stage: boolean;
  has_natural_light: boolean;
  images: string[];
  virtual_tour_url: string | null;
  price_range: string | null;
  features: string[];
  is_active: boolean;
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: 'default' },
  confirmed: { label: '已确认', color: 'blue' },
  executed: { label: '已完成', color: 'green' },
  archived: { label: '已归档', color: 'default' },
  cancelled: { label: '已取消', color: 'red' },
};

const ROLE_MAP: Record<string, { label: string; icon: React.ReactNode }> = {
  mc: { label: '司仪', icon: <SoundOutlined /> },
  photographer: { label: '摄影师', icon: <CameraOutlined /> },
  videographer: { label: '摄像师', icon: <PlayCircleOutlined /> },
  florist: { label: '花艺师', icon: '🌸' },
  lighting: { label: '灯光师', icon: '💡' },
  dj: { label: 'DJ', icon: '🎵' },
  other: { label: '其他', icon: <TeamOutlined /> },
};

const EVENT_TYPE_MAP: Record<string, string> = {
  wedding: '婚宴', birthday: '寿宴', corporate: '商务', family: '家庭聚会',
};

const TIMELINE_NODES = [
  { key: 'setup_start', label: '布场开始' },
  { key: 'guest_arrival', label: '客人到场' },
  { key: 'event_start', label: '宴会开始' },
  { key: 'event_end', label: '宴会结束' },
  { key: 'teardown_end', label: '撤场完成' },
];

export default function EventOrderPage() {
  const [loading, setLoading] = useState(true);
  const [storeId] = useState(localStorage.getItem('store_id') || '');
  const [activeTab, setActiveTab] = useState('eo-list');

  const [eoList, setEoList] = useState<EventOrder[]>([]);
  const [halls, setHalls] = useState<Hall[]>([]);

  // Drawers & Modals
  const [detailVisible, setDetailVisible] = useState(false);
  const [currentEO, setCurrentEO] = useState<EventOrder | null>(null);
  const [generateVisible, setGenerateVisible] = useState(false);
  const [generateForm] = Form.useForm();

  const fetchData = async () => {
    setLoading(true);
    try {
      const [eos, hallList] = await Promise.all([
        apiClient.get<EventOrder[]>(`/api/v1/event-orders?store_id=${storeId}`),
        apiClient.get<Hall[]>(`/api/v1/hall-showcase?store_id=${storeId}`),
      ]);
      setEoList(eos);
      setHalls(hallList);
    } catch (e: any) {
      message.error(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const handleViewDetail = async (eo: EventOrder) => {
    try {
      const detail = await apiClient.get<EventOrder>(`/api/v1/event-orders/${eo.id}`);
      setCurrentEO(detail);
      setDetailVisible(true);
    } catch {
      message.error('获取详情失败');
    }
  };

  const handleGenerate = async () => {
    try {
      const values = await generateForm.validateFields();
      await apiClient.post('/api/v1/event-orders/generate', {
        store_id: storeId,
        reservation_id: values.reservation_id,
        event_date: values.event_date.format('YYYY-MM-DD'),
        event_type: values.event_type || 'wedding',
        guest_count: values.guest_count || 100,
        table_count: values.table_count || 10,
        budget_fen: (values.budget_yuan || 0) * 100,
        special_requirements: values.special_requirements || '',
      });
      message.success('EO单已生成');
      setGenerateVisible(false);
      generateForm.resetFields();
      fetchData();
    } catch {
      message.error('生成失败');
    }
  };

  const handleConfirm = async (eoId: string) => {
    try {
      await apiClient.patch(`/api/v1/event-orders/${eoId}/confirm`, {
        approved_by: 'current_user',
      });
      message.success('EO单已确认');
      fetchData();
      if (currentEO?.id === eoId) {
        handleViewDetail({ id: eoId } as EventOrder);
      }
    } catch {
      message.error('确认失败');
    }
  };

  const handleFulfillment = async (eoId: string, node: string) => {
    try {
      await apiClient.patch(`/api/v1/event-orders/${eoId}/fulfillment`, {
        node,
        notes: `${node} 打卡`,
      });
      message.success('打卡成功');
      handleViewDetail({ id: eoId } as EventOrder);
    } catch {
      message.error('打卡失败');
    }
  };

  // ── EO 列表列 ──
  const eoColumns = [
    {
      title: '宴会日期',
      dataIndex: 'event_date',
      key: 'date',
      render: (v: string) => v || '-',
      sorter: (a: EventOrder, b: EventOrder) => (a.event_date || '').localeCompare(b.event_date || ''),
    },
    {
      title: '类型',
      dataIndex: 'event_type',
      key: 'type',
      render: (v: string) => <Tag>{EVENT_TYPE_MAP[v] || v}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (v: string) => {
        const s = STATUS_MAP[v] || { label: v, color: 'default' };
        return <Tag color={s.color}>{s.label}</Tag>;
      },
      filters: Object.entries(STATUS_MAP).map(([k, v]) => ({ text: v.label, value: k })),
      onFilter: (value: any, record: EventOrder) => record.status === value,
    },
    {
      title: '人数',
      dataIndex: 'party_size',
      key: 'size',
      render: (v: number) => v ? `${v}人` : '-',
    },
    {
      title: '桌数',
      dataIndex: 'table_count',
      key: 'tables',
      render: (v: number) => v ? `${v}桌` : '-',
    },
    {
      title: '预算',
      dataIndex: 'estimated_budget_yuan',
      key: 'budget',
      render: (v: number) => v > 0 ? <Text strong>¥{v.toFixed(0)}</Text> : '-',
    },
    {
      title: 'AI',
      dataIndex: 'ai_generated',
      key: 'ai',
      render: (v: boolean, r: EventOrder) => v ? (
        <Tooltip title={`AI置信度 ${Math.round(r.ai_confidence * 100)}%`}>
          <Tag color="purple">AI生成</Tag>
        </Tooltip>
      ) : null,
    },
    {
      title: '版本',
      dataIndex: 'version',
      key: 'ver',
      render: (v: number) => `v${v}`,
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, r: EventOrder) => (
        <Space>
          <Button size="small" type="link" onClick={() => handleViewDetail(r)}>详情</Button>
          {r.status === 'draft' && (
            <Button size="small" type="link" onClick={() => handleConfirm(r.id)}>确认</Button>
          )}
        </Space>
      ),
    },
  ];

  // ── 统计 ──
  const draftCount = eoList.filter(e => e.status === 'draft').length;
  const confirmedCount = eoList.filter(e => e.status === 'confirmed').length;
  const executedCount = eoList.filter(e => e.status === 'executed').length;

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>
          <FileTextOutlined /> EO执行引擎
        </Title>
        <Button type="primary" icon={<RocketOutlined />} onClick={() => setGenerateVisible(true)}>
          AI生成EO单
        </Button>
      </div>

      <Spin spinning={loading}>
        {/* 统计卡片 */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card size="small">
              <Statistic title="待确认" value={draftCount} suffix="单" valueStyle={{ color: '#faad14' }} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="执行中" value={confirmedCount} suffix="单" valueStyle={{ color: '#1890ff' }} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="已完成" value={executedCount} suffix="单" valueStyle={{ color: '#52c41a' }} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="宴会厅" value={halls.length} suffix="个" prefix={<EnvironmentOutlined />} />
            </Card>
          </Col>
        </Row>

        <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
          {
            key: 'eo-list',
            label: `EO单 (${eoList.length})`,
            children: (
              <Table
                dataSource={eoList}
                columns={eoColumns}
                rowKey="id"
                size="small"
                pagination={{ pageSize: 10 }}
              />
            ),
          },
          {
            key: 'halls',
            label: `宴会厅 (${halls.length})`,
            children: halls.length === 0 ? (
              <Empty description="暂无宴会厅" />
            ) : (
              <Row gutter={[16, 16]}>
                {halls.map(hall => (
                  <Col key={hall.id} xs={24} sm={12} lg={8}>
                    <Card
                      size="small"
                      title={hall.hall_name}
                      extra={hall.price_range && <Text type="warning">{hall.price_range}</Text>}
                    >
                      <Descriptions size="small" column={2}>
                        <Descriptions.Item label="容纳">
                          {hall.capacity_min && hall.capacity_max
                            ? `${hall.capacity_min}-${hall.capacity_max}人`
                            : '-'}
                        </Descriptions.Item>
                        <Descriptions.Item label="桌数">
                          {hall.table_count_max ? `≤${hall.table_count_max}桌` : '-'}
                        </Descriptions.Item>
                        <Descriptions.Item label="面积">
                          {hall.area_sqm ? `${hall.area_sqm}m²` : '-'}
                        </Descriptions.Item>
                        <Descriptions.Item label="层高">
                          {hall.ceiling_height ? `${hall.ceiling_height}m` : '-'}
                        </Descriptions.Item>
                      </Descriptions>
                      <div style={{ marginTop: 8 }}>
                        {hall.has_led_screen && <Tag color="blue">LED</Tag>}
                        {hall.has_stage && <Tag color="purple">舞台</Tag>}
                        {hall.has_natural_light && <Tag color="green">自然光</Tag>}
                        {hall.features.map((f, i) => <Tag key={i}>{f}</Tag>)}
                      </div>
                    </Card>
                  </Col>
                ))}
              </Row>
            ),
          },
        ]} />
      </Spin>

      {/* AI 生成 EO 单 Modal */}
      <Modal
        title="AI 生成 EO 单"
        open={generateVisible}
        onOk={handleGenerate}
        onCancel={() => setGenerateVisible(false)}
        okText="生成"
        width={560}
      >
        <Form form={generateForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="reservation_id" label="预约ID" rules={[{ required: true }]}>
                <Input placeholder="关联预约单号" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="event_date" label="宴会日期" rules={[{ required: true }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="event_type" label="宴会类型" initialValue="wedding">
                <Select options={[
                  { value: 'wedding', label: '婚宴' },
                  { value: 'birthday', label: '寿宴' },
                  { value: 'corporate', label: '商务' },
                  { value: 'family', label: '家庭聚会' },
                ]} />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="guest_count" label="人数" initialValue={100}>
                <InputNumber min={1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="table_count" label="桌数" initialValue={10}>
                <InputNumber min={1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="budget_yuan" label="预算(元)">
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="special_requirements" label="特殊要求">
                <Input.TextArea rows={1} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* EO 详情 Drawer */}
      <Drawer
        title={currentEO ? `EO单 v${currentEO.version} — ${EVENT_TYPE_MAP[currentEO.event_type] || currentEO.event_type}` : 'EO详情'}
        open={detailVisible}
        onClose={() => setDetailVisible(false)}
        width={640}
      >
        {currentEO && (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            {/* 基本信息 */}
            <Card size="small" title="基本信息">
              <Descriptions size="small" column={2}>
                <Descriptions.Item label="宴会日期">{currentEO.event_date}</Descriptions.Item>
                <Descriptions.Item label="类型">
                  <Tag>{EVENT_TYPE_MAP[currentEO.event_type] || currentEO.event_type}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="人数">{currentEO.party_size}人</Descriptions.Item>
                <Descriptions.Item label="桌数">{currentEO.table_count}桌</Descriptions.Item>
                <Descriptions.Item label="预算">¥{currentEO.estimated_budget_yuan.toFixed(0)}</Descriptions.Item>
                <Descriptions.Item label="状态">
                  <Tag color={STATUS_MAP[currentEO.status]?.color}>{STATUS_MAP[currentEO.status]?.label}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="套餐">{currentEO.menu_package || '-'}</Descriptions.Item>
                <Descriptions.Item label="服务人员">{currentEO.service_staff_count}人</Descriptions.Item>
              </Descriptions>
              {currentEO.ai_generated && (
                <div style={{ marginTop: 8 }}>
                  <Tag color="purple">AI生成</Tag>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    置信度 {Math.round(currentEO.ai_confidence * 100)}%
                  </Text>
                </div>
              )}
            </Card>

            {/* 履约时间线 */}
            <Card size="small" title="履约时间线">
              <Steps
                direction="vertical"
                size="small"
                current={
                  TIMELINE_NODES.findIndex(n => !currentEO.fulfillment_timeline[n.key]?.actual_time)
                }
                items={TIMELINE_NODES.map(node => {
                  const data = currentEO.fulfillment_timeline[node.key] || {};
                  const completed = !!data.actual_time;
                  return {
                    title: node.label,
                    status: completed ? 'finish' : 'wait',
                    description: completed ? (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {dayjs(data.actual_time).format('HH:mm')} — {data.notes || ''}
                      </Text>
                    ) : (
                      currentEO.status === 'confirmed' && (
                        <Button
                          size="small"
                          type="link"
                          onClick={() => handleFulfillment(currentEO.id, node.key)}
                        >
                          打卡
                        </Button>
                      )
                    ),
                  };
                })}
              />
            </Card>

            {/* 演职人员 */}
            <Card size="small" title={`演职人员 (${currentEO.staff?.length || 0})`}>
              {(!currentEO.staff || currentEO.staff.length === 0) ? (
                <Empty description="暂无演职人员" />
              ) : (
                <List
                  size="small"
                  dataSource={currentEO.staff}
                  renderItem={s => {
                    const roleInfo = ROLE_MAP[s.role] || { label: s.role, icon: <TeamOutlined /> };
                    return (
                      <List.Item
                        extra={
                          <Space>
                            {s.fee_yuan > 0 && <Text>¥{s.fee_yuan.toFixed(0)}</Text>}
                            <Tag color={
                              s.confirm_status === 'confirmed' ? 'green'
                                : s.confirm_status === 'declined' ? 'red'
                                  : 'default'
                            }>
                              {s.confirm_status === 'confirmed' ? '已确认'
                                : s.confirm_status === 'declined' ? '已拒绝'
                                  : '待确认'}
                            </Tag>
                          </Space>
                        }
                      >
                        <List.Item.Meta
                          avatar={<Avatar size="small">{typeof roleInfo.icon === 'string' ? roleInfo.icon : roleInfo.label[0]}</Avatar>}
                          title={<Space><Text>{roleInfo.label}</Text><Text type="secondary">{s.staff_name}</Text></Space>}
                          description={
                            <Space>
                              {s.staff_phone && <Text type="secondary" style={{ fontSize: 12 }}>{s.staff_phone}</Text>}
                              {s.company && <Text type="secondary" style={{ fontSize: 12 }}>{s.company}</Text>}
                            </Space>
                          }
                        />
                      </List.Item>
                    );
                  }}
                />
              )}
            </Card>
          </Space>
        )}
      </Drawer>
    </div>
  );
}
