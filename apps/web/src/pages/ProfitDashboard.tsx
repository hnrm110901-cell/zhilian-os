import React, { useState, useEffect, useCallback } from 'react';
import { DatePicker } from 'antd';
import {
  ReloadOutlined, RiseOutlined, FallOutlined,
  DollarOutlined, WarningOutlined, CheckCircleOutlined,
} from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZSelect, ZTable, ZTabs, ZEmpty,
} from '../design-system/components';
import type { ZTableColumn } from '../design-system/components/ZTable';
import styles from './ProfitDashboard.module.css';

// ── 类型定义 ──────────────────────────────────────────────────────────────────

interface StoreRankingItem {
  store_id:         string;
  store_name:       string;
  actual_cost_pct:  number;
  theoretical_pct:  number;
  variance_pct:     number;
  variance_status:  'ok' | 'warning' | 'critical';
  actual_cost_yuan: number;
  revenue_yuan:     number;
  top_ingredients:  { name: string; cost_yuan: number }[];
}

interface RankingResponse {
  stores:     StoreRankingItem[];
  summary:    { store_count: number; avg_actual_cost_pct: number; over_budget_count: number };
  start_date: string;
  end_date:   string;
}

interface MonthlyReport {
  store_id:           string;
  period_label:       string;
  executive_summary:  {
    headline:              string;
    revenue_yuan:          number;
    actual_cost_pct:       number;
    cost_rate_status:      string;
    waste_cost_yuan:       number;
    decision_adoption_pct: number;
    total_saving_yuan:     number;
  };
  weekly_trend_chart: {
    x_axis:         string[];
    cost_rate_data: number[];
    revenue_data:   number[];
    point_colors:   string[];
  };
}

interface VarianceIngredient {
  item_id:         string;
  name:            string;
  usage_cost_fen:  number;
  usage_cost_yuan: number;
}

interface VarianceDetail {
  store_id:         string;
  start_date:       string;
  end_date:         string;
  actual_cost_fen:  number;
  actual_cost_yuan: number;
  revenue_yuan:     number;
  actual_cost_pct:  number;
  theoretical_pct:  number;
  variance_pct:     number;
  variance_status:  string;
  top_ingredients:  VarianceIngredient[];
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────

const statusColor = (s: string) =>
  s === 'critical' ? '#C53030' : s === 'warning' ? '#faad14' : '#1A7A52';

const statusBadgeType = (s: string): 'success' | 'warning' | 'critical' | 'default' =>
  s === 'critical' ? 'critical' : s === 'warning' ? 'warning' : s === 'ok' ? 'success' : 'default';

const statusBadgeText = (s: string) =>
  s === 'ok' ? '正常' : s === 'warning' ? '偏高' : s === 'critical' ? '超标' : s;

// ── 食材明细列（外部定义，稳定引用） ─────────────────────────────────────────

const ingredientColumns: ZTableColumn<any>[] = [
  {
    key: 'rank',
    title: '#',
    width: 56,
    align: 'center',
    render: (rank: number) => (
      <span style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 28, height: 28, borderRadius: '50%',
        background: rank <= 3 ? '#0AAF9A' : '#d9d9d9',
        color: rank <= 3 ? '#fff' : '#666',
        fontWeight: 700, fontSize: 13,
      }}>
        {rank}
      </span>
    ),
  },
  {
    key: 'name',
    title: '食材名称',
    render: (name: string) => <strong>{name}</strong>,
  },
  {
    key: 'usage_cost_yuan',
    title: '用料成本',
    align: 'right',
    render: (yuan: number) => (
      <strong style={{ color: '#0AAF9A' }}>
        ¥{yuan?.toLocaleString('zh-CN', { minimumFractionDigits: 0 })}
      </strong>
    ),
  },
  {
    key: 'cost_share_pct',
    title: '占实际成本',
    width: 150,
    render: (pct: number) => {
      const color = pct >= 20 ? '#C53030' : pct >= 10 ? '#faad14' : '#0AAF9A';
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 90, height: 5, background: '#f0f0f0', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{ width: `${Math.min(100, pct)}%`, height: '100%', background: color, borderRadius: 3 }} />
          </div>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{pct?.toFixed(1)}%</span>
        </div>
      );
    },
  },
];

// ════════════════════════════════════════════════════════════════════════════════
// ProfitDashboard — 成本率趋势可视化
// ════════════════════════════════════════════════════════════════════════════════

const ProfitDashboard: React.FC = () => {
  const [loading,         setLoading]         = useState(false);
  const [rankingData,     setRankingData]     = useState<RankingResponse | null>(null);
  const [monthlyReport,   setMonthlyReport]   = useState<MonthlyReport | null>(null);
  const [varianceData,    setVarianceData]    = useState<VarianceDetail | null>(null);
  const [varianceLoading, setVarianceLoading] = useState(false);
  const [selectedStore,   setSelectedStore]   = useState<string>('');
  const [reportLoading,   setReportLoading]   = useState(false);
  const [dateRange,       setDateRange]       = useState<[Dayjs, Dayjs]>([
    dayjs().subtract(30, 'day'), dayjs(),
  ]);
  const [reportMonth, setReportMonth] = useState<Dayjs>(dayjs().subtract(1, 'month'));

  // ── 数据加载 ───────────────────────────────────────────────────────────────

  const loadRanking = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/api/v1/hq/food-cost-ranking', {
        params: {
          start_date: dateRange[0].format('YYYY-MM-DD'),
          end_date:   dateRange[1].format('YYYY-MM-DD'),
        },
      });
      setRankingData(res.data);
      if (res.data?.stores?.length > 0 && !selectedStore) {
        setSelectedStore(res.data.stores[0].store_id);
      }
    } catch (err: any) {
      handleApiError(err, '加载成本排名失败');
    } finally {
      setLoading(false);
    }
  }, [dateRange, selectedStore]);

  const loadMonthlyReport = useCallback(async (storeId: string) => {
    if (!storeId) return;
    setReportLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/reports/monthly/${storeId}`, {
        params: { year: reportMonth.year(), month: reportMonth.month() + 1 },
      });
      setMonthlyReport(res.data);
    } catch (err: any) {
      handleApiError(err, '加载月度报告失败');
    } finally {
      setReportLoading(false);
    }
  }, [reportMonth]);

  const loadVariance = useCallback(async (storeId: string) => {
    if (!storeId) return;
    setVarianceLoading(true);
    try {
      const res = await apiClient.get('/api/v1/hq/food-cost-variance', {
        params: {
          store_id:   storeId,
          start_date: dateRange[0].format('YYYY-MM-DD'),
          end_date:   dateRange[1].format('YYYY-MM-DD'),
        },
      });
      setVarianceData(res.data);
    } catch (err: any) {
      handleApiError(err, '加载食材成本明细失败');
    } finally {
      setVarianceLoading(false);
    }
  }, [dateRange]);

  useEffect(() => { loadRanking(); }, [loadRanking]);
  useEffect(() => { if (selectedStore) loadMonthlyReport(selectedStore); }, [selectedStore, loadMonthlyReport]);
  useEffect(() => { if (selectedStore) loadVariance(selectedStore); }, [selectedStore, loadVariance]);

  // ── 图表配置 ───────────────────────────────────────────────────────────────

  const rankingChartOption = rankingData ? {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any[]) => {
        const store  = params[0]?.name || '';
        const actual = params[0]?.value || 0;
        const theory = params[1]?.value || 0;
        return `${store}<br/>实际: <b>${actual.toFixed(1)}%</b><br/>理论: ${theory.toFixed(1)}%`;
      },
    },
    legend: { data: ['实际成本率', '理论成本率'] },
    xAxis: {
      type: 'category',
      data: rankingData.stores.map(s => s.store_name || s.store_id),
      axisLabel: { rotate: 30, fontSize: 12 },
    },
    yAxis: { type: 'value', name: '成本率 (%)', axisLabel: { formatter: '{value}%' } },
    series: [
      {
        name: '实际成本率',
        type: 'bar',
        data: rankingData.stores.map(s => ({
          value: s.actual_cost_pct,
          itemStyle: { color: statusColor(s.variance_status) },
        })),
        label: { show: true, position: 'top', formatter: '{c}%', fontSize: 11 },
      },
      {
        name: '理论成本率',
        type: 'line',
        data: rankingData.stores.map(s => s.theoretical_pct),
        lineStyle: { color: '#0AAF9A', type: 'dashed' },
        symbol: 'circle', symbolSize: 6,
        itemStyle: { color: '#0AAF9A' },
      },
    ],
  } : {};

  const trendChartOption = monthlyReport?.weekly_trend_chart ? (() => {
    const chart = monthlyReport.weekly_trend_chart;
    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: any[]) => {
          const week    = params[0]?.name || '';
          const costPct = params[0]?.value || 0;
          const revenue = params[1]?.value || 0;
          return `${week}<br/>成本率: <b>${Number(costPct).toFixed(1)}%</b><br/>营业额: ¥${Number(revenue).toLocaleString()}`;
        },
      },
      legend: { data: ['成本率', '营业额'] },
      xAxis:  { type: 'category', data: chart.x_axis },
      yAxis: [
        { type: 'value', name: '成本率 (%)', axisLabel: { formatter: '{value}%' }, splitLine: { lineStyle: { type: 'dashed' } } },
        { type: 'value', name: '营业额 (¥)', axisLabel: { formatter: '¥{value}' }, splitLine: { show: false } },
      ],
      series: [
        {
          name: '成本率', type: 'line', yAxisIndex: 0,
          data: chart.cost_rate_data.map((v: number, i: number) => ({
            value: v, itemStyle: { color: chart.point_colors[i] || '#0AAF9A' },
          })),
          lineStyle: { color: '#0AAF9A', width: 2 },
          areaStyle: { opacity: 0.1 },
          symbol: 'circle', symbolSize: 8,
          markLine: {
            data: [{ yAxis: 35, name: '警戒线', lineStyle: { color: '#faad14', type: 'dashed' } }],
          },
        },
        {
          name: '营业额', type: 'bar', yAxisIndex: 1,
          data: chart.revenue_data,
          itemStyle: { color: 'rgba(24,144,255,0.2)' },
          barMaxWidth: 30,
        },
      ],
    };
  })() : {};

  // ── 排名表格列（依赖 setSelectedStore，定义在组件内） ─────────────────────

  const rankingColumns: ZTableColumn<StoreRankingItem>[] = [
    {
      key: '_rank' as any,
      title: '#',
      width: 48,
      render: (_: any, __: any, i: number) => i + 1,
    },
    {
      key: 'store_name',
      title: '门店',
      render: (name: string, row: StoreRankingItem) => (
        <button
          className={`${styles.storeLink} ${row.store_id === selectedStore ? styles.storeLinkActive : ''}`}
          onClick={() => setSelectedStore(row.store_id)}
        >
          {name || row.store_id}
        </button>
      ),
    },
    {
      key: 'actual_cost_pct',
      title: '实际成本率',
      align: 'right',
      render: (v: number, row: StoreRankingItem) => (
        <strong style={{ color: statusColor(row.variance_status) }}>{v?.toFixed(1)}%</strong>
      ),
    },
    {
      key: 'theoretical_pct',
      title: '理论成本率',
      align: 'right',
      render: (v: number) => `${v?.toFixed(1) ?? '-'}%`,
    },
    {
      key: 'variance_pct',
      title: '差异',
      align: 'right',
      render: (v: number) => {
        const color = v > 5 ? '#C53030' : v > 2 ? '#faad14' : '#1A7A52';
        const Icon  = v > 0 ? RiseOutlined : FallOutlined;
        return <span style={{ color }}><Icon /> {v?.toFixed(1)}%</span>;
      },
    },
    {
      key: 'variance_status',
      title: '状态',
      width: 80,
      align: 'center',
      render: (s: string) => <ZBadge type={statusBadgeType(s)} text={statusBadgeText(s)} />,
    },
    {
      key: 'actual_cost_yuan',
      title: '实际成本',
      align: 'right',
      render: (v: number) => `¥${v?.toLocaleString() ?? '-'}`,
    },
  ];

  const summary  = rankingData?.summary;
  const execSum  = monthlyReport?.executive_summary;

  const storeOptions = (rankingData?.stores || []).map(s => ({
    value: s.store_id,
    label: s.store_name || s.store_id,
  }));

  // ── 渲染 ──────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>
      <h2 className={styles.pageTitle}>
        <DollarOutlined style={{ marginRight: 8 }} />
        成本率趋势 &amp; 利润分析
      </h2>

      {/* 顶部筛选 */}
      <ZCard style={{ marginBottom: 14 }}>
        <div className={styles.toolbar}>
          <span className={styles.toolbarLabel}>日期区间：</span>
          <DatePicker.RangePicker
            value={dateRange}
            onChange={(v) => v && setDateRange(v as [Dayjs, Dayjs])}
            format="YYYY-MM-DD"
          />
          <ZButton variant="primary" icon={<ReloadOutlined />} onClick={loadRanking} disabled={loading}>
            刷新
          </ZButton>
        </div>
      </ZCard>

      {/* 全局摘要 KPI */}
      {summary && (
        <div className={styles.kpiGrid3} style={{ marginBottom: 14 }}>
          <ZCard>
            <ZKpi value={summary.store_count} unit="家" label="参与分析门店数" />
          </ZCard>
          <ZCard>
            <ZKpi
              value={summary.avg_actual_cost_pct?.toFixed(1)}
              unit="%"
              label="平均食材成本率"
            />
          </ZCard>
          <ZCard>
            <ZKpi
              value={summary.over_budget_count}
              unit={`/ ${summary.store_count}`}
              label="超预算门店"
            />
          </ZCard>
        </div>
      )}

      {/* 三个 Tab */}
      <ZTabs
        items={[
          // ── Tab 1: 跨店成本排名 ────────────────────────────────────────────
          {
            key: 'ranking',
            label: '跨店成本排名',
            children: loading ? (
              <ZSkeleton rows={6} block />
            ) : rankingData ? (
              <>
                <ZCard title="成本率排名（实际 vs 理论）" style={{ marginBottom: 14 }}>
                  <ReactECharts option={rankingChartOption} style={{ height: 300 }} />
                </ZCard>
                <ZCard title="门店明细">
                  <ZTable
                    columns={rankingColumns}
                    data={rankingData.stores}
                    rowKey="store_id"
                    emptyText="暂无门店数据"
                  />
                </ZCard>
              </>
            ) : (
              <ZEmpty description="暂无数据" />
            ),
          },

          // ── Tab 2: 单店月度趋势 ────────────────────────────────────────────
          {
            key: 'trend',
            label: '单店月度趋势',
            children: (
              <>
                <ZCard style={{ marginBottom: 14 }}>
                  <div className={styles.toolbar}>
                    <span className={styles.toolbarLabel}>选择门店：</span>
                    <ZSelect
                      value={selectedStore || undefined}
                      options={storeOptions}
                      onChange={(v) => setSelectedStore(v as string)}
                      style={{ width: 200 }}
                    />
                    <span className={styles.toolbarLabel}>报告月份：</span>
                    <DatePicker
                      picker="month"
                      value={reportMonth}
                      onChange={(v) => v && setReportMonth(v)}
                      format="YYYY年MM月"
                      disabledDate={(d) => d && d > dayjs().endOf('month')}
                    />
                    <ZButton
                      icon={<ReloadOutlined />}
                      onClick={() => loadMonthlyReport(selectedStore)}
                      disabled={!selectedStore || reportLoading}
                    >
                      刷新
                    </ZButton>
                    {selectedStore && (
                      <a
                        className={styles.pdfLink}
                        href={`/api/v1/reports/monthly/${selectedStore}/html?year=${reportMonth.year()}&month=${reportMonth.month() + 1}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        打印 PDF
                      </a>
                    )}
                  </div>
                </ZCard>

                {reportLoading ? (
                  <ZSkeleton rows={6} block />
                ) : monthlyReport ? (
                  <>
                    {execSum && (
                      <div
                        className={`${styles.alertBar} ${styles[`alert_${execSum.cost_rate_status}`]}`}
                        style={{ marginBottom: 14 }}
                      >
                        {execSum.headline}
                      </div>
                    )}

                    {execSum && (
                      <div className={styles.kpiGrid4} style={{ marginBottom: 14 }}>
                        <ZCard>
                          <ZKpi
                            value={`¥${execSum.revenue_yuan?.toLocaleString('zh-CN', { minimumFractionDigits: 0 })}`}
                            label="月营业额"
                          />
                        </ZCard>
                        <ZCard>
                          <ZKpi
                            value={execSum.actual_cost_pct?.toFixed(1)}
                            unit="%"
                            label="食材成本率"
                          />
                          <div style={{ marginTop: 6 }}>
                            <ZBadge
                              type={statusBadgeType(execSum.cost_rate_status)}
                              text={statusBadgeText(execSum.cost_rate_status)}
                            />
                          </div>
                        </ZCard>
                        <ZCard>
                          <ZKpi
                            value={execSum.decision_adoption_pct?.toFixed(0)}
                            unit="%"
                            label="决策采纳率"
                          />
                        </ZCard>
                        <ZCard>
                          <ZKpi
                            value={`¥${execSum.total_saving_yuan?.toLocaleString('zh-CN', { minimumFractionDigits: 0 })}`}
                            label="决策节省金额"
                          />
                        </ZCard>
                      </div>
                    )}

                    <ZCard title={`${monthlyReport.period_label} 成本率周趋势`} style={{ marginBottom: 14 }}>
                      <ReactECharts option={trendChartOption} style={{ height: 320 }} />
                      <p className={styles.chartHint}>
                        橙色虚线为 35% 警戒线；柱状为营业额（右轴）；点颜色：绿=正常 橙=偏高 红=超标
                      </p>
                    </ZCard>
                  </>
                ) : (
                  selectedStore && <ZEmpty description="请点击刷新加载月度报告" />
                )}
              </>
            ),
          },

          // ── Tab 3: 单店食材明细 ────────────────────────────────────────────
          {
            key: 'variance',
            label: '单店食材明细',
            children: (
              <>
                <ZCard style={{ marginBottom: 14 }}>
                  <div className={styles.toolbar}>
                    <span className={styles.toolbarLabel}>选择门店：</span>
                    <ZSelect
                      value={selectedStore || undefined}
                      options={storeOptions}
                      onChange={(v) => { const s = v as string; setSelectedStore(s); loadVariance(s); }}
                      style={{ width: 200 }}
                    />
                    <ZButton
                      icon={<ReloadOutlined />}
                      onClick={() => selectedStore && loadVariance(selectedStore)}
                      disabled={!selectedStore || varianceLoading}
                    >
                      刷新
                    </ZButton>
                    {varianceData && (
                      <span className={styles.dateRange}>
                        {varianceData.start_date} 至 {varianceData.end_date}
                      </span>
                    )}
                  </div>
                </ZCard>

                {!selectedStore ? (
                  <ZEmpty description="请在「跨店成本排名」中点击一家门店，或在上方下拉菜单中选择门店" />
                ) : varianceLoading ? (
                  <ZSkeleton rows={6} block />
                ) : varianceData ? (
                  <>
                    <div className={styles.kpiGrid4} style={{ marginBottom: 14 }}>
                      <ZCard>
                        <ZKpi
                          value={`¥${varianceData.actual_cost_yuan?.toLocaleString('zh-CN', { minimumFractionDigits: 0 })}`}
                          label="实际食材成本"
                        />
                      </ZCard>
                      <ZCard>
                        <ZKpi
                          value={varianceData.actual_cost_pct?.toFixed(1)}
                          unit="%"
                          label="实际成本率"
                        />
                        <div style={{ marginTop: 6 }}>
                          <ZBadge
                            type={statusBadgeType(varianceData.variance_status)}
                            text={statusBadgeText(varianceData.variance_status)}
                          />
                        </div>
                      </ZCard>
                      <ZCard>
                        <ZKpi
                          value={varianceData.theoretical_pct?.toFixed(1)}
                          unit="%"
                          label="理论成本率"
                        />
                      </ZCard>
                      <ZCard>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
                          实际 vs 理论差异
                        </div>
                        <div style={{
                          fontSize: 22, fontWeight: 700, lineHeight: 1.2,
                          color: varianceData.variance_pct > 5 ? '#C53030'
                               : varianceData.variance_pct > 2 ? '#faad14'
                               : '#1A7A52',
                        }}>
                          {varianceData.variance_pct > 0 ? <RiseOutlined /> : <FallOutlined />}
                          {' '}{varianceData.variance_pct?.toFixed(1)}%
                        </div>
                      </ZCard>
                    </div>

                    <ZCard
                      title={
                        <span>
                          <DollarOutlined style={{ color: '#0AAF9A', marginRight: 6 }} />
                          Top 10 食材用料成本（按金额排序）
                        </span>
                      }
                      extra={
                        <span className={styles.dateRange}>
                          营业额 ¥{varianceData.revenue_yuan?.toLocaleString('zh-CN', { minimumFractionDigits: 0 })}
                        </span>
                      }
                    >
                      <ZTable
                        columns={ingredientColumns}
                        data={varianceData.top_ingredients.map((item, idx) => ({
                          ...item,
                          rank: idx + 1,
                          cost_share_pct: varianceData.actual_cost_fen > 0
                            ? Math.round(item.usage_cost_fen / varianceData.actual_cost_fen * 1000) / 10
                            : 0,
                        }))}
                        rowKey="item_id"
                        emptyText="暂无食材用料数据"
                      />
                    </ZCard>
                  </>
                ) : (
                  <ZEmpty description="请点击刷新加载食材成本明细" />
                )}
              </>
            ),
          },
        ]}
      />
    </div>
  );
};

export default ProfitDashboard;
