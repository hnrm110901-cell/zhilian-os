import React, { useState, useEffect, useCallback, useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZTable, ZEmpty } from '../design-system/components';
import type { ZTableColumn } from '../design-system/components';
import { apiClient, handleApiError } from '../services/api';
import styles from './TaxCashflowPage.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

interface TaxResult {
  tax_type: string;
  tax_name: string;
  tax_rate: number;
  taxable_base_yuan: number;
  tax_amount_yuan: number;
  declared_yuan: number;
  deviation_yuan: number;
  deviation_pct: number;
  risk_level: string;
  calc_date: string;
  detail: string | null;
}

interface CashflowDay {
  forecast_date: string;
  inflow_yuan: number;
  outflow_yuan: number;
  net_yuan: number;
  balance_yuan: number;
  confidence: number;
}

interface AgentAction {
  id: string;
  action_level: string;
  agent_name: string;
  trigger_type: string;
  title: string;
  description: string;
  recommended_action: string | null;
  expected_impact_yuan: number;
  confidence: number;
  status: string;
  period: string | null;
  created_at: string | null;
}

interface CfoDashboard {
  store_id: string;
  period: string;
  profit: {
    net_revenue_yuan: number;
    gross_profit_yuan: number;
    profit_margin_pct: number;
    total_cost_yuan: number;
  } | null;
  tax: {
    total_tax_yuan: number;
    total_deviation_yuan: number;
    tax_types: number;
    max_risk: string;
  } | null;
  cashflow: {
    total_net_yuan: number;
    min_balance_yuan: number;
    max_balance_yuan: number;
    gap_days: number;
  } | null;
  pending_actions: AgentAction[];
  risk: { open_total: number; high_priority: number } | null;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const STORE_ID = localStorage.getItem('store_id') || 'store-demo-001';

const RISK_BADGE: Record<string, 'neutral' | 'success' | 'warning' | 'error'> = {
  low:      'success',
  medium:   'warning',
  high:     'error',
  critical: 'error',
};
const RISK_LABELS: Record<string, string> = {
  low: '低', medium: '中', high: '高', critical: '严重',
};
const LEVEL_BADGE: Record<string, 'neutral' | 'warning' | 'error'> = {
  L1: 'warning', L2: 'error', L3: 'error',
};

// ── Tax columns ───────────────────────────────────────────────────────────────

const taxColumns: ZTableColumn<TaxResult>[] = [
  { key: 'tax_name', title: '税种' },
  {
    key: 'tax_rate',
    title: '税率',
    align: 'center',
    render: (v) => <span>{(Number(v) * 100).toFixed(2)}%</span>,
  },
  {
    key: 'taxable_base_yuan',
    title: '计税基础',
    align: 'right',
    render: (v) => <span className={styles.mono}>¥{Number(v).toFixed(2)}</span>,
  },
  {
    key: 'tax_amount_yuan',
    title: '应纳税额',
    align: 'right',
    render: (v) => <span className={styles.amount}>¥{Number(v).toFixed(2)}</span>,
  },
  {
    key: 'deviation_yuan',
    title: '偏差',
    align: 'right',
    render: (v, row) => (
      <span className={Number(v) > 0 ? styles.devWarn : styles.devOk}>
        {Number(v) > 0 ? '+' : ''}¥{Number(v).toFixed(2)}
        <span style={{ fontSize: 10, marginLeft: 4 }}>({Number(row.deviation_pct).toFixed(1)}%)</span>
      </span>
    ),
  },
  {
    key: 'risk_level',
    title: '风险',
    align: 'center',
    render: (v) => <ZBadge type={RISK_BADGE[v] || 'neutral'} text={RISK_LABELS[v] || v} />,
  },
];

// ── Agent action columns ──────────────────────────────────────────────────────

const actionColumns: ZTableColumn<AgentAction>[] = [
  {
    key: 'action_level',
    title: '级别',
    align: 'center',
    render: (v) => (
      <span className={styles.levelBadge} data-level={v}>{v}</span>
    ),
  },
  { key: 'agent_name', title: 'Agent', align: 'center' },
  {
    key: 'title',
    title: '动作',
    render: (v, row) => (
      <div>
        <div style={{ fontWeight: 600, fontSize: 13 }}>{v}</div>
        {row.description && (
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
            {row.description}
          </div>
        )}
      </div>
    ),
  },
  {
    key: 'expected_impact_yuan',
    title: '预期影响',
    align: 'right',
    render: (v) => (
      <span className={Number(v) >= 0 ? styles.amountGreen : styles.amount}>
        ¥{Number(v).toFixed(2)}
      </span>
    ),
  },
  {
    key: 'status',
    title: '状态',
    align: 'center',
    render: (v) => (
      <ZBadge
        type={v === 'pending' ? 'warning' : v === 'accepted' ? 'success' : 'neutral'}
        text={v === 'pending' ? '待处理' : v === 'accepted' ? '已接受' : '已忽略'}
      />
    ),
  },
];

// ── Component ─────────────────────────────────────────────────────────────────

const TaxCashflowPage: React.FC = () => {
  const today         = new Date().toISOString().slice(0, 10);
  const currentMonth  = today.slice(0, 7);

  const [dashboard, setDashboard]       = useState<CfoDashboard | null>(null);
  const [taxResults, setTaxResults]     = useState<TaxResult[]>([]);
  const [cashflows, setCashflows]       = useState<CashflowDay[]>([]);
  const [actions, setActions]           = useState<AgentAction[]>([]);
  const [loading, setLoading]           = useState(false);
  const [computing, setComputing]       = useState<Record<string, boolean>>({});
  const [activeTab, setActiveTab]       = useState<'tax' | 'cashflow' | 'actions'>('tax');
  const [period]                        = useState(currentMonth);

  const loadDashboard = useCallback(async () => {
    try {
      const res = await apiClient.get(`/api/v1/finance-agent/dashboard/${STORE_ID}`, {
        params: { period },
      });
      setDashboard(res.data);
    } catch (e) { handleApiError(e); }
  }, [period]);

  const loadTax = useCallback(async () => {
    try {
      const res = await apiClient.get(`/api/v1/finance-agent/tax/${STORE_ID}`, {
        params: { period },
      });
      setTaxResults(res.data.results || []);
    } catch (e) { handleApiError(e); }
  }, [period]);

  const loadCashflow = useCallback(async () => {
    try {
      const res = await apiClient.get(`/api/v1/finance-agent/cashflow/${STORE_ID}`);
      setCashflows(res.data.forecasts || []);
    } catch (e) { handleApiError(e); }
  }, []);

  const loadActions = useCallback(async () => {
    try {
      const res = await apiClient.get(`/api/v1/finance-agent/actions/${STORE_ID}`);
      setActions(res.data.actions || []);
    } catch (e) { handleApiError(e); }
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.allSettled([loadDashboard(), loadTax(), loadCashflow(), loadActions()]);
    } finally { setLoading(false); }
  }, [loadDashboard, loadTax, loadCashflow, loadActions]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const triggerCompute = async (what: 'tax' | 'cashflow') => {
    setComputing(c => ({ ...c, [what]: true }));
    try {
      if (what === 'tax') {
        await apiClient.post(`/api/v1/finance-agent/tax/compute/${STORE_ID}`, null, {
          params: { period, force: true },
        });
        await loadTax();
      } else {
        await apiClient.post(`/api/v1/finance-agent/cashflow/compute/${STORE_ID}`, null, {
          params: { force: true },
        });
        await loadCashflow();
      }
      await loadDashboard();
    } catch (e) { handleApiError(e); }
    finally { setComputing(c => ({ ...c, [what]: false })); }
  };

  const respondAction = async (actionId: string, action: 'accepted' | 'dismissed') => {
    try {
      await apiClient.post(`/api/v1/finance-agent/actions/${actionId}/respond`, { action });
      await loadActions();
      await loadDashboard();
    } catch (e) { handleApiError(e); }
  };

  // ── Cashflow line chart ───────────────────────────────────────────────────

  const cashflowOption = useMemo(() => {
    if (!cashflows.length) return {};
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['入账', '出账', '余额'], textStyle: { fontSize: 11 } },
      grid: { top: 32, bottom: 40, left: 70, right: 20 },
      xAxis: {
        type: 'category',
        data: cashflows.map(f => f.forecast_date.slice(5)),
        axisLabel: { fontSize: 10, rotate: 45, interval: 4 },
      },
      yAxis: [
        {
          type: 'value',
          name: '金额(元)',
          axisLabel: { fontSize: 10, formatter: (v: number) => `${(v / 1000).toFixed(0)}k` },
        },
      ],
      series: [
        {
          name: '入账',
          type: 'bar',
          data: cashflows.map(f => f.inflow_yuan),
          itemStyle: { color: 'rgba(82, 196, 26, 0.7)' },
          barMaxWidth: 8,
        },
        {
          name: '出账',
          type: 'bar',
          data: cashflows.map(f => -f.outflow_yuan),
          itemStyle: { color: 'rgba(245, 34, 45, 0.6)' },
          barMaxWidth: 8,
        },
        {
          name: '余额',
          type: 'line',
          data: cashflows.map(f => f.balance_yuan),
          lineStyle: { color: '#FF6B2C', width: 2 },
          itemStyle: { color: '#FF6B2C' },
          symbolSize: 0,
          areaStyle: {
            color: {
              type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(255, 107, 44, 0.15)' },
                { offset: 1, color: 'rgba(255, 107, 44, 0)' },
              ],
            },
          },
          markLine: {
            data: [{ yAxis: 0, lineStyle: { color: '#f5222d', width: 1.5, type: 'dashed' } }],
            label: { formatter: '零线' },
          },
        },
      ],
    };
  }, [cashflows]);

  const d = dashboard;
  const gapDays = cashflows.filter(f => f.balance_yuan < 0).length;
  const minBalance = cashflows.length ? Math.min(...cashflows.map(f => f.balance_yuan)) : 0;
  const totalTax = taxResults.reduce((s, r) => s + r.tax_amount_yuan, 0);
  const pendingCount = actions.filter(a => a.status === 'pending').length;

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>CFO 工作台</h1>
          <p className={styles.pageSub}>税务智能 · 现金流预测 · Agent 动作 · {period}</p>
        </div>
        <div className={styles.headerActions}>
          <ZButton onClick={() => triggerCompute('tax')}    disabled={computing['tax']}>
            {computing['tax'] ? '计算中…' : '重算税务'}
          </ZButton>
          <ZButton onClick={() => triggerCompute('cashflow')} disabled={computing['cashflow']}>
            {computing['cashflow'] ? '预测中…' : '刷新预测'}
          </ZButton>
          <ZButton onClick={loadAll}>刷新</ZButton>
        </div>
      </div>

      {/* KPI row */}
      <div className={styles.kpiGrid}>
        {loading && !d ? (
          [...Array(4)].map((_, i) => <ZSkeleton key={i} height={88} />)
        ) : (
          <>
            <ZCard>
              <ZKpi label="应纳税合计" value={`¥${totalTax.toFixed(0)}`} />
              <div className={taxResults.some(r => r.risk_level === 'high' || r.risk_level === 'critical') ? styles.kpiSubWarn : styles.kpiSub}>
                {d?.tax?.max_risk === 'high' || d?.tax?.max_risk === 'critical'
                  ? `⚠ 偏差 ¥${Math.abs(d?.tax?.total_deviation_yuan ?? 0).toFixed(0)}`
                  : `${taxResults.length} 个税种`}
              </div>
            </ZCard>
            <ZCard>
              <ZKpi label="30天净现金流" value={`¥${(d?.cashflow?.total_net_yuan ?? 0).toFixed(0)}`} />
              <div className={gapDays > 0 ? styles.kpiSubWarn : styles.kpiSub}>
                {gapDays > 0 ? `⚠ ${gapDays}天资金缺口` : '无资金缺口'}
              </div>
            </ZCard>
            <ZCard>
              <ZKpi label="预测最低余额"
                value={`¥${minBalance.toFixed(0)}`}
              />
              <div className={minBalance < 0 ? styles.kpiSubWarn : styles.kpiSub}>
                {minBalance < 0 ? '建议提前融资' : '资金状态良好'}
              </div>
            </ZCard>
            <ZCard>
              <ZKpi label="待处理 Agent 动作" value={pendingCount} unit="条" />
              <div className={pendingCount > 0 ? styles.kpiSubWarn : styles.kpiSub}>
                {pendingCount > 0 ? '需人工确认' : '全部已处理'}
              </div>
            </ZCard>
          </>
        )}
      </div>

      {/* Tab section */}
      <ZCard>
        <div className={styles.tabBar}>
          {(['tax', 'cashflow', 'actions'] as const).map(tab => (
            <button
              key={tab}
              className={`${styles.tab} ${activeTab === tab ? styles.tabActive : ''}`}
              onClick={() => setActiveTab(tab)}
            >
              {{ tax: '税务计算', cashflow: '现金流预测', actions: `Agent 动作${pendingCount > 0 ? ` (${pendingCount})` : ''}` }[tab]}
            </button>
          ))}
        </div>

        {/* Tax table */}
        {activeTab === 'tax' && (
          loading ? <ZSkeleton height={200} /> :
          taxResults.length > 0 ? (
            <>
              <ZTable columns={taxColumns} data={taxResults} rowKey="tax_type" />
              <div className={styles.taxNote}>
                * 应纳税额为系统估算，以税务机关最终核定为准。偏差=应纳−已申报。
              </div>
            </>
          ) : <ZEmpty text="暂无税务计算结果，请点击「重算税务」" />
        )}

        {/* Cashflow chart */}
        {activeTab === 'cashflow' && (
          loading ? <ZSkeleton height={320} /> :
          cashflows.length > 0 ? (
            <div>
              <div className={styles.chart}>
                <ReactECharts option={cashflowOption} style={{ height: '100%' }} />
              </div>
              {gapDays > 0 && (
                <div className={styles.gapAlert}>
                  ⚠ 未来 {cashflows.length} 天内预计有 {gapDays} 天出现资金缺口，最低余额 ¥{minBalance.toFixed(2)}
                </div>
              )}
            </div>
          ) : <ZEmpty text="暂无现金流预测，请点击「刷新预测」" />
        )}

        {/* Agent actions */}
        {activeTab === 'actions' && (
          loading ? <ZSkeleton height={200} /> :
          actions.length > 0 ? (
            <div>
              {actions.map(a => (
                <div key={a.id} className={`${styles.actionCard} ${a.status !== 'pending' ? styles.actionDone : ''}`}>
                  <div className={styles.actionHeader}>
                    <span className={`${styles.levelBadge} ${styles[`level${a.action_level}`]}`}>
                      {a.action_level}
                    </span>
                    <span className={styles.agentName}>{a.agent_name}</span>
                    <span className={styles.actionTitle}>{a.title}</span>
                    <span style={{ flex: 1 }} />
                    <span className={a.expected_impact_yuan >= 0 ? styles.amountGreen : styles.amount}>
                      ¥{a.expected_impact_yuan.toFixed(2)}
                    </span>
                  </div>
                  {a.description && (
                    <div className={styles.actionDesc}>{a.description}</div>
                  )}
                  {a.status === 'pending' && (
                    <div className={styles.actionBtns}>
                      <ZButton onClick={() => respondAction(a.id, 'accepted')}>接受建议</ZButton>
                      <ZButton onClick={() => respondAction(a.id, 'dismissed')}>忽略</ZButton>
                    </div>
                  )}
                  {a.status !== 'pending' && (
                    <div className={styles.actionStatus}>
                      {a.status === 'accepted' ? '✓ 已接受' : '— 已忽略'}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : <ZEmpty text="暂无 Agent 动作记录" />
        )}
      </ZCard>
    </div>
  );
};

export default TaxCashflowPage;
