import React, { useState, useEffect, useCallback } from 'react';
import {
  Table, Tag, Select, Space, Typography, Alert,
} from 'antd';
import {
  CheckCircleOutlined, EditOutlined, SyncOutlined, RobotOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient, handleApiError } from '../services/api';
import AgentWorkspaceTemplate from '../components/AgentWorkspaceTemplate';
import { ZCard, ZEmpty } from '../design-system/components';

const { Text } = Typography;
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

  const s = data?.summary;

  const fetchData = useCallback(async () => {
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
  }, [days, storeId]);

  useEffect(() => { fetchData(); }, [fetchData]);

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

  const overviewContent = (
    <>
      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}

      {/* 图表行：饼 + 折线 */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 12, marginBottom: 12 }}>
        <ZCard title="决策状态分布">
          {data && data.status_dist.length > 0
            ? <ReactECharts option={pieOption} style={{ height: 220 }} />
            : <div style={{ height: 220 }}><ZEmpty /></div>}
        </ZCard>
        <ZCard title="周度 AI 决策采纳率趋势">
          {data && data.weekly_trend.length > 0
            ? <ReactECharts option={lineOption} style={{ height: 220 }} />
            : <div style={{ height: 220 }}><ZEmpty /></div>}
        </ZCard>
      </div>

      {/* 柱状图 */}
      <ZCard title="各 Agent 决策分布" style={{ marginBottom: 12 }}>
        {data && data.agent_stats.length > 0
          ? <ReactECharts option={barOption} style={{ height: 240 }} />
          : <div style={{ height: 240 }}><ZEmpty /></div>}
      </ZCard>

      {/* 日志表 */}
      <ZCard title="最近决策日志">
        <Table
          dataSource={data?.recent_logs ?? []}
          columns={columns}
          rowKey="id"
          size="small"
          pagination={false}
          scroll={{ x: 700 }}
          locale={{ emptyText: '暂无决策记录' }}
        />
      </ZCard>
    </>
  );

  return (
    <AgentWorkspaceTemplate
      agentName="AI 治理看板"
      agentIcon="🤖"
      agentColor="#1677ff"
      description="决策采纳率 · 人工干预率 · Agent 健康度 · 信任分"
      status={(s?.pending_count ?? 0) > 10 ? 'warning' : loading ? 'idle' : 'running'}
      loading={loading}
      onRefresh={fetchData}
      headerExtra={
        <Space>
          <Select value={days} onChange={setDays} style={{ width: 110 }} size="small">
            <Option value={7}>近 7 天</Option>
            <Option value={30}>近 30 天</Option>
            <Option value={90}>近 90 天</Option>
          </Select>
          <Select
            placeholder="全部门店"
            allowClear
            style={{ width: 130 }}
            size="small"
            onChange={(v) => setStoreId(v)}
          />
        </Space>
      }
      kpis={[
        {
          label: '决策总数',
          value: s?.total_decisions ?? '—',
          unit: '条',
          icon: <RobotOutlined />,
        },
        {
          label: 'AI采纳率',
          value: s != null ? s.adoption_rate.toFixed(1) : '—',
          unit: '%',
          valueColor: (s?.adoption_rate ?? 0) >= 70 ? '#52c41a' : '#faad14',
          icon: <CheckCircleOutlined />,
        },
        {
          label: '人工干预率',
          value: s != null ? s.override_rate.toFixed(1) : '—',
          unit: '%',
          valueColor: (s?.override_rate ?? 0) <= 20 ? '#52c41a' : '#ff4d4f',
          icon: <EditOutlined />,
        },
        {
          label: '平均置信度',
          value: s != null ? s.avg_confidence.toFixed(1) : '—',
          unit: '%',
          icon: <RobotOutlined />,
        },
        {
          label: '平均信任分',
          value: s != null ? s.avg_trust_score.toFixed(1) : '—',
          unit: '%',
        },
        {
          label: '待人工审批',
          value: s?.pending_count ?? '—',
          unit: '条',
          valueColor: (s?.pending_count ?? 0) > 0 ? '#faad14' : undefined,
          icon: <SyncOutlined />,
        },
      ]}
      tabs={[
        { key: 'overview', label: '总览', children: overviewContent },
      ]}
      defaultTab="overview"
    />
  );
};

export default GovDashboardPage;
