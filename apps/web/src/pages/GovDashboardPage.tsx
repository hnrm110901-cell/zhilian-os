import React, { useState, useEffect } from 'react';
import {
  Card, Row, Col, Statistic, Table, Tag, Select, Spin,
  Alert, Typography, Space,
} from 'antd';
import {
  CheckCircleOutlined, CloseCircleOutlined,
  EditOutlined, SyncOutlined, RobotOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Title, Text } = Typography;
const { Option } = Select;

// ── Types ─────────────────────────────────────────────────────────────────────

interface Summary {
  total_decisions: number;
  decided_count: number;
  adoption_rate: number;
  override_rate: number;
  avg_confidence: number;
  avg_trust_score: number;
  pending_count: number;
}

interface StatusDist {
  status: string;
  count: number;
}

interface WeeklyTrend {
  week_start: string;
  week_end: string;
  total: number;
  decided: number;
  adoption_rate: number;
}

interface AgentStat {
  agent_type: string;
  total: number;
  approved: number;
  rejected: number;
  modified: number;
  pending: number;
  adoption_rate: number;
}

interface DecisionLog {
  id: string;
  created_at: string;
  store_id: string;
  agent_type: string | null;
  decision_type: string | null;
  ai_suggestion: string;
  decision_status: string | null;
  outcome: string | null;
  ai_confidence: number;
  trust_score: number;
  cost_impact_yuan: number;
  revenue_impact_yuan: number;
}

interface DashboardData {
  summary: Summary;
  status_dist: StatusDist[];
  weekly_trend: WeeklyTrend[];
  agent_stats: AgentStat[];
  recent_logs: DecisionLog[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const STATUS_COLOR: Record<string, string> = {
  pending:   'gold',
  approved:  'green',
  rejected:  'red',
  modified:  'blue',
  executed:  'cyan',
  cancelled: 'default',
};

const STATUS_LABEL: Record<string, string> = {
  pending:   '待决策',
  approved:  '已采纳',
  rejected:  '已拒绝',
  modified:  '已修改',
  executed:  '已执行',
  cancelled: '已取消',
};

const AGENT_LABEL: Record<string, string> = {
  decision:     '决策Agent',
  schedule:     '排班Agent',
  inventory:    '库存Agent',
  order:        '订单Agent',
  ops:          '运维Agent',
  performance:  '绩效Agent',
  quality:      '质检Agent',
  kpi:          'KPI Agent',
  fct:          '财税Agent',
};

// ── Component ─────────────────────────────────────────────────────────────────

const GovDashboardPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<DashboardData | null>(null);
  const [days, setDays] = useState(30);
  const [storeId, setStoreId] = useState<string | undefined>(undefined);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ days: String(days) });
      if (storeId) params.set('store_id', storeId);
      const resp = await apiClient.get(`/api/v1/governance/dashboard?${params}`);
      setData(resp.data);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, [days, storeId]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 决策状态饼图 ────────────────────────────────────────────────────────────
  const pieOption = data ? {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { orient: 'vertical', right: 10, top: 'center' },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      avoidLabelOverlap: false,
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
      data: data.status_dist.map(d => ({
        name: STATUS_LABEL[d.status] ?? d.status,
        value: d.count,
      })),
    }],
  } : {};

  // ── 周度采纳率折线图 ─────────────────────────────────────────────────────────
  const lineOption = data ? {
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: data.weekly_trend.map(w => w.week_start),
      axisLabel: { fontSize: 11 },
    },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
    series: [{
      name: '采纳率',
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      data: data.weekly_trend.map(w => w.adoption_rate),
      itemStyle: { color: '#1677ff' },
      areaStyle: { color: 'rgba(22,119,255,0.08)' },
    }],
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
  } : {};

  // ── 各 Agent 柱状图 ─────────────────────────────────────────────────────────
  const barOption = data ? {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['已采纳', '已拒绝', '已修改', '待决策'], bottom: 0 },
    xAxis: {
      type: 'category',
      data: data.agent_stats.map(a => AGENT_LABEL[a.agent_type] ?? a.agent_type),
      axisLabel: { fontSize: 11 },
    },
    yAxis: { type: 'value' },
    series: [
      { name: '已采纳', type: 'bar', stack: 'total', data: data.agent_stats.map(a => a.approved), itemStyle: { color: '#52c41a' } },
      { name: '已拒绝', type: 'bar', stack: 'total', data: data.agent_stats.map(a => a.rejected), itemStyle: { color: '#ff4d4f' } },
      { name: '已修改', type: 'bar', stack: 'total', data: data.agent_stats.map(a => a.modified), itemStyle: { color: '#1677ff' } },
      { name: '待决策', type: 'bar', stack: 'total', data: data.agent_stats.map(a => a.pending), itemStyle: { color: '#d9d9d9' } },
    ],
    grid: { left: 40, right: 20, top: 20, bottom: 50 },
  } : {};

  // ── 决策日志表格 ─────────────────────────────────────────────────────────────
  const columns = [
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 130, render: (v: string) => <Text style={{ fontSize: 12 }}>{v}</Text> },
    { title: 'Agent', dataIndex: 'agent_type', key: 'agent_type', width: 100, render: (v: string) => AGENT_LABEL[v] ?? v ?? '-' },
    { title: 'AI建议摘要', dataIndex: 'ai_suggestion', key: 'ai_suggestion', ellipsis: true },
    {
      title: '状态', dataIndex: 'decision_status', key: 'decision_status', width: 90,
      render: (v: string) => <Tag color={STATUS_COLOR[v] ?? 'default'}>{STATUS_LABEL[v] ?? v ?? '-'}</Tag>,
    },
    {
      title: '置信度', dataIndex: 'ai_confidence', key: 'ai_confidence', width: 80,
      render: (v: number) => `${v}%`,
    },
    {
      title: '¥影响', key: 'impact', width: 100,
      render: (_: unknown, r: DecisionLog) => {
        const net = r.revenue_impact_yuan - r.cost_impact_yuan;
        return <Text style={{ color: net >= 0 ? '#52c41a' : '#ff4d4f' }}>
          {net >= 0 ? '+' : ''}{net.toFixed(0)}
        </Text>;
      },
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Title level={4} style={{ margin: 0 }}>
            <RobotOutlined style={{ marginRight: 8 }} />AI 治理看板
          </Title>
          <Text type="secondary">决策采纳率 · 人工干预率 · Agent 健康度 · 信任分</Text>
        </Col>
        <Col>
          <Space>
            <Select value={days} onChange={setDays} style={{ width: 110 }}>
              <Option value={7}>近 7 天</Option>
              <Option value={30}>近 30 天</Option>
              <Option value={90}>近 90 天</Option>
            </Select>
            <Select
              placeholder="全部门店"
              allowClear
              style={{ width: 130 }}
              onChange={(v) => setStoreId(v)}
            >
              {/* populated from stores API if needed */}
            </Select>
          </Space>
        </Col>
      </Row>

      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}

      <Spin spinning={loading}>
        {/* ── KPI 卡片 ────────────────────────────────────────────────────── */}
        <Row gutter={[16, 16]}>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic
                title="决策总数"
                value={data?.summary.total_decisions ?? 0}
                suffix={<Text type="secondary" style={{ fontSize: 12 }}>条</Text>}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic
                title="AI决策采纳率"
                value={data?.summary.adoption_rate ?? 0}
                precision={1}
                suffix="%"
                valueStyle={{ color: (data?.summary.adoption_rate ?? 0) >= 70 ? '#52c41a' : '#faad14' }}
                prefix={<CheckCircleOutlined />}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic
                title="人工干预率"
                value={data?.summary.override_rate ?? 0}
                precision={1}
                suffix="%"
                valueStyle={{ color: (data?.summary.override_rate ?? 0) <= 20 ? '#52c41a' : '#ff4d4f' }}
                prefix={<EditOutlined />}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic
                title="平均置信度"
                value={data?.summary.avg_confidence ?? 0}
                precision={1}
                suffix="%"
                prefix={<RobotOutlined />}
              />
            </Card>
          </Col>
        </Row>

        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic
                title="平均信任分"
                value={data?.summary.avg_trust_score ?? 0}
                precision={1}
                suffix="%"
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic
                title="待人工审批"
                value={data?.summary.pending_count ?? 0}
                suffix="条"
                valueStyle={{ color: (data?.summary.pending_count ?? 0) > 0 ? '#faad14' : undefined }}
                prefix={<SyncOutlined />}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic
                title="已决策"
                value={data?.summary.decided_count ?? 0}
                suffix="条"
                prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic
                title="统计周期"
                value={days}
                suffix="天"
              />
            </Card>
          </Col>
        </Row>

        {/* ── 图表区 ────────────────────────────────────────────────────────── */}
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} md={8}>
            <Card title="决策状态分布" size="small">
              {data && data.status_dist.length > 0 ? (
                <ReactECharts option={pieOption} style={{ height: 220 }} />
              ) : (
                <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Text type="secondary">暂无数据</Text>
                </div>
              )}
            </Card>
          </Col>
          <Col xs={24} md={16}>
            <Card title="周度 AI 决策采纳率趋势" size="small">
              {data && data.weekly_trend.length > 0 ? (
                <ReactECharts option={lineOption} style={{ height: 220 }} />
              ) : (
                <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Text type="secondary">暂无数据</Text>
                </div>
              )}
            </Card>
          </Col>
        </Row>

        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24}>
            <Card title="各 Agent 决策分布" size="small">
              {data && data.agent_stats.length > 0 ? (
                <ReactECharts option={barOption} style={{ height: 240 }} />
              ) : (
                <div style={{ height: 240, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Text type="secondary">暂无 Agent 决策数据</Text>
                </div>
              )}
            </Card>
          </Col>
        </Row>

        {/* ── 决策日志表格 ──────────────────────────────────────────────────── */}
        <Card title="最近决策日志" size="small" style={{ marginTop: 16 }}>
          <Table
            dataSource={data?.recent_logs ?? []}
            columns={columns}
            rowKey="id"
            size="small"
            pagination={false}
            scroll={{ x: 700 }}
            locale={{ emptyText: '暂无决策记录' }}
          />
        </Card>
      </Spin>
    </div>
  );
};

export default GovDashboardPage;
