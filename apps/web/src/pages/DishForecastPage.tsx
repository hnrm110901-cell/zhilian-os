/**
 * 菜品销售预测引擎 — Phase 6 Month 7
 * 4 Tabs: 预测看板 / 汇总分析 / 精度追踪 / 菜品预测详情
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Typography, Tabs, Table, Tag, Select, InputNumber, Button, Space,
  Card, Row, Col, Statistic, Input, Empty, Spin, Alert, Tooltip,
} from 'antd';
import { SearchOutlined, ReloadOutlined, LineChartOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { apiClient, handleApiError } from '../services/api';
import styles from './DishForecastPage.module.css';

const { Title, Text } = Typography;
const { Option } = Select;

// ── 常量 ──────────────────────────────────────────────────────────────────────

const PHASE_CONFIG: Record<string, { label: string; color: string; antColor: string }> = {
  launch:  { label: '新品', color: '#1A7A52', antColor: 'green' },
  growth:  { label: '成长', color: '#FF6B2C', antColor: 'blue' },
  peak:    { label: '成熟', color: '#faad14', antColor: 'gold' },
  decline: { label: '衰退', color: '#C8923A', antColor: 'orange' },
  exit:    { label: '退出', color: '#C53030', antColor: 'red' },
};

const DEFAULT_STORE = localStorage.getItem('store_id') || '';
const DEFAULT_PERIOD = dayjs().subtract(1, 'month').format('YYYY-MM');

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface ForecastRec {
  id: number;
  dish_id: string;
  dish_name: string;
  category: string;
  lifecycle_phase: string;
  periods_used: number;
  hist_avg_orders: number;
  hist_avg_revenue: number;
  trend_orders_pct: number;
  trend_revenue_pct: number;
  lifecycle_adj_pct: number;
  predicted_order_count: number;
  predicted_order_low: number;
  predicted_order_high: number;
  predicted_revenue_yuan: number;
  predicted_revenue_low: number;
  predicted_revenue_high: number;
  predicted_fcr: number;
  predicted_gpm: number;
  base_period: string;
}

interface PhaseRow {
  lifecycle_phase: string;
  dish_count: number;
  total_orders: number;
  total_revenue: number;
  avg_trend: number;
  avg_lc_adj: number;
  avg_periods_used: number;
}

interface SummaryData {
  store_id: string;
  forecast_period: string;
  total_dishes: number;
  total_revenue: number;
  by_phase: PhaseRow[];
}

interface AccuracyRec {
  dish_id: string;
  dish_name: string;
  category: string;
  lifecycle_phase: string;
  predicted_order_count: number;
  predicted_revenue_yuan: number;
  actual_orders: number;
  actual_revenue: number;
  order_error_pct: number | null;
  revenue_error_pct: number | null;
}

interface HistoryRec {
  forecast_period: string;
  base_period: string;
  lifecycle_phase: string;
  predicted_order_count: number;
  predicted_order_low: number;
  predicted_order_high: number;
  predicted_revenue_yuan: number;
  predicted_revenue_low: number;
  predicted_revenue_high: number;
  trend_revenue_pct: number;
  lifecycle_adj_pct: number;
  periods_used: number;
  actual_orders: number | null;
  actual_revenue: number | null;
}

// ── 辅助 ──────────────────────────────────────────────────────────────────────

function trendTag(pct: number) {
  if (pct > 0.5) return <Tag color="green">+{pct.toFixed(1)}%</Tag>;
  if (pct < -0.5) return <Tag color="red">{pct.toFixed(1)}%</Tag>;
  return <Tag color="default">持平</Tag>;
}

function phaseTag(phase: string) {
  const cfg = PHASE_CONFIG[phase] ?? { label: phase, antColor: 'default' };
  return <Tag color={cfg.antColor}>{cfg.label}</Tag>;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tab 1 — 预测看板
// ═══════════════════════════════════════════════════════════════════════════════

const ForecastBoard: React.FC<{ storeId: string }> = ({ storeId }) => {
  const [forecastPeriod, setForecastPeriod] = useState(dayjs().format('YYYY-MM'));
  const [phase, setPhase] = useState<string | undefined>(undefined);
  const [limit, setLimit] = useState(100);
  const [data, setData] = useState<ForecastRec[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = {
        forecast_period: forecastPeriod,
        limit,
      };
      if (phase) params.lifecycle_phase = phase;
      const resp = await apiClient.get(`/api/v1/dish-forecast/${storeId}`, { params });
      setData(resp.data.forecasts ?? []);
      setTotal(resp.data.count ?? 0);
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  }, [storeId, forecastPeriod, phase, limit]);

  useEffect(() => { load(); }, [load]);

  const cols = [
    { title: '菜品', dataIndex: 'dish_name', width: 130,
      render: (n: string, r: ForecastRec) => <span><Text strong>{n}</Text><br/><Text type="secondary" style={{fontSize:11}}>{r.category}</Text></span> },
    { title: '阶段', dataIndex: 'lifecycle_phase', width: 70,
      render: (v: string) => phaseTag(v) },
    { title: '参考期数', dataIndex: 'periods_used', width: 80, align: 'center' as const },
    { title: '预测订单', dataIndex: 'predicted_order_count', width: 90, align: 'right' as const,
      render: (v: number, r: ForecastRec) =>
        <Tooltip title={`区间: ${r.predicted_order_low} – ${r.predicted_order_high}`}>
          <span className={styles.point}>{v.toFixed(1)}</span>
        </Tooltip> },
    { title: '预测营收(¥)', dataIndex: 'predicted_revenue_yuan', width: 110, align: 'right' as const,
      render: (v: number, r: ForecastRec) =>
        <Tooltip title={`区间: ¥${r.predicted_revenue_low} – ¥${r.predicted_revenue_high}`}>
          <span className={styles.revenue}>¥{v.toFixed(2)}</span>
        </Tooltip> },
    { title: '营收趋势', dataIndex: 'trend_revenue_pct', width: 90,
      render: (v: number) => trendTag(v) },
    { title: '阶段调整', dataIndex: 'lifecycle_adj_pct', width: 90, align: 'right' as const,
      render: (v: number) => v === 0 ? '—' : <span style={{color: v > 0 ? '#1A7A52' : '#C53030'}}>{v > 0 ? '+' : ''}{v.toFixed(1)}%</span> },
    { title: '预测成本率', dataIndex: 'predicted_fcr', width: 95, align: 'right' as const,
      render: (v: number) => `${v.toFixed(1)}%` },
    { title: '预测毛利率', dataIndex: 'predicted_gpm', width: 95, align: 'right' as const,
      render: (v: number) => `${v.toFixed(1)}%` },
  ];

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <span>预测期：</span>
        <Input value={forecastPeriod} onChange={e => setForecastPeriod(e.target.value)}
               placeholder="YYYY-MM" style={{ width: 110 }} />
        <span>生命阶段：</span>
        <Select allowClear placeholder="全部" style={{ width: 100 }} value={phase} onChange={setPhase}>
          {Object.entries(PHASE_CONFIG).map(([k, v]) =>
            <Option key={k} value={k}>{v.label}</Option>
          )}
        </Select>
        <span>最多：</span>
        <InputNumber min={1} max={500} value={limit} onChange={v => setLimit(v ?? 100)} style={{ width: 80 }} />
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
      </Space>
      <Text type="secondary" style={{ marginBottom: 8, display: 'block' }}>共 {total} 条预测（将鼠标悬停在订单/营收上可查看置信区间）</Text>
      <Table
        dataSource={data}
        columns={cols}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={{ pageSize: 50, showSizeChanger: true }}
        rowClassName={r => {
          const p = r.lifecycle_phase;
          if (p === 'exit') return styles.rowExit;
          if (p === 'decline') return styles.rowDecline;
          if (p === 'launch') return styles.rowLaunch;
          return '';
        }}
        scroll={{ x: 900 }}
      />
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// Tab 2 — 汇总分析
// ═══════════════════════════════════════════════════════════════════════════════

const SummaryAnalysis: React.FC<{ storeId: string }> = ({ storeId }) => {
  const [forecastPeriod, setForecastPeriod] = useState(dayjs().format('YYYY-MM'));
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/dish-forecast/summary/${storeId}`, {
        params: { forecast_period: forecastPeriod },
      });
      setSummary(resp.data);
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  }, [storeId, forecastPeriod]);

  useEffect(() => { load(); }, [load]);

  const barOption = summary ? {
    tooltip: { trigger: 'axis' },
    legend: { data: ['菜品数', '预测营收(百元)'] },
    xAxis: { type: 'category', data: summary.by_phase.map(r => PHASE_CONFIG[r.lifecycle_phase]?.label ?? r.lifecycle_phase) },
    yAxis: [
      { type: 'value', name: '菜品数' },
      { type: 'value', name: '营收(百元)' },
    ],
    series: [
      { name: '菜品数', type: 'bar', data: summary.by_phase.map(r => r.dish_count),
        itemStyle: { color: '#FF6B2C' } },
      { name: '预测营收(百元)', type: 'bar', yAxisIndex: 1,
        data: summary.by_phase.map(r => (r.total_revenue / 100).toFixed(0)),
        itemStyle: { color: '#1A7A52' } },
    ],
  } : {};

  const pieOption = summary ? {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie', radius: ['40%', '65%'],
      data: summary.by_phase.map(r => ({
        name: PHASE_CONFIG[r.lifecycle_phase]?.label ?? r.lifecycle_phase,
        value: r.dish_count,
        itemStyle: { color: PHASE_CONFIG[r.lifecycle_phase]?.color },
      })),
    }],
  } : {};

  const trendBarOption = summary ? {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: summary.by_phase.map(r => PHASE_CONFIG[r.lifecycle_phase]?.label ?? r.lifecycle_phase) },
    yAxis: { type: 'value', name: '平均趋势(%/期)' },
    series: [{
      type: 'bar',
      data: summary.by_phase.map(r => ({
        value: r.avg_trend.toFixed(2),
        itemStyle: { color: r.avg_trend >= 0 ? '#1A7A52' : '#C53030' },
      })),
    }],
  } : {};

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <span>预测期：</span>
        <Input value={forecastPeriod} onChange={e => setForecastPeriod(e.target.value)}
               placeholder="YYYY-MM" style={{ width: 110 }} />
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
      </Space>

      {summary && (
        <>
          <Row gutter={16} style={{ marginBottom: 24 }}>
            <Col span={6}><Card><Statistic title="预测菜品数" value={summary.total_dishes} suffix="道" /></Card></Col>
            <Col span={6}><Card><Statistic title="预测总营收" value={summary.total_revenue.toFixed(2)} prefix="¥" /></Card></Col>
            <Col span={6}><Card><Statistic title="生命阶段分布" value={summary.by_phase.length} suffix="个阶段" /></Card></Col>
            <Col span={6}><Card><Statistic title="预测期" value={summary.forecast_period} /></Card></Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Card title="阶段菜品数 vs 预测营收" size="small">
                <ReactECharts option={barOption} style={{ height: 260 }} />
              </Card>
            </Col>
            <Col span={12}>
              <Card title="菜品阶段分布" size="small">
                <ReactECharts option={pieOption} style={{ height: 260 }} />
              </Card>
            </Col>
          </Row>

          <Row gutter={16} style={{ marginTop: 16 }}>
            <Col span={12}>
              <Card title="各阶段平均营收趋势" size="small">
                <ReactECharts option={trendBarOption} style={{ height: 220 }} />
              </Card>
            </Col>
            <Col span={12}>
              <Card title="阶段明细" size="small">
                <Table
                  dataSource={summary.by_phase}
                  rowKey="lifecycle_phase"
                  size="small"
                  pagination={false}
                  columns={[
                    { title: '阶段', dataIndex: 'lifecycle_phase', render: (v: string) => phaseTag(v) },
                    { title: '菜品数', dataIndex: 'dish_count', align: 'right' as const },
                    { title: '预测营收', dataIndex: 'total_revenue', align: 'right' as const, render: (v: number) => `¥${v.toFixed(0)}` },
                    { title: '均趋势', dataIndex: 'avg_trend', align: 'right' as const, render: (v: number) => trendTag(v) },
                    { title: '均期数', dataIndex: 'avg_periods_used', align: 'right' as const, render: (v: number) => v.toFixed(1) },
                  ]}
                />
              </Card>
            </Col>
          </Row>
        </>
      )}
      {loading && <div style={{ textAlign: 'center', padding: 48 }}><Spin size="large" /></div>}
      {!loading && !summary && <Empty description="暂无数据" style={{ padding: 48 }} />}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// Tab 3 — 精度追踪
// ═══════════════════════════════════════════════════════════════════════════════

const AccuracyTracking: React.FC<{ storeId: string }> = ({ storeId }) => {
  const [forecastPeriod, setForecastPeriod] = useState(DEFAULT_PERIOD);
  const [limit, setLimit] = useState(50);
  const [data, setData] = useState<AccuracyRec[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/dish-forecast/accuracy/${storeId}`, {
        params: { forecast_period: forecastPeriod, limit },
      });
      setData(resp.data.accuracy ?? []);
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  }, [storeId, forecastPeriod, limit]);

  useEffect(() => { load(); }, [load]);

  const scatterOption = data.length ? {
    tooltip: { trigger: 'item', formatter: (p: { data: [number, number, string] }) => `${p.data[2]}<br/>预测: ¥${p.data[0]}<br/>实际: ¥${p.data[1]}` },
    xAxis: { type: 'value', name: '预测营收(¥)' },
    yAxis: { type: 'value', name: '实际营收(¥)' },
    series: [
      {
        type: 'scatter',
        data: data.map(r => [r.predicted_revenue_yuan, r.actual_revenue, r.dish_name]),
        symbolSize: 8,
        itemStyle: {
          color: (p: { data: [number, number, string] }) => {
            const err = Math.abs((p.data[1] - p.data[0]) / (p.data[0] || 1) * 100);
            return err > 20 ? '#C53030' : err > 10 ? '#faad14' : '#1A7A52';
          },
        },
      },
      {
        type: 'line', silent: true, symbol: 'none',
        lineStyle: { type: 'dashed', color: '#aaa' },
        data: (() => {
          const vals = data.flatMap(r => [r.predicted_revenue_yuan, r.actual_revenue]);
          const mx = Math.max(...vals);
          return [[0, 0], [mx, mx]];
        })(),
      },
    ],
  } : {};

  const cols = [
    { title: '菜品', dataIndex: 'dish_name', width: 120,
      render: (n: string, r: AccuracyRec) => <span><Text strong>{n}</Text><br/><Text type="secondary" style={{fontSize:11}}>{r.category}</Text></span> },
    { title: '阶段', dataIndex: 'lifecycle_phase', width: 70, render: (v: string) => phaseTag(v) },
    { title: '预测订单', dataIndex: 'predicted_order_count', width: 90, align: 'right' as const, render: (v: number) => v.toFixed(1) },
    { title: '实际订单', dataIndex: 'actual_orders', width: 90, align: 'right' as const },
    { title: '订单误差', dataIndex: 'order_error_pct', width: 90, align: 'right' as const,
      render: (v: number | null) => v == null ? '—' : trendTag(v) },
    { title: '预测营收', dataIndex: 'predicted_revenue_yuan', width: 100, align: 'right' as const, render: (v: number) => `¥${v.toFixed(2)}` },
    { title: '实际营收', dataIndex: 'actual_revenue', width: 100, align: 'right' as const, render: (v: number) => `¥${v.toFixed(2)}` },
    { title: '营收误差', dataIndex: 'revenue_error_pct', width: 90, align: 'right' as const,
      render: (v: number | null) => v == null ? '—' : trendTag(v) },
  ];

  return (
    <div>
      <Alert
        type="info"
        message="精度追踪需要预测期的实际数据已入库才能显示结果。若下方无数据，请先完成当期盈利数据录入。"
        style={{ marginBottom: 16 }}
        showIcon
      />
      <Space wrap style={{ marginBottom: 16 }}>
        <span>回测期：</span>
        <Input value={forecastPeriod} onChange={e => setForecastPeriod(e.target.value)}
               placeholder="YYYY-MM" style={{ width: 110 }} />
        <span>最多：</span>
        <InputNumber min={1} max={200} value={limit} onChange={v => setLimit(v ?? 50)} style={{ width: 80 }} />
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>查询</Button>
      </Space>

      {data.length > 0 && (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={12}>
            <Card title="预测 vs 实际营收散点（对角线为完美预测）" size="small">
              <ReactECharts option={scatterOption} style={{ height: 280 }} />
            </Card>
          </Col>
          <Col span={12}>
            <Card title="误差概要" size="small" style={{ height: '100%' }}>
              <Row gutter={8}>
                {[
                  { label: '误差 <10%', count: data.filter(r => Math.abs(r.revenue_error_pct ?? 999) < 10).length, color: '#1A7A52' },
                  { label: '误差 10-20%', count: data.filter(r => { const e = Math.abs(r.revenue_error_pct ?? 999); return e >= 10 && e < 20; }).length, color: '#faad14' },
                  { label: '误差 >20%', count: data.filter(r => Math.abs(r.revenue_error_pct ?? 999) >= 20).length, color: '#C53030' },
                ].map(item => (
                  <Col span={8} key={item.label}>
                    <Card size="small" style={{ textAlign: 'center', borderColor: item.color }}>
                      <div style={{ fontSize: 24, fontWeight: 700, color: item.color }}>{item.count}</div>
                      <div style={{ fontSize: 12 }}>{item.label}</div>
                    </Card>
                  </Col>
                ))}
              </Row>
            </Card>
          </Col>
        </Row>
      )}

      <Table
        dataSource={data}
        columns={cols}
        rowKey="dish_id"
        loading={loading}
        size="small"
        pagination={{ pageSize: 20 }}
        locale={{ emptyText: '暂无回测数据——该期实际数据尚未入库' }}
        rowClassName={r => {
          const err = Math.abs(r.revenue_error_pct ?? 0);
          if (err > 20) return styles.rowHighError;
          return '';
        }}
        scroll={{ x: 750 }}
      />
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// Tab 4 — 菜品预测详情
// ═══════════════════════════════════════════════════════════════════════════════

const DishForecastDetail: React.FC<{ storeId: string }> = ({ storeId }) => {
  const [dishId, setDishId] = useState('');
  const [inputDishId, setInputDishId] = useState('');
  const [periods, setPeriods] = useState(6);
  const [history, setHistory] = useState<HistoryRec[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (id: string) => {
    if (!id) return;
    setLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/dish-forecast/dish/${storeId}/${id}`, {
        params: { periods },
      });
      setHistory(resp.data.history ?? []);
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  }, [storeId, periods]);

  const handleSearch = () => {
    const id = inputDishId.trim();
    setDishId(id);
    load(id);
  };

  const sortedHistory = [...history].sort((a, b) => a.forecast_period.localeCompare(b.forecast_period));

  const ciOption = sortedHistory.length ? {
    tooltip: { trigger: 'axis' },
    legend: { data: ['预测营收', '实际营收', '置信上限', '置信下限'] },
    xAxis: { type: 'category', data: sortedHistory.map(r => r.forecast_period) },
    yAxis: { type: 'value', name: '营收(¥)' },
    series: [
      {
        name: '预测营收', type: 'line', symbol: 'circle',
        data: sortedHistory.map(r => r.predicted_revenue_yuan),
        lineStyle: { color: '#FF6B2C' }, itemStyle: { color: '#FF6B2C' },
      },
      {
        name: '实际营收', type: 'line', symbol: 'diamond',
        data: sortedHistory.map(r => r.actual_revenue),
        lineStyle: { color: '#1A7A52', type: 'dashed' }, itemStyle: { color: '#1A7A52' },
      },
      {
        name: '置信上限', type: 'line', symbol: 'none',
        data: sortedHistory.map(r => r.predicted_revenue_high),
        lineStyle: { color: '#adc6ff', type: 'dotted' }, itemStyle: { color: '#adc6ff' },
      },
      {
        name: '置信下限', type: 'line', symbol: 'none',
        data: sortedHistory.map(r => r.predicted_revenue_low),
        lineStyle: { color: '#adc6ff', type: 'dotted' }, itemStyle: { color: '#adc6ff' },
        areaStyle: { color: 'rgba(173,198,255,0.15)', origin: 'auto' },
      },
    ],
  } : {};

  const cols = [
    { title: '预测期', dataIndex: 'forecast_period', width: 90 },
    { title: '基础期', dataIndex: 'base_period', width: 90 },
    { title: '阶段', dataIndex: 'lifecycle_phase', width: 70, render: (v: string) => phaseTag(v) },
    { title: '期数', dataIndex: 'periods_used', width: 60, align: 'center' as const },
    { title: '预测订单', dataIndex: 'predicted_order_count', width: 90, align: 'right' as const,
      render: (v: number, r: HistoryRec) => <Tooltip title={`[${r.predicted_order_low}, ${r.predicted_order_high}]`}>{v.toFixed(1)}</Tooltip> },
    { title: '预测营收', dataIndex: 'predicted_revenue_yuan', width: 100, align: 'right' as const, render: (v: number) => `¥${v.toFixed(2)}` },
    { title: '实际订单', dataIndex: 'actual_orders', width: 85, align: 'right' as const,
      render: (v: number | null) => v ?? <Text type="secondary">—</Text> },
    { title: '实际营收', dataIndex: 'actual_revenue', width: 95, align: 'right' as const,
      render: (v: number | null) => v != null ? `¥${v.toFixed(2)}` : <Text type="secondary">—</Text> },
    { title: '营收趋势', dataIndex: 'trend_revenue_pct', width: 90, render: (v: number) => trendTag(v) },
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
          prefix={<LineChartOutlined />}
        />
        <InputNumber min={1} max={24} value={periods} onChange={v => setPeriods(v ?? 6)}
                     addonBefore="期数" style={{ width: 120 }} />
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>查询</Button>
      </Space>

      {dishId && loading && <div style={{ textAlign: 'center', padding: 48 }}><Spin size="large" /></div>}

      {dishId && !loading && history.length === 0 && (
        <Empty description={`菜品 ${dishId} 暂无预测历史`} style={{ padding: 48 }} />
      )}

      {history.length > 0 && (
        <>
          <Card title={`菜品 ${dishId} — 预测营收置信区间走势`} size="small" style={{ marginBottom: 16 }}>
            <ReactECharts option={ciOption} style={{ height: 300 }} />
          </Card>
          <Table
            dataSource={history}
            columns={cols}
            rowKey="forecast_period"
            loading={loading}
            size="small"
            pagination={false}
            scroll={{ x: 720 }}
          />
        </>
      )}

      {!dishId && (
        <Empty description="请输入菜品 ID 查看历史预测走势" style={{ padding: 64 }} />
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// 主页面
// ═══════════════════════════════════════════════════════════════════════════════

const DishForecastPage: React.FC = () => {
  const [storeId, setStoreId] = useState(DEFAULT_STORE);
  const [basePeriod, setBasePeriod] = useState(DEFAULT_PERIOD);
  const [generating, setGenerating] = useState(false);
  const [genResult, setGenResult] = useState<{ dish_count: number; forecast_period: string; total_predicted_revenue: number } | null>(null);

  const handleGenerate = async () => {
    setGenerating(true);
    setGenResult(null);
    try {
      const resp = await apiClient.post(`/api/v1/dish-forecast/generate/${storeId}`, null, {
        params: { base_period: basePeriod },
      });
      setGenResult(resp.data);
    } catch (e) {
      handleApiError(e);
    } finally {
      setGenerating(false);
    }
  };

  const items = [
    { key: 'board',    label: '预测看板',   children: <ForecastBoard storeId={storeId} /> },
    { key: 'summary',  label: '汇总分析',   children: <SummaryAnalysis storeId={storeId} /> },
    { key: 'accuracy', label: '精度追踪',   children: <AccuracyTracking storeId={storeId} /> },
    { key: 'detail',   label: '菜品预测详情', children: <DishForecastDetail storeId={storeId} /> },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Title level={4} style={{ margin: 0 }}>菜品销售预测引擎</Title>
        <Space wrap>
          <span>门店：</span>
          <Input value={storeId} onChange={e => setStoreId(e.target.value)}
                 placeholder="门店ID" style={{ width: 90 }} />
          <span>基础期：</span>
          <Input value={basePeriod} onChange={e => setBasePeriod(e.target.value)}
                 placeholder="YYYY-MM" style={{ width: 110 }} />
          <Button type="primary" onClick={handleGenerate} loading={generating}>
            生成预测
          </Button>
        </Space>
      </div>

      {genResult && (
        <Alert
          type="success"
          showIcon
          closable
          style={{ marginBottom: 12 }}
          message={
            `预测完成：${genResult.forecast_period} 期共 ${genResult.dish_count} 道菜，` +
            `预测总营收 ¥${genResult.total_predicted_revenue.toFixed(2)}`
          }
        />
      )}

      <Tabs items={items} defaultActiveKey="board" />
    </div>
  );
};

export default DishForecastPage;
