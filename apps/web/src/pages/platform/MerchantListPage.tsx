import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Button, Modal, Steps, Form, Input, InputNumber,
  Select, Tag, Space, Row, Col, message, Badge, Divider,
} from 'antd';
import {
  PlusOutlined, ShopOutlined, BankOutlined,
  ReloadOutlined, SearchOutlined, StopOutlined,
  CheckCircleOutlined, TeamOutlined, CopyOutlined,
  MailOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../../services/api';
import {
  CUISINE_LABELS, INDUSTRY_LABELS, CUISINE_OPTIONS,
  type MerchantSummary, type PlatformStats,
} from './merchant-constants';
import styles from './MerchantListPage.module.css';

// ── 种子客户 mock 数据（后端未启动时降级展示） ────────────────────────────────
const SEED_MERCHANTS: MerchantSummary[] = [
  {
    brand_id: 'BRD_CZYZ0001', brand_name: '尝在一起', cuisine_type: 'hunan',
    status: 'active', avg_ticket_yuan: 80,
    group_id: 'GRP_CZYZ0001', group_name: '尝在一起餐饮管理有限公司',
    contact_person: '尝在一起联系人', contact_phone: '0731-00000001',
    store_count: 3, user_count: 1, created_at: '2026-01-15T00:00:00Z',
  },
  {
    brand_id: 'BRD_ZQX0001', brand_name: '最黔线', cuisine_type: 'guizhou',
    status: 'active', avg_ticket_yuan: 75,
    group_id: 'GRP_ZQX0001', group_name: '老江菜馆餐饮管理有限公司',
    contact_person: '最黔线联系人', contact_phone: '0731-00000002',
    store_count: 6, user_count: 1, created_at: '2026-01-20T00:00:00Z',
  },
  {
    brand_id: 'BRD_SGC0001', brand_name: '尚宫厨', cuisine_type: 'hunan',
    status: 'active', avg_ticket_yuan: 180,
    group_id: 'GRP_SGC0001', group_name: '尚宫厨餐饮管理有限公司',
    contact_person: '尚宫厨联系人', contact_phone: '0731-00000003',
    store_count: 5, user_count: 1, created_at: '2026-02-01T00:00:00Z',
  },
];

const SEED_STATS: PlatformStats = {
  total_merchants: 3, active_merchants: 3, inactive_merchants: 0,
  total_stores: 14, active_stores: 14,
  total_users: 3, active_users: 3, total_groups: 3,
};

const MerchantListPage: React.FC = () => {
  const navigate = useNavigate();
  const [merchants, setMerchants] = useState<MerchantSummary[]>([]);
  const [stats, setStats] = useState<PlatformStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [cuisineFilter, setCuisineFilter] = useState<string | undefined>(undefined);

  // Onboard wizard
  const [onboardVisible, setOnboardVisible] = useState(false);
  const [onboardStep, setOnboardStep] = useState(0);
  const [onboardForm] = Form.useForm();
  const [onboardLoading, setOnboardLoading] = useState(false);
  const [onboardResult, setOnboardResult] = useState<{ group_id: string; brand_id: string; admin_user_id: string } | null>(null);

  // ── Data fetching ──────────────────────────────────────────────────────────

  const fetchStats = useCallback(async () => {
    try {
      const data = await apiClient.get<PlatformStats>('/api/v1/merchants/stats');
      setStats(data);
    } catch {
      setStats(SEED_STATS);
    }
  }, []);

  const fetchMerchants = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (keyword) params.set('keyword', keyword);
      if (statusFilter) params.set('status', statusFilter);
      if (cuisineFilter) params.set('cuisine_type', cuisineFilter);
      const qs = params.toString();
      const data = await apiClient.get<MerchantSummary[]>(`/api/v1/merchants${qs ? `?${qs}` : ''}`);
      setMerchants(data);
    } catch {
      // 后端未启动时降级显示种子客户
      let fallback = SEED_MERCHANTS;
      if (keyword) {
        const q = keyword.toLowerCase();
        fallback = fallback.filter(m =>
          m.brand_name.toLowerCase().includes(q) ||
          m.group_name.toLowerCase().includes(q) ||
          m.contact_person.includes(q)
        );
      }
      if (statusFilter) fallback = fallback.filter(m => m.status === statusFilter);
      if (cuisineFilter) fallback = fallback.filter(m => m.cuisine_type === cuisineFilter);
      setMerchants(fallback);
    } finally {
      setLoading(false);
    }
  }, [keyword, statusFilter, cuisineFilter]);

  useEffect(() => { fetchStats(); }, [fetchStats]);
  useEffect(() => { fetchMerchants(); }, [fetchMerchants]);

  const refreshAll = () => { fetchMerchants(); fetchStats(); };

  // ── Onboard ────────────────────────────────────────────────────────────────

  const handleOnboard = async () => {
    try {
      const values = await onboardForm.validateFields();
      setOnboardLoading(true);
      const result = await apiClient.post<{ message: string; group_id: string; brand_id: string; admin_user_id: string }>('/api/v1/merchants/onboard', {
        group: {
          group_name: values.group_name,
          legal_entity: values.legal_entity,
          unified_social_credit_code: values.unified_social_credit_code,
          industry_type: values.industry_type || 'chinese_formal',
          contact_person: values.contact_person,
          contact_phone: values.contact_phone,
          address: values.address,
        },
        brand: {
          brand_name: values.brand_name,
          cuisine_type: values.cuisine_type || 'chinese_formal',
          avg_ticket_yuan: values.avg_ticket_yuan,
          target_food_cost_pct: values.target_food_cost_pct ?? 35,
          target_labor_cost_pct: values.target_labor_cost_pct ?? 25,
          target_rent_cost_pct: values.target_rent_cost_pct,
          target_waste_pct: values.target_waste_pct ?? 3,
        },
        admin: {
          username: values.admin_username,
          email: values.admin_email,
          password: values.admin_password,
          full_name: values.admin_full_name,
        },
      });
      setOnboardResult(result);
      setOnboardStep(3);
      message.success('商户开通成功');
      refreshAll();
    } catch {
      message.error('商户开通失败');
    } finally {
      setOnboardLoading(false);
    }
  };

  const closeOnboard = () => {
    setOnboardVisible(false);
    setOnboardStep(0);
    setOnboardResult(null);
    onboardForm.resetFields();
  };

  const copyText = (text: string) => {
    navigator.clipboard.writeText(text);
    message.success('已复制');
  };

  // ── Table columns ──────────────────────────────────────────────────────────

  const columns: ColumnsType<MerchantSummary> = [
    {
      title: '品牌', dataIndex: 'brand_name', key: 'brand_name', width: 180,
      render: (_: unknown, r: MerchantSummary) => (
        <div className={styles.brandCell}>
          <span className={styles.brandName}>{r.brand_name}</span>
          <span className={styles.brandId}>{r.brand_id}</span>
        </div>
      ),
    },
    {
      title: '集团', dataIndex: 'group_name', key: 'group_name', width: 180,
      render: (_: unknown, r: MerchantSummary) => (
        <div className={styles.groupCell}>
          <span className={styles.groupName}>{r.group_name}</span>
          <span className={styles.groupContact}>{r.contact_person} {r.contact_phone}</span>
        </div>
      ),
    },
    {
      title: '菜系', dataIndex: 'cuisine_type', key: 'cuisine_type', width: 90,
      render: (v: string) => <Tag>{CUISINE_LABELS[v] || v}</Tag>,
    },
    {
      title: '人均', dataIndex: 'avg_ticket_yuan', key: 'avg_ticket', width: 80,
      render: (v: number | null) => v ? `¥${v}` : '-',
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (s: string) => (
        <Badge status={s === 'active' ? 'success' : 'error'} text={s === 'active' ? '运营中' : '已停用'} />
      ),
    },
    {
      title: '门店', dataIndex: 'store_count', key: 'store_count', width: 70, align: 'center',
      render: (v: number) => (
        <span className={styles.countBadge}>
          <ShopOutlined className={styles.countIcon} />{v}
        </span>
      ),
    },
    {
      title: '用户', dataIndex: 'user_count', key: 'user_count', width: 70, align: 'center',
      render: (v: number) => (
        <span className={styles.countBadge}>
          <TeamOutlined className={styles.countIcon} />{v}
        </span>
      ),
    },
    {
      title: '开通时间', dataIndex: 'created_at', key: 'created_at', width: 110,
      render: (v: string | null) => v ? new Date(v).toLocaleDateString('zh-CN') : '-',
    },
  ];

  // ── Onboard steps ──────────────────────────────────────────────────────────

  const stepItems = [
    { title: '集团信息' },
    { title: '品牌配置' },
    { title: '管理员账号' },
    ...(onboardResult ? [{ title: '完成' }] : []),
  ];

  const renderStepContent = () => {
    if (onboardStep === 3 && onboardResult) {
      return (
        <div className={styles.onboardResult}>
          <CheckCircleOutlined className={styles.onboardResultIcon} />
          <div className={styles.onboardResultTitle}>商户开通成功</div>
          <div className={styles.onboardResultDesc}>集团、品牌和管理员账号已创建</div>
          <div className={styles.onboardResultIds}>
            <span>集团 ID: {onboardResult.group_id} <CopyOutlined style={{ cursor: 'pointer' }} onClick={() => copyText(onboardResult.group_id)} /></span>
            <span>品牌 ID: {onboardResult.brand_id} <CopyOutlined style={{ cursor: 'pointer' }} onClick={() => copyText(onboardResult.brand_id)} /></span>
            <span>用户 ID: {onboardResult.admin_user_id}</span>
          </div>
        </div>
      );
    }
    switch (onboardStep) {
      case 0:
        return (
          <>
            <Form.Item name="group_name" label="集团名称" rules={[{ required: true, message: '请输入集团名称' }]}>
              <Input placeholder="如：贵州尝在一起餐饮管理有限公司" />
            </Form.Item>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="legal_entity" label="法人代表" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="unified_social_credit_code" label="统一社会信用代码" rules={[{ required: true, len: 18, message: '需 18 位' }]}>
                  <Input maxLength={18} />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="industry_type" label="行业类型" initialValue="chinese_formal">
              <Select options={Object.entries(INDUSTRY_LABELS).map(([v, l]) => ({ value: v, label: l }))} />
            </Form.Item>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="contact_person" label="联系人" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="contact_phone" label="联系电话" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="address" label="地址">
              <Input placeholder="集团注册地址" />
            </Form.Item>
          </>
        );
      case 1:
        return (
          <>
            <Form.Item name="brand_name" label="品牌名称" rules={[{ required: true }]}>
              <Input placeholder="如：尝在一起" />
            </Form.Item>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="cuisine_type" label="菜系" initialValue="chinese_formal">
                  <Select options={CUISINE_OPTIONS} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="avg_ticket_yuan" label="人均消费（元）">
                  <InputNumber min={0} style={{ width: '100%' }} placeholder="如 68" />
                </Form.Item>
              </Col>
            </Row>
            <Divider plain style={{ fontSize: 12, color: 'rgba(0,0,0,0.35)' }}>经营目标（%）</Divider>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="target_food_cost_pct" label="食材成本率" initialValue={35}>
                  <InputNumber min={0} max={100} addonAfter="%" style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="target_labor_cost_pct" label="人力成本率" initialValue={25}>
                  <InputNumber min={0} max={100} addonAfter="%" style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="target_rent_cost_pct" label="租金成本率">
                  <InputNumber min={0} max={100} addonAfter="%" style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="target_waste_pct" label="损耗率" initialValue={3}>
                  <InputNumber min={0} max={100} addonAfter="%" style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>
          </>
        );
      case 2:
        return (
          <>
            <div style={{ marginBottom: 16, padding: '10px 12px', background: 'rgba(255,107,44,0.06)', borderRadius: 8, fontSize: 13 }}>
              此账号将作为商户的首位管理员（店长角色），拥有品牌内全部数据权限
            </div>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="admin_username" label="登录用户名" rules={[{ required: true }]}>
                  <Input placeholder="英文/数字" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="admin_full_name" label="姓名">
                  <Input placeholder="真实姓名" />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="admin_email" label="邮箱" rules={[{ required: true, type: 'email' }]}>
              <Input prefix={<MailOutlined />} />
            </Form.Item>
            <Form.Item name="admin_password" label="初始密码" rules={[{ required: true, min: 6, message: '至少 6 位' }]}>
              <Input.Password placeholder="至少 6 位" />
            </Form.Item>
          </>
        );
      default:
        return null;
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className={styles.container}>
      {/* ── Stats ───────────────────────────────────────────────────────────── */}
      <Row gutter={16} className={styles.statsRow}>
        {[
          { label: '商户总数', value: stats?.total_merchants ?? 0, color: '#FF6B2C', icon: <BankOutlined /> },
          { label: '运营中', value: stats?.active_merchants ?? 0, color: '#52c41a', icon: <CheckCircleOutlined /> },
          { label: '已停用', value: stats?.inactive_merchants ?? 0, color: '#ff4d4f', icon: <StopOutlined /> },
          { label: '总门店', value: stats?.total_stores ?? 0, color: '#1677ff', icon: <ShopOutlined /> },
          { label: '总用户', value: stats?.total_users ?? 0, color: '#722ed1', icon: <TeamOutlined /> },
          { label: '集团数', value: stats?.total_groups ?? 0, color: '#fa8c16', icon: <BankOutlined /> },
        ].map(item => (
          <Col span={4} key={item.label}>
            <Card className={styles.statCard} size="small">
              <div className={styles.statIcon} style={{ color: item.color }}>{item.icon}</div>
              <div className={styles.statValue} style={{ color: item.color }}>{item.value}</div>
              <div className={styles.statLabel}>{item.label}</div>
            </Card>
          </Col>
        ))}
      </Row>

      {/* ── Toolbar + Table ─────────────────────────────────────────────────── */}
      <Card>
        <div className={styles.toolbar}>
          <div className={styles.toolbarLeft}>
            <span className={styles.toolbarTitle}>商户列表</span>
            <Input
              placeholder="搜索品牌/集团/联系人"
              prefix={<SearchOutlined />}
              allowClear
              style={{ width: 220 }}
              value={keyword}
              onChange={e => setKeyword(e.target.value)}
              onPressEnter={fetchMerchants}
            />
            <Select
              placeholder="状态"
              allowClear
              style={{ width: 100 }}
              value={statusFilter}
              onChange={setStatusFilter}
              options={[
                { value: 'active', label: '运营中' },
                { value: 'inactive', label: '已停用' },
              ]}
            />
            <Select
              placeholder="菜系"
              allowClear
              style={{ width: 100 }}
              value={cuisineFilter}
              onChange={setCuisineFilter}
              options={CUISINE_OPTIONS}
            />
          </div>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={refreshAll}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setOnboardVisible(true)}>
              开通新商户
            </Button>
          </Space>
        </div>
        <Table<MerchantSummary>
          rowKey="brand_id"
          columns={columns}
          dataSource={merchants}
          loading={loading}
          pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 个商户` }}
          size="middle"
          scroll={{ x: 1100 }}
          onRow={(record) => ({
            onClick: () => navigate(`/platform/merchants/${record.brand_id}`),
            style: { cursor: 'pointer' },
          })}
        />
      </Card>

      {/* ── Onboard Modal ───────────────────────────────────────────────────── */}
      <Modal
        title="开通新商户"
        open={onboardVisible}
        width={640}
        onCancel={closeOnboard}
        destroyOnClose
        footer={
          onboardStep === 3 ? (
            <Button type="primary" onClick={closeOnboard}>关闭</Button>
          ) : (
            <Space>
              {onboardStep > 0 && (
                <Button onClick={() => setOnboardStep(s => s - 1)}>上一步</Button>
              )}
              {onboardStep < 2 ? (
                <Button type="primary" onClick={async () => {
                  try {
                    await onboardForm.validateFields();
                    setOnboardStep(s => s + 1);
                  } catch { /* validation */ }
                }}>下一步</Button>
              ) : (
                <Button type="primary" loading={onboardLoading} onClick={handleOnboard}>
                  确认开通
                </Button>
              )}
            </Space>
          )
        }
      >
        <Steps current={onboardStep} items={stepItems} style={{ marginBottom: 24 }} size="small" />
        <Form form={onboardForm} layout="vertical" preserve>
          {renderStepContent()}
        </Form>
      </Modal>
    </div>
  );
};

export default MerchantListPage;
