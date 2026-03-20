/**
 * 菜品营收归因页面 — Phase 6 Month 9
 * 4 Tabs: 归因看板 / 汇总分析 / 增降幅榜 / 菜品归因历史
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  Tabs, Table, Tag, Select, Button, Input, Spin, Alert, Tooltip,
  Card, Space, Typography, Row, Col, Statistic,
} from 'antd';
import { SearchOutlined, SyncOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';

import { apiClient } from '../services/api';
import styles from './DishAttributionPage.module.css';

const { Title, Text } = Typography;
const { Option } = Select;

// ── 常量 ─────────────────────────────────────────────────────────────────────

const DEFAULT_STORE = localStorage.getItem('store_id') || '';
const DEFAULT_PERIOD = dayjs().subtract(1, 'month').format('YYYY-MM');

const DRIVER_CONFIG: Record<string, { color: string; label: string }> = {
  price:       { color: 'orange',  label: '价格驱动' },
  volume:      { color: 'blue',    label: '销量驱动' },
  interaction: { color: 'green',   label: '交互效应' },
  mixed:       { color: 'purple',  label: '混合因素' },
  stable:      { color: 'default', label: '稳定' },
};

const ROW_CLASS: Record<string, string> = {
  price:       styles.rowPrice,
  volume:      styles.rowVolume,
  interaction: styles.rowInteraction,
  mixed:       styles.rowMixed,
  stable:      styles.rowStable,
};

// ── 工具函数 ──────────────────────────────────────────────────────────────────

function fmtYuan(v: number | null | undefined): string {
  if (v == null) return '-';
  const sign = v >= 0 ? '+' : '';
  return `${sign}¥${Math.abs(v).toFixed(2)}`;
}

function DeltaCell({ value }: { value: number }) {
  const cls = value >= 0 ? styles.positive : styles.negative;
  const icon = value >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />;
  return (
    <span className={`${styles.effectCell} ${cls}`}>
      {icon} ¥{Math.abs(value).toFixed(2)}
    </span>
  );
}

function EffectCell({ value, label }: { value: number; label: string }) {
  const cls = value >= 0 ? styles.positive : styles.negative;
  return (
    <Tooltip title={`${label}: ${fmtYuan(value)}`}>
      <span className={`${styles.effectCell} ${cls}`}>{fmtYuan(value)}</span>
    </Tooltip>
  );
}

// ── 子组件 ────────────────────────────────────────────────────────────────────

interface AttributionRow {
  id: number;
  dish_id: string;
  dish_name: string;
  category: string | null;
  current_revenue: number;
  prev_revenue: number;
  revenue_delta: number;
  revenue_delta_pct: number;
  current_orders: number;
  prev_orders: number;
  order_delta: number;
  current_avg_price: number;
  prev_avg_price: number;
  price_delta: number;
  price_effect_yuan: number;
  volume_effect_yuan: number;
  interaction_yuan: number;
  primary_driver: string;
  prev_period: string;
}

function AttributionBoard({
  storeId, period,
}: { storeId: string; period: string }) {
  const [driver, setDriver] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<AttributionRow[]>([]);
  const [error, setError] = useState('');
  const [fetched, setFetched] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const params: Record<string, string | number> = { period, limit: 200 };
      if (driver) params.driver = driver;
      const resp = await apiClient.get(`/api/v1/dish-attribution/${storeId}`, { params });
      setRows(resp.data.data ?? []);
      setFetched(true);
    } catch {
      setError('加载失败，请重试');
    } finally {
      setLoading(false);
    }
  }, [storeId, period, driver]);

  const columns: ColumnsType<AttributionRow> = [
    { title: '菜品', dataIndex: 'dish_name', width: 120, fixed: 'left',
      render: (v, r) => <><div style={{ fontWeight: 600 }}>{v}</div><Text type="secondary" style={{ fontSize: 11 }}>{r.category ?? '-'}</Text></> },
    { title: '驱动因子', dataIndex: 'primary_driver', width: 100,
      render: v => { const c = DRIVER_CONFIG[v] ?? { color: 'default', label: v }; return <Tag color={c.color} className={styles.driverTag}>{c.label}</Tag>; } },
    { title: '营收变化', dataIndex: 'revenue_delta', width: 110, sorter: (a, b) => a.revenue_delta - b.revenue_delta,
      render: v => <DeltaCell value={v} /> },
    { title: '变化%', dataIndex: 'revenue_delta_pct', width: 80,
      render: v => <span className={v >= 0 ? styles.positive : styles.negative}>{v >= 0 ? '+' : ''}{v}%</span> },
    { title: '价格效应', dataIndex: 'price_effect_yuan', width: 100,
      render: v => <EffectCell value={v} label="价格效应" /> },
    { title: '销量效应', dataIndex: 'volume_effect_yuan', width: 100,
      render: v => <EffectCell value={v} label="销量效应" /> },
    { title: '交互效应', dataIndex: 'interaction_yuan', width: 100,
      render: v => <EffectCell value={v} label="交互效应" /> },
    { title: '当期营收', dataIndex: 'current_revenue', width: 100,
      render: v => `¥${Number(v).toFixed(2)}` },
    { title: '上期营收', dataIndex: 'prev_revenue', width: 100,
      render: v => `¥${Number(v).toFixed(2)}` },
    { title: '均价变化', dataIndex: 'price_delta', width: 90,
      render: v => <span className={v >= 0 ? styles.positive : styles.negative}>{fmtYuan(v)}</span> },
    { title: '销量变化', dataIndex: 'order_delta', width: 80,
      render: v => <span className={v >= 0 ? styles.positive : styles.negative}>{v >= 0 ? '+' : ''}{v}</span> },
  ];

  return (
    <>
      <div className={styles.controlBar}>
        <Select
          allowClear
          placeholder="筛选驱动因子"
          style={{ width: 160 }}
          value={driver}
          onChange={setDriver}
        >
          {Object.entries(DRIVER_CONFIG).map(([k, v]) => (
            <Option key={k} value={k}><Tag color={v.color} className={styles.driverTag}>{v.label}</Tag></Option>
          )) : null}
        </Select>
        <Button type="primary" icon={<SearchOutlined />} onClick={load} loading={loading}>查询</Button>
      </div>
      {error && <Alert type="error" message={error} style={{ marginBottom: 12 }} />}
      {!fetched && !loading && (
        <Alert type="info" message="选择筛选条件后点击查询加载数据" style={{ marginBottom: 12 }} />
      )}
      <Table
        rowKey="id"
        columns={columns}
        dataSource={rows}
        loading={loading}
        scroll={{ x: 900 }}
        size="small"
        pagination={{ pageSize: 20, showSizeChanger: true }}
        rowClassName={r => ROW_CLASS[r.primary_driver] ?? ''}
      />
    </>
  );
}

// ── 汇总分析 ──────────────────────────────────────────────────────────────────

interface SummaryDriver {
  primary_driver: string;
  dish_count: number;
  total_delta: number;
  price_effect: number;
  volume_effect: number;
  interaction: number;
  gainers: number;
  losers: number;
}

interface Summary {
  store_id: string;
  period: string;
  total_delta: number;
  total_price_effect: number;
  total_volume_effect: number;
  total_interaction: number;
  by_driver: SummaryDriver[];
}

function SummaryAnalysis({ storeId, period }: { storeId: string; period: string }) {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const resp = await apiClient.get(`/api/v1/dish-attribution/summary/${storeId}`, { params: { period } });
      setData(resp.data.data);
    } catch {
      setError('加载失败，请重试');
    } finally {
      setLoading(false);
    }
  }, [storeId, period]);

  const pieOption = data ? {
    tooltip: { trigger: 'item', formatter: '{b}: {d}%' },
    legend: { bottom: 0, type: 'scroll' },
    series: [{
      type: 'pie',
      radius: ['40%', '65%'],
      data: data.by_driver.map(d => ({
        name: DRIVER_CONFIG[d.primary_driver]?.label ?? d.primary_driver,
        value: d.dish_count,
      })),
      emphasis: { itemStyle: { shadowBlur: 10 } },
    }],
  } : {};

  const barOption = data ? {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: {
      type: 'category',
      data: data.by_driver.map(d => DRIVER_CONFIG[d.primary_driver]?.label ?? d.primary_driver),
    },
    yAxis: { type: 'value', name: '营收变化 (¥)' },
    series: [
      { name: '价格效应', type: 'bar', stack: 'total',
        data: data.by_driver.map(d => d.price_effect),
        itemStyle: { color: '#C8923A' } },
      { name: '销量效应', type: 'bar', stack: 'total',
        data: data.by_driver.map(d => d.volume_effect),
        itemStyle: { color: '#0AAF9A' } },
      { name: '交互效应', type: 'bar', stack: 'total',
        data: data.by_driver.map(d => d.interaction),
        itemStyle: { color: '#1A7A52' } },
    ],
    legend: { top: 0 },
    grid: { top: 40, bottom: 40 },
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
          <div className={styles.summaryGrid}>
            <Card size="small" className={styles.statCard}>
              <div className={styles.statLabel}>总营收变化</div>
              <div className={`${styles.statValue} ${data.total_delta >= 0 ? styles.statValuePositive : styles.statValueNegative}`}>
                {fmtYuan(data.total_delta)}
              </div>
            </Card>
            <Card size="small" className={styles.statCard}>
              <div className={styles.statLabel}>价格效应合计</div>
              <div className={`${styles.statValue} ${data.total_price_effect >= 0 ? styles.statValuePositive : styles.statValueNegative}`}>
                {fmtYuan(data.total_price_effect)}
              </div>
            </Card>
            <Card size="small" className={styles.statCard}>
              <div className={styles.statLabel}>销量效应合计</div>
              <div className={`${styles.statValue} ${data.total_volume_effect >= 0 ? styles.statValuePositive : styles.statValueNegative}`}>
                {fmtYuan(data.total_volume_effect)}
              </div>
            </Card>
            <Card size="small" className={styles.statCard}>
              <div className={styles.statLabel}>交互效应合计</div>
              <div className={`${styles.statValue} ${data.total_interaction >= 0 ? styles.statValuePositive : styles.statValueNegative}`}>
                {fmtYuan(data.total_interaction)}
              </div>
            </Card>
          </div>
          <div className={styles.chartsRow}>
            <Card title="驱动因子分布 (菜品数)" size="small">
              <ReactECharts option={pieOption} style={{ height: 260 }} />
            </Card>
            <Card title="各驱动因子 PVM 效应分解" size="small">
              <ReactECharts option={barOption} style={{ height: 260 }} />
            </Card>
          </div>
          <div style={{ marginTop: 16 }}>
            <Table
              rowKey="primary_driver"
              size="small"
              dataSource={data.by_driver}
              pagination={false}
              columns={[
                { title: '驱动因子', dataIndex: 'primary_driver',
                  render: v => <Tag color={DRIVER_CONFIG[v]?.color ?? 'default'}>{DRIVER_CONFIG[v]?.label ?? v}</Tag> },
                { title: '菜品数', dataIndex: 'dish_count', width: 80 },
                { title: '营收变化', dataIndex: 'total_delta', render: v => <DeltaCell value={v} /> },
                { title: '价格效应', dataIndex: 'price_effect', render: v => <EffectCell value={v} label="价格效应" /> },
                { title: '销量效应', dataIndex: 'volume_effect', render: v => <EffectCell value={v} label="销量效应" /> },
                { title: '交互效应', dataIndex: 'interaction', render: v => <EffectCell value={v} label="交互效应" /> },
                { title: '上涨菜品', dataIndex: 'gainers', width: 90,
                  render: v => <span className={styles.positive}>{v}</span> },
                { title: '下跌菜品', dataIndex: 'losers', width: 90,
                  render: v => <span className={styles.negative}>{v}</span> },
              ]}
            />
          </div>
        </>
      )}
    </>
  );
}

// ── 增降幅榜 ──────────────────────────────────────────────────────────────────

interface MoverRow {
  dish_id: string;
  dish_name: string;
  category: string | null;
  current_revenue: number;
  prev_revenue: number;
  revenue_delta: number;
  revenue_delta_pct: number;
  price_effect_yuan: number;
  volume_effect_yuan: number;
  interaction_yuan: number;
  primary_driver: string;
}

function MoverList({ storeId, period }: { storeId: string; period: string }) {
  const [loading, setLoading] = useState(false);
  const [gainers, setGainers] = useState<MoverRow[]>([]);
  const [losers, setLosers] = useState<MoverRow[]>([]);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [rGain, rLoss] = await Promise.all([
        apiClient.get(`/api/v1/dish-attribution/movers/${storeId}`, { params: { period, direction: 'gain', limit: 10 } }),
        apiClient.get(`/api/v1/dish-attribution/movers/${storeId}`, { params: { period, direction: 'loss', limit: 10 } }),
      ]);
      setGainers(rGain.data.data ?? []);
      setLosers(rLoss.data.data ?? []);
    } catch {
      setError('加载失败，请重试');
    } finally {
      setLoading(false);
    }
  }, [storeId, period]);

  const barCols: ColumnsType<MoverRow> = [
    { title: '菜品', dataIndex: 'dish_name', ellipsis: true, width: 120 },
    { title: '驱动', dataIndex: 'primary_driver',
      render: v => <Tag color={DRIVER_CONFIG[v]?.color ?? 'default'} className={styles.driverTag}>{DRIVER_CONFIG[v]?.label ?? v}</Tag> },
    { title: '营收变化', dataIndex: 'revenue_delta', render: v => <DeltaCell value={v} /> },
    { title: '变化%', dataIndex: 'revenue_delta_pct',
      render: v => <span className={v >= 0 ? styles.positive : styles.negative}>{v >= 0 ? '+' : ''}{v}%</span> },
  ];

  const gainOption = gainers.length ? {
    tooltip: { trigger: 'axis' },
    yAxis: { type: 'category', data: gainers.map(r => r.dish_name).reverse() },
    xAxis: { type: 'value', name: '营收变化 (¥)' },
    series: [
      { name: '价格效应', type: 'bar', stack: 'total', data: gainers.map(r => r.price_effect_yuan).reverse(), itemStyle: { color: '#C8923A' } },
      { name: '销量效应', type: 'bar', stack: 'total', data: gainers.map(r => r.volume_effect_yuan).reverse(), itemStyle: { color: '#0AAF9A' } },
      { name: '交互效应', type: 'bar', stack: 'total', data: gainers.map(r => r.interaction_yuan).reverse(), itemStyle: { color: '#1A7A52' } },
    ],
    legend: { top: 0 },
    grid: { left: 80, right: 20, top: 30, bottom: 30 },
  } : {};

  const lossOption = losers.length ? {
    tooltip: { trigger: 'axis' },
    yAxis: { type: 'category', data: losers.map(r => r.dish_name) },
    xAxis: { type: 'value', name: '营收变化 (¥)' },
    series: [
      { name: '价格效应', type: 'bar', stack: 'total', data: losers.map(r => r.price_effect_yuan), itemStyle: { color: '#C8923A' } },
      { name: '销量效应', type: 'bar', stack: 'total', data: losers.map(r => r.volume_effect_yuan), itemStyle: { color: '#0AAF9A' } },
      { name: '交互效应', type: 'bar', stack: 'total', data: losers.map(r => r.interaction_yuan), itemStyle: { color: '#1A7A52' } },
    ],
    legend: { top: 0 },
    grid: { left: 80, right: 20, top: 30, bottom: 30 },
  } : {};

  return (
    <>
      <div className={styles.controlBar}>
        <Button type="primary" icon={<SyncOutlined />} onClick={load} loading={loading}>加载榜单</Button>
      </div>
      {error && <Alert type="error" message={error} style={{ marginBottom: 12 }} />}
      {loading && <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>}
      {(gainers.length > 0 || losers.length > 0) && (
        <>
          <div className={styles.moversRow}>
            <Card
              title={<span style={{ color: '#1A7A52' }}><ArrowUpOutlined /> 增幅最大 Top 10</span>}
              size="small"
            >
              {gainers.length > 0 && (
                <ReactECharts option={gainOption} style={{ height: 240 }} />
              )}
              <Table
                rowKey="dish_id" size="small" dataSource={gainers}
                columns={barCols} pagination={false}
                rowClassName={() => styles.rowVolume}
              />
            </Card>
            <Card
              title={<span style={{ color: '#C53030' }}><ArrowDownOutlined /> 降幅最大 Top 10</span>}
              size="small"
            >
              {losers.length > 0 && (
                <ReactECharts option={lossOption} style={{ height: 240 }} />
              )}
              <Table
                rowKey="dish_id" size="small" dataSource={losers}
                columns={barCols} pagination={false}
                rowClassName={() => styles.rowPrice}
              />
            </Card>
          </div>
        </>
      )}
    </>
  );
}

// ── 菜品归因历史 ──────────────────────────────────────────────────────────────

interface HistoryRow {
  period: string;
  prev_period: string;
  revenue_delta: number;
  revenue_delta_pct: number;
  price_effect_yuan: number;
  volume_effect_yuan: number;
  interaction_yuan: number;
  order_delta: number;
  price_delta: number;
  primary_driver: string;
}

function DishHistory({ storeId, period }: { storeId: string; period: string }) {
  const [dishId, setDishId] = useState('');
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!dishId.trim()) return;
    setLoading(true); setError('');
    try {
      const resp = await apiClient.get(
        `/api/v1/dish-attribution/dish/${storeId}/${dishId.trim()}`,
        { params: { periods: 12 } }
      );
      setRows(resp.data.data ?? []);
    } catch {
      setError('加载失败，请重试');
    } finally {
      setLoading(false);
    }
  }, [storeId, dishId]);

  const histOption = rows.length ? {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { top: 0, data: ['价格效应', '销量效应', '交互效应'] },
    xAxis: { type: 'category', data: [...rows].reverse().map(r => r.period) },
    yAxis: { type: 'value', name: '营收变化 (¥)' },
    series: [
      { name: '价格效应', type: 'bar', stack: 'total',
        data: [...rows].reverse().map(r => r.price_effect_yuan),
        itemStyle: { color: '#C8923A' } },
      { name: '销量效应', type: 'bar', stack: 'total',
        data: [...rows].reverse().map(r => r.volume_effect_yuan),
        itemStyle: { color: '#0AAF9A' } },
      { name: '交互效应', type: 'bar', stack: 'total',
        data: [...rows].reverse().map(r => r.interaction_yuan),
        itemStyle: { color: '#1A7A52' } },
    ],
    grid: { top: 50, bottom: 30 },
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
        <div className={styles.historyHint}>输入菜品 ID 后点击查询，可查看该菜品近 12 期的 PVM 归因历史。</div>
      )}
      {rows.length > 0 && (
        <>
          <Card title="PVM 效应历史分解" size="small" style={{ marginBottom: 16 }}>
            <ReactECharts option={histOption} style={{ height: 280 }} />
          </Card>
          <Table
            rowKey="period"
            size="small"
            dataSource={rows}
            pagination={false}
            columns={[
              { title: '期间', dataIndex: 'period', width: 90 },
              { title: '对比期', dataIndex: 'prev_period', width: 90 },
              { title: '营收变化', dataIndex: 'revenue_delta', render: v => <DeltaCell value={v} /> },
              { title: '变化%', dataIndex: 'revenue_delta_pct',
                render: v => <span className={v >= 0 ? styles.positive : styles.negative}>{v >= 0 ? '+' : ''}{v}%</span> },
              { title: '价格效应', dataIndex: 'price_effect_yuan', render: v => <EffectCell value={v} label="价格效应" /> },
              { title: '销量效应', dataIndex: 'volume_effect_yuan', render: v => <EffectCell value={v} label="销量效应" /> },
              { title: '交互效应', dataIndex: 'interaction_yuan', render: v => <EffectCell value={v} label="交互效应" /> },
              { title: '销量变化', dataIndex: 'order_delta',
                render: v => <span className={v >= 0 ? styles.positive : styles.negative}>{v >= 0 ? '+' : ''}{v}</span> },
              { title: '均价变化', dataIndex: 'price_delta', render: v => <EffectCell value={v} label="均价变化" /> },
              { title: '主要驱动', dataIndex: 'primary_driver',
                render: v => <Tag color={DRIVER_CONFIG[v]?.color ?? 'default'}>{DRIVER_CONFIG[v]?.label ?? v}</Tag> },
            ]}
          />
        </>
      )}
    </>
  );
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

const DishAttributionPage: React.FC = () => {
  const [storeId,      setStoreId]      = useState(DEFAULT_STORE);
  const [storeOptions, setStoreOptions] = useState<string[]>([DEFAULT_STORE]);
  const [period, setPeriod] = useState(DEFAULT_PERIOD);

  useEffect(() => {
    apiClient.get<{ items: Array<{ id: string }> }>('/api/v1/stores?limit=50')
      .then(data => {
        const ids = (data.items ?? []).map((s: { id: string }) => s.id).filter(Boolean);
        if (ids.length > 0) setStoreOptions(ids);
      })
      .catch(() => { /* 保持默认 */ });
  }, []);
  const [computing, setComputing] = useState(false);
  const [computeMsg, setComputeMsg] = useState('');

  const handleCompute = async () => {
    setComputing(true); setComputeMsg('');
    try {
      const resp = await apiClient.post(
        `/api/v1/dish-attribution/compute/${storeId}?period=${period}`
      );
      const d = resp.data.data;
      setComputeMsg(
        `归因计算完成：分析菜品 ${d.dish_count} 道，` +
        `新增 ${d.new_dishes}，停售 ${d.discontinued_dishes}，` +
        `总营收变化 ${fmtYuan(d.total_revenue_delta)}`
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
            <Title level={4} style={{ margin: 0 }}>菜品营收归因 — Price-Volume-Mix 分析</Title>
            <Text type="secondary">
              将营收变化拆解为价格效应 + 销量效应 + 交互效应，精准识别主要驱动因子
            </Text>
          </Col>
          <Col>
            <Space>
              <Select value={storeId} onChange={setStoreId} style={{ width: 110 }}>
                {storeOptions.map(s => <Option key={s} value={s}>{s}</Option>)}
              </Select>
              <Select
                value={period}
                onChange={setPeriod}
                style={{ width: 120 }}
              >
                {periods.map(p => <Option key={p} value={p}>{p}</Option>)}
              </Select>
              <Button
                type="primary"
                icon={<SyncOutlined />}
                loading={computing}
                onClick={handleCompute}
              >
                触发归因计算
              </Button>
            </Space>
          </Col>
        </Row>
        {computeMsg && (
          <Alert
            type={computeMsg.includes('失败') ? 'error' : 'success'}
            message={computeMsg}
            style={{ marginTop: 8 }}
            closable
            onClose={() => setComputeMsg('')}
          />
        )}
      </div>

      <Tabs
        defaultActiveKey="board"
        items={[
          {
            key: 'board',
            label: '归因看板',
            children: <AttributionBoard storeId={storeId} period={period} />,
          },
          {
            key: 'summary',
            label: '汇总分析',
            children: <SummaryAnalysis storeId={storeId} period={period} />,
          },
          {
            key: 'movers',
            label: '增降幅榜',
            children: <MoverList storeId={storeId} period={period} />,
          },
          {
            key: 'history',
            label: '菜品归因历史',
            children: <DishHistory storeId={storeId} period={period} />,
          },
        ]}
      />
    </div>
  );
};

export default DishAttributionPage;
