/**
 * 菜品成本压缩机会页面 — Phase 6 Month 11
 * 4 Tabs: 压缩机会榜 / 汇总分析 / Top机会 / 菜品FCR历史
 */

import React, { useState, useCallback } from 'react';
import {
  Tabs, Table, Tag, Select, Button, Input, Spin, Alert, Tooltip,
  Card, Space, Typography, Row, Col, Progress,
} from 'antd';
import { SearchOutlined, SyncOutlined, DollarOutlined, WarningOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';

import { apiClient } from '../services/api';
import styles from './CostCompressionPage.module.css';

const { Title, Text } = Typography;
const { Option } = Select;

// ── 常量 ─────────────────────────────────────────────────────────────────────

const DEFAULT_STORE = localStorage.getItem('store_id') || '';
const DEFAULT_PERIOD = dayjs().subtract(1, 'month').format('YYYY-MM');

const ACTION_CONFIG: Record<string, { label: string; color: string; rowClass: string; desc: string }> = {
  renegotiate:    { label: '重新谈判', color: '#C53030', rowClass: styles.rowRenegotiate,   desc: 'FCR超标>5pp且持续恶化' },
  reformulate:    { label: '调整配方', color: '#C8923A', rowClass: styles.rowReformulate,   desc: 'FCR超标3-5pp' },
  adjust_portion: { label: '调整份量', color: '#FF6B2C', rowClass: styles.rowAdjustPortion, desc: 'FCR超标1-3pp' },
  monitor:        { label: '持续监控', color: '#8c8c8c', rowClass: styles.rowMonitor,       desc: '已达目标' },
};

const TREND_CONFIG: Record<string, { label: string; cls: string }> = {
  improving: { label: '↓ 改善中', cls: styles.trendImproving },
  stable:    { label: '→ 稳定',   cls: styles.trendStable },
  worsening: { label: '↑ 恶化',   cls: styles.trendWorsening },
};

const PRIORITY_CONFIG: Record<string, { label: string; cls: string }> = {
  high:   { label: '紧急', cls: styles.prioHigh },
  medium: { label: '中等', cls: styles.prioMedium },
  low:    { label: '低',   cls: styles.prioLow },
};

// ── 工具函数 ──────────────────────────────────────────────────────────────────

function fmtYuan(v: number | null | undefined) {
  if (v == null) return '-';
  return `¥${Number(v).toFixed(2)}`;
}

function FcrGapBar({ gap, maxGap = 10 }: { gap: number; maxGap?: number }) {
  if (gap <= 0) return <span className={styles.trendImproving}>已达目标</span>;
  const pct = Math.min(100, (gap / maxGap) * 100);
  const color = gap > 5 ? '#C53030' : gap > 3 ? '#C8923A' : '#FF6B2C';
  return (
    <Tooltip title={`FCR超标 ${gap}pp`}>
      <Progress percent={pct} size="small" strokeColor={color}
        format={() => `+${gap}pp`} style={{ width: 120 }} />
    </Tooltip>
  );
}

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface CompressionRow {
  id: number;
  dish_id: string;
  dish_name: string;
  category: string | null;
  revenue_yuan: number;
  order_count: number;
  current_fcr: number;
  current_gpm: number | null;
  target_fcr: number;
  store_avg_fcr: number;
  fcr_gap: number;
  compression_opportunity_yuan: number;
  expected_saving_yuan: number;
  prev_fcr: number | null;
  fcr_trend: string;
  compression_action: string;
  action_priority: string;
}

// ── Tab 1: 压缩机会榜 ─────────────────────────────────────────────────────────

function CompressionBoard({ storeId, period }: { storeId: string; period: string }) {
  const [action, setAction]     = useState<string | undefined>(undefined);
  const [priority, setPriority] = useState<string | undefined>(undefined);
  const [loading, setLoading]   = useState(false);
  const [rows, setRows]         = useState<CompressionRow[]>([]);
  const [error, setError]       = useState('');
  const [fetched, setFetched]   = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const params: Record<string, string | number> = { period, limit: 200 };
      if (action)   params.action   = action;
      if (priority) params.priority = priority;
      const resp = await apiClient.get(`/api/v1/cost-compression/${storeId}`, { params });
      setRows(resp.data.data ?? []);
      setFetched(true);
    } catch {
      setError('加载失败，请重试');
    } finally {
      setLoading(false);
    }
  }, [storeId, period, action, priority]);

  const columns: ColumnsType<CompressionRow> = [
    { title: '菜品', dataIndex: 'dish_name', width: 120, fixed: 'left',
      render: (v, r) => (
        <><div style={{ fontWeight: 600 }}>{v}</div>
          <Text type="secondary" style={{ fontSize: 11 }}>{r.category ?? '-'}</Text></>
      ) },
    { title: '建议行动', dataIndex: 'compression_action', width: 100,
      render: v => {
        const cfg = ACTION_CONFIG[v] ?? { label: v, color: '#ccc' };
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
      } },
    { title: '优先级', dataIndex: 'action_priority', width: 72,
      render: v => { const c = PRIORITY_CONFIG[v]; return <span className={c?.cls}>{c?.label ?? v}</span>; } },
    { title: 'FCR超标缺口', dataIndex: 'fcr_gap', width: 150,
      sorter: (a, b) => a.fcr_gap - b.fcr_gap,
      render: v => <FcrGapBar gap={v} /> },
    { title: '当前FCR', dataIndex: 'current_fcr', width: 85,
      sorter: (a, b) => a.current_fcr - b.current_fcr,
      render: v => `${v}%` },
    { title: '目标FCR', dataIndex: 'target_fcr', width: 80,
      render: v => <span style={{ color: '#1A7A52' }}>{v}%</span> },
    { title: 'FCR趋势', dataIndex: 'fcr_trend', width: 90,
      render: v => { const c = TREND_CONFIG[v]; return <span className={c?.cls}>{c?.label ?? v}</span>; } },
    { title: '单期压缩机会', dataIndex: 'compression_opportunity_yuan', width: 120,
      sorter: (a, b) => a.compression_opportunity_yuan - b.compression_opportunity_yuan,
      render: v => <span style={{ color: '#C53030', fontWeight: 600 }}>{fmtYuan(v)}</span> },
    { title: '年化节省预估', dataIndex: 'expected_saving_yuan', width: 120,
      sorter: (a, b) => a.expected_saving_yuan - b.expected_saving_yuan,
      render: v => <span style={{ color: '#FF6B2C', fontWeight: 600 }}>{fmtYuan(v)}</span> },
    { title: '当期营收', dataIndex: 'revenue_yuan', width: 95, render: v => fmtYuan(v) },
  ];

  return (
    <>
      <div className={styles.controlBar}>
        <Select allowClear placeholder="筛选建议行动" style={{ width: 140 }}
          value={action} onChange={v => { setAction(v); setPriority(undefined); }}>
          {Object.entries(ACTION_CONFIG).map(([k, v]) => (
            <Option key={k} value={k}><Tag color={v.color}>{v.label}</Tag></Option>
          ))}
        </Select>
        <Select allowClear placeholder="筛选优先级" style={{ width: 120 }}
          value={priority} onChange={v => { setPriority(v); setAction(undefined); }}>
          {Object.entries(PRIORITY_CONFIG).map(([k, v]) => (
            <Option key={k} value={k}><span className={v.cls}>{v.label}</span></Option>
          ))}
        </Select>
        <Button type="primary" icon={<SearchOutlined />} onClick={load} loading={loading}>查询</Button>
      </div>
      {error  && <Alert type="error" message={error} style={{ marginBottom: 12 }} />}
      {!fetched && !loading && (
        <Alert type="info" message="选择筛选条件后点击查询，或直接查询全部压缩机会" style={{ marginBottom: 12 }} />
      )}
      <Table
        rowKey="id" columns={columns} dataSource={rows} loading={loading}
        scroll={{ x: 900 }} size="small"
        pagination={{ pageSize: 20, showSizeChanger: true }}
        rowClassName={r => ACTION_CONFIG[r.compression_action]?.rowClass ?? ''}
        summary={pageData => {
          const totalOpp    = pageData.reduce((s, r) => s + r.compression_opportunity_yuan, 0);
          const totalSaving = pageData.reduce((s, r) => s + r.expected_saving_yuan, 0);
          return (
            <Table.Summary.Row>
              <Table.Summary.Cell index={0} colSpan={7}>
                <strong>本页合计</strong>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={7}>
                <strong style={{ color: '#C53030' }}>{fmtYuan(totalOpp)}</strong>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={8}>
                <strong style={{ color: '#FF6B2C' }}>{fmtYuan(totalSaving)}</strong>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={9} />
            </Table.Summary.Row>
          );
        }}
      />
    </>
  );
}

// ── Tab 2: 汇总分析 ───────────────────────────────────────────────────────────

interface SummaryAction {
  compression_action: string;
  dish_count: number;
  total_opportunity: number;
  total_saving: number;
  avg_fcr_gap: number;
  high_priority_dishes: number;
}

interface SummaryTrend {
  fcr_trend: string;
  dish_count: number;
  total_opportunity: number;
  avg_current_fcr: number;
  avg_fcr_gap: number;
}

interface Summary {
  total_opportunity_yuan: number;
  total_expected_saving_yuan: number;
  by_action: SummaryAction[];
  by_trend: SummaryTrend[];
}

function SummaryTab({ storeId, period }: { storeId: string; period: string }) {
  const [loading, setLoading] = useState(false);
  const [data, setData]       = useState<Summary | null>(null);
  const [error, setError]     = useState('');

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const resp = await apiClient.get(`/api/v1/cost-compression/summary/${storeId}`, { params: { period } });
      setData(resp.data.data);
    } catch {
      setError('加载失败，请重试');
    } finally {
      setLoading(false);
    }
  }, [storeId, period]);

  const actionBarOption = data ? {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { top: 0 },
    xAxis: { type: 'category',
      data: data.by_action.map(d => ACTION_CONFIG[d.compression_action]?.label ?? d.compression_action) },
    yAxis: [
      { type: 'value', name: '压缩机会 (¥)', position: 'left' },
      { type: 'value', name: '菜品数',        position: 'right' },
    ],
    series: [
      { name: '单期压缩机会', type: 'bar', yAxisIndex: 0,
        data: data.by_action.map(d => d.total_opportunity),
        itemStyle: { color: (p: { dataIndex: number }) => {
          const k = data.by_action[p.dataIndex].compression_action;
          return ACTION_CONFIG[k]?.color ?? '#ccc';
        } },
        label: { show: true, formatter: (p: { value: number }) => `¥${p.value.toFixed(0)}` } },
      { name: '菜品数', type: 'line', yAxisIndex: 1,
        data: data.by_action.map(d => d.dish_count),
        itemStyle: { color: '#722ed1' } },
    ],
    grid: { top: 50, bottom: 40 },
  } : {};

  const trendPieOption = data ? {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie', radius: ['40%', '65%'],
      data: data.by_trend.map(d => ({
        name: TREND_CONFIG[d.fcr_trend]?.label ?? d.fcr_trend,
        value: d.dish_count,
        itemStyle: {
          color: d.fcr_trend === 'improving' ? '#1A7A52'
               : d.fcr_trend === 'worsening' ? '#C53030' : '#8c8c8c',
        },
      })),
    }],
  } : {};

  return (
    <>
      <div className={styles.controlBar}>
        <Button type="primary" icon={<SyncOutlined />} onClick={load} loading={loading}>加载汇总</Button>
      </div>
      {error  && <Alert type="error" message={error} style={{ marginBottom: 12 }} />}
      {loading && <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>}
      {data && (
        <>
          <div className={styles.kpiRow}>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>单期总压缩机会</div>
              <div className={styles.kpiValue} style={{ color: '#C53030' }}>
                {fmtYuan(data.total_opportunity_yuan)}
              </div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>年化预期节省</div>
              <div className={styles.kpiValue} style={{ color: '#FF6B2C' }}>
                {fmtYuan(data.total_expected_saving_yuan)}
              </div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>需紧急处理菜品</div>
              <div className={styles.kpiValue} style={{ color: '#C53030' }}>
                {data.by_action.find(d => d.compression_action === 'renegotiate')?.dish_count ?? 0} 道
              </div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>FCR恶化菜品</div>
              <div className={styles.kpiValue} style={{ color: '#C8923A' }}>
                {data.by_trend.find(d => d.fcr_trend === 'worsening')?.dish_count ?? 0} 道
              </div>
            </div>
          </div>

          <div className={styles.summaryCharts}>
            <Card title="各行动类型压缩机会 & 菜品数" size="small">
              <ReactECharts option={actionBarOption} style={{ height: 280 }} />
            </Card>
            <Card title="FCR趋势分布（菜品数）" size="small">
              <ReactECharts option={trendPieOption} style={{ height: 280 }} />
            </Card>
          </div>

          <Row gutter={16}>
            <Col span={14}>
              <Card title="按行动类型统计" size="small">
                <Table rowKey="compression_action" size="small" dataSource={data.by_action}
                  pagination={false}
                  rowClassName={r => ACTION_CONFIG[r.compression_action]?.rowClass ?? ''}
                  columns={[
                    { title: '建议行动', dataIndex: 'compression_action',
                      render: v => <Tag color={ACTION_CONFIG[v]?.color ?? 'default'}>{ACTION_CONFIG[v]?.label ?? v}</Tag> },
                    { title: '菜品数', dataIndex: 'dish_count', width: 70 },
                    { title: '单期机会', dataIndex: 'total_opportunity',
                      render: v => <span style={{ color: '#C53030', fontWeight: 600 }}>{fmtYuan(v)}</span> },
                    { title: '年化节省', dataIndex: 'total_saving',
                      render: v => <span style={{ color: '#FF6B2C' }}>{fmtYuan(v)}</span> },
                    { title: '平均缺口', dataIndex: 'avg_fcr_gap',
                      render: v => `${v}pp` },
                    { title: '高优先级', dataIndex: 'high_priority_dishes',
                      render: v => <span className={styles.prioHigh}>{v} 道</span> },
                  ]}
                />
              </Card>
            </Col>
            <Col span={10}>
              <Card title="FCR趋势详情" size="small">
                <Table rowKey="fcr_trend" size="small" dataSource={data.by_trend}
                  pagination={false}
                  columns={[
                    { title: 'FCR趋势', dataIndex: 'fcr_trend',
                      render: v => { const c = TREND_CONFIG[v]; return <span className={c?.cls}>{c?.label ?? v}</span>; } },
                    { title: '菜品数', dataIndex: 'dish_count', width: 70 },
                    { title: '压缩机会', dataIndex: 'total_opportunity',
                      render: v => <span style={{ color: '#C53030' }}>{fmtYuan(v)}</span> },
                    { title: '均FCR', dataIndex: 'avg_current_fcr',
                      render: v => `${v}%` },
                  ]}
                />
              </Card>
            </Col>
          </Row>
        </>
      )}
    </>
  );
}

// ── Tab 3: Top 机会 ───────────────────────────────────────────────────────────

interface TopRow {
  dish_id: string;
  dish_name: string;
  category: string | null;
  current_fcr: number;
  target_fcr: number;
  fcr_gap: number;
  compression_opportunity_yuan: number;
  expected_saving_yuan: number;
  fcr_trend: string;
  compression_action: string;
  action_priority: string;
  revenue_yuan: number;
}

function TopOpportunities({ storeId, period }: { storeId: string; period: string }) {
  const [topN, setTopN]       = useState(10);
  const [loading, setLoading] = useState(false);
  const [rows, setRows]       = useState<TopRow[]>([]);
  const [error, setError]     = useState('');

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const resp = await apiClient.get(`/api/v1/cost-compression/top/${storeId}`,
        { params: { period, limit: topN } });
      setRows(resp.data.data ?? []);
    } catch {
      setError('加载失败，请重试');
    } finally {
      setLoading(false);
    }
  }, [storeId, period, topN]);

  const barOption = rows.length ? {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { top: 0, data: ['单期压缩机会', '年化预期节省'] },
    yAxis: { type: 'category', data: [...rows].reverse().map(r => r.dish_name) },
    xAxis: { type: 'value', name: '金额 (¥)' },
    series: [
      { name: '单期压缩机会', type: 'bar', stack: 'a',
        data: [...rows].reverse().map(r => r.compression_opportunity_yuan),
        itemStyle: { color: '#C53030' } },
    ],
    grid: { left: 90, right: 20, top: 40, bottom: 30 },
  } : {};

  return (
    <>
      <div className={styles.topBar}>
        <span>显示 Top</span>
        <Select value={topN} onChange={setTopN} style={{ width: 80 }}>
          {[5, 10, 20].map(n => <Option key={n} value={n}>{n}</Option>)}
        </Select>
        <Button type="primary" icon={<DollarOutlined />} onClick={load} loading={loading}>加载 Top 机会</Button>
      </div>
      {error  && <Alert type="error" message={error} style={{ marginBottom: 12 }} />}
      {loading && <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>}
      {rows.length > 0 && (
        <>
          <Card title={`Top ${rows.length} 压缩机会（单期可节省 ¥）`} size="small" style={{ marginBottom: 16 }}>
            <ReactECharts option={barOption} style={{ height: Math.max(240, rows.length * 28 + 80) }} />
          </Card>
          <Table rowKey="dish_id" size="small" dataSource={rows} pagination={false}
            rowClassName={r => ACTION_CONFIG[r.compression_action]?.rowClass ?? ''}
            columns={[
              { title: '排名', width: 50, render: (_, __, i) => <strong>{i + 1}</strong> },
              { title: '菜品', dataIndex: 'dish_name', ellipsis: true,
                render: (v, r) => <><span style={{ fontWeight: 600 }}>{v}</span> <Text type="secondary" style={{ fontSize: 11 }}>{r.category ?? ''}</Text></> },
              { title: '行动', dataIndex: 'compression_action',
                render: v => <Tag color={ACTION_CONFIG[v]?.color ?? 'default'}>{ACTION_CONFIG[v]?.label ?? v}</Tag> },
              { title: '优先级', dataIndex: 'action_priority',
                render: v => <span className={PRIORITY_CONFIG[v]?.cls}>{PRIORITY_CONFIG[v]?.label ?? v}</span> },
              { title: 'FCR缺口', dataIndex: 'fcr_gap', render: v => `+${v}pp` },
              { title: '当前FCR', dataIndex: 'current_fcr', render: v => `${v}%` },
              { title: '目标FCR', dataIndex: 'target_fcr', render: v => <span style={{ color: '#1A7A52' }}>{v}%</span> },
              { title: '单期机会', dataIndex: 'compression_opportunity_yuan',
                render: v => <strong style={{ color: '#C53030' }}>{fmtYuan(v)}</strong> },
              { title: '年化节省', dataIndex: 'expected_saving_yuan',
                render: v => <strong style={{ color: '#FF6B2C' }}>{fmtYuan(v)}</strong> },
            ]}
          />
        </>
      )}
    </>
  );
}

// ── Tab 4: 菜品 FCR 历史 ──────────────────────────────────────────────────────

interface FcrHistRow {
  period: string;
  current_fcr: number;
  prev_fcr: number | null;
  fcr_gap: number;
  target_fcr: number;
  store_avg_fcr: number;
  fcr_trend: string;
  compression_action: string;
  action_priority: string;
  compression_opportunity_yuan: number;
  expected_saving_yuan: number;
  revenue_yuan: number;
}

function DishFcrHistory({ storeId }: { storeId: string }) {
  const [dishId, setDishId]   = useState('');
  const [loading, setLoading] = useState(false);
  const [rows, setRows]       = useState<FcrHistRow[]>([]);
  const [error, setError]     = useState('');

  const load = useCallback(async () => {
    if (!dishId.trim()) return;
    setLoading(true); setError('');
    try {
      const resp = await apiClient.get(
        `/api/v1/cost-compression/dish/${storeId}/${dishId.trim()}`,
        { params: { periods: 12 } }
      );
      setRows(resp.data.data ?? []);
    } catch {
      setError('加载失败，请重试');
    } finally {
      setLoading(false);
    }
  }, [storeId, dishId]);

  const fcrLineOption = rows.length ? {
    tooltip: { trigger: 'axis' },
    legend: { top: 0, data: ['当前FCR', '门店均FCR', '目标FCR'] },
    xAxis: { type: 'category', data: [...rows].reverse().map(r => r.period) },
    yAxis: { type: 'value', name: 'FCR (%)', min: 0 },
    series: [
      { name: '当前FCR', type: 'line', smooth: true,
        data: [...rows].reverse().map(r => r.current_fcr),
        lineStyle: { width: 2, color: '#C53030' }, itemStyle: { color: '#C53030' },
        areaStyle: { color: 'rgba(255,77,79,0.08)' } },
      { name: '门店均FCR', type: 'line', smooth: true,
        data: [...rows].reverse().map(r => r.store_avg_fcr),
        lineStyle: { width: 1.5, color: '#C8923A', type: 'dashed' },
        itemStyle: { color: '#C8923A' } },
      { name: '目标FCR', type: 'line', smooth: true,
        data: [...rows].reverse().map(r => r.target_fcr),
        lineStyle: { width: 1.5, color: '#1A7A52', type: 'dashed' },
        itemStyle: { color: '#1A7A52' } },
    ],
    grid: { top: 50, bottom: 40 },
  } : {};

  return (
    <>
      <div className={styles.historySearch}>
        <Input placeholder="输入菜品 ID (如 D001)" style={{ width: 220 }}
          value={dishId} onChange={e => setDishId(e.target.value)} onPressEnter={load} />
        <Button type="primary" icon={<SearchOutlined />} onClick={load} loading={loading}>查询历史</Button>
      </div>
      {error  && <Alert type="error" message={error} style={{ marginBottom: 12 }} />}
      {loading && <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>}
      {!rows.length && !loading && (
        <div className={styles.historyHint}>输入菜品 ID 后点击查询，可查看该菜品近 12 期的 FCR 变化与压缩机会历史。</div>
      )}
      {rows.length > 0 && (
        <>
          <Card title="FCR 趋势（当前 vs 门店均值 vs 目标）" size="small" style={{ marginBottom: 16 }}>
            <ReactECharts option={fcrLineOption} style={{ height: 260 }} />
          </Card>
          <Table rowKey="period" size="small" dataSource={rows} pagination={false}
            rowClassName={r => ACTION_CONFIG[r.compression_action]?.rowClass ?? ''}
            columns={[
              { title: '期间', dataIndex: 'period', width: 90 },
              { title: '当前FCR', dataIndex: 'current_fcr', render: v => `${v}%` },
              { title: '上期FCR', dataIndex: 'prev_fcr', render: v => v == null ? '-' : `${v}%` },
              { title: '目标FCR', dataIndex: 'target_fcr', render: v => <span style={{ color: '#1A7A52' }}>{v}%</span> },
              { title: 'FCR缺口', dataIndex: 'fcr_gap',
                render: v => <span style={{ color: v > 0 ? '#C53030' : '#1A7A52' }}>{v > 0 ? `+${v}pp` : `${v}pp`}</span> },
              { title: 'FCR趋势', dataIndex: 'fcr_trend',
                render: v => { const c = TREND_CONFIG[v]; return <span className={c?.cls}>{c?.label ?? v}</span>; } },
              { title: '建议行动', dataIndex: 'compression_action',
                render: v => <Tag color={ACTION_CONFIG[v]?.color ?? 'default'}>{ACTION_CONFIG[v]?.label ?? v}</Tag> },
              { title: '单期机会', dataIndex: 'compression_opportunity_yuan',
                render: v => <span style={{ color: '#C53030' }}>{fmtYuan(v)}</span> },
              { title: '年化节省', dataIndex: 'expected_saving_yuan',
                render: v => <span style={{ color: '#FF6B2C' }}>{fmtYuan(v)}</span> },
            ]}
          />
        </>
      )}
    </>
  );
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

const CostCompressionPage: React.FC = () => {
  const [storeId] = useState(DEFAULT_STORE);
  const [period, setPeriod]   = useState(DEFAULT_PERIOD);
  const [reduction, setReduction] = useState(2.0);
  const [computing, setComputing] = useState(false);
  const [computeMsg, setComputeMsg] = useState('');

  const handleCompute = async () => {
    setComputing(true); setComputeMsg('');
    try {
      const resp = await apiClient.post(
        `/api/v1/cost-compression/compute/${storeId}`,
        null,
        { params: { period, target_fcr_reduction: reduction } }
      );
      const d = resp.data.data;
      setComputeMsg(
        `计算完成：${d.dish_count} 道菜，门店均FCR ${d.store_avg_fcr}% → 目标 ${d.target_fcr}% | ` +
        `单期总压缩机会 ¥${d.total_opportunity_yuan?.toFixed(2)}，` +
        `年化节省预估 ¥${d.total_expected_saving_yuan?.toFixed(2)}`
      );
    } catch {
      setComputeMsg('计算失败，请重试');
    } finally {
      setComputing(false);
    }
  };

  const periods: string[] = [];
  for (let i = 0; i < 12; i++) periods.push(dayjs().subtract(i, 'month').format('YYYY-MM'));

  return (
    <div>
      <div className={styles.pageHeader}>
        <Row justify="space-between" align="middle">
          <Col>
            <Title level={4} style={{ margin: 0 }}>菜品成本压缩机会引擎</Title>
            <Text type="secondary">
              逐道菜量化 FCR 超标缺口，识别最高价值的成本压缩机会，直接服务"成本率降低 2 个点"目标
            </Text>
          </Col>
          <Col>
            <Space>
              <Select value={period} onChange={setPeriod} style={{ width: 120 }}>
                {periods.map(p => <Option key={p} value={p}>{p}</Option>)}
              </Select>
              <Tooltip title="目标降低几个百分点（默认 2pp）">
                <Select value={reduction} onChange={setReduction} style={{ width: 100 }}>
                  {[1.0, 1.5, 2.0, 2.5, 3.0].map(n => (
                    <Option key={n} value={n}>目标降 {n}pp</Option>
                  ))}
                </Select>
              </Tooltip>
              <Button type="primary" icon={<WarningOutlined />} loading={computing} onClick={handleCompute}>
                触发压缩计算
              </Button>
            </Space>
          </Col>
        </Row>
        {computeMsg && (
          <Alert type={computeMsg.includes('失败') ? 'error' : 'success'}
            message={computeMsg} style={{ marginTop: 8 }} closable onClose={() => setComputeMsg('')} />
        )}
      </div>

      <Tabs defaultActiveKey="board" items={[
        { key: 'board',   label: '压缩机会榜', children: <CompressionBoard storeId={storeId} period={period} /> },
        { key: 'summary', label: '汇总分析',   children: <SummaryTab      storeId={storeId} period={period} /> },
        { key: 'top',     label: 'Top 机会',   children: <TopOpportunities storeId={storeId} period={period} /> },
        { key: 'history', label: '菜品FCR历史', children: <DishFcrHistory  storeId={storeId} /> },
      ]} />
    </div>
  );
};

export default CostCompressionPage;
