/**
 * MarketingCampaignPage
 * 营销活动管理 — AI 发券策略 / 活动列表 / 顾客画像分析
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Tabs, Table, Button, Modal, Form, Input, InputNumber, Select,
  Card, Statistic, Tag, Space, Progress, Descriptions, Spin,
  message, Badge, Tooltip, Row, Col, Alert,
} from 'antd';
import {
  PlusOutlined, UserOutlined, GiftOutlined, BarChartOutlined,
  PlayCircleOutlined, StopOutlined, ReloadOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';

const { TabPane } = Tabs;
const { Option } = Select;

// ── Types ────────────────────────────────────────────────────────────────────

interface Campaign {
  id: string;
  name: string;
  campaign_type: string;
  status: 'draft' | 'active' | 'completed' | 'cancelled';
  start_date: string | null;
  end_date: string | null;
  budget: number;
  actual_cost: number;
  reach_count: number;
  conversion_count: number;
  revenue_generated: number;
  description: string | null;
  created_at: string;
}

interface CustomerProfile {
  customer_id: string;
  basic_info: { name: string; phone: string; member_level: string };
  consumption: {
    total_orders: number;
    total_amount: number;
    avg_order_amount: number;
    last_order_date: string | null;
    days_since_last_order: number;
    favorite_dishes: string[];
    preferred_time: string;
    preferred_day: string;
  };
  value_score: number;
  churn_risk: number;
  segment: string;
}

interface CouponStrategy {
  coupon_type: string;
  amount: string;
  threshold: string | null;
  valid_days: number;
  target_segment: string;
  expected_conversion: number;
  expected_roi: number;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  draft:     'default',
  active:    'processing',
  completed: 'success',
  cancelled: 'error',
};

const STATUS_LABELS: Record<string, string> = {
  draft:     '草稿',
  active:    '进行中',
  completed: '已完成',
  cancelled: '已取消',
};

const SEGMENT_COLORS: Record<string, string> = {
  high_value: '#f50',
  potential:  '#2db7f5',
  at_risk:    '#faad14',
  lost:       '#d9d9d9',
  new:        '#87d068',
};

const SEGMENT_LABELS: Record<string, string> = {
  high_value: '高价值',
  potential:  '潜力客户',
  at_risk:    '流失风险',
  lost:       '已流失',
  new:        '新客户',
};

// ── Campaign List Tab ─────────────────────────────────────────────────────────

const CampaignList: React.FC<{ storeId: string; onRefresh: () => void }> = ({ storeId, onRefresh }) => {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();

  const fetchCampaigns = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (statusFilter) params.status = statusFilter;
      const data = await apiClient.get(`/api/v1/marketing/stores/${storeId}/campaigns`, { params });
      setCampaigns(data.campaigns || []);
    } catch {
      message.error('加载活动列表失败');
    } finally {
      setLoading(false);
    }
  }, [storeId, statusFilter]);

  useEffect(() => { fetchCampaigns(); }, [fetchCampaigns]);

  const handleStatusChange = async (id: string, status: string) => {
    try {
      await apiClient.patch(`/api/v1/marketing/stores/${storeId}/campaigns/${id}/status`, null, {
        params: { status },
      });
      message.success(`活动已${STATUS_LABELS[status]}`);
      fetchCampaigns();
      onRefresh();
    } catch {
      message.error('操作失败');
    }
  };

  const columns = [
    {
      title: '活动名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, row: Campaign) => (
        <Space direction="vertical" size={0}>
          <span style={{ fontWeight: 600 }}>{name}</span>
          <span style={{ fontSize: 12, color: '#888' }}>{row.campaign_type}</span>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => <Badge status={STATUS_COLORS[s] as any} text={STATUS_LABELS[s]} />,
    },
    {
      title: '预算 / 花费',
      key: 'budget',
      render: (_: any, row: Campaign) => (
        <Space direction="vertical" size={0}>
          <span>预算: ¥{row.budget.toLocaleString()}</span>
          <Progress
            size="small"
            percent={row.budget > 0 ? Math.min(100, Math.round(row.actual_cost / row.budget * 100)) : 0}
            format={p => `${p}%`}
          />
        </Space>
      ),
    },
    {
      title: '触达 / 转化',
      key: 'reach',
      render: (_: any, row: Campaign) => (
        <Space>
          <Statistic value={row.reach_count}   suffix="人" valueStyle={{ fontSize: 13 }} />
          <span>/</span>
          <Statistic value={row.conversion_count} suffix="人" valueStyle={{ fontSize: 13, color: '#3f8600' }} />
        </Space>
      ),
    },
    {
      title: '带来营收',
      dataIndex: 'revenue_generated',
      key: 'revenue',
      render: (v: number) => <span style={{ color: '#3f8600' }}>¥{v.toLocaleString()}</span>,
    },
    {
      title: '周期',
      key: 'period',
      render: (_: any, row: Campaign) => (
        <span>{row.start_date || '—'} ~ {row.end_date || '—'}</span>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, row: Campaign) => (
        <Space>
          {row.status === 'draft' && (
            <Tooltip title="启动活动">
              <Button
                type="link" size="small" icon={<PlayCircleOutlined />}
                onClick={() => handleStatusChange(row.id, 'active')}
              />
            </Tooltip>
          )}
          {row.status === 'active' && (
            <Tooltip title="完成活动">
              <Button
                type="link" size="small" icon={<StopOutlined />}
                onClick={() => handleStatusChange(row.id, 'completed')}
              />
            </Tooltip>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Select
          placeholder="全部状态" allowClear style={{ width: 140 }}
          onChange={v => setStatusFilter(v)}
        >
          {Object.entries(STATUS_LABELS).map(([k, v]) => (
            <Option key={k} value={k}>{v}</Option>
          ))}
        </Select>
        <Button icon={<ReloadOutlined />} onClick={fetchCampaigns}>刷新</Button>
      </Space>
      <Table
        dataSource={campaigns}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 10 }}
      />
    </div>
  );
};

// ── Create Campaign Tab ───────────────────────────────────────────────────────

const CreateCampaign: React.FC<{ storeId: string; onCreated: () => void }> = ({ storeId, onCreated }) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<any>(null);
  const [strategyLoading, setStrategyLoading] = useState(false);

  const previewStrategy = async () => {
    const values = form.getFieldsValue();
    if (!values.objective) return;
    setStrategyLoading(true);
    try {
      const scenarioMap: Record<string, string> = {
        acquisition: 'new_product_launch',
        activation:  'member_day',
        retention:   'traffic_decline',
      };
      const data = await apiClient.post('/api/v1/marketing/coupon-strategy', {
        scenario: scenarioMap[values.objective] || 'default',
        store_id: storeId,
      });
      setPreview(data);
    } catch {
      message.error('预览策略失败');
    } finally {
      setStrategyLoading(false);
    }
  };

  const onFinish = async (values: any) => {
    setLoading(true);
    try {
      const data = await apiClient.post(`/api/v1/marketing/stores/${storeId}/campaigns`, {
        store_id:    storeId,
        objective:   values.objective,
        budget:      values.budget,
        name:        values.name,
        description: values.description,
      });
      message.success(`活动 "${data.name}" 已创建（预期触达 ${data.expected_reach} 人）`);
      form.resetFields();
      setPreview(null);
      onCreated();
    } catch {
      message.error('创建活动失败');
    } finally {
      setLoading(false);
    }
  };

  const objectiveLabels: Record<string, string> = {
    acquisition: '🎯 拉新 — 吸引新顾客首次消费',
    activation:  '🔥 促活 — 激活沉睡的潜力客户',
    retention:   '🤝 挽回 — 召回流失风险客户',
  };

  return (
    <Row gutter={24}>
      <Col xs={24} md={12}>
        <Card title="活动配置" bordered={false}>
          <Form form={form} layout="vertical" onFinish={onFinish}>
            <Form.Item name="name" label="活动名称（可选）">
              <Input placeholder="AI 将自动生成名称" />
            </Form.Item>

            <Form.Item name="objective" label="营销目标" rules={[{ required: true }]}>
              <Select placeholder="选择目标" onChange={previewStrategy}>
                {Object.entries(objectiveLabels).map(([k, v]) => (
                  <Option key={k} value={k}>{v}</Option>
                ))}
              </Select>
            </Form.Item>

            <Form.Item name="budget" label="营销预算（元）" rules={[{ required: true }]}>
              <InputNumber
                min={100} max={100000} step={100} style={{ width: '100%' }}
                formatter={v => `¥ ${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                prefix="¥"
              />
            </Form.Item>

            <Form.Item name="description" label="活动描述（可选）">
              <Input.TextArea rows={2} placeholder="AI 将自动生成活动描述" />
            </Form.Item>

            <Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} icon={<PlusOutlined />}>
                AI 生成并创建活动
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </Col>

      <Col xs={24} md={12}>
        <Card
          title={<><GiftOutlined /> AI 发券策略预览</>}
          bordered={false}
          extra={strategyLoading && <Spin size="small" />}
        >
          {preview ? (
            <Descriptions column={1} size="small">
              <Descriptions.Item label="券类型">{preview.coupon_type}</Descriptions.Item>
              <Descriptions.Item label="面额">¥{preview.amount}</Descriptions.Item>
              <Descriptions.Item label="门槛">
                {preview.threshold ? `满 ¥${preview.threshold}` : '无门槛'}
              </Descriptions.Item>
              <Descriptions.Item label="有效期">{preview.valid_days} 天</Descriptions.Item>
              <Descriptions.Item label="目标客群">
                <Tag color={SEGMENT_COLORS[preview.target_segment] || 'blue'}>
                  {SEGMENT_LABELS[preview.target_segment] || preview.target_segment}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="预期转化率">
                {(preview.expected_conversion * 100).toFixed(0)}%
              </Descriptions.Item>
              <Descriptions.Item label="预期 ROI">
                {preview.expected_roi}x
              </Descriptions.Item>
            </Descriptions>
          ) : (
            <Alert
              message="选择营销目标后将自动预览 AI 建议的发券策略"
              type="info" showIcon
            />
          )}
        </Card>
      </Col>
    </Row>
  );
};

// ── Customer Analysis Tab ─────────────────────────────────────────────────────

const CustomerAnalysis: React.FC<{ storeId: string }> = ({ storeId }) => {
  const [phone, setPhone]       = useState('');
  const [profile, setProfile]   = useState<CustomerProfile | null>(null);
  const [loading, setLoading]   = useState(false);
  const [triggering, setTriggering] = useState(false);

  const fetchProfile = async () => {
    if (!phone) return;
    setLoading(true);
    try {
      const data = await apiClient.get(
        `/api/v1/marketing/stores/${storeId}/customers/${phone}/profile`
      );
      setProfile(data);
    } catch {
      message.error('未找到该顾客数据');
      setProfile(null);
    } finally {
      setLoading(false);
    }
  };

  const triggerMarketing = async (triggerType: string) => {
    if (!profile) return;
    setTriggering(true);
    try {
      await apiClient.post(
        `/api/v1/marketing/stores/${storeId}/customers/${profile.customer_id}/trigger`,
        { trigger_type: triggerType, store_id: storeId }
      );
      message.success('营销触达已发送');
    } catch {
      message.error('触达失败');
    } finally {
      setTriggering(false);
    }
  };

  const churnColor = profile
    ? profile.churn_risk < 0.3 ? '#3f8600'
      : profile.churn_risk < 0.6 ? '#faad14' : '#cf1322'
    : '#000';

  return (
    <div>
      <Space.Compact style={{ marginBottom: 24, width: '100%', maxWidth: 400 }}>
        <Input
          placeholder="输入顾客手机号查询画像"
          value={phone}
          onChange={e => setPhone(e.target.value)}
          onPressEnter={fetchProfile}
          prefix={<UserOutlined />}
        />
        <Button type="primary" onClick={fetchProfile} loading={loading}>查询</Button>
      </Space.Compact>

      {profile && (
        <Row gutter={[16, 16]}>
          {/* 基础信息 */}
          <Col xs={24} md={8}>
            <Card title="顾客基础" size="small">
              <Descriptions column={1} size="small">
                <Descriptions.Item label="姓名">{profile.basic_info.name}</Descriptions.Item>
                <Descriptions.Item label="手机">{profile.basic_info.phone}</Descriptions.Item>
                <Descriptions.Item label="会员等级">{profile.basic_info.member_level}</Descriptions.Item>
                <Descriptions.Item label="客户分群">
                  <Tag color={SEGMENT_COLORS[profile.segment]}>
                    {SEGMENT_LABELS[profile.segment] || profile.segment}
                  </Tag>
                </Descriptions.Item>
              </Descriptions>
            </Card>
          </Col>

          {/* RFM 评分 */}
          <Col xs={24} md={8}>
            <Card title="价值评估" size="small">
              <Row gutter={8}>
                <Col span={12}>
                  <Statistic
                    title="价值评分"
                    value={profile.value_score.toFixed(1)}
                    suffix="/ 100"
                    valueStyle={{ color: profile.value_score > 60 ? '#3f8600' : '#faad14' }}
                  />
                </Col>
                <Col span={12}>
                  <Statistic
                    title="流失风险"
                    value={(profile.churn_risk * 100).toFixed(0)}
                    suffix="%"
                    valueStyle={{ color: churnColor }}
                  />
                </Col>
                <Col span={12} style={{ marginTop: 8 }}>
                  <Statistic
                    title="累计消费"
                    value={profile.consumption.total_orders}
                    suffix="次"
                  />
                </Col>
                <Col span={12} style={{ marginTop: 8 }}>
                  <Statistic
                    title="上次消费"
                    value={profile.consumption.days_since_last_order}
                    suffix="天前"
                  />
                </Col>
              </Row>
            </Card>
          </Col>

          {/* 偏好 */}
          <Col xs={24} md={8}>
            <Card title="消费偏好" size="small">
              <Descriptions column={1} size="small">
                <Descriptions.Item label="偏好时段">
                  {profile.consumption.preferred_time}
                </Descriptions.Item>
                <Descriptions.Item label="偏好星期">
                  {profile.consumption.preferred_day}
                </Descriptions.Item>
                <Descriptions.Item label="常点菜品">
                  <Space wrap>
                    {profile.consumption.favorite_dishes.slice(0, 3).map(d => (
                      <Tag key={d}>{d}</Tag>
                    ))}
                  </Space>
                </Descriptions.Item>
                <Descriptions.Item label="客单价">
                  ¥{profile.consumption.avg_order_amount}
                </Descriptions.Item>
              </Descriptions>
            </Card>
          </Col>

          {/* 营销触达 */}
          <Col xs={24}>
            <Card title="一键营销触达" size="small">
              <Space>
                <Button
                  icon={<GiftOutlined />}
                  onClick={() => triggerMarketing('birthday')}
                  loading={triggering}
                >
                  发送生日券
                </Button>
                <Button
                  icon={<GiftOutlined />}
                  onClick={() => triggerMarketing('churn_warning')}
                  loading={triggering}
                  disabled={profile.churn_risk < 0.3}
                >
                  挽回优惠（流失风险 {(profile.churn_risk * 100).toFixed(0)}%）
                </Button>
                <Button
                  icon={<GiftOutlined />}
                  onClick={() => triggerMarketing('repurchase_reminder')}
                  loading={triggering}
                >
                  复购提醒
                </Button>
              </Space>
            </Card>
          </Col>
        </Row>
      )}
    </div>
  );
};

// ── Main Page ─────────────────────────────────────────────────────────────────

const MarketingCampaignPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('campaigns');
  const [refreshKey, setRefreshKey] = useState(0);
  const [storeId, setStoreId] = useState(localStorage.getItem('store_id') || '');
  const [stores, setStores] = useState<any[]>([]);

  useEffect(() => {
    const loadStores = async () => {
      try {
        const res = await apiClient.get('/api/v1/stores');
        const list: any[] = res.stores || res || [];
        setStores(list);
        if (list.length > 0) setStoreId(list[0].store_id || list[0].id || '');
      } catch { /* ignore */ }
    };
    loadStores();
  }, []);

  const handleRefresh = () => setRefreshKey(k => k + 1);

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h2 style={{ margin: 0 }}>营销活动中心</h2>
          <p style={{ color: '#888', marginTop: 4 }}>
            AI 驱动的营销策略生成 · 顾客 360° 画像 · 私域触达自动化
          </p>
        </div>
        <Select value={storeId} onChange={setStoreId} style={{ width: 160 }}>
          {stores.length > 0
            ? stores.map((s: any) => <Option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</Option>)
          : null}
        </Select>
      </div>

      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane
          tab={<><BarChartOutlined />活动列表</>}
          key="campaigns"
        >
          <CampaignList key={`${refreshKey}-${storeId}`} storeId={storeId} onRefresh={handleRefresh} />
        </TabPane>

        <TabPane
          tab={<><PlusOutlined />创建活动</>}
          key="create"
        >
          <CreateCampaign storeId={storeId} onCreated={() => { handleRefresh(); setActiveTab('campaigns'); }} />
        </TabPane>

        <TabPane
          tab={<><UserOutlined />顾客分析</>}
          key="customers"
        >
          <CustomerAnalysis storeId={storeId} />
        </TabPane>
      </Tabs>
    </div>
  );
};

export default MarketingCampaignPage;
