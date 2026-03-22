/**
 * 跨店菜品对标引擎 — Phase 6 Month 4
 * 对比同名菜品跨门店 FCR/GPM 排名，量化¥改进潜力，推广最佳实践
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Row, Col, Card, Statistic, Select, Button, Table, Tag, Tabs, Spin,
  Typography, Space, Tooltip, message, Empty, Input,
} from 'antd';
import {
  TrophyOutlined, RiseOutlined, FallOutlined, SyncOutlined,
  SearchOutlined, BarChartOutlined, WarningOutlined, LineChartOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { apiClient, handleApiError } from '../services/api';
import styles from './DishBenchmarkPage.module.css';

const { Title, Text } = Typography;
const { Option } = Select;

// ── 配置 ──────────────────────────────────────────────────────────────────────
const TIER_CONFIG: Record<string, { label: string; color: string; antColor: string; cls: string }> = {
  top:        { label: '标杆',   color: '#389e0d', antColor: 'success', cls: styles.tierTop },
  above_avg:  { label: '良好',   color: '#FF6B2C', antColor: 'processing', cls: styles.tierAboveAvg },
  below_avg:  { label: '待改进', color: '#C8923A', antColor: 'warning', cls: styles.tierBelowAvg },
  laggard:    { label: '落后',   color: '#C53030', antColor: 'error', cls: styles.tierLaggard },
};

// ── 类型 ──────────────────────────────────────────────────────────────────────
interface BenchRecord {
  id: number;
  dish_name: string;
  store_count: number;
  food_cost_rate: number;
  gross_profit_margin: number;
  order_count: number;
  revenue_yuan: number;
  fcr_rank: number;
  fcr_percentile: number;
  fcr_tier: string;
  best_fcr_value: number;
  best_fcr_store_id: string;
  fcr_gap_pp: number;
  fcr_gap_yuan_impact: number;
  gpm_rank: number;
  gpm_percentile: number;
  gpm_tier: string;
  best_gpm_value: number;
  best_gpm_store_id: string;
  gpm_gap_pp: number;
  gpm_gap_yuan_impact: number;
}

interface TierStat {
  fcr_tier: string;
  dish_count: number;
  fcr_yuan_potential: number;
  gpm_yuan_potential: number;
  avg_fcr_gap: number;
  avg_gpm_gap: number;
}

interface Summary {
  store_id: string;
  period: string;
  total_dishes: number;
  by_tier: TierStat[];
  total_fcr_potential: number;
  total_gpm_potential: number;
}

interface TrendPoint {
  period: string;
  dish_count: number;
  laggard_count: number;
  top_count: number;
  avg_fcr_gap: number;
  avg_gpm_gap: number;
  total_fcr_potential: number;
  total_gpm_potential: number;
}

interface CrossStoreRow {
  store_id: string;
  store_count: number;
  food_cost_rate: number;
  gross_profit_margin: number;
  order_count: number;
  revenue_yuan: number;
  fcr_rank: number;
  fcr_tier: string;
  fcr_gap_pp: number;
  fcr_gap_yuan_impact: number;
  gpm_rank: number;
  gpm_tier: string;
  gpm_gap_pp: number;
  gpm_gap_yuan_impact: number;
}

// ── 辅助 ──────────────────────────────────────────────────────────────────────
const fmt  = (n: number) =>
  `¥${Math.abs(n).toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}`;
const fmtPct = (n: number) => `${Number(n).toFixed(1)}%`;
const fmtPP  = (n: number) => `${n > 0 ? '+' : ''}${Number(n).toFixed(1)}pp`;

// ── 主页面 ────────────────────────────────────────────────────────────────────
const DishBenchmarkPage: React.FC = () => {
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
  const [computing,  setComputing]  = useState(false);
  const [loading,    setLoading]    = useState(false);
  const [records,    setRecords]    = useState<BenchRecord[]>([]);
  const [summary,    setSummary]    = useState<Summary | null>(null);
  const [trend,      setTrend]      = useState<TrendPoint[]>([]);
  const [tierFilter, setTierFilter] = useState<string | undefined>(undefined);
  const [activeTab,  setActiveTab]  = useState('ranking');
  // 菜品横向对比
  const [dishName,   setDishName]   = useState('');
  const [crossStore, setCrossStore] = useState<CrossStoreRow[]>([]);
  const [crossLoading, setCrossLoading] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [recRes, sumRes, trendRes] = await Promise.all([
        apiClient.get(`/api/v1/dish-benchmark/store/${storeId}`, {
          params: { period, fcr_tier: tierFilter, limit: 100 },
        }),
        apiClient.get(`/api/v1/dish-benchmark/store/${storeId}/summary`,
          { params: { period } }),
        apiClient.get(`/api/v1/dish-benchmark/store/${storeId}/trend`,
          { params: { period, periods: 6 } }),
      ]);
      setRecords(recRes.data.records   || []);
      setSummary(sumRes.data           || null);
      setTrend(trendRes.data.trend     || []);
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  }, [storeId, period, tierFilter]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleCompute = async () => {
    setComputing(true);
    try {
      const res = await apiClient.post('/api/v1/dish-benchmark/compute',
        null, { params: { period } });
      message.success(
        `对标完成：${res.data.dish_count} 道菜 / ${res.data.store_count} 家门店，` +
        `生成 ${res.data.record_count} 条记录`
      );
      fetchAll();
    } catch (e) { handleApiError(e); }
    finally { setComputing(false); }
  };

  const handleCrossStore = async () => {
    if (!dishName.trim()) { message.warning('请输入菜品名'); return; }
    setCrossLoading(true);
    try {
      const res = await apiClient.get(
        `/api/v1/dish-benchmark/dish/${encodeURIComponent(dishName.trim())}`,
        { params: { period } }
      );
      setCrossStore(res.data.stores || []);
      if ((res.data.stores || []).length === 0) {
        message.info('该菜品暂无跨店对标数据，请先运行对标计算');
      }
    } catch (e) { handleApiError(e); }
    finally { setCrossLoading(false); }
  };

  // ── KPI ───────────────────────────────────────────────────────────────────
  const totalDishes = summary?.total_dishes ?? 0;
  const fcrPotential = summary?.total_fcr_potential ?? 0;
  const gpmPotential = summary?.total_gpm_potential ?? 0;
  const laggardCount = summary?.by_tier.find(t => t.fcr_tier === 'laggard')?.dish_count ?? 0;

  // ── 档位分布饼图 ──────────────────────────────────────────────────────────
  const tierPieOption = () => {
    if (!summary) return {};
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'item', formatter: '{b}: {c}道 ({d}%)' },
      series: [{
        type: 'pie', radius: ['40%', '70%'],
        data: summary.by_tier.map(t => ({
          name: TIER_CONFIG[t.fcr_tier]?.label || t.fcr_tier,
          value: t.dish_count,
          itemStyle: { color: TIER_CONFIG[t.fcr_tier]?.color || '#aaa' },
        })).filter(d => d.value > 0),
        label: { formatter: '{b}\n{c}道' },
      }],
    };
  };

  // ── 趋势折线图 ────────────────────────────────────────────────────────────
  const trendOption = () => ({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['落后菜品数', '标杆菜品数', '平均FCR差距pp'], bottom: 0 },
    grid: { left: 55, right: 50, top: 40, bottom: 55 },
    xAxis: { type: 'category', data: trend.map(t => t.period) },
    yAxis: [
      { type: 'value', name: '道数', min: 0 },
      { type: 'value', name: 'pp差距', min: 0, axisLabel: { formatter: '{value}pp' } },
    ],
    series: [
      {
        name: '落后菜品数', type: 'bar',
        data: trend.map(t => t.laggard_count),
        itemStyle: { color: '#C53030' },
      },
      {
        name: '标杆菜品数', type: 'bar',
        data: trend.map(t => t.top_count),
        itemStyle: { color: '#1A7A52' },
      },
      {
        name: '平均FCR差距pp', type: 'line', smooth: true, yAxisIndex: 1,
        data: trend.map(t => t.avg_fcr_gap.toFixed(1)),
        itemStyle: { color: '#C8923A' },
        lineStyle: { type: 'dashed' },
      },
    ],
  });

  // ── ¥潜力柱图 ─────────────────────────────────────────────────────────────
  const potentialBarOption = () => {
    if (!summary) return {};
    const tiers = summary.by_tier.filter(t => t.dish_count > 0);
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { data: ['FCR¥潜力', 'GPM¥潜力'], bottom: 0 },
      grid: { left: 60, right: 20, top: 30, bottom: 50 },
      xAxis: { type: 'category', data: tiers.map(t => TIER_CONFIG[t.fcr_tier]?.label || t.fcr_tier) },
      yAxis: { type: 'value', name: '¥' },
      series: [
        {
          name: 'FCR¥潜力', type: 'bar',
          data: tiers.map(t => ({ value: t.fcr_yuan_potential.toFixed(0),
            itemStyle: { color: TIER_CONFIG[t.fcr_tier]?.color || '#aaa' } })),
        },
        {
          name: 'GPM¥潜力', type: 'bar',
          data: tiers.map(t => t.gpm_yuan_potential.toFixed(0)),
          itemStyle: { color: '#aaa' },
        },
      ],
    };
  };

  // ── 对标列表列 ────────────────────────────────────────────────────────────
  const columns = [
    {
      title: '菜品', dataIndex: 'dish_name', width: 130,
      render: (n: string) => <Text strong>{n}</Text>,
    },
    {
      title: 'FCR档位', dataIndex: 'fcr_tier', width: 90,
      render: (t: string) => {
        const cfg = TIER_CONFIG[t] || { label: t, antColor: 'default' };
        return <Tag color={cfg.antColor}>{cfg.label}</Tag>;
      },
    },
    {
      title: '本店FCR%', dataIndex: 'food_cost_rate', width: 95,
      render: (v: number) => fmtPct(v),
      sorter: (a: BenchRecord, b: BenchRecord) => a.food_cost_rate - b.food_cost_rate,
    },
    {
      title: '最优FCR%', dataIndex: 'best_fcr_value', width: 95,
      render: (v: number, r: BenchRecord) => (
        <Space size={2}>
          <Text style={{ color: '#389e0d' }}>{fmtPct(v)}</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>({r.best_fcr_store_id})</Text>
        </Space>
      ),
    },
    {
      title: 'FCR差距', dataIndex: 'fcr_gap_pp', width: 85,
      render: (v: number) => v > 0
        ? <Text style={{ color: '#C53030' }}>+{v.toFixed(1)}pp</Text>
        : <Text style={{ color: '#389e0d' }}>-</Text>,
      sorter: (a: BenchRecord, b: BenchRecord) => b.fcr_gap_pp - a.fcr_gap_pp,
    },
    {
      title: 'FCR¥潜力', dataIndex: 'fcr_gap_yuan_impact', width: 95,
      render: (v: number) => v > 0
        ? <Text style={{ color: '#C53030' }}>{fmt(v)}</Text>
        : <Text type="secondary">-</Text>,
      sorter: (a: BenchRecord, b: BenchRecord) =>
        b.fcr_gap_yuan_impact - a.fcr_gap_yuan_impact,
      defaultSortOrder: 'descend' as const,
    },
    {
      title: '本店GPM%', dataIndex: 'gross_profit_margin', width: 95,
      render: (v: number) => fmtPct(v),
    },
    {
      title: 'GPM差距', dataIndex: 'gpm_gap_pp', width: 85,
      render: (v: number) => v > 0
        ? <Text style={{ color: '#C8923A' }}>-{v.toFixed(1)}pp</Text>
        : <Text style={{ color: '#389e0d' }}>-</Text>,
    },
    {
      title: '参与门店数', dataIndex: 'store_count', width: 90,
      render: (v: number) => `${v}家`,
    },
  ];

  // ── 跨店横比列 ────────────────────────────────────────────────────────────
  const crossColumns = [
    { title: '门店', dataIndex: 'store_id', width: 90 },
    {
      title: 'FCR档位', dataIndex: 'fcr_tier', width: 85,
      render: (t: string) => {
        const cfg = TIER_CONFIG[t] || { label: t, antColor: 'default' };
        return <Tag color={cfg.antColor}>{cfg.label}</Tag>;
      },
    },
    {
      title: 'FCR排名', dataIndex: 'fcr_rank', width: 75,
      render: (v: number, r: CrossStoreRow) => (
        <Text strong style={{ color: v === 1 ? '#389e0d' : undefined }}>
          {v === 1 ? '🥇 ' : ''}{v}/{r.store_count}
        </Text>
      ),
    },
    { title: 'FCR%', dataIndex: 'food_cost_rate', render: (v: number) => fmtPct(v) },
    {
      title: 'FCR¥潜力', dataIndex: 'fcr_gap_yuan_impact',
      render: (v: number) => v > 0
        ? <Text style={{ color: '#C53030' }}>{fmt(v)}</Text>
        : <Text type="secondary" style={{ color: '#389e0d' }}>最优</Text>,
    },
    {
      title: 'GPM排名', dataIndex: 'gpm_rank', width: 75,
      render: (v: number, r: CrossStoreRow) => (
        <Text strong style={{ color: v === 1 ? '#389e0d' : undefined }}>
          {v === 1 ? '🥇 ' : ''}{v}/{r.store_count}
        </Text>
      ),
    },
    { title: 'GPM%', dataIndex: 'gross_profit_margin', render: (v: number) => fmtPct(v) },
    { title: '销量', dataIndex: 'order_count', render: (v: number) => `${v}单` },
    { title: '营收', dataIndex: 'revenue_yuan', render: (v: number) => fmt(v) },
  ];

  const periodOptions = Array.from({ length: 12 }, (_, i) =>
    dayjs().subtract(i + 1, 'month').format('YYYY-MM')
  );

  return (
    <div className={styles.page}>
      {/* ── 顶部控制 ─────────────────────────────────────────────────────── */}
      <div className={styles.header}>
        <Title level={4} style={{ margin: 0 }}>
          <TrophyOutlined /> 跨店菜品对标
        </Title>
        <Space>
          <Select value={storeId} onChange={setStoreId} style={{ width: 120 }}>
            {storeOptions.map(s => <Option key={s} value={s}>{s}</Option>)}
          </Select>
          <Select value={period} onChange={setPeriod} style={{ width: 120 }}>
            {periodOptions.map(p => <Option key={p} value={p}>{p}</Option>)}
          </Select>
          <Tooltip title="跨全链对标计算（全量），按菜品名聚合所有门店数据">
            <Button type="primary" icon={<SyncOutlined spin={computing} />}
              onClick={handleCompute} loading={computing}>
              运行对标
            </Button>
          </Tooltip>
        </Space>
      </div>

      {/* ── KPI 卡片 ─────────────────────────────────────────────────────── */}
      <Row gutter={[16, 16]}>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="对标菜品数" value={totalDishes} suffix="道"
              prefix={<BarChartOutlined />} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="落后档菜品" value={laggardCount} suffix="道"
              prefix={<WarningOutlined />} valueStyle={{ color: '#C53030' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="FCR¥改进潜力" value={fcrPotential.toFixed(0)}
              prefix="¥" valueStyle={{ color: '#C53030' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="GPM¥改进潜力" value={gpmPotential.toFixed(0)}
              prefix="¥" valueStyle={{ color: '#C8923A' }} />
          </Card>
        </Col>
      </Row>

      {/* ── 主内容 ───────────────────────────────────────────────────────── */}
      <Card bodyStyle={{ padding: '0 16px 16px' }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
          {
            key: 'ranking',
            label: <span><TrophyOutlined /> 对标排行</span>,
            children: (
              <Spin spinning={loading}>
                <Space style={{ marginBottom: 12 }}>
                  <Select value={tierFilter} onChange={setTierFilter}
                    style={{ width: 110 }} allowClear placeholder="FCR档位">
                    <Option value="top">🟢 标杆</Option>
                    <Option value="above_avg">🔵 良好</Option>
                    <Option value="below_avg">🟠 待改进</Option>
                    <Option value="laggard">🔴 落后</Option>
                  </Select>
                </Space>
                {records.length === 0 ? (
                  <Empty description="暂无对标数据，请先点击「运行对标」" />
                ) : (
                  <Table
                    dataSource={records}
                    columns={columns}
                    rowKey="id"
                    size="small"
                    pagination={{ pageSize: 20, showSizeChanger: true }}
                    scroll={{ x: 950 }}
                    rowClassName={(r) =>
                      r.fcr_tier === 'laggard' ? styles.rowLaggard : ''
                    }
                  />
                )}
              </Spin>
            ),
          },
          {
            key: 'laggard',
            label: <span><FallOutlined /> 落后菜品</span>,
            children: (
              <Spin spinning={loading}>
                {records.filter(r => r.fcr_tier === 'laggard').length === 0 ? (
                  <Empty description="本期无落后档菜品" />
                ) : (
                  <Table
                    dataSource={records.filter(r => r.fcr_tier === 'laggard')}
                    columns={columns}
                    rowKey="id"
                    size="small"
                    pagination={false}
                    scroll={{ x: 950 }}
                    rowClassName={() => styles.rowLaggard}
                    title={() => (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        FCR落后档（percentile &lt; 25%）菜品，按¥改进潜力排序——优先解决高价值差距
                      </Text>
                    )}
                  />
                )}
              </Spin>
            ),
          },
          {
            key: 'cross',
            label: <span><SearchOutlined /> 菜品横比</span>,
            children: (
              <div>
                <Space style={{ marginBottom: 12 }}>
                  <Input
                    value={dishName}
                    onChange={e => setDishName(e.target.value)}
                    onPressEnter={handleCrossStore}
                    placeholder="输入菜品名（如：宫保鸡丁）"
                    style={{ width: 220 }}
                    prefix={<SearchOutlined />}
                  />
                  <Button onClick={handleCrossStore} loading={crossLoading}>
                    查询跨店对比
                  </Button>
                </Space>
                <Spin spinning={crossLoading}>
                  {crossStore.length === 0 ? (
                    <Empty description="输入菜品名后点击查询" />
                  ) : (
                    <Table
                      dataSource={crossStore}
                      columns={crossColumns}
                      rowKey="store_id"
                      size="small"
                      pagination={false}
                      scroll={{ x: 750 }}
                      rowClassName={(r) =>
                        r.fcr_rank === 1 ? styles.bestStore : ''
                      }
                      title={() => (
                        <Text strong>
                          「{dishName}」{period} 跨店对比（共 {crossStore[0]?.store_count || 0} 家门店）
                        </Text>
                      )}
                    />
                  )}
                </Spin>
              </div>
            ),
          },
          {
            key: 'trend',
            label: <span><LineChartOutlined /> 改进趋势</span>,
            children: (
              <Spin spinning={loading}>
                {trend.length === 0 ? (
                  <Empty description="暂无趋势数据" />
                ) : (
                  <Row gutter={16}>
                    <Col xs={24} lg={16}>
                      <Text strong style={{ display: 'block', marginBottom: 8 }}>
                        近6期落后/标杆菜品数 + 平均FCR差距趋势
                      </Text>
                      <ReactECharts option={trendOption()} style={{ height: 320 }} notMerge />
                    </Col>
                    <Col xs={24} lg={8}>
                      <Text strong style={{ display: 'block', marginBottom: 8 }}>
                        当期FCR档位分布
                      </Text>
                      <ReactECharts option={tierPieOption()} style={{ height: 200 }} notMerge />
                      <Text strong style={{ display: 'block', margin: '12px 0 8px' }}>
                        各档位¥改进潜力
                      </Text>
                      <ReactECharts option={potentialBarOption()} style={{ height: 180 }} notMerge />
                    </Col>
                  </Row>
                )}
              </Spin>
            ),
          },
        ]} />
      </Card>
    </div>
  );
};

export default DishBenchmarkPage;
