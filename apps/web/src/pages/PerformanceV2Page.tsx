/**
 * 绩效 Agent 2.0 — Phase 11
 * 驾驶舱：OKR进度 + 游戏化排行榜 + AI预警 + 能力成长树
 * 路由：/performance-v2
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Row, Col, Table, Tag, Space, Button, Modal, Form, Input,
  Select, Spin, Typography, Progress, List, Badge,
  InputNumber, Alert, Divider, Tooltip,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  TrophyOutlined, ThunderboltOutlined, WarningOutlined,
  CheckCircleOutlined, PlusOutlined, ApartmentOutlined,
  StarOutlined, FireOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';
import { ZCard, ZKpi, ZSkeleton } from '../design-system/components';
import AgentWorkspaceTemplate from '../components/AgentWorkspaceTemplate';

const { Text } = Typography;
const { Option } = Select;

const BASE = '/api/v1/performance-v2';

// ── 工具：当前周期 ─────────────────────────────────────────────────────────────
function currentPeriod(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

// ── 告警严重度颜色 ─────────────────────────────────────────────────────────────
const SEVERITY_COLOR: Record<string, string> = {
  high:   'error',
  medium: 'warning',
  low:    'processing',
};

// ── 类型定义 ───────────────────────────────────────────────────────────────────
interface DashboardData {
  store_id:    string;
  period:      string;
  okr:         OKRProgress | null;
  leaderboard: LeaderEntry[];
  alert_summary: {
    total:          number;
    high:           number;
    medium:         number;
    top_high_alert: AlertItem | null;
  };
  gamification: {
    top3_badge_counts:   Record<string, number>;
    total_energy_store:  number;
  };
}

interface OKRProgress {
  okr_id:          string;
  objective:       string;
  overall_progress: number;
  key_results:     any[];
  latest_snapshots: SnapshotItem[];
}

interface SnapshotItem {
  kr_index:     number;
  value:        number;
  target:       number;
  progress_pct: number;
  snapshot_at:  string;
}

interface LeaderEntry {
  rank:          number;
  employee_id:   string;
  weekly_energy: number;
  total_energy:  number;
  badge_count:   number;
}

interface AlertItem {
  alert_id:    string;
  alert_type:  string;
  severity:    string;
  title:       string;
  message:     string;
  action_hint: string;
  predicted_at: string;
}

interface SkillItem {
  skill_id:      string;
  skill_code:    string;
  skill_name:    string;
  role_id:       string;
  current_level: number;
  max_level:     number;
  progress_pct:  number;
  salary_bonus:  number;
  next_criteria: any;
}


// ════════════════════════════════════════════════════════════════
// 主页面
// ════════════════════════════════════════════════════════════════

export default function PerformanceV2Page() {
  const storeId  = localStorage.getItem('store_id')  || 'S001';
  const brandId  = localStorage.getItem('brand_id')  || 'B001';
  const [period, setPeriod] = useState(currentPeriod());

  return (
    <AgentWorkspaceTemplate
      agentName="绩效 Agent 2.0"
      agentIcon="🏆"
      agentColor="#faad14"
      description="OKR 进度 · 游戏化排行榜 · AI 预警 · 能力成长树"
      status="running"
      headerExtra={
        <Space size="small">
          <Text type="secondary" style={{ fontSize: 12 }}>周期</Text>
          <Input
            value={period}
            onChange={e => setPeriod(e.target.value)}
            style={{ width: 110 }}
            size="small"
            placeholder="2024-06"
          />
        </Space>
      }
      tabs={[
        {
          key: 'dashboard',
          label: '驾驶舱',
          children: <DashboardTab storeId={storeId} brandId={brandId} period={period} />,
        },
        {
          key: 'okr',
          label: 'OKR 管理',
          children: <OKRTab storeId={storeId} brandId={brandId} period={period} />,
        },
        {
          key: 'gamification',
          label: '游戏化排行',
          children: <GamificationTab storeId={storeId} period={period} />,
        },
        {
          key: 'alerts',
          label: 'AI 预警',
          children: <AlertsTab storeId={storeId} brandId={brandId} period={period} />,
        },
        {
          key: 'skills',
          label: '能力成长树',
          children: <SkillTreeTab />,
        },
      ]}
      defaultTab="dashboard"
    />
  );
}


// ════════════════════════════════════════════════════════════════
// Tab 1：驾驶舱
// ════════════════════════════════════════════════════════════════

function DashboardTab({ storeId, brandId, period }: { storeId: string; brandId: string; period: string }) {
  const [data, setData]       = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(`${BASE}/stores/${storeId}/dashboard`, { params: { period } });
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId, period]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={6} />;
  if (!data) return null;

  const okr = data.okr;

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {/* 顶部预警横幅 */}
      {data.alert_summary.high > 0 && data.alert_summary.top_high_alert && (
        <Alert
          type="error"
          icon={<WarningOutlined />}
          showIcon
          message={`高危预警 ${data.alert_summary.high} 条`}
          description={data.alert_summary.top_high_alert.title}
          action={
            <Button size="small" danger>
              查看全部
            </Button>
          }
        />
      )}

      {/* KPI 行 */}
      <Row gutter={16}>
        <Col span={6}>
          <ZKpi
            label="总能量值（本周）"
            value={data.gamification.total_energy_store}
            unit="pts"
            color="#faad14"
          />
        </Col>
        <Col span={6}>
          <ZKpi
            label="高危预警"
            value={data.alert_summary.high}
            unit="条"
            color={data.alert_summary.high > 0 ? '#f5222d' : '#52c41a'}
          />
        </Col>
        <Col span={6}>
          <ZKpi
            label="中等预警"
            value={data.alert_summary.medium}
            unit="条"
            color={data.alert_summary.medium > 0 ? '#fa8c16' : '#52c41a'}
          />
        </Col>
        <Col span={6}>
          <ZKpi
            label="OKR整体进度"
            value={okr ? Math.round((okr.overall_progress || 0) * 100) : 0}
            unit="%"
            color="#1890ff"
          />
        </Col>
      </Row>

      <Row gutter={16}>
        {/* OKR 进度卡 */}
        <Col span={12}>
          <ZCard title="OKR 进度" extra={<Tag color="blue">{period}</Tag>}>
            {okr ? (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Text strong>{okr.objective}</Text>
                <Progress
                  percent={Math.round((okr.overall_progress || 0) * 100)}
                  status={okr.overall_progress >= 0.95 ? 'success' : 'active'}
                />
                {okr.latest_snapshots.map(s => (
                  <div key={s.kr_index}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      KR{s.kr_index + 1}
                    </Text>
                    <Progress
                      percent={Math.round((s.progress_pct || 0) * 100)}
                      size="small"
                      format={p => `${p}%`}
                    />
                  </div>
                ))}
              </Space>
            ) : (
              <Text type="secondary">本周期暂无 OKR，请先在 OKR 管理中创建</Text>
            )}
          </ZCard>
        </Col>

        {/* 能量排行榜 Top 5 */}
        <Col span={12}>
          <ZCard title="能量排行榜 Top 5" extra={<FireOutlined style={{ color: '#fa541c' }} />}>
            <List
              dataSource={data.leaderboard}
              renderItem={item => (
                <List.Item>
                  <Space>
                    <Badge
                      count={item.rank}
                      style={{
                        backgroundColor:
                          item.rank === 1 ? '#faad14' :
                          item.rank === 2 ? '#bfbfbf' :
                          item.rank === 3 ? '#d4883a' : '#1890ff',
                      }}
                    />
                    <Text>{item.employee_id}</Text>
                  </Space>
                  <Space>
                    <Tag color="gold">{item.weekly_energy} pts</Tag>
                    <Tag>{item.badge_count} 徽章</Tag>
                    {(data.gamification.top3_badge_counts[item.employee_id] ?? 0) > 0 && (
                      <Tag color="purple">
                        本期 {data.gamification.top3_badge_counts[item.employee_id]} 枚
                      </Tag>
                    )}
                  </Space>
                </List.Item>
              )}
            />
          </ZCard>
        </Col>
      </Row>
    </Space>
  );
}


// ════════════════════════════════════════════════════════════════
// Tab 2：OKR 管理
// ════════════════════════════════════════════════════════════════

function OKRTab({ storeId, brandId, period }: { storeId: string; brandId: string; period: string }) {
  const [okrs, setOkrs]             = useState<any[]>([]);
  const [loading, setLoading]       = useState(false);
  const [createModal, setCreateModal] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(`${BASE}/brands/${brandId}/okrs`, { params: { period } });
      setOkrs(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [brandId, period]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    try {
      const vals = await form.validateFields();
      await apiClient.post(`${BASE}/brands/${brandId}/okrs`, {
        period,
        objective: vals.objective,
        key_results: [
          { kr: vals.kr1, target: Number(vals.kr1_target) },
        ].filter(k => k.kr),
      });
      showSuccess('品牌OKR创建成功');
      setCreateModal(false);
      form.resetFields();
      load();
    } catch (e) { handleApiError(e); }
  };

  const columns: ColumnsType<any> = [
    { title: '目标', dataIndex: 'objective', key: 'objective', width: '40%' },
    { title: '周期', dataIndex: 'period',    key: 'period',    width: 100 },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => (
        <Tag color={s === 'active' ? 'success' : 'default'}>
          {s === 'active' ? '进行中' : s}
        </Tag>
      ),
    },
    {
      title: 'KR 数量',
      key: 'kr_count',
      render: (_: any, r: any) => r.key_results?.length ?? 0,
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Row justify="space-between">
        <Col><Text strong>品牌OKR列表</Text></Col>
        <Col>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModal(true)}>
            创建品牌OKR
          </Button>
        </Col>
      </Row>

      {loading ? <ZSkeleton rows={4} /> : (
        <Table
          dataSource={okrs}
          columns={columns}
          rowKey="okr_id"
          size="small"
          pagination={false}
        />
      )}

      {/* 门店OKR进度 */}
      <StoreOKRProgress storeId={storeId} period={period} />

      {/* 创建品牌OKR Modal */}
      <Modal
        title="创建品牌OKR"
        open={createModal}
        onOk={handleCreate}
        onCancel={() => setCreateModal(false)}
        okText="创建"
      >
        <Form form={form} layout="vertical">
          <Form.Item name="objective" label="目标 (O)" rules={[{ required: true }]}>
            <Input.TextArea rows={2} placeholder="例：本季度全品牌营收突破1亿" />
          </Form.Item>
          <Form.Item name="kr1" label="关键结果 KR1">
            <Input placeholder="例：各门店月均营业额达标率 ≥ 90%" />
          </Form.Item>
          <Form.Item name="kr1_target" label="KR1 目标值">
            <InputNumber style={{ width: '100%' }} placeholder="例：0.9" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}

function StoreOKRProgress({ storeId, period }: { storeId: string; period: string }) {
  const [data, setData]       = useState<OKRProgress | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    apiClient.get(`${BASE}/stores/${storeId}/okr-progress`, { params: { period } })
      .then(r => setData(r.data?.okr ?? null))
      .catch(handleApiError)
      .finally(() => setLoading(false));
  }, [storeId, period]);

  return (
    <ZCard title={`门店 OKR 进度（${storeId}）`}>
      {loading && <Spin />}
      {!loading && !data && <Text type="secondary">本周期暂无门店OKR</Text>}
      {data && (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text strong>{data.objective}</Text>
          <Progress
            percent={Math.round((data.overall_progress || 0) * 100)}
            status="active"
          />
          {data.latest_snapshots.map(s => (
            <Row key={s.kr_index} align="middle" gutter={8}>
              <Col span={4}><Text type="secondary">KR{s.kr_index + 1}</Text></Col>
              <Col span={14}>
                <Progress
                  percent={Math.round((s.progress_pct || 0) * 100)}
                  size="small"
                />
              </Col>
              <Col span={6}>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {s.value} / {s.target}
                </Text>
              </Col>
            </Row>
          ))}
        </Space>
      )}
    </ZCard>
  );
}


// ════════════════════════════════════════════════════════════════
// Tab 3：游戏化排行
// ════════════════════════════════════════════════════════════════

function GamificationTab({ storeId, period }: { storeId: string; period: string }) {
  const [leaderboard, setLeaderboard] = useState<LeaderEntry[]>([]);
  const [badges, setBadges]           = useState<any[]>([]);
  const [loading, setLoading]         = useState(false);
  const [highFiveModal, setHighFiveModal] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [lbRes, bdRes] = await Promise.all([
        apiClient.get(`${BASE}/stores/${storeId}/leaderboard`, { params: { period, top_n: 10 } }),
        apiClient.get(`${BASE}/badges`),
      ]);
      setLeaderboard(lbRes.data.leaderboard ?? []);
      setBadges(bdRes.data ?? []);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId, period]);

  useEffect(() => { load(); }, [load]);

  const handleInitBadges = async () => {
    try {
      const r = await apiClient.post(`${BASE}/badges/init-system`);
      showSuccess(`初始化完成，新增 ${r.data.initialized} 枚系统徽章`);
      load();
    } catch (e) { handleApiError(e); }
  };

  const handleHighFive = async () => {
    try {
      const vals = await form.validateFields();
      await apiClient.post(`${BASE}/peer-high-fives`, {
        from_emp_id: vals.from_emp_id,
        to_emp_id:   vals.to_emp_id,
        store_id:    storeId,
        message:     vals.message,
      });
      showSuccess('High Five 发送成功！对方获得 +5 能量值');
      setHighFiveModal(false);
      form.resetFields();
      load();
    } catch (e) { handleApiError(e); }
  };

  const lbColumns: ColumnsType<LeaderEntry> = [
    {
      title: '排名',
      dataIndex: 'rank',
      key: 'rank',
      width: 60,
      render: (rank: number) => (
        <Badge
          count={rank}
          style={{
            backgroundColor:
              rank === 1 ? '#faad14' :
              rank === 2 ? '#bfbfbf' :
              rank === 3 ? '#d4883a' : '#1890ff',
          }}
        />
      ),
    },
    { title: '员工', dataIndex: 'employee_id', key: 'employee_id' },
    {
      title: '本周能量',
      dataIndex: 'weekly_energy',
      key: 'weekly_energy',
      render: (v: number) => <Tag color="gold">{v} pts</Tag>,
    },
    {
      title: '总能量',
      dataIndex: 'total_energy',
      key: 'total_energy',
      render: (v: number) => <Text type="secondary">{v} pts</Text>,
    },
    {
      title: '徽章数',
      dataIndex: 'badge_count',
      key: 'badge_count',
      render: (v: number) => <Tag icon={<TrophyOutlined />}>{v}</Tag>,
    },
  ];

  const badgeColumns: ColumnsType<any> = [
    { title: '代码', dataIndex: 'badge_code', key: 'badge_code', width: 160 },
    { title: '名称', dataIndex: 'badge_name', key: 'badge_name' },
    {
      title: '类型',
      dataIndex: 'badge_type',
      key: 'badge_type',
      render: (t: string) => <Tag>{t}</Tag>,
    },
    {
      title: '能量奖励',
      dataIndex: 'energy_reward',
      key: 'energy_reward',
      render: (v: number) => <Tag color="gold">+{v} pts</Tag>,
    },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Row justify="space-between">
        <Col><Text strong>能量排行榜</Text></Col>
        <Col>
          <Space>
            <Button icon={<StarOutlined />} onClick={() => setHighFiveModal(true)}>
              发送 High Five
            </Button>
            <Button onClick={handleInitBadges}>初始化系统徽章</Button>
          </Space>
        </Col>
      </Row>

      {loading ? <ZSkeleton rows={5} /> : (
        <>
          <Table
            dataSource={leaderboard}
            columns={lbColumns}
            rowKey="employee_id"
            size="small"
            pagination={false}
          />

          <Divider>系统徽章列表</Divider>

          <Table
            dataSource={badges}
            columns={badgeColumns}
            rowKey="id"
            size="small"
            pagination={{ pageSize: 10 }}
          />
        </>
      )}

      <Modal
        title="发送 High Five 同伴互认"
        open={highFiveModal}
        onOk={handleHighFive}
        onCancel={() => setHighFiveModal(false)}
        okText="发送"
      >
        <Form form={form} layout="vertical">
          <Form.Item name="from_emp_id" label="发送人员工ID" rules={[{ required: true }]}>
            <Input placeholder="例：E001" />
          </Form.Item>
          <Form.Item name="to_emp_id" label="接收人员工ID" rules={[{ required: true }]}>
            <Input placeholder="例：E002" />
          </Form.Item>
          <Form.Item name="message" label="留言（可选）">
            <Input.TextArea rows={2} placeholder="你今天的服务太棒了！" />
          </Form.Item>
          <Alert
            type="info"
            message="发送后接收人获得 +5 能量值"
            style={{ marginTop: 8 }}
          />
        </Form>
      </Modal>
    </Space>
  );
}


// ════════════════════════════════════════════════════════════════
// Tab 4：AI 预警
// ════════════════════════════════════════════════════════════════

function AlertsTab({ storeId, brandId, period }: { storeId: string; brandId: string; period: string }) {
  const [alerts, setAlerts]   = useState<AlertItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [scanModal, setScanModal] = useState(false);
  const [scanForm] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(`${BASE}/stores/${storeId}/alerts`, { params: { period } });
      setAlerts(r.data ?? []);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId, period]);

  useEffect(() => { load(); }, [load]);

  const handleResolve = async (alertId: string) => {
    try {
      await apiClient.patch(`${BASE}/alerts/${alertId}/resolve`);
      showSuccess('已标记为已处理');
      load();
    } catch (e) { handleApiError(e); }
  };

  const handleScan = async () => {
    try {
      const vals = await scanForm.validateFields();
      const r = await apiClient.post(`${BASE}/alerts/scan`, {
        store_id:               storeId,
        brand_id:               brandId,
        period,
        employees_data:         JSON.parse(vals.employees_data || '[]'),
        store_waste_rate:       vals.store_waste_rate ? Number(vals.store_waste_rate) : null,
        target_waste_rate:      Number(vals.target_waste_rate || 0.05),
        consecutive_waste_days: Number(vals.consecutive_waste_days || 1),
        dry_run:                false,
      });
      showSuccess(`扫描完成，发现 ${r.data.total_alerts} 条预警`);
      setScanModal(false);
      scanForm.resetFields();
      load();
    } catch (e) { handleApiError(e); }
  };

  const columns: ColumnsType<AlertItem> = [
    {
      title: '严重度',
      dataIndex: 'severity',
      key: 'severity',
      width: 90,
      render: (s: string) => (
        <Tag color={SEVERITY_COLOR[s] ?? 'default'}>
          {s === 'high' ? '高危' : s === 'medium' ? '中等' : '低'}
        </Tag>
      ),
    },
    { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
    { title: '建议动作', dataIndex: 'action_hint', key: 'action_hint', ellipsis: true },
    {
      title: '时间',
      dataIndex: 'predicted_at',
      key: 'predicted_at',
      width: 140,
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 90,
      render: (_: any, r: AlertItem) => (
        <Button
          size="small"
          type="link"
          icon={<CheckCircleOutlined />}
          onClick={() => handleResolve(r.alert_id)}
        >
          已处理
        </Button>
      ),
    },
  ];

  const highAlerts   = alerts.filter(a => a.severity === 'high');
  const mediumAlerts = alerts.filter(a => a.severity === 'medium');

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Row justify="space-between">
        <Col>
          <Space>
            <Text strong>未处理预警</Text>
            {highAlerts.length > 0   && <Tag color="error"  >高危 {highAlerts.length}</Tag>}
            {mediumAlerts.length > 0 && <Tag color="warning">中等 {mediumAlerts.length}</Tag>}
          </Space>
        </Col>
        <Col>
          <Button
            type="primary"
            danger
            icon={<WarningOutlined />}
            onClick={() => setScanModal(true)}
          >
            触发扫描
          </Button>
        </Col>
      </Row>

      {loading ? <ZSkeleton rows={4} /> : (
        <Table
          dataSource={alerts}
          columns={columns}
          rowKey="alert_id"
          size="small"
          expandable={{
            expandedRowRender: (r: AlertItem) => (
              <Text type="secondary" style={{ fontSize: 12 }}>{r.message}</Text>
            ),
          }}
          pagination={{ pageSize: 10 }}
        />
      )}

      <Modal
        title="触发预警扫描"
        open={scanModal}
        onOk={handleScan}
        onCancel={() => setScanModal(false)}
        okText="开始扫描"
        width={560}
      >
        <Alert
          type="info"
          message="输入员工绩效数据，系统自动检测提成缺口、损耗超标等预警"
          style={{ marginBottom: 16 }}
        />
        <Form form={scanForm} layout="vertical">
          <Form.Item
            name="employees_data"
            label="员工数据（JSON数组）"
            extra='格式：[{"employee_id":"E001","role_name":"服务员","current_commission_fen":3000,"target_commission_fen":10000}]'
          >
            <Input.TextArea rows={4} placeholder='[{"employee_id":"E001",...}]' />
          </Form.Item>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="store_waste_rate" label="实际损耗率">
                <InputNumber style={{ width: '100%' }} step={0.01} placeholder="0.08" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="target_waste_rate" label="目标损耗率">
                <InputNumber style={{ width: '100%' }} step={0.01} placeholder="0.05" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="consecutive_waste_days" label="连续天数">
                <InputNumber style={{ width: '100%' }} placeholder="3" />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </Space>
  );
}


// ════════════════════════════════════════════════════════════════
// Tab 5：能力成长树
// ════════════════════════════════════════════════════════════════

function SkillTreeTab() {
  const storeId = localStorage.getItem('store_id') || 'S001';
  const [employeeId, setEmployeeId] = useState('');
  const [skills, setSkills]         = useState<SkillItem[]>([]);
  const [skillDefs, setSkillDefs]   = useState<any[]>([]);
  const [loading, setLoading]       = useState(false);
  const [createDefModal, setCreateDefModal] = useState(false);
  const [promoteModal, setPromoteModal]     = useState(false);
  const [defForm] = Form.useForm();
  const [promoteForm] = Form.useForm();
  const brandId = localStorage.getItem('brand_id') || 'B001';

  useEffect(() => {
    apiClient.get(`${BASE}/skill-definitions`, { params: { brand_id: brandId } })
      .then(r => setSkillDefs(r.data ?? []))
      .catch(handleApiError);
  }, [brandId]);

  const loadSkillTree = async () => {
    if (!employeeId.trim()) return;
    setLoading(true);
    try {
      const r = await apiClient.get(`${BASE}/employees/${employeeId}/skill-tree`);
      setSkills(r.data.skills ?? []);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  };

  const handleCreateDef = async () => {
    try {
      const vals = await defForm.validateFields();
      await apiClient.post(`${BASE}/skill-definitions`, {
        role_id:    vals.role_id,
        skill_code: vals.skill_code,
        skill_name: vals.skill_name,
        max_level:  Number(vals.max_level || 5),
        level_criteria: [],
        salary_delta_per_level: vals.salary_delta ? Number(vals.salary_delta) : null,
      }, { params: { brand_id: brandId } });
      showSuccess('技能定义创建成功');
      setCreateDefModal(false);
      defForm.resetFields();
      const r = await apiClient.get(`${BASE}/skill-definitions`, { params: { brand_id: brandId } });
      setSkillDefs(r.data ?? []);
    } catch (e) { handleApiError(e); }
  };

  const handlePromote = async () => {
    try {
      const vals = await promoteForm.validateFields();
      await apiClient.patch(`${BASE}/employee-skill-levels`, {
        employee_id:    employeeId,
        store_id:       storeId,
        skill_id:       vals.skill_id,
        new_level:      Number(vals.new_level),
        promotion_note: vals.note,
      });
      showSuccess('技能晋升成功');
      setPromoteModal(false);
      promoteForm.resetFields();
      loadSkillTree();
    } catch (e) { handleApiError(e); }
  };

  const skillDefColumns: ColumnsType<any> = [
    { title: '技能代码', dataIndex: 'skill_code', key: 'skill_code', width: 120 },
    { title: '技能名称', dataIndex: 'skill_name', key: 'skill_name' },
    { title: '适用岗位', dataIndex: 'role_id',    key: 'role_id',    width: 100 },
    { title: '最高等级', dataIndex: 'max_level',  key: 'max_level',  width: 80 },
    {
      title: '薪酬加成/级',
      dataIndex: 'salary_delta_per_level',
      key: 'salary_delta',
      render: (v: number | null) => v ? `¥${(v / 100).toFixed(0)}/月` : '-',
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {/* 技能定义管理 */}
      <ZCard
        title="技能定义库"
        extra={
          <Button icon={<PlusOutlined />} size="small" onClick={() => setCreateDefModal(true)}>
            新增技能
          </Button>
        }
      >
        <Table
          dataSource={skillDefs}
          columns={skillDefColumns}
          rowKey="skill_id"
          size="small"
          pagination={{ pageSize: 5 }}
        />
      </ZCard>

      {/* 员工技能树查询 */}
      <ZCard title="员工技能树">
        <Space style={{ marginBottom: 12 }}>
          <Input
            placeholder="输入员工ID"
            value={employeeId}
            onChange={e => setEmployeeId(e.target.value)}
            style={{ width: 180 }}
          />
          <Button type="primary" onClick={loadSkillTree} loading={loading}>
            查询
          </Button>
          {skills.length > 0 && (
            <Button icon={<TrophyOutlined />} onClick={() => setPromoteModal(true)}>
              技能晋升
            </Button>
          )}
        </Space>

        {loading && <Spin />}
        {!loading && skills.length === 0 && employeeId && (
          <Text type="secondary">该员工暂无技能记录</Text>
        )}
        {skills.length > 0 && (
          <Row gutter={[12, 12]}>
            {skills.map(s => (
              <Col span={12} key={s.skill_id}>
                <ZCard style={{ background: 'var(--bg-raised)' }}>
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Row justify="space-between">
                      <Text strong>{s.skill_name}</Text>
                      <Tag color="blue">Lv.{s.current_level} / {s.max_level}</Tag>
                    </Row>
                    <Progress
                      percent={Math.round(s.progress_pct * 100)}
                      size="small"
                      strokeColor={s.progress_pct >= 1 ? '#52c41a' : '#1890ff'}
                    />
                    <Row justify="space-between">
                      <Text type="secondary" style={{ fontSize: 11 }}>岗位：{s.role_id}</Text>
                      {s.salary_bonus > 0 && (
                        <Tag color="green">+¥{(s.salary_bonus / 100).toFixed(0)}/月</Tag>
                      )}
                    </Row>
                    {s.next_criteria && (
                      <Tooltip title={JSON.stringify(s.next_criteria)}>
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          下一级：{s.next_criteria?.description ?? '查看详情'}
                        </Text>
                      </Tooltip>
                    )}
                  </Space>
                </ZCard>
              </Col>
            ))}
          </Row>
        )}
      </ZCard>

      {/* 创建技能定义 Modal */}
      <Modal
        title="新增技能定义"
        open={createDefModal}
        onOk={handleCreateDef}
        onCancel={() => setCreateDefModal(false)}
        okText="创建"
      >
        <Form form={defForm} layout="vertical">
          <Form.Item name="role_id" label="适用岗位" rules={[{ required: true }]}>
            <Select placeholder="选择岗位">
              {['waiter', 'kitchen', 'cashier', 'store_manager'].map(r => (
                <Option key={r} value={r}>{r}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="skill_code" label="技能代码" rules={[{ required: true }]}>
            <Input placeholder="例：upsell_skill" />
          </Form.Item>
          <Form.Item name="skill_name" label="技能名称" rules={[{ required: true }]}>
            <Input placeholder="例：加单推荐技巧" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="max_level" label="最高等级">
                <InputNumber min={2} max={10} defaultValue={5} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="salary_delta" label="薪酬加成/级（分）">
                <InputNumber placeholder="例：5000" style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* 技能晋升 Modal */}
      <Modal
        title={`员工 ${employeeId} 技能晋升`}
        open={promoteModal}
        onOk={handlePromote}
        onCancel={() => setPromoteModal(false)}
        okText="确认晋升"
      >
        <Form form={promoteForm} layout="vertical">
          <Form.Item name="skill_id" label="选择技能" rules={[{ required: true }]}>
            <Select placeholder="选择技能">
              {skills.map(s => (
                <Option key={s.skill_id} value={s.skill_id}>
                  {s.skill_name}（当前 Lv.{s.current_level}）
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="new_level" label="晋升至等级" rules={[{ required: true }]}>
            <InputNumber min={1} max={10} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="note" label="晋升备注">
            <Input.TextArea rows={2} placeholder="晋升原因说明" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
