/**
 * 菜品生命周期管理引擎 — Phase 6 Month 6
 * 追踪每道菜的生命阶段（上市/成长/成熟/衰退/退出），检测阶段跃迁，生成阶段匹配行动建议
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Row, Col, Card, Statistic, Select, Button, Table, Tag, Tabs, Spin,
  Typography, Space, Tooltip, message, Empty, Input, Timeline, Alert,
} from 'antd';
import {
  RocketOutlined, RiseOutlined, TrophyOutlined, FallOutlined,
  PoweroffOutlined, SyncOutlined, SearchOutlined, WarningOutlined,
  HistoryOutlined, BarChartOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { apiClient, handleApiError } from '../services/api';
import styles from './DishLifecyclePage.module.css';

const { Title, Text } = Typography;
const { Option } = Select;

// ── 配置 ──────────────────────────────────────────────────────────────────────
const PHASE_CONFIG: Record<string, {
  label: string; antColor: string; color: string;
  icon: React.ReactNode; rowClass: string;
}> = {
  launch:  { label: '上市', antColor: 'processing', color: '#FF6B2C', icon: <RocketOutlined />, rowClass: styles.rowLaunch },
  growth:  { label: '成长', antColor: 'success',    color: '#1A7A52', icon: <RiseOutlined />,   rowClass: '' },
  peak:    { label: '成熟', antColor: 'green',       color: '#389e0d', icon: <TrophyOutlined />, rowClass: '' },
  decline: { label: '衰退', antColor: 'warning',     color: '#C8923A', icon: <FallOutlined />,   rowClass: styles.rowDecline },
  exit:    { label: '退出', antColor: 'error',        color: '#C53030', icon: <PoweroffOutlined />, rowClass: styles.rowExit },
};

const PHASE_ORDER = ['launch', 'growth', 'peak', 'decline', 'exit'];

// ── 类型 ──────────────────────────────────────────────────────────────────────
interface LifecycleRecord {
  id: number;
  dish_id: string;
  dish_name: string;
  category: string;
  bcg_quadrant: string;
  order_count: number;
  revenue_yuan: number;
  gross_profit_margin: number;
  food_cost_rate: number;
  revenue_trend_pct: number;
  order_trend_pct: number;
  fcr_trend_pp: number;
  phase: string;
  prev_phase: string | null;
  phase_changed: boolean;
  phase_duration_months: number;
  action_label: string;
  action_description: string;
  expected_impact_yuan: number;
  confidence_pct: number;
}

interface PhaseStat {
  phase: string;
  dish_count: number;
  transition_count: number;
  total_impact: number;
  avg_duration: number;
  avg_rev_trend: number;
  total_revenue: number;
  action_label: string;
}

interface Summary {
  store_id: string;
  period: string;
  total_dishes: number;
  total_transitions: number;
  by_phase: PhaseStat[];
  total_impact_yuan: number;
}

interface TransitionAlert {
  dish_id: string;
  dish_name: string;
  category: string;
  bcg_quadrant: string;
  prev_phase: string;
  phase: string;
  phase_duration_months: number;
  revenue_trend_pct: number;
  order_trend_pct: number;
  revenue_yuan: number;
  expected_impact_yuan: number;
  action_label: string;
  action_description: string;
}

interface HistoryPoint {
  period: string;
  bcg_quadrant: string;
  phase: string;
  prev_phase: string | null;
  phase_changed: boolean;
  phase_duration_months: number;
  revenue_yuan: number;
  order_count: number;
  revenue_trend_pct: number;
  order_trend_pct: number;
  action_label: string;
  expected_impact_yuan: number;
}

// ── 辅助 ──────────────────────────────────────────────────────────────────────
const fmt    = (n: number) => `¥${Math.abs(n).toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}`;
const fmtPct = (n: number) => `${Number(n).toFixed(1)}%`;
const fmtTrend = (n: number) => (
  <Text style={{ color: n >= 0 ? '#1A7A52' : '#C53030' }}>
    {n >= 0 ? '+' : ''}{Number(n).toFixed(1)}%
  </Text>
);

const PhaseTag: React.FC<{ phase: string }> = ({ phase }) => {
  const cfg = PHASE_CONFIG[phase] || { label: phase, antColor: 'default', icon: null };
  return <Tag color={cfg.antColor}>{cfg.icon} {cfg.label}</Tag>;
};

// ── 主页面 ────────────────────────────────────────────────────────────────────
const DishLifecyclePage: React.FC = () => {
  const [storeId,      setStoreId]      = useState(localStorage.getItem('store_id') || '');
  const [storeOptions, setStoreOptions] = useState<string[]>([]);
  const [period,       setPeriod]       = useState(dayjs().subtract(1, 'month').format('YYYY-MM'));

  useEffect(() => {
    apiClient.get<{ items: Array<{ id: string }> }>('/api/v1/stores?limit=50')
      .then(data => {
        const ids = (data.items ?? []).map((s: { id: string }) => s.id).filter(Boolean);
        if (ids.length > 0) setStoreOptions(ids);
      })
      .catch(() => { /* 保持默认 */ });
  }, []);
  const [computing, setComputing] = useState(false);
  const [loading,   setLoading]   = useState(false);
  const [records,   setRecords]   = useState<LifecycleRecord[]>([]);
  const [summary,   setSummary]   = useState<Summary | null>(null);
  const [transitions, setTransitions] = useState<TransitionAlert[]>([]);
  const [phaseFilter, setPhaseFilter] = useState<string | undefined>(undefined);
  const [activeTab, setActiveTab] = useState('board');
  // 菜品生命线
  const [dishQuery, setDishQuery]   = useState('');
  const [history,   setHistory]     = useState<HistoryPoint[]>([]);
  const [histLoading, setHistLoading] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [recRes, sumRes, transRes] = await Promise.all([
        apiClient.get(`/api/v1/dish-lifecycle/${storeId}`, {
          params: { period, phase: phaseFilter, limit: 200 },
        }),
        apiClient.get(`/api/v1/dish-lifecycle/summary/${storeId}`, { params: { period } }),
        apiClient.get(`/api/v1/dish-lifecycle/transitions/${storeId}`, { params: { period } }),
      ]);
      setRecords(recRes.data.records         || []);
      setSummary(sumRes.data                 || null);
      setTransitions(transRes.data.transitions || []);
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  }, [storeId, period, phaseFilter]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleCompute = async () => {
    setComputing(true);
    try {
      const res = await apiClient.post(
        `/api/v1/dish-lifecycle/compute/${storeId}`, null, { params: { period } }
      );
      message.success(
        `生命周期分析完成：${res.data.dish_count} 道菜，` +
        `${res.data.transition_count} 次阶段跃迁，` +
        `总行动¥潜力 ${fmt(res.data.total_impact_yuan)}`
      );
      fetchAll();
    } catch (e) { handleApiError(e); }
    finally { setComputing(false); }
  };

  const handleQueryHistory = async () => {
    const q = dishQuery.trim();
    if (!q) { message.warning('请输入菜品ID或名称'); return; }
    setHistLoading(true);
    try {
      const res = await apiClient.get(
        `/api/v1/dish-lifecycle/dish/${storeId}/${encodeURIComponent(q)}`,
        { params: { periods: 12 } }
      );
      setHistory(res.data.history || []);
      if ((res.data.history || []).length === 0)
        message.info('暂无该菜品生命周期数据');
    } catch (e) { handleApiError(e); }
    finally { setHistLoading(false); }
  };

  // ── KPI ───────────────────────────────────────────────────────────────────
  const totalDishes    = summary?.total_dishes     ?? 0;
  const totalTrans     = summary?.total_transitions ?? 0;
  const totalImpact    = summary?.total_impact_yuan ?? 0;
  const exitCount      = summary?.by_phase.find(p => p.phase === 'exit')?.dish_count ?? 0;
  const declineCount   = summary?.by_phase.find(p => p.phase === 'decline')?.dish_count ?? 0;

  // ── 阶段分布饼图 ──────────────────────────────────────────────────────────
  const phasePieOption = () => {
    if (!summary) return {};
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'item', formatter: '{b}: {c}道 ({d}%)' },
      series: [{
        type: 'pie', radius: ['40%', '70%'],
        data: summary.by_phase
          .filter(p => p.dish_count > 0)
          .map(p => ({
            name: PHASE_CONFIG[p.phase]?.label || p.phase,
            value: p.dish_count,
            itemStyle: { color: PHASE_CONFIG[p.phase]?.color || '#aaa' },
          })),
        label: { formatter: '{b}\n{c}道' },
      }],
    };
  };

  // ── 各阶段¥影响柱图 ───────────────────────────────────────────────────────
  const impactBarOption = () => {
    if (!summary) return {};
    const phases = summary.by_phase.filter(p => p.dish_count > 0);
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 60, right: 20, top: 30, bottom: 50 },
      xAxis: { type: 'category', data: phases.map(p => PHASE_CONFIG[p.phase]?.label || p.phase) },
      yAxis: { type: 'value', name: '¥' },
      series: [{
        name: '行动¥潜力', type: 'bar',
        data: phases.map(p => ({
          value: p.total_impact.toFixed(0),
          itemStyle: { color: PHASE_CONFIG[p.phase]?.color || '#aaa' },
        })),
        label: { show: true, position: 'top', formatter: (v: any) => `¥${v.value}` },
      }],
    };
  };

  // ── 生命线营收折线图 ──────────────────────────────────────────────────────
  const historyLineOption = () => {
    const sorted = [...history].reverse();
    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        formatter: (params: any[]) => {
          const p = params[0];
          const h = sorted[p.dataIndex];
          return `${p.name}<br/>营收: ${fmt(h.revenue_yuan)}<br/>阶段: ${PHASE_CONFIG[h.phase]?.label || h.phase}<br/>趋势: ${h.revenue_trend_pct > 0 ? '+' : ''}${h.revenue_trend_pct.toFixed(1)}%`;
        },
      },
      xAxis: { type: 'category', data: sorted.map(h => h.period) },
      yAxis: { type: 'value', name: '¥营收', axisLabel: { formatter: (v: number) => `¥${(v/1000).toFixed(0)}k` } },
      series: [{
        type: 'line', smooth: true,
        data: sorted.map(h => ({
          value: h.revenue_yuan,
          itemStyle: { color: PHASE_CONFIG[h.phase]?.color || '#aaa' },
          symbol: h.phase_changed ? 'diamond' : 'circle',
          symbolSize: h.phase_changed ? 12 : 6,
        })),
        lineStyle: { color: '#FF6B2C', width: 2 },
        areaStyle: { color: 'rgba(22,119,255,0.08)' },
      }],
    };
  };

  // ── 看板列 ───────────────────────────────────────────────────────────────
  const columns = [
    {
      title: '菜品', dataIndex: 'dish_name', width: 130,
      render: (n: string, r: LifecycleRecord) => (
        <Space direction="vertical" size={0}>
          <Text strong>{n}</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>{r.category}</Text>
        </Space>
      ),
    },
    {
      title: '生命阶段', dataIndex: 'phase', width: 95,
      render: (p: string, r: LifecycleRecord) => (
        <Space direction="vertical" size={2}>
          <PhaseTag phase={p} />
          {r.phase_changed && (
            <Tag color="volcano" style={{ fontSize: 10, margin: 0 }}>
              ↑↓ 跃迁
            </Tag>
          )}
        </Space>
      ),
    },
    {
      title: '已在本阶段', dataIndex: 'phase_duration_months', width: 95,
      render: (v: number) => `${v}个月`,
    },
    {
      title: '营收趋势', dataIndex: 'revenue_trend_pct', width: 85,
      sorter: (a: LifecycleRecord, b: LifecycleRecord) => a.revenue_trend_pct - b.revenue_trend_pct,
      render: fmtTrend,
    },
    {
      title: '销量趋势', dataIndex: 'order_trend_pct', width: 85,
      render: fmtTrend,
    },
    {
      title: '当期营收', dataIndex: 'revenue_yuan', width: 90,
      render: (v: number) => fmt(v),
    },
    {
      title: '建议动作', dataIndex: 'action_label', width: 115,
      render: (l: string, r: LifecycleRecord) => (
        <Tooltip title={r.action_description}>
          <Tag color={PHASE_CONFIG[r.phase]?.antColor || 'default'}>{l}</Tag>
        </Tooltip>
      ),
    },
    {
      title: '行动¥潜力', dataIndex: 'expected_impact_yuan', width: 95,
      sorter: (a: LifecycleRecord, b: LifecycleRecord) =>
        b.expected_impact_yuan - a.expected_impact_yuan,
      defaultSortOrder: 'descend' as const,
      render: (v: number) => <Text style={{ color: '#1A7A52' }}>{fmt(v)}</Text>,
    },
    {
      title: '置信度', dataIndex: 'confidence_pct', width: 75,
      render: (v: number) => fmtPct(v),
    },
  ];

  const periodOptions = Array.from({ length: 12 }, (_, i) =>
    dayjs().subtract(i + 1, 'month').format('YYYY-MM')
  );

  const isDeclineTransition = (t: TransitionAlert) =>
    ['decline', 'exit'].includes(t.phase);

  return (
    <div className={styles.page}>
      {/* ── 顶部控制 ─────────────────────────────────────────────────────── */}
      <div className={styles.header}>
        <Title level={4} style={{ margin: 0 }}>
          <HistoryOutlined /> 菜品生命周期
        </Title>
        <Space>
          <Select value={storeId} onChange={setStoreId} style={{ width: 120 }}>
            {storeOptions.map(s => <Option key={s} value={s}>{s}</Option>)}
          </Select>
          <Select value={period} onChange={setPeriod} style={{ width: 120 }}>
            {periodOptions.map(p => <Option key={p} value={p}>{p}</Option>)}
          </Select>
          <Tooltip title="基于BCG变化+环比趋势，为每道菜标注生命阶段与行动建议">
            <Button type="primary" icon={<SyncOutlined spin={computing} />}
              onClick={handleCompute} loading={computing}>
              分析生命周期
            </Button>
          </Tooltip>
        </Space>
      </div>

      {/* ── 跃迁预警横幅 ─────────────────────────────────────────────────── */}
      {(exitCount > 0 || declineCount > 0) && (
        <Alert
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          message={
            `${exitCount > 0 ? `${exitCount} 道菜进入退出期` : ''}` +
            `${exitCount > 0 && declineCount > 0 ? '，' : ''}` +
            `${declineCount > 0 ? `${declineCount} 道菜处于衰退期` : ''}` +
            ` — 共涉及 ${fmt(
              (summary?.by_phase.filter(p => ['exit','decline'].includes(p.phase))
                .reduce((s, p) => s + p.total_impact, 0) ?? 0)
            )} 行动¥潜力`
          }
          style={{ borderRadius: 8 }}
        />
      )}

      {/* ── KPI 卡片 ─────────────────────────────────────────────────────── */}
      <Row gutter={[16, 16]}>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="分析菜品数" value={totalDishes} suffix="道"
              prefix={<BarChartOutlined />} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="本期阶段跃迁" value={totalTrans} suffix="次"
              prefix={<WarningOutlined />} valueStyle={{ color: '#C8923A' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="退出/衰退菜品" value={exitCount + declineCount} suffix="道"
              prefix={<FallOutlined />} valueStyle={{ color: '#C53030' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="行动¥总潜力" value={totalImpact.toFixed(0)}
              prefix="¥" valueStyle={{ color: '#1A7A52' }} />
          </Card>
        </Col>
      </Row>

      {/* ── 主内容 ───────────────────────────────────────────────────────── */}
      <Card bodyStyle={{ padding: '0 16px 16px' }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
          {
            key: 'board',
            label: <span><BarChartOutlined /> 生命周期看板</span>,
            children: (
              <Spin spinning={loading}>
                <Space style={{ marginBottom: 12 }}>
                  <Select value={phaseFilter} onChange={setPhaseFilter}
                    style={{ width: 120 }} allowClear placeholder="筛选阶段">
                    {PHASE_ORDER.map(p => (
                      <Option key={p} value={p}>
                        {PHASE_CONFIG[p]?.icon} {PHASE_CONFIG[p]?.label}
                      </Option>
                    ))}
                  </Select>
                </Space>
                {records.length === 0 ? (
                  <Empty description="暂无数据，请先点击「分析生命周期」" />
                ) : (
                  <Table
                    dataSource={records}
                    columns={columns}
                    rowKey="id"
                    size="small"
                    pagination={{ pageSize: 20, showSizeChanger: true }}
                    scroll={{ x: 1000 }}
                    rowClassName={(r) => PHASE_CONFIG[r.phase]?.rowClass || ''}
                  />
                )}
              </Spin>
            ),
          },
          {
            key: 'transitions',
            label: (
              <span>
                <WarningOutlined /> 阶段跃迁预警
                {transitions.length > 0 && (
                  <Tag color="volcano" style={{ marginLeft: 4 }}>{transitions.length}</Tag>
                )}
              </span>
            ),
            children: (
              <Spin spinning={loading}>
                {transitions.length === 0 ? (
                  <Empty description="本期无阶段跃迁" />
                ) : (
                  <Row gutter={[12, 0]}>
                    {transitions.map(t => (
                      <Col key={t.dish_id} xs={24} md={12} xl={8} style={{ marginBottom: 12 }}>
                        <Card
                          size="small"
                          className={`${styles.transCard} ${isDeclineTransition(t) ? styles.transCardDown : styles.transCardUp}`}
                        >
                          <Space direction="vertical" size={4} style={{ width: '100%' }}>
                            <Space>
                              <Text strong>{t.dish_name}</Text>
                              <Text type="secondary" style={{ fontSize: 11 }}>{t.category}</Text>
                            </Space>
                            <Space>
                              <PhaseTag phase={t.prev_phase} />
                              <Text>→</Text>
                              <PhaseTag phase={t.phase} />
                            </Space>
                            <Space>
                              <Text style={{ fontSize: 12 }}>营收趋势 {fmtTrend(t.revenue_trend_pct)}</Text>
                              <Text style={{ fontSize: 12 }}>销量趋势 {fmtTrend(t.order_trend_pct)}</Text>
                            </Space>
                            <Space>
                              <Tag color={PHASE_CONFIG[t.phase]?.antColor || 'default'}>
                                {t.action_label}
                              </Tag>
                              <Text style={{ color: '#1A7A52', fontSize: 12 }}>
                                {fmt(t.expected_impact_yuan)}
                              </Text>
                            </Space>
                            <Text type="secondary" style={{ fontSize: 11 }}>
                              {t.action_description}
                            </Text>
                          </Space>
                        </Card>
                      </Col>
                    ))}
                  </Row>
                )}
              </Spin>
            ),
          },
          {
            key: 'distribution',
            label: <span><BarChartOutlined /> 阶段分布</span>,
            children: (
              <Spin spinning={loading}>
                {!summary ? <Empty /> : (
                  <Row gutter={16}>
                    <Col xs={24} lg={10}>
                      <Text strong style={{ display: 'block', marginBottom: 8 }}>
                        当期生命周期阶段分布
                      </Text>
                      <ReactECharts option={phasePieOption()} style={{ height: 280 }} notMerge />
                    </Col>
                    <Col xs={24} lg={14}>
                      <Text strong style={{ display: 'block', marginBottom: 8 }}>
                        各阶段行动¥潜力
                      </Text>
                      <ReactECharts option={impactBarOption()} style={{ height: 280 }} notMerge />
                    </Col>
                    <Col xs={24}>
                      <Table
                        dataSource={summary.by_phase}
                        rowKey="phase"
                        size="small"
                        pagination={false}
                        style={{ marginTop: 12 }}
                        columns={[
                          { title: '阶段', dataIndex: 'phase',
                            render: (p: string) => <PhaseTag phase={p} /> },
                          { title: '菜品数', dataIndex: 'dish_count' },
                          { title: '本期跃迁', dataIndex: 'transition_count',
                            render: (v: number) => v > 0 ? <Tag color="volcano">{v}次</Tag> : '-' },
                          { title: '平均持续(月)', dataIndex: 'avg_duration',
                            render: (v: number) => Number(v).toFixed(1) },
                          { title: '平均营收趋势', dataIndex: 'avg_rev_trend',
                            render: (v: number) => fmtTrend(v) },
                          { title: '行动¥潜力', dataIndex: 'total_impact',
                            render: (v: number) => <Text style={{ color: '#1A7A52' }}>{fmt(v)}</Text> },
                          { title: '建议动作', dataIndex: 'action_label',
                            render: (l: string, r: PhaseStat) =>
                              <Tag color={PHASE_CONFIG[r.phase]?.antColor || 'default'}>{l}</Tag> },
                        ]}
                      />
                    </Col>
                  </Row>
                )}
              </Spin>
            ),
          },
          {
            key: 'timeline',
            label: <span><HistoryOutlined /> 菜品生命线</span>,
            children: (
              <div>
                <Space style={{ marginBottom: 12 }}>
                  <Input
                    value={dishQuery}
                    onChange={e => setDishQuery(e.target.value)}
                    onPressEnter={handleQueryHistory}
                    placeholder="输入菜品ID（如：D001）"
                    style={{ width: 220 }}
                    prefix={<SearchOutlined />}
                  />
                  <Button onClick={handleQueryHistory} loading={histLoading}>
                    查询生命线
                  </Button>
                </Space>
                <Spin spinning={histLoading}>
                  {history.length === 0 ? (
                    <Empty description="输入菜品ID后点击查询" />
                  ) : (
                    <Row gutter={16}>
                      <Col xs={24} lg={14}>
                        <Text strong style={{ display: 'block', marginBottom: 8 }}>
                          近{history.length}期营收走势（◆ = 阶段跃迁点）
                        </Text>
                        <ReactECharts option={historyLineOption()} style={{ height: 260 }} notMerge />
                      </Col>
                      <Col xs={24} lg={10}>
                        <Text strong style={{ display: 'block', marginBottom: 8 }}>
                          阶段流转时间线
                        </Text>
                        <Timeline
                          items={[...history].reverse().map(h => ({
                            color: PHASE_CONFIG[h.phase]?.color || '#aaa',
                            dot: h.phase_changed ? '◆' : undefined,
                            children: (
                              <Space direction="vertical" size={0}>
                                <Space>
                                  <Text strong style={{ fontSize: 12 }}>{h.period}</Text>
                                  <PhaseTag phase={h.phase} />
                                  {h.phase_changed && (
                                    <Tag color="volcano" style={{ fontSize: 10, margin: 0 }}>跃迁</Tag>
                                  )}
                                </Space>
                                <Text type="secondary" style={{ fontSize: 11 }}>
                                  营收 {fmt(h.revenue_yuan)} | 已持续 {h.phase_duration_months} 月
                                  | {h.action_label}
                                </Text>
                              </Space>
                            ),
                          }))}
                        />
                      </Col>
                    </Row>
                  )}
                </Spin>
              </div>
            ),
          },
        ]} />
      </Card>
    </div>
  );
};

export default DishLifecyclePage;
