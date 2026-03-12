import React, { useState, useEffect, useCallback, useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZTable, ZEmpty } from '../design-system/components';
import type { ZTableColumn } from '../design-system/components';
import { apiClient, handleApiError } from '../services/api';
import styles from './DeveloperConsolePage.module.css';

// ── Types ────────────────────────────────────────────────────────────────────

interface ConsoleOverview {
  developer: { id: string; name: string; tier: string; status: string };
  api_usage: { month: string; total_calls: number; billable_calls: number } | null;
  plugin_summary: { total: number; published: number; total_installs: number; avg_rating: number | null } | null;
  revenue_summary: { pending_yuan: number; paid_yuan: number } | null;
  webhook_health: { active_count: number; failing_count: number } | null;
  as_of: string;
}

interface TrendItem  { date: string; calls: number }
interface PluginItem {
  id: string; name: string; icon_emoji: string; category: string;
  status: string; install_count: number; rating_avg: number; rating_count: number;
}
interface RevenueRecord {
  period: string; gross_revenue_yuan: number; net_payout_yuan: number;
  share_pct: number; status: string;
}
interface LeaderEntry {
  rank: number; id: string; company_name: string; tier: string;
  plugin_count: number; total_installs: number; net_yuan: number;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const TIER_BADGE: Record<string, 'neutral' | 'success' | 'warning' | 'error'> = {
  free: 'neutral', basic: 'success', pro: 'warning', enterprise: 'error',
};
const TIER_LABELS: Record<string, string> = {
  free: '免费版', basic: '基础版', pro: '专业版', enterprise: '企业版',
};
const SETTLEMENT_BADGE: Record<string, 'neutral' | 'warning' | 'success'> = {
  pending: 'warning', approved: 'neutral', paid: 'success',
};

const DEVELOPER_ID = localStorage.getItem('developer_id') || 'dev-demo-001';

// ── Plugin columns ────────────────────────────────────────────────────────────

const pluginColumns: ZTableColumn<PluginItem>[] = [
  {
    key: 'name',
    title: '插件',
    render: (v, row) => (
      <span className={styles.pluginName}>
        <span className={styles.emoji}>{row.icon_emoji}</span>{v}
      </span>
    ),
  },
  {
    key: 'status',
    title: '状态',
    align: 'center',
    render: (v) => <ZBadge type={v === 'published' ? 'success' : 'warning'} text={v === 'published' ? '已上线' : v} />,
  },
  {
    key: 'install_count',
    title: '安装量',
    align: 'right',
    render: (v) => <b>{Number(v).toLocaleString()}</b>,
  },
  {
    key: 'rating_avg',
    title: '评分',
    align: 'center',
    render: (v, row) => row.rating_count > 0
      ? <span className={styles.rating}>★ {Number(v).toFixed(1)}</span>
      : <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>暂无</span>,
  },
];

// ── Revenue columns ───────────────────────────────────────────────────────────

const revenueColumns: ZTableColumn<RevenueRecord>[] = [
  { key: 'period', title: '周期' },
  {
    key: 'gross_revenue_yuan',
    title: '流水',
    align: 'right',
    render: (v) => <span className={styles.amount}>¥{Number(v).toFixed(2)}</span>,
  },
  {
    key: 'share_pct',
    title: '分成比',
    align: 'center',
    render: (v) => <span>{v}%</span>,
  },
  {
    key: 'net_payout_yuan',
    title: '实收',
    align: 'right',
    render: (v) => <span className={styles.amountGreen}>¥{Number(v).toFixed(2)}</span>,
  },
  {
    key: 'status',
    title: '状态',
    align: 'center',
    render: (v) => <ZBadge type={SETTLEMENT_BADGE[v] || 'neutral'} text={
      v === 'pending' ? '待审' : v === 'approved' ? '已审' : '已付'
    } />,
  },
];

// ── Leaderboard columns ───────────────────────────────────────────────────────

const leaderColumns: ZTableColumn<LeaderEntry>[] = [
  {
    key: 'rank',
    title: '#',
    align: 'center',
    render: (v) => <span className={v <= 3 ? styles.topRank : ''}>{v}</span>,
  },
  {
    key: 'company_name',
    title: '开发者',
    render: (v, row) => (
      <span>{v} <ZBadge type={TIER_BADGE[row.tier] || 'neutral'} text={TIER_LABELS[row.tier] || row.tier} /></span>
    ),
  },
  {
    key: 'plugin_count',
    title: '插件数',
    align: 'center',
  },
  {
    key: 'total_installs',
    title: '总安装',
    align: 'right',
    render: (v) => <b>{Number(v).toLocaleString()}</b>,
  },
  {
    key: 'net_yuan',
    title: '累计分成',
    align: 'right',
    render: (v) => <span className={styles.amount}>¥{Number(v).toFixed(2)}</span>,
  },
];

// ── Component ─────────────────────────────────────────────────────────────────

const DeveloperConsolePage: React.FC = () => {
  const [overview, setOverview]   = useState<ConsoleOverview | null>(null);
  const [trend, setTrend]         = useState<TrendItem[]>([]);
  const [plugins, setPlugins]     = useState<PluginItem[]>([]);
  const [revenue, setRevenue]     = useState<RevenueRecord[]>([]);
  const [leaderboard, setLeaderboard] = useState<LeaderEntry[]>([]);
  const [loading, setLoading]     = useState(false);
  const [snapping, setSnapping]   = useState(false);
  const [activeTab, setActiveTab] = useState<'plugins' | 'revenue' | 'leaderboard'>('plugins');

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [ovRes, trendRes, plugRes, revRes, lbRes] = await Promise.allSettled([
        apiClient.get(`/api/v1/console/developers/${DEVELOPER_ID}/overview`),
        apiClient.get(`/api/v1/console/developers/${DEVELOPER_ID}/trend`, { params: { days: 7 } }),
        apiClient.get(`/api/v1/console/developers/${DEVELOPER_ID}/plugins`),
        apiClient.get(`/api/v1/console/developers/${DEVELOPER_ID}/revenue`),
        apiClient.get('/api/v1/console/admin/leaderboard', { params: { limit: 10 } }),
      ]);
      if (ovRes.status === 'fulfilled')    setOverview(ovRes.value.data);
      if (trendRes.status === 'fulfilled') setTrend(trendRes.value.data.trend || []);
      if (plugRes.status === 'fulfilled')  setPlugins(plugRes.value.data.plugins || []);
      if (revRes.status === 'fulfilled')   setRevenue(revRes.value.data.records || []);
      if (lbRes.status === 'fulfilled')    setLeaderboard(lbRes.value.data.leaderboard || []);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const takeSnapshot = async () => {
    setSnapping(true);
    try {
      await apiClient.post(`/api/v1/console/developers/${DEVELOPER_ID}/snapshot`);
      loadAll();
    } catch (e) { handleApiError(e); }
    finally { setSnapping(false); }
  };

  // Trend chart option
  const trendOption = useMemo(() => ({
    tooltip: { trigger: 'axis' },
    grid: { top: 12, bottom: 28, left: 50, right: 12 },
    xAxis: {
      type: 'category',
      data: trend.map(t => t.date.slice(5)),   // MM-DD
      axisLabel: { fontSize: 11 },
    },
    yAxis: { type: 'value', axisLabel: { fontSize: 11 } },
    series: [{
      name: 'API 调用',
      type: 'bar',
      data: trend.map(t => t.calls),
      itemStyle: { color: 'var(--accent, #0AAF9A)', opacity: 0.8 },
      barMaxWidth: 20,
    }],
  }), [trend]);

  const dev = overview?.developer;
  const api = overview?.api_usage;
  const ps  = overview?.plugin_summary;
  const rev = overview?.revenue_summary;
  const wh  = overview?.webhook_health;

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>ISV 开发者控制台</h1>
          {dev && (
            <p className={styles.pageSub}>
              {dev.name} · <ZBadge type={TIER_BADGE[dev.tier] || 'neutral'} text={TIER_LABELS[dev.tier] || dev.tier} />
            </p>
          )}
        </div>
        <div className={styles.headerActions}>
          <ZButton onClick={takeSnapshot} disabled={snapping}>
            {snapping ? '刷新中…' : '更新快照'}
          </ZButton>
          <ZButton onClick={loadAll}>刷新</ZButton>
        </div>
      </div>

      {/* KPI row */}
      <div className={styles.kpiGrid}>
        {loading && !overview ? (
          [...Array(4)].map((_, i) => <ZSkeleton key={i} height={88} />)
        ) : overview ? (
          <>
            <ZCard>
              <ZKpi label="本月 API 调用" value={api?.total_calls?.toLocaleString() ?? '—'} unit="次" />
              <div className={styles.kpiSub}>计费调用 {api?.billable_calls?.toLocaleString() ?? 0} 次</div>
            </ZCard>
            <ZCard>
              <ZKpi label="上线插件" value={ps?.published ?? 0} unit="个" />
              <div className={styles.kpiSub}>总安装 {ps?.total_installs?.toLocaleString() ?? 0} 次</div>
            </ZCard>
            <ZCard>
              <ZKpi label="待结算收入" value={`¥${rev?.pending_yuan?.toFixed(2) ?? '0.00'}`} />
              <div className={styles.kpiSub}>已付款 ¥{rev?.paid_yuan?.toFixed(2) ?? '0.00'}</div>
            </ZCard>
            <ZCard>
              <ZKpi label="Webhook 订阅" value={wh?.active_count ?? 0} unit="个" />
              {(wh?.failing_count ?? 0) > 0 && (
                <div className={styles.kpiSubWarn}>⚠ {wh!.failing_count} 个异常</div>
              )}
            </ZCard>
          </>
        ) : null}
      </div>

      {/* Trend chart */}
      <ZCard title="近7天 API 调用趋势">
        {loading ? (
          <ZSkeleton height={200} />
        ) : trend.length > 0 ? (
          <div className={styles.chart}>
            <ReactECharts option={trendOption} style={{ height: '100%' }} />
          </div>
        ) : (
          <ZEmpty text="暂无调用记录" />
        )}
      </ZCard>

      {/* Tab section */}
      <ZCard>
        <div className={styles.tabBar}>
          {(['plugins', 'revenue', 'leaderboard'] as const).map(tab => (
            <button
              key={tab}
              className={`${styles.tab} ${activeTab === tab ? styles.tabActive : ''}`}
              onClick={() => setActiveTab(tab)}
            >
              {{ plugins: '我的插件', revenue: '收入历史', leaderboard: '开发者排行' }[tab]}
            </button>
          ))}
        </div>

        {activeTab === 'plugins' && (
          loading ? <ZSkeleton height={200} /> :
          plugins.length > 0 ? (
            <ZTable columns={pluginColumns} data={plugins} rowKey="id" />
          ) : <ZEmpty text="暂无插件" />
        )}

        {activeTab === 'revenue' && (
          loading ? <ZSkeleton height={200} /> :
          revenue.length > 0 ? (
            <ZTable columns={revenueColumns} data={revenue} rowKey="period" />
          ) : <ZEmpty text="暂无结算记录" />
        )}

        {activeTab === 'leaderboard' && (
          loading ? <ZSkeleton height={200} /> :
          leaderboard.length > 0 ? (
            <ZTable columns={leaderColumns} data={leaderboard} rowKey="id" />
          ) : <ZEmpty text="暂无排行数据" />
        )}
      </ZCard>
    </div>
  );
};

export default DeveloperConsolePage;
