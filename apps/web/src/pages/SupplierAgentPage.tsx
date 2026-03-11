// SupplierAgentPage.tsx — Phase 11 供应商管理 Agent 工作台
// 路由：/supplier-agent（admin 权限）
import React, { useState, useEffect, useCallback } from 'react';
import { Tabs, Table, Tag, Button, Modal, Form, Input, InputNumber,
         Select, DatePicker, message, Statistic, Row, Col, Badge,
         Tooltip, Progress, Drawer, Descriptions, Space, Alert, Spin } from 'antd';
import {
  ShoppingOutlined, FileProtectOutlined, AlertOutlined,
  ThunderboltOutlined, RiseOutlined, DollarOutlined,
  CheckCircleOutlined, ExclamationCircleOutlined, SyncOutlined,
} from '@ant-design/icons';
import ZCard from '../design-system/components/ZCard';
import ZKpi from '../design-system/components/ZKpi';
import ZSkeleton from '../design-system/components/ZSkeleton';
import { apiClient } from '../utils/apiClient';
import styles from './SupplierAgentPage.module.css';

const { Option } = Select;
const { TabPane } = Tabs;

// ── Types ────────────────────────────────────────────────────────────────────

interface DashboardData {
  supplier_tier_distribution: { strategic: number; preferred: number; approved: number; probation: number };
  active_contracts: number;
  unresolved_alerts: number;
  pending_sourcing_recommendations: number;
  monthly_estimated_saving_yuan: number;
  data_as_of: string;
}

interface SupplierProfile {
  id: string;
  supplier_id: string;
  tier: string;
  composite_score: number;
  price_score: number;
  quality_score: number;
  delivery_score: number;
  service_score: number;
  risk_flags: string[];
  last_rated_at: string | null;
}

interface SupplierContract {
  id: string;
  contract_no: string;
  contract_name: string;
  supplier_id: string;
  start_date: string;
  end_date: string;
  days_to_expiry: number;
  status: string;
  annual_value_yuan: number;
  auto_renew: boolean;
}

interface Alert {
  id: string;
  alert_type: string;
  risk_level: string;
  title: string;
  days_to_expiry?: number;
  financial_impact_yuan: number;
  recommended_action?: string;
  mitigation_plan?: string;
  probability?: number;
  created_at: string;
}

interface SourcingRec {
  id: string;
  material_name: string;
  required_qty: number;
  needed_by_date: string;
  recommended_supplier_id: string;
  recommended_price_yuan: number;
  estimated_total_yuan: number;
  estimated_saving_yuan: number;
  sourcing_strategy: string;
  confidence: number;
  status: string;
}

// ── 常量 ─────────────────────────────────────────────────────────────────────

const TIER_COLOR: Record<string, string> = {
  strategic: 'purple', preferred: 'blue', approved: 'green', probation: 'orange', suspended: 'red',
};
const TIER_LABEL: Record<string, string> = {
  strategic: '战略', preferred: '优选', approved: '合格', probation: '试用', suspended: '暂停',
};
const RISK_COLOR: Record<string, string> = {
  critical: 'error', high: 'warning', medium: 'processing', low: 'success',
};

// ── 组件 ─────────────────────────────────────────────────────────────────────

const SupplierAgentPage: React.FC = () => {
  const brandId = localStorage.getItem('brand_id') || 'BRAND001';
  const [activeTab, setActiveTab] = useState('dashboard');

  // Dashboard
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [dashLoading, setDashLoading] = useState(true);

  // 供应商档案
  const [profiles, setProfiles] = useState<SupplierProfile[]>([]);
  const [profilesLoading, setProfilesLoading] = useState(false);

  // 合同
  const [contracts, setContracts] = useState<SupplierContract[]>([]);
  const [contractsLoading, setContractsLoading] = useState(false);

  // 预警
  const [alerts, setAlerts] = useState<{ contract_alerts: Alert[]; supply_risks: Alert[]; total_unresolved: number }>({
    contract_alerts: [], supply_risks: [], total_unresolved: 0,
  });
  const [alertsLoading, setAlertsLoading] = useState(false);

  // 寻源推荐
  const [sourcingRecs, setSourcingRecs] = useState<SourcingRec[]>([]);
  const [sourcingLoading, setSourcingLoading] = useState(false);

  // Agent 操作状态
  const [scanning, setScanning] = useState(false);
  const [ratingModal, setRatingModal] = useState(false);
  const [ratingForm] = Form.useForm();

  // 详情抽屉
  const [detailDrawer, setDetailDrawer] = useState<{ open: boolean; item: Alert | null }>({ open: false, item: null });

  // ── 数据加载 ────────────────────────────────────────────────────────────────

  const loadDashboard = useCallback(async () => {
    try {
      setDashLoading(true);
      const data = await apiClient.get(`/api/v1/supplier-agent/dashboard?brand_id=${brandId}`);
      setDashboard(data as DashboardData);
    } catch {
      message.error('加载驾驶舱失败');
    } finally {
      setDashLoading(false);
    }
  }, [brandId]);

  const loadProfiles = useCallback(async () => {
    try {
      setProfilesLoading(true);
      const data = await apiClient.get(`/api/v1/supplier-agent/profiles?brand_id=${brandId}`);
      setProfiles((data as any).items || []);
    } catch {
      message.error('加载供应商档案失败');
    } finally {
      setProfilesLoading(false);
    }
  }, [brandId]);

  const loadContracts = useCallback(async () => {
    try {
      setContractsLoading(true);
      const data = await apiClient.get(`/api/v1/supplier-agent/contracts?brand_id=${brandId}`);
      setContracts((data as any).items || []);
    } catch {
      message.error('加载合同失败');
    } finally {
      setContractsLoading(false);
    }
  }, [brandId]);

  const loadAlerts = useCallback(async () => {
    try {
      setAlertsLoading(true);
      const data = await apiClient.get(`/api/v1/supplier-agent/alerts?brand_id=${brandId}&is_resolved=false`);
      setAlerts(data as any);
    } catch {
      message.error('加载预警失败');
    } finally {
      setAlertsLoading(false);
    }
  }, [brandId]);

  const loadSourcing = useCallback(async () => {
    try {
      setSourcingLoading(true);
      const data = await apiClient.get(`/api/v1/supplier-agent/sourcing-recommendations?brand_id=${brandId}&status=pending`);
      setSourcingRecs((data as any).items || []);
    } catch {
      message.error('加载寻源推荐失败');
    } finally {
      setSourcingLoading(false);
    }
  }, [brandId]);

  useEffect(() => { loadDashboard(); }, [loadDashboard]);

  useEffect(() => {
    if (activeTab === 'profiles') loadProfiles();
    if (activeTab === 'contracts') loadContracts();
    if (activeTab === 'alerts') loadAlerts();
    if (activeTab === 'sourcing') loadSourcing();
  }, [activeTab, loadProfiles, loadContracts, loadAlerts, loadSourcing]);

  // ── Agent 操作 ──────────────────────────────────────────────────────────────

  const handleScanContractRisk = async () => {
    setScanning(true);
    try {
      const result = await apiClient.post(`/api/v1/supplier-agent/agents/scan-contract-risk?brand_id=${brandId}`, {});
      message.success(`合同风险扫描完成：发现 ${(result as any).alerts_created} 条新预警`);
      loadDashboard();
      if (activeTab === 'alerts') loadAlerts();
    } catch {
      message.error('扫描失败，请重试');
    } finally {
      setScanning(false);
    }
  };

  const handleScanSupplyRisk = async () => {
    setScanning(true);
    try {
      const result = await apiClient.post(`/api/v1/supplier-agent/agents/scan-supply-risk?brand_id=${brandId}`, {});
      message.success(`供应链风险扫描完成：发现 ${(result as any).events_created} 条新风险`);
      loadDashboard();
      if (activeTab === 'alerts') loadAlerts();
    } catch {
      message.error('扫描失败，请重试');
    } finally {
      setScanning(false);
    }
  };

  const handleRateSupplier = async (values: any) => {
    try {
      const result = await apiClient.post('/api/v1/supplier-agent/agents/rate-supplier', {
        brand_id: brandId,
        supplier_id: values.supplier_id,
        eval_period: values.eval_period,
        service_score: values.service_score,
      });
      const r = result as any;
      message.success(`评级完成：综合得分 ${r.composite_score?.toFixed(1)} 分，建议分级 ${r.tier_suggestion}`);
      setRatingModal(false);
      ratingForm.resetFields();
      if (activeTab === 'profiles') loadProfiles();
    } catch {
      message.error('评级失败');
    }
  };

  const handleAcceptSourcing = async (recId: string) => {
    try {
      await apiClient.put(`/api/v1/supplier-agent/sourcing-recommendations/${recId}/accept`, {});
      message.success('已接受寻源推荐');
      loadSourcing();
      loadDashboard();
    } catch {
      message.error('操作失败');
    }
  };

  const handleResolveAlert = async (alertId: string, type: 'contract' | 'supply') => {
    try {
      const endpoint = type === 'contract'
        ? `/api/v1/supplier-agent/alerts/contract/${alertId}/resolve`
        : `/api/v1/supplier-agent/alerts/supply/${alertId}/resolve`;
      await apiClient.put(endpoint, { resolved_by: 'current_user' });
      message.success('已标记为已处理');
      loadAlerts();
      loadDashboard();
    } catch {
      message.error('操作失败');
    }
  };

  // ── 表格列定义 ──────────────────────────────────────────────────────────────

  const profileColumns = [
    { title: '供应商ID', dataIndex: 'supplier_id', key: 'supplier_id', width: 120,
      render: (v: string) => <span className={styles.code}>{v?.slice(0, 8)}...</span> },
    { title: '分级', dataIndex: 'tier', key: 'tier', width: 80,
      render: (t: string) => <Tag color={TIER_COLOR[t]}>{TIER_LABEL[t] || t}</Tag> },
    { title: '综合得分', dataIndex: 'composite_score', key: 'composite_score', width: 120,
      render: (v: number) => (
        <Progress percent={v} size="small" status={v >= 70 ? 'success' : v >= 50 ? 'normal' : 'exception'}
                  format={(p) => `${p?.toFixed(0)}`} />
      ),
    },
    { title: '价格', dataIndex: 'price_score', key: 'price_score', width: 80,
      render: (v: number) => <span style={{ color: v >= 70 ? '#52c41a' : '#fa8c16' }}>{v?.toFixed(0)}</span> },
    { title: '质量', dataIndex: 'quality_score', key: 'quality_score', width: 80,
      render: (v: number) => <span style={{ color: v >= 70 ? '#52c41a' : '#fa8c16' }}>{v?.toFixed(0)}</span> },
    { title: '交期', dataIndex: 'delivery_score', key: 'delivery_score', width: 80,
      render: (v: number) => <span style={{ color: v >= 70 ? '#52c41a' : '#fa8c16' }}>{v?.toFixed(0)}</span> },
    { title: '风险标签', dataIndex: 'risk_flags', key: 'risk_flags',
      render: (flags: string[]) => (
        <>
          {(flags || []).map(f => <Tag key={f} color="red" style={{ fontSize: 11 }}>{f}</Tag>)}
        </>
      ),
    },
    { title: '最近评级', dataIndex: 'last_rated_at', key: 'last_rated_at', width: 120,
      render: (v: string | null) => v ? v.slice(0, 10) : <Tag color="default">未评级</Tag> },
  ];

  const contractColumns = [
    { title: '合同编号', dataIndex: 'contract_no', key: 'contract_no', width: 140 },
    { title: '合同名称', dataIndex: 'contract_name', key: 'contract_name', ellipsis: true },
    { title: '到期日', dataIndex: 'end_date', key: 'end_date', width: 110 },
    {
      title: '剩余天数', dataIndex: 'days_to_expiry', key: 'days_to_expiry', width: 100,
      render: (d: number) => (
        <Tag color={d <= 7 ? 'red' : d <= 30 ? 'orange' : 'green'}>
          {d > 0 ? `${d}天` : '已到期'}
        </Tag>
      ),
    },
    { title: '年度金额', dataIndex: 'annual_value_yuan', key: 'annual_value_yuan', width: 120,
      render: (v: number) => `¥${(v || 0).toLocaleString()}` },
    { title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (s: string) => {
        const map: Record<string, string> = { active: 'success', expiring: 'warning', expired: 'error', draft: 'default' };
        const label: Record<string, string> = { active: '生效中', expiring: '即将到期', expired: '已到期', draft: '草稿' };
        return <Badge status={map[s] as any || 'default'} text={label[s] || s} />;
      },
    },
    { title: '自动续签', dataIndex: 'auto_renew', key: 'auto_renew', width: 80,
      render: (v: boolean) => v ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : '—' },
  ];

  const alertColumns = (type: 'contract' | 'supply') => [
    { title: '预警标题', dataIndex: 'title', key: 'title', ellipsis: true },
    { title: '风险等级', dataIndex: 'risk_level', key: 'risk_level', width: 90,
      render: (r: string) => <Badge status={RISK_COLOR[r] as any} text={r?.toUpperCase()} /> },
    { title: '潜在¥损失', dataIndex: 'financial_impact_yuan', key: 'financial_impact_yuan', width: 110,
      render: (v: number) => v ? `¥${v.toLocaleString()}` : '—' },
    { title: '建议行动', dataIndex: type === 'contract' ? 'recommended_action' : 'mitigation_plan',
      key: 'action', ellipsis: true,
      render: (v: string) => <Tooltip title={v}><span>{v?.slice(0, 40)}...</span></Tooltip> },
    { title: '操作', key: 'ops', width: 100,
      render: (_: any, record: Alert) => (
        <Space size={4}>
          <Button size="small" onClick={() => setDetailDrawer({ open: true, item: record })}>详情</Button>
          <Button size="small" type="primary" danger
                  onClick={() => handleResolveAlert(record.id, type)}>已处理</Button>
        </Space>
      ),
    },
  ];

  const sourcingColumns = [
    { title: '物料名称', dataIndex: 'material_name', key: 'material_name', width: 120 },
    { title: '需求量', dataIndex: 'required_qty', key: 'required_qty', width: 80 },
    { title: '最迟到货', dataIndex: 'needed_by_date', key: 'needed_by_date', width: 110 },
    { title: '推荐单价', dataIndex: 'recommended_price_yuan', key: 'recommended_price_yuan', width: 100,
      render: (v: number) => `¥${v?.toFixed(4)}` },
    { title: '预计总额', dataIndex: 'estimated_total_yuan', key: 'estimated_total_yuan', width: 100,
      render: (v: number) => `¥${v?.toFixed(2)}` },
    { title: '预计节省', dataIndex: 'estimated_saving_yuan', key: 'estimated_saving_yuan', width: 100,
      render: (v: number) => (
        <span style={{ color: v > 0 ? '#52c41a' : '#f5222d' }}>
          {v > 0 ? '+' : ''}{`¥${v?.toFixed(2)}`}
        </span>
      ),
    },
    { title: '策略', dataIndex: 'sourcing_strategy', key: 'sourcing_strategy', width: 80,
      render: (s: string) => <Tag>{s === 'single' ? '单一采购' : s === 'split' ? '分拆采购' : s}</Tag> },
    { title: '置信度', dataIndex: 'confidence', key: 'confidence', width: 80,
      render: (v: number) => `${(v * 100).toFixed(0)}%` },
    { title: '操作', key: 'ops', width: 100,
      render: (_: any, r: SourcingRec) => (
        <Button size="small" type="primary" icon={<CheckCircleOutlined />}
                onClick={() => handleAcceptSourcing(r.id)}>
          接受
        </Button>
      ),
    },
  ];

  // ── 渲染 ─────────────────────────────────────────────────────────────────────

  const tierDist = dashboard?.supplier_tier_distribution;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>
          <ShoppingOutlined className={styles.titleIcon} />
          供应商管理 Agent
        </div>
        <Space>
          <Button icon={<SyncOutlined spin={scanning} />} onClick={handleScanContractRisk}
                  loading={scanning} disabled={scanning}>
            扫描合同风险
          </Button>
          <Button icon={<AlertOutlined />} onClick={handleScanSupplyRisk}
                  loading={scanning} disabled={scanning}>
            扫描供应链风险
          </Button>
          <Button type="primary" icon={<ThunderboltOutlined />}
                  onClick={() => setRatingModal(true)}>
            触发评级
          </Button>
        </Space>
      </div>

      <Tabs activeKey={activeTab} onChange={setActiveTab} className={styles.tabs}>

        {/* ── 驾驶舱 ── */}
        <TabPane tab="驾驶舱" key="dashboard">
          {dashLoading ? (
            <ZSkeleton rows={4} />
          ) : dashboard ? (
            <>
              {dashboard.unresolved_alerts > 0 && (
                <Alert
                  type="warning"
                  message={`当前有 ${dashboard.unresolved_alerts} 条未处理预警，请及时处理`}
                  style={{ marginBottom: 16 }}
                  showIcon
                />
              )}
              <Row gutter={16} style={{ marginBottom: 16 }}>
                <Col span={6}>
                  <ZCard>
                    <Statistic title="本月预计节省¥" value={dashboard.monthly_estimated_saving_yuan}
                               precision={2} prefix={<DollarOutlined />}
                               valueStyle={{ color: '#52c41a' }} />
                  </ZCard>
                </Col>
                <Col span={6}>
                  <ZCard>
                    <Statistic title="活跃合同数" value={dashboard.active_contracts}
                               prefix={<FileProtectOutlined />} />
                  </ZCard>
                </Col>
                <Col span={6}>
                  <ZCard>
                    <Statistic title="未处理预警" value={dashboard.unresolved_alerts}
                               prefix={<AlertOutlined />}
                               valueStyle={{ color: dashboard.unresolved_alerts > 0 ? '#f5222d' : '#52c41a' }} />
                  </ZCard>
                </Col>
                <Col span={6}>
                  <ZCard>
                    <Statistic title="待处理寻源推荐" value={dashboard.pending_sourcing_recommendations}
                               prefix={<RiseOutlined />} />
                  </ZCard>
                </Col>
              </Row>

              <Row gutter={16}>
                <Col span={12}>
                  <ZCard title="供应商分级分布">
                    <div className={styles.tierDist}>
                      {[
                        { key: 'strategic', label: '战略级', color: '#722ed1' },
                        { key: 'preferred', label: '优选级', color: '#1890ff' },
                        { key: 'approved',  label: '合格级', color: '#52c41a' },
                        { key: 'probation', label: '试用期', color: '#fa8c16' },
                      ].map(({ key, label, color }) => (
                        <div key={key} className={styles.tierRow}>
                          <Tag color={color}>{label}</Tag>
                          <Progress
                            percent={Math.round(
                              ((tierDist as any)?.[key] || 0) /
                              Math.max(Object.values(tierDist || {}).reduce((a: any, b: any) => a + b, 0), 1) * 100
                            )}
                            size="small"
                            strokeColor={color}
                            style={{ flex: 1, margin: '0 8px' }}
                          />
                          <span className={styles.tierCount}>{(tierDist as any)?.[key] || 0} 家</span>
                        </div>
                      ))}
                    </div>
                  </ZCard>
                </Col>
                <Col span={12}>
                  <ZCard title="快速操作">
                    <div className={styles.quickActions}>
                      <Button block icon={<FileProtectOutlined />} onClick={() => setActiveTab('contracts')}
                              style={{ marginBottom: 8 }}>
                        查看合同列表
                      </Button>
                      <Button block icon={<AlertOutlined />} onClick={() => setActiveTab('alerts')}
                              style={{ marginBottom: 8 }}
                              danger={dashboard.unresolved_alerts > 0}>
                        处理预警 {dashboard.unresolved_alerts > 0 && `(${dashboard.unresolved_alerts})`}
                      </Button>
                      <Button block icon={<RiseOutlined />} onClick={() => setActiveTab('sourcing')}>
                        处理寻源推荐 {dashboard.pending_sourcing_recommendations > 0
                          && `(${dashboard.pending_sourcing_recommendations})`}
                      </Button>
                    </div>
                  </ZCard>
                </Col>
              </Row>
            </>
          ) : null}
        </TabPane>

        {/* ── 供应商档案 ── */}
        <TabPane tab={`供应商档案`} key="profiles">
          <Table
            dataSource={profiles}
            columns={profileColumns}
            rowKey="id"
            loading={profilesLoading}
            pagination={{ pageSize: 20 }}
            size="small"
          />
        </TabPane>

        {/* ── 合同管理 ── */}
        <TabPane tab={`合同管理（${contracts.length}）`} key="contracts">
          <Table
            dataSource={contracts}
            columns={contractColumns}
            rowKey="id"
            loading={contractsLoading}
            pagination={{ pageSize: 20 }}
            size="small"
          />
        </TabPane>

        {/* ── 预警中心 ── */}
        <TabPane tab={
          <span>
            预警中心
            {alerts.total_unresolved > 0 && (
              <Badge count={alerts.total_unresolved} style={{ marginLeft: 4 }} />
            )}
          </span>
        } key="alerts">
          {alertsLoading ? <Spin /> : (
            <>
              <ZCard title={`合同预警（${alerts.contract_alerts.length}）`} style={{ marginBottom: 16 }}>
                <Table dataSource={alerts.contract_alerts}
                       columns={alertColumns('contract')}
                       rowKey="id" size="small" pagination={false} />
              </ZCard>
              <ZCard title={`供应链风险（${alerts.supply_risks.length}）`}>
                <Table dataSource={alerts.supply_risks}
                       columns={alertColumns('supply')}
                       rowKey="id" size="small" pagination={false} />
              </ZCard>
            </>
          )}
        </TabPane>

        {/* ── 寻源推荐 ── */}
        <TabPane tab={`寻源推荐（${sourcingRecs.length}）`} key="sourcing">
          <Table
            dataSource={sourcingRecs}
            columns={sourcingColumns}
            rowKey="id"
            loading={sourcingLoading}
            pagination={{ pageSize: 20 }}
            size="small"
          />
        </TabPane>

      </Tabs>

      {/* 预警详情抽屉 */}
      <Drawer
        title={detailDrawer.item?.title}
        open={detailDrawer.open}
        onClose={() => setDetailDrawer({ open: false, item: null })}
        width={480}
      >
        {detailDrawer.item && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="风险等级">
              <Badge status={RISK_COLOR[detailDrawer.item.risk_level] as any}
                     text={detailDrawer.item.risk_level?.toUpperCase()} />
            </Descriptions.Item>
            {detailDrawer.item.days_to_expiry !== undefined && (
              <Descriptions.Item label="距到期天数">{detailDrawer.item.days_to_expiry} 天</Descriptions.Item>
            )}
            {detailDrawer.item.probability !== undefined && (
              <Descriptions.Item label="发生概率">{(detailDrawer.item.probability * 100).toFixed(0)}%</Descriptions.Item>
            )}
            <Descriptions.Item label="潜在¥损失">
              ¥{(detailDrawer.item.financial_impact_yuan || 0).toLocaleString()}
            </Descriptions.Item>
            <Descriptions.Item label="建议行动">
              {detailDrawer.item.recommended_action || detailDrawer.item.mitigation_plan || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="发现时间">{detailDrawer.item.created_at?.slice(0, 10)}</Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>

      {/* 供应商评级 Modal */}
      <Modal
        title="触发供应商综合评级"
        open={ratingModal}
        onCancel={() => { setRatingModal(false); ratingForm.resetFields(); }}
        onOk={() => ratingForm.submit()}
        okText="开始评级"
      >
        <Form form={ratingForm} layout="vertical" onFinish={handleRateSupplier}>
          <Form.Item name="supplier_id" label="供应商ID" rules={[{ required: true }]}>
            <Input placeholder="输入供应商ID" />
          </Form.Item>
          <Form.Item name="eval_period" label="评估月份（如：2026-03）" rules={[{ required: true }]}>
            <Input placeholder="2026-03" />
          </Form.Item>
          <Form.Item name="service_score" label="服务评分（0-100，可选）">
            <InputNumber min={0} max={100} style={{ width: '100%' }} placeholder="留空使用默认75分" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default SupplierAgentPage;
