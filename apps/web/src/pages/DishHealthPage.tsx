/**
 * 菜品综合健康评分引擎 — Phase 6 Month 8
 * 4 Tabs: 健康评分看板 / 评分分布 / 行动优先级 / 菜品健康历史
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Typography, Tabs, Table, Tag, Select, InputNumber, Button, Space,
  Card, Row, Col, Statistic, Input, Empty, Spin, Alert, Progress, Tooltip,
} from 'antd';
import {
  SearchOutlined, ReloadOutlined, ExclamationCircleOutlined,
  CheckCircleOutlined, EyeOutlined, RocketOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { apiClient, handleApiError } from '../services/api';
import styles from './DishHealthPage.module.css';

const { Title, Text } = Typography;
const { Option } = Select;

// ── 常量 ──────────────────────────────────────────────────────────────────────

const TIER_CONFIG: Record<string, { label: string; color: string; antColor: string; rowClass: string }> = {
  excellent: { label: '优秀', color: '#1A7A52', antColor: 'green',  rowClass: 'rowExcellent' },
  good:      { label: '良好', color: '#FF6B2C', antColor: 'blue',   rowClass: 'rowGood' },
  fair:      { label: '一般', color: '#faad14', antColor: 'gold',   rowClass: 'rowFair' },
  poor:      { label: '较差', color: '#C53030', antColor: 'red',    rowClass: 'rowPoor' },
};

const PRIORITY_CONFIG: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  immediate: { label: '立即介入', color: '#C53030', icon: <ExclamationCircleOutlined /> },
  monitor:   { label: '密切观察', color: '#faad14', icon: <EyeOutlined /> },
  maintain:  { label: '保持现状', color: '#FF6B2C', icon: <CheckCircleOutlined /> },
  promote:   { label: '重点推广', color: '#1A7A52', icon: <RocketOutlined /> },
};

const COMPONENT_LABELS: Record<string, string> = {
  profitability: '盈利能力',
  growth:        '成长性',
  benchmark:     '跨店对标',
  forecast:      '预测成熟度',
};

const DEFAULT_STORE = localStorage.getItem('store_id') || '';
const DEFAULT_PERIOD = dayjs().subtract(1, 'month').format('YYYY-MM');

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface HealthRec {
  id: number;
  dish_id: string;
  dish_name: string;
  category: string;
  profitability_score: number;
  growth_score: number;
  benchmark_score: number;
  forecast_score: number;
  total_score: number;
  health_tier: string;
  top_strength: string;
  top_weakness: string;
  action_priority: string;
  action_label: string;
  action_description: string;
  expected_impact_yuan: number;
  lifecycle_phase: string;
  revenue_yuan: number;
}

interface TierRow {
  health_tier: string;
  dish_count: number;
  avg_score: number;
  total_impact: number;
  avg_profitability: number;
  avg_growth: number;
  avg_benchmark: number;
  avg_forecast: number;
}

interface SummaryData {
  store_id: string;
  period: string;
  total_dishes: number;
  total_impact_yuan: number;
  by_tier: TierRow[];
}

interface PriorityItem {
  dish_id: string;
  dish_name: string;
  category: string;
  health_tier: string;
  total_score: number;
  top_weakness: string;
  action_label: string;
  action_description: string;
  expected_impact_yuan: number;
  lifecycle_phase: string;
  revenue_yuan: number;
}

interface HistoryRec {
  period: string;
  total_score: number;
  health_tier: string;
  profitability_score: number;
  growth_score: number;
  benchmark_score: number;
  forecast_score: number;
  action_priority: string;
  lifecycle_phase: string;
  expected_impact_yuan: number;
}

// ── 辅助组件 ──────────────────────────────────────────────────────────────────

function scoreBar(score: number, max = 100) {
  const pct = Math.round((score / max) * 100);
  const color = pct >= 80 ? '#1A7A52' : pct >= 60 ? '#FF6B2C' : pct >= 40 ? '#faad14' : '#C53030';
  return (
    <div style={{ minWidth: 110 }}>
      <Progress percent={pct} strokeColor={color} size="small" format={() => score.toFixed(1)} />
    </div>
  );
}

function tierTag(tier: string) {
  const cfg = TIER_CONFIG[tier] ?? { label: tier, antColor: 'default' };
  return <Tag color={cfg.antColor}>{cfg.label}</Tag>;
}

function priorityTag(priority: string) {
  const cfg = PRIORITY_CONFIG[priority];
  if (!cfg) return <Tag>{priority}</Tag>;
  return <Tag color={cfg.color} icon={cfg.icon}>{cfg.label}</Tag>;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tab 1 — 健康评分看板
// ═══════════════════════════════════════════════════════════════════════════════

const HealthBoard: React.FC<{ storeId: string }> = ({ storeId }) => {
  const [period, setPeriod]       = useState(DEFAULT_PERIOD);
  const [tier, setTier]           = useState<string | undefined>(undefined);
  const [limit, setLimit]         = useState(100);
  const [data, setData]           = useState<HealthRec[]>([]);
  const [count, setCount]         = useState(0);
  const [loading, setLoading]     = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = { period, limit };
      if (tier) params.health_tier = tier;
      const resp = await apiClient.get(`/api/v1/dish-health/${storeId}`, { params });
      setData(resp.data.scores ?? []);
      setCount(resp.data.count ?? 0);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId, period, tier, limit]);

  useEffect(() => { load(); }, [load]);

  const cols = [
    { title: '菜品', dataIndex: 'dish_name', width: 130,
      render: (n: string, r: HealthRec) =>
        <span><Text strong>{n}</Text><br/><Text type="secondary" style={{fontSize:11}}>{r.category}</Text></span> },
    { title: '等级', dataIndex: 'health_tier', width: 75,
      render: (v: string) => tierTag(v) },
    { title: '综合评分', dataIndex: 'total_score', width: 160,
      render: (v: number) => scoreBar(v) },
    { title: '盈利', dataIndex: 'profitability_score', width: 90, align: 'right' as const,
      render: (v: number) => <Tooltip title="盈利能力 (0-25)">{v.toFixed(1)}</Tooltip> },
    { title: '成长', dataIndex: 'growth_score', width: 90, align: 'right' as const,
      render: (v: number) => <Tooltip title="成长性 (0-25)">{v.toFixed(1)}</Tooltip> },
    { title: '对标', dataIndex: 'benchmark_score', width: 90, align: 'right' as const,
      render: (v: number) => <Tooltip title="跨店对标 (0-25)">{v.toFixed(1)}</Tooltip> },
    { title: '预测', dataIndex: 'forecast_score', width: 90, align: 'right' as const,
      render: (v: number) => <Tooltip title="预测成熟度 (0-25)">{v.toFixed(1)}</Tooltip> },
    { title: '弱项', dataIndex: 'top_weakness', width: 90,
      render: (v: string) => <Tag>{COMPONENT_LABELS[v] ?? v}</Tag> },
    { title: '行动', dataIndex: 'action_priority', width: 100,
      render: (v: string) => priorityTag(v) },
    { title: '改善空间', dataIndex: 'expected_impact_yuan', width: 100, align: 'right' as const,
      render: (v: number) => <span className={styles.impact}>¥{v.toFixed(0)}</span> },
  ];

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <span>数据期：</span>
        <Input value={period} onChange={e => setPeriod(e.target.value)}
               placeholder="YYYY-MM" style={{ width: 110 }} />
        <span>健康等级：</span>
        <Select allowClear placeholder="全部" style={{ width: 100 }} value={tier} onChange={setTier}>
          {Object.entries(TIER_CONFIG).map(([k, v]) =>
            <Option key={k} value={k}>{v.label}</Option>)}
        </Select>
        <span>最多：</span>
        <InputNumber min={1} max={500} value={limit}
                     onChange={v => setLimit(v ?? 100)} style={{ width: 80 }} />
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
      </Space>
      <Text type="secondary" style={{ marginBottom: 8, display: 'block' }}>
        共 {count} 道菜品（悬停维度分可查看说明）
      </Text>
      <Table
        dataSource={data}
        columns={cols}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={{ pageSize: 50, showSizeChanger: true }}
        rowClassName={r => styles[TIER_CONFIG[r.health_tier]?.rowClass ?? ''] ?? ''}
        scroll={{ x: 980 }}
      />
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// Tab 2 — 评分分布
// ═══════════════════════════════════════════════════════════════════════════════

const ScoreDistribution: React.FC<{ storeId: string }> = ({ storeId }) => {
  const [period, setPeriod]     = useState(DEFAULT_PERIOD);
  const [summary, setSummary]   = useState<SummaryData | null>(null);
  const [loading, setLoading]   = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/dish-health/summary/${storeId}`,
                                        { params: { period } });
      setSummary(resp.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId, period]);

  useEffect(() => { load(); }, [load]);

  const pieOption = summary ? {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie', radius: ['40%', '65%'],
      data: summary.by_tier.map(r => ({
        name: TIER_CONFIG[r.health_tier]?.label ?? r.health_tier,
        value: r.dish_count,
        itemStyle: { color: TIER_CONFIG[r.health_tier]?.color },
      })),
    }],
  } : {};

  const radarOption = summary && summary.by_tier.length ? {
    tooltip: {},
    legend: { data: summary.by_tier.map(r => TIER_CONFIG[r.health_tier]?.label ?? r.health_tier) },
    radar: {
      indicator: [
        { name: '盈利能力', max: 25 },
        { name: '成长性',   max: 25 },
        { name: '跨店对标', max: 25 },
        { name: '预测成熟', max: 25 },
      ],
    },
    series: [{
      type: 'radar',
      data: summary.by_tier.map(r => ({
        name: TIER_CONFIG[r.health_tier]?.label ?? r.health_tier,
        value: [r.avg_profitability, r.avg_growth, r.avg_benchmark, r.avg_forecast],
        itemStyle: { color: TIER_CONFIG[r.health_tier]?.color },
        areaStyle: { opacity: 0.15 },
      })),
    }],
  } : {};

  const impactBarOption = summary ? {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: summary.by_tier.map(r => TIER_CONFIG[r.health_tier]?.label ?? r.health_tier) },
    yAxis: { type: 'value', name: '改善空间(¥)' },
    series: [{
      type: 'bar',
      data: summary.by_tier.map(r => ({
        value: r.total_impact.toFixed(0),
        itemStyle: { color: TIER_CONFIG[r.health_tier]?.color },
      })),
    }],
  } : {};

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <span>数据期：</span>
        <Input value={period} onChange={e => setPeriod(e.target.value)}
               placeholder="YYYY-MM" style={{ width: 110 }} />
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
      </Space>

      {summary && (
        <>
          <Row gutter={16} style={{ marginBottom: 24 }}>
            <Col span={6}><Card><Statistic title="评分菜品" value={summary.total_dishes} suffix="道" /></Card></Col>
            <Col span={6}><Card><Statistic title="总改善空间" value={summary.total_impact_yuan.toFixed(0)} prefix="¥" /></Card></Col>
            <Col span={6}><Card><Statistic title="健康等级数" value={summary.by_tier.length} suffix="级" /></Card></Col>
            <Col span={6}><Card><Statistic title="数据期" value={summary.period} /></Card></Col>
          </Row>

          <Row gutter={16}>
            <Col span={8}>
              <Card title="菜品等级分布" size="small">
                <ReactECharts option={pieOption} style={{ height: 280 }} />
              </Card>
            </Col>
            <Col span={16}>
              <Card title="4 维度均分雷达（按等级对比）" size="small">
                <ReactECharts option={radarOption} style={{ height: 280 }} />
              </Card>
            </Col>
          </Row>

          <Row gutter={16} style={{ marginTop: 16 }}>
            <Col span={12}>
              <Card title="各等级总改善空间(¥)" size="small">
                <ReactECharts option={impactBarOption} style={{ height: 220 }} />
              </Card>
            </Col>
            <Col span={12}>
              <Card title="等级详情" size="small">
                <Table
                  dataSource={summary.by_tier}
                  rowKey="health_tier"
                  size="small"
                  pagination={false}
                  columns={[
                    { title: '等级', dataIndex: 'health_tier', render: (v: string) => tierTag(v) },
                    { title: '菜品', dataIndex: 'dish_count', align: 'right' as const },
                    { title: '均分', dataIndex: 'avg_score', align: 'right' as const, render: (v: number) => v.toFixed(1) },
                    { title: '改善¥', dataIndex: 'total_impact', align: 'right' as const, render: (v: number) => `¥${v.toFixed(0)}` },
                  ]}
                />
              </Card>
            </Col>
          </Row>
        </>
      )}
      {loading && <div style={{ textAlign: 'center', padding: 48 }}><Spin size="large" /></div>}
      {!loading && !summary && <Empty style={{ padding: 48 }} />}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// Tab 3 — 行动优先级
// ═══════════════════════════════════════════════════════════════════════════════

const ActionPriorities: React.FC<{ storeId: string }> = ({ storeId }) => {
  const [period, setPeriod]     = useState(DEFAULT_PERIOD);
  const [priority, setPriority] = useState<string>('immediate');
  const [limit, setLimit]       = useState(20);
  const [items, setItems]       = useState<PriorityItem[]>([]);
  const [loading, setLoading]   = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/dish-health/priorities/${storeId}`, {
        params: { period, priority, limit },
      });
      setItems(resp.data.items ?? []);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId, period, priority, limit]);

  useEffect(() => { load(); }, [load]);

  const cfg = PRIORITY_CONFIG[priority];

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <span>数据期：</span>
        <Input value={period} onChange={e => setPeriod(e.target.value)}
               placeholder="YYYY-MM" style={{ width: 110 }} />
        <span>优先级：</span>
        <Select value={priority} onChange={setPriority} style={{ width: 120 }}>
          {Object.entries(PRIORITY_CONFIG).map(([k, v]) =>
            <Option key={k} value={k}>{v.label}</Option>)}
        </Select>
        <InputNumber min={1} max={100} value={limit}
                     onChange={v => setLimit(v ?? 20)} addonBefore="最多" style={{ width: 110 }} />
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
      </Space>

      {items.length > 0 && (
        <Alert
          type={priority === 'immediate' ? 'error' : priority === 'monitor' ? 'warning' : 'success'}
          showIcon
          style={{ marginBottom: 16 }}
          message={`${cfg?.label} — 共 ${items.length} 道菜品，合计改善空间 ¥${items.reduce((s, r) => s + r.expected_impact_yuan, 0).toFixed(0)}`}
        />
      )}

      <Row gutter={[12, 12]}>
        {items.map(item => (
          <Col key={item.dish_id} xs={24} sm={12} md={8} lg={6}>
            <Card
              size="small"
              className={styles.actionCard}
              style={{ borderLeft: `4px solid ${cfg?.color}` }}
              title={
                <Space>
                  <Text strong>{item.dish_name}</Text>
                  {tierTag(item.health_tier)}
                </Space>
              }
            >
              <div className={styles.scoreRow}>
                <Text type="secondary">综合评分</Text>
                <Text strong style={{ color: TIER_CONFIG[item.health_tier]?.color }}>
                  {item.total_score.toFixed(1)}
                </Text>
              </div>
              <div className={styles.scoreRow}>
                <Text type="secondary">弱项维度</Text>
                <Tag>{COMPONENT_LABELS[item.top_weakness] ?? item.top_weakness}</Tag>
              </div>
              <div className={styles.scoreRow}>
                <Text type="secondary">改善空间</Text>
                <Text strong className={styles.impact}>¥{item.expected_impact_yuan.toFixed(0)}</Text>
              </div>
              <div style={{ marginTop: 8, fontSize: 12, color: '#666' }}>
                {item.action_description}
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      {loading && <div style={{ textAlign: 'center', padding: 48 }}><Spin size="large" /></div>}
      {!loading && items.length === 0 && (
        <Empty description={`暂无「${cfg?.label}」类菜品`} style={{ padding: 48 }} />
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// Tab 4 — 菜品健康历史
// ═══════════════════════════════════════════════════════════════════════════════

const DishHealthHistory: React.FC<{ storeId: string }> = ({ storeId }) => {
  const [dishId, setDishId]         = useState('');
  const [inputDishId, setInputDishId] = useState('');
  const [periods, setPeriods]       = useState(6);
  const [history, setHistory]       = useState<HistoryRec[]>([]);
  const [loading, setLoading]       = useState(false);

  const load = useCallback(async (id: string) => {
    if (!id) return;
    setLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/dish-health/dish/${storeId}/${id}`,
                                        { params: { periods } });
      setHistory(resp.data.history ?? []);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId, periods]);

  const handleSearch = () => {
    const id = inputDishId.trim();
    setDishId(id);
    load(id);
  };

  const sortedHistory = [...history].sort((a, b) => a.period.localeCompare(b.period));

  const lineOption = sortedHistory.length ? {
    tooltip: { trigger: 'axis' },
    legend: { data: ['综合评分', '盈利能力', '成长性', '跨店对标', '预测成熟'] },
    xAxis: { type: 'category', data: sortedHistory.map(r => r.period) },
    yAxis: { type: 'value', min: 0, max: 100, name: '评分' },
    series: [
      { name: '综合评分', type: 'line', symbol: 'circle', lineStyle: { width: 2 },
        data: sortedHistory.map(r => r.total_score),
        itemStyle: { color: '#FF6B2C' } },
      { name: '盈利能力', type: 'bar', stack: 'score', barMaxWidth: 30,
        data: sortedHistory.map(r => r.profitability_score),
        itemStyle: { color: 'rgba(82,196,26,0.6)' } },
      { name: '成长性', type: 'bar', stack: 'score',
        data: sortedHistory.map(r => r.growth_score),
        itemStyle: { color: 'rgba(22,119,255,0.6)' } },
      { name: '跨店对标', type: 'bar', stack: 'score',
        data: sortedHistory.map(r => r.benchmark_score),
        itemStyle: { color: 'rgba(250,173,20,0.6)' } },
      { name: '预测成熟', type: 'bar', stack: 'score',
        data: sortedHistory.map(r => r.forecast_score),
        itemStyle: { color: 'rgba(245,34,45,0.4)' } },
    ],
  } : {};

  const cols = [
    { title: '期间', dataIndex: 'period', width: 90 },
    { title: '综合分', dataIndex: 'total_score', width: 120,
      render: (v: number) => scoreBar(v) },
    { title: '等级', dataIndex: 'health_tier', width: 75,
      render: (v: string) => tierTag(v) },
    { title: '盈利', dataIndex: 'profitability_score', width: 80, align: 'right' as const, render: (v: number) => v.toFixed(1) },
    { title: '成长', dataIndex: 'growth_score', width: 80, align: 'right' as const, render: (v: number) => v.toFixed(1) },
    { title: '对标', dataIndex: 'benchmark_score', width: 80, align: 'right' as const, render: (v: number) => v.toFixed(1) },
    { title: '预测', dataIndex: 'forecast_score', width: 80, align: 'right' as const, render: (v: number) => v.toFixed(1) },
    { title: '行动', dataIndex: 'action_priority', width: 100,
      render: (v: string) => priorityTag(v) },
    { title: '改善¥', dataIndex: 'expected_impact_yuan', width: 90, align: 'right' as const,
      render: (v: number) => `¥${v.toFixed(0)}` },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 20 }}>
        <Input
          value={inputDishId}
          onChange={e => setInputDishId(e.target.value)}
          onPressEnter={handleSearch}
          placeholder="输入菜品 ID"
          style={{ width: 180 }}
        />
        <InputNumber min={1} max={24} value={periods} onChange={v => setPeriods(v ?? 6)}
                     addonBefore="期数" style={{ width: 120 }} />
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>查询</Button>
      </Space>

      {dishId && loading && <div style={{ textAlign: 'center', padding: 48 }}><Spin size="large" /></div>}

      {dishId && !loading && history.length === 0 && (
        <Empty description={`菜品 ${dishId} 暂无健康评分历史`} style={{ padding: 48 }} />
      )}

      {history.length > 0 && (
        <>
          <Card title={`菜品 ${dishId} — 综合评分走势（折线=综合分，堆叠柱=4维度分解）`}
                size="small" style={{ marginBottom: 16 }}>
            <ReactECharts option={lineOption} style={{ height: 300 }} />
          </Card>
          <Table
            dataSource={history}
            columns={cols}
            rowKey="period"
            size="small"
            pagination={false}
            scroll={{ x: 700 }}
          />
        </>
      )}

      {!dishId && (
        <Empty description="请输入菜品 ID 查看健康评分历史走势" style={{ padding: 64 }} />
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// 主页面
// ═══════════════════════════════════════════════════════════════════════════════

const DishHealthPage: React.FC = () => {
  const [storeId, setStoreId]     = useState(DEFAULT_STORE);
  const [period, setPeriod]       = useState(DEFAULT_PERIOD);
  const [computing, setComputing] = useState(false);
  const [compResult, setCompResult] = useState<{
    dish_count: number; tier_counts: Record<string, number>; total_impact_yuan: number;
  } | null>(null);

  const handleCompute = async () => {
    setComputing(true);
    setCompResult(null);
    try {
      const resp = await apiClient.post(
        `/api/v1/dish-health/compute/${storeId}`,
        null,
        { params: { period } },
      );
      setCompResult(resp.data);
    } catch (e) { handleApiError(e); }
    finally { setComputing(false); }
  };

  const items = [
    { key: 'board',    label: '健康评分看板',  children: <HealthBoard storeId={storeId} /> },
    { key: 'dist',     label: '评分分布',      children: <ScoreDistribution storeId={storeId} /> },
    { key: 'actions',  label: '行动优先级',    children: <ActionPriorities storeId={storeId} /> },
    { key: 'history',  label: '菜品健康历史',  children: <DishHealthHistory storeId={storeId} /> },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Title level={4} style={{ margin: 0 }}>菜品综合健康评分引擎</Title>
        <Space wrap>
          <span>门店：</span>
          <Input value={storeId} onChange={e => setStoreId(e.target.value)}
                 placeholder="门店ID" style={{ width: 90 }} />
          <span>数据期：</span>
          <Input value={period} onChange={e => setPeriod(e.target.value)}
                 placeholder="YYYY-MM" style={{ width: 110 }} />
          <Button type="primary" onClick={handleCompute} loading={computing}>
            计算健康评分
          </Button>
        </Space>
      </div>

      {compResult && (
        <Alert
          type="success"
          showIcon
          closable
          style={{ marginBottom: 12 }}
          message={
            `评分完成：${compResult.dish_count} 道菜品，` +
            `优秀 ${compResult.tier_counts['excellent'] ?? 0} / 良好 ${compResult.tier_counts['good'] ?? 0} / ` +
            `一般 ${compResult.tier_counts['fair'] ?? 0} / 较差 ${compResult.tier_counts['poor'] ?? 0}，` +
            `总改善空间 ¥${compResult.total_impact_yuan.toFixed(0)}`
          }
        />
      )}

      <Tabs items={items} defaultActiveKey="board" />
    </div>
  );
};

export default DishHealthPage;
