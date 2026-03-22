import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Button, Modal, Steps, Form, Input, InputNumber,
  Select, Tag, Drawer, Space, Row, Col, message, Popconfirm,
  Tooltip, Switch, Descriptions, Tabs, Typography, Badge, Divider,
} from 'antd';
import {
  PlusOutlined, ShopOutlined, UserAddOutlined, BankOutlined,
  ReloadOutlined, SearchOutlined, EditOutlined, StopOutlined,
  CheckCircleOutlined, DeleteOutlined, TeamOutlined, CopyOutlined,
  PhoneOutlined, MailOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../utils/apiClient';
import AgentConfigPage from './AgentConfigPage';
import styles from './MerchantManagementPage.module.css';

const { Text } = Typography;

// ── Constants ────────────────────────────────────────────────────────────────

const CUISINE_LABELS: Record<string, string> = {
  chinese_formal: '中餐正餐', sichuan: '川菜', hunan: '湘菜',
  cantonese: '粤菜', guizhou: '黔菜', hotpot: '火锅',
  bbq: '烧烤', fast_food: '快餐', other: '其他',
};

const INDUSTRY_LABELS: Record<string, string> = {
  chinese_formal: '中餐正餐', hotpot: '火锅', fast_food: '快餐',
  bbq: '烧烤', other: '其他',
};

const ROLE_LABELS: Record<string, string> = {
  admin: '管理员', store_manager: '店长', assistant_manager: '店助',
  floor_manager: '楼面经理', customer_manager: '客户经理',
  team_leader: '领班', waiter: '服务员', head_chef: '厨师长',
  station_manager: '档口负责人', chef: '厨师',
  warehouse_manager: '库管', finance: '财务', procurement: '采购',
};

const CUISINE_OPTIONS = Object.entries(CUISINE_LABELS).map(([v, l]) => ({ value: v, label: l }));
const ROLE_OPTIONS = [
  'store_manager', 'floor_manager', 'head_chef', 'waiter',
  'chef', 'warehouse_manager', 'finance', 'procurement',
].map(v => ({ value: v, label: ROLE_LABELS[v] || v }));

// ── Types ────────────────────────────────────────────────────────────────────

interface MerchantSummary {
  brand_id: string;
  brand_name: string;
  cuisine_type: string;
  status: string;
  avg_ticket_yuan: number | null;
  group_id: string;
  group_name: string;
  contact_person: string;
  contact_phone: string;
  store_count: number;
  user_count: number;
  created_at: string | null;
}

interface StoreItem {
  id: string;
  name: string;
  code: string;
  city: string;
  district: string;
  status: string;
  address: string;
  seats: number | null;
  created_at: string | null;
}

interface UserItem {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  store_id: string | null;
  created_at: string | null;
}

interface MerchantDetail {
  brand_id: string;
  brand_name: string;
  cuisine_type: string;
  avg_ticket_yuan: number | null;
  target_food_cost_pct: number;
  target_labor_cost_pct: number;
  target_rent_cost_pct: number | null;
  target_waste_pct: number;
  logo_url: string | null;
  status: string;
  created_at: string | null;
  group: {
    group_id: string;
    group_name: string;
    legal_entity: string;
    unified_social_credit_code: string;
    industry_type: string;
    contact_person: string;
    contact_phone: string;
    address: string | null;
  };
  stores: StoreItem[];
  users: UserItem[];
}

interface PlatformStats {
  total_merchants: number;
  active_merchants: number;
  inactive_merchants: number;
  total_stores: number;
  active_stores: number;
  total_users: number;
  active_users: number;
  total_groups: number;
}

// ── Component ────────────────────────────────────────────────────────────────

const MerchantManagementPage: React.FC = () => {
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

  // Detail drawer
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [detail, setDetail] = useState<MerchantDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Edit merchant
  const [editVisible, setEditVisible] = useState(false);
  const [editForm] = Form.useForm();

  // Edit group
  const [editGroupVisible, setEditGroupVisible] = useState(false);
  const [editGroupForm] = Form.useForm();

  // Add store / user
  const [addStoreVisible, setAddStoreVisible] = useState(false);
  const [storeForm] = Form.useForm();
  const [addUserVisible, setAddUserVisible] = useState(false);
  const [userForm] = Form.useForm();

  // ── Data fetching ──────────────────────────────────────────────────────────

  const fetchStats = useCallback(async () => {
    try {
      const data = await apiClient.get<PlatformStats>('/api/v1/merchants/stats');
      setStats(data);
    } catch { /* silent */ }
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
      message.error('加载商户列表失败');
    } finally {
      setLoading(false);
    }
  }, [keyword, statusFilter, cuisineFilter]);

  useEffect(() => { fetchStats(); }, [fetchStats]);
  useEffect(() => { fetchMerchants(); }, [fetchMerchants]);

  const fetchDetail = async (brandId: string) => {
    setDetailLoading(true);
    setDrawerVisible(true);
    try {
      const data = await apiClient.get<MerchantDetail>(`/api/v1/merchants/${brandId}`);
      setDetail(data);
    } catch {
      message.error('加载商户详情失败');
    } finally {
      setDetailLoading(false);
    }
  };

  const refreshDetail = () => {
    if (detail) fetchDetail(detail.brand_id);
  };

  const refreshAll = () => {
    fetchMerchants();
    fetchStats();
  };

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
      setOnboardStep(3); // success step
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

  // ── Edit merchant ──────────────────────────────────────────────────────────

  const openEditMerchant = () => {
    if (!detail) return;
    editForm.setFieldsValue({
      brand_name: detail.brand_name,
      cuisine_type: detail.cuisine_type,
      avg_ticket_yuan: detail.avg_ticket_yuan,
      target_food_cost_pct: detail.target_food_cost_pct,
      target_labor_cost_pct: detail.target_labor_cost_pct,
      target_rent_cost_pct: detail.target_rent_cost_pct,
      target_waste_pct: detail.target_waste_pct,
    });
    setEditVisible(true);
  };

  const handleEditMerchant = async () => {
    if (!detail) return;
    try {
      const values = await editForm.validateFields();
      await apiClient.put(`/api/v1/merchants/${detail.brand_id}`, values);
      message.success('品牌信息已更新');
      setEditVisible(false);
      refreshDetail();
      refreshAll();
    } catch {
      message.error('更新失败');
    }
  };

  // ── Edit group ─────────────────────────────────────────────────────────────

  const openEditGroup = () => {
    if (!detail) return;
    editGroupForm.setFieldsValue({ ...detail.group });
    setEditGroupVisible(true);
  };

  const handleEditGroup = async () => {
    if (!detail) return;
    try {
      const values = await editGroupForm.validateFields();
      await apiClient.put(`/api/v1/merchants/${detail.brand_id}/group`, values);
      message.success('集团信息已更新');
      setEditGroupVisible(false);
      refreshDetail();
      refreshAll();
    } catch {
      message.error('更新失败');
    }
  };

  // ── Toggle status ──────────────────────────────────────────────────────────

  const handleToggleMerchant = async (brandId: string) => {
    try {
      await apiClient.post(`/api/v1/merchants/${brandId}/toggle-status`, {});
      message.success('状态已切换');
      refreshDetail();
      refreshAll();
    } catch {
      message.error('操作失败');
    }
  };

  const handleToggleUser = async (userId: string) => {
    if (!detail) return;
    try {
      await apiClient.post(`/api/v1/merchants/${detail.brand_id}/users/${userId}/toggle-status`, {});
      message.success('用户状态已切换');
      refreshDetail();
    } catch {
      message.error('操作失败');
    }
  };

  // ── Remove store / user ────────────────────────────────────────────────────

  const handleRemoveStore = async (storeId: string) => {
    if (!detail) return;
    try {
      await apiClient.delete(`/api/v1/merchants/${detail.brand_id}/stores/${storeId}`);
      message.success('门店已移除');
      refreshDetail();
      refreshAll();
    } catch {
      message.error('移除失败');
    }
  };

  const handleRemoveUser = async (userId: string) => {
    if (!detail) return;
    try {
      await apiClient.delete(`/api/v1/merchants/${detail.brand_id}/users/${userId}`);
      message.success('用户已移除');
      refreshDetail();
      refreshAll();
    } catch {
      message.error('移除失败');
    }
  };

  // ── Add store ──────────────────────────────────────────────────────────────

  const handleAddStore = async () => {
    if (!detail) return;
    try {
      const values = await storeForm.validateFields();
      await apiClient.post(`/api/v1/merchants/${detail.brand_id}/stores`, values);
      message.success('门店添加成功');
      setAddStoreVisible(false);
      storeForm.resetFields();
      refreshDetail();
      refreshAll();
    } catch {
      message.error('添加门店失败');
    }
  };

  // ── Add user ───────────────────────────────────────────────────────────────

  const handleAddUser = async () => {
    if (!detail) return;
    try {
      const values = await userForm.validateFields();
      await apiClient.post(`/api/v1/merchants/${detail.brand_id}/users`, values);
      message.success('用户添加成功');
      setAddUserVisible(false);
      userForm.resetFields();
      refreshDetail();
      refreshAll();
    } catch {
      message.error('添加用户失败');
    }
  };

  // ── Copy helper ────────────────────────────────────────────────────────────

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
    {
      title: '操作', key: 'action', width: 80, fixed: 'right',
      render: (_: unknown, r: MerchantSummary) => (
        <Button type="link" size="small" onClick={(e) => { e.stopPropagation(); fetchDetail(r.brand_id); }}>
          详情
        </Button>
      ),
    },
  ];

  // ── Drawer sub-table columns ───────────────────────────────────────────────

  const storeColumns: ColumnsType<StoreItem> = [
    { title: '名称', dataIndex: 'name', key: 'name', width: 140 },
    { title: '编码', dataIndex: 'code', key: 'code', width: 90 },
    { title: '城市', dataIndex: 'city', key: 'city', width: 80 },
    { title: '座位', dataIndex: 'seats', key: 'seats', width: 60, render: (v: number | null) => v ?? '-' },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 70,
      render: (s: string) => <Badge status={s === 'active' ? 'success' : 'default'} text={s} />,
    },
    {
      title: '', key: 'action', width: 50,
      render: (_: unknown, r: StoreItem) => (
        <Popconfirm title={`确认移除「${r.name}」?`} onConfirm={() => handleRemoveStore(r.id)}>
          <Button type="text" size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  const userColumns: ColumnsType<UserItem> = [
    {
      title: '用户', dataIndex: 'username', key: 'username', width: 120,
      render: (_: unknown, r: UserItem) => (
        <div>
          <div style={{ fontWeight: 500 }}>{r.full_name || r.username}</div>
          <Text type="secondary" style={{ fontSize: 11 }}>{r.username}</Text>
        </div>
      ),
    },
    {
      title: '角色', dataIndex: 'role', key: 'role', width: 80,
      render: (v: string) => <Tag>{ROLE_LABELS[v] || v}</Tag>,
    },
    {
      title: '启用', dataIndex: 'is_active', key: 'is_active', width: 60,
      render: (v: boolean, r: UserItem) => (
        <Switch size="small" checked={v} onChange={() => handleToggleUser(r.id)} />
      ),
    },
    {
      title: '', key: 'action', width: 50,
      render: (_: unknown, r: UserItem) => (
        <Popconfirm title={`确认移除用户「${r.username}」?`} onConfirm={() => handleRemoveUser(r.id)}>
          <Button type="text" size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
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
            onClick: () => fetchDetail(record.brand_id),
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

      {/* ── Detail Drawer ───────────────────────────────────────────────────── */}
      <Drawer
        title={null}
        open={drawerVisible}
        onClose={() => { setDrawerVisible(false); setDetail(null); }}
        width={700}
        loading={detailLoading}
      >
        {detail && (
          <>
            {/* Header */}
            <div className={styles.drawerHeader}>
              <div className={styles.drawerBrandInfo}>
                <div className={styles.drawerBrandName}>
                  {detail.brand_name}
                  <Tag color={detail.status === 'active' ? 'green' : 'red'} style={{ marginLeft: 8, verticalAlign: 'middle' }}>
                    {detail.status === 'active' ? '运营中' : '已停用'}
                  </Tag>
                </div>
                <div className={styles.drawerBrandMeta}>
                  <span>{CUISINE_LABELS[detail.cuisine_type] || detail.cuisine_type}</span>
                  {detail.avg_ticket_yuan && <span>人均 ¥{detail.avg_ticket_yuan}</span>}
                  <span>{detail.brand_id}</span>
                  {detail.created_at && <span>开通于 {new Date(detail.created_at).toLocaleDateString('zh-CN')}</span>}
                </div>
              </div>
              <Space>
                <Tooltip title="编辑品牌">
                  <Button icon={<EditOutlined />} onClick={openEditMerchant} />
                </Tooltip>
                <Popconfirm
                  title={`确认${detail.status === 'active' ? '停用' : '启用'}该商户？`}
                  onConfirm={() => handleToggleMerchant(detail.brand_id)}
                >
                  <Button danger={detail.status === 'active'} icon={detail.status === 'active' ? <StopOutlined /> : <CheckCircleOutlined />}>
                    {detail.status === 'active' ? '停用' : '启用'}
                  </Button>
                </Popconfirm>
              </Space>
            </div>

            <Tabs
              defaultActiveKey="overview"
              items={[
                {
                  key: 'overview',
                  label: '概览',
                  children: (
                    <>
                      {/* Group info */}
                      <div className={styles.detailSection}>
                        <div className={styles.detailSectionTitle}>
                          <span><BankOutlined /> 集团信息</span>
                          <Button type="link" size="small" icon={<EditOutlined />} onClick={openEditGroup}>编辑</Button>
                        </div>
                        <div className={styles.groupInfo}>
                          <div className={styles.groupInfoItem}>
                            <span className={styles.groupInfoLabel}>集团名称</span>
                            <span className={styles.groupInfoValue}>{detail.group.group_name}</span>
                          </div>
                          <div className={styles.groupInfoItem}>
                            <span className={styles.groupInfoLabel}>法人</span>
                            <span className={styles.groupInfoValue}>{detail.group.legal_entity}</span>
                          </div>
                          <div className={styles.groupInfoItem}>
                            <span className={styles.groupInfoLabel}>信用代码</span>
                            <span className={styles.groupInfoValue}>{detail.group.unified_social_credit_code}</span>
                          </div>
                          <div className={styles.groupInfoItem}>
                            <span className={styles.groupInfoLabel}>行业</span>
                            <span className={styles.groupInfoValue}>{INDUSTRY_LABELS[detail.group.industry_type] || detail.group.industry_type}</span>
                          </div>
                          <div className={styles.groupInfoItem}>
                            <span className={styles.groupInfoLabel}>联系人</span>
                            <span className={styles.groupInfoValue}>{detail.group.contact_person}</span>
                          </div>
                          <div className={styles.groupInfoItem}>
                            <span className={styles.groupInfoLabel}>电话</span>
                            <span className={styles.groupInfoValue}>{detail.group.contact_phone}</span>
                          </div>
                          {detail.group.address && (
                            <div className={styles.groupInfoItem} style={{ gridColumn: '1 / -1' }}>
                              <span className={styles.groupInfoLabel}>地址</span>
                              <span className={styles.groupInfoValue}>{detail.group.address}</span>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Targets */}
                      <div className={styles.detailSection}>
                        <div className={styles.detailSectionTitle}>经营目标</div>
                        <div className={styles.targetGrid}>
                          <div className={styles.targetCard}>
                            <div className={styles.targetValue}>{detail.target_food_cost_pct}%</div>
                            <div className={styles.targetLabel}>食材成本率</div>
                          </div>
                          <div className={styles.targetCard}>
                            <div className={styles.targetValue}>{detail.target_labor_cost_pct}%</div>
                            <div className={styles.targetLabel}>人力成本率</div>
                          </div>
                          <div className={styles.targetCard}>
                            <div className={styles.targetValue}>{detail.target_rent_cost_pct ?? '-'}%</div>
                            <div className={styles.targetLabel}>租金成本率</div>
                          </div>
                          <div className={styles.targetCard}>
                            <div className={styles.targetValue}>{detail.target_waste_pct}%</div>
                            <div className={styles.targetLabel}>损耗率</div>
                          </div>
                        </div>
                      </div>
                    </>
                  ),
                },
                {
                  key: 'stores',
                  label: `门店 (${detail.stores.length})`,
                  children: (
                    <div className={styles.detailSection}>
                      <div className={styles.detailSectionTitle}>
                        <span><ShopOutlined /> 门店列表</span>
                        <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => setAddStoreVisible(true)}>
                          添加门店
                        </Button>
                      </div>
                      <Table<StoreItem>
                        rowKey="id"
                        columns={storeColumns}
                        dataSource={detail.stores}
                        pagination={false}
                        size="small"
                        locale={{ emptyText: '暂无门店，点击上方按钮添加' }}
                      />
                    </div>
                  ),
                },
                {
                  key: 'users',
                  label: `用户 (${detail.users.length})`,
                  children: (
                    <div className={styles.detailSection}>
                      <div className={styles.detailSectionTitle}>
                        <span><UserAddOutlined /> 用户列表</span>
                        <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => setAddUserVisible(true)}>
                          添加用户
                        </Button>
                      </div>
                      <Table<UserItem>
                        rowKey="id"
                        columns={userColumns}
                        dataSource={detail.users}
                        pagination={false}
                        size="small"
                        locale={{ emptyText: '暂无用户，点击上方按钮添加' }}
                      />
                    </div>
                  ),
                },
                {
                  key: 'agents',
                  label: 'Agent 配置',
                  children: (
                    <AgentConfigPage brandId={detail.brand_id} brandName={detail.brand_name} />
                  ),
                },
              ]}
            />
          </>
        )}
      </Drawer>

      {/* ── Edit Merchant Modal ─────────────────────────────────────────────── */}
      <Modal title="编辑品牌信息" open={editVisible} onCancel={() => setEditVisible(false)} onOk={handleEditMerchant} width={560}>
        <Form form={editForm} layout="vertical">
          <Form.Item name="brand_name" label="品牌名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="cuisine_type" label="菜系">
                <Select options={CUISINE_OPTIONS} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="avg_ticket_yuan" label="人均消费（元）">
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Divider plain style={{ fontSize: 12, color: 'rgba(0,0,0,0.35)' }}>经营目标</Divider>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="target_food_cost_pct" label="食材成本率(%)">
                <InputNumber min={0} max={100} addonAfter="%" style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="target_labor_cost_pct" label="人力成本率(%)">
                <InputNumber min={0} max={100} addonAfter="%" style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="target_rent_cost_pct" label="租金成本率(%)">
                <InputNumber min={0} max={100} addonAfter="%" style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="target_waste_pct" label="损耗率(%)">
                <InputNumber min={0} max={100} addonAfter="%" style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* ── Edit Group Modal ────────────────────────────────────────────────── */}
      <Modal title="编辑集团信息" open={editGroupVisible} onCancel={() => setEditGroupVisible(false)} onOk={handleEditGroup} width={560}>
        <Form form={editGroupForm} layout="vertical">
          <Form.Item name="group_name" label="集团名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="legal_entity" label="法人">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="unified_social_credit_code" label="统一社会信用代码">
                <Input maxLength={18} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="contact_person" label="联系人">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="contact_phone" label="联系电话">
                <Input />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="address" label="地址">
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      {/* ── Add Store Modal ─────────────────────────────────────────────────── */}
      <Modal title="添加门店" open={addStoreVisible} onCancel={() => { setAddStoreVisible(false); storeForm.resetFields(); }} onOk={handleAddStore}>
        <Form form={storeForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="store_name" label="门店名称" rules={[{ required: true }]}>
                <Input placeholder="如：花果园店" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="store_code" label="门店编码" rules={[{ required: true }]}>
                <Input placeholder="如：GY001" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="city" label="城市"><Input /></Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="district" label="区域"><Input /></Form.Item>
            </Col>
          </Row>
          <Form.Item name="address" label="地址"><Input /></Form.Item>
          <Form.Item name="seats" label="座位数"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
        </Form>
      </Modal>

      {/* ── Add User Modal ──────────────────────────────────────────────────── */}
      <Modal title="添加用户" open={addUserVisible} onCancel={() => { setAddUserVisible(false); userForm.resetFields(); }} onOk={handleAddUser}>
        <Form form={userForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="username" label="用户名" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="full_name" label="姓名"><Input /></Form.Item>
            </Col>
          </Row>
          <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email' }]}>
            <Input prefix={<MailOutlined />} />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, min: 6 }]}>
            <Input.Password />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="role" label="角色" initialValue="waiter">
                <Select options={ROLE_OPTIONS} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="store_id" label="所属门店">
                <Select
                  allowClear
                  placeholder="可选"
                  options={detail?.stores.map(s => ({ value: s.id, label: s.name })) || []}
                />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </div>
  );
};

export default MerchantManagementPage;
