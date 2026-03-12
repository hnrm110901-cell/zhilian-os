/**
 * 菜品组合矩阵分析页面 — Phase 6 Month 10
 * 4 Tabs: BCG矩阵图 / 汇总分析 / 行动推荐榜 / 菜品象限历史
 */

import React, { useState, useCallback } from 'react';
import {
  Tabs, Table, Tag, Select, Button, Input, Spin, Alert, Tooltip,
  Card, Space, Typography, Row, Col,
} from 'antd';
import { SearchOutlined, SyncOutlined, StarOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';

import { apiClient } from '../services/api';
import styles from './MenuMatrixPage.module.css';

const { Title, Text } = Typography;
const { Option } = Select;

// ── 常量 ─────────────────────────────────────────────────────────────────────

const DEFAULT_STORE  = 'S001';
const DEFAULT_PERIOD = dayjs().subtract(1, 'month').format('YYYY-MM');

const QUADRANT_CONFIG: Record<string, {
  label: string; color: string; bgColor: string;
  borderColor: string; rowClass: string; action: string; actionLabel: string;
  icon: string;
}> = {
  star: {
    label: '明星菜', color: '#d48806', bgColor: '#fffbe6',
    borderColor: '#faad14', rowClass: styles.rowStar,
    action: 'promote', actionLabel: '重点推广', icon: '⭐',
  },
  cash_cow: {
    label: '现金牛菜', color: '#389e0d', bgColor: 'rgba(26,122,82,0.08)',
    borderColor: '#1A7A52', rowClass: styles.rowCashCow,
    action: 'maintain', actionLabel: '稳定维护', icon: '🐄',
  },
  question_mark: {
    label: '问题菜', color: '#0958d9', bgColor: '#e6f4ff',
    borderColor: '#0AAF9A', rowClass: styles.rowQuestionMark,
    action: 'develop', actionLabel: '挖掘潜力', icon: '❓',
  },
  dog: {
    label: '瘦狗菜', color: '#cf1322', bgColor: '#fff2f0',
    borderColor: '#C53030', rowClass: styles.rowDog,
    action: 'retire', actionLabel: '考虑退出', icon: '🐕',
  },
};

const PRIORITY_CLASS: Record<string, string> = {
  high:   styles.prioHigh,
  medium: styles.prioMedium,
  low:    styles.prioLow,
};

const PRIORITY_LABELS: Record<string, string> = {
  high: '紧急', medium: '中等', low: '低',
};

// ── 工具函数 ──────────────────────────────────────────────────────────────────

function fmtYuan(v: number | null | undefined): string {
  if (v == null) return '-';
  return `¥${Number(v).toFixed(2)}`;
}

function QuadrantTag({ quadrant }: { quadrant: string }) {
  const cfg = QUADRANT_CONFIG[quadrant];
  if (!cfg) return <Tag>{quadrant}</Tag>;
  return (
    <Tag style={{ background: cfg.bgColor, borderColor: cfg.borderColor, color: cfg.color }}>
      {cfg.icon} {cfg.label}
    </Tag>
  );
}

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface MatrixRow {
  id: number;
  dish_id: string;
  dish_name: string;
  category: string | null;
  revenue_yuan: number;
  order_count: number;
  menu_contribution_pct: number | null;
  prev_revenue_yuan: number | null;
  revenue_delta_pct: number | null;
  revenue_percentile: number;
  growth_percentile: number;
  matrix_quadrant: string;
  optimization_action: string;
  action_priority: string;
  expected_impact_yuan: number;
}

// ── Tab 1: BCG 矩阵散点图 ─────────────────────────────────────────────────────

function MatrixScatter({ storeId, period }: { storeId: string; period: string }) {
  const [quadrant, setQuadrant]   = useState<string | undefined>(undefined);
  const [loading, setLoading]     = useState(false);
  const [rows, setRows]           = useState<MatrixRow[]>([]);
  const [error, setError]         = useState('');
  const [fetched, setFetched]     = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const params: Record<string, string | number> = { period, limit: 300 };
      if (quadrant) params.quadrant = quadrant;
      const resp = await apiClient.get(`/api/v1/menu-matrix/${storeId}`, { params });
      setRows(resp.data.data ?? []);
      setFetched(true);
    } catch {
      setError('加载失败，请重试');
    } finally {
      setLoading(false);
    }
  }, [storeId, period, quadrant]);

  // 散点图：X = revenue_percentile, Y = growth_percentile
  const scatterOption = rows.length ? (() => {
    const seriesData: Record<string, [number, number, string, number][]> = {
      star: [], cash_cow: [], question_mark: [], dog: [],
    };
    rows.forEach(r => {
      seriesData[r.matrix_quadrant]?.push([
        r.revenue_percentile,
        r.growth_percentile,
        r.dish_name,
        r.revenue_yuan,
      ]);
    });

    const colors: Record<string, string> = {
      star: '#faad14', cash_cow: '#1A7A52',
      question_mark: '#0AAF9A', dog: '#C53030',
    };

    return {
      tooltip: {
        trigger: 'item',
        formatter: (p: { data: [number, number, string, number] }) =>
          `${p.data[2]}<br/>营收百分位: ${p.data[0]}%<br/>增长百分位: ${p.data[1]}%<br/>营收: ¥${p.data[3].toFixed(2)}`,
      },
      legend: { data: Object.values(QUADRANT_CONFIG).map(c => c.label), bottom: 0 },
      xAxis: {
        type: 'value', name: '营收百分位', min: 0, max: 100,
        axisLabel: { formatter: '{value}%' },
        splitLine: [{ lineStyle: { type: 'dashed', color: '#ddd' } }],
      },
      yAxis: {
        type: 'value', name: '增长百分位', min: 0, max: 100,
        axisLabel: { formatter: '{value}%' },
        splitLine: [{ lineStyle: { type: 'dashed', color: '#ddd' } }],
      },
      // 象限分割线
      markLine: {
        silent: true,
        lineStyle: { color: '#bbb', type: 'dashed' },
        data: [{ xAxis: 50 }, { yAxis: 50 }],
      },
      series: Object.entries(seriesData).map(([q, data]) => ({
        name: QUADRANT_CONFIG[q]?.label ?? q,
        type: 'scatter',
        data,
        symbolSize: (d: number[]) => Math.max(8, Math.min(24, d[3] / 500)),
        itemStyle: { color: colors[q] ?? '#ccc', opacity: 0.8 },
      })),
    };
  })() : {};

  const tableCols: ColumnsType<MatrixRow> = [
    { title: '菜品', dataIndex: 'dish_name', width: 120, fixed: 'left',
      render: (v, r) => <><div style={{ fontWeight: 600 }}>{v}</div><Text type="secondary" style={{ fontSize: 11 }}>{r.category ?? '-'}</Text></> },
    { title: '象限', dataIndex: 'matrix_quadrant', width: 110,
      render: v => <QuadrantTag quadrant={v} /> },
    { title: '优先级', dataIndex: 'action_priority', width: 70,
      render: v => <span className={PRIORITY_CLASS[v] ?? ''}>{PRIORITY_LABELS[v] ?? v}</span> },
    { title: '营收百分位', dataIndex: 'revenue_percentile', width: 95, sorter: (a, b) => a.revenue_percentile - b.revenue_percentile,
      render: v => `${v}%` },
    { title: '增长百分位', dataIndex: 'growth_percentile', width: 95, sorter: (a, b) => a.growth_percentile - b.growth_percentile,
      render: v => `${v}%` },
    { title: '增长率', dataIndex: 'revenue_delta_pct', width: 80,
      render: v => v == null ? '-' : <span style={{ color: v >= 0 ? '#1A7A52' : '#C53030' }}>{v >= 0 ? '+' : ''}{v}%</span> },
    { title: '当期营收', dataIndex: 'revenue_yuan', width: 100, sorter: (a, b) => a.revenue_yuan - b.revenue_yuan,
      render: v => fmtYuan(v) },
    { title: '菜单占比', dataIndex: 'menu_contribution_pct', width: 85,
      render: v => v == null ? '-' : `${v}%` },
    { title: '预期影响', dataIndex: 'expected_impact_yuan', width: 100, sorter: (a, b) => a.expected_impact_yuan - b.expected_impact_yuan,
      render: v => <span style={{ color: '#0AAF9A', fontWeight: 600 }}>{fmtYuan(v)}</span> },
  ];

  return (
    <>
      <div className={styles.controlBar}>
        <Select allowClear placeholder="筛选象限" style={{ width: 150 }} value={quadrant} onChange={setQuadrant}>
          {Object.entries(QUADRANT_CONFIG).map(([k, v]) => (
            <Option key={k} value={k}>{v.icon} {v.label}</Option>
          ))}
        </Select>
        <Button type="primary" icon={<SearchOutlined />} onClick={load} loading={loading}>查询</Button>
      </div>
      {error && <Alert type="error" message={error} style={{ marginBottom: 12 }} />}
      {!fetched && !loading && (
        <Alert type="info" message="选择筛选条件后点击查询，或直接查询全部菜品" style={{ marginBottom: 12 }} />
      )}
      {rows.length > 0 && (
        <Card title="BCG 矩阵散点图（X轴: 营收百分位 / Y轴: 增长百分位）" size="small" style={{ marginBottom: 16 }}>
          <ReactECharts option={scatterOption} style={{ height: 380 }} />
        </Card>
      )}
      <Table
        rowKey="id"
        columns={tableCols}
        dataSource={rows}
        loading={loading}
        scroll={{ x: 760 }}
        size="small"
        pagination={{ pageSize: 20, showSizeChanger: true }}
        rowClassName={r => QUADRANT_CONFIG[r.matrix_quadrant]?.rowClass ?? ''}
      />
    </>
  );
}

// ── Tab 2: 汇总分析 ───────────────────────────────────────────────────────────

interface QuadrantItem {
  quadrant: string;
  dish_count: number;
  total_revenue: number;
  avg_rev_pct: number;
  avg_grow_pct: number;
  total_impact: number;
  high_priority_dishes: number;
}

interface Summary {
  store_id: string;
  period: string;
  total_dishes: number;
  total_revenue: number;
  total_expected_impact: number;
  by_quadrant: QuadrantItem[];
}

function SummaryTab({ storeId, period }: { storeId: string; period: string }) {
  const [loading, setLoading] = useState(false);
  const [data, setData]       = useState<Summary | null>(null);
  const [error, setError]     = useState('');

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const resp = await apiClient.get(`/api/v1/menu-matrix/summary/${storeId}`, { params: { period } });
      setData(resp.data.data);
    } catch {
      setError('加载失败，请重试');
    } finally {
      setLoading(false);
    }
  }, [storeId, period]);

  const pieRevOption = data ? {
    tooltip: { trigger: 'item', formatter: '{b}: ¥{c} ({d}%)' },
    legend: { bottom: 0, type: 'scroll' },
    series: [{
      type: 'pie', radius: ['40%', '65%'],
      data: data.by_quadrant.map(d => ({
        name: QUADRANT_CONFIG[d.quadrant]?.label ?? d.quadrant,
        value: d.total_revenue,
        itemStyle: { color: QUADRANT_CONFIG[d.quadrant]?.borderColor ?? '#ccc' },
      })),
    }],
  } : {};

  const barImpactOption = data ? {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category',
      data: data.by_quadrant.map(d => QUADRANT_CONFIG[d.quadrant]?.label ?? d.quadrant) },
    yAxis: { type: 'value', name: '预期影响 (¥)' },
    series: [{
      type: 'bar',
      data: data.by_quadrant.map(d => ({
        value: d.total_impact,
        itemStyle: { color: QUADRANT_CONFIG[d.quadrant]?.borderColor ?? '#ccc' },
      })),
      label: { show: true, formatter: (p: { value: number }) => `¥${p.value.toFixed(0)}` },
    }],
    grid: { top: 30, bottom: 40 },
  } : {};

  return (
    <>
      <div className={styles.controlBar}>
        <Button type="primary" icon={<SyncOutlined />} onClick={load} loading={loading}>加载汇总</Button>
      </div>
      {error && <Alert type="error" message={error} style={{ marginBottom: 12 }} />}
      {loading && <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>}
      {data && (
        <>
          {/* 四象限卡片 */}
          <div className={styles.quadrantGrid}>
            {(['star', 'cash_cow', 'question_mark', 'dog'] as const).map(q => {
              const cfg = QUADRANT_CONFIG[q];
              const item = data.by_quadrant.find(d => d.quadrant === q);
              return (
                <div key={q} className={styles.quadrantCard}
                  style={{ background: cfg.bgColor, border: `1px solid ${cfg.borderColor}` }}>
                  <div className={styles.qLabel} style={{ color: cfg.color }}>{cfg.icon} {cfg.label}</div>
                  <div className={styles.qCount} style={{ color: cfg.color }}>
                    {item?.dish_count ?? 0} 道
                  </div>
                  <div className={styles.qRevenue}>营收 {fmtYuan(item?.total_revenue ?? 0)}</div>
                  <div className={styles.qImpact} style={{ color: cfg.color }}>
                    预期影响 {fmtYuan(item?.total_impact ?? 0)}
                  </div>
                </div>
              );
            })}
          </div>

          {/* 汇总数字 */}
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={8}>
              <Card size="small">
                <div style={{ textAlign: 'center' }}>
                  <div style={{ color: '#8c8c8c', fontSize: 13 }}>总菜品数</div>
                  <div style={{ fontSize: 24, fontWeight: 700 }}>{data.total_dishes} 道</div>
                </div>
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small">
                <div style={{ textAlign: 'center' }}>
                  <div style={{ color: '#8c8c8c', fontSize: 13 }}>总营收</div>
                  <div style={{ fontSize: 24, fontWeight: 700, color: '#1A7A52' }}>{fmtYuan(data.total_revenue)}</div>
                </div>
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small">
                <div style={{ textAlign: 'center' }}>
                  <div style={{ color: '#8c8c8c', fontSize: 13 }}>优化预期影响</div>
                  <div style={{ fontSize: 24, fontWeight: 700, color: '#0AAF9A' }}>{fmtYuan(data.total_expected_impact)}</div>
                </div>
              </Card>
            </Col>
          </Row>

          {/* 图表 */}
          <Row gutter={16}>
            <Col span={12}>
              <Card title="各象限营收占比" size="small">
                <ReactECharts option={pieRevOption} style={{ height: 260 }} />
              </Card>
            </Col>
            <Col span={12}>
              <Card title="各象限优化预期影响 (¥)" size="small">
                <ReactECharts option={barImpactOption} style={{ height: 260 }} />
              </Card>
            </Col>
          </Row>

          {/* 明细表 */}
          <div style={{ marginTop: 16 }}>
            <Table
              rowKey="quadrant" size="small" dataSource={data.by_quadrant}
              pagination={false}
              rowClassName={r => QUADRANT_CONFIG[r.quadrant]?.rowClass ?? ''}
              columns={[
                { title: '象限', dataIndex: 'quadrant', render: v => <QuadrantTag quadrant={v} /> },
                { title: '菜品数', dataIndex: 'dish_count', width: 80 },
                { title: '总营收', dataIndex: 'total_revenue', render: v => fmtYuan(v) },
                { title: '营收百分位均值', dataIndex: 'avg_rev_pct', render: v => `${v}%` },
                { title: '增长百分位均值', dataIndex: 'avg_grow_pct', render: v => `${v}%` },
                { title: '优化预期影响', dataIndex: 'total_impact',
                  render: v => <span style={{ color: '#0AAF9A', fontWeight: 600 }}>{fmtYuan(v)}</span> },
                { title: '高优先级菜品', dataIndex: 'high_priority_dishes', width: 110,
                  render: v => <span className={styles.prioHigh}>{v} 道</span> },
              ]}
            />
          </div>
        </>
      )}
    </>
  );
}

// ── Tab 3: 行动推荐榜 ─────────────────────────────────────────────────────────

interface ActionRow {
  dish_id: string;
  dish_name: string;
  category: string | null;
  revenue_yuan: number;
  revenue_delta_pct: number | null;
  revenue_percentile: number;
  growth_percentile: number;
  matrix_quadrant: string;
  action_priority: string;
  expected_impact_yuan: number;
}

function ActionsTab({ storeId, period }: { storeId: string; period: string }) {
  const [loading, setLoading] = useState(false);
  const [actionData, setActionData] = useState<Record<string, ActionRow[]>>({});
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [rPromote, rMaintain, rDevelop, rRetire] = await Promise.all([
        apiClient.get(`/api/v1/menu-matrix/actions/${storeId}`, { params: { period, action: 'promote', limit: 8 } }),
        apiClient.get(`/api/v1/menu-matrix/actions/${storeId}`, { params: { period, action: 'maintain', limit: 8 } }),
        apiClient.get(`/api/v1/menu-matrix/actions/${storeId}`, { params: { period, action: 'develop', limit: 8 } }),
        apiClient.get(`/api/v1/menu-matrix/actions/${storeId}`, { params: { period, action: 'retire', limit: 8 } }),
      ]);
      setActionData({
        promote:  rPromote.data.data  ?? [],
        maintain: rMaintain.data.data ?? [],
        develop:  rDevelop.data.data  ?? [],
        retire:   rRetire.data.data   ?? [],
      });
    } catch {
      setError('加载失败，请重试');
    } finally {
      setLoading(false);
    }
  }, [storeId, period]);

  const actionCols: ColumnsType<ActionRow> = [
    { title: '菜品', dataIndex: 'dish_name', ellipsis: true, width: 110 },
    { title: '优先级', dataIndex: 'action_priority',
      render: v => <span className={PRIORITY_CLASS[v] ?? ''}>{PRIORITY_LABELS[v] ?? v}</span> },
    { title: '营收', dataIndex: 'revenue_yuan', render: v => fmtYuan(v) },
    { title: '增长率', dataIndex: 'revenue_delta_pct',
      render: v => v == null ? '-' : <span style={{ color: v >= 0 ? '#1A7A52' : '#C53030' }}>{v >= 0 ? '+' : ''}{v}%</span> },
    { title: '预期影响', dataIndex: 'expected_impact_yuan',
      render: v => <span style={{ color: '#0AAF9A', fontWeight: 600 }}>{fmtYuan(v)}</span> },
  ];

  const totalImpact = Object.values(actionData).flat()
    .reduce((s, r) => s + r.expected_impact_yuan, 0);

  return (
    <>
      <div className={styles.controlBar}>
        <Button type="primary" icon={<StarOutlined />} onClick={load} loading={loading}>加载行动榜</Button>
        {Object.keys(actionData).length > 0 && (
          <span style={{ color: '#0AAF9A', fontWeight: 600 }}>
            全部行动预期影响合计：{fmtYuan(totalImpact)}
          </span>
        )}
      </div>
      {error && <Alert type="error" message={error} style={{ marginBottom: 12 }} />}
      {loading && <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>}
      {Object.keys(actionData).length > 0 && (
        <div className={styles.actionsRow}>
          {(['promote', 'develop', 'maintain', 'retire'] as const).map(act => {
            const cfg = Object.values(QUADRANT_CONFIG).find(c => c.action === act)!;
            const rows = actionData[act] ?? [];
            return (
              <Card
                key={act}
                title={
                  <span style={{ color: cfg.color }}>
                    {cfg.icon} {cfg.actionLabel} ({rows.length} 道)
                  </span>
                }
                size="small"
                style={{ borderColor: cfg.borderColor }}
              >
                <Table
                  rowKey="dish_id" size="small" dataSource={rows}
                  columns={actionCols} pagination={false}
                  rowClassName={() => cfg.rowClass}
                />
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}

// ── Tab 4: 菜品象限历史 ───────────────────────────────────────────────────────

interface HistoryRow {
  period: string;
  matrix_quadrant: string;
  optimization_action: string;
  action_priority: string;
  revenue_yuan: number;
  revenue_delta_pct: number | null;
  revenue_percentile: number;
  growth_percentile: number;
  expected_impact_yuan: number;
}

function DishHistory({ storeId }: { storeId: string }) {
  const [dishId, setDishId]   = useState('');
  const [loading, setLoading] = useState(false);
  const [rows, setRows]       = useState<HistoryRow[]>([]);
  const [error, setError]     = useState('');

  const load = useCallback(async () => {
    if (!dishId.trim()) return;
    setLoading(true); setError('');
    try {
      const resp = await apiClient.get(
        `/api/v1/menu-matrix/dish/${storeId}/${dishId.trim()}`,
        { params: { periods: 12 } }
      );
      setRows(resp.data.data ?? []);
    } catch {
      setError('加载失败，请重试');
    } finally {
      setLoading(false);
    }
  }, [storeId, dishId]);

  // 象限变迁时序图
  const quadrantOrder: Record<string, number> = {
    dog: 1, question_mark: 2, cash_cow: 3, star: 4,
  };

  const lineOption = rows.length ? {
    tooltip: {
      trigger: 'axis',
      formatter: (params: { name: string; data: number }[]) => {
        const r = rows.find(x => x.period === params[0].name);
        if (!r) return params[0].name;
        const qcfg = QUADRANT_CONFIG[r.matrix_quadrant];
        return `${r.period}<br/>${qcfg?.label ?? r.matrix_quadrant}<br/>营收: ¥${Number(r.revenue_yuan).toFixed(2)}`;
      },
    },
    xAxis: { type: 'category', data: [...rows].reverse().map(r => r.period) },
    yAxis: {
      type: 'value', min: 0, max: 4,
      axisLabel: {
        formatter: (v: number) =>
          ['', '瘦狗菜', '问题菜', '现金牛菜', '明星菜'][v] ?? '',
      },
    },
    series: [{
      type: 'line', smooth: true,
      data: [...rows].reverse().map(r => quadrantOrder[r.matrix_quadrant] ?? 0),
      markPoint: { data: [{ type: 'max', name: '最高' }, { type: 'min', name: '最低' }] },
      lineStyle: { color: '#0AAF9A', width: 2 },
      areaStyle: { color: 'rgba(22,119,255,0.08)' },
      symbol: 'circle', symbolSize: 8,
      itemStyle: { color: (p: { dataIndex: number }) => {
        const q = [...rows].reverse()[p.dataIndex]?.matrix_quadrant;
        return QUADRANT_CONFIG[q]?.borderColor ?? '#0AAF9A';
      } },
    }],
    grid: { top: 20, bottom: 40 },
  } : {};

  return (
    <>
      <div className={styles.historySearch}>
        <Input
          placeholder="输入菜品 ID (如 D001)"
          style={{ width: 220 }}
          value={dishId}
          onChange={e => setDishId(e.target.value)}
          onPressEnter={load}
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={load} loading={loading}>查询历史</Button>
      </div>
      {error && <Alert type="error" message={error} style={{ marginBottom: 12 }} />}
      {loading && <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>}
      {!rows.length && !loading && (
        <div className={styles.historyHint}>输入菜品 ID 后点击查询，查看该菜品近 12 期的象限变迁轨迹。</div>
      )}
      {rows.length > 0 && (
        <>
          <Card title="象限变迁趋势（越高表示象限越优）" size="small" style={{ marginBottom: 16 }}>
            <ReactECharts option={lineOption} style={{ height: 240 }} />
          </Card>
          <Table
            rowKey="period" size="small" dataSource={rows} pagination={false}
            rowClassName={r => QUADRANT_CONFIG[r.matrix_quadrant]?.rowClass ?? ''}
            columns={[
              { title: '期间', dataIndex: 'period', width: 90 },
              { title: '象限', dataIndex: 'matrix_quadrant', render: v => <QuadrantTag quadrant={v} /> },
              { title: '优先级', dataIndex: 'action_priority',
                render: v => <span className={PRIORITY_CLASS[v] ?? ''}>{PRIORITY_LABELS[v] ?? v}</span> },
              { title: '营收', dataIndex: 'revenue_yuan', render: v => fmtYuan(v) },
              { title: '增长率', dataIndex: 'revenue_delta_pct',
                render: v => v == null ? '-' : <span style={{ color: v >= 0 ? '#1A7A52' : '#C53030' }}>{v >= 0 ? '+' : ''}{v}%</span> },
              { title: '营收百分位', dataIndex: 'revenue_percentile', render: v => `${v}%` },
              { title: '增长百分位', dataIndex: 'growth_percentile', render: v => `${v}%` },
              { title: '预期影响', dataIndex: 'expected_impact_yuan',
                render: v => <span style={{ color: '#0AAF9A' }}>{fmtYuan(v)}</span> },
            ]}
          />
        </>
      )}
    </>
  );
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

const MenuMatrixPage: React.FC = () => {
  const [storeId]   = useState(DEFAULT_STORE);
  const [period, setPeriod]     = useState(DEFAULT_PERIOD);
  const [computing, setComputing] = useState(false);
  const [computeMsg, setComputeMsg] = useState('');

  const handleCompute = async () => {
    setComputing(true); setComputeMsg('');
    try {
      const resp = await apiClient.post(
        `/api/v1/menu-matrix/compute/${storeId}?period=${period}`
      );
      const d = resp.data.data;
      const qStr = Object.entries(d.quadrant_counts as Record<string, number>)
        .map(([q, n]) => `${QUADRANT_CONFIG[q]?.label ?? q}:${n}`)
        .join(' / ');
      setComputeMsg(
        `分析完成：共 ${d.dish_count} 道菜，新菜 ${d.new_dishes} 道 | ${qStr} | 预期影响合计 ¥${d.total_expected_impact_yuan?.toFixed(2)}`
      );
    } catch {
      setComputeMsg('计算失败，请重试');
    } finally {
      setComputing(false);
    }
  };

  const periods: string[] = [];
  for (let i = 0; i < 12; i++) {
    periods.push(dayjs().subtract(i, 'month').format('YYYY-MM'));
  }

  return (
    <div>
      <div className={styles.pageHeader}>
        <Row justify="space-between" align="middle">
          <Col>
            <Title level={4} style={{ margin: 0 }}>菜品组合矩阵分析 — BCG 四象限</Title>
            <Text type="secondary">
              按营收百分位 × 增长百分位将菜品分类为明星菜/现金牛菜/问题菜/瘦狗菜，生成行动建议
            </Text>
          </Col>
          <Col>
            <Space>
              <Select value={period} onChange={setPeriod} style={{ width: 120 }}>
                {periods.map(p => <Option key={p} value={p}>{p}</Option>)}
              </Select>
              <Tooltip title="将当前期菜品全部计算并写入矩阵（幂等）">
                <Button type="primary" icon={<SyncOutlined />} loading={computing} onClick={handleCompute}>
                  触发矩阵计算
                </Button>
              </Tooltip>
            </Space>
          </Col>
        </Row>
        {computeMsg && (
          <Alert
            type={computeMsg.includes('失败') ? 'error' : 'success'}
            message={computeMsg}
            style={{ marginTop: 8 }}
            closable onClose={() => setComputeMsg('')}
          />
        )}
      </div>

      <Tabs
        defaultActiveKey="scatter"
        items={[
          { key: 'scatter', label: 'BCG矩阵图',   children: <MatrixScatter storeId={storeId} period={period} /> },
          { key: 'summary', label: '汇总分析',    children: <SummaryTab   storeId={storeId} period={period} /> },
          { key: 'actions', label: '行动推荐榜',  children: <ActionsTab   storeId={storeId} period={period} /> },
          { key: 'history', label: '菜品象限历史', children: <DishHistory  storeId={storeId} /> },
        ]}
      />
    </div>
  );
};

export default MenuMatrixPage;
