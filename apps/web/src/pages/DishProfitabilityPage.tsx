/**
 * 菜品盈利能力分析引擎 — Phase 6 Month 1
 * BCG四象限菜单工程：人气 × 盈利双轴定位
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Row, Col, Card, Statistic, Select, Button, Table, Tag, Tabs, Spin,
  Typography, Space, Tooltip, message, Empty,
} from 'antd';
import {
  StarOutlined, FireOutlined, DollarOutlined, BarChartOutlined,
  SyncOutlined, PieChartOutlined, LineChartOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { apiClient, handleApiError } from '../services/api';
import styles from './DishProfitabilityPage.module.css';

const { Title, Text } = Typography;
const { Option } = Select;

// ── BCG 常量 ─────────────────────────────────────────────────────────────────
const BCG_CONFIG = {
  star:          { label: '明星菜', color: '#faad14', bg: '#fffbe6', icon: '⭐' },
  cash_cow:      { label: '现金牛', color: '#1A7A52', bg: 'rgba(26,122,82,0.08)', icon: '🐄' },
  question_mark: { label: '问题菜', color: '#0AAF9A', bg: '#e6f4ff', icon: '❓' },
  dog:           { label: '瘦狗菜', color: '#C53030', bg: '#fff2f0', icon: '🐶' },
} as const;

type BcgKey = keyof typeof BCG_CONFIG;
const BCG_QUADRANTS = Object.keys(BCG_CONFIG) as BcgKey[];

// ── 类型 ──────────────────────────────────────────────────────────────────────
interface Dish {
  dish_id: string;
  dish_name: string;
  category: string;
  order_count: number;
  avg_selling_price: number;
  revenue_yuan: number;
  food_cost_yuan: number;
  food_cost_rate: number;
  gross_profit_yuan: number;
  gross_profit_margin: number;
  popularity_rank: number;
  profitability_rank: number;
  popularity_percentile: number;
  profit_percentile: number;
  bcg_quadrant: BcgKey;
  bcg_label: string;
}

interface BcgQuadrantStat {
  quadrant: BcgKey;
  dish_count: number;
  total_revenue: number;
  total_gross_profit: number;
  avg_gpm: number;
  avg_fcr: number;
  revenue_share_pct: number;
}

interface CategoryStat {
  category: string;
  dish_count: number;
  total_orders: number;
  total_revenue: number;
  total_gross_profit: number;
  avg_gpm: number;
  avg_fcr: number;
}

interface TrendPoint {
  period: string;
  order_count: number;
  revenue_yuan: number;
  food_cost_rate: number;
  gross_profit_yuan: number;
  gross_profit_margin: number;
  bcg_quadrant: BcgKey;
  popularity_rank: number;
  profitability_rank: number;
}

// ── 辅助函数 ──────────────────────────────────────────────────────────────────
const fmt = (n: number) => `¥${n.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}`;
const fmtPct = (n: number) => `${n.toFixed(1)}%`;

// ── 主页面 ────────────────────────────────────────────────────────────────────
const DishProfitabilityPage: React.FC = () => {
  const [storeId,      setStoreId]      = useState(localStorage.getItem('store_id') || '');
  const [storeOptions, setStoreOptions] = useState<string[]>([]);

  useEffect(() => {
    apiClient.get<{ items: Array<{ id: string }> }>('/api/v1/stores?limit=50')
      .then(data => {
        const ids = (data.items ?? []).map((s: { id: string }) => s.id).filter(Boolean);
        if (ids.length > 0) setStoreOptions(ids);
      })
      .catch(() => { /* 保持默认 */ });
  }, []);
  const [period, setPeriod]   = useState(dayjs().subtract(1, 'month').format('YYYY-MM'));
  const [computing, setComputing]   = useState(false);
  const [loading, setLoading]       = useState(false);
  const [dishes, setDishes]         = useState<Dish[]>([]);
  const [bcgSummary, setBcgSummary] = useState<BcgQuadrantStat[]>([]);
  const [categories, setCategories] = useState<CategoryStat[]>([]);
  const [topDishes, setTopDishes]   = useState<Dish[]>([]);
  const [trend, setTrend]           = useState<TrendPoint[]>([]);
  const [selectedDish, setSelectedDish] = useState<string | null>(null);
  const [activeTab, setActiveTab]   = useState('bcg');

  // ── 数据拉取 ─────────────────────────────────────────────────────────────
  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [dishRes, bcgRes, catRes, topRes] = await Promise.all([
        apiClient.get(`/api/v1/dish-profit/${storeId}`, { params: { period, limit: 200 } }),
        apiClient.get(`/api/v1/dish-profit/bcg/${storeId}`, { params: { period } }),
        apiClient.get(`/api/v1/dish-profit/category/${storeId}`, { params: { period } }),
        apiClient.get(`/api/v1/dish-profit/top/${storeId}`, { params: { period, metric: 'gross_profit_yuan', limit: 10 } }),
      ]);
      setDishes(dishRes.data.dishes || []);
      setBcgSummary(bcgRes.data.by_quadrant || []);
      setCategories(catRes.data.categories || []);
      setTopDishes(topRes.data.dishes || []);
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  }, [storeId, period]);

  const fetchTrend = useCallback(async (dishId: string) => {
    try {
      const res = await apiClient.get(`/api/v1/dish-profit/trend/${storeId}/${dishId}`, { params: { periods: 6 } });
      setTrend(res.data.trend || []);
    } catch (e) {
      handleApiError(e);
    }
  }, [storeId]);

  useEffect(() => { fetchAll(); }, [fetchAll]);
  useEffect(() => {
    if (selectedDish) fetchTrend(selectedDish);
  }, [selectedDish, fetchTrend]);

  // ── 触发计算 ──────────────────────────────────────────────────────────────
  const handleCompute = async () => {
    setComputing(true);
    try {
      const res = await apiClient.post(`/api/v1/dish-profit/compute/${storeId}`, null, { params: { period } });
      message.success(`计算完成：${res.data.dish_count} 道菜品`);
      fetchAll();
    } catch (e) {
      handleApiError(e);
    } finally {
      setComputing(false);
    }
  };

  // ── KPI 汇总 ──────────────────────────────────────────────────────────────
  const starCount   = dishes.filter(d => d.bcg_quadrant === 'star').length;
  const avgFcr      = dishes.length ? dishes.reduce((s, d) => s + d.food_cost_rate, 0) / dishes.length : 0;
  const topByProfit = [...dishes].sort((a, b) => b.gross_profit_yuan - a.gross_profit_yuan)[0];

  // ── BCG 散点图 ────────────────────────────────────────────────────────────
  const scatterOption = () => {
    const seriesMap: Record<BcgKey, { name: string; color: string; data: [number, number, string, string][] }> = {
      star:          { name: '⭐明星菜', color: '#faad14', data: [] },
      cash_cow:      { name: '🐄现金牛', color: '#1A7A52', data: [] },
      question_mark: { name: '❓问题菜', color: '#0AAF9A', data: [] },
      dog:           { name: '🐶瘦狗菜', color: '#C53030', data: [] },
    };
    dishes.forEach(d => {
      seriesMap[d.bcg_quadrant]?.data.push([
        d.popularity_percentile,
        d.profit_percentile,
        d.dish_name,
        `销量${d.order_count} | 毛利${fmtPct(d.gross_profit_margin)} | 食材成本率${fmtPct(d.food_cost_rate)}`,
      ]);
    });

    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'item',
        formatter: (p: any) => `<b>${p.data[2]}</b><br/>${p.data[3]}`,
      },
      legend: { data: BCG_QUADRANTS.map(k => seriesMap[k].name), bottom: 0 },
      grid: { left: 60, right: 20, top: 40, bottom: 60 },
      xAxis: {
        type: 'value', min: 0, max: 100, name: '人气百分位 →', nameLocation: 'end',
        splitLine: { lineStyle: { type: 'dashed', opacity: 0.4 } },
        axisLabel: { formatter: '{value}%' },
      },
      yAxis: {
        type: 'value', min: 0, max: 100, name: '↑ 毛利百分位', nameLocation: 'end',
        splitLine: { lineStyle: { type: 'dashed', opacity: 0.4 } },
        axisLabel: { formatter: '{value}%' },
      },
      // 四象限分隔线
      markLine: undefined,
      series: [
        // 分隔线（两条 markLine 用虚拟 scatter 实现）
        ...BCG_QUADRANTS.map(k => ({
          name: seriesMap[k].name,
          type: 'scatter',
          symbolSize: (val: any) => Math.max(8, Math.min(24, val[0] / 5 + 8)),
          data: seriesMap[k].data,
          itemStyle: { color: seriesMap[k].color, opacity: 0.85 },
        })),
        // 中线标记
        {
          name: '_divider_x',
          type: 'line',
          data: [[50, 0], [50, 100]],
          lineStyle: { color: '#aaa', type: 'dashed', width: 1 },
          symbol: 'none',
          tooltip: { show: false },
          legendHoverLink: false,
          silent: true,
        } as any,
        {
          name: '_divider_y',
          type: 'line',
          data: [[0, 50], [100, 50]],
          lineStyle: { color: '#aaa', type: 'dashed', width: 1 },
          symbol: 'none',
          tooltip: { show: false },
          legendHoverLink: false,
          silent: true,
        } as any,
      ],
    };
  };

  // ── 趋势图 ────────────────────────────────────────────────────────────────
  const trendOption = () => ({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['毛利率%', '食材成本率%', '销量'], bottom: 0 },
    grid: { left: 50, right: 50, top: 40, bottom: 60 },
    xAxis: { type: 'category', data: trend.map(t => t.period), axisLabel: { rotate: 30 } },
    yAxis: [
      { type: 'value', name: '%', min: 0, max: 100 },
      { type: 'value', name: '销量', splitLine: { show: false } },
    ],
    series: [
      { name: '毛利率%',    type: 'line', data: trend.map(t => t.gross_profit_margin.toFixed(1)), smooth: true, itemStyle: { color: '#1A7A52' } },
      { name: '食材成本率%', type: 'line', data: trend.map(t => t.food_cost_rate.toFixed(1)),      smooth: true, itemStyle: { color: '#C53030' } },
      { name: '销量',       type: 'bar',  data: trend.map(t => t.order_count), yAxisIndex: 1, itemStyle: { color: '#0AAF9A', opacity: 0.6 } },
    ],
  });

  // ── 分类饼图 ──────────────────────────────────────────────────────────────
  const categoryPieOption = () => ({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', formatter: '{b}: {d}%' },
    series: [{
      type: 'pie', radius: ['40%', '70%'], center: ['50%', '50%'],
      data: categories.map(c => ({ name: c.category, value: c.total_revenue.toFixed(0) })),
      label: { formatter: '{b}\n{d}%' },
    }],
  });

  // ── 菜品列表列定义 ────────────────────────────────────────────────────────
  const dishColumns = [
    { title: '排名', dataIndex: 'popularity_rank', width: 60, sorter: (a: Dish, b: Dish) => a.popularity_rank - b.popularity_rank },
    { title: '菜品', dataIndex: 'dish_name', render: (n: string, r: Dish) => (
      <Space>
        <span>{n}</span>
        <Tag color={BCG_CONFIG[r.bcg_quadrant].color}>{r.bcg_label}</Tag>
      </Space>
    )},
    { title: '分类', dataIndex: 'category', width: 80 },
    { title: '销量', dataIndex: 'order_count', width: 70, sorter: (a: Dish, b: Dish) => a.order_count - b.order_count },
    { title: '均价', dataIndex: 'avg_selling_price', width: 70, render: (v: number) => `¥${v.toFixed(1)}` },
    { title: '收入', dataIndex: 'revenue_yuan', width: 90, sorter: (a: Dish, b: Dish) => a.revenue_yuan - b.revenue_yuan, render: (v: number) => fmt(v) },
    { title: '食材成本率', dataIndex: 'food_cost_rate', width: 100, sorter: (a: Dish, b: Dish) => a.food_cost_rate - b.food_cost_rate, render: (v: number) => (
      <Text type={v > 45 ? 'danger' : v > 35 ? 'warning' : 'success'}>{fmtPct(v)}</Text>
    )},
    { title: '毛利率', dataIndex: 'gross_profit_margin', width: 80, sorter: (a: Dish, b: Dish) => a.gross_profit_margin - b.gross_profit_margin, render: (v: number) => (
      <Text type={v >= 60 ? 'success' : v >= 40 ? 'warning' : 'danger'}>{fmtPct(v)}</Text>
    )},
    { title: '毛利额', dataIndex: 'gross_profit_yuan', width: 90, sorter: (a: Dish, b: Dish) => a.gross_profit_yuan - b.gross_profit_yuan, render: (v: number) => fmt(v) },
    {
      title: '操作', width: 80,
      render: (_: any, r: Dish) => (
        <Button size="small" type="link" onClick={() => { setSelectedDish(r.dish_id); setActiveTab('trend'); }}>
          趋势
        </Button>
      ),
    },
  ];

  // ── BCG汇总列 ─────────────────────────────────────────────────────────────
  const bcgColumns = [
    { title: '象限', dataIndex: 'quadrant', render: (q: BcgKey) => (
      <Space>
        <span>{BCG_CONFIG[q].icon}</span>
        <Tag color={BCG_CONFIG[q].color}>{BCG_CONFIG[q].label}</Tag>
      </Space>
    )},
    { title: '菜品数', dataIndex: 'dish_count', width: 80 },
    { title: '总收入', dataIndex: 'total_revenue', render: (v: number) => fmt(v) },
    { title: '总毛利', dataIndex: 'total_gross_profit', render: (v: number) => fmt(v) },
    { title: '均毛利率', dataIndex: 'avg_gpm', render: (v: number) => fmtPct(v) },
    { title: '均食材成本率', dataIndex: 'avg_fcr', render: (v: number) => fmtPct(v) },
    { title: '收入占比', dataIndex: 'revenue_share_pct', render: (v: number) => (
      <div className={styles.shareBar}>
        <div className={styles.shareBarFill} style={{ width: `${v}%` }} />
        <span>{fmtPct(v)}</span>
      </div>
    )},
  ];

  // ── 分类汇总列 ────────────────────────────────────────────────────────────
  const catColumns = [
    { title: '分类',      dataIndex: 'category' },
    { title: '菜品数',    dataIndex: 'dish_count', width: 80 },
    { title: '总销量',    dataIndex: 'total_orders', width: 80 },
    { title: '总收入',    dataIndex: 'total_revenue',      render: (v: number) => fmt(v) },
    { title: '总毛利',    dataIndex: 'total_gross_profit', render: (v: number) => fmt(v) },
    { title: '均毛利率',  dataIndex: 'avg_gpm', render: (v: number) => fmtPct(v) },
    { title: '均食材成本率', dataIndex: 'avg_fcr', render: (v: number) => fmtPct(v) },
  ];

  // ── 月份选项 ──────────────────────────────────────────────────────────────
  const periodOptions = Array.from({ length: 12 }, (_, i) =>
    dayjs().subtract(i + 1, 'month').format('YYYY-MM')
  );

  return (
    <div className={styles.page}>
      {/* ── 顶部控制 ──────────────────────────────────────────────────────── */}
      <div className={styles.header}>
        <Title level={4} style={{ margin: 0 }}>
          <PieChartOutlined /> 菜品盈利能力分析
        </Title>
        <Space>
          <Select value={storeId} onChange={setStoreId} style={{ width: 120 }}>
            {storeOptions.map(s => <Option key={s} value={s}>{s}</Option>)}
          </Select>
          <Select value={period} onChange={setPeriod} style={{ width: 120 }}>
            {periodOptions.map(p => <Option key={p} value={p}>{p}</Option>)}
          </Select>
          <Tooltip title="重新聚合当期菜品销售数据，计算BCG四象限">
            <Button
              type="primary"
              icon={<SyncOutlined spin={computing} />}
              onClick={handleCompute}
              loading={computing}
            >
              重新计算
            </Button>
          </Tooltip>
        </Space>
      </div>

      {/* ── KPI 卡片 ──────────────────────────────────────────────────────── */}
      <Row gutter={[16, 16]} className={styles.kpiRow}>
        <Col xs={12} sm={6}>
          <Card size="small" className={styles.kpiCard}>
            <Statistic
              title="菜品总数"
              value={dishes.length}
              suffix="道"
              prefix={<BarChartOutlined />}
              valueStyle={{ color: '#0AAF9A' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" className={styles.kpiCard}>
            <Statistic
              title="明星菜"
              value={starCount}
              suffix={`/ ${dishes.length}`}
              prefix={<StarOutlined />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" className={styles.kpiCard}>
            <Statistic
              title="平均食材成本率"
              value={avgFcr.toFixed(1)}
              suffix="%"
              prefix={<FireOutlined />}
              valueStyle={{ color: avgFcr > 40 ? '#C53030' : '#1A7A52' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" className={styles.kpiCard}>
            <Statistic
              title="最高毛利菜品"
              value={topByProfit?.dish_name ?? '—'}
              prefix={<DollarOutlined />}
              valueStyle={{ color: '#1A7A52', fontSize: 16 }}
              suffix={topByProfit ? fmt(topByProfit.gross_profit_yuan) : ''}
            />
          </Card>
        </Col>
      </Row>

      {/* ── 主内容 Tabs ───────────────────────────────────────────────────── */}
      <Card bodyStyle={{ padding: '0 16px 16px' }}>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'bcg',
              label: <span><PieChartOutlined /> BCG四象限</span>,
              children: (
                <Spin spinning={loading}>
                  {dishes.length === 0 ? (
                    <Empty description="暂无数据，请先点击「重新计算」" />
                  ) : (
                    <Row gutter={16}>
                      <Col xs={24} lg={16}>
                        <ReactECharts
                          option={scatterOption()}
                          style={{ height: 420 }}
                          notMerge
                        />
                        <div className={styles.quadrantHints}>
                          {BCG_QUADRANTS.map(q => (
                            <div key={q} className={styles.quadrantHint}
                              style={{ borderColor: BCG_CONFIG[q].color, background: BCG_CONFIG[q].bg }}>
                              <span style={{ color: BCG_CONFIG[q].color, fontWeight: 600 }}>
                                {BCG_CONFIG[q].icon} {BCG_CONFIG[q].label}
                              </span>
                              <Text type="secondary" style={{ fontSize: 11 }}>
                                {q === 'star'          && '人气高 × 毛利高 → 重点推广'}
                                {q === 'cash_cow'      && '人气高 × 毛利低 → 优化成本'}
                                {q === 'question_mark' && '人气低 × 毛利高 → 加强营销'}
                                {q === 'dog'           && '人气低 × 毛利低 → 考虑下架'}
                              </Text>
                            </div>
                          ))}
                        </div>
                      </Col>
                      <Col xs={24} lg={8}>
                        <Table
                          dataSource={bcgSummary}
                          columns={bcgColumns}
                          rowKey="quadrant"
                          size="small"
                          pagination={false}
                          scroll={{ x: 300 }}
                        />
                      </Col>
                    </Row>
                  )}
                </Spin>
              ),
            },
            {
              key: 'list',
              label: <span><BarChartOutlined /> 菜品明细</span>,
              children: (
                <Spin spinning={loading}>
                  <Table
                    dataSource={dishes}
                    columns={dishColumns}
                    rowKey="dish_id"
                    size="small"
                    pagination={{ pageSize: 20, showSizeChanger: true }}
                    scroll={{ x: 900 }}
                  />
                </Spin>
              ),
            },
            {
              key: 'top',
              label: <span><StarOutlined /> Top菜品</span>,
              children: (
                <Spin spinning={loading}>
                  {topDishes.length === 0 ? <Empty /> : (
                    <Row gutter={16}>
                      <Col xs={24} lg={12}>
                        <ReactECharts
                          option={{
                            backgroundColor: 'transparent',
                            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
                            grid: { left: 120, right: 20, top: 20, bottom: 40 },
                            xAxis: { type: 'value', axisLabel: { formatter: (v: number) => fmt(v) } },
                            yAxis: { type: 'category', data: [...topDishes].reverse().map(d => d.dish_name) },
                            series: [{
                              type: 'bar',
                              data: [...topDishes].reverse().map(d => ({
                                value: d.gross_profit_yuan,
                                itemStyle: { color: BCG_CONFIG[d.bcg_quadrant].color },
                              })),
                              label: { show: true, position: 'right', formatter: (p: any) => fmt(p.value) },
                            }],
                          }}
                          style={{ height: 360 }}
                          notMerge
                        />
                      </Col>
                      <Col xs={24} lg={12}>
                        <Table
                          dataSource={topDishes}
                          columns={[
                            { title: '菜品', dataIndex: 'dish_name', render: (n: string, r: Dish) => (
                              <Space>
                                <Tag color={BCG_CONFIG[r.bcg_quadrant].color}>{BCG_CONFIG[r.bcg_quadrant].icon}</Tag>
                                {n}
                              </Space>
                            )},
                            { title: '毛利额', dataIndex: 'gross_profit_yuan', render: fmt },
                            { title: '毛利率', dataIndex: 'gross_profit_margin', render: fmtPct },
                            { title: '食材成本率', dataIndex: 'food_cost_rate', render: (v: number) => (
                              <Text type={v > 45 ? 'danger' : 'success'}>{fmtPct(v)}</Text>
                            )},
                          ]}
                          rowKey="dish_id"
                          size="small"
                          pagination={false}
                        />
                      </Col>
                    </Row>
                  )}
                </Spin>
              ),
            },
            {
              key: 'category',
              label: <span><PieChartOutlined /> 分类汇总</span>,
              children: (
                <Spin spinning={loading}>
                  {categories.length === 0 ? <Empty /> : (
                    <Row gutter={16}>
                      <Col xs={24} lg={8}>
                        <ReactECharts
                          option={categoryPieOption()}
                          style={{ height: 300 }}
                          notMerge
                        />
                      </Col>
                      <Col xs={24} lg={16}>
                        <Table
                          dataSource={categories}
                          columns={catColumns}
                          rowKey="category"
                          size="small"
                          pagination={false}
                        />
                      </Col>
                    </Row>
                  )}
                </Spin>
              ),
            },
            {
              key: 'trend',
              label: <span><LineChartOutlined /> 菜品趋势</span>,
              children: (
                <div>
                  <Space style={{ marginBottom: 12 }}>
                    <Text>选择菜品：</Text>
                    <Select
                      showSearch
                      placeholder="搜索菜品..."
                      value={selectedDish}
                      onChange={v => setSelectedDish(v)}
                      style={{ width: 200 }}
                      optionFilterProp="label"
                      options={dishes.map(d => ({ value: d.dish_id, label: d.dish_name }))}
                    />
                  </Space>
                  {!selectedDish ? (
                    <Empty description="请先选择一道菜品" />
                  ) : trend.length === 0 ? (
                    <Empty description="该菜品暂无历史趋势数据" />
                  ) : (
                    <ReactECharts
                      option={trendOption()}
                      style={{ height: 360 }}
                      notMerge
                    />
                  )}
                </div>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
};

export default DishProfitabilityPage;
