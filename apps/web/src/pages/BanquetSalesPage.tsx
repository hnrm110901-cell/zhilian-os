/**
 * 宴会销控看板 — Phase P2 (宴荟佳能力)
 * 档期日历 · 销售漏斗 · 竞对分析 · 动态定价
 */
import React, { useEffect, useState } from 'react';
import {
  Card, Row, Col, Table, Statistic, Tabs, Tag, Button, Modal, Form,
  Input, Select, InputNumber, DatePicker, Spin, Alert, Typography, Space,
  message, Progress, Tooltip, Badge, Calendar, Descriptions,
} from 'antd';
import {
  FunnelPlotOutlined, CalendarOutlined, DollarOutlined,
  TrophyOutlined, PlusOutlined, ArrowRightOutlined,
  CloseCircleOutlined, PhoneOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';
import dayjs from 'dayjs';

const { Title, Text } = Typography;

interface FunnelStage {
  stage: string;
  count: number;
  total_value_yuan: number;
  avg_probability: number;
}

interface FunnelRecord {
  id: string;
  customer_name: string;
  customer_phone: string;
  event_type: string;
  current_stage: string;
  conversion_probability: number;
  estimated_value_yuan: number;
  target_date: string | null;
  table_count: number | null;
  follow_up_count: number;
  lost_reason: string | null;
  lost_to_competitor: string | null;
  created_at: string;
}

interface Competitor {
  id: string;
  competitor_name: string;
  price_range_yuan: string;
  lost_deals_count: number;
  won_deals_count: number;
  common_lost_reasons: string[];
}

const STAGE_LABELS: Record<string, string> = {
  lead: '线索', intent: '意向', room_lock: '锁厅',
  negotiation: '议价', signed: '签约', preparation: '筹备',
  completed: '完成', lost: '输单',
};

const STAGE_COLORS: Record<string, string> = {
  lead: 'default', intent: 'blue', room_lock: 'cyan',
  negotiation: 'geekblue', signed: 'green', preparation: 'lime',
  completed: 'success', lost: 'error',
};

export default function BanquetSalesPage() {
  const [loading, setLoading] = useState(true);
  const [storeId] = useState(localStorage.getItem('store_id') || '');
  const [activeTab, setActiveTab] = useState('funnel');

  const [funnelStats, setFunnelStats] = useState<{ stages: FunnelStage[] } | null>(null);
  const [funnelRecords, setFunnelRecords] = useState<FunnelRecord[]>([]);
  const [competitors, setCompetitors] = useState<Competitor[]>([]);

  // Modals
  const [leadVisible, setLeadVisible] = useState(false);
  const [leadForm] = Form.useForm();

  const fetchData = async () => {
    setLoading(true);
    try {
      const [stats, records, comps] = await Promise.all([
        apiClient.get<any>(`/api/v1/banquet-sales/funnel/stats?store_id=${storeId}`),
        apiClient.get<FunnelRecord[]>(`/api/v1/banquet-sales/funnel?store_id=${storeId}`),
        apiClient.get<Competitor[]>(`/api/v1/banquet-sales/competitors?store_id=${storeId}`),
      ]);
      setFunnelStats(stats);
      setFunnelRecords(records);
      setCompetitors(comps);
    } catch (e: any) {
      message.error(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const handleCreateLead = async () => {
    try {
      const values = await leadForm.validateFields();
      await apiClient.post('/api/v1/banquet-sales/leads', {
        store_id: storeId,
        ...values,
        estimated_value: (values.estimated_value || 0) * 100,
      });
      message.success('线索创建成功');
      setLeadVisible(false);
      leadForm.resetFields();
      fetchData();
    } catch {
      message.error('创建失败');
    }
  };

  const handleAdvance = async (id: string, stage: string) => {
    try {
      await apiClient.patch(`/api/v1/banquet-sales/funnel/${id}/advance`, {
        new_stage: stage,
        note: `推进到${STAGE_LABELS[stage]}`,
      });
      message.success('阶段已更新');
      fetchData();
    } catch {
      message.error('操作失败');
    }
  };

  // ── 漏斗表格列 ──
  const funnelColumns = [
    {
      title: '客户',
      key: 'customer',
      render: (_: unknown, r: FunnelRecord) => (
        <Space direction="vertical" size={0}>
          <Text strong>{r.customer_name}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}><PhoneOutlined /> {r.customer_phone}</Text>
        </Space>
      ),
    },
    {
      title: '阶段',
      dataIndex: 'current_stage',
      key: 'stage',
      render: (v: string) => <Tag color={STAGE_COLORS[v]}>{STAGE_LABELS[v] || v}</Tag>,
      filters: Object.entries(STAGE_LABELS).map(([k, v]) => ({ text: v, value: k })),
      onFilter: (value: any, record: FunnelRecord) => record.current_stage === value,
    },
    {
      title: '成交概率',
      dataIndex: 'conversion_probability',
      key: 'prob',
      render: (v: number) => (
        <Progress
          percent={Math.round(v * 100)}
          size="small"
          style={{ width: 80 }}
          strokeColor={v >= 0.7 ? '#52c41a' : v >= 0.4 ? '#faad14' : '#ff4d4f'}
        />
      ),
      sorter: (a: FunnelRecord, b: FunnelRecord) => a.conversion_probability - b.conversion_probability,
    },
    {
      title: '预估金额',
      dataIndex: 'estimated_value_yuan',
      key: 'value',
      render: (v: number) => <Text strong>¥{v.toFixed(0)}</Text>,
      sorter: (a: FunnelRecord, b: FunnelRecord) => a.estimated_value_yuan - b.estimated_value_yuan,
    },
    {
      title: '宴会日期',
      dataIndex: 'target_date',
      key: 'date',
      render: (v: string | null) => v || '-',
    },
    { title: '跟进', dataIndex: 'follow_up_count', key: 'followup', render: (v: number) => `${v}次` },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, r: FunnelRecord) => {
        if (r.current_stage === 'completed' || r.current_stage === 'lost') return null;
        const stages = ['lead', 'intent', 'room_lock', 'negotiation', 'signed', 'preparation', 'completed'];
        const idx = stages.indexOf(r.current_stage);
        const next = stages[idx + 1];
        if (!next) return null;
        return (
          <Button size="small" type="link" icon={<ArrowRightOutlined />}
            onClick={() => handleAdvance(r.id, next)}>
            {STAGE_LABELS[next]}
          </Button>
        );
      },
    },
  ];

  // ── 竞对表格列 ──
  const competitorColumns = [
    { title: '竞对', dataIndex: 'competitor_name', key: 'name' },
    { title: '价格范围', dataIndex: 'price_range_yuan', key: 'price' },
    {
      title: '输单',
      dataIndex: 'lost_deals_count',
      key: 'lost',
      render: (v: number) => <Text type="danger">{v}单</Text>,
      sorter: (a: Competitor, b: Competitor) => a.lost_deals_count - b.lost_deals_count,
    },
    {
      title: '赢单',
      dataIndex: 'won_deals_count',
      key: 'won',
      render: (v: number) => <Text type="success">{v}单</Text>,
    },
    {
      title: '输单原因',
      dataIndex: 'common_lost_reasons',
      key: 'reasons',
      render: (v: string[]) => v.map((r, i) => <Tag key={i}>{r}</Tag>),
    },
  ];

  const totalValue = funnelStats?.stages.reduce((s, st) => s + st.total_value_yuan, 0) || 0;
  const activeLeads = funnelRecords.filter(r => !['completed', 'lost'].includes(r.current_stage)).length;

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>
          <FunnelPlotOutlined /> 宴会销控
        </Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setLeadVisible(true)}>
          新建线索
        </Button>
      </div>

      <Spin spinning={loading}>
        {/* 漏斗概览卡片 */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card size="small">
              <Statistic title="活跃线索" value={activeLeads} suffix="条" />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="管道总额" value={totalValue} prefix="¥" suffix="" precision={0} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="签约率"
                value={
                  funnelRecords.length > 0
                    ? Math.round(funnelRecords.filter(r => r.current_stage === 'signed' || r.current_stage === 'completed').length / funnelRecords.length * 100)
                    : 0
                }
                suffix="%"
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="竞对威胁"
                value={competitors.length}
                suffix="家"
                prefix={<TrophyOutlined />}
              />
            </Card>
          </Col>
        </Row>

        {/* 漏斗阶段条 */}
        {funnelStats && (
          <Card size="small" style={{ marginBottom: 16 }}>
            <Row gutter={8}>
              {funnelStats.stages
                .filter(s => s.stage !== 'lost')
                .map(s => (
                  <Col key={s.stage} flex="auto">
                    <div style={{ textAlign: 'center', padding: '8px 4px', background: '#fafafa', borderRadius: 6 }}>
                      <div style={{ fontSize: 20, fontWeight: 700 }}>{s.count}</div>
                      <Tag color={STAGE_COLORS[s.stage]}>{STAGE_LABELS[s.stage]}</Tag>
                      <div style={{ fontSize: 11, color: '#999' }}>¥{s.total_value_yuan.toFixed(0)}</div>
                    </div>
                  </Col>
                ))
              }
            </Row>
          </Card>
        )}

        <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
          {
            key: 'funnel',
            label: '销售漏斗',
            children: (
              <Table
                dataSource={funnelRecords}
                columns={funnelColumns}
                rowKey="id"
                size="small"
                pagination={{ pageSize: 10 }}
              />
            ),
          },
          {
            key: 'competitors',
            label: `竞对分析 (${competitors.length})`,
            children: (
              <Table
                dataSource={competitors}
                columns={competitorColumns}
                rowKey="id"
                size="small"
                pagination={false}
              />
            ),
          },
        ]} />
      </Spin>

      {/* 新建线索 Modal */}
      <Modal
        title="新建宴会线索"
        open={leadVisible}
        onOk={handleCreateLead}
        onCancel={() => setLeadVisible(false)}
        okText="创建"
      >
        <Form form={leadForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="customer_name" label="客户姓名" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="customer_phone" label="手机号" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="event_type" label="宴会类型">
                <Select placeholder="选择类型" options={[
                  { value: 'wedding', label: '婚宴' },
                  { value: 'birthday', label: '寿宴' },
                  { value: 'corporate', label: '商务' },
                  { value: 'family', label: '家庭聚会' },
                  { value: 'other', label: '其他' },
                ]} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="table_count" label="预估桌数">
                <InputNumber min={1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="target_date" label="目标日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="estimated_value" label="预估金额(元)">
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </div>
  );
}
