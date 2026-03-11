// BusinessIntelPage.tsx — Phase 12 经营智能体工作台
// 路由：/business-intel（admin 权限）
import React, { useState, useEffect, useCallback } from 'react';
import {
  Tabs, Table, Tag, Button, Modal, Form, Input, InputNumber,
  Select, DatePicker, message, Statistic, Row, Col, Badge,
  Tooltip, Progress, Drawer, Descriptions, Space, Alert, Spin,
} from 'antd';
import {
  BarChartOutlined, RiseOutlined, FallOutlined, DollarOutlined,
  CheckCircleOutlined, ExclamationCircleOutlined, SyncOutlined,
  RobotOutlined, BulbOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import ZCard from '../design-system/components/ZCard';
import ZKpi from '../design-system/components/ZKpi';
import ZSkeleton from '../design-system/components/ZSkeleton';
import { apiClient } from '../utils/apiClient';
import styles from './BusinessIntelPage.module.css';

const { TabPane } = Tabs;
const { Option } = Select;

// ── Types ────────────────────────────────────────────────────────────────────

interface DashboardData {
  brand_id: string;
  store_id: string;
  today: string;
  today_decision: {
    id: string | null;
    total_saving_yuan: number;
    priority: string | null;
    top3: Array<{ rank: number; action: string; saving_yuan: number; confidence: number }>;
  };
  open_alerts: {
    count: number;
    critical_count: number;
    top_alert: { level: string; impact_yuan: number; action: string } | null;
  };
  kpi_health: {
    overall_score: number | null;
    at_risk_count: number;
    period: string | null;
  };
  forecast_7d: {
    predicted_revenue_yuan: number | null;
    trend_direction: string;
    confidence: number | null;
  };
}

interface RevenueAlert {
  id: string;
  store_id: string;
  alert_date: string;
  anomaly_level: string;
  deviation_pct: number;
  impact_yuan: number;
  recommended_action: string;
  is_resolved: boolean;
}

interface Decision {
  id: string;
  store_id: string;
  decision_date: string;
  total_saving_yuan: number;
  priority: string;
  status: string;
  top_recommendation: { rank: number; action: string; saving_yuan: number } | null;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const DEFAULT_BRAND = 'B001';
const DEFAULT_STORE = 'S001';

const ANOMALY_COLOR: Record<string, string> = {
  normal: 'green', warning: 'gold', critical: 'orange', severe: 'red',
};

const PRIORITY_COLOR: Record<string, string> = {
  p0: 'red', p1: 'orange', p2: 'blue', p3: 'default',
};

const STATUS_COLOR: Record<string, string> = {
  pending: 'blue', accepted: 'green', rejected: 'red', executed: 'purple',
};

const TREND_ICON: Record<string, React.ReactNode> = {
  up: <RiseOutlined style={{ color: '#52c41a' }} />,
  down: <FallOutlined style={{ color: '#ff4d4f' }} />,
  stable: <BarChartOutlined style={{ color: '#1890ff' }} />,
};

// ── Component ─────────────────────────────────────────────────────────────────

const BusinessIntelPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [alerts, setAlerts] = useState<RevenueAlert[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [detectLoading, setDetectLoading] = useState(false);
  const [insightLoading, setInsightLoading] = useState(false);
  const [detectResult, setDetectResult] = useState<Record<string, unknown> | null>(null);
  const [insightResult, setInsightResult] = useState<Record<string, unknown> | null>(null);
  const [detectModal, setDetectModal] = useState(false);
  const [insightModal, setInsightModal] = useState(false);
  const [detectForm] = Form.useForm();
  const [activeTab, setActiveTab] = useState('dashboard');

  const brandId = DEFAULT_BRAND;
  const storeId = DEFAULT_STORE;

  // ── Data Fetching ──────────────────────────────────────────────────────────

  const loadDashboard = useCallback(async () => {
    try {
      const data = await apiClient.get<DashboardData>(
        `/api/v1/business-intel/dashboard?brand_id=${brandId}&store_id=${storeId}`
      );
      setDashboard(data);
    } catch {
      // Dashboard optional — page still works
    }
  }, [brandId, storeId]);

  const loadAlerts = useCallback(async () => {
    try {
      const data = await apiClient.get<{ count: number; alerts: RevenueAlert[] }>(
        `/api/v1/business-intel/alerts?brand_id=${brandId}&store_id=${storeId}&include_resolved=false`
      );
      setAlerts(data.alerts);
    } catch {
      setAlerts([]);
    }
  }, [brandId, storeId]);

  const loadDecisions = useCallback(async () => {
    try {
      const data = await apiClient.get<{ count: number; decisions: Decision[] }>(
        `/api/v1/business-intel/decisions?brand_id=${brandId}&store_id=${storeId}`
      );
      setDecisions(data.decisions);
    } catch {
      setDecisions([]);
    }
  }, [brandId, storeId]);

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await Promise.all([loadDashboard(), loadAlerts(), loadDecisions()]);
      setLoading(false);
    };
    init();
  }, [loadDashboard, loadAlerts, loadDecisions]);

  // ── Agent Actions ──────────────────────────────────────────────────────────

  const handleDetectAnomaly = async (values: { actual_yuan: number; expected_yuan: number }) => {
    setDetectLoading(true);
    try {
      const result = await apiClient.post<Record<string, unknown>>(
        '/api/v1/business-intel/agents/detect-anomaly',
        {
          brand_id: brandId,
          store_id: storeId,
          actual_yuan: values.actual_yuan,
          expected_yuan: values.expected_yuan,
        }
      );
      setDetectResult(result);
      message.success('异常检测完成');
      await loadAlerts();
    } catch {
      message.error('异常检测失败');
    } finally {
      setDetectLoading(false);
    }
  };

  const handleGenerateInsight = async () => {
    setInsightLoading(true);
    try {
      const result = await apiClient.post<Record<string, unknown>>(
        '/api/v1/business-intel/agents/biz-insight',
        { brand_id: brandId, store_id: storeId }
      );
      setInsightResult(result);
      message.success('Top3决策建议生成成功');
      await Promise.all([loadDashboard(), loadDecisions()]);
    } catch {
      message.error('生成决策建议失败');
    } finally {
      setInsightLoading(false);
    }
  };

  const handleResolveAlert = async (alertId: string) => {
    try {
      await apiClient.request(`/api/v1/business-intel/alerts/${alertId}/resolve`, {
        method: 'PATCH', body: JSON.stringify({}),
      });
      message.success('预警已标记处理');
      await loadAlerts();
    } catch {
      message.error('操作失败');
    }
  };

  const handleAcceptDecision = async (decisionId: string) => {
    try {
      await apiClient.request(`/api/v1/business-intel/decisions/${decisionId}/accept`, {
        method: 'PATCH', body: JSON.stringify({ accepted_rank: 1 }),
      });
      message.success('已采纳决策建议');
      await loadDecisions();
    } catch {
      message.error('操作失败');
    }
  };

  // ── Alert Columns ──────────────────────────────────────────────────────────

  const alertColumns = [
    { title: '日期', dataIndex: 'alert_date', width: 110 },
    {
      title: '异常等级',
      dataIndex: 'anomaly_level',
      width: 100,
      render: (v: string) => <Tag color={ANOMALY_COLOR[v] || 'default'}>{v}</Tag>,
    },
    {
      title: '偏差%',
      dataIndex: 'deviation_pct',
      width: 90,
      render: (v: number) => (
        <span style={{ color: v < 0 ? '#ff4d4f' : '#52c41a' }}>
          {v > 0 ? '+' : ''}{v.toFixed(1)}%
        </span>
      ),
    },
    {
      title: '影响金额',
      dataIndex: 'impact_yuan',
      width: 110,
      render: (v: number) => `¥${Math.abs(v).toLocaleString()}`,
    },
    {
      title: '建议行动',
      dataIndex: 'recommended_action',
      ellipsis: true,
    },
    {
      title: '操作',
      width: 90,
      render: (_: unknown, record: RevenueAlert) => (
        <Button size="small" onClick={() => handleResolveAlert(record.id)}>已处理</Button>
      ),
    },
  ];

  // ── Decision Columns ───────────────────────────────────────────────────────

  const decisionColumns = [
    { title: '日期', dataIndex: 'decision_date', width: 110 },
    {
      title: '优先级',
      dataIndex: 'priority',
      width: 80,
      render: (v: string) => <Tag color={PRIORITY_COLOR[v] || 'default'}>{v?.toUpperCase()}</Tag>,
    },
    {
      title: '预计节省',
      dataIndex: 'total_saving_yuan',
      width: 120,
      render: (v: number) => <span style={{ color: '#52c41a', fontWeight: 600 }}>¥{v.toLocaleString()}</span>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (v: string) => <Tag color={STATUS_COLOR[v] || 'default'}>{v}</Tag>,
    },
    {
      title: 'Top建议',
      dataIndex: 'top_recommendation',
      ellipsis: true,
      render: (v: Decision['top_recommendation']) => v?.action || '—',
    },
    {
      title: '操作',
      width: 90,
      render: (_: unknown, record: Decision) =>
        record.status === 'pending' ? (
          <Button size="small" type="primary" onClick={() => handleAcceptDecision(record.id)}>
            采纳
          </Button>
        ) : null,
    },
  ];

  // ── Render ─────────────────────────────────────────────────────────────────

  if (loading) return <ZSkeleton />;

  const d = dashboard;

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <h2 className={styles.title}>
          <RobotOutlined /> 经营智能体
        </h2>
        <Space>
          <Button
            icon={<ThunderboltOutlined />}
            onClick={() => setDetectModal(true)}
          >
            营收异常检测
          </Button>
          <Button
            type="primary"
            icon={<BulbOutlined />}
            loading={insightLoading}
            onClick={() => { handleGenerateInsight(); setInsightModal(true); }}
          >
            生成Top3决策
          </Button>
        </Space>
      </div>

      {/* KPI 概览 */}
      <Row gutter={16} className={styles.kpiRow}>
        <Col span={6}>
          <ZCard>
            <Statistic
              title="今日预计节省"
              value={d?.today_decision.total_saving_yuan ?? 0}
              prefix="¥"
              valueStyle={{ color: '#52c41a' }}
            />
          </ZCard>
        </Col>
        <Col span={6}>
          <ZCard>
            <Statistic
              title="未处理预警"
              value={d?.open_alerts.count ?? alerts.length}
              suffix={
                (d?.open_alerts.critical_count ?? 0) > 0
                  ? <Badge count={d?.open_alerts.critical_count} color="red" style={{ marginLeft: 8 }} />
                  : null
              }
              valueStyle={{ color: (d?.open_alerts.count ?? 0) > 0 ? '#ff4d4f' : '#52c41a' }}
            />
          </ZCard>
        </Col>
        <Col span={6}>
          <ZCard>
            <Statistic
              title="KPI健康度"
              value={d?.kpi_health.overall_score ?? '—'}
              suffix={d?.kpi_health.overall_score ? '/100' : ''}
              valueStyle={{
                color: (d?.kpi_health.overall_score ?? 0) >= 80 ? '#52c41a'
                  : (d?.kpi_health.overall_score ?? 0) >= 60 ? '#faad14' : '#ff4d4f',
              }}
            />
          </ZCard>
        </Col>
        <Col span={6}>
          <ZCard>
            <Statistic
              title="7日营收预测"
              value={d?.forecast_7d.predicted_revenue_yuan ?? '—'}
              prefix={d?.forecast_7d.predicted_revenue_yuan ? '¥' : ''}
              suffix={d?.forecast_7d.trend_direction ? TREND_ICON[d.forecast_7d.trend_direction] : null}
            />
          </ZCard>
        </Col>
      </Row>

      {/* 今日决策建议 */}
      {d?.today_decision.top3 && d.today_decision.top3.length > 0 && (
        <ZCard className={styles.decisionCard} title={<><BulbOutlined /> 今日Top3经营建议</>}>
          {d.today_decision.top3.map((rec, i) => (
            <div key={i} className={styles.recItem}>
              <Tag color={i === 0 ? 'red' : i === 1 ? 'orange' : 'blue'}>#{rec.rank}</Tag>
              <span className={styles.recAction}>{rec.action}</span>
              <Tag color="green">节省 ¥{rec.saving_yuan?.toLocaleString()}</Tag>
              <Progress
                percent={Math.round((rec.confidence ?? 0) * 100)}
                size="small"
                style={{ width: 100, marginLeft: 8 }}
                format={p => `${p}%置信`}
              />
            </div>
          ))}
        </ZCard>
      )}

      {/* Tab 面板 */}
      <Tabs activeKey={activeTab} onChange={setActiveTab} className={styles.tabs}>
        <TabPane tab={<><ExclamationCircleOutlined /> 营收预警</>} key="alerts">
          <Table
            columns={alertColumns}
            dataSource={alerts}
            rowKey="id"
            pagination={{ pageSize: 10 }}
            size="small"
          />
        </TabPane>

        <TabPane tab={<><CheckCircleOutlined /> 历史决策</>} key="decisions">
          <Table
            columns={decisionColumns}
            dataSource={decisions}
            rowKey="id"
            pagination={{ pageSize: 10 }}
            size="small"
          />
        </TabPane>
      </Tabs>

      {/* 异常检测 Modal */}
      <Modal
        title={<><ThunderboltOutlined /> 营收异常检测</>}
        open={detectModal}
        onCancel={() => { setDetectModal(false); setDetectResult(null); detectForm.resetFields(); }}
        footer={null}
        width={520}
      >
        {!detectResult ? (
          <Form form={detectForm} layout="vertical" onFinish={handleDetectAnomaly}>
            <Form.Item name="actual_yuan" label="实际营收（元）" rules={[{ required: true }]}>
              <InputNumber style={{ width: '100%' }} min={0} precision={2} />
            </Form.Item>
            <Form.Item name="expected_yuan" label="预期营收（元）" rules={[{ required: true }]}>
              <InputNumber style={{ width: '100%' }} min={0} precision={2} />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={detectLoading} block>
              开始检测
            </Button>
          </Form>
        ) : (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="异常等级">
              <Tag color={ANOMALY_COLOR[(detectResult.anomaly_level as string) ?? 'normal']}>
                {detectResult.anomaly_level as string}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="偏差%">
              {(detectResult.deviation_pct as number)?.toFixed(1)}%
            </Descriptions.Item>
            <Descriptions.Item label="影响金额">
              ¥{Math.abs(detectResult.impact_yuan as number).toLocaleString()}
            </Descriptions.Item>
            <Descriptions.Item label="建议行动">
              {(detectResult.recommended_action as string) || '—'}
            </Descriptions.Item>
            {!!detectResult.ai_insight && (
              <Descriptions.Item label="AI洞察">
                {detectResult.ai_insight as string}
              </Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Modal>

      {/* Top3决策 Modal */}
      <Modal
        title={<><BulbOutlined /> Top3经营决策建议</>}
        open={insightModal}
        onCancel={() => { setInsightModal(false); setInsightResult(null); }}
        footer={null}
        width={600}
      >
        {insightLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin tip="AI分析中..." /></div>
        ) : insightResult ? (
          <>
            <Alert
              type="success"
              message={`预计总节省：¥${(insightResult.total_saving_yuan as number)?.toLocaleString()}`}
              style={{ marginBottom: 16 }}
            />
            {((insightResult.top3_recommendations as Array<{
              rank: number; action: string; saving_yuan: number;
              urgency_hours: number; confidence: number; rationale: string;
            }>) ?? []).map(rec => (
              <ZCard key={rec.rank} className={styles.recCard}>
                <Tag color={rec.rank === 1 ? 'red' : rec.rank === 2 ? 'orange' : 'blue'}>
                  Top {rec.rank}
                </Tag>
                <strong style={{ marginLeft: 8 }}>{rec.action}</strong>
                <div style={{ marginTop: 8, color: '#666' }}>{rec.rationale}</div>
                <div style={{ marginTop: 8 }}>
                  <Tag color="green">节省 ¥{rec.saving_yuan?.toLocaleString()}</Tag>
                  <Tag color="blue">紧急度 {rec.urgency_hours}h</Tag>
                  <Tag>置信度 {Math.round((rec.confidence ?? 0) * 100)}%</Tag>
                </div>
              </ZCard>
            ))}
          </>
        ) : null}
      </Modal>
    </div>
  );
};

export default BusinessIntelPage;
