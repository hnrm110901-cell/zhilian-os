/**
 * 菜品研发 Agent — Phase 10
 * 驾驶舱 + 菜品列表 + 新建立项 + AI风险扫描
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Row, Col, Table, Tag, Space, Button, Modal, Form, Input,
  Select, Spin, Typography, Alert,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  PlusOutlined, WarningOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';
import { ZCard, ZKpi } from '../design-system/components';
import AgentWorkspaceTemplate from '../components/AgentWorkspaceTemplate';

const { Text } = Typography;
const { Option } = Select;

// ── 状态 / 类型 映射 ───────────────────────────────────────────────────────────
const DISH_STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft:         { label: '草稿',   color: 'default' },
  ideation:      { label: '洞察',   color: 'cyan' },
  in_dev:        { label: '研发中', color: 'processing' },
  sampling:      { label: '样品',   color: 'blue' },
  pilot_pending: { label: '待试点', color: 'warning' },
  piloting:      { label: '试点中', color: 'gold' },
  launch_ready:  { label: '待上市', color: 'lime' },
  launched:      { label: '已上市', color: 'success' },
  optimizing:    { label: '优化中', color: 'purple' },
  discontinued:  { label: '停售',   color: 'error' },
  archived:      { label: '归档',   color: 'default' },
};

const DISH_TYPE_MAP: Record<string, string> = {
  main_course: '主菜',
  appetizer:   '前菜',
  soup:        '汤品',
  dessert:     '甜品',
  beverage:    '饮品',
  side_dish:   '小食',
  combo:       '套餐',
  seasonal:    '季节限定',
  innovation:  '创新菜',
};

// ── 类型定义 ───────────────────────────────────────────────────────────────────
interface DashboardData {
  total_dishes:    number;
  in_dev_count:    number;
  active_pilots:   number;
  avg_margin_rate: number;
  high_risk_count: number;
}

interface DishSummary {
  id:                string;
  dish_code:         string;
  dish_name:         string;
  dish_type:         string;
  status:            string;
  target_price_yuan: number | null;
  flavor_tags:       string[];
}

interface RiskItem {
  dish_id:     string;
  dish_name:   string;
  risk_level:  string;
  description: string;
}

interface RiskResult {
  risk_count:    number;
  high_risks:    RiskItem[];
  medium_risks:  RiskItem[];
  risks:         RiskItem[];
}

// ── 主组件 ─────────────────────────────────────────────────────────────────────
export default function DishRdPage() {
  const navigate  = useNavigate();
  const brandId   = localStorage.getItem('brand_id') || 'B001';

  const [dashboard,    setDashboard]    = useState<DashboardData | null>(null);
  const [dishes,       setDishes]       = useState<DishSummary[]>([]);
  const [dashLoading,  setDashLoading]  = useState(false);
  const [listLoading,  setListLoading]  = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [search,       setSearch]       = useState('');

  // 新建菜品
  const [createOpen,    setCreateOpen]    = useState(false);
  const [createLoading, setCreateLoading] = useState(false);
  const [form] = Form.useForm();

  // 风险扫描
  const [riskOpen,    setRiskOpen]    = useState(false);
  const [riskLoading, setRiskLoading] = useState(false);
  const [riskResult,  setRiskResult]  = useState<RiskResult | null>(null);

  // ── 数据加载 ──────────────────────────────────────────────────────────────────
  const loadDashboard = useCallback(async () => {
    setDashLoading(true);
    try {
      const res = await apiClient.get<DashboardData>(
        `/api/v1/dish-rd/brands/${brandId}/dashboard`
      );
      setDashboard(res);
    } catch (e) {
      handleApiError(e, '加载驾驶舱失败');
    } finally {
      setDashLoading(false);
    }
  }, [brandId]);

  const loadDishes = useCallback(async () => {
    setListLoading(true);
    try {
      const params: Record<string, any> = { limit: 100 };
      if (statusFilter) params.status   = statusFilter;
      if (search.trim()) params.keyword = search.trim();
      const res = await apiClient.get<DishSummary[]>(
        `/api/v1/dish-rd/brands/${brandId}/dishes`, { params }
      );
      setDishes(res);
    } catch (e) {
      handleApiError(e, '加载菜品列表失败');
    } finally {
      setListLoading(false);
    }
  }, [brandId, statusFilter, search]);

  useEffect(() => { loadDashboard(); }, [loadDashboard]);
  useEffect(() => { loadDishes();    }, [loadDishes]);

  // ── 操作 ──────────────────────────────────────────────────────────────────────
  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      setCreateLoading(true);
      await apiClient.post(`/api/v1/dish-rd/brands/${brandId}/dishes`, {
        ...values,
        target_price_yuan: values.target_price_yuan
          ? Number(values.target_price_yuan) : null,
      });
      showSuccess('菜品立项成功');
      setCreateOpen(false);
      form.resetFields();
      loadDashboard();
      loadDishes();
    } catch (e: any) {
      if (e?.errorFields) return; // form validation
      handleApiError(e, '创建失败');
    } finally {
      setCreateLoading(false);
    }
  };

  const handleRiskScan = async () => {
    setRiskResult(null);
    setRiskOpen(true);
    setRiskLoading(true);
    try {
      const res = await apiClient.get<RiskResult>(
        `/api/v1/dish-rd/brands/${brandId}/agent/risk-scan`
      );
      setRiskResult(res);
    } catch (e) {
      handleApiError(e, '风险扫描失败');
      setRiskOpen(false);
    } finally {
      setRiskLoading(false);
    }
  };

  // ── 表格列 ────────────────────────────────────────────────────────────────────
  const columns: ColumnsType<DishSummary> = [
    {
      title: '菜品编码', dataIndex: 'dish_code', width: 130,
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: '菜品名称', dataIndex: 'dish_name',
      render: (v: string, row) => (
        <a onClick={() => navigate(`/dish-rd/${row.id}`)}>{v}</a>
      ),
    },
    {
      title: '类型', dataIndex: 'dish_type', width: 90,
      render: (v: string) => DISH_TYPE_MAP[v] ?? v,
    },
    {
      title: '状态', dataIndex: 'status', width: 100,
      render: (v: string) => {
        const cfg = DISH_STATUS_MAP[v];
        return cfg ? <Tag color={cfg.color}>{cfg.label}</Tag> : <Tag>{v}</Tag>;
      },
    },
    {
      title: '目标售价', dataIndex: 'target_price_yuan', width: 100,
      render: (v: number | null) => v != null ? `¥${v.toFixed(0)}` : '—',
    },
    {
      title: '风味标签', dataIndex: 'flavor_tags',
      render: (tags: string[]) =>
        (tags ?? []).slice(0, 3).map(t => <Tag key={t}>{t}</Tag>),
    },
    {
      title: '操作', width: 90,
      render: (_: any, row) => (
        <Button size="small" type="link" onClick={() => navigate(`/dish-rd/${row.id}`)}>
          详情
        </Button>
      ),
    },
  ];

  // ── 渲染 ──────────────────────────────────────────────────────────────────────
  const templateKpis = dashboard ? [
    { label: '菜品总数',   value: dashboard.total_dishes,                              unit: '道' },
    { label: '研发中',     value: dashboard.in_dev_count,                              unit: '道' },
    { label: '活跃试点',   value: dashboard.active_pilots,                             unit: '项' },
    { label: '平均毛利率', value: (dashboard.avg_margin_rate * 100).toFixed(1),        unit: '%'  },
    { label: '高风险预警', value: dashboard.high_risk_count,                           unit: '项',
      valueColor: dashboard.high_risk_count > 0 ? '#ff4d4f' : undefined },
  ] : [];

  const pageContent = (
    <>
      {/* 菜品列表 */}
      <ZCard
        title="菜品研发列表"
        extra={
          <Space>
            <Button icon={<WarningOutlined />} onClick={handleRiskScan}>
              AI风险扫描
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              新建菜品
            </Button>
          </Space>
        }
      >
        <Space style={{ marginBottom: 16 }}>
          <Select
            allowClear placeholder="全部状态" style={{ width: 130 }}
            value={statusFilter} onChange={v => setStatusFilter(v)}
          >
            {Object.entries(DISH_STATUS_MAP).map(([k, v]) => (
              <Option key={k} value={k}>{v.label}</Option>
            ))}
          </Select>
          <Input.Search
            placeholder="菜品名 / 编码"
            value={search}
            onChange={e => setSearch(e.target.value)}
            onSearch={loadDishes}
            style={{ width: 200 }}
            allowClear
          />
        </Space>

        <Table
          loading={listLoading}
          dataSource={dishes}
          columns={columns}
          rowKey="id"
          size="middle"
          pagination={{ pageSize: 20 }}
          onRow={row => ({ style: { cursor: 'pointer' }, onClick: () => navigate(`/dish-rd/${row.id}`) })}
        />
      </ZCard>

      {/* 新建菜品 Modal */}
      <Modal
        title="新建菜品立项"
        open={createOpen}
        onCancel={() => { setCreateOpen(false); form.resetFields(); }}
        onOk={handleCreate}
        confirmLoading={createLoading}
        width={520}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="dish_name" label="菜品名称" rules={[{ required: true, message: '请填写菜品名称' }]}>
            <Input placeholder="如：招牌红烧肉" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="dish_type" label="菜品类型" rules={[{ required: true, message: '请选择类型' }]}>
                <Select>
                  {Object.entries(DISH_TYPE_MAP).map(([k, v]) => (
                    <Option key={k} value={k}>{v}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="target_price_yuan" label="目标售价（元）">
                <Input type="number" min={0} placeholder="68" suffix="元" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="positioning" label="产品定位">
                <Select allowClear>
                  <Option value="signature">招牌菜</Option>
                  <Option value="traffic">引流菜</Option>
                  <Option value="profit">利润菜</Option>
                  <Option value="seasonal">季节限定</Option>
                  <Option value="innovation">创新研发</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="category_id" label="菜品分类ID">
                <Input placeholder="可选" />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* AI风险扫描 Modal */}
      <Modal
        title="AI 全品类风险扫描"
        open={riskOpen}
        onCancel={() => setRiskOpen(false)}
        footer={<Button onClick={() => setRiskOpen(false)}>关闭</Button>}
        width={600}
        destroyOnClose
      >
        {riskLoading ? (
          <div style={{ textAlign: 'center', padding: 48 }}>
            <Spin size="large" tip="正在扫描..." />
          </div>
        ) : riskResult ? (
          <div>
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={8}>
                <ZKpi label="总风险数" value={riskResult.risk_count} unit="项" />
              </Col>
              <Col span={8}>
                <ZKpi label="高风险" value={riskResult.high_risks?.length ?? 0} unit="项" />
              </Col>
              <Col span={8}>
                <ZKpi label="中风险" value={riskResult.medium_risks?.length ?? 0} unit="项" />
              </Col>
            </Row>
            {(riskResult.risks ?? []).length > 0 ? (
              riskResult.risks.map((r, i) => (
                <Alert
                  key={i}
                  type={r.risk_level === 'high' ? 'error' : 'warning'}
                  message={
                    <Space>
                      <a onClick={() => { setRiskOpen(false); navigate(`/dish-rd/${r.dish_id}`); }}>
                        {r.dish_name}
                      </a>
                      <Tag color={r.risk_level === 'high' ? 'red' : 'orange'}>
                        {r.risk_level === 'high' ? '高风险' : '中风险'}
                      </Tag>
                    </Space>
                  }
                  description={r.description}
                  style={{ marginBottom: 8 }}
                  showIcon
                />
              ))
            ) : (
              <Alert type="success" message="当前无风险预警，所有菜品状态正常" showIcon />
            )}
          </div>
        ) : null}
      </Modal>
    </>
  );

  return (
    <AgentWorkspaceTemplate
      agentName="菜品研发 Agent"
      agentIcon="🍽️"
      agentColor="#52c41a"
      description="菜品立项 · 研发跟踪 · 试点管理 · AI 风险扫描"
      status={dashboard?.high_risk_count ? 'warning' : 'running'}
      kpis={templateKpis}
      kpiLoading={dashLoading}
      tabs={[{ key: 'list', label: '菜品列表', children: pageContent }]}
      defaultTab="list"
      loading={dashLoading}
      onRefresh={() => { loadDashboard(); loadDishes(); }}
    />
  );
}
