import React, { useState, useEffect, useCallback, useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZTable, ZEmpty } from '../design-system/components';
import type { ZTableColumn } from '../design-system/components';
import { apiClient, handleApiError } from '../services/api';
import styles from './PlatformAnalyticsPage.module.css';

// ── Types ──────────────────────────────────────────────────────────────────────

interface PlatformOverview {
  total_developers: number;
  active_developers: number;
  by_tier: Record<string, number>;
  published_plugins: number;
  pending_plugins: number;
  total_installs: number;
  avg_plugin_rating: number;
  total_gross_revenue_yuan: number;
  total_net_payout_yuan: number;
  platform_profit_yuan: number;
  current_month: string;
  current_month_gross_yuan: number;
  current_month_net_yuan: number;
}

interface TrendItem {
  period: string;
  gross_yuan: number;
  net_yuan: number;
  platform_profit_yuan: number;
  developer_count: number;
}

interface TopPlugin {
  id: string;
  name: string;
  icon_emoji: string;
  category: string;
  install_count: number;
  rating_avg: number;
  rating_count: number;
  tier_required: string;
  price_type: string;
  developer_name: string;
}

// ── Constants ──────────────────────────────────────────────────────────────────

const TIER_BADGE: Record<string, 'neutral' | 'success' | 'warning' | 'error'> = {
  free: 'neutral', basic: 'success', pro: 'warning', enterprise: 'error',
};
const TIER_LABELS: Record<string, string> = {
  free: '免费版', basic: '基础版', pro: '专业版', enterprise: '企业版',
};
const TIER_COLORS: Record<string, string> = {
  free: '#d9d9d9', basic: '#1A7A52', pro: '#C8923A', enterprise: '#C53030',
};
const CAT_LABELS: Record<string, string> = {
  pos_integration: 'POS', erp_integration: 'ERP',
  marketing: '营销', analytics: '分析', operations: '运营',
};

// ── Top plugins columns ────────────────────────────────────────────────────────

const topPluginColumns: ZTableColumn<TopPlugin>[] = [
  {
    key: 'name',
    title: '插件',
    render: (name, row) => (
      <div className={styles.pluginNameCell}>
        <span className={styles.pluginEmoji}>{row.icon_emoji}</span>
        <div className={styles.pluginMeta}>
          <div className={styles.pluginName}>{name}</div>
          <div className={styles.pluginDev}>{row.developer_name}</div>
        </div>
      </div>
    ),
  },
  {
    key: 'category',
    title: '分类',
    render: (cat) => <ZBadge type="neutral" text={CAT_LABELS[cat] || cat} />,
  },
  {
    key: 'tier_required',
    title: '门槛',
    align: 'center',
    render: (tier) => <ZBadge type={TIER_BADGE[tier] || 'neutral'} text={TIER_LABELS[tier] || tier} />,
  },
  {
    key: 'install_count',
    title: '安装量',
    align: 'right',
    render: (n) => <span style={{ fontWeight: 700 }}>{Number(n).toLocaleString()}</span>,
  },
  {
    key: 'rating_avg',
    title: '评分',
    align: 'center',
    render: (v, row) => row.rating_count > 0
      ? <span className={styles.ratingDisplay}>★ {Number(v).toFixed(1)}<span style={{ color: 'var(--text-secondary)', fontWeight: 400 }}>({row.rating_count})</span></span>
      : <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>暂无</span>,
  },
];

// ── Component ──────────────────────────────────────────────────────────────────

const PlatformAnalyticsPage: React.FC = () => {
  const [overview, setOverview] = useState<PlatformOverview | null>(null);
  const [trends, setTrends] = useState<TrendItem[]>([]);
  const [topPlugins, setTopPlugins] = useState<TopPlugin[]>([]);
  const [loading, setLoading] = useState(false);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [overviewRes, trendsRes, topRes] = await Promise.allSettled([
        apiClient.get('/api/v1/platform/overview'),
        apiClient.get('/api/v1/platform/trends', { params: { months: 6 } }),
        apiClient.get('/api/v1/platform/top-plugins', { params: { limit: 10 } }),
      ]);
      if (overviewRes.status === 'fulfilled') setOverview(overviewRes.value.data);
      if (trendsRes.status === 'fulfilled') setTrends(trendsRes.value.data.trends || []);
      if (topRes.status === 'fulfilled') setTopPlugins(topRes.value.data.plugins || []);
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  // Revenue trend ECharts option
  const trendOption = useMemo(() => ({
    tooltip: {
      trigger: 'axis',
      formatter: (params: { seriesName: string; value: number }[]) =>
        params.map(p => `${p.seriesName}: ¥${Number(p.value).toFixed(2)}`).join('<br/>'),
    },
    legend: { data: ['总收入', 'ISV分成', '平台利润'], bottom: 0, itemHeight: 8 },
    grid: { top: 16, bottom: 36, left: 60, right: 16 },
    xAxis: {
      type: 'category',
      data: trends.map(t => t.period),
      axisLabel: { fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: '¥{value}', fontSize: 11 },
    },
    series: [
      {
        name: '总收入',
        type: 'line',
        smooth: true,
        data: trends.map(t => t.gross_yuan.toFixed(2)),
        areaStyle: { opacity: 0.12, color: '#0AAF9A' },
        lineStyle: { color: '#0AAF9A', width: 2 },
        itemStyle: { color: '#0AAF9A' },
        symbol: 'circle', symbolSize: 5,
      },
      {
        name: 'ISV分成',
        type: 'line',
        smooth: true,
        data: trends.map(t => t.net_yuan.toFixed(2)),
        areaStyle: { opacity: 0.1, color: '#1A7A52' },
        lineStyle: { color: '#1A7A52', width: 2 },
        itemStyle: { color: '#1A7A52' },
        symbol: 'circle', symbolSize: 5,
      },
      {
        name: '平台利润',
        type: 'bar',
        data: trends.map(t => t.platform_profit_yuan.toFixed(2)),
        itemStyle: { color: 'rgba(64, 150, 255, 0.6)' },
        barMaxWidth: 20,
      },
    ],
  }), [trends]);

  // Tier breakdown — total devs for percentage bar
  const totalDevs = overview ? overview.total_developers : 0;

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>平台商业化总览</h1>
          <p className={styles.pageSub}>ISV 生态规模 · 收入趋势 · 插件市场健康度</p>
        </div>
        <div className={styles.headerActions}>
          <ZButton onClick={loadAll}>刷新</ZButton>
        </div>
      </div>

      {/* KPI Row 1 — Ecosystem */}
      <div className={styles.kpiGrid}>
        {loading && !overview ? (
          [...Array(4)].map((_, i) => <ZSkeleton key={i} height={88} />)
        ) : overview ? (
          <>
            <ZCard>
              <ZKpi label="ISV 开发者" value={overview.total_developers} unit="位" />
              <div className={styles.kpiDetail}>活跃 {overview.active_developers} 位</div>
            </ZCard>
            <ZCard>
              <ZKpi label="上线插件" value={overview.published_plugins} unit="个" />
              <div className={styles.kpiDetail}>待审核 {overview.pending_plugins} 个</div>
            </ZCard>
            <ZCard>
              <ZKpi label="累计安装" value={overview.total_installs.toLocaleString()} unit="次" />
              <div className={styles.kpiDetail}>平均评分 ★{overview.avg_plugin_rating.toFixed(1)}</div>
            </ZCard>
            <ZCard>
              <ZKpi label="本月总收入" value={`¥${overview.current_month_gross_yuan.toFixed(2)}`} />
              <div className={styles.kpiDetail}>本月分成 ¥{overview.current_month_net_yuan.toFixed(2)}</div>
            </ZCard>
          </>
        ) : null}
      </div>

      {/* KPI Row 2 — Revenue */}
      <div className={styles.kpiGrid}>
        {loading && !overview ? (
          [...Array(4)].map((_, i) => <ZSkeleton key={i} height={88} />)
        ) : overview ? (
          <>
            <ZCard>
              <ZKpi label="累计总收入" value={`¥${overview.total_gross_revenue_yuan.toFixed(2)}`} />
            </ZCard>
            <ZCard>
              <ZKpi label="累计分成支付" value={`¥${overview.total_net_payout_yuan.toFixed(2)}`} />
            </ZCard>
            <ZCard>
              <ZKpi label="累计平台利润" value={`¥${overview.platform_profit_yuan.toFixed(2)}`} />
            </ZCard>
            <ZCard>
              <ZKpi label="平台分成留存" value={
                overview.total_gross_revenue_yuan > 0
                  ? `${((overview.platform_profit_yuan / overview.total_gross_revenue_yuan) * 100).toFixed(1)}%`
                  : '—'
              } />
              <div className={styles.kpiDetail}>ISV 分成比例 {
                overview.total_gross_revenue_yuan > 0
                  ? `${((overview.total_net_payout_yuan / overview.total_gross_revenue_yuan) * 100).toFixed(1)}%`
                  : '—'
              }</div>
            </ZCard>
          </>
        ) : null}
      </div>

      {/* Revenue Trend + ISV Tier breakdown */}
      <div className={styles.twoCol}>
        <ZCard title="月度收入趋势（近6个月）">
          {loading ? (
            <ZSkeleton height={280} />
          ) : trends.length > 0 ? (
            <div className={styles.chartContainer}>
              <ReactECharts option={trendOption} style={{ height: '100%' }} />
            </div>
          ) : (
            <ZEmpty text="暂无趋势数据，请先生成结算记录" />
          )}
        </ZCard>

        <ZCard title="ISV 套餐分布">
          {loading ? (
            <ZSkeleton height={200} />
          ) : overview ? (
            <div className={styles.tierList}>
              {(['enterprise', 'pro', 'basic', 'free'] as const).map(tier => {
                const count = overview.by_tier[tier] || 0;
                const pct = totalDevs > 0 ? (count / totalDevs) * 100 : 0;
                return (
                  <div key={tier}>
                    <div className={styles.tierRow}>
                      <ZBadge type={TIER_BADGE[tier]} text={TIER_LABELS[tier]} />
                      <span className={styles.tierCount}>{count}</span>
                    </div>
                    <div className={styles.tierBar}>
                      <div
                        className={styles.tierBarFill}
                        style={{
                          width: `${pct}%`,
                          background: TIER_COLORS[tier],
                        }}
                      />
                    </div>
                  </div>
                );
              })}
              <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>
                共 {totalDevs} 位开发者
              </div>
            </div>
          ) : <ZEmpty text="暂无数据" />}
        </ZCard>
      </div>

      {/* Top 10 plugins */}
      <ZCard title={`热门插件 Top ${topPlugins.length}`}>
        {loading ? (
          <ZSkeleton height={240} />
        ) : topPlugins.length > 0 ? (
          <ZTable columns={topPluginColumns} data={topPlugins} rowKey="id" />
        ) : (
          <ZEmpty text="暂无已发布插件" />
        )}
      </ZCard>

      {/* Platform health numbers */}
      {overview && (
        <ZCard title="平台健康快览">
          <div className={styles.healthGrid}>
            <div className={styles.healthItem}>
              <div className={styles.healthLabel}>活跃开发者占比</div>
              <div className={`${styles.healthValue} ${styles.healthValueGreen}`}>
                {overview.total_developers > 0
                  ? `${((overview.active_developers / overview.total_developers) * 100).toFixed(0)}%`
                  : '—'}
              </div>
            </div>
            <div className={styles.healthItem}>
              <div className={styles.healthLabel}>平均安装量 / 插件</div>
              <div className={`${styles.healthValue} ${styles.healthValueAccent}`}>
                {overview.published_plugins > 0
                  ? Math.round(overview.total_installs / overview.published_plugins)
                  : 0}
              </div>
            </div>
            <div className={styles.healthItem}>
              <div className={styles.healthLabel}>本月环比</div>
              <div className={styles.healthValue}>
                {overview.current_month}
              </div>
            </div>
          </div>
        </ZCard>
      )}
    </div>
  );
};

export default PlatformAnalyticsPage;
