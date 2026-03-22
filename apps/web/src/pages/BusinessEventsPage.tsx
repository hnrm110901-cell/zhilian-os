import React, { useState, useEffect, useCallback, useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZTable, ZEmpty } from '../design-system/components';
import type { ZTableColumn } from '../design-system/components';
import { apiClient, handleApiError } from '../services/api';
import styles from './BusinessEventsPage.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

interface EventType {
  type: string;
  label: string;
  profit_relevant: boolean;
}

interface BusinessEvent {
  id: string;
  store_id: string;
  event_type: string;
  event_type_label: string;
  event_subtype: string | null;
  source_system: string;
  source_event_id: string | null;
  amount_yuan: number;
  period: string;
  event_date: string;
  status: string;
  created_at: string | null;
}

interface EventStats {
  store_id: string;
  period: string;
  total_events: number;
  by_type: Record<string, {
    label: string;
    event_count: number;
    total_yuan: number;
    first_date: string | null;
    last_date: string | null;
  }>;
  summary: {
    total_sale_yuan: number;
    total_cost_yuan: number;
    estimated_profit_yuan: number;
  };
}

interface ProfitAttribution {
  store_id: string;
  period: string;
  calc_date: string;
  revenue: { gross_revenue_yuan: number; refund_yuan: number; net_revenue_yuan: number };
  costs: {
    food_cost_yuan: number;
    waste_cost_yuan: number;
    platform_commission_yuan: number;
    labor_cost_yuan: number;
    other_expense_yuan: number;
    total_cost_yuan: number;
  };
  profit: { gross_profit_yuan: number; profit_margin_pct: number };
  event_count: number;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const STORE_ID = localStorage.getItem('store_id') || 'store-demo-001';
const STATUS_BADGE: Record<string, 'neutral' | 'warning' | 'success' | 'error'> = {
  raw:        'neutral',
  mapped:     'warning',
  attributed: 'success',
  archived:   'neutral',
};
const STATUS_LABELS: Record<string, string> = {
  raw: '待处理', mapped: '已映射', attributed: '已归因', archived: '已归档',
};
const SOURCE_COLORS: Record<string, string> = {
  pos: '#FF6B2C', meituan: '#FF4D00', eleme: '#0FC0FC',
  wechat_pay: '#07C160', erp: '#722ED1', manual: '#8C8C8C', system: '#1890FF',
};

// ── Event stream columns ──────────────────────────────────────────────────────

const eventColumns: ZTableColumn<BusinessEvent>[] = [
  {
    key: 'event_date',
    title: '日期',
    render: (v) => <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>{v}</span>,
  },
  {
    key: 'event_type_label',
    title: '事件类型',
    render: (v, row) => (
      <span>
        {v}
        {row.event_subtype && (
          <span style={{ color: 'var(--text-secondary)', fontSize: 11, marginLeft: 4 }}>
            · {row.event_subtype}
          </span>
        )}
      </span>
    ),
  },
  {
    key: 'source_system',
    title: '来源',
    align: 'center',
    render: (v) => (
      <span style={{
        background: SOURCE_COLORS[v] || '#8C8C8C',
        color: '#fff',
        borderRadius: 4,
        padding: '2px 6px',
        fontSize: 11,
        fontWeight: 600,
      }}>
        {v}
      </span>
    ),
  },
  {
    key: 'amount_yuan',
    title: '金额',
    align: 'right',
    render: (v) => (
      <span style={{
        fontWeight: 700,
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 12,
        color: v > 0 ? 'var(--accent, #FF6B2C)' : '#8C8C8C',
      }}>
        ¥{Number(v).toFixed(2)}
      </span>
    ),
  },
  {
    key: 'status',
    title: '状态',
    align: 'center',
    render: (v) => <ZBadge type={STATUS_BADGE[v] || 'neutral'} text={STATUS_LABELS[v] || v} />,
  },
];

// ── Component ─────────────────────────────────────────────────────────────────

const BusinessEventsPage: React.FC = () => {
  // Today and current month defaults
  const today = new Date().toISOString().slice(0, 10);
  const currentMonth = today.slice(0, 7);
  const monthStart = `${currentMonth}-01`;

  const [eventTypes, setEventTypes]       = useState<EventType[]>([]);
  const [events, setEvents]               = useState<BusinessEvent[]>([]);
  const [eventTotal, setEventTotal]       = useState(0);
  const [stats, setStats]                 = useState<EventStats | null>(null);
  const [attribution, setAttribution]     = useState<ProfitAttribution | null>(null);
  const [loading, setLoading]             = useState(false);
  const [computing, setComputing]         = useState(false);
  const [activeTab, setActiveTab]         = useState<'stream' | 'stats' | 'profit'>('profit');
  const [filterType, setFilterType]       = useState('');
  const [dateFrom]                        = useState(monthStart);
  const [dateTo]                          = useState(today);
  const [period]                          = useState(currentMonth);

  const loadEventTypes = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/events/types');
      setEventTypes(res.data.event_types || []);
    } catch (e) { handleApiError(e); }
  }, []);

  const loadStream = useCallback(async () => {
    try {
      const params: Record<string, string | number> = {
        store_id: STORE_ID, date_from: dateFrom, date_to: dateTo,
        limit: 100, offset: 0,
      };
      if (filterType) params.event_type = filterType;
      const res = await apiClient.get('/api/v1/events/stream', { params });
      setEvents(res.data.events || []);
      setEventTotal(res.data.total || 0);
    } catch (e) { handleApiError(e); }
  }, [dateFrom, dateTo, filterType]);

  const loadStats = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/events/stats', {
        params: { store_id: STORE_ID, period },
      });
      setStats(res.data);
    } catch (e) { handleApiError(e); }
  }, [period]);

  const loadAttribution = useCallback(async () => {
    try {
      const res = await apiClient.get(`/api/v1/events/profit/attribution/${STORE_ID}`, {
        params: { period },
      });
      setAttribution(res.data);
    } catch (e) { handleApiError(e); }
  }, [period]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.allSettled([loadStream(), loadStats(), loadAttribution()]);
    } finally { setLoading(false); }
  }, [loadStream, loadStats, loadAttribution]);

  useEffect(() => { loadEventTypes(); loadAll(); }, [loadEventTypes, loadAll]);

  const computeProfit = async () => {
    setComputing(true);
    try {
      await apiClient.post(`/api/v1/events/profit/compute/${STORE_ID}`, null, {
        params: { period },
      });
      await loadAttribution();
    } catch (e) { handleApiError(e); }
    finally { setComputing(false); }
  };

  // ── Profit waterfall chart ─────────────────────────────────────────────────

  const waterfallOption = useMemo(() => {
    if (!attribution) return {};
    const { revenue, costs, profit } = attribution;
    const items = [
      { name: '销售收入',   value: revenue.gross_revenue_yuan,       color: '#1A7A52' },
      { name: '退款',       value: -revenue.refund_yuan,             color: '#C53030' },
      { name: '食材成本',   value: -costs.food_cost_yuan,            color: '#C8923A' },
      { name: '损耗',       value: -costs.waste_cost_yuan,           color: '#fa541c' },
      { name: '平台抽佣',   value: -costs.platform_commission_yuan,  color: '#722ed1' },
      { name: '人工费用',   value: -costs.labor_cost_yuan,           color: '#FF6B2C' },
      { name: '其他费用',   value: -costs.other_expense_yuan,        color: '#13c2c2' },
      { name: '毛利润',     value: profit.gross_profit_yuan,         color: profit.gross_profit_yuan >= 0 ? '#FF6B2C' : '#C53030' },
    ];
    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          const p = params[0];
          return `${p.name}<br/>¥${Math.abs(p.value).toFixed(2)}`;
        },
      },
      grid: { top: 12, bottom: 40, left: 70, right: 12 },
      xAxis: {
        type: 'category',
        data: items.map(i => i.name),
        axisLabel: { fontSize: 11, rotate: 30 },
      },
      yAxis: { type: 'value', axisLabel: { fontSize: 11, formatter: (v: number) => `¥${(v/1000).toFixed(0)}k` } },
      series: [{
        type: 'bar',
        data: items.map(i => ({
          value: i.value,
          itemStyle: { color: i.color },
        })),
        barMaxWidth: 40,
      }],
    };
  }, [attribution]);

  // ── Stats donut chart ─────────────────────────────────────────────────────

  const donutOption = useMemo(() => {
    if (!stats) return {};
    const data = Object.entries(stats.by_type).map(([type, v]) => ({
      name: v.label,
      value: v.event_count,
    }));
    return {
      tooltip: { trigger: 'item' },
      series: [{
        type: 'pie',
        radius: ['50%', '75%'],
        data,
        label: { fontSize: 11 },
      }],
    };
  }, [stats]);

  const attr = attribution;

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>经营事件中心</h1>
          <p className={styles.pageSub}>
            经营事件流水 · 利润归因分析 · {period}
          </p>
        </div>
        <div className={styles.headerActions}>
          <ZButton onClick={computeProfit} disabled={computing}>
            {computing ? '计算中…' : '重新归因'}
          </ZButton>
          <ZButton onClick={loadAll}>刷新</ZButton>
        </div>
      </div>

      {/* KPI row */}
      <div className={styles.kpiGrid}>
        {loading && !attr ? (
          [...Array(4)].map((_, i) => <ZSkeleton key={i} height={88} />)
        ) : attr ? (
          <>
            <ZCard>
              <ZKpi label="净收入" value={`¥${attr.revenue.net_revenue_yuan.toFixed(0)}`} />
              <div className={styles.kpiSub}>
                总销售 ¥{attr.revenue.gross_revenue_yuan.toFixed(0)}
              </div>
            </ZCard>
            <ZCard>
              <ZKpi label="总成本" value={`¥${attr.costs.total_cost_yuan.toFixed(0)}`} />
              <div className={styles.kpiSub}>
                食材 ¥{attr.costs.food_cost_yuan.toFixed(0)} + 损耗 ¥{attr.costs.waste_cost_yuan.toFixed(0)}
              </div>
            </ZCard>
            <ZCard>
              <ZKpi
                label="毛利润"
                value={`¥${attr.profit.gross_profit_yuan.toFixed(0)}`}
              />
              <div className={attr.profit.gross_profit_yuan >= 0 ? styles.kpiSub : styles.kpiSubWarn}>
                利润率 {attr.profit.profit_margin_pct.toFixed(1)}%
              </div>
            </ZCard>
            <ZCard>
              <ZKpi label="归因事件" value={attr.event_count.toLocaleString()} unit="条" />
              <div className={styles.kpiSub}>平台抽佣 ¥{attr.costs.platform_commission_yuan.toFixed(0)}</div>
            </ZCard>
          </>
        ) : null}
      </div>

      {/* Tab section */}
      <ZCard>
        <div className={styles.tabBar}>
          {(['profit', 'stats', 'stream'] as const).map(tab => (
            <button
              key={tab}
              className={`${styles.tab} ${activeTab === tab ? styles.tabActive : ''}`}
              onClick={() => setActiveTab(tab)}
            >
              {{ profit: '利润归因', stats: '事件统计', stream: '事件流水' }[tab]}
            </button>
          ))}
        </div>

        {/* Profit waterfall */}
        {activeTab === 'profit' && (
          loading ? <ZSkeleton height={280} /> :
          attr ? (
            <div>
              <div className={styles.chart}>
                <ReactECharts option={waterfallOption} style={{ height: '100%' }} />
              </div>
              {attr.costs.food_cost_yuan > 0 && attr.revenue.net_revenue_yuan > 0 && (
                <div className={styles.costRateRow}>
                  <span className={styles.costRateItem}>
                    食材成本率{' '}
                    <b>{((attr.costs.food_cost_yuan / attr.revenue.net_revenue_yuan) * 100).toFixed(1)}%</b>
                  </span>
                  <span className={styles.costRateItem}>
                    损耗率{' '}
                    <b>{((attr.costs.waste_cost_yuan / attr.revenue.net_revenue_yuan) * 100).toFixed(1)}%</b>
                  </span>
                  <span className={styles.costRateItem}>
                    平台抽佣率{' '}
                    <b>{((attr.costs.platform_commission_yuan / attr.revenue.net_revenue_yuan) * 100).toFixed(1)}%</b>
                  </span>
                </div>
              )}
            </div>
          ) : <ZEmpty text="暂无利润归因数据，请点击「重新归因」" />
        )}

        {/* Stats donut */}
        {activeTab === 'stats' && (
          loading ? <ZSkeleton height={280} /> :
          stats ? (
            <div className={styles.statsLayout}>
              <div className={styles.donut}>
                <ReactECharts option={donutOption} style={{ height: '100%' }} />
              </div>
              <div className={styles.statsTable}>
                {Object.entries(stats.by_type).map(([type, v]) => (
                  <div key={type} className={styles.statsRow}>
                    <span className={styles.statsLabel}>{v.label}</span>
                    <span className={styles.statsCount}>{v.event_count} 条</span>
                    <span className={styles.statsAmount}>¥{v.total_yuan.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : <ZEmpty text="暂无统计数据" />
        )}

        {/* Event stream */}
        {activeTab === 'stream' && (
          <div>
            <div className={styles.streamFilter}>
              <select
                className={styles.typeSelect}
                value={filterType}
                onChange={e => setFilterType(e.target.value)}
              >
                <option value="">全部类型</option>
                {eventTypes.map(t => (
                  <option key={t.type} value={t.type}>{t.label}</option>
                ))}
              </select>
              <span className={styles.totalCount}>共 {eventTotal} 条</span>
            </div>
            {loading ? <ZSkeleton height={200} /> :
             events.length > 0 ? (
               <ZTable columns={eventColumns} data={events} rowKey="id" />
             ) : <ZEmpty text="暂无事件记录" />
            }
          </div>
        )}
      </ZCard>

      {/* Event types reference */}
      <ZCard title="支持的事件类型">
        <div className={styles.typeGrid}>
          {eventTypes.map(t => (
            <div key={t.type} className={styles.typeCard}>
              <span className={styles.typeCode}>{t.type}</span>
              <span className={styles.typeLabel}>{t.label}</span>
              {t.profit_relevant && (
                <span className={styles.profitTag}>利润归因</span>
              )}
            </div>
          ))}
        </div>
      </ZCard>
    </div>
  );
};

export default BusinessEventsPage;
