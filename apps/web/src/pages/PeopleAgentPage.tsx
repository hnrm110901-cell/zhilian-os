// PeopleAgentPage.tsx — Phase 12B 人员智能体工作台
// 路由：/people-agent（admin 权限）
import React, { useState, useEffect, useCallback } from 'react';
import {
  Tabs, Table, Tag, Button, Modal, Form, Input, InputNumber,
  Select, DatePicker, message, Statistic, Row, Col, Badge,
  Progress, Descriptions, Space, Alert, Spin,
} from 'antd';
import {
  TeamOutlined, RiseOutlined, FallOutlined, DollarOutlined,
  CheckCircleOutlined, ExclamationCircleOutlined, SyncOutlined,
  RobotOutlined, UserOutlined, CalendarOutlined, WarningOutlined,
} from '@ant-design/icons';
import ZCard from '../design-system/components/ZCard';
import ZSkeleton from '../design-system/components/ZSkeleton';
import { apiClient } from '../utils/apiClient';
import styles from './PeopleAgentPage.module.css';

const { TabPane } = Tabs;
const { Option } = Select;

// ── Types ─────────────────────────────────────────────────────────────────────

interface DashboardData {
  brand_id: string;
  store_id: string;
  today: string;
  shift_status: {
    shift_date: string | null;
    coverage_rate: number | null;
    status: string | null;
    labor_cost_pct: number | null;
  };
  labor_cost: {
    period: string | null;
    labor_cost_ratio: number | null;
    revenue_per_employee_yuan: number | null;
    optimization_potential_yuan: number | null;
  };
  attendance_alerts: {
    open_count: number;
    critical_count: number;
  };
  pending_staffing: {
    has_decision: boolean;
    decision_id: string | null;
    total_impact_yuan: number;
    priority: string | null;
  };
}

interface AttendanceAlert {
  id: string;
  alert_date: string;
  alert_type: string;
  severity: string;
  employee_name: string | null;
  estimated_impact_yuan: number;
  is_resolved: boolean;
}

interface StaffingDecision {
  id: string;
  decision_date: string;
  priority: string;
  status: string;
  current_headcount: number | null;
  optimal_headcount: number | null;
  total_impact_yuan: number;
  top_recommendation: { rank: number; action: string; impact_yuan: number } | null;
}

// ── Constants ──────────────────────────────────────────────────────────────────

const DEFAULT_BRAND = 'B001';
const DEFAULT_STORE = 'S001';

const SEVERITY_COLOR: Record<string, string> = {
  critical: 'red', warning: 'gold', info: 'blue',
};

const ALERT_TYPE_LABEL: Record<string, string> = {
  late: '迟到', absent: '缺勤', early_leave: '早退',
  overtime: '超时', understaffed: '人手不足',
};

const PRIORITY_COLOR: Record<string, string> = {
  p0: 'red', p1: 'orange', p2: 'blue', p3: 'default',
};

const STATUS_COLOR: Record<string, string> = {
  pending: 'blue', accepted: 'green', rejected: 'red',
};

const RATING_COLOR: Record<string, string> = {
  outstanding: 'gold', exceeds: 'green', meets: 'blue',
  below: 'orange', unsatisfactory: 'red',
};

const RATING_LABEL: Record<string, string> = {
  outstanding: '优秀', exceeds: '良好', meets: '达标',
  below: '待改进', unsatisfactory: '不合格',
};

// ── Component ──────────────────────────────────────────────────────────────────

const PeopleAgentPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [alerts, setAlerts] = useState<AttendanceAlert[]>([]);
  const [decisions, setDecisions] = useState<StaffingDecision[]>([]);
  const [activeTab, setActiveTab] = useState('dashboard');

  // Agent action state
  const [shiftModal, setShiftModal] = useState(false);
  const [shiftLoading, setShiftLoading] = useState(false);
  const [shiftResult, setShiftResult] = useState<Record<string, unknown> | null>(null);

  const [perfModal, setPerfModal] = useState(false);
  const [perfLoading, setPerfLoading] = useState(false);
  const [perfResult, setPerfResult] = useState<Record<string, unknown> | null>(null);

  const [laborModal, setLaborModal] = useState(false);
  const [laborLoading, setLaborLoading] = useState(false);
  const [laborResult, setLaborResult] = useState<Record<string, unknown> | null>(null);

  const [warnModal, setWarnModal] = useState(false);
  const [warnLoading, setWarnLoading] = useState(false);

  const [staffModal, setStaffModal] = useState(false);
  const [staffLoading, setStaffLoading] = useState(false);
  const [staffResult, setStaffResult] = useState<Record<string, unknown> | null>(null);

  const [shiftForm] = Form.useForm();
  const [perfForm] = Form.useForm();
  const [laborForm] = Form.useForm();
  const [warnForm] = Form.useForm();
  const [staffForm] = Form.useForm();

  const brandId = DEFAULT_BRAND;
  const storeId = DEFAULT_STORE;

  // ── Data Fetching ────────────────────────────────────────────────────────────

  const loadDashboard = useCallback(async () => {
    try {
      const data = await apiClient.get<DashboardData>(
        `/api/v1/people/dashboard?brand_id=${brandId}&store_id=${storeId}`
      );
      setDashboard(data);
    } catch {
      // Dashboard optional
    }
  }, [brandId, storeId]);

  const loadAlerts = useCallback(async () => {
    try {
      const data = await apiClient.get<{ count: number; alerts: AttendanceAlert[] }>(
        `/api/v1/people/attendance-alerts?brand_id=${brandId}&store_id=${storeId}&include_resolved=false`
      );
      setAlerts(data.alerts);
    } catch {
      setAlerts([]);
    }
  }, [brandId, storeId]);

  const loadDecisions = useCallback(async () => {
    try {
      const data = await apiClient.get<{ count: number; decisions: StaffingDecision[] }>(
        `/api/v1/people/staffing-decisions?brand_id=${brandId}&store_id=${storeId}`
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

  // ── Agent Actions ────────────────────────────────────────────────────────────

  const handleShiftOptimize = async (values: Record<string, unknown>) => {
    setShiftLoading(true);
    try {
      const result = await apiClient.post<Record<string, unknown>>(
        '/api/v1/people/agents/shift-optimize',
        { brand_id: brandId, store_id: storeId, ...values }
      );
      setShiftResult(result);
      message.success('排班优化分析完成');
      await loadDashboard();
    } catch {
      message.error('排班优化失败');
    } finally {
      setShiftLoading(false);
    }
  };

  const handlePerformanceScore = async (values: Record<string, unknown>) => {
    setPerfLoading(true);
    try {
      const result = await apiClient.post<Record<string, unknown>>(
        '/api/v1/people/agents/performance-score',
        { brand_id: brandId, store_id: storeId, ...values }
      );
      setPerfResult(result);
      message.success('绩效评分完成');
    } catch {
      message.error('绩效评分失败');
    } finally {
      setPerfLoading(false);
    }
  };

  const handleLaborCost = async (values: Record<string, unknown>) => {
    setLaborLoading(true);
    try {
      const result = await apiClient.post<Record<string, unknown>>(
        '/api/v1/people/agents/labor-cost',
        { brand_id: brandId, store_id: storeId, ...values }
      );
      setLaborResult(result);
      message.success('人力成本分析完成');
      await loadDashboard();
    } catch {
      message.error('人力成本分析失败');
    } finally {
      setLaborLoading(false);
    }
  };

  const handleAttendanceWarn = async (values: Record<string, unknown>) => {
    setWarnLoading(true);
    try {
      await apiClient.post<Record<string, unknown>>(
        '/api/v1/people/agents/attendance-warn',
        { brand_id: brandId, store_id: storeId, ...values }
      );
      message.success('考勤预警已记录');
      setWarnModal(false);
      warnForm.resetFields();
      await Promise.all([loadDashboard(), loadAlerts()]);
    } catch {
      message.error('考勤预警记录失败');
    } finally {
      setWarnLoading(false);
    }
  };

  const handleStaffingPlan = async (values: Record<string, unknown>) => {
    setStaffLoading(true);
    try {
      const result = await apiClient.post<Record<string, unknown>>(
        '/api/v1/people/agents/staffing-plan',
        { brand_id: brandId, store_id: storeId, ...values }
      );
      setStaffResult(result);
      message.success('人员配置建议生成成功');
      await Promise.all([loadDashboard(), loadDecisions()]);
    } catch {
      message.error('生成人员配置建议失败');
    } finally {
      setStaffLoading(false);
    }
  };

  const handleResolveAlert = async (alertId: string) => {
    try {
      await apiClient.request(`/api/v1/people/attendance-alerts/${alertId}/resolve`, {
        method: 'PATCH', body: JSON.stringify({}),
      });
      message.success('预警已标记处理');
      await Promise.all([loadAlerts(), loadDashboard()]);
    } catch {
      message.error('操作失败');
    }
  };

  const handleAcceptDecision = async (decisionId: string) => {
    try {
      await apiClient.request(`/api/v1/people/staffing-decisions/${decisionId}/accept`, {
        method: 'PATCH', body: JSON.stringify({ accepted_rank: 1 }),
      });
      message.success('已采纳配置建议');
      await loadDecisions();
    } catch {
      message.error('操作失败');
    }
  };

  // ── Alert Columns ────────────────────────────────────────────────────────────

  const alertColumns = [
    { title: '日期', dataIndex: 'alert_date', width: 110 },
    {
      title: '类型',
      dataIndex: 'alert_type',
      width: 90,
      render: (v: string) => ALERT_TYPE_LABEL[v] || v,
    },
    {
      title: '严重度',
      dataIndex: 'severity',
      width: 90,
      render: (v: string) => <Tag color={SEVERITY_COLOR[v] || 'default'}>{v}</Tag>,
    },
    { title: '员工', dataIndex: 'employee_name', width: 100, render: (v: string | null) => v || '—' },
    {
      title: '影响金额',
      dataIndex: 'estimated_impact_yuan',
      width: 110,
      render: (v: number) => v > 0 ? `¥${v.toLocaleString()}` : '—',
    },
    {
      title: '操作',
      width: 90,
      render: (_: unknown, record: AttendanceAlert) => (
        <Button size="small" onClick={() => handleResolveAlert(record.id)}>已处理</Button>
      ),
    },
  ];

  // ── Decision Columns ─────────────────────────────────────────────────────────

  const decisionColumns = [
    { title: '日期', dataIndex: 'decision_date', width: 110 },
    {
      title: '优先级',
      dataIndex: 'priority',
      width: 80,
      render: (v: string) => <Tag color={PRIORITY_COLOR[v] || 'default'}>{v?.toUpperCase()}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      render: (v: string) => <Tag color={STATUS_COLOR[v] || 'default'}>{v}</Tag>,
    },
    {
      title: '预计影响',
      dataIndex: 'total_impact_yuan',
      width: 120,
      render: (v: number) => <span style={{ color: '#52c41a', fontWeight: 600 }}>¥{v.toLocaleString()}</span>,
    },
    {
      title: '当前/最优人数',
      render: (_: unknown, r: StaffingDecision) =>
        r.current_headcount != null ? `${r.current_headcount} / ${r.optimal_headcount}` : '—',
      width: 120,
    },
    {
      title: 'Top建议',
      dataIndex: 'top_recommendation',
      ellipsis: true,
      render: (v: StaffingDecision['top_recommendation']) => v?.action || '—',
    },
    {
      title: '操作',
      width: 90,
      render: (_: unknown, record: StaffingDecision) =>
        record.status === 'pending' ? (
          <Button size="small" type="primary" onClick={() => handleAcceptDecision(record.id)}>
            采纳
          </Button>
        ) : null,
    },
  ];

  // ── Render ────────────────────────────────────────────────────────────────────

  if (loading) return <ZSkeleton />;

  const d = dashboard;

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <h2 className={styles.title}>
          <TeamOutlined /> 人员智能体
        </h2>
        <Space wrap>
          <Button icon={<CalendarOutlined />} onClick={() => setShiftModal(true)}>
            排班优化
          </Button>
          <Button icon={<UserOutlined />} onClick={() => setPerfModal(true)}>
            绩效评分
          </Button>
          <Button icon={<DollarOutlined />} onClick={() => setLaborModal(true)}>
            人力成本分析
          </Button>
          <Button icon={<WarningOutlined />} onClick={() => setWarnModal(true)}>
            记录考勤预警
          </Button>
          <Button type="primary" icon={<RobotOutlined />} loading={staffLoading}
            onClick={() => setStaffModal(true)}>
            生成配置建议
          </Button>
        </Space>
      </div>

      {/* KPI 概览 */}
      <Row gutter={16} className={styles.kpiRow}>
        <Col span={6}>
          <ZCard>
            <Statistic
              title="排班覆盖率"
              value={d?.shift_status.coverage_rate != null
                ? Math.round((d.shift_status.coverage_rate) * 100) : '—'}
              suffix={d?.shift_status.coverage_rate != null ? '%' : ''}
              valueStyle={{
                color: (d?.shift_status.coverage_rate ?? 0) >= 0.9 ? '#52c41a'
                  : (d?.shift_status.coverage_rate ?? 0) >= 0.75 ? '#faad14' : '#ff4d4f',
              }}
            />
          </ZCard>
        </Col>
        <Col span={6}>
          <ZCard>
            <Statistic
              title="人力成本率"
              value={d?.labor_cost.labor_cost_ratio != null
                ? d.labor_cost.labor_cost_ratio.toFixed(1) : '—'}
              suffix={d?.labor_cost.labor_cost_ratio != null ? '%' : ''}
              valueStyle={{
                color: (d?.labor_cost.labor_cost_ratio ?? 0) <= 28 ? '#52c41a'
                  : (d?.labor_cost.labor_cost_ratio ?? 0) <= 32 ? '#faad14' : '#ff4d4f',
              }}
            />
          </ZCard>
        </Col>
        <Col span={6}>
          <ZCard>
            <Statistic
              title="未处理考勤预警"
              value={d?.attendance_alerts.open_count ?? alerts.length}
              suffix={
                (d?.attendance_alerts.critical_count ?? 0) > 0
                  ? <Badge count={d?.attendance_alerts.critical_count} color="red" style={{ marginLeft: 8 }} />
                  : null
              }
              valueStyle={{
                color: (d?.attendance_alerts.open_count ?? 0) > 0 ? '#ff4d4f' : '#52c41a',
              }}
            />
          </ZCard>
        </Col>
        <Col span={6}>
          <ZCard>
            <Statistic
              title="优化潜力"
              value={d?.labor_cost.optimization_potential_yuan
                ? Math.round(d.labor_cost.optimization_potential_yuan) : 0}
              prefix="¥"
              valueStyle={{ color: '#52c41a' }}
            />
          </ZCard>
        </Col>
      </Row>

      {/* 待处理配置建议 */}
      {d?.pending_staffing.has_decision && (
        <Alert
          type="warning"
          icon={<RobotOutlined />}
          message={`有待处理的人员配置建议（预计影响 ¥${d.pending_staffing.total_impact_yuan.toLocaleString()}）`}
          action={
            <Button size="small" type="primary"
              onClick={() => handleAcceptDecision(d.pending_staffing.decision_id!)}>
              查看并采纳
            </Button>
          }
          showIcon
        />
      )}

      {/* Tab 面板 */}
      <Tabs activeKey={activeTab} onChange={setActiveTab} className={styles.tabs}>
        <TabPane tab={<><WarningOutlined /> 考勤预警</>} key="alerts">
          <Table
            columns={alertColumns}
            dataSource={alerts}
            rowKey="id"
            pagination={{ pageSize: 10 }}
            size="small"
          />
        </TabPane>

        <TabPane tab={<><CheckCircleOutlined /> 配置建议</>} key="decisions">
          <Table
            columns={decisionColumns}
            dataSource={decisions}
            rowKey="id"
            pagination={{ pageSize: 10 }}
            size="small"
          />
        </TabPane>
      </Tabs>

      {/* 排班优化 Modal */}
      <Modal
        title={<><CalendarOutlined /> 排班优化分析</>}
        open={shiftModal}
        onCancel={() => { setShiftModal(false); setShiftResult(null); shiftForm.resetFields(); }}
        footer={null}
        width={560}
      >
        {!shiftResult ? (
          <Form form={shiftForm} layout="vertical" onFinish={handleShiftOptimize}>
            <Row gutter={12}>
              <Col span={12}>
                <Form.Item name="required_headcount" label="需求人数" rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} min={1} precision={0} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="scheduled_headcount" label="排班人数" rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} min={0} precision={0} />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={12}>
              <Col span={12}>
                <Form.Item name="estimated_labor_cost_yuan" label="预估人力成本（元）" rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} min={0} precision={2} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="revenue_yuan" label="预期营收（元）" rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} min={0} precision={2} />
                </Form.Item>
              </Col>
            </Row>
            <Button type="primary" htmlType="submit" loading={shiftLoading} block>
              开始分析
            </Button>
          </Form>
        ) : (
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="排班状态">
              <Tag color={shiftResult.shift_status === 'optimal' ? 'green' : 'orange'}>
                {shiftResult.shift_status as string}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="覆盖率">
              {((shiftResult.coverage_rate as number) * 100).toFixed(1)}%
            </Descriptions.Item>
            <Descriptions.Item label="人力成本率">
              {(shiftResult.labor_cost_ratio_pct as number).toFixed(1)}%
            </Descriptions.Item>
            <Descriptions.Item label="优化建议" span={2}>
              {((shiftResult.optimization_suggestions as string[]) ?? []).join('；') || '—'}
            </Descriptions.Item>
            {!!shiftResult.ai_insight && (
              <Descriptions.Item label="AI洞察" span={2}>
                {shiftResult.ai_insight as string}
              </Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Modal>

      {/* 绩效评分 Modal */}
      <Modal
        title={<><UserOutlined /> 员工绩效评分</>}
        open={perfModal}
        onCancel={() => { setPerfModal(false); setPerfResult(null); perfForm.resetFields(); }}
        footer={null}
        width={600}
      >
        {!perfResult ? (
          <Form form={perfForm} layout="vertical" onFinish={handlePerformanceScore}>
            <Row gutter={12}>
              <Col span={12}>
                <Form.Item name="employee_id" label="员工ID" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="employee_name" label="员工姓名">
                  <Input />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={12}>
              <Col span={8}>
                <Form.Item name="role" label="岗位" rules={[{ required: true }]}>
                  <Select>
                    <Option value="store_manager">店长</Option>
                    <Option value="chef">厨师长</Option>
                    <Option value="waiter">服务员</Option>
                    <Option value="cashier">收银员</Option>
                  </Select>
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="period" label="考核月份" rules={[{ required: true }]}
                  initialValue="2026-03">
                  <Input placeholder="2026-03" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="base_salary" label="底薪（元）" initialValue={5000}>
                  <InputNumber style={{ width: '100%' }} min={0} precision={2} />
                </Form.Item>
              </Col>
            </Row>
            <Button type="primary" htmlType="submit" loading={perfLoading} block>
              生成绩效评分
            </Button>
          </Form>
        ) : (
          <>
            <Descriptions column={2} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="综合评分">
                <span style={{ fontSize: 18, fontWeight: 700 }}>
                  {(perfResult.overall_score as number)?.toFixed(1)}
                </span>
              </Descriptions.Item>
              <Descriptions.Item label="绩效等级">
                <Tag color={RATING_COLOR[(perfResult.rating as string)] || 'default'}>
                  {RATING_LABEL[(perfResult.rating as string)] || perfResult.rating as string}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="基础提成">
                ¥{(perfResult.base_commission_yuan as number)?.toFixed(2)}
              </Descriptions.Item>
              <Descriptions.Item label="奖励提成">
                ¥{(perfResult.bonus_commission_yuan as number)?.toFixed(2)}
              </Descriptions.Item>
              <Descriptions.Item label="合计提成" span={2}>
                <span style={{ color: '#52c41a', fontWeight: 600 }}>
                  ¥{(perfResult.total_commission_yuan as number)?.toFixed(2)}
                </span>
              </Descriptions.Item>
            </Descriptions>
            {((perfResult.improvement_areas as string[]) ?? []).length > 0 && (
              <Alert
                type="info"
                message="改进建议"
                description={(perfResult.improvement_areas as string[]).join('；')}
                style={{ marginBottom: 8 }}
              />
            )}
          </>
        )}
      </Modal>

      {/* 人力成本分析 Modal */}
      <Modal
        title={<><DollarOutlined /> 人力成本分析</>}
        open={laborModal}
        onCancel={() => { setLaborModal(false); setLaborResult(null); laborForm.resetFields(); }}
        footer={null}
        width={560}
      >
        {!laborResult ? (
          <Form form={laborForm} layout="vertical" onFinish={handleLaborCost}>
            <Row gutter={12}>
              <Col span={12}>
                <Form.Item name="period" label="月份" rules={[{ required: true }]}
                  initialValue="2026-03">
                  <Input placeholder="2026-03" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="avg_headcount" label="平均在岗人数" rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} min={0} precision={1} />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={12}>
              <Col span={12}>
                <Form.Item name="total_labor_cost_yuan" label="总人力成本（元）" rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} min={0} precision={2} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="revenue_yuan" label="月营收（元）" rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} min={0} precision={2} />
                </Form.Item>
              </Col>
            </Row>
            <Button type="primary" htmlType="submit" loading={laborLoading} block>
              开始分析
            </Button>
          </Form>
        ) : (
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="人力成本率">
              {(laborResult.labor_cost_ratio_pct as number)?.toFixed(1)}%
            </Descriptions.Item>
            <Descriptions.Item label="目标成本率">
              {(laborResult.target_ratio_pct as number)?.toFixed(1)}%
            </Descriptions.Item>
            <Descriptions.Item label="偏差">
              <span style={{ color: (laborResult.deviation_pct as number) > 0 ? '#ff4d4f' : '#52c41a' }}>
                {(laborResult.deviation_pct as number) > 0 ? '+' : ''}{(laborResult.deviation_pct as number)?.toFixed(1)}pp
              </span>
            </Descriptions.Item>
            <Descriptions.Item label="人效">
              ¥{(laborResult.revenue_per_employee_yuan as number)?.toLocaleString()}
            </Descriptions.Item>
            {(laborResult.optimization_potential_yuan as number) > 0 && (
              <Descriptions.Item label="优化空间" span={2}>
                <span style={{ color: '#52c41a', fontWeight: 600 }}>
                  ¥{(laborResult.optimization_potential_yuan as number)?.toLocaleString()}
                </span>
              </Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Modal>

      {/* 考勤预警 Modal */}
      <Modal
        title={<><WarningOutlined /> 记录考勤预警</>}
        open={warnModal}
        onCancel={() => { setWarnModal(false); warnForm.resetFields(); }}
        footer={null}
        width={480}
      >
        <Form form={warnForm} layout="vertical" onFinish={handleAttendanceWarn}>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="employee_name" label="员工姓名">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="alert_type" label="异常类型" rules={[{ required: true }]}>
                <Select>
                  <Option value="late">迟到</Option>
                  <Option value="absent">缺勤</Option>
                  <Option value="early_leave">早退</Option>
                  <Option value="overtime">超时加班</Option>
                  <Option value="understaffed">人手不足</Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="count_in_period" label="本月次数" initialValue={1}>
                <InputNumber style={{ width: '100%' }} min={1} precision={0} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="estimated_impact_yuan" label="影响金额（元）" initialValue={0}>
                <InputNumber style={{ width: '100%' }} min={0} precision={2} />
              </Form.Item>
            </Col>
          </Row>
          <Button type="primary" htmlType="submit" loading={warnLoading} block>
            提交预警
          </Button>
        </Form>
      </Modal>

      {/* 人员配置建议 Modal */}
      <Modal
        title={<><RobotOutlined /> 生成人员配置建议</>}
        open={staffModal}
        onCancel={() => { setStaffModal(false); setStaffResult(null); staffForm.resetFields(); }}
        footer={null}
        width={600}
      >
        {!staffResult ? (
          <Form form={staffForm} layout="vertical" onFinish={handleStaffingPlan}>
            <Row gutter={12}>
              <Col span={12}>
                <Form.Item name="current_headcount" label="当前编制人数" rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} min={0} precision={0} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="revenue_yuan" label="月营收（元）" rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} min={0} precision={2} />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="target_revenue_per_person" label="目标人效（元/人）"
              initialValue={50000}>
              <InputNumber style={{ width: '100%' }} min={1000} precision={0} />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={staffLoading} block>
              AI分析配置
            </Button>
          </Form>
        ) : staffLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin tip="AI分析中..." /></div>
        ) : (
          <>
            <Alert
              type="success"
              message={`最优人数：${staffResult.optimal_headcount} 人（当前 ${staffResult.current_headcount}，差额 ${(staffResult.headcount_gap as number) > 0 ? '+' : ''}${staffResult.headcount_gap}）`}
              style={{ marginBottom: 16 }}
            />
            {((staffResult.top3_recommendations as Array<{
              rank: number; action: string; impact_yuan: number;
              urgency_days: number; confidence: number;
            }>) ?? []).map(rec => (
              <ZCard key={rec.rank} className={styles.recCard}>
                <Tag color={rec.rank === 1 ? 'red' : rec.rank === 2 ? 'orange' : 'blue'}>
                  Top {rec.rank}
                </Tag>
                <strong style={{ marginLeft: 8 }}>{rec.action}</strong>
                <div style={{ marginTop: 8 }}>
                  <Tag color="green">影响 ¥{rec.impact_yuan?.toLocaleString()}</Tag>
                  <Tag color="blue">urgency {rec.urgency_days}天</Tag>
                  <Tag>置信度 {Math.round((rec.confidence ?? 0) * 100)}%</Tag>
                </div>
              </ZCard>
            ))}
          </>
        )}
      </Modal>
    </div>
  );
};

export default PeopleAgentPage;
