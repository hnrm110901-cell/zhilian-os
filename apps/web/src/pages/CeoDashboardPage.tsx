import React, { useState, useEffect, useCallback, useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZTable, ZEmpty } from '../design-system/components';
import type { ZTableColumn } from '../design-system/components';
import { apiClient, handleApiError } from '../services/api';
import styles from './CeoDashboardPage.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

interface ProfitRank {
  rank: number;
  store_id: string;
  net_revenue_yuan: number;
  gross_profit_yuan: number;
  profit_margin_pct: number;
  total_cost_yuan: number;
}

interface RiskHeat {
  store_id: string;
  open_total: number;
  high_count: number;
  max_severity: string;
}

interface TaxAlert {
  store_id: string;
  tax_type: string;
  tax_name: string;
  deviation_yuan: number;
  deviation_pct: number;
  risk_level: string;
}

interface CashGapStore {
  store_id: string;
  gap_days: number;
  min_balance_yuan: number;
}

interface SettlementIssue {
  store_id: string;
  platform: string;
  period: string;
  deviation_yuan: number;
  risk_level: string;
  settle_date: string;
}

interface CeoDashboard {
  period: string;
  as_of: string;
  brand_summary: {
    store_count: number;
    total_revenue_yuan: number;
    total_profit_yuan: number;
    total_cost_yuan: number;
    avg_margin_pct: number;
  } | null;
  profit_rank: ProfitRank[];
  risk_heat: RiskHeat[];
  tax_alerts: TaxAlert[];
  cash_gap_stores: CashGapStore[];
  settlement_issues: SettlementIssue[];
  pending_l2_actions: number;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const today   = new Date().toISOString().slice(0, 10);
const period  = today.slice(0, 7);
const SEV_COLORS: Record<string, string> = {
  critical: '#C53030', high: '#C8923A', medium: '#faad14', low: '#1A7A52',
};

// ── Profit rank columns ───────────────────────────────────────────────────────

const rankColumns: ZTableColumn<ProfitRank>[] = [
  {
    key: 'rank',
    title: '#',
    align: 'center',
    render: (v) => (
      <span style={{
        fontWeight: 800,
        color: v <= 3 ? '#C8923A' : 'var(--text-primary)',
        fontSize: v <= 3 ? 16 : 13,
      }}>{v}</span>
    ),
  },
  { key: 'store_id', title: '门店 ID' },
  {
    key: 'net_revenue_yuan',
    title: '净收入',
    align: 'right',
    render: (v) => <span className={styles.mono}>¥{Number(v).toFixed(0)}</span>,
  },
  {
    key: 'gross_profit_yuan',
    title: '毛利润',
    align: 'right',
    render: (v) => <span className={styles.amount}>¥{Number(v).toFixed(0)}</span>,
  },
  {
    key: 'profit_margin_pct',
    title: '利润率',
    align: 'center',
    render: (v) => (
      <span style={{
        color: Number(v) >= 20 ? '#1A7A52' : Number(v) >= 10 ? '#faad14' : '#C53030',
        fontWeight: 600,
      }}>
        {Number(v).toFixed(1)}%
      </span>
    ),
  },
];

// ── Component ─────────────────────────────────────────────────────────────────

const CeoDashboardPage: React.FC = () => {
  const [data, setData]       = useState<CeoDashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'rank' | 'risk' | 'tax' | 'cash'>('rank');

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/api/v1/dashboards/ceo', { params: { period } });
      setData(res.data);
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadDashboard(); }, [loadDashboard]);

  // ── Profit rank bar chart ─────────────────────────────────────────────────

  const rankBarOption = useMemo(() => {
    if (!data?.profit_rank.length) return {};
    const top = data.profit_rank.slice(0, 8);
    return {
      tooltip: { trigger: 'axis' },
      grid: { top: 12, bottom: 40, left: 100, right: 20 },
      xAxis: { type: 'value', axisLabel: { fontSize: 10, formatter: (v: number) => `¥${(v/1000).toFixed(0)}k` } },
      yAxis: {
        type: 'category',
        data: top.map(r => r.store_id).reverse(),
        axisLabel: { fontSize: 10 },
      },
      series: [
        {
          name: '净收入',
          type: 'bar',
          data: top.map(r => r.net_revenue_yuan).reverse(),
          itemStyle: { color: 'rgba(255,107,44,0.25)' },
          barMaxWidth: 16,
        },
        {
          name: '毛利润',
          type: 'bar',
          data: top.map(r => r.gross_profit_yuan).reverse(),
          itemStyle: { color: '#FF6B2C' },
          barMaxWidth: 16,
        },
      ],
    };
  }, [data]);

  // ── Risk heat scatter ─────────────────────────────────────────────────────

  const riskHeatOption = useMemo(() => {
    if (!data?.risk_heat.length) return {};
    return {
      tooltip: {
        formatter: (p: any) => `${p.data[2]}<br/>高风险: ${p.data[0]} / 总: ${p.data[1]}`,
      },
      grid: { top: 12, bottom: 40, left: 50, right: 20 },
      xAxis: { type: 'value', name: '高风险数', axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value', name: '总开放数', axisLabel: { fontSize: 10 } },
      series: [{
        type: 'scatter',
        data: data.risk_heat.map(r => [r.high_count, r.open_total, r.store_id]),
        symbolSize: (d: number[]) => Math.max(10, d[0] * 6 + 8),
        itemStyle: {
          color: (p: any) => {
            const v = p.data[0];
            return v >= 3 ? '#C53030' : v >= 1 ? '#C8923A' : '#1A7A52';
          },
          opacity: 0.8,
        },
      }],
    };
  }, [data]);

  const bs = data?.brand_summary;

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>CEO 驾驶舱</h1>
          <p className={styles.pageSub}>
            多门店利润 · 风险热力 · 税务告警 · 现金缺口 · {period}
          </p>
        </div>
        <div className={styles.headerActions}>
          <ZButton onClick={loadDashboard}>刷新</ZButton>
        </div>
      </div>

      {/* Brand KPI row */}
      <div className={styles.kpiGrid}>
        {loading && !bs ? (
          [...Array(5)].map((_, i) => <ZSkeleton key={i} height={88} />)
        ) : bs ? (
          <>
            <ZCard>
              <ZKpi label="门店数" value={bs.store_count} unit="家" />
            </ZCard>
            <ZCard>
              <ZKpi label="品牌总收入" value={`¥${(bs.total_revenue_yuan / 10000).toFixed(1)}万`} />
            </ZCard>
            <ZCard>
              <ZKpi label="品牌总利润" value={`¥${(bs.total_profit_yuan / 10000).toFixed(1)}万`} />
              <div className={styles.kpiSub}>均利润率 {bs.avg_margin_pct.toFixed(1)}%</div>
            </ZCard>
            <ZCard>
              <ZKpi label="待处理L2动作" value={data?.pending_l2_actions ?? 0} unit="条" />
              <div className={(data?.pending_l2_actions ?? 0) > 0 ? styles.kpiSubWarn : styles.kpiSub}>
                {(data?.pending_l2_actions ?? 0) > 0 ? '需 CFO 确认' : '无待处理'}
              </div>
            </ZCard>
            <ZCard>
              <ZKpi label="现金缺口门店" value={data?.cash_gap_stores.length ?? 0} unit="家" />
              <div className={(data?.cash_gap_stores.length ?? 0) > 0 ? styles.kpiSubWarn : styles.kpiSub}>
                {(data?.cash_gap_stores.length ?? 0) > 0 ? '需关注' : '无缺口'}
              </div>
            </ZCard>
          </>
        ) : null}
      </div>

      {/* Main tabs */}
      <ZCard>
        <div className={styles.tabBar}>
          {(['rank', 'risk', 'tax', 'cash'] as const).map(tab => (
            <button
              key={tab}
              className={`${styles.tab} ${activeTab === tab ? styles.tabActive : ''}`}
              onClick={() => setActiveTab(tab)}
            >
              {{
                rank: '利润排行',
                risk: `风险热力${data?.risk_heat.length ? ` (${data.risk_heat.length})` : ''}`,
                tax:  `税务告警${data?.tax_alerts.length ? ` (${data.tax_alerts.length})` : ''}`,
                cash: `现金缺口${data?.cash_gap_stores.length ? ` (${data.cash_gap_stores.length})` : ''}`,
              }[tab]}
            </button>
          ))}
        </div>

        {/* Profit rank */}
        {activeTab === 'rank' && (
          loading ? <ZSkeleton height={280} /> :
          (data?.profit_rank.length ?? 0) > 0 ? (
            <div className={styles.rankLayout}>
              <div className={styles.rankChart}>
                <ReactECharts option={rankBarOption} style={{ height: '100%' }} />
              </div>
              <div style={{ flex: 1 }}>
                <ZTable columns={rankColumns} data={data!.profit_rank} rowKey="store_id" />
              </div>
            </div>
          ) : <ZEmpty text="暂无利润数据" />
        )}

        {/* Risk heat */}
        {activeTab === 'risk' && (
          loading ? <ZSkeleton height={280} /> :
          (data?.risk_heat.length ?? 0) > 0 ? (
            <div>
              <div className={styles.chartMed}>
                <ReactECharts option={riskHeatOption} style={{ height: '100%' }} />
              </div>
              <div className={styles.heatTable}>
                {data!.risk_heat.map(r => (
                  <div key={r.store_id} className={styles.heatRow}>
                    <span className={styles.heatStore}>{r.store_id}</span>
                    <span className={styles.heatBar}>
                      <span
                        className={styles.heatFill}
                        style={{
                          width: `${Math.min(100, r.high_count * 20)}%`,
                          background: SEV_COLORS[r.max_severity] || '#1A7A52',
                        }}
                      />
                    </span>
                    <span className={styles.heatCount}>
                      高: {r.high_count} / 总: {r.open_total}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : <ZEmpty text="暂无风险数据" />
        )}

        {/* Tax alerts */}
        {activeTab === 'tax' && (
          loading ? <ZSkeleton height={200} /> :
          (data?.tax_alerts.length ?? 0) > 0 ? (
            <div className={styles.alertList}>
              {data!.tax_alerts.map((a, i) => (
                <div key={i} className={styles.alertRow}>
                  <ZBadge
                    type={a.risk_level === 'critical' ? 'error' : 'warning'}
                    text={a.risk_level === 'critical' ? '严重' : '高'}
                  />
                  <span className={styles.alertStore}>{a.store_id}</span>
                  <span className={styles.alertName}>{a.tax_name}</span>
                  <span style={{ flex: 1 }} />
                  <span className={styles.devWarn}>
                    ¥{Math.abs(a.deviation_yuan).toFixed(2)}
                    <span style={{ fontSize: 10, marginLeft: 3 }}>({a.deviation_pct.toFixed(1)}%)</span>
                  </span>
                </div>
              ))}
            </div>
          ) : <ZEmpty text="无税务偏差告警" />
        )}

        {/* Cash gap */}
        {activeTab === 'cash' && (
          loading ? <ZSkeleton height={200} /> :
          (data?.cash_gap_stores.length ?? 0) > 0 ? (
            <div className={styles.alertList}>
              {data!.cash_gap_stores.map((c, i) => (
                <div key={i} className={styles.alertRow}>
                  <span className={styles.gapDays}>{c.gap_days}天</span>
                  <span className={styles.alertStore}>{c.store_id}</span>
                  <span style={{ flex: 1 }} />
                  <span className={styles.devWarn}>
                    最低余额 ¥{c.min_balance_yuan.toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          ) : <ZEmpty text="无现金缺口门店" />
        )}
      </ZCard>

      {/* Settlement issues */}
      {(data?.settlement_issues.length ?? 0) > 0 && (
        <ZCard title="结算异常（高风险）">
          <div className={styles.alertList}>
            {data!.settlement_issues.map((s, i) => (
              <div key={i} className={styles.alertRow}>
                <ZBadge type="error" text={s.risk_level === 'critical' ? '严重' : '高'} />
                <span className={styles.alertStore}>{s.store_id}</span>
                <span className={styles.alertName}>{s.platform} · {s.period}</span>
                <span style={{ flex: 1 }} />
                <span className={styles.devWarn}>
                  偏差 ¥{Math.abs(s.deviation_yuan).toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </ZCard>
      )}
    </div>
  );
};

export default CeoDashboardPage;
