/**
 * 总部宴会仪表盘（三标签）
 * 路由：/hq/banquet
 * Tab1 仪表盘：GET /api/v1/banquet-agent/stores/{id}/dashboard?year=&month=
 *              GET /api/v1/banquet-lifecycle/{id}/funnel
 *              GET /api/v1/banquet-agent/stores/{id}/orders?status=confirmed
 * Tab2 销售管道：GET /api/v1/banquet-lifecycle/{store_id}/pipeline
 * Tab3 销控日历：GET /api/v1/banquet-lifecycle/{store_id}/availability/{year}/{month}
 */
import React, { useEffect, useState, useCallback } from 'react';
import dayjs from 'dayjs';
import {
  ZCard, ZKpi, ZBadge, ZSkeleton, ZEmpty, ZSelect, ZTabs, ZButton, ZInput, ZModal,
} from '../../design-system/components';
import apiClient from '../../services/api';
import { handleApiError } from '../../utils/message';
import styles from './Banquet.module.css';
import ReactECharts from 'echarts-for-react';

const STORE_ID = localStorage.getItem('store_id') || 'S001';

/* ─── 类型 ─── */
interface DashboardData {
  store_id:         string;
  year:             number;
  month:            number;
  revenue_yuan:     number;
  gross_margin_pct: number;
  order_count:      number;
  conversion_rate:  number;
  room_utilization: number;
}

interface FunnelStage {
  stage:       string;
  stage_label: string;
  count:       number;
}

interface FunnelData {
  stages: FunnelStage[];
  total:  number;
}

interface BanquetOrder {
  banquet_id:    string;
  banquet_type:  string;
  banquet_date:  string;
  table_count:   number;
  amount_yuan:   number;
  status:        string;
}

interface PipelineLead {
  banquet_id:    string;
  banquet_type:  string;
  expected_date: string;
  contact_name:  string | null;
  amount_yuan:   number | null;
}

interface PipelineStage {
  stage:       string;
  stage_label: string;
  count:       number;
  leads:       PipelineLead[];
}

interface CalendarDay {
  date:            string;
  confirmed_count: number;
  locked_count:    number;
  capacity:        number;
  is_auspicious:   boolean;
}

/* ─── 工具函数 ─── */
function buildMonthOptions() {
  return Array.from({ length: 6 }, (_, i) => {
    const m = dayjs().subtract(i, 'month').format('YYYY-MM');
    return { value: m, label: m };
  });
}

const ORDER_STATUS_MAP: Record<string, { text: string; type: 'success' | 'info' | 'warning' | 'default' }> = {
  confirmed: { text: '已确认', type: 'success' },
  pending:   { text: '待确认', type: 'warning' },
  completed: { text: '已完成', type: 'info'    },
  cancelled: { text: '已取消', type: 'default' },
};

/* ─── Tab1：仪表盘 ─── */
function DashboardTab() {
  const [month,         setMonth]         = useState(dayjs().format('YYYY-MM'));
  const [dashboard,     setDashboard]     = useState<DashboardData | null>(null);
  const [funnel,        setFunnel]        = useState<FunnelData | null>(null);
  const [orders,        setOrders]        = useState<BanquetOrder[]>([]);
  const [loadingKpi,    setLoadingKpi]    = useState(true);
  const [loadingFunnel, setLoadingFunnel] = useState(true);
  const [loadingOrders, setLoadingOrders] = useState(true);
  const [syncing,       setSyncing]       = useState(false);
  const [trend,         setTrend]         = useState<{ month: string; revenue_yuan: number; order_count: number; gross_profit_yuan: number }[]>([]);

  // 月度目标
  const [targetYuan,    setTargetYuan]    = useState<number | null>(null);
  const [targetOpen,    setTargetOpen]    = useState(false);
  const [targetInput,   setTargetInput]   = useState('');
  const [savingTarget,  setSavingTarget]  = useState(false);
  const [targetProgress, setTargetProgress] = useState<{
    achievement_pct: number; gap_yuan: number;
    daily_needed_yuan: number; run_rate_yuan: number; on_track: boolean;
  } | null>(null);
  const [targetTrend, setTargetTrend] = useState<{ month: string; target_yuan: number; actual_yuan: number }[]>([]);

  const loadDashboard = useCallback(async (m: string) => {
    setLoadingKpi(true);
    const [year, mon] = m.split('-').map(Number);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/dashboard`,
        { params: { year, month: mon } },
      );
      setDashboard(resp);
    } catch (e) {
      handleApiError(e, '宴会仪表盘加载失败');
      setDashboard(null);
    } finally {
      setLoadingKpi(false);
    }
  }, []);

  const loadFunnel = useCallback(async () => {
    setLoadingFunnel(true);
    try {
      const resp = await apiClient.get(`/api/v1/banquet-lifecycle/${STORE_ID}/funnel`);
      setFunnel(resp);
    } catch {
      setFunnel(null);
    } finally {
      setLoadingFunnel(false);
    }
  }, []);

  const loadOrders = useCallback(async () => {
    setLoadingOrders(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/orders`,
        { params: { status: 'confirmed' } },
      );
      setOrders(Array.isArray(resp) ? resp : (resp?.items ?? []));
    } catch {
      setOrders([]);
    } finally {
      setLoadingOrders(false);
    }
  }, []);

  useEffect(() => { loadDashboard(month); }, [loadDashboard, month]);
  useEffect(() => {
    loadFunnel();
    loadOrders();
    apiClient.get(`/api/v1/banquet-agent/stores/${STORE_ID}/analytics/monthly-trend`, { params: { months: 6 } })
      .then(r => setTrend(r.data?.months ?? []))
      .catch(() => setTrend([]));
  }, [loadFunnel, loadOrders]);

  useEffect(() => {
    const [y, m] = month.split('-').map(Number);
    apiClient.get(`/api/v1/banquet-agent/stores/${STORE_ID}/revenue-targets/${y}/${m}`)
      .then(r => setTargetYuan(r.data?.target_yuan ?? null))
      .catch(() => setTargetYuan(null));
    apiClient.get(`/api/v1/banquet-agent/stores/${STORE_ID}/analytics/target-progress`, { params: { year: y, month: m } })
      .then(r => setTargetProgress(r.data))
      .catch(() => setTargetProgress(null));
    apiClient.get(`/api/v1/banquet-agent/stores/${STORE_ID}/analytics/target-trend`, { params: { months: 6 } })
      .then(r => setTargetTrend(r.data?.months ?? []))
      .catch(() => setTargetTrend([]));
  }, [month]);

  const syncKpi = async () => {
    setSyncing(true);
    try {
      await apiClient.post(
        `/api/v1/banquet-agent/stores/${STORE_ID}/kpi/sync`,
        null,
        { params: { sync_date: dayjs().format('YYYY-MM-DD') } },
      );
      await loadDashboard(month);
    } catch (e) {
      handleApiError(e, 'KPI 同步失败');
    } finally {
      setSyncing(false);
    }
  };

  const saveTarget = async () => {
    const v = parseFloat(targetInput);
    if (!v || v <= 0) return;
    setSavingTarget(true);
    try {
      const [y, m] = month.split('-').map(Number);
      await apiClient.put(
        `/api/v1/banquet-agent/stores/${STORE_ID}/revenue-targets/${y}/${m}`,
        { target_yuan: v },
      );
      setTargetYuan(v);
      setTargetOpen(false);
    } catch (e) {
      handleApiError(e, '保存目标失败');
    } finally {
      setSavingTarget(false);
    }
  };

  const d = dashboard;

  return (
    <div className={styles.tabContent}>
      <div className={styles.tabHeader}>
        <ZSelect
          value={month}
          options={buildMonthOptions()}
          onChange={(v) => setMonth(v as string)}
          style={{ width: 120 }}
        />
        <ZButton variant="ghost" size="sm" onClick={syncKpi} disabled={syncing}>
          {syncing ? '同步中…' : '同步今日 KPI'}
        </ZButton>
      </div>

      {loadingKpi ? (
        <div className={styles.kpiRow}><ZSkeleton rows={2} /></div>
      ) : !d ? (
        <ZCard><ZEmpty title="暂无本月数据" description="请确认已接入宴会模块" /></ZCard>
      ) : (
        <div className={styles.kpiRow}>
          <ZCard>
            <ZKpi value={`¥${(d.revenue_yuan / 10000).toFixed(1)}万`} label="本月营收" />
          </ZCard>
          <ZCard>
            <ZKpi value={d.gross_margin_pct.toFixed(1)} label="毛利率" unit="%" />
          </ZCard>
          <ZCard>
            <ZKpi value={d.order_count} label="订单数" unit="单" />
          </ZCard>
          <ZCard>
            <ZKpi value={d.conversion_rate.toFixed(1)} label="线索转化率" unit="%" />
          </ZCard>
        </div>
      )}

      <ZCard title="销售漏斗">
        {loadingFunnel ? (
          <ZSkeleton rows={4} />
        ) : !funnel?.stages?.length ? (
          <ZEmpty title="暂无漏斗数据" />
        ) : (
          <div className={styles.funnel}>
            {funnel.stages.map((stage) => {
              const pct = funnel.total > 0
                ? Math.round((stage.count / funnel.total) * 100)
                : 0;
              return (
                <div key={stage.stage} className={styles.funnelRow}>
                  <div className={styles.funnelLabel}>{stage.stage_label}</div>
                  <div className={styles.funnelBarWrap}>
                    <div className={styles.funnelBar} style={{ width: `${pct}%` }} />
                  </div>
                  <div className={styles.funnelCount}>{stage.count}</div>
                </div>
              );
            })}
          </div>
        )}
      </ZCard>

      <ZCard title="近期确认订单" subtitle={`门店 ${STORE_ID}`}>
        {loadingOrders ? (
          <ZSkeleton rows={4} />
        ) : !orders.length ? (
          <ZEmpty title="暂无确认订单" />
        ) : (
          <div className={styles.table}>
            <div className={styles.thead}>
              <span>类型</span>
              <span>日期</span>
              <span>桌数</span>
              <span>金额</span>
              <span>状态</span>
            </div>
            {orders.map((order) => {
              const s = ORDER_STATUS_MAP[order.status] ?? { text: order.status, type: 'default' as const };
              return (
                <div key={order.banquet_id} className={styles.trow}>
                  <span className={styles.tdType}>{order.banquet_type}</span>
                  <span className={styles.tdDate}>{dayjs(order.banquet_date).format('MM-DD')}</span>
                  <span className={styles.tdTable}>{order.table_count}桌</span>
                  <span className={styles.tdAmount}>¥{order.amount_yuan.toLocaleString()}</span>
                  <span><ZBadge type={s.type} text={s.text} /></span>
                </div>
              );
            })}
          </div>
        )}
      </ZCard>

      {/* 6 个月营收走势 */}
      {trend.length > 0 && (() => {
        const trendOption = {
          tooltip: { trigger: 'axis' as const },
          legend: { data: ['营收（万）', '毛利（万）', '订单数'], bottom: 0, textStyle: { fontSize: 11 } },
          grid: { left: 50, right: 20, top: 20, bottom: 50 },
          xAxis: { type: 'category' as const, data: trend.map(t => t.month.slice(5)) },
          yAxis: [
            { type: 'value' as const, name: '万元', axisLabel: { formatter: (v: number) => `${(v / 10000).toFixed(0)}` } },
            { type: 'value' as const, name: '单', min: 0 },
          ],
          series: [
            {
              name: '营收（万）',
              type: 'line' as const,
              yAxisIndex: 0,
              data: trend.map(t => t.revenue_yuan),
              smooth: true,
              itemStyle: { color: '#0AAF9A' },
              lineStyle: { width: 2 },
            },
            {
              name: '毛利（万）',
              type: 'line' as const,
              yAxisIndex: 0,
              data: trend.map(t => t.gross_profit_yuan),
              smooth: true,
              itemStyle: { color: '#3b82f6' },
              lineStyle: { width: 2, type: 'dashed' as const },
            },
            {
              name: '订单数',
              type: 'bar' as const,
              yAxisIndex: 1,
              data: trend.map(t => t.order_count),
              itemStyle: { color: 'rgba(100,180,100,0.4)' },
              barMaxWidth: 24,
            },
          ],
        };
        return (
          <ZCard title="近 6 个月营收走势">
            <ReactECharts option={trendOption} style={{ height: 220 }} />
          </ZCard>
        );
      })()}

      {/* 本月营收目标 */}
      <ZCard>
        <div className={styles.targetHeader}>
          <div className={styles.sectionTitle}>本月目标</div>
          <ZButton variant="ghost" size="sm" onClick={() => { setTargetInput(String(targetYuan ?? '')); setTargetOpen(true); }}>
            {targetYuan !== null ? '编辑目标' : '设置目标'}
          </ZButton>
        </div>
        {targetYuan === null ? (
          <div className={styles.targetEmpty}>未设置本月营收目标</div>
        ) : (() => {
          const actual = dashboard?.revenue_yuan ?? 0;
          const pct = Math.min(100, targetYuan > 0 ? (actual / targetYuan) * 100 : 0);
          const barColor = pct >= 80 ? '#22c55e' : pct >= 60 ? '#f97316' : '#ef4444';
          return (
            <div className={styles.targetBody}>
              <div className={styles.targetMeta}>
                <span>目标：¥{(targetYuan / 10000).toFixed(1)}万</span>
                <span>实际：¥{(actual / 10000).toFixed(1)}万</span>
                <span style={{ color: barColor, fontWeight: 700 }}>{pct.toFixed(1)}%</span>
              </div>
              <div className={styles.targetBarBg}>
                <div className={styles.targetBarFill} style={{ width: `${pct}%`, background: barColor }} />
              </div>
              {targetProgress && (
                <div className={styles.targetInsights}>
                  <span className={targetProgress.on_track ? styles.onTrack : styles.offTrack}>
                    {targetProgress.on_track ? '✓ 按目标进行' : '⚠ 低于目标进度'}
                  </span>
                  {!targetProgress.on_track && targetProgress.daily_needed_yuan > 0 && (
                    <span className={styles.dailyNeeded}>
                      需每日完成 ¥{(targetProgress.daily_needed_yuan / 10000).toFixed(1)}万
                    </span>
                  )}
                </div>
              )}
            </div>
          );
        })()}
        {targetTrend.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <ReactECharts
              style={{ height: 140 }}
              option={{
                tooltip: { trigger: 'axis' as const },
                legend: { data: ['目标', '实际'], top: 0, right: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 11 } },
                grid: { left: 50, right: 12, top: 28, bottom: 24 },
                xAxis: { type: 'category' as const, data: targetTrend.map(r => r.month.slice(5)), axisLabel: { fontSize: 11 } },
                yAxis: { type: 'value' as const, axisLabel: { fontSize: 11, formatter: (v: number) => `${(v / 10000).toFixed(0)}万` } },
                series: [
                  { name: '目标', type: 'line' as const, data: targetTrend.map(r => r.target_yuan), itemStyle: { color: '#94a3b8' }, lineStyle: { type: 'dashed' as const } },
                  { name: '实际', type: 'bar' as const,  data: targetTrend.map(r => r.actual_yuan), itemStyle: { color: 'var(--accent, #0AAF9A)' } },
                ],
              }}
            />
          </div>
        )}
      </ZCard>

      {/* 月度目标设置 Modal */}
      <ZModal
        open={targetOpen}
        title="设置月度营收目标"
        onClose={() => setTargetOpen(false)}
        footer={
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <ZButton variant="ghost" onClick={() => setTargetOpen(false)}>取消</ZButton>
            <ZButton variant="primary" onClick={saveTarget} disabled={savingTarget || !targetInput}>
              {savingTarget ? '保存中…' : '确认'}
            </ZButton>
          </div>
        }
      >
        <div style={{ padding: '8px 0' }}>
          <label style={{ fontSize: 13, color: 'var(--text-secondary)', display: 'block', marginBottom: 6 }}>目标营收（元）</label>
          <ZInput
            type="number"
            value={targetInput}
            onChange={v => setTargetInput(v)}
            placeholder="如：500000"
          />
        </div>
      </ZModal>
    </div>
  );
}

/* ─── Tab2：销售管道 ─── */
function PipelineTab() {
  const [pipeline,  setPipeline]  = useState<PipelineStage[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [expanded,  setExpanded]  = useState<Record<string, boolean>>({});

  useEffect(() => {
    setLoading(true);
    apiClient.get(`/api/v1/banquet-lifecycle/${STORE_ID}/pipeline`)
      .then(resp => {
        const raw = resp.data;
        setPipeline(Array.isArray(raw) ? raw : (raw?.stages ?? []));
      })
      .catch(() => setPipeline([]))
      .finally(() => setLoading(false));
  }, []);

  const toggle = (stage: string) =>
    setExpanded(prev => ({ ...prev, [stage]: !prev[stage] }));

  if (loading) return <div className={styles.tabContent}><ZSkeleton rows={6} /></div>;
  if (!pipeline.length) return (
    <div className={styles.tabContent}>
      <ZEmpty title="暂无管道数据" description="请确认后端 pipeline 接口已就绪" />
    </div>
  );

  return (
    <div className={styles.tabContent}>
      {pipeline.map(stage => (
        <ZCard
          key={stage.stage}
          title={
            <div className={styles.pipelineTitle}>
              <span>{stage.stage_label}</span>
              <ZBadge type="info" text={String(stage.count)} />
            </div>
          }
          extra={
            <button className={styles.expandBtn} onClick={() => toggle(stage.stage)}>
              {expanded[stage.stage] ? '收起 ▲' : '展开 ▼'}
            </button>
          }
        >
          {expanded[stage.stage] && (
            stage.leads.length === 0 ? (
              <ZEmpty title="该阶段暂无线索" />
            ) : (
              <div className={styles.pipelineList}>
                {stage.leads.map(lead => (
                  <div key={lead.banquet_id} className={styles.pipelineRow}>
                    <div className={styles.pipelineInfo}>
                      <div className={styles.pipelineType}>{lead.banquet_type}</div>
                      <div className={styles.pipelineMeta}>
                        {dayjs(lead.expected_date).format('MM-DD')}
                        {lead.contact_name ? ` · ${lead.contact_name}` : ''}
                      </div>
                    </div>
                    {lead.amount_yuan != null && (
                      <span className={styles.pipelineAmount}>
                        ¥{lead.amount_yuan.toLocaleString()}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )
          )}
        </ZCard>
      ))}
    </div>
  );
}

/* ─── Tab3：销控日历 ─── */
const WEEK_DAYS = ['日', '一', '二', '三', '四', '五', '六'];

function AvailabilityTab() {
  const [calMonth, setCalMonth]   = useState(dayjs().format('YYYY-MM'));
  const [days,     setDays]       = useState<CalendarDay[]>([]);
  const [loading,  setLoading]    = useState(true);

  const loadCal = useCallback(async (m: string) => {
    setLoading(true);
    const [year, month] = m.split('-');
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-lifecycle/${STORE_ID}/availability/${year}/${month}`,
      );
      const raw = resp.data;
      setDays(Array.isArray(raw) ? raw : (raw?.days ?? []));
    } catch {
      setDays([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadCal(calMonth); }, [loadCal, calMonth]);

  // Build calendar grid
  const firstDay   = dayjs(`${calMonth}-01`);
  const startDow   = firstDay.day(); // 0=Sun
  const daysInMonth = firstDay.daysInMonth();

  const dayMap: Record<string, CalendarDay> = {};
  days.forEach(d => { dayMap[d.date] = d; });

  const cells: (CalendarDay | null)[] = [
    ...Array(startDow).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => {
      const dateStr = firstDay.add(i, 'day').format('YYYY-MM-DD');
      return dayMap[dateStr] ?? {
        date: dateStr, confirmed_count: 0, locked_count: 0,
        capacity: 0, is_auspicious: false,
      };
    }),
  ];

  // Pad to full rows
  while (cells.length % 7 !== 0) cells.push(null);

  return (
    <div className={styles.tabContent}>
      <div className={styles.calHeader}>
        <ZSelect
          value={calMonth}
          options={buildMonthOptions()}
          onChange={v => setCalMonth(v as string)}
          style={{ width: 120 }}
        />
      </div>

      {loading ? (
        <ZSkeleton rows={6} />
      ) : (
        <ZCard>
          <div className={styles.calGrid}>
            {WEEK_DAYS.map(d => (
              <div key={d} className={styles.calWeekday}>{d}</div>
            ))}
            {cells.map((cell, idx) => {
              if (!cell) return <div key={`empty-${idx}`} className={styles.calEmpty} />;
              const full = cell.capacity > 0 && cell.confirmed_count >= cell.capacity;
              const hasBanquet = cell.confirmed_count > 0 || cell.locked_count > 0;
              return (
                <div
                  key={cell.date}
                  className={[
                    styles.calCell,
                    cell.is_auspicious ? styles.calAuspicious : '',
                    full ? styles.calFull : '',
                  ].join(' ')}
                >
                  <span className={styles.calDay}>
                    {dayjs(cell.date).date()}
                  </span>
                  {hasBanquet && (
                    <div className={styles.calDots}>
                      {cell.confirmed_count > 0 && (
                        <span className={styles.dotConfirmed} title={`已确认 ${cell.confirmed_count}`} />
                      )}
                      {cell.locked_count > 0 && (
                        <span className={styles.dotLocked} title={`锁台 ${cell.locked_count}`} />
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <div className={styles.calLegend}>
            <span className={styles.legendItem}><span className={styles.dotConfirmed} />已确认</span>
            <span className={styles.legendItem}><span className={styles.dotLocked} />锁台</span>
            <span className={styles.legendItem}><span className={styles.legendAuspicious} />吉日</span>
            <span className={styles.legendItem}><span className={styles.legendFull} />满负荷</span>
          </div>
        </ZCard>
      )}
    </div>
  );
}

/* ─── Tab4：AI 建议 ─── */
interface HallRec {
  hall_id:        string | null;
  hall_name?:     string;
  name?:          string;
  hall_type?:     string;
  max_people?:    number | null;
  min_spend_yuan?: number | null;
  min_spend?:     number | null;
}

interface FollowupItem {
  lead_id:    string;
  days_stale: number;
  stage:      string;
  suggestion: string;
}

interface PackageRec {
  package_id:                     string;
  package_name:                   string;
  suggested_price_per_person_yuan: number;
  total_price_yuan:               number;
  estimated_gross_profit_yuan:    number;
  gross_margin_pct:               number;
  banquet_type:                   string;
}

function AITab() {
  const [scanning,      setScanning]      = useState(false);
  const [followups,     setFollowups]     = useState<FollowupItem[] | null>(null);

  const [recPeople,     setRecPeople]     = useState('');
  const [recBudget,     setRecBudget]     = useState('');
  const [recType,       setRecType]       = useState('');
  const [recommending,  setRecommending]  = useState(false);
  const [packages,      setPackages]      = useState<PackageRec[] | null>(null);

  const [hallDate,      setHallDate]      = useState('');
  const [hallPeople,    setHallPeople]    = useState('');
  const [hallSlot,      setHallSlot]      = useState('all_day');
  const [hallLoading,   setHallLoading]   = useState(false);
  const [halls,         setHalls]         = useState<HallRec[] | null>(null);

  const SLOT_OPTIONS = [
    { value: 'all_day', label: '全天' },
    { value: 'lunch',   label: '午宴' },
    { value: 'dinner',  label: '晚宴' },
  ];

  const BANQUET_TYPE_OPTIONS = [
    { value: '',         label: '不限类型' },
    { value: 'wedding',  label: '婚宴' },
    { value: 'birthday', label: '寿宴' },
    { value: 'business', label: '商务宴' },
    { value: 'other',    label: '其他' },
  ];

  const runFollowupScan = useCallback(async () => {
    setScanning(true);
    setFollowups(null);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/agent/followup-scan`,
        { params: { dry_run: true } },
      );
      setFollowups(resp.data?.items ?? []);
    } catch {
      setFollowups([]);
    } finally {
      setScanning(false);
    }
  }, []);

  const runQuoteRecommend = useCallback(async () => {
    const pc = parseInt(recPeople, 10);
    const budget = parseFloat(recBudget);
    if (!pc || !budget) return;
    setRecommending(true);
    setPackages(null);
    try {
      const params: Record<string, string | number> = { people_count: pc, budget_yuan: budget };
      if (recType) params.banquet_type = recType;
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/agent/quote-recommend`,
        { params },
      );
      setPackages(resp.data?.recommendations ?? resp.data ?? []);
    } catch {
      setPackages([]);
    } finally {
      setRecommending(false);
    }
  }, [recPeople, recBudget, recType]);

  const runHallRecommend = useCallback(async () => {
    if (!hallDate || !hallPeople) return;
    setHallLoading(true);
    setHalls(null);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/agent/hall-recommend`,
        { params: { target_date: hallDate, slot_name: hallSlot, people_count: parseInt(hallPeople, 10) } },
      );
      setHalls(resp.data?.available_halls ?? resp.data?.halls ?? resp.data ?? []);
    } catch {
      setHalls([]);
    } finally {
      setHallLoading(false);
    }
  }, [hallDate, hallPeople, hallSlot]);

  return (
    <div className={styles.tabContent}>
      {/* 跟进扫描 */}
      <ZCard>
        <div className={styles.aiSectionHeader}>
          <div className={styles.aiSectionTitle}>跟进扫描</div>
          <ZButton variant="primary" size="sm" onClick={runFollowupScan} disabled={scanning}>
            {scanning ? '扫描中…' : '扫描停滞线索'}
          </ZButton>
        </div>
        {followups === null && !scanning && (
          <div className={styles.aiHint}>点击「扫描停滞线索」获取跟进建议</div>
        )}
        {scanning && <ZSkeleton rows={3} />}
        {followups !== null && !scanning && followups.length === 0 && (
          <ZEmpty title="暂无停滞线索" description="所有线索均在正常跟进中" />
        )}
        {followups !== null && followups.length > 0 && (
          <div className={styles.followupList}>
            {followups.map(item => (
              <div key={item.lead_id} className={styles.followupRow}>
                <div className={styles.followupMeta}>
                  <ZBadge type="warning" text={`${item.days_stale}天未跟进`} />
                  <span className={styles.followupStage}>{item.stage}</span>
                </div>
                <div className={styles.followupText}>{item.suggestion}</div>
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* 报价推荐 */}
      <ZCard>
        <div className={styles.aiSectionTitle}>报价推荐</div>
        <div className={styles.aiForm}>
          <div className={styles.aiFormRow}>
            <div className={styles.aiField}>
              <label className={styles.aiLabel}>用餐人数</label>
              <ZInput
                type="number"
                value={recPeople}
                onChange={v => setRecPeople(v)}
                placeholder="如：200"
              />
            </div>
            <div className={styles.aiField}>
              <label className={styles.aiLabel}>预算上限（元）</label>
              <ZInput
                type="number"
                value={recBudget}
                onChange={v => setRecBudget(v)}
                placeholder="如：60000"
              />
            </div>
          </div>
          <div className={styles.aiFormRow}>
            <div className={styles.aiField}>
              <label className={styles.aiLabel}>宴会类型（选填）</label>
              <ZSelect
                value={recType}
                options={BANQUET_TYPE_OPTIONS}
                onChange={v => setRecType(v as string)}
              />
            </div>
            <div className={styles.aiFieldAction}>
              <ZButton
                variant="primary"
                onClick={runQuoteRecommend}
                disabled={recommending || !recPeople || !recBudget}
              >
                {recommending ? '推荐中…' : '推荐套餐'}
              </ZButton>
            </div>
          </div>
        </div>
        {recommending && <ZSkeleton rows={3} />}
        {packages !== null && !recommending && packages.length === 0 && (
          <ZEmpty title="暂无匹配套餐" description="请调整人数或预算后重试" />
        )}
        {packages !== null && packages.length > 0 && (
          <div className={styles.packageList}>
            {packages.map(pkg => (
              <div key={pkg.package_id} className={styles.packageCard}>
                <div className={styles.packageName}>{pkg.package_name}</div>
                <div className={styles.packageMeta}>
                  <span>{pkg.banquet_type}</span>
                  <span>·</span>
                  <span>¥{pkg.suggested_price_per_person_yuan}/人</span>
                </div>
                <div className={styles.packageStats}>
                  <span className={styles.packageTotal}>总价¥{pkg.total_price_yuan.toLocaleString()}</span>
                  <span className={styles.packageProfit}>
                    毛利¥{pkg.estimated_gross_profit_yuan.toLocaleString()} · {pkg.gross_margin_pct}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* 厅房推荐 */}
      <ZCard>
        <div className={styles.aiSectionTitle}>厅房推荐</div>
        <div className={styles.aiForm}>
          <div className={styles.aiFormRow}>
            <div className={styles.aiField}>
              <label className={styles.aiLabel}>目标日期</label>
              <ZInput
                type="date"
                value={hallDate}
                onChange={v => setHallDate(v)}
              />
            </div>
            <div className={styles.aiField}>
              <label className={styles.aiLabel}>用餐时段</label>
              <ZSelect
                value={hallSlot}
                options={SLOT_OPTIONS}
                onChange={v => setHallSlot(v as string)}
              />
            </div>
          </div>
          <div className={styles.aiFormRow}>
            <div className={styles.aiField}>
              <label className={styles.aiLabel}>用餐人数</label>
              <ZInput
                type="number"
                value={hallPeople}
                onChange={v => setHallPeople(v)}
                placeholder="如：200"
              />
            </div>
            <div className={styles.aiFieldAction}>
              <ZButton
                variant="primary"
                onClick={runHallRecommend}
                disabled={hallLoading || !hallDate || !hallPeople}
              >
                {hallLoading ? '查询中…' : '查询可用厅房'}
              </ZButton>
            </div>
          </div>
        </div>
        {hallLoading && <ZSkeleton rows={3} />}
        {halls !== null && !hallLoading && halls.length === 0 && (
          <ZEmpty title="暂无可用厅房" description="请更换日期或时段后重试" />
        )}
        {halls !== null && halls.length > 0 && (
          <div className={styles.packageList}>
            {halls.map((h, i) => (
              <div key={h.hall_id ?? i} className={styles.packageCard}>
                <div className={styles.packageName}>{h.hall_name ?? h.name}</div>
                <div className={styles.packageMeta}>
                  <span>{h.hall_type ?? ''}</span>
                  {h.max_people && <><span>·</span><span>最多{h.max_people}人</span></>}
                </div>
                {(h.min_spend_yuan ?? h.min_spend) != null && (
                  <div className={styles.packageStats}>
                    <span className={styles.packageTotal}>
                      最低消费¥{((h.min_spend_yuan ?? h.min_spend ?? 0)).toLocaleString()}
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Tab5：利润复盘 ─── */
interface ProfitRow {
  snapshot_id:          string;
  order_id:             string;
  banquet_date:         string | null;
  banquet_type:         string | null;
  revenue_yuan:         number;
  ingredient_cost_yuan: number;
  labor_cost_yuan:      number;
  gross_profit_yuan:    number;
  gross_margin_pct:     number;
}

function ProfitTab() {
  const [month,       setMonth]       = useState(dayjs().format('YYYY-MM'));
  const [rows,        setRows]        = useState<ProfitRow[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [triggering,  setTriggering]  = useState<string | null>(null);

  const loadSnapshots = useCallback(async (m: string) => {
    setLoading(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/profit-snapshots`,
        { params: { month: m } },
      );
      setRows(Array.isArray(resp.data) ? resp.data : []);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadSnapshots(month); }, [loadSnapshots, month]);

  const triggerReview = async (orderId: string) => {
    setTriggering(orderId);
    try {
      await apiClient.post(
        `/api/v1/banquet-agent/stores/${STORE_ID}/orders/${orderId}/review`,
      );
      await loadSnapshots(month);
    } catch {
      /* review generation errors are non-critical */
    } finally {
      setTriggering(null);
    }
  };

  const totalRevenue = rows.reduce((s, r) => s + r.revenue_yuan, 0);
  const totalProfit  = rows.reduce((s, r) => s + r.gross_profit_yuan, 0);
  const avgMargin    = rows.length > 0
    ? (rows.reduce((s, r) => s + r.gross_margin_pct, 0) / rows.length).toFixed(1)
    : '0.0';

  return (
    <div className={styles.tabContent}>
      <div className={styles.tabHeader}>
        <ZSelect
          value={month}
          options={buildMonthOptions()}
          onChange={v => setMonth(v as string)}
        />
      </div>
      <ZCard>
        {loading ? (
          <ZSkeleton rows={4} />
        ) : rows.length === 0 ? (
          <ZEmpty title="暂无利润数据" description="宴会完成后录入利润快照" />
        ) : (
          <>
            <div className={styles.profitTable}>
              <div className={`${styles.profitRow} ${styles.profitHead}`}>
                <span>日期</span>
                <span>类型</span>
                <span>收入¥</span>
                <span>毛利¥</span>
                <span>毛利率</span>
                <span></span>
              </div>
              {rows.map(r => (
                <div key={r.snapshot_id} className={styles.profitRow}>
                  <span>{r.banquet_date ? dayjs(r.banquet_date).format('MM-DD') : '-'}</span>
                  <span>{r.banquet_type ?? '-'}</span>
                  <span>¥{r.revenue_yuan.toLocaleString()}</span>
                  <span className={r.gross_profit_yuan >= 0 ? styles.profitPos : styles.profitNeg}>
                    ¥{r.gross_profit_yuan.toLocaleString()}
                  </span>
                  <span>{r.gross_margin_pct.toFixed(1)}%</span>
                  <span>
                    <ZButton
                      variant="ghost"
                      size="sm"
                      onClick={() => triggerReview(r.order_id)}
                      disabled={triggering === r.order_id}
                    >
                      {triggering === r.order_id ? '…' : '复盘'}
                    </ZButton>
                  </span>
                </div>
              ))}
              <div className={`${styles.profitRow} ${styles.profitTotal}`}>
                <span>合计</span>
                <span></span>
                <span>¥{totalRevenue.toLocaleString()}</span>
                <span>¥{totalProfit.toLocaleString()}</span>
                <span>{avgMargin}%</span>
                <span></span>
              </div>
            </div>
          </>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Tab6：资源配置 ─── */

const HALL_TYPE_OPTIONS = [
  { value: 'main_hall', label: '大厅' },
  { value: 'vip_room',  label: '包间' },
  { value: 'garden',    label: '花园/露台' },
  { value: 'outdoor',   label: '户外场地' },
];

const HALL_TYPE_LABELS: Record<string, string> = {
  main_hall: '大厅',
  vip_room:  '包间',
  garden:    '花园/露台',
  outdoor:   '户外',
};

interface HallItem {
  hall_id:        string;
  name:           string;
  hall_type:      string;
  max_tables:     number;
  max_people:     number;
  min_spend_yuan: number;
  floor_area_m2:  number | null;
  description:    string | null;
  is_active:      boolean;
}

interface PackageItem {
  package_id:           string;
  name:                 string;
  banquet_type:         string | null;
  suggested_price_yuan: number;
  cost_yuan:            number | null;
  gross_margin_pct:     number | null;
  target_people_min:    number;
  target_people_max:    number;
  description:          string | null;
  is_active:            boolean;
}

const BANQUET_TYPE_OPTIONS_WITH_EMPTY = [
  { value: '',           label: '不限类型' },
  { value: 'wedding',    label: '婚宴' },
  { value: 'birthday',   label: '寿宴' },
  { value: 'business',   label: '商务宴' },
  { value: 'full_moon',  label: '满月酒' },
  { value: 'graduation', label: '升学宴' },
  { value: 'other',      label: '其他' },
];

const BANQUET_TYPE_LABELS: Record<string, string> = {
  wedding:    '婚宴',
  birthday:   '寿宴',
  business:   '商务宴',
  full_moon:  '满月酒',
  graduation: '升学宴',
  other:      '其他',
};

function useHalls() {
  const [halls, setHalls]     = useState<HallItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/halls`,
        { params: { active_only: false } },
      );
      setHalls(Array.isArray(resp.data) ? resp.data : []);
    } catch { setHalls([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);
  return { halls, loading, reload: load };
}

function usePackages() {
  const [packages, setPackages] = useState<PackageItem[]>([]);
  const [loading, setLoading]   = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/packages`,
        { params: { active_only: false } },
      );
      setPackages(Array.isArray(resp.data) ? resp.data : []);
    } catch { setPackages([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);
  return { packages, loading, reload: load };
}

function HallsSection() {
  const { halls, loading, reload } = useHalls();
  const [modalOpen,   setModalOpen]   = useState(false);
  const [editing,     setEditing]     = useState<HallItem | null>(null);
  const [saving,      setSaving]      = useState(false);

  const [fName,       setFName]       = useState('');
  const [fType,       setFType]       = useState('main_hall');
  const [fMaxTables,  setFMaxTables]  = useState('');
  const [fMaxPeople,  setFMaxPeople]  = useState('');
  const [fMinSpend,   setFMinSpend]   = useState('');
  const [fArea,       setFArea]       = useState('');
  const [fDesc,       setFDesc]       = useState('');

  const openCreate = () => {
    setEditing(null);
    setFName(''); setFType('main_hall');
    setFMaxTables(''); setFMaxPeople('');
    setFMinSpend(''); setFArea(''); setFDesc('');
    setModalOpen(true);
  };

  const openEdit = (h: HallItem) => {
    setEditing(h);
    setFName(h.name);
    setFType(h.hall_type);
    setFMaxTables(String(h.max_tables));
    setFMaxPeople(String(h.max_people));
    setFMinSpend(String(h.min_spend_yuan));
    setFArea(h.floor_area_m2 != null ? String(h.floor_area_m2) : '');
    setFDesc(h.description ?? '');
    setModalOpen(true);
  };

  const handleSave = async () => {
    if (!fName || !fMaxPeople) return;
    setSaving(true);
    const body = {
      name:           fName,
      hall_type:      fType,
      max_tables:     parseInt(fMaxTables, 10) || 1,
      max_people:     parseInt(fMaxPeople, 10),
      min_spend_yuan: parseFloat(fMinSpend) || 0,
      floor_area_m2:  fArea ? parseFloat(fArea) : null,
      description:    fDesc || null,
    };
    try {
      if (editing) {
        await apiClient.patch(
          `/api/v1/banquet-agent/stores/${STORE_ID}/halls/${editing.hall_id}`, body,
        );
      } else {
        await apiClient.post(`/api/v1/banquet-agent/stores/${STORE_ID}/halls`, body);
      }
      setModalOpen(false);
      reload();
    } catch (e) {
      handleApiError(e, editing ? '更新厅房失败' : '创建厅房失败');
    } finally {
      setSaving(false);
    }
  };

  const handleDeactivate = async (h: HallItem) => {
    try {
      await apiClient.delete(`/api/v1/banquet-agent/stores/${STORE_ID}/halls/${h.hall_id}`);
      reload();
    } catch (e) {
      handleApiError(e, '停用厅房失败');
    }
  };

  return (
    <>
      <div className={styles.resHeader}>
        <div className={styles.resSectionTitle}>厅房管理</div>
        <ZButton variant="primary" size="sm" onClick={openCreate}>+ 新增厅房</ZButton>
      </div>
      {loading ? <ZSkeleton rows={3} /> : halls.length === 0 ? (
        <ZEmpty title="暂无厅房数据" description="点击「新增厅房」添加" />
      ) : (
        <div className={styles.resTable}>
          {halls.map(h => (
            <div
              key={h.hall_id}
              className={`${styles.resRow} ${!h.is_active ? styles.resInactiveRow : ''}`}
            >
              <div className={styles.resMain}>
                <div className={styles.resName}>{h.name}</div>
                <div className={styles.resMeta}>
                  {HALL_TYPE_LABELS[h.hall_type] ?? h.hall_type}
                  {' · '}最多{h.max_people}人
                  {h.min_spend_yuan > 0 ? ` · 最低消费¥${h.min_spend_yuan.toLocaleString()}` : ''}
                </div>
              </div>
              <ZBadge type={h.is_active ? 'success' : 'default'} text={h.is_active ? '在用' : '已停用'} />
              <div className={styles.resActions}>
                <ZButton variant="ghost" size="sm" onClick={() => openEdit(h)}>编辑</ZButton>
                {h.is_active && (
                  <ZButton variant="ghost" size="sm" onClick={() => handleDeactivate(h)}>停用</ZButton>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <ZModal
        open={modalOpen}
        title={editing ? '编辑厅房' : '新增厅房'}
        onClose={() => setModalOpen(false)}
        footer={
          <div className={styles.resModalFooter}>
            <ZButton variant="ghost" onClick={() => setModalOpen(false)}>取消</ZButton>
            <ZButton variant="primary" onClick={handleSave} disabled={saving || !fName || !fMaxPeople}>
              {saving ? '保存中…' : '保存'}
            </ZButton>
          </div>
        }
      >
        <div className={styles.resForm}>
          <div className={styles.resField}>
            <label className={styles.resLabel}>厅房名称</label>
            <ZInput value={fName} onChange={v => setFName(v)} placeholder="如：一号宴会厅" />
          </div>
          <div className={styles.resField}>
            <label className={styles.resLabel}>厅房类型</label>
            <ZSelect value={fType} options={HALL_TYPE_OPTIONS} onChange={v => setFType(v as string)} />
          </div>
          <div className={styles.resFieldRow}>
            <div className={styles.resField}>
              <label className={styles.resLabel}>最多桌数</label>
              <ZInput type="number" value={fMaxTables} onChange={v => setFMaxTables(v)} placeholder="如：20" />
            </div>
            <div className={styles.resField}>
              <label className={styles.resLabel}>最多人数</label>
              <ZInput type="number" value={fMaxPeople} onChange={v => setFMaxPeople(v)} placeholder="如：200" />
            </div>
          </div>
          <div className={styles.resFieldRow}>
            <div className={styles.resField}>
              <label className={styles.resLabel}>最低消费（元）</label>
              <ZInput type="number" value={fMinSpend} onChange={v => setFMinSpend(v)} placeholder="如：20000" />
            </div>
            <div className={styles.resField}>
              <label className={styles.resLabel}>面积（m²，选填）</label>
              <ZInput type="number" value={fArea} onChange={v => setFArea(v)} placeholder="如：500" />
            </div>
          </div>
          <div className={styles.resField}>
            <label className={styles.resLabel}>备注（选填）</label>
            <ZInput value={fDesc} onChange={v => setFDesc(v)} placeholder="厅房介绍…" />
          </div>
        </div>
      </ZModal>
    </>
  );
}

function PackagesSection() {
  const { packages, loading, reload } = usePackages();
  const [modalOpen, setModalOpen]     = useState(false);
  const [editing,   setEditing]       = useState<PackageItem | null>(null);
  const [saving,    setSaving]        = useState(false);
  const [perfMap,   setPerfMap]       = useState<Record<string, { usage_count: number; avg_gross_margin_pct: number | null }>>({});

  // Load performance data for all packages
  useEffect(() => {
    if (!packages.length) return;
    Promise.allSettled(
      packages.map(p =>
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE_ID}/packages/${p.package_id}/performance`)
          .then(r => ({ id: p.package_id, data: r.data }))
      )
    ).then(results => {
      const map: typeof perfMap = {};
      results.forEach(r => {
        if (r.status === 'fulfilled') {
          map[r.value.id] = {
            usage_count:         r.value.data.usage_count,
            avg_gross_margin_pct: r.value.data.avg_gross_margin_pct,
          };
        }
      });
      setPerfMap(map);
    });
  }, [packages]);

  const [fName,     setFName]         = useState('');
  const [fType,     setFType]         = useState('');
  const [fPrice,    setFPrice]        = useState('');
  const [fCost,     setFCost]         = useState('');
  const [fPeopleMin, setFPeopleMin]   = useState('');
  const [fPeopleMax, setFPeopleMax]   = useState('');
  const [fDesc,     setFDesc]         = useState('');

  const openCreate = () => {
    setEditing(null);
    setFName(''); setFType(''); setFPrice(''); setFCost('');
    setFPeopleMin(''); setFPeopleMax(''); setFDesc('');
    setModalOpen(true);
  };

  const openEdit = (p: PackageItem) => {
    setEditing(p);
    setFName(p.name);
    setFType(p.banquet_type ?? '');
    setFPrice(String(p.suggested_price_yuan));
    setFCost(p.cost_yuan != null ? String(p.cost_yuan) : '');
    setFPeopleMin(String(p.target_people_min));
    setFPeopleMax(String(p.target_people_max));
    setFDesc(p.description ?? '');
    setModalOpen(true);
  };

  const handleSave = async () => {
    if (!fName || !fPrice) return;
    setSaving(true);
    const body = {
      name:                 fName,
      banquet_type:         fType || null,
      suggested_price_yuan: parseFloat(fPrice),
      cost_yuan:            fCost ? parseFloat(fCost) : null,
      target_people_min:    parseInt(fPeopleMin, 10) || 1,
      target_people_max:    parseInt(fPeopleMax, 10) || 999,
      description:          fDesc || null,
    };
    try {
      if (editing) {
        await apiClient.patch(
          `/api/v1/banquet-agent/stores/${STORE_ID}/packages/${editing.package_id}`, body,
        );
      } else {
        await apiClient.post(`/api/v1/banquet-agent/stores/${STORE_ID}/packages`, body);
      }
      setModalOpen(false);
      reload();
    } catch (e) {
      handleApiError(e, editing ? '更新套餐失败' : '创建套餐失败');
    } finally {
      setSaving(false);
    }
  };

  const handleDeactivate = async (p: PackageItem) => {
    try {
      await apiClient.delete(`/api/v1/banquet-agent/stores/${STORE_ID}/packages/${p.package_id}`);
      reload();
    } catch (e) {
      handleApiError(e, '下架套餐失败');
    }
  };

  return (
    <>
      <div className={styles.resHeader}>
        <div className={styles.resSectionTitle}>套餐管理</div>
        <ZButton variant="primary" size="sm" onClick={openCreate}>+ 新增套餐</ZButton>
      </div>
      {loading ? <ZSkeleton rows={3} /> : packages.length === 0 ? (
        <ZEmpty title="暂无套餐数据" description="点击「新增套餐」添加" />
      ) : (
        <div className={styles.resTable}>
          {packages.map(p => (
            <div
              key={p.package_id}
              className={`${styles.resRow} ${!p.is_active ? styles.resInactiveRow : ''}`}
            >
              <div className={styles.resMain}>
                <div className={styles.resName}>{p.name}</div>
                <div className={styles.resMeta}>
                  {p.banquet_type ? (BANQUET_TYPE_LABELS[p.banquet_type] ?? p.banquet_type) : '通用'}
                  {' · '}{p.target_people_min}–{p.target_people_max}人
                  {' · '}¥{p.suggested_price_yuan.toLocaleString()}
                  {p.gross_margin_pct != null ? ` · 毛利率${p.gross_margin_pct}%` : ''}
                </div>
              </div>
              {perfMap[p.package_id] !== undefined ? (
                perfMap[p.package_id].usage_count > 0 ? (
                  <span className={styles.perfBadge}>
                    {perfMap[p.package_id].usage_count}单
                    {perfMap[p.package_id].avg_gross_margin_pct != null
                      ? ` · ${perfMap[p.package_id].avg_gross_margin_pct}%毛利`
                      : ''}
                  </span>
                ) : (
                  <span className={styles.perfBadgeEmpty}>未使用</span>
                )
              ) : null}
              <ZBadge type={p.is_active ? 'success' : 'default'} text={p.is_active ? '上架' : '已下架'} />
              <div className={styles.resActions}>
                <ZButton variant="ghost" size="sm" onClick={() => openEdit(p)}>编辑</ZButton>
                {p.is_active && (
                  <ZButton variant="ghost" size="sm" onClick={() => handleDeactivate(p)}>下架</ZButton>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <ZModal
        open={modalOpen}
        title={editing ? '编辑套餐' : '新增套餐'}
        onClose={() => setModalOpen(false)}
        footer={
          <div className={styles.resModalFooter}>
            <ZButton variant="ghost" onClick={() => setModalOpen(false)}>取消</ZButton>
            <ZButton variant="primary" onClick={handleSave} disabled={saving || !fName || !fPrice}>
              {saving ? '保存中…' : '保存'}
            </ZButton>
          </div>
        }
      >
        <div className={styles.resForm}>
          <div className={styles.resField}>
            <label className={styles.resLabel}>套餐名称</label>
            <ZInput value={fName} onChange={v => setFName(v)} placeholder="如：经典婚宴套餐" />
          </div>
          <div className={styles.resField}>
            <label className={styles.resLabel}>适用宴会类型（选填）</label>
            <ZSelect
              value={fType}
              options={BANQUET_TYPE_OPTIONS_WITH_EMPTY}
              onChange={v => setFType(v as string)}
            />
          </div>
          <div className={styles.resFieldRow}>
            <div className={styles.resField}>
              <label className={styles.resLabel}>建议售价（元）</label>
              <ZInput type="number" value={fPrice} onChange={v => setFPrice(v)} placeholder="如：30000" />
            </div>
            <div className={styles.resField}>
              <label className={styles.resLabel}>估算成本（元，选填）</label>
              <ZInput type="number" value={fCost} onChange={v => setFCost(v)} placeholder="如：12000" />
            </div>
          </div>
          <div className={styles.resFieldRow}>
            <div className={styles.resField}>
              <label className={styles.resLabel}>最少人数</label>
              <ZInput type="number" value={fPeopleMin} onChange={v => setFPeopleMin(v)} placeholder="1" />
            </div>
            <div className={styles.resField}>
              <label className={styles.resLabel}>最多人数</label>
              <ZInput type="number" value={fPeopleMax} onChange={v => setFPeopleMax(v)} placeholder="999" />
            </div>
          </div>
          <div className={styles.resField}>
            <label className={styles.resLabel}>套餐描述（选填）</label>
            <ZInput value={fDesc} onChange={v => setFDesc(v)} placeholder="套餐包含内容…" />
          </div>
        </div>
      </ZModal>
    </>
  );
}

/* ─── Tab6c: 任务模板管理 ─── */

interface TemplateItem {
  template_id:   string;
  template_name: string;
  banquet_type:  string;
  task_count:    number;
  version:       number;
  is_active:     boolean;
}

interface TaskDefRow {
  task_name:  string;
  owner_role: string;
  days_before: number;
}

function TemplatesSection() {
  const [templates,   setTemplates]   = useState<TemplateItem[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [tplOpen,     setTplOpen]     = useState(false);
  const [editingTpl,  setEditingTpl]  = useState<TemplateItem | null>(null);
  const [saving,      setSaving]      = useState(false);

  // form fields
  const [fName,       setFName]       = useState('');
  const [fType,       setFType]       = useState('wedding');
  const [taskDefs,    setTaskDefs]    = useState<TaskDefRow[]>([
    { task_name: '', owner_role: 'kitchen', days_before: 1 },
  ]);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/banquet-agent/stores/${STORE_ID}/templates`);
      setTemplates(Array.isArray(resp.data) ? resp.data : []);
    } catch {
      setTemplates([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  const openCreate = () => {
    setEditingTpl(null);
    setFName('');
    setFType('wedding');
    setTaskDefs([{ task_name: '', owner_role: 'kitchen', days_before: 1 }]);
    setTplOpen(true);
  };

  const openEdit = async (tpl: TemplateItem) => {
    setEditingTpl(tpl);
    setFName(tpl.template_name);
    setFType(tpl.banquet_type);
    // Load full task_defs from detail endpoint (use template data if available)
    setTaskDefs([{ task_name: '(加载中)', owner_role: 'kitchen', days_before: 1 }]);
    setTplOpen(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/templates`,
        { params: { banquet_type: tpl.banquet_type } },
      );
      const found = (resp.data as TemplateItem[]).find(t => t.template_id === tpl.template_id);
      if (found && (found as unknown as { task_defs: TaskDefRow[] }).task_defs) {
        setTaskDefs((found as unknown as { task_defs: TaskDefRow[] }).task_defs);
      } else {
        setTaskDefs([{ task_name: '', owner_role: 'kitchen', days_before: 1 }]);
      }
    } catch {
      setTaskDefs([{ task_name: '', owner_role: 'kitchen', days_before: 1 }]);
    }
  };

  const handleSave = async () => {
    if (!fName.trim()) return;
    const validDefs = taskDefs.filter(d => d.task_name.trim());
    setSaving(true);
    try {
      if (editingTpl) {
        await apiClient.patch(
          `/api/v1/banquet-agent/stores/${STORE_ID}/templates/${editingTpl.template_id}`,
          { template_name: fName, banquet_type: fType, task_defs: validDefs },
        );
      } else {
        await apiClient.post(
          `/api/v1/banquet-agent/stores/${STORE_ID}/templates`,
          { template_name: fName, banquet_type: fType, task_defs: validDefs },
        );
      }
      setTplOpen(false);
      reload();
    } catch (e) {
      handleApiError(e, editingTpl ? '更新模板失败' : '创建模板失败');
    } finally {
      setSaving(false);
    }
  };

  const handleDeactivate = async (tpl: TemplateItem) => {
    try {
      await apiClient.delete(
        `/api/v1/banquet-agent/stores/${STORE_ID}/templates/${tpl.template_id}`,
      );
      reload();
    } catch (e) {
      handleApiError(e, '停用模板失败');
    }
  };

  const updateTaskDef = (idx: number, field: keyof TaskDefRow, val: string | number) => {
    setTaskDefs(prev => prev.map((d, i) => i === idx ? { ...d, [field]: val } : d));
  };

  const addTaskDef = () => {
    setTaskDefs(prev => [...prev, { task_name: '', owner_role: 'kitchen', days_before: 1 }]);
  };

  const removeTaskDef = (idx: number) => {
    setTaskDefs(prev => prev.filter((_, i) => i !== idx));
  };

  return (
    <>
      <div className={styles.resHeader}>
        <div className={styles.resSectionTitle}>任务模板</div>
        <ZButton variant="primary" size="sm" onClick={openCreate}>+ 新建模板</ZButton>
      </div>
      {loading ? <ZSkeleton rows={3} /> : templates.length === 0 ? (
        <ZEmpty title="暂无模板" description="点击「新建模板」添加" />
      ) : (
        <div className={styles.resTable}>
          {templates.map(tpl => (
            <div
              key={tpl.template_id}
              className={`${styles.resRow} ${!tpl.is_active ? styles.resInactiveRow : ''}`}
            >
              <div className={styles.resMain}>
                <div className={styles.resName}>{tpl.template_name}</div>
                <div className={styles.resMeta}>
                  {BANQUET_TYPE_LABELS[tpl.banquet_type] ?? tpl.banquet_type}
                  {' · '}{tpl.task_count}个任务
                  {' · '}v{tpl.version}
                </div>
              </div>
              <ZBadge type={tpl.is_active ? 'success' : 'default'} text={tpl.is_active ? '启用' : '已停用'} />
              <div className={styles.resActions}>
                <ZButton variant="ghost" size="sm" onClick={() => openEdit(tpl)}>编辑</ZButton>
                {tpl.is_active && (
                  <ZButton variant="ghost" size="sm" onClick={() => handleDeactivate(tpl)}>停用</ZButton>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <ZModal
        open={tplOpen}
        title={editingTpl ? '编辑模板' : '新建模板'}
        onClose={() => setTplOpen(false)}
        footer={
          <div className={styles.resModalFooter}>
            <ZButton variant="ghost" onClick={() => setTplOpen(false)}>取消</ZButton>
            <ZButton variant="primary" onClick={handleSave} disabled={saving || !fName.trim()}>
              {saving ? '保存中…' : '保存'}
            </ZButton>
          </div>
        }
      >
        <div className={styles.resForm}>
          <div className={styles.resField}>
            <label className={styles.resLabel}>模板名称</label>
            <ZInput value={fName} onChange={v => setFName(v)} placeholder="如：婚宴标准执行模板" />
          </div>
          <div className={styles.resField}>
            <label className={styles.resLabel}>适用宴会类型</label>
            <ZSelect
              value={fType}
              options={[
                { value: 'wedding',  label: '婚宴' },
                { value: 'birthday', label: '生日宴' },
                { value: 'business', label: '商务宴' },
                { value: 'other',    label: '其他' },
              ]}
              onChange={v => setFType(v as string)}
            />
          </div>
          <div className={styles.resField}>
            <label className={styles.resLabel}>任务清单</label>
            <div className={styles.tplTaskDefs}>
              {taskDefs.map((d, i) => (
                <div key={i} className={styles.tplTaskRow}>
                  <ZInput
                    value={d.task_name}
                    onChange={val => updateTaskDef(i, 'task_name', val)}
                    placeholder="任务名称"
                  />
                  <ZSelect
                    value={d.owner_role}
                    options={[
                      { value: 'kitchen',  label: '厨房' },
                      { value: 'service',  label: '服务' },
                      { value: 'decor',    label: '布置' },
                      { value: 'purchase', label: '采购' },
                      { value: 'manager',  label: '店长' },
                    ]}
                    onChange={v => updateTaskDef(i, 'owner_role', v as string)}
                  />
                  <ZInput
                    type="number"
                    value={String(d.days_before)}
                    onChange={val => updateTaskDef(i, 'days_before', parseInt(val, 10) || 1)}
                    placeholder="提前天数"
                  />
                  <button className={styles.tplRemoveBtn} onClick={() => removeTaskDef(i)}>✕</button>
                </div>
              ))}
            </div>
            <button className={styles.tplAddBtn} onClick={addTaskDef}>＋ 添加任务</button>
          </div>
        </div>
      </ZModal>
    </>
  );
}

function ResourceTab() {
  const [subTab, setSubTab] = useState<'halls' | 'packages' | 'templates'>('halls');

  return (
    <div className={styles.tabContent}>
      <div className={styles.resChipBar}>
        {(['halls', 'packages', 'templates'] as const).map(t => (
          <button
            key={t}
            className={`${styles.resChip} ${subTab === t ? styles.resChipActive : ''}`}
            onClick={() => setSubTab(t)}
          >
            {t === 'halls' ? '厅房' : t === 'packages' ? '套餐' : '任务模板'}
          </button>
        ))}
      </div>
      <ZCard>
        {subTab === 'halls'     ? <HallsSection />     :
         subTab === 'packages'  ? <PackagesSection />  :
                                  <TemplatesSection />}
      </ZCard>
    </div>
  );
}

/* ─── Tab8: 转化分析 ─── */

interface AnalyticsFunnelStage {
  stage:           string;
  label:           string;
  count:           number;
  conversion_rate: number | null;
}

interface FunnelResp {
  period:                   string;
  stages:                   AnalyticsFunnelStage[];
  total_leads:              number;
  won_count:                number;
  lost_count:               number;
  overall_conversion_rate:  number;
}

interface ForecastBucket {
  month:                   string;
  confirmed_revenue_yuan:  number;
  order_count:             number;
}

interface LostReason {
  reason: string;
  count:  number;
  pct:    number;
}

interface AROrder {
  order_id:            string;
  banquet_type:        string;
  banquet_date:        string;
  total_amount_yuan:   number;
  paid_yuan:           number;
  balance_yuan:        number;
  days_until_event:    number;
  contact_name:        string | null;
}

interface ReceivablesData {
  order_count:             number;
  total_outstanding_yuan:  number;
  orders:                  AROrder[];
}

interface ExceptionSummaryItem {
  id:             string;
  exception_type: string;
  severity:       string;
  description:    string;
  status:         string;
  created_at:     string;
  banquet_type:   string | null;
}

interface AgingBucket {
  count:        number;
  balance_yuan: number;
  items:        { order_id: string; banquet_date: string; balance_yuan: number; days_overdue: number; contact_name: string | null }[];
}
interface AgingData {
  total_balance_yuan: number;
  buckets: { '0_30': AgingBucket; '31_60': AgingBucket; '61_90': AgingBucket; over_90: AgingBucket };
}
interface QuoteStatItem { banquet_type: string; count: number; accepted: number; total_amount_yuan: number }
interface QuoteStats {
  total_quotes: number; accepted_quotes: number; acceptance_pct: number;
  type_distribution: QuoteStatItem[];
}
/* Phase 15 */
interface ServiceQualityType { banquet_type: string; task_count: number; completion_pct: number; exception_count: number }
interface ServiceQualityData {
  order_count: number; task_completion_pct: number;
  avg_delay_hours: number; exception_rate_pct: number;
  by_banquet_type: ServiceQualityType[];
}
interface LeadTimeBuckets { under_30: number; d30_60: number; d60_90: number; over_90: number }
interface LeadTimeData { total: number; avg_lead_time_days: number; buckets: LeadTimeBuckets; bucket_pcts: LeadTimeBuckets }
interface RetentionCustomer { customer_id: string; name: string; order_count: number; total_yuan: number }
interface RetentionData {
  total_customers: number; repeat_customers: number; repeat_rate_pct: number;
  avg_ltv_yuan: number; top_customers: RetentionCustomer[];
}
interface CancellationType { banquet_type: string; count: number }
interface CancellationData {
  total: number; revenue_lost_yuan: number;
  by_banquet_type: CancellationType[];
  by_lead_time: { urgent_7d: number; d7_30: number; over_30d: number };
}

/* Phase 17 */
interface PkgProfitRow {
  pkg_id: string; name: string; banquet_type: string;
  suggested_price_yuan: number; cost_yuan: number;
  theoretical_margin_pct: number | null; actual_margin_pct: number | null;
  order_count: number;
}
interface SeasonalMonth { month: number; avg_orders: number; avg_revenue_yuan: number; is_peak: boolean; is_low: boolean }
interface SeasonalWeekday { weekday: number; label: string; avg_orders: number; relative_pct: number }
interface SeasonalData { monthly: SeasonalMonth[]; weekly: SeasonalWeekday[] }
interface RevForecast { target_month: string; base_revenue_yuan: number; confirmed_revenue_yuan: number; forecast_yuan: number }
interface BriefAlert {
  order_id: string; banquet_date: string; banquet_type: string; days_until: number;
  risk_level: 'high' | 'medium' | 'ok';
  pending_tasks: number; unpaid_yuan: number; open_exceptions: number;
}
interface DailyBriefData { today_banquets: number; next_n_banquets: number; days: number; alerts: BriefAlert[] }
/* Phase 18 */
interface LeadSourceRow {
  source: string; lead_count: number; converted: number;
  conversion_rate_pct: number; revenue_yuan: number; revenue_per_lead_yuan: number;
}
interface PricingBucket {
  range: string; lead_count: number; order_count: number;
  conversion_rate_pct: number | null; avg_revenue_yuan: number | null;
}

function AnalyticsTab() {
  const [month,    setMonth]    = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });
  const [funnel,       setFunnel]       = useState<FunnelResp | null>(null);
  const [forecast,     setForecast]     = useState<ForecastBucket[]>([]);
  const [lostData,     setLostData]     = useState<LostReason[]>([]);
  const [receivables,  setReceivables]  = useState<ReceivablesData | null>(null);
  const [openExc,      setOpenExc]      = useState<ExceptionSummaryItem[]>([]);
  const [excStats,     setExcStats]     = useState<{
    total: number;
    by_type: { type: string; count: number; resolved: number }[];
    by_severity: { severity: string; count: number }[];
    avg_resolution_hours: number | null;
  } | null>(null);
  const [agingData,    setAgingData]    = useState<AgingData | null>(null);
  const [quoteStats,   setQuoteStats]   = useState<QuoteStats | null>(null);
  /* Phase 15 */
  const [svcQuality,   setSvcQuality]   = useState<ServiceQualityData | null>(null);
  const [leadTime,     setLeadTime]     = useState<LeadTimeData | null>(null);
  const [retention,    setRetention]    = useState<RetentionData | null>(null);
  const [cancellation, setCancellation] = useState<CancellationData | null>(null);
  const [execSummary,  setExecSummary]  = useState<ExecSummaryData | null>(null);
  /* Phase 17 */
  const [pkgProfit,    setPkgProfit]    = useState<PkgProfitRow[]>([]);
  const [seasonal,     setSeasonal]     = useState<SeasonalData | null>(null);
  const [revForecast,  setRevForecast]  = useState<RevForecast | null>(null);
  /* Phase 18 */
  const [leadSourceRoi,  setLeadSourceRoi]  = useState<LeadSourceRow[]>([]);
  const [pricingBuckets, setPricingBuckets] = useState<PricingBucket[]>([]);
  const [loading,      setLoading]      = useState(false);

  const load = useCallback(async (m: string) => {
    setLoading(true);
    try {
      const STORE = localStorage.getItem('store_id') || 'S001';
      const [y, mo] = m.split('-');
      const [
        funnelR, forecastR, lostR, arR, excR, excStatsR,
        agingR, quoteStatsR, svcR, ltR, retR, cancelR, execR,
        pkgProfitR, seasonalR, revForecastR,
        leadSrcR, pricingR,
      ] = await Promise.allSettled([
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/funnel`, { params: { month: m } }),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/revenue-forecast`, { params: { months: 3 } }),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/lost-analysis`, { params: { month: m } }),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/receivables`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/exceptions`, { params: { status: 'open' } }),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/exception-stats`, { params: { month: m } }),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/receivables-aging`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/quote-stats`, { params: { year: Number(y), month: Number(mo) } }),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/service-quality`, { params: { month: m } }),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/booking-lead-time`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/customer-retention`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/cancellation-analysis`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/executive-summary`, { params: { year: Number(y), month: Number(mo) } }),
        /* Phase 17 */
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/menu-packages/profitability`, { params: { year: Number(y), month: Number(mo) } }),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/seasonal-patterns`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/revenue-forecast`),
        /* Phase 18 */
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/lead-source-roi`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/pricing-analysis`),
      ]);
      if (funnelR.status === 'fulfilled')     setFunnel(funnelR.value.data);
      if (forecastR.status === 'fulfilled')   setForecast(forecastR.value.data?.forecast ?? []);
      if (lostR.status === 'fulfilled')       setLostData(lostR.value.data?.reasons ?? []);
      if (arR.status === 'fulfilled')         setReceivables(arR.value.data);
      if (excR.status === 'fulfilled')        setOpenExc(Array.isArray(excR.value.data) ? excR.value.data : []);
      if (excStatsR.status === 'fulfilled')   setExcStats(excStatsR.value.data);
      if (agingR.status === 'fulfilled')      setAgingData(agingR.value.data);
      if (quoteStatsR.status === 'fulfilled') setQuoteStats(quoteStatsR.value.data);
      if (svcR.status === 'fulfilled')        setSvcQuality(svcR.value.data);
      if (ltR.status === 'fulfilled')         setLeadTime(ltR.value.data);
      if (retR.status === 'fulfilled')        setRetention(retR.value.data);
      if (cancelR.status === 'fulfilled')     setCancellation(cancelR.value.data);
      if (execR.status === 'fulfilled')       setExecSummary(execR.value.data);
      if (pkgProfitR.status === 'fulfilled')  setPkgProfit(pkgProfitR.value.data?.packages ?? []);
      if (seasonalR.status === 'fulfilled')   setSeasonal(seasonalR.value.data);
      if (revForecastR.status === 'fulfilled') setRevForecast(revForecastR.value.data);
      if (leadSrcR.status === 'fulfilled')    setLeadSourceRoi(leadSrcR.value.data?.sources ?? []);
      if (pricingR.status === 'fulfilled')    setPricingBuckets(pricingR.value.data?.buckets ?? []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(month); }, [load, month]);

  /* funnel bar chart */
  const funnelOption = funnel ? {
    tooltip: { trigger: 'axis' as const },
    grid: { left: 100, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'value' as const, minInterval: 1 },
    yAxis: {
      type: 'category' as const,
      data: [...funnel.stages].reverse().map(s => s.label),
      axisLabel: { fontSize: 12 },
    },
    series: [{
      type: 'bar' as const,
      data: [...funnel.stages].reverse().map(s => s.count),
      itemStyle: { color: 'var(--accent, #0AAF9A)' },
      label: {
        show: true,
        position: 'right' as const,
        formatter: (p: { value: number; dataIndex: number }) => {
          const stage = funnel.stages[funnel.stages.length - 1 - p.dataIndex];
          return stage.conversion_rate != null
            ? `${p.value} (${(stage.conversion_rate * 100).toFixed(0)}%)`
            : `${p.value}`;
        },
      },
    }],
  } : null;

  /* forecast bar chart */
  const forecastOption = forecast.length > 0 ? {
    tooltip: { trigger: 'axis' as const },
    grid: { left: 60, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category' as const, data: forecast.map(b => b.month) },
    yAxis: { type: 'value' as const, axisLabel: { formatter: (v: number) => `${(v / 10000).toFixed(0)}万` } },
    series: [{
      type: 'bar' as const,
      data: forecast.map(b => b.confirmed_revenue_yuan),
      itemStyle: { color: '#3b82f6' },
      label: { show: true, position: 'top' as const, formatter: (p: { value: number }) => p.value > 0 ? `${(p.value / 10000).toFixed(1)}万` : '' },
    }],
  } : null;

  const maxLost = lostData.length > 0 ? Math.max(...lostData.map(r => r.count)) : 1;

  return (
    <div className={styles.analyticsTab}>
      {/* 月份选择 */}
      <div className={styles.analyticsPicker}>
        <ZInput
          type="month"
          value={month}
          onChange={v => setMonth(v)}
        />
      </div>

      {loading ? <ZSkeleton rows={8} /> : (
        <>
          {/* 转化漏斗 */}
          <ZCard title="转化漏斗">
            {!funnel || funnel.total_leads === 0 ? (
              <ZEmpty title="暂无数据" description="当月尚无线索记录" />
            ) : (
              <>
                <div className={styles.funnelKpis}>
                  <div className={styles.funnelKpi}>
                    <span className={styles.funnelKpiValue}>{funnel.total_leads}</span>
                    <span className={styles.funnelKpiLabel}>总线索</span>
                  </div>
                  <div className={styles.funnelKpi}>
                    <span className={styles.funnelKpiValue}>{funnel.won_count}</span>
                    <span className={styles.funnelKpiLabel}>成交</span>
                  </div>
                  <div className={styles.funnelKpi}>
                    <span className={styles.funnelKpiValue}>{funnel.lost_count}</span>
                    <span className={styles.funnelKpiLabel}>流失</span>
                  </div>
                  <div className={styles.funnelKpi}>
                    <span className={styles.funnelKpiValue}>
                      {(funnel.overall_conversion_rate * 100).toFixed(1)}%
                    </span>
                    <span className={styles.funnelKpiLabel}>整体转化</span>
                  </div>
                </div>
                {funnelOption && (
                  <ReactECharts option={funnelOption} style={{ height: 240 }} />
                )}
              </>
            )}
          </ZCard>

          {/* 营收预测 */}
          <ZCard title="近 3 个月营收预测（已确认订单）">
            {forecast.every(b => b.order_count === 0) ? (
              <ZEmpty title="暂无确认订单" description="确认订单后自动显示" />
            ) : forecastOption ? (
              <ReactECharts option={forecastOption} style={{ height: 180 }} />
            ) : null}
          </ZCard>

          {/* 流失归因 */}
          <ZCard title={`流失归因（${month}）`}>
            {lostData.length === 0 ? (
              <ZEmpty title="本月暂无流失线索" description="" />
            ) : (
              <div className={styles.lostList}>
                {lostData.map(r => (
                  <div key={r.reason} className={styles.lostRow}>
                    <span className={styles.lostReason}>{r.reason}</span>
                    <div className={styles.lostBarWrap}>
                      <div
                        className={styles.lostBar}
                        style={{ width: `${(r.count / maxLost) * 100}%` }}
                      />
                    </div>
                    <span className={styles.lostCount}>{r.count} ({r.pct}%)</span>
                  </div>
                ))}
              </div>
            )}
          </ZCard>

          {/* 应收账款 */}
          <ZCard title="应收账款（未结清）">
            {!receivables || receivables.order_count === 0 ? (
              <ZEmpty title="暂无应收账款" description="所有订单均已全额付款" />
            ) : (
              <>
                <div className={styles.arSummary}>
                  <div className={styles.arKpi}>
                    <span className={styles.arKpiValue}>{receivables.order_count}</span>
                    <span className={styles.arKpiLabel}>待收订单</span>
                  </div>
                  <div className={styles.arKpi}>
                    <span className={styles.arKpiValue}>
                      ¥{(receivables.total_outstanding_yuan / 10000).toFixed(1)}万
                    </span>
                    <span className={styles.arKpiLabel}>应收合计</span>
                  </div>
                </div>
                <div className={styles.arList}>
                  {receivables.orders.map(o => (
                    <div key={o.order_id} className={`${styles.arRow} ${o.days_until_event <= 7 ? styles.arUrgent : ''}`}>
                      <div className={styles.arLeft}>
                        <span className={styles.arType}>{o.banquet_type}</span>
                        {o.contact_name && <span className={styles.arContact}>{o.contact_name}</span>}
                        <span className={styles.arDate}>{dayjs(o.banquet_date).format('MM-DD')}</span>
                        {o.days_until_event <= 7 && (
                          <span className={styles.arDaysTag}>
                            {o.days_until_event <= 0 ? '已过期' : `${o.days_until_event}天`}
                          </span>
                        )}
                      </div>
                      <div className={styles.arRight}>
                        <span className={styles.arBalance}>¥{o.balance_yuan.toLocaleString()}</span>
                        <span className={styles.arTotal}>/ ¥{o.total_amount_yuan.toLocaleString()}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </ZCard>

          {/* 待处理异常 */}
          <ZCard title={`待处理异常${openExc.length > 0 ? `（${openExc.length}）` : ''}`}>
            {openExc.length === 0 ? (
              <ZEmpty title="暂无待处理异常" description="各门店运营正常" />
            ) : (
              <div className={styles.excSummaryList}>
                {openExc.map(exc => (
                  <div
                    key={exc.id}
                    className={`${styles.excSummaryRow} ${exc.severity === 'high' ? styles.excSummaryHigh : ''}`}
                  >
                    <div className={styles.excSummaryLeft}>
                      <span className={styles.excSummaryType}>{exc.exception_type}</span>
                      <span className={styles.excSummaryDesc}>{exc.description}</span>
                    </div>
                    <ZBadge
                      type={exc.severity === 'high' ? 'default' : 'warning'}
                      text={exc.severity === 'high' ? '严重' : exc.severity === 'medium' ? '中度' : '轻微'}
                    />
                  </div>
                ))}
              </div>
            )}
          </ZCard>

          {/* 异常统计分析 */}
          <ZCard title="异常统计（本月）">
            {!excStats || excStats.total === 0 ? (
              <ZEmpty title="暂无异常" description="本月无异常记录" />
            ) : (
              <div className={styles.excStatsBody}>
                <div className={styles.excStatsSummary}>
                  <div className={styles.excStatItem}>
                    <span className={styles.excStatValue}>{excStats.total}</span>
                    <span className={styles.excStatLabel}>总数</span>
                  </div>
                  {excStats.avg_resolution_hours != null && (
                    <div className={styles.excStatItem}>
                      <span className={styles.excStatValue}>{excStats.avg_resolution_hours}h</span>
                      <span className={styles.excStatLabel}>平均解决时长</span>
                    </div>
                  )}
                </div>
                <div className={styles.excStatsByType}>
                  {excStats.by_type.map(bt => (
                    <div key={bt.type} className={styles.excStatTypeRow}>
                      <span className={styles.excStatTypeName}>{bt.type}</span>
                      <span className={styles.excStatTypeCount}>{bt.count} 次</span>
                      <span className={styles.excStatTypeResolved}>({bt.resolved} 已解决)</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </ZCard>

          {/* 应收账款账龄 */}
          <ZCard title="应收账款账龄分析">
            {!agingData || agingData.total_balance_yuan === 0 ? (
              <ZEmpty title="暂无逾期应收" description="所有订单均已结清" />
            ) : (
              <div className={styles.agingBody}>
                <div className={styles.agingTotal}>
                  合计应收 <strong>¥{agingData.total_balance_yuan.toLocaleString()}</strong>
                </div>
                <div className={styles.agingBuckets}>
                  {([
                    { key: '0_30',   label: '0–30天',  urgent: false },
                    { key: '31_60',  label: '31–60天', urgent: false },
                    { key: '61_90',  label: '61–90天', urgent: true  },
                    { key: 'over_90', label: '90天以上', urgent: true  },
                  ] as { key: keyof AgingData['buckets']; label: string; urgent: boolean }[]).map(b => {
                    const bucket = agingData.buckets[b.key];
                    if (bucket.count === 0) return null;
                    return (
                      <div key={b.key} className={`${styles.agingBucket} ${b.urgent ? styles.agingBucketUrgent : ''}`}>
                        <div className={styles.agingBucketLabel}>{b.label}</div>
                        <div className={styles.agingBucketCount}>{bucket.count} 单</div>
                        <div className={styles.agingBucketAmount}>¥{bucket.balance_yuan.toLocaleString()}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </ZCard>

          {/* 报价统计 */}
          <ZCard title={`报价统计（${month}）`}>
            {!quoteStats || quoteStats.total_quotes === 0 ? (
              <ZEmpty title="本月暂无报价记录" description="" />
            ) : (
              <div className={styles.quoteStatsBody}>
                <div className={styles.quoteStatsSummary}>
                  <div className={styles.quoteStatItem}>
                    <span className={styles.quoteStatValue}>{quoteStats.total_quotes}</span>
                    <span className={styles.quoteStatLabel}>总报价</span>
                  </div>
                  <div className={styles.quoteStatItem}>
                    <span className={styles.quoteStatValue}>{quoteStats.accepted_quotes}</span>
                    <span className={styles.quoteStatLabel}>已接受</span>
                  </div>
                  <div className={styles.quoteStatItem}>
                    <span className={styles.quoteStatValue} style={{ color: quoteStats.acceptance_pct >= 50 ? '#22c55e' : '#f97316' }}>
                      {quoteStats.acceptance_pct}%
                    </span>
                    <span className={styles.quoteStatLabel}>接受率</span>
                  </div>
                </div>
                <div className={styles.quoteTypeList}>
                  {quoteStats.type_distribution.map(t => (
                    <div key={t.banquet_type} className={styles.quoteTypeRow}>
                      <span className={styles.quoteTypeName}>{t.banquet_type}</span>
                      <span className={styles.quoteTypeCount}>{t.count} 份</span>
                      <span className={styles.quoteTypeAccepted}>{t.accepted} 接受</span>
                      <span className={styles.quoteTypeAmount}>¥{t.total_amount_yuan.toLocaleString()}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </ZCard>

          {/* Phase 15: 服务品质 */}
          <ZCard title={`服务品质（${month}）`}>
            {!svcQuality || svcQuality.order_count === 0 ? (
              <ZEmpty title="本月暂无宴会订单" description="" />
            ) : (
              <div className={styles.svcQualityBody}>
                <div className={styles.svcKpiRow}>
                  <div className={styles.svcKpi}>
                    <span className={styles.svcKpiVal}>{svcQuality.task_completion_pct}%</span>
                    <span className={styles.svcKpiLabel}>任务完成率</span>
                  </div>
                  <div className={styles.svcKpi}>
                    <span className={styles.svcKpiVal} style={{ color: svcQuality.avg_delay_hours > 1 ? '#f97316' : '#22c55e' }}>
                      {svcQuality.avg_delay_hours.toFixed(1)}h
                    </span>
                    <span className={styles.svcKpiLabel}>平均延误</span>
                  </div>
                  <div className={styles.svcKpi}>
                    <span className={styles.svcKpiVal} style={{ color: svcQuality.exception_rate_pct > 10 ? '#dc2626' : '#22c55e' }}>
                      {svcQuality.exception_rate_pct}%
                    </span>
                    <span className={styles.svcKpiLabel}>异常率</span>
                  </div>
                </div>
                {svcQuality.by_banquet_type.length > 0 && (
                  <div className={styles.svcTypeList}>
                    {svcQuality.by_banquet_type.map(t => (
                      <div key={t.banquet_type} className={styles.svcTypeRow}>
                        <span className={styles.svcTypeName}>{t.banquet_type}</span>
                        <span className={styles.svcTypeCount}>{t.task_count} 任务</span>
                        <span className={styles.svcTypePct}>{t.completion_pct}% 完成</span>
                        <span className={styles.svcTypeExc}>{t.exception_count} 异常</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </ZCard>

          {/* Phase 15: 预订提前量 */}
          <ZCard title="预订提前量分布">
            {!leadTime || leadTime.total === 0 ? (
              <ZEmpty title="暂无数据" description="" />
            ) : (
              <div className={styles.leadTimeBody}>
                <div className={styles.leadTimeAvg}>
                  平均提前 <strong>{leadTime.avg_lead_time_days} 天</strong>（共 {leadTime.total} 单）
                </div>
                <div className={styles.leadTimeBuckets}>
                  {([
                    { key: 'under_30', label: '<30天' },
                    { key: 'd30_60',   label: '30–60天' },
                    { key: 'd60_90',   label: '60–90天' },
                    { key: 'over_90',  label: '>90天' },
                  ] as { key: keyof LeadTimeBuckets; label: string }[]).map(b => (
                    <div key={b.key} className={styles.leadTimeBucket}>
                      <div className={styles.leadTimeBucketLabel}>{b.label}</div>
                      <div className={styles.leadTimeBucketCount}>{leadTime.buckets[b.key]}</div>
                      <div className={styles.leadTimeBar}>
                        <div
                          className={styles.leadTimeBarFill}
                          style={{ width: `${leadTime.bucket_pcts[b.key]}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </ZCard>

          {/* Phase 15: 客户保留 */}
          <ZCard title="客户保留分析">
            {!retention || retention.total_customers === 0 ? (
              <ZEmpty title="暂无客户数据" description="" />
            ) : (
              <div className={styles.retentionBody}>
                <div className={styles.retentionSummary}>
                  <div className={styles.retentionKpi}>
                    <span className={styles.retentionKpiVal}>{retention.total_customers}</span>
                    <span className={styles.retentionKpiLabel}>总客户数</span>
                  </div>
                  <div className={styles.retentionKpi}>
                    <span className={styles.retentionKpiVal}>{retention.repeat_customers}</span>
                    <span className={styles.retentionKpiLabel}>复购客户</span>
                  </div>
                  <div className={styles.retentionKpi}>
                    <span
                      className={styles.retentionKpiVal}
                      style={{ color: retention.repeat_rate_pct >= 30 ? '#22c55e' : '#f97316' }}
                    >
                      {retention.repeat_rate_pct}%
                    </span>
                    <span className={styles.retentionKpiLabel}>复购率</span>
                  </div>
                  <div className={styles.retentionKpi}>
                    <span className={styles.retentionKpiVal}>¥{retention.avg_ltv_yuan.toLocaleString()}</span>
                    <span className={styles.retentionKpiLabel}>客均LTV</span>
                  </div>
                </div>
                {retention.top_customers.length > 0 && (
                  <div className={styles.retentionTopList}>
                    <div className={styles.retentionTopTitle}>Top 客户</div>
                    {retention.top_customers.map(c => (
                      <div key={c.customer_id} className={styles.retentionTopRow}>
                        <span className={styles.retentionTopName}>{c.name}</span>
                        <span className={styles.retentionTopOrders}>{c.order_count} 单</span>
                        <span className={styles.retentionTopAmount}>¥{c.total_yuan.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </ZCard>

          {/* Phase 15: 取消分析 */}
          <ZCard title="取消订单分析">
            {!cancellation || cancellation.total === 0 ? (
              <ZEmpty title="近期无取消订单" description="很好！继续保持" />
            ) : (
              <div className={styles.cancelBody}>
                <div className={styles.cancelSummary}>
                  <span className={styles.cancelTotal}>{cancellation.total} 单取消</span>
                  <span className={styles.cancelLost}>
                    损失收入 <strong>¥{cancellation.revenue_lost_yuan.toLocaleString()}</strong>
                  </span>
                </div>
                {cancellation.by_banquet_type.length > 0 && (
                  <div className={styles.cancelByType}>
                    {cancellation.by_banquet_type.map(t => (
                      <div key={t.banquet_type} className={styles.cancelTypeRow}>
                        <span className={styles.cancelTypeName}>{t.banquet_type}</span>
                        <span className={styles.cancelTypeCount}>{t.count} 单</span>
                      </div>
                    ))}
                  </div>
                )}
                <div className={styles.cancelLeadTime}>
                  <div className={styles.cancelLtItem}>
                    <span className={styles.cancelLtLabel}>7天内取消</span>
                    <span className={styles.cancelLtCount} style={{ color: '#dc2626' }}>
                      {cancellation.by_lead_time.urgent_7d}
                    </span>
                  </div>
                  <div className={styles.cancelLtItem}>
                    <span className={styles.cancelLtLabel}>7–30天</span>
                    <span className={styles.cancelLtCount} style={{ color: '#f97316' }}>
                      {cancellation.by_lead_time.d7_30}
                    </span>
                  </div>
                  <div className={styles.cancelLtItem}>
                    <span className={styles.cancelLtLabel}>30天以前</span>
                    <span className={styles.cancelLtCount}>{cancellation.by_lead_time.over_30d}</span>
                  </div>
                </div>
              </div>
            )}
          </ZCard>
          {/* Phase 16: 月度执行摘要 */}
          <ZCard title={`月度执行摘要（${month}）`}>
            {!execSummary || execSummary.metrics.order_count === 0 ? (
              <ZEmpty title="本月暂无宴会数据" description="" />
            ) : (
              <div className={styles.execSummaryBody}>
                <div className={styles.execMetricGrid}>
                  {([
                    { key: 'revenue_yuan',           label: '营收',       fmt: (v: number) => `¥${v.toLocaleString()}` },
                    { key: 'order_count',             label: '订单数',     fmt: (v: number) => `${v} 单` },
                    { key: 'avg_order_yuan',          label: '客单价',     fmt: (v: number) => `¥${v.toLocaleString()}` },
                    { key: 'conversion_rate_pct',     label: '转化率',     fmt: (v: number) => `${v}%` },
                    { key: 'task_completion_pct',     label: '任务完成',   fmt: (v: number) => `${v}%` },
                    { key: 'exception_rate_pct',      label: '异常率',     fmt: (v: number) => `${v}%` },
                    { key: 'repeat_rate_pct',         label: '复购率',     fmt: (v: number) => `${v}%` },
                    { key: 'cancellation_rate_pct',   label: '取消率',     fmt: (v: number) => `${v}%` },
                    { key: 'revenue_lost_yuan',       label: '损失收入',   fmt: (v: number) => `¥${v.toLocaleString()}` },
                    { key: 'target_achievement_pct',  label: '目标达成',   fmt: (v: number | null) => v != null ? `${v}%` : '—' },
                  ] as { key: keyof ExecSummaryMetrics; label: string; fmt: (v: number | null) => string }[]).map(item => (
                    <div key={item.key} className={styles.execMetricItem}>
                      <span className={styles.execMetricLabel}>{item.label}</span>
                      <span className={styles.execMetricValue}>
                        {item.fmt(execSummary.metrics[item.key] as number | null)}
                      </span>
                    </div>
                  ))}
                </div>
                {execSummary.highlights.length > 0 && (
                  <div className={styles.execInsights}>
                    {execSummary.highlights.map((h, i) => (
                      <div key={i} className={styles.execHighlight}>✅ {h}</div>
                    ))}
                    {execSummary.risks.map((r, i) => (
                      <div key={i} className={styles.execRisk}>⚠️ {r}</div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </ZCard>

          {/* Phase 17: 套餐毛利排行 */}
          <ZCard title="套餐毛利排行">
            {pkgProfit.length === 0 ? (
              <ZEmpty title="暂无套餐数据" description="请先在资源配置中创建套餐" />
            ) : (
              <div className={styles.pkgProfitList}>
                {pkgProfit.slice(0, 8).map(p => {
                  const margin = p.actual_margin_pct ?? p.theoretical_margin_pct ?? 0;
                  return (
                    <div key={p.pkg_id} className={styles.pkgProfitRow}>
                      <div className={styles.pkgProfitName}>
                        <span>{p.name}</span>
                        <span className={styles.pkgProfitPct} style={{ color: margin >= 50 ? 'var(--green, #22c55e)' : margin >= 30 ? '#f97316' : '#ef4444' }}>
                          {margin.toFixed(1)}%
                        </span>
                      </div>
                      <div className={styles.pkgProfitBars}>
                        <div className={styles.pkgBar}>
                          <div className={styles.pkgBarTheo} style={{ width: `${Math.min((p.theoretical_margin_pct ?? 0), 100)}%` }} title={`理论 ${p.theoretical_margin_pct?.toFixed(1)}%`} />
                        </div>
                        {p.actual_margin_pct != null && (
                          <div className={styles.pkgBar}>
                            <div className={styles.pkgBarActual} style={{ width: `${Math.min(p.actual_margin_pct, 100)}%` }} title={`实际 ${p.actual_margin_pct.toFixed(1)}%`} />
                          </div>
                        )}
                      </div>
                      <span className={styles.pkgProfitOrderCnt}>{p.order_count} 单</span>
                    </div>
                  );
                })}
                <div className={styles.pkgProfitLegend}>
                  <span className={styles.pkgLegendTheo}>■ 理论毛利率</span>
                  <span className={styles.pkgLegendActual}>■ 实际毛利率</span>
                </div>
              </div>
            )}
          </ZCard>

          {/* Phase 17: 季节性峰谷 */}
          <ZCard title="季节性规律">
            {!seasonal ? (
              <ZEmpty title="暂无历史数据" description="需要至少1年历史订单" />
            ) : (
              <div className={styles.seasonalBody}>
                <div className={styles.seasonalLabel}>月度热力图（深色 = 高峰）</div>
                <div className={styles.monthHeatRow}>
                  {seasonal.monthly.map(m => (
                    <div
                      key={m.month}
                      className={`${styles.monthCell} ${m.is_peak ? styles.monthCellPeak : ''} ${m.is_low ? styles.monthCellLow : ''}`}
                      title={`${m.month}月 均${m.avg_orders.toFixed(1)}单`}
                    >
                      {m.month}月
                    </div>
                  ))}
                </div>
                <div className={styles.seasonalLabel} style={{ marginTop: 12 }}>周几分布</div>
                <div className={styles.weekdayBars}>
                  {seasonal.weekly.map(d => (
                    <div key={d.weekday} className={styles.weekdayBarItem}>
                      <div className={styles.weekdayBar} style={{ height: `${Math.max(d.relative_pct * 0.8, 4)}px` }} title={`${d.relative_pct.toFixed(1)}%`} />
                      <span className={styles.weekdayLabel}>{d.label.replace('周', '')}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </ZCard>

          {/* Phase 17: 营收预测 */}
          <ZCard title="下月营收预测">
            {!revForecast ? (
              <ZEmpty title="暂无预测数据" description="需要历史订单作为基准" />
            ) : (
              <div className={styles.forecastBody}>
                <div className={styles.forecastTarget}>{revForecast.target_month}</div>
                <div className={styles.forecastKpiRow}>
                  <div className={styles.forecastKpi}>
                    <span className={styles.forecastKpiValue}>¥{revForecast.forecast_yuan.toLocaleString()}</span>
                    <span className={styles.forecastKpiLabel}>预测营收</span>
                  </div>
                  <div className={styles.forecastKpi}>
                    <span className={styles.forecastKpiValue}>¥{revForecast.confirmed_revenue_yuan.toLocaleString()}</span>
                    <span className={styles.forecastKpiLabel}>已确认</span>
                  </div>
                  <div className={styles.forecastKpi}>
                    <span className={styles.forecastKpiValue}>¥{revForecast.base_revenue_yuan.toLocaleString()}</span>
                    <span className={styles.forecastKpiLabel}>历史均值</span>
                  </div>
                </div>
                {revForecast.forecast_yuan > 0 && (
                  <div className={styles.forecastProgress}>
                    <div
                      className={styles.forecastProgressBar}
                      style={{ width: `${Math.min(revForecast.confirmed_revenue_yuan / revForecast.forecast_yuan * 100, 100).toFixed(0)}%` }}
                    />
                  </div>
                )}
                <div className={styles.forecastProgressLabel}>
                  已确认 {revForecast.forecast_yuan > 0 ? (revForecast.confirmed_revenue_yuan / revForecast.forecast_yuan * 100).toFixed(0) : 0}%
                </div>
              </div>
            )}
          </ZCard>

          {/* Phase 18: 线索来源 ROI */}
          {leadSourceRoi.length > 0 && (
            <ZCard title="线索来源 ROI">
              <div className={styles.srcRoiList}>
                {leadSourceRoi.map(s => {
                  const maxRev = Math.max(...leadSourceRoi.map(x => x.revenue_yuan), 1);
                  return (
                    <div key={s.source} className={styles.srcRoiRow}>
                      <span className={styles.srcName}>{s.source}</span>
                      <div className={styles.srcBar}>
                        <div className={styles.srcBarFill} style={{ width: `${(s.revenue_yuan / maxRev * 100).toFixed(0)}%` }} />
                      </div>
                      <span className={styles.srcConv}>{s.conversion_rate_pct}%</span>
                      <span className={styles.srcRevenue}>¥{s.revenue_yuan.toLocaleString()}</span>
                    </div>
                  );
                })}
              </div>
            </ZCard>
          )}

          {/* Phase 18: 价格段成交率分析 */}
          {pricingBuckets.length > 0 && (
            <ZCard title="价格段成交率">
              <div className={styles.priceGrid}>
                {pricingBuckets.map(b => (
                  <div key={b.range} className={styles.priceBucket}>
                    <div className={styles.priceBucketRange}>{b.range}</div>
                    <div className={styles.priceBucketConv}>
                      {b.conversion_rate_pct != null ? `${b.conversion_rate_pct}%` : '—'}
                    </div>
                    <div className={styles.priceBucketLabel}>转化率</div>
                    <div className={styles.priceBucketAvg}>
                      {b.avg_revenue_yuan != null ? `¥${b.avg_revenue_yuan.toLocaleString()}` : '—'}
                    </div>
                    <div className={styles.priceBucketLabel}>件均</div>
                    <div className={styles.priceBucketCount}>{b.lead_count} 线索</div>
                  </div>
                ))}
              </div>
            </ZCard>
          )}
        </>
      )}
    </div>
  );
}

interface CustomerItem {
  id:                       string;
  name:                     string;
  phone:                    string;
  customer_type:            string | null;
  vip_level:                number | null;
  total_banquet_count:      number;
  total_banquet_amount_yuan: number;
  source:                   string | null;
}

interface CustomerDetailResp {
  customer: CustomerItem & { wechat_id?: string | null; company_name?: string | null; tags?: string | null; remark?: string | null };
  leads:    Array<{ lead_id: string; banquet_type: string; expected_date: string | null; stage_label: string }>;
  orders:   Array<{ order_id: string; banquet_type: string; banquet_date: string; order_status: string; total_amount_yuan: number }>;
}

const HQ_STORE_ID = localStorage.getItem('store_id') || 'S001';

function CustomerTab() {
  const [q,           setQ]           = useState('');
  const [debouncedQ,  setDebouncedQ]  = useState('');
  const [customers,   setCustomers]   = useState<CustomerItem[]>([]);
  const [loading,     setLoading]     = useState(false);
  const [detailId,    setDetailId]    = useState<string | null>(null);
  const [detail,      setDetail]      = useState<CustomerDetailResp | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q), 350);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    setLoading(true);
    apiClient.get(
      `/api/v1/banquet-agent/stores/${HQ_STORE_ID}/customers`,
      debouncedQ ? { params: { q: debouncedQ } } : undefined,
    ).then(r => {
      const raw = r.data;
      setCustomers(Array.isArray(raw) ? raw : (raw?.items ?? []));
    }).catch(() => setCustomers([])).finally(() => setLoading(false));
  }, [debouncedQ]);

  const openDetail = async (id: string) => {
    setDetailId(id);
    setDetail(null);
    setDetailLoading(true);
    try {
      const r = await apiClient.get(
        `/api/v1/banquet-agent/stores/${HQ_STORE_ID}/customers/${id}`,
      );
      setDetail(r.data);
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const VIP_LABELS = ['', '⭐', '⭐⭐', '⭐⭐⭐'];

  return (
    <div className={styles.customerTab}>
      <div className={styles.customerSearch}>
        <ZInput
          value={q}
          onChange={v => setQ(v)}
          placeholder="搜索客户姓名 / 手机号…"
        />
      </div>

      {loading ? (
        <ZSkeleton rows={5} />
      ) : !customers.length ? (
        <ZEmpty title="暂无客户" description="尚未录入客户档案" />
      ) : (
        <div className={styles.customerList}>
          {customers.map(c => (
            <div key={c.id} className={styles.customerRow} onClick={() => openDetail(c.id)}>
              <div className={styles.customerLeft}>
                <div className={styles.customerName}>
                  {c.name}
                  {c.vip_level ? <span className={styles.vipTag}>{VIP_LABELS[c.vip_level] ?? ''}</span> : null}
                </div>
                <div className={styles.customerMeta}>
                  {c.phone}
                  {c.customer_type ? ` · ${c.customer_type}` : ''}
                  {c.source ? ` · ${c.source}` : ''}
                </div>
              </div>
              <div className={styles.customerRight}>
                <div className={styles.customerStat}>{c.total_banquet_count} 场</div>
                <div className={styles.customerAmount}>¥{c.total_banquet_amount_yuan.toLocaleString()}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 客户详情 Modal */}
      <ZModal
        open={!!detailId}
        title={detail?.customer?.name ?? '客户档案'}
        onClose={() => { setDetailId(null); setDetail(null); }}
        footer={
          <ZButton variant="ghost" onClick={() => { setDetailId(null); setDetail(null); }}>
            关闭
          </ZButton>
        }
      >
        {detailLoading ? (
          <ZSkeleton rows={6} />
        ) : !detail ? (
          <ZEmpty title="加载失败" description="请重试" />
        ) : (
          <div className={styles.detailBody}>
            {/* 基本信息 */}
            <div className={styles.detailSection}>
              <div className={styles.detailSectionTitle}>基本信息</div>
              <div className={styles.detailGrid}>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>手机</span>
                  <span className={styles.detailValue}>{detail.customer.phone}</span>
                </div>
                {detail.customer.wechat_id && (
                  <div className={styles.detailItem}>
                    <span className={styles.detailLabel}>微信</span>
                    <span className={styles.detailValue}>{detail.customer.wechat_id}</span>
                  </div>
                )}
                {detail.customer.company_name && (
                  <div className={styles.detailItem}>
                    <span className={styles.detailLabel}>公司</span>
                    <span className={styles.detailValue}>{detail.customer.company_name}</span>
                  </div>
                )}
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>宴会总数</span>
                  <span className={styles.detailValue}>{detail.customer.total_banquet_count} 场</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>累计金额</span>
                  <span className={styles.detailValue}>¥{detail.customer.total_banquet_amount_yuan.toLocaleString()}</span>
                </div>
                {detail.customer.remark && (
                  <div className={styles.detailItem} style={{ gridColumn: '1 / -1' }}>
                    <span className={styles.detailLabel}>备注</span>
                    <span className={styles.detailValue}>{detail.customer.remark}</span>
                  </div>
                )}
              </div>
            </div>

            {/* 线索记录 */}
            <div className={styles.detailSection}>
              <div className={styles.detailSectionTitle}>线索记录（{detail.leads.length}）</div>
              {detail.leads.length === 0 ? (
                <div className={styles.detailEmpty}>暂无线索</div>
              ) : detail.leads.map(l => (
                <div key={l.lead_id} className={styles.detailLeadRow}>
                  <span>{l.banquet_type}</span>
                  {l.expected_date && <span>{dayjs(l.expected_date).format('YYYY-MM-DD')}</span>}
                  <ZBadge type="info" text={l.stage_label} />
                </div>
              ))}
            </div>

            {/* 订单记录 */}
            <div className={styles.detailSection}>
              <div className={styles.detailSectionTitle}>订单记录（{detail.orders.length}）</div>
              {detail.orders.length === 0 ? (
                <div className={styles.detailEmpty}>暂无订单</div>
              ) : detail.orders.map(o => (
                <div key={o.order_id} className={styles.detailOrderRow}>
                  <span>{o.banquet_type}</span>
                  <span>{dayjs(o.banquet_date).format('YYYY-MM-DD')}</span>
                  <span>¥{o.total_amount_yuan.toLocaleString()}</span>
                  <ZBadge type="default" text={o.order_status} />
                </div>
              ))}
            </div>
          </div>
        )}
      </ZModal>
    </div>
  );
}

/* ─── 主组件 ─── */

/* ─── 报价管理 Tab ─── */
const QUOTE_STATUS_FILTERS = [
  { value: 'all',      label: '全部'   },
  { value: 'active',   label: '有效'   },
  { value: 'accepted', label: '已接受' },
  { value: 'expired',  label: '已过期' },
];

function QuoteManagementTab() {
  const [statusFilter, setStatusFilter] = useState('all');
  const [quotes, setQuotes] = useState<{
    quote_id: string; lead_id: string; quoted_amount_yuan: number;
    valid_until: string | null; is_accepted: boolean; is_expired: boolean;
    created_at: string | null;
  }[]>([]);
  const [total,   setTotal]   = useState(0);
  const [loading, setLoading] = useState(false);
  const [revoking, setRevoking] = useState<string | null>(null);

  const load = useCallback(async (status: string) => {
    setLoading(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/quotes`,
        { params: { status, page: 1, page_size: 30 } },
      );
      setQuotes(resp.data?.items ?? []);
      setTotal(resp.data?.total ?? 0);
    } catch {
      setQuotes([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(statusFilter); }, [load, statusFilter]);

  const handleRevoke = async (leadId: string, quoteId: string) => {
    setRevoking(quoteId);
    try {
      await apiClient.delete(
        `/api/v1/banquet-agent/stores/${STORE_ID}/leads/${leadId}/quotes/${quoteId}`,
      );
      load(statusFilter);
    } catch (e) {
      handleApiError(e, '撤销失败');
    } finally {
      setRevoking(null);
    }
  };

  return (
    <div className={styles.quoteTab}>
      <div className={styles.chipBar}>
        {QUOTE_STATUS_FILTERS.map(f => (
          <button
            key={f.value}
            className={`${styles.chip} ${statusFilter === f.value ? styles.chipActive : ''}`}
            onClick={() => setStatusFilter(f.value)}
          >
            {f.label}
          </button>
        ))}
      </div>
      <ZCard>
        {loading ? (
          <ZSkeleton rows={4} />
        ) : quotes.length === 0 ? (
          <ZEmpty title="暂无报价" description="当前过滤条件下没有报价记录" />
        ) : (
          <>
            <div className={styles.quoteTotal}>共 {total} 条</div>
            <div className={styles.quoteList}>
              {quotes.map(q => (
                <div key={q.quote_id} className={styles.quoteRow}>
                  <div className={styles.quoteLeft}>
                    <div className={styles.quoteAmount}>¥{q.quoted_amount_yuan.toLocaleString()}</div>
                    <div className={styles.quoteMeta}>
                      {q.valid_until ? `有效至 ${q.valid_until}` : '无截止日期'}
                    </div>
                  </div>
                  <div className={styles.quoteRight}>
                    {q.is_accepted ? (
                      <ZBadge type="success" text="已接受" />
                    ) : q.is_expired ? (
                      <ZBadge type="default" text="已过期" />
                    ) : (
                      <>
                        <ZBadge type="info" text="有效" />
                        <ZButton
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRevoke(q.lead_id, q.quote_id)}
                          disabled={revoking === q.quote_id}
                        >
                          {revoking === q.quote_id ? '…' : '撤销'}
                        </ZButton>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </ZCard>
    </div>
  );
}

/* ─── 厅房月历 Tab ─── */
interface HallDayCell { date: string; booked: boolean; slots: { slot_name: string; banquet_type: string }[] }
interface HallScheduleData { hall_id: string; hall_name: string; hall_type: string; days: HallDayCell[] }

function HallScheduleTab() {
  const [calMonth,  setCalMonth]  = useState(dayjs().format('YYYY-MM'));
  const [halls,     setHalls]     = useState<HallScheduleData[]>([]);
  const [loading,   setLoading]   = useState(false);
  const [activeHall, setActiveHall] = useState<string | null>(null);

  const loadSchedule = useCallback(async (m: string) => {
    setLoading(true);
    const [y, mo] = m.split('-').map(Number);
    const STORE = localStorage.getItem('store_id') || 'S001';
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE}/halls/monthly-schedule`,
        { params: { year: y, month: mo } },
      );
      const rawHalls: HallScheduleData[] = resp.data?.halls ?? [];
      setHalls(rawHalls);
      if (rawHalls.length > 0 && !activeHall) setActiveHall(rawHalls[0].hall_id);
    } catch {
      setHalls([]);
    } finally {
      setLoading(false);
    }
  }, [activeHall]);

  useEffect(() => { loadSchedule(calMonth); }, [loadSchedule, calMonth]);

  const firstDay  = dayjs(`${calMonth}-01`);
  const startDow  = firstDay.day();
  const daysInMonth = firstDay.daysInMonth();

  const currentHall = halls.find(h => h.hall_id === activeHall) ?? halls[0];

  const dayMap: Record<string, HallDayCell> = {};
  (currentHall?.days ?? []).forEach(d => { dayMap[d.date] = d; });

  const cells: (HallDayCell | null)[] = [
    ...Array(startDow).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => {
      const dateStr = firstDay.add(i, 'day').format('YYYY-MM-DD');
      return dayMap[dateStr] ?? { date: dateStr, booked: false, slots: [] };
    }),
  ];
  while (cells.length % 7 !== 0) cells.push(null);

  return (
    <div className={styles.tabContent}>
      <div className={styles.calHeader}>
        <ZSelect
          value={calMonth}
          options={buildMonthOptions()}
          onChange={v => setCalMonth(v as string)}
          style={{ width: 120 }}
        />
      </div>

      {/* Hall selector */}
      {halls.length > 1 && (
        <div className={styles.hallSelector}>
          {halls.map(h => (
            <button
              key={h.hall_id}
              className={`${styles.hallChip} ${activeHall === h.hall_id ? styles.hallChipActive : ''}`}
              onClick={() => setActiveHall(h.hall_id)}
            >
              {h.hall_name}
            </button>
          ))}
        </div>
      )}

      {loading ? (
        <ZSkeleton rows={6} />
      ) : !currentHall ? (
        <ZEmpty title="暂无厅房数据" description="请先在资源配置中添加厅房" />
      ) : (
        <ZCard title={`${currentHall.hall_name} — ${calMonth} 档期`}>
          <div className={styles.calGrid}>
            {WEEK_DAYS.map(d => <div key={d} className={styles.calWeekday}>{d}</div>)}
            {cells.map((cell, idx) => {
              if (!cell) return <div key={`empty-${idx}`} className={styles.calEmpty} />;
              return (
                <div
                  key={cell.date}
                  className={`${styles.calCell} ${cell.booked ? styles.hallBooked : ''}`}
                >
                  <span className={styles.calDay}>{dayjs(cell.date).date()}</span>
                  {cell.booked && (
                    <div className={styles.calDots}>
                      {cell.slots.map((s, si) => (
                        <span
                          key={si}
                          className={styles.dotConfirmed}
                          title={`${s.slot_name} · ${s.banquet_type}`}
                        />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <div className={styles.calLegend}>
            <span className={styles.legendItem}><span className={styles.dotConfirmed} />已预订</span>
          </div>
        </ZCard>
      )}
    </div>
  );
}

/* ─── 跨店对比 Tab ─── */
/* ─── Phase 16: interfaces ─── */
interface BenchmarkMetric {
  metric:       string;
  label:        string;
  store_value:  number;
  brand_avg:    number;
  delta_pct:    number;
  status:       'above' | 'below' | 'on_par';
  rank:         number;
  total_stores: number;
}

interface StoreComparisonRow {
  store_id:             string;
  store_name:           string;
  revenue_yuan:         number;
  order_count:          number;
  conversion_rate_pct:  number;
  repeat_rate_pct:      number;
  is_self:              boolean;
  rank:                 number | null;
}

interface ExecSummaryMetrics {
  revenue_yuan:             number;
  order_count:              number;
  avg_order_yuan:           number;
  conversion_rate_pct:      number;
  task_completion_pct:      number;
  exception_rate_pct:       number;
  repeat_rate_pct:          number;
  cancellation_rate_pct:    number;
  revenue_lost_yuan:        number;
  target_achievement_pct:   number | null;
}

interface ExecSummaryData {
  year:       number;
  month:      number;
  metrics:    ExecSummaryMetrics;
  highlights: string[];
  risks:      string[];
}

function CrossStoreTab() {
  const [month,     setMonth]     = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });
  const [benchmark,   setBenchmark]   = useState<{ self_rank: number; total_stores: number; metrics: BenchmarkMetric[] } | null>(null);
  const [comparison,  setComparison]  = useState<StoreComparisonRow[]>([]);
  const [brandAvg,    setBrandAvg]    = useState<Partial<StoreComparisonRow> | null>(null);
  const [loading,     setLoading]     = useState(false);

  const load = useCallback(async (m: string) => {
    setLoading(true);
    const [y, mo] = m.split('-').map(Number);
    const STORE = localStorage.getItem('store_id') || 'S001';
    try {
      const [bmR, compR] = await Promise.allSettled([
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/benchmark`, { params: { year: y, month: mo } }),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/brand-comparison`, { params: { year: y, month: mo } }),
      ]);
      if (bmR.status === 'fulfilled')   setBenchmark(bmR.value.data);
      if (compR.status === 'fulfilled') {
        setComparison(compR.value.data?.stores ?? []);
        setBrandAvg(compR.value.data?.brand_avg ?? null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(month); }, [load, month]);

  return (
    <div className={styles.crossStoreTab}>
      <div className={styles.analyticsPicker}>
        <ZInput type="month" value={month} onChange={v => setMonth(v)} />
      </div>

      {/* Benchmark 卡 */}
      <ZCard title="本店 vs 品牌均值">
        {loading ? (
          <ZSkeleton rows={3} />
        ) : !benchmark || benchmark.metrics.length === 0 ? (
          <ZEmpty title="暂无对比数据" description="品牌下暂无其他门店数据" />
        ) : (
          <div className={styles.benchmarkBody}>
            <div className={styles.benchmarkRank}>
              排名 <strong>{benchmark.self_rank}/{benchmark.total_stores}</strong> 家门店
            </div>
            <div className={styles.benchmarkGrid}>
              {benchmark.metrics.map(m2 => (
                <div key={m2.metric} className={styles.benchmarkCard}>
                  <div className={styles.benchmarkLabel}>{m2.label}</div>
                  <div className={styles.benchmarkValue}>
                    {typeof m2.store_value === 'number' && m2.metric === 'revenue_yuan'
                      ? `¥${m2.store_value.toLocaleString()}`
                      : `${m2.store_value}${m2.metric.endsWith('pct') ? '%' : ''}`
                    }
                  </div>
                  <div className={`${styles.benchmarkDelta} ${
                    m2.status === 'above' ? styles.deltaAbove :
                    m2.status === 'below' ? styles.deltaBelow : styles.deltaOnPar
                  }`}>
                    {m2.delta_pct > 0 ? '+' : ''}{m2.delta_pct}% vs 均值
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      {/* 全店对比表 */}
      <ZCard title="全店 KPI 排名">
        {loading ? (
          <ZSkeleton rows={4} />
        ) : comparison.length === 0 ? (
          <ZEmpty title="暂无跨店数据" description="当前品牌下暂无门店记录" />
        ) : (
          <div className={styles.crossStoreList}>
            {[...comparison, ...(brandAvg ? [{ ...brandAvg, rank: null, is_self: false }] : [])].map((r, i) => (
              <div key={r.store_id ?? `avg-${i}`} className={`${styles.crossStoreRow} ${r.is_self ? styles.crossStoreSelf : ''}`}>
                <div className={styles.crossStoreRank}>{r.rank ?? '—'}</div>
                <div className={styles.crossStoreInfo}>
                  <div className={styles.crossStoreId}>{(r as StoreComparisonRow).store_name ?? r.store_id}</div>
                  <div className={styles.crossStoreMeta}>
                    {(r as StoreComparisonRow).order_count} 单 · 转化 {(r as StoreComparisonRow).conversion_rate_pct}%
                  </div>
                </div>
                <div className={styles.crossStoreRight}>
                  <div className={styles.crossStoreRevenue}>¥{(r as StoreComparisonRow).revenue_yuan?.toLocaleString()}</div>
                  <div className={styles.crossStoreMargin}>复购 {(r as StoreComparisonRow).repeat_rate_pct}%</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 18: 合同履约 Tab ─── */
interface ComplianceOrder { order_id: string; banquet_date: string; banquet_type: string; contact_name: string | null; days_until?: number; deposit_yuan?: number; days_overdue?: number; overdue_yuan?: number; contact_phone?: string | null; has_contract?: boolean }
interface ComplianceData {
  total_orders: number;
  unsigned:    { count: number; orders: ComplianceOrder[] };
  deposit_due: { count: number; total_overdue_yuan: number; orders: ComplianceOrder[] };
  final_due:   { count: number; total_overdue_yuan: number; orders: ComplianceOrder[] };
}

function ContractTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [data,    setData]    = useState<ComplianceData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/contracts/compliance`)
      .then(r => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [STORE]);

  if (loading) return <ZSkeleton rows={5} />;
  if (!data)   return <ZEmpty title="合同数据加载失败" description="请稍后重试" />;

  const BT_LABEL: Record<string, string> = { wedding: '婚宴', birthday: '寿宴', business: '商务宴', full_month: '满月宴', graduation: '升学宴', other: '其他' };

  return (
    <div className={styles.contractTab}>
      <div className={styles.contractKpiRow}>
        <div className={styles.contractKpi}>
          <span className={styles.contractKpiVal} style={{ color: data.unsigned.count > 0 ? '#ef4444' : '#22c55e' }}>{data.unsigned.count}</span>
          <span className={styles.contractKpiLabel}>未签合同</span>
        </div>
        <div className={styles.contractKpi}>
          <span className={styles.contractKpiVal} style={{ color: data.deposit_due.count > 0 ? '#ef4444' : '#22c55e' }}>{data.deposit_due.count}</span>
          <span className={styles.contractKpiLabel}>定金未付</span>
        </div>
        <div className={styles.contractKpi}>
          <span className={styles.contractKpiVal} style={{ color: data.final_due.count > 0 ? '#f97316' : '#22c55e' }}>{data.final_due.count}</span>
          <span className={styles.contractKpiLabel}>尾款逾期</span>
        </div>
        <div className={styles.contractKpi}>
          <span className={styles.contractKpiVal}>{data.total_orders}</span>
          <span className={styles.contractKpiLabel}>总订单</span>
        </div>
      </div>

      {data.unsigned.count > 0 && (
        <ZCard title={`未签合同（${data.unsigned.count}）`}>
          <div className={styles.contractAlertList}>
            {data.unsigned.orders.map(o => (
              <div key={o.order_id} className={styles.contractAlertRow}>
                <div className={styles.contractAlertDate}>{o.banquet_date} · {BT_LABEL[o.banquet_type] ?? o.banquet_type}</div>
                <div className={styles.contractAlertMeta}>
                  <span>{o.contact_name ?? '—'}</span>
                  {o.days_until != null && <ZBadge type={o.days_until <= 7 ? 'warning' : 'info'} text={`${o.days_until} 天后`} />}
                  <ZBadge type="default" text={o.has_contract ? '草稿' : '无合同'} />
                </div>
              </div>
            ))}
          </div>
        </ZCard>
      )}

      {data.deposit_due.count > 0 && (
        <ZCard title={`定金未付（${data.deposit_due.count}单 · 共¥${data.deposit_due.total_overdue_yuan.toLocaleString()}）`}>
          <div className={styles.contractAlertList}>
            {data.deposit_due.orders.map(o => (
              <div key={o.order_id} className={styles.contractAlertRow}>
                <div className={styles.contractAlertDate}>{o.banquet_date} · {BT_LABEL[o.banquet_type] ?? o.banquet_type}</div>
                <div className={styles.contractAlertMeta}>
                  <span>{o.contact_name ?? '—'}</span>
                  {o.contact_phone && <span className={styles.contractPhone}>{o.contact_phone}</span>}
                  <span className={styles.contractAlertAmount}>定金¥{(o.deposit_yuan ?? 0).toLocaleString()}</span>
                  <ZBadge type="warning" text={`${o.days_until} 天后宴会`} />
                </div>
              </div>
            ))}
          </div>
        </ZCard>
      )}

      {data.final_due.count > 0 && (
        <ZCard title={`尾款逾期（${data.final_due.count}单 · 共¥${data.final_due.total_overdue_yuan.toLocaleString()}）`}>
          <div className={styles.contractAlertList}>
            {data.final_due.orders.map(o => (
              <div key={o.order_id} className={styles.contractAlertRow}>
                <div className={styles.contractAlertDate}>{o.banquet_date} · {BT_LABEL[o.banquet_type] ?? o.banquet_type}</div>
                <div className={styles.contractAlertMeta}>
                  <span>{o.contact_name ?? '—'}</span>
                  {o.contact_phone && <span className={styles.contractPhone}>{o.contact_phone}</span>}
                  <span className={styles.contractAlertAmount}>逾期¥{(o.overdue_yuan ?? 0).toLocaleString()}</span>
                  <ZBadge type="default" text={`已过 ${o.days_overdue} 天`} />
                </div>
              </div>
            ))}
          </div>
        </ZCard>
      )}

      {data.unsigned.count === 0 && data.deposit_due.count === 0 && data.final_due.count === 0 && (
        <ZEmpty title="合同履约全部正常" description="无待处理事项" />
      )}
    </div>
  );
}

/* ─── Phase 18: 客户评价 Tab ─── */
interface ReviewSummaryData {
  total: number; avg_score: number | null;
  score_distribution: Record<string, number>;
  monthly_trend: { month: string; avg_score: number; count: number }[];
  by_banquet_type: { banquet_type: string; avg_score: number; count: number }[];
}
interface LowScoreItem { review_id: string; order_id: string; score: number; banquet_date: string; banquet_type: string; contact_name: string | null; ai_summary: string | null; tags: string[]; created_at: string | null }

function ReviewsTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [summary,    setSummary]    = useState<ReviewSummaryData | null>(null);
  const [lowScores,  setLowScores]  = useState<LowScoreItem[]>([]);
  const [loading,    setLoading]    = useState(true);

  useEffect(() => {
    Promise.allSettled([
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/reviews/summary`, { params: { months: 6 } }),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/reviews/low-score-alerts`, { params: { threshold: 3 } }),
    ]).then(([sumR, lowR]) => {
      if (sumR.status === 'fulfilled')  setSummary(sumR.value.data);
      if (lowR.status === 'fulfilled')  setLowScores(lowR.value.data?.items ?? []);
    }).finally(() => setLoading(false));
  }, [STORE]);

  const STARS = ['1', '2', '3', '4', '5'];
  const maxDist = summary ? Math.max(...STARS.map(s => summary.score_distribution[s] ?? 0), 1) : 1;

  if (loading) return <ZSkeleton rows={6} />;

  return (
    <div className={styles.reviewTab}>
      {/* KPI 行 */}
      <div className={styles.reviewKpiRow}>
        <div className={styles.reviewKpi}>
          <span className={styles.reviewKpiVal}>{summary?.total ?? 0}</span>
          <span className={styles.reviewKpiLabel}>总评价</span>
        </div>
        <div className={styles.reviewKpi}>
          <span className={styles.reviewKpiVal}>{summary?.avg_score?.toFixed(1) ?? '—'}</span>
          <span className={styles.reviewKpiLabel}>均分</span>
        </div>
        <div className={styles.reviewKpi}>
          <span className={styles.reviewKpiVal} style={{ color: lowScores.length > 0 ? '#ef4444' : '#22c55e' }}>{lowScores.length}</span>
          <span className={styles.reviewKpiLabel}>低分预警</span>
        </div>
      </div>

      {/* 评分分布 */}
      {summary && summary.total > 0 && (
        <ZCard title="评分分布">
          <div className={styles.reviewScoreDist}>
            {STARS.map(s => (
              <div key={s} className={styles.reviewScoreRow}>
                <span className={styles.reviewStarLabel}>{s}★</span>
                <div className={styles.reviewScoreBar}>
                  <div
                    className={styles.reviewScoreBarFill}
                    style={{
                      width: `${((summary.score_distribution[s] ?? 0) / maxDist * 100).toFixed(0)}%`,
                      background: Number(s) >= 4 ? '#22c55e' : Number(s) === 3 ? '#f97316' : '#ef4444',
                    }}
                  />
                </div>
                <span className={styles.reviewStarCount}>{summary.score_distribution[s] ?? 0}</span>
              </div>
            ))}
          </div>
        </ZCard>
      )}

      {/* 月度趋势 */}
      {summary && summary.monthly_trend.length > 0 && (
        <ZCard title="月度均分趋势">
          <div className={styles.reviewTrendRow}>
            {summary.monthly_trend.map(m => (
              <div key={m.month} className={styles.reviewTrendItem}>
                <div
                  className={styles.reviewTrendBar}
                  style={{ height: `${(m.avg_score / 5 * 60).toFixed(0)}px`, background: m.avg_score >= 4 ? '#22c55e' : m.avg_score >= 3 ? '#f97316' : '#ef4444' }}
                  title={`${m.avg_score.toFixed(1)} (${m.count}条)`}
                />
                <span className={styles.reviewTrendLabel}>{m.month.slice(5)}</span>
              </div>
            ))}
          </div>
        </ZCard>
      )}

      {/* 低分预警 */}
      {lowScores.length > 0 && (
        <ZCard title={`低分预警（≤3分，近90天）`}>
          <div className={styles.reviewLowList}>
            {lowScores.map(r => (
              <div key={r.review_id} className={styles.reviewLowRow}>
                <div className={styles.reviewLowScore} style={{ color: r.score <= 2 ? '#ef4444' : '#f97316' }}>
                  {r.score}★
                </div>
                <div className={styles.reviewLowBody}>
                  <div className={styles.reviewLowMeta}>
                    <span>{r.banquet_date}</span>
                    <span>{r.banquet_type}</span>
                    {r.contact_name && <span>{r.contact_name}</span>}
                  </div>
                  {r.ai_summary && <div className={styles.reviewLowText}>{r.ai_summary}</div>}
                  {r.tags.length > 0 && (
                    <div className={styles.reviewLowTags}>
                      {r.tags.map((t, i) => <ZBadge key={i} type="warning" text={t} />)}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </ZCard>
      )}

      {(!summary || summary.total === 0) && lowScores.length === 0 && (
        <ZEmpty title="暂无评价数据" description="宴会完成后可在订单详情生成评价" />
      )}
    </div>
  );
}

/* ─── Phase 19: 宴后复盘 Tab ─── */

interface CostByType {
  banquet_type: string;
  event_count: number;
  revenue_yuan: number;
  ingredient_cost_yuan: number;
  labor_cost_yuan: number;
  material_cost_yuan: number;
  other_cost_yuan: number;
  total_cost_yuan: number;
  gross_profit_yuan: number;
  gross_margin_pct: number | null;
}

interface AgingBucket {
  label: string;
  count: number;
  amount_yuan: number;
}

interface RankingRow {
  order_id: string;
  banquet_date: string;
  banquet_type: string;
  contact_name: string | null;
  total_yuan: number;
  gross_margin_pct: number | null;
  gross_profit_yuan: number;
  customer_rating: number | null;
}

function PostEventTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [costData,  setCostData]  = useState<CostByType[]>([]);
  const [aging,     setAging]     = useState<AgingBucket[]>([]);
  const [ranking,   setRanking]   = useState<RankingRow[]>([]);
  const [loading,   setLoading]   = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/cost-breakdown`),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/payment-aging`),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/event-performance-ranking`, { params: { sort_by: 'margin', top_n: 5 } }),
    ]).then(([c, a, r]) => {
      if (c.status === 'fulfilled') setCostData(c.value.data?.by_type ?? []);
      if (a.status === 'fulfilled') setAging(a.value.data?.buckets ?? []);
      if (r.status === 'fulfilled') setRanking(r.value.data?.ranking ?? []);
    }).finally(() => setLoading(false));
  }, [STORE]);

  const AGING_COLORS: Record<string, string> = {
    '0-7天': '#22c55e', '8-30天': '#f59e0b', '31-60天': '#f97316', '60天+': '#ef4444',
  };

  if (loading) return <ZSkeleton rows={6} />;

  return (
    <div className={styles.postEventTab}>
      {/* 场次绩效排行 */}
      <ZCard title="场次绩效排行（毛利率 Top-5）">
        {ranking.length === 0 ? (
          <ZEmpty title="暂无已完成场次数据" />
        ) : (
          <div className={styles.rankingList}>
            {ranking.map((row, idx) => (
              <div key={row.order_id} className={styles.rankingRow}>
                <div className={styles.rankingIdx}>{idx + 1}</div>
                <div className={styles.rankingBody}>
                  <div className={styles.rankingTitle}>
                    {row.banquet_type} · {row.banquet_date}
                    {row.contact_name ? ` · ${row.contact_name}` : ''}
                  </div>
                  <div className={styles.rankingMeta}>
                    总额 ¥{row.total_yuan.toLocaleString()}
                    {row.customer_rating != null ? ` · ⭐ ${row.customer_rating}` : ''}
                  </div>
                </div>
                <div className={styles.rankingMargin}>
                  {row.gross_margin_pct != null ? `${row.gross_margin_pct}%` : '-'}
                </div>
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* 成本穿透 */}
      <ZCard title="成本穿透（按宴会类型）">
        {costData.length === 0 ? (
          <ZEmpty title="暂无成本快照数据" />
        ) : (
          <div className={styles.costBreakdown}>
            {costData.map(row => {
              const maxCost = Math.max(...costData.map(r => r.total_cost_yuan), 1);
              return (
                <div key={row.banquet_type} className={styles.costRow}>
                  <div className={styles.costType}>{row.banquet_type}</div>
                  <div className={styles.costBars}>
                    {[
                      { label: '原料', val: row.ingredient_cost_yuan, color: '#3b82f6' },
                      { label: '人工', val: row.labor_cost_yuan,      color: '#8b5cf6' },
                      { label: '物料', val: row.material_cost_yuan,   color: '#06b6d4' },
                      { label: '其他', val: row.other_cost_yuan,      color: '#94a3b8' },
                    ].map(seg => (
                      <div key={seg.label} className={styles.costSeg}>
                        <div className={styles.costSegLabel}>{seg.label}</div>
                        <div className={styles.costSegBar}>
                          <div
                            className={styles.costSegFill}
                            style={{ width: `${Math.round(seg.val / maxCost * 100)}%`, background: seg.color }}
                          />
                        </div>
                        <div className={styles.costSegVal}>¥{seg.val.toLocaleString()}</div>
                      </div>
                    ))}
                  </div>
                  <div className={styles.costMargin}>
                    毛利率 {row.gross_margin_pct != null ? `${row.gross_margin_pct}%` : '-'}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </ZCard>

      {/* 账龄分析 */}
      <ZCard title="应收账款账龄">
        {aging.length === 0 ? (
          <ZEmpty title="暂无逾期应收款" />
        ) : (
          <div className={styles.agingGrid}>
            {aging.map(bk => (
              <div
                key={bk.label}
                className={styles.agingBucket}
                style={{ borderLeft: `4px solid ${AGING_COLORS[bk.label] ?? '#94a3b8'}` }}
              >
                <div className={styles.agingLabel} style={{ color: AGING_COLORS[bk.label] }}>{bk.label}</div>
                <div className={styles.agingAmount}>¥{bk.amount_yuan.toLocaleString()}</div>
                <div className={styles.agingCount}>{bk.count} 单</div>
              </div>
            ))}
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 19: 运营健康 Tab ─── */

interface HealthDimension {
  name: string;
  score: number;
  max: number;
  detail: string;
}

interface HealthScore {
  total_score: number;
  grade: string;
  dimensions: HealthDimension[];
}

interface BenchmarkRow {
  label: string;
  year: number;
  month: number;
  event_count: number;
  revenue_yuan: number;
  gross_profit_yuan: number;
}

interface QuarterlySummary {
  year: number;
  quarter: number;
  period: { start: string; end: string };
  total_orders: number;
  confirmed_orders: number;
  total_revenue_yuan: number;
  total_paid_yuan: number;
  avg_gross_margin_pct: number | null;
  avg_customer_rating: number | null;
  unsigned_contracts: number;
  lead_count: number;
}

function HealthScoreTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [health,    setHealth]    = useState<HealthScore | null>(null);
  const [benchmark, setBenchmark] = useState<BenchmarkRow[]>([]);
  const [quarterly, setQuarterly] = useState<QuarterlySummary | null>(null);
  const [loading,   setLoading]   = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/operations-health-score`),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/monthly-benchmark`, { params: { months: 12 } }),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/reports/quarterly-summary`),
    ]).then(([h, b, q]) => {
      if (h.status === 'fulfilled') setHealth(h.value.data);
      if (b.status === 'fulfilled') setBenchmark(b.value.data?.data ?? []);
      if (q.status === 'fulfilled') setQuarterly(q.value.data);
    }).finally(() => setLoading(false));
  }, [STORE]);

  if (loading) return <ZSkeleton rows={6} />;

  const scoreColor = (s: number) => s >= 80 ? '#22c55e' : s >= 60 ? '#f59e0b' : '#ef4444';
  const maxRevenue = Math.max(...benchmark.map(r => r.revenue_yuan), 1);

  return (
    <div className={styles.healthTab}>
      {/* 总分仪表 */}
      {health && (
        <ZCard title="运营健康评分">
          <div className={styles.healthScoreRow}>
            <div
              className={styles.healthScoreBig}
              style={{ color: scoreColor(health.total_score) }}
            >
              {health.total_score}
            </div>
            <div className={styles.healthGrade} style={{ color: scoreColor(health.total_score) }}>
              {health.grade} 级
            </div>
          </div>
          <div className={styles.healthDims}>
            {health.dimensions.map(dim => (
              <div key={dim.name} className={styles.healthDimRow}>
                <div className={styles.healthDimName}>{dim.name}</div>
                <div className={styles.healthDimBar}>
                  <div
                    className={styles.healthDimFill}
                    style={{
                      width: `${Math.round(dim.score / dim.max * 100)}%`,
                      background: scoreColor(dim.score / dim.max * 100),
                    }}
                  />
                </div>
                <div className={styles.healthDimScore}>{dim.score}/{dim.max}</div>
                <div className={styles.healthDimDetail}>{dim.detail}</div>
              </div>
            ))}
          </div>
        </ZCard>
      )}

      {/* 季度摘要 */}
      {quarterly && (
        <ZCard title={`Q${quarterly.quarter} ${quarterly.year} 季度摘要`}>
          <div className={styles.qSummaryGrid}>
            <div className={styles.qSummaryItem}>
              <div className={styles.qSummaryVal}>{quarterly.total_orders}</div>
              <div className={styles.qSummaryLabel}>总场次</div>
            </div>
            <div className={styles.qSummaryItem}>
              <div className={styles.qSummaryVal}>¥{quarterly.total_revenue_yuan.toLocaleString()}</div>
              <div className={styles.qSummaryLabel}>总收入</div>
            </div>
            <div className={styles.qSummaryItem}>
              <div className={styles.qSummaryVal}>
                {quarterly.avg_gross_margin_pct != null ? `${quarterly.avg_gross_margin_pct}%` : '-'}
              </div>
              <div className={styles.qSummaryLabel}>平均毛利率</div>
            </div>
            <div className={styles.qSummaryItem}>
              <div className={styles.qSummaryVal}>
                {quarterly.avg_customer_rating != null ? quarterly.avg_customer_rating.toFixed(1) : '-'}
              </div>
              <div className={styles.qSummaryLabel}>评价均分</div>
            </div>
            <div className={styles.qSummaryItem}>
              <div className={styles.qSummaryVal}>{quarterly.unsigned_contracts}</div>
              <div className={styles.qSummaryLabel}>未签合同</div>
            </div>
            <div className={styles.qSummaryItem}>
              <div className={styles.qSummaryVal}>{quarterly.lead_count}</div>
              <div className={styles.qSummaryLabel}>线索数</div>
            </div>
          </div>
        </ZCard>
      )}

      {/* 月度基准折线（简易条形替代，避免引入额外 ECharts 实例） */}
      <ZCard title="12个月收入趋势">
        {benchmark.length === 0 ? (
          <ZEmpty title="暂无历史数据" />
        ) : (
          <div className={styles.benchmarkChart}>
            {benchmark.map(row => (
              <div key={row.label} className={styles.benchmarkItem}>
                <div
                  className={styles.benchmarkBar}
                  style={{ height: `${Math.round(row.revenue_yuan / maxRevenue * 80)}px` }}
                  title={`¥${row.revenue_yuan.toLocaleString()}`}
                />
                <div className={styles.benchmarkLabel}>{`${row.month}月`}</div>
              </div>
            ))}
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 17: 运营简报 Tab ─── */
function DailyBriefTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [brief,     setBrief]     = useState<DailyBriefData | null>(null);
  const [loading,   setLoading]   = useState(true);
  const [pushing,   setPushing]   = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/operations/daily-brief`, { params: { days: 7 } });
      setBrief(r.data);
    } catch {
      setBrief(null);
    } finally {
      setLoading(false);
    }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  const handlePush = async () => {
    setPushing(true);
    try {
      await apiClient.post(`/api/v1/banquet-agent/stores/${STORE}/operations/daily-brief/push`);
      await load();
    } catch (e) {
      handleApiError(e, '推送简报失败');
    } finally {
      setPushing(false);
    }
  };

  const riskColor = (level: string) => level === 'high' ? '#ef4444' : level === 'medium' ? '#f97316' : '#22c55e';
  const riskLabel = (level: string) => level === 'high' ? '高风险' : level === 'medium' ? '注意' : '正常';

  return (
    <div className={styles.briefTab}>
      <div className={styles.briefHeader}>
        <div className={styles.briefTitle}>运营简报（未来7天）</div>
        <ZButton variant="primary" size="sm" onClick={handlePush} disabled={pushing}>
          {pushing ? '推送中…' : '推送简报'}
        </ZButton>
      </div>
      {loading ? (
        <ZSkeleton rows={4} />
      ) : !brief ? (
        <ZEmpty title="暂无数据" description="请稍后重试" />
      ) : (
        <>
          <div className={styles.briefKpiRow}>
            <div className={styles.briefKpi}>
              <span className={styles.briefKpiValue}>{brief.today_banquets}</span>
              <span className={styles.briefKpiLabel}>今日宴会</span>
            </div>
            <div className={styles.briefKpi}>
              <span className={styles.briefKpiValue}>{brief.next_n_banquets}</span>
              <span className={styles.briefKpiLabel}>7天内宴会</span>
            </div>
            <div className={styles.briefKpi}>
              <span className={styles.briefKpiValue} style={{ color: '#ef4444' }}>
                {brief.alerts.filter(a => a.risk_level === 'high').length}
              </span>
              <span className={styles.briefKpiLabel}>高风险</span>
            </div>
            <div className={styles.briefKpi}>
              <span className={styles.briefKpiValue} style={{ color: '#f97316' }}>
                {brief.alerts.filter(a => a.risk_level === 'medium').length}
              </span>
              <span className={styles.briefKpiLabel}>需关注</span>
            </div>
          </div>
          {brief.alerts.length === 0 ? (
            <ZEmpty title="近7天无待处理事项" description="所有宴会准备就绪" />
          ) : (
            <div className={styles.briefAlertList}>
              {brief.alerts.map(a => (
                <div key={a.order_id} className={styles.briefAlertRow} style={{ borderLeftColor: riskColor(a.risk_level) }}>
                  <div className={styles.briefAlertMeta}>
                    <span className={styles.briefAlertDate}>{a.banquet_date}</span>
                    <span className={styles.briefAlertType}>{a.banquet_type}</span>
                    <ZBadge
                      type={a.risk_level === 'high' ? 'warning' : a.risk_level === 'medium' ? 'info' : 'success'}
                      text={riskLabel(a.risk_level)}
                    />
                  </div>
                  <div className={styles.briefAlertIssues}>
                    {a.pending_tasks > 0 && <span>待完任务 {a.pending_tasks}</span>}
                    {a.unpaid_yuan > 0 && <span>未收款 ¥{a.unpaid_yuan.toLocaleString()}</span>}
                    {a.open_exceptions > 0 && <span>异常 {a.open_exceptions}</span>}
                    {a.pending_tasks === 0 && a.unpaid_yuan === 0 && a.open_exceptions === 0 && <span className={styles.briefAlertOk}>准备就绪</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function HQBanquet() {
  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>宴会经营仪表盘</div>
      </div>
      <ZTabs
        items={[
          { key: 'dashboard',  label: '仪表盘',  children: <DashboardTab /> },
          { key: 'pipeline',  label: '销售管道', children: <PipelineTab /> },
          { key: 'calendar',  label: '销控日历', children: <AvailabilityTab /> },
          { key: 'ai',        label: 'AI 建议',  children: <AITab /> },
          { key: 'profit',    label: '利润复盘', children: <ProfitTab /> },
          { key: 'resource',  label: '资源配置', children: <ResourceTab /> },
          { key: 'customers', label: '客户档案', children: <CustomerTab /> },
          { key: 'analytics', label: '转化分析', children: <AnalyticsTab /> },
          { key: 'quotes',    label: '报价管理',  children: <QuoteManagementTab /> },
          { key: 'hallsched', label: '厅房月历',  children: <HallScheduleTab /> },
          { key: 'crossstore',   label: '跨店对比',  children: <CrossStoreTab /> },
          { key: 'dailybrief',   label: '运营简报',  children: <DailyBriefTab /> },
          { key: 'contract',     label: '合同履约',  children: <ContractTab /> },
          { key: 'reviews',      label: '客户评价',  children: <ReviewsTab /> },
          { key: 'postevent',    label: '宴后复盘',  children: <PostEventTab /> },
          { key: 'healthscore',  label: '运营健康',  children: <HealthScoreTab /> },
          { key: 'custinsight',  label: '客户洞察',  children: <CustomerInsightTab /> },
          { key: 'funnel',       label: '获客漏斗',  children: <FunnelAnalyticsTab /> },
          { key: 'menuinsight',  label: '套餐洞察',  children: <MenuInsightTab /> },
          { key: 'revforecast',  label: '营收预测',  children: <RevenueForecastTab /> },
          { key: 'staffexc',     label: '员工绩效',  children: <StaffExceptionTab /> },
          { key: 'satisfaction', label: '满意度',    children: <SatisfactionTab /> },
          { key: 'yoy',          label: '年度对比',  children: <YearOverYearTab /> },
          { key: 'alertcenter',  label: '预警中心',  children: <AlertCenterTab /> },
          { key: 'periodcmp',    label: '期间对比',  children: <PeriodComparisonTab /> },
          { key: 'oprisk',       label: '运营风险',  children: <OperationRiskTab /> },
          { key: 'cancelanal',   label: '取消分析',  children: <CancellationAnalysisTab /> },
          { key: 'leadhealth',   label: '线索健康',  children: <LeadPipelineHealthTab /> },
          { key: 'refundrisk',   label: '退款风险',  children: <RefundRiskTab /> },
          { key: 'targetgap',    label: '目标达成',  children: <MonthlyTargetGapTab /> },
          { key: 'seasonal',     label: '季节规律',  children: <SeasonalPatternTab /> },
          { key: 'custltv',      label: '客户LTV',   children: <CustomerLTVTab /> },
          { key: 'repeatcust',   label: '回头客',    children: <RepeatCustomerTab /> },
          { key: 'leadtime',     label: '提前天数',  children: <BookingLeadTimeTab /> },
          { key: 'tableutil',    label: '桌位利用',  children: <TableUtilizationTab /> },
          { key: 'satref',       label: '满意&转介', children: <SatisfactionReferralTab /> },
          { key: 'qturnaround',  label: '报价周转',  children: <QuoteTurnaroundTab /> },
          { key: 'newrepeat',    label: '新客对比',  children: <NewVsRepeatMonthlyTab /> },
          { key: 'amendment',    label: '订单修改',  children: <OrderAmendmentTab /> },
          { key: 'profitab',     label: '盈利分析',  children: <ProfitabilityTab /> },
          { key: 'crosssell',    label: '交叉销售',  children: <CrossSellTab /> },
          { key: 'vipspend',     label: 'VIP消费',   children: <VipSpendingTab /> },
          { key: 'loyalty',      label: '积分兑换',  children: <LoyaltyRedemptionTab /> },
          { key: 'forecast',     label: '预测准确',  children: <ForecastAccuracyTab /> },
          { key: 'deposit35',    label: '定金退款',  children: <DepositRefundTab /> },
          { key: 'seasonal35',   label: '季节指数',  children: <SeasonalRevenueTab /> },
          { key: 'canceltype',   label: '取消分析',  children: <CancellationReasonsTab /> },
          { key: 'weekdaypat',   label: '星期分布',  children: <WeekdayPatternTab /> },
          { key: 'revtable',    label: '桌均收入',  children: <RevenuePerTableTab /> },
          { key: 'sentiment',   label: '评价情感',  children: <ReviewSentimentTab /> },
          { key: 'upsell38',    label: '加购分析',  children: <UpsellAnalysisTab /> },
          { key: 'revtrend38',  label: '收入趋势',  children: <RevenueTrendTab /> },
          { key: 'profitmargin', label: '利润率',   children: <ProfitMarginTab /> },
          { key: 'typetrendp39', label: '类型趋势', children: <TypeTrendTab /> },
          { key: 'reorderp40',   label: '复购分析', children: <ReorderAnalysisTab /> },
          { key: 'depositp40',   label: '定金分析', children: <DepositAnalysisTab /> },
          { key: 'noshowp41',    label: '爽约分析', children: <NoShowAnalysisTab /> },
          { key: 'pkgpopularp41', label: '套餐热度', children: <PackagePopularityTab /> },
          { key: 'guestrevp42',   label: '人均消费', children: <GuestRevenueTab /> },
          { key: 'vipanalyp42',   label: 'VIP分析',  children: <VipAnalysisTab /> },
          { key: 'pertablep43',   label: '每桌收入', children: <PerTableRevenueTab /> },
          { key: 'ltvp43',        label: '客户价值', children: <CustomerLtvTab /> },
          { key: 'funnelp44',     label: '转化漏斗', children: <LeadFunnelTab /> },
          { key: 'refundp44',     label: '退款分析', children: <RefundAnalysisTab /> },
          { key: 'peakdayp45',    label: '高峰日',   children: <PeakDayTab /> },
          { key: 'warningp45',    label: '风险预警', children: <EarlyWarningTab /> },
          { key: 'advancep46',    label: '提前预订', children: <AdvanceBookingTab /> },
          { key: 'canceltypp46',  label: '类型取消', children: <CancellationTypeTab /> },
          { key: 'monthrevp47',   label: '月度收入', children: <MonthlyRevenueTrendTab /> },
          { key: 'vippremiump47', label: 'VIP溢价',  children: <VipPremiumTab /> },
          { key: 'hvthreshp48',   label: '高价值单', children: <HighValueThresholdTab /> },
          { key: 'referralp48',   label: '转介绍',   children: <ReferralLeadTab /> },
          { key: 'sattrndp49',    label: '满意度',   children: <SatisfactionTrendTab /> },
          { key: 'scoredistp49',  label: '评分分布', children: <ReviewScoreDistTab /> },
          { key: 'wkndvswkdp50',  label: '周末分析', children: <WeekendVsWeekdayTab /> },
          { key: 'quarterlyp50',  label: '季度收入', children: <QuarterlyRevenueTab /> },
          { key: 'typerevp51',    label: '类型占比', children: <TypeRevenueShareTab /> },
          { key: 'leadconvp51',   label: '转化趋势', children: <MonthlyLeadConversionTab /> },
          { key: 'canceltypp52',  label: '取消率',   children: <TypeCancellationRateTab /> },
          { key: 'peakhrp52',     label: '高峰时段', children: <PeakBookingHourTab /> },
          { key: 'clvp53',        label: '客户CLV',  children: <CustomerLifetimeValueTab /> },
          { key: 'datepopup53',   label: '日期热度', children: <BanquetDatePopularityTab /> },
          { key: 'paymentprefp54', label: '支付偏好', children: <PaymentMethodPreferenceTab /> },
          { key: 'seasonp54',      label: '季节分析', children: <BanquetSeasonAnalysisTab /> },
          { key: 'winlossp55',    label: '赢输比率', children: <LeadWinLossRatioTab /> },
          { key: 'newcustp55',    label: '新客增长', children: <MonthlyNewCustomersTab /> },
          { key: 'funnelp56',     label: '转化漏斗', children: <LeadStageFunnelTab /> },
          { key: 'ordervtrndp56', label: '客单价',   children: <OrderValueTrendTab /> },
          { key: 'srcp57',        label: '渠道收入', children: <CustomerSourceRevenueTab /> },
          { key: 'canceltimp57',  label: '取消时机', children: <OrderCancellationTimingTab /> },
          { key: 'complrp58',     label: '完成率',   children: <OrderCompletionRateTab /> },
          { key: 'exctypp58',     label: '异常分布', children: <ExceptionTypeDistributionTab /> },
          { key: 'wkdayp59',      label: '星期分布', children: <BanquetWeekdayDistributionTab /> },
          { key: 'partialp59',    label: '尾款未清', children: <PaymentPartialRateTab /> },
        ]}
      />
    </div>
  );
}

/* ─── Phase 57: 渠道收入 Tab ─── */
function CustomerSourceRevenueTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE}/customer-source-revenue?months=12`
      );
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;
  if (!data || data.total_won === 0) return <ZEmpty text="暂无渠道收入数据" />;

  const maxRev = Math.max(...(data.by_channel || []).map((c: any) => c.revenue_yuan), 1);

  return (
    <div className={styles.p57Wrap}>
      <ZCard>
        <div className={styles.p57KpiRow}>
          <div className={styles.p57Kpi}>
            <span className={styles.p57KpiVal}>{data.total_won}</span>
            <span className={styles.p57KpiLabel}>赢单线索</span>
          </div>
          <div className={styles.p57Kpi}>
            <span className={styles.p57KpiVal}>{data.top_channel || '—'}</span>
            <span className={styles.p57KpiLabel}>最高收入渠道</span>
          </div>
        </div>
        <div className={styles.p57ChannelList}>
          {(data.by_channel || []).map((c: any) => (
            <div key={c.channel} className={styles.p57ChannelRow}>
              <span className={styles.p57ChannelName}>{c.channel}</span>
              <div className={styles.p57Track}>
                <div
                  className={styles.p57Fill}
                  style={{ width: `${Math.round(c.revenue_yuan / maxRev * 100)}%` }}
                />
              </div>
              <span className={styles.p57Rev}>¥{c.revenue_yuan}</span>
              <span className={styles.p57SmCount}>{c.won_leads}单</span>
            </div>
          ))}
        </div>
      </ZCard>
    </div>
  );
}

/* ─── Phase 57: 取消时机 Tab ─── */
function OrderCancellationTimingTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE}/order-cancellation-timing?months=12`
      );
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;
  if (!data || data.total_cancelled === 0) return <ZEmpty text="暂无取消订单数据" />;

  const maxCount = Math.max(...(data.distribution || []).map((d: any) => d.count), 1);

  return (
    <div className={styles.p57Wrap}>
      <ZCard>
        <div className={styles.p57KpiRow}>
          <div className={styles.p57Kpi}>
            <span className={styles.p57KpiVal}>{data.total_cancelled}</span>
            <span className={styles.p57KpiLabel}>取消总单数</span>
          </div>
          <div className={styles.p57Kpi}>
            <span className={styles.p57KpiVal}>
              {data.avg_days_before != null ? `${data.avg_days_before}天` : '—'}
            </span>
            <span className={styles.p57KpiLabel}>平均提前天数</span>
          </div>
        </div>
        <div className={styles.p57BucketList}>
          {(data.distribution || []).map((d: any) => (
            <div key={d.bucket} className={styles.p57BucketRow}>
              <span className={styles.p57BucketName}>{d.bucket}</span>
              <div className={styles.p57Track}>
                <div
                  className={styles.p57CancelFill}
                  style={{ width: `${Math.round(d.count / maxCount * 100)}%` }}
                />
              </div>
              <span className={styles.p57BucketCount}>{d.count}单</span>
              <span className={styles.p57BucketPct}>{d.pct}%</span>
            </div>
          ))}
        </div>
      </ZCard>
    </div>
  );
}

/* ─── Phase 58: 订单完成率 Tab ─── */
function OrderCompletionRateTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE}/order-completion-rate?months=12`
      );
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;
  if (!data || data.total_orders === 0) return <ZEmpty text="暂无订单数据" />;

  const completedPct = data.completion_rate_pct ?? 0;
  const inProgressPct = 100 - completedPct;

  return (
    <div className={styles.p58Wrap}>
      <ZCard>
        <div className={styles.p58KpiRow}>
          <div className={styles.p58Kpi}>
            <span className={styles.p58KpiVal}>{data.total_orders}</span>
            <span className={styles.p58KpiLabel}>总订单数</span>
          </div>
          <div className={styles.p58Kpi}>
            <span className={styles.p58KpiVal}>{data.completed_count}</span>
            <span className={styles.p58KpiLabel}>已完成</span>
          </div>
          <div className={styles.p58Kpi}>
            <span className={styles.p58KpiVal}>{completedPct}%</span>
            <span className={styles.p58KpiLabel}>完成率</span>
          </div>
        </div>
        <div className={styles.p58BarWrap}>
          <div className={styles.p58BarLabel}>
            <span>已完成</span><span>进行中</span>
          </div>
          <div className={styles.p58Track}>
            <div className={styles.p58CompletedFill} style={{ width: `${completedPct}%` }} />
            <div className={styles.p58InProgressFill} style={{ width: `${inProgressPct}%` }} />
          </div>
          <div className={styles.p58BarLabel}>
            <span>{completedPct}%</span><span>{inProgressPct.toFixed(1)}%</span>
          </div>
        </div>
      </ZCard>
    </div>
  );
}

/* ─── Phase 58: 异常类型分布 Tab ─── */
function ExceptionTypeDistributionTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE}/exception-type-distribution?months=6`
      );
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;
  if (!data || data.total_exceptions === 0) return <ZEmpty text="暂无异常事件数据" />;

  const maxCount = Math.max(...(data.by_type || []).map((t: any) => t.count), 1);

  return (
    <div className={styles.p58Wrap}>
      <ZCard>
        <div className={styles.p58KpiRow}>
          <div className={styles.p58Kpi}>
            <span className={styles.p58KpiVal}>{data.total_exceptions}</span>
            <span className={styles.p58KpiLabel}>异常总数</span>
          </div>
          <div className={styles.p58Kpi}>
            <span className={styles.p58KpiVal}>{data.most_common_type || '—'}</span>
            <span className={styles.p58KpiLabel}>最多异常类型</span>
          </div>
        </div>
        <div className={styles.p58TypeList}>
          {(data.by_type || []).map((t: any) => (
            <div key={t.type} className={styles.p58TypeRow}>
              <span className={styles.p58TypeName}>{t.type}</span>
              <div className={styles.p58Track}>
                <div
                  className={styles.p58ExcFill}
                  style={{ width: `${Math.round(t.count / maxCount * 100)}%` }}
                />
              </div>
              <span className={styles.p58TypeCount}>{t.count}次</span>
              <span className={styles.p58TypePct}>{t.pct}%</span>
            </div>
          ))}
        </div>
      </ZCard>
    </div>
  );
}

/* ─── Phase 59: 星期分布 Tab ─── */
function BanquetWeekdayDistributionTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE}/banquet-weekday-distribution?months=12`
      );
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;
  if (!data || data.total_orders === 0) return <ZEmpty text="暂无宴会日期数据" />;

  const maxCount = Math.max(...(data.by_weekday || []).map((d: any) => d.count), 1);

  return (
    <div className={styles.p59Wrap}>
      <ZCard>
        <div className={styles.p59KpiRow}>
          <div className={styles.p59Kpi}>
            <span className={styles.p59KpiVal}>{data.total_orders}</span>
            <span className={styles.p59KpiLabel}>总订单数</span>
          </div>
          <div className={styles.p59Kpi}>
            <span className={styles.p59KpiVal}>{data.peak_weekday || '—'}</span>
            <span className={styles.p59KpiLabel}>最热星期</span>
          </div>
        </div>
        <div className={styles.p59DayList}>
          {(data.by_weekday || []).map((d: any) => (
            <div key={d.weekday} className={styles.p59DayRow}>
              <span className={styles.p59DayName}>{d.weekday}</span>
              <div className={styles.p59Track}>
                <div
                  className={`${styles.p59DayFill} ${d.weekday === data.peak_weekday ? styles.p59Peak : ''}`}
                  style={{ width: `${Math.round(d.count / maxCount * 100)}%` }}
                />
              </div>
              <span className={styles.p59DayCount}>{d.count}</span>
              <span className={styles.p59DayPct}>{d.pct}%</span>
            </div>
          ))}
        </div>
      </ZCard>
    </div>
  );
}

/* ─── Phase 59: 尾款未清 Tab ─── */
function PaymentPartialRateTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE}/payment-partial-rate?months=6`
      );
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;
  if (!data || data.total_orders === 0) return <ZEmpty text="暂无订单数据" />;

  const partialPct  = data.partial_rate_pct ?? 0;
  const clearedPct  = 100 - partialPct;

  return (
    <div className={styles.p59Wrap}>
      <ZCard>
        <div className={styles.p59KpiRow}>
          <div className={styles.p59Kpi}>
            <span className={styles.p59KpiVal}>{data.total_orders}</span>
            <span className={styles.p59KpiLabel}>合计订单</span>
          </div>
          <div className={styles.p59Kpi}>
            <span className={styles.p59KpiVal}>{data.partial_count}</span>
            <span className={styles.p59KpiLabel}>尾款未清</span>
          </div>
          <div className={styles.p59Kpi}>
            <span className={styles.p59KpiVal}>¥{data.outstanding_yuan}</span>
            <span className={styles.p59KpiLabel}>待收金额</span>
          </div>
        </div>
        <div className={styles.p59BarWrap}>
          <div className={styles.p59BarLabel}>
            <span>已结清 {clearedPct.toFixed(1)}%</span>
            <span>未结清 {partialPct}%</span>
          </div>
          <div className={styles.p59BarTrack}>
            <div className={styles.p59ClearedFill}  style={{ width: `${clearedPct}%` }} />
            <div className={styles.p59PartialFill}   style={{ width: `${partialPct}%` }} />
          </div>
        </div>
      </ZCard>
    </div>
  );
}

/* ─── Phase 21: 客户洞察 Tab ─── */
function CustomerInsightTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';

  interface SegmentItem {
    segment: string;
    label: string;
    color: string;
    customer_count: number;
    total_yuan: number;
    avg_yuan: number;
  }
  interface VipItem {
    rank: number;
    customer_id: string;
    name: string;
    phone: string | null;
    banquet_count: number;
    total_yuan: number;
    last_banquet: string | null;
    vip_level: number;
  }
  interface ChurnItem {
    customer_id: string;
    name: string;
    phone: string | null;
    banquet_count: number;
    total_yuan: number;
    last_banquet: string | null;
    months_inactive: number | null;
    risk_level: string;
  }

  const [segments,  setSegments]  = useState<SegmentItem[]>([]);
  const [vips,      setVips]      = useState<VipItem[]>([]);
  const [churns,    setChurns]    = useState<ChurnItem[]>([]);
  const [loading,   setLoading]   = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/customers/segmentation`),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/customers/vip-ranking`, { params: { top_n: 10 } }),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/churn-risk`, { params: { months_inactive: 12, min_banquets: 2, top_n: 10 } }),
    ]).then(([seg, vip, churn]) => {
      if (seg.status === 'fulfilled') setSegments(seg.value.data?.segments ?? []);
      if (vip.status === 'fulfilled') setVips(vip.value.data?.ranking ?? []);
      if (churn.status === 'fulfilled') setChurns(churn.value.data?.items ?? []);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <ZSkeleton rows={6} />;

  return (
    <div className={styles.customerInsightTab}>
      {/* 客户分层 */}
      <ZCard title="客户分层">
        {segments.length === 0 ? (
          <ZEmpty title="暂无客户数据" description="确认客户档案已录入" />
        ) : (
          <div className={styles.segmentGrid}>
            {segments.map(s => (
              <div key={s.segment} className={styles.segmentCard} style={{ borderTop: `3px solid ${s.color}` }}>
                <div className={styles.segmentLabel}>{s.label}</div>
                <div className={styles.segmentCount}>{s.customer_count} 人</div>
                <div className={styles.segmentMeta}>
                  合计 ¥{s.total_yuan.toLocaleString()}
                </div>
                <div className={styles.segmentMeta}>
                  均消 ¥{s.avg_yuan.toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* VIP 排行 */}
      <ZCard title="VIP 客户 Top10">
        {vips.length === 0 ? (
          <ZEmpty title="暂无VIP客户" description="累计消费≥5000元后自动进入VIP" />
        ) : (
          <div className={styles.vipList}>
            {vips.map(v => (
              <div key={v.customer_id} className={styles.vipRow}>
                <span className={styles.vipRank}>#{v.rank}</span>
                <div className={styles.vipInfo}>
                  <div className={styles.vipName}>{v.name}</div>
                  <div className={styles.vipMeta}>
                    {v.banquet_count} 场 · 上次：{v.last_banquet ?? '未知'}
                  </div>
                </div>
                <div className={styles.vipAmt}>¥{v.total_yuan.toLocaleString()}</div>
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* 流失风险 */}
      <ZCard title="流失风险客户">
        {churns.length === 0 ? (
          <ZEmpty title="暂无流失风险" description="所有高频客户均在活跃期" />
        ) : (
          <div className={styles.churnList}>
            {churns.map(c => (
              <div key={c.customer_id} className={styles.churnRow}>
                <div className={styles.churnInfo}>
                  <div className={styles.churnName}>{c.name}</div>
                  <div className={styles.churnMeta}>
                    {c.banquet_count} 场 · 历史 ¥{c.total_yuan.toLocaleString()}
                  </div>
                </div>
                <div className={styles.churnRight}>
                  <ZBadge
                    type={c.risk_level === 'high' ? 'warning' : 'default'}
                    text={`${c.months_inactive ?? '?'} 月未复购`}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 21: 获客漏斗 Tab ─── */
function FunnelAnalyticsTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';

  interface FunnelStage {
    stage: string;
    label: string;
    count: number;
    conversion_rate_pct: number | null;
  }
  interface CapGap {
    date: string;
    weekday: number;
    booked_slots: number;
    capacity: number;
    utilization_pct: number;
    suggested_discount_pct: number;
  }
  interface UpsellOpp {
    order_id: string;
    banquet_date: string;
    contact_name: string | null;
    table_count: number;
    current_yuan: number;
    price_per_table_yuan: number;
    median_price_yuan: number;
    upsell_yuan: number;
  }

  const [stages,   setStages]   = useState<FunnelStage[]>([]);
  const [funnel,   setFunnel]   = useState<{ total_leads: number; overall_win_rate: number } | null>(null);
  const [gaps,     setGaps]     = useState<CapGap[]>([]);
  const [upsells,  setUpsells]  = useState<UpsellOpp[]>([]);
  const [loading,  setLoading]  = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/acquisition-funnel`),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/capacity-gaps`, { params: { days: 30, threshold_pct: 30 } }),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/upsell-opportunities`, { params: { top_n: 10 } }),
    ]).then(([fn, cg, us]) => {
      if (fn.status === 'fulfilled') {
        setStages(fn.value.data?.stages ?? []);
        setFunnel({ total_leads: fn.value.data?.total_leads ?? 0, overall_win_rate: fn.value.data?.overall_win_rate ?? 0 });
      }
      if (cg.status === 'fulfilled') setGaps(cg.value.data?.gaps ?? []);
      if (us.status === 'fulfilled') setUpsells(us.value.data?.opportunities ?? []);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <ZSkeleton rows={6} />;

  const maxStageCount = Math.max(...stages.map(s => s.count), 1);

  return (
    <div className={styles.funnelAnalyticsTab}>
      {/* 获客漏斗 */}
      <ZCard title={`获客漏斗 · 总线索 ${funnel?.total_leads ?? 0} 条 · 成交率 ${funnel?.overall_win_rate ?? 0}%`}>
        {stages.length === 0 ? (
          <ZEmpty title="暂无线索数据" description="录入线索后自动生成漏斗" />
        ) : (
          <div className={styles.funnelStages}>
            {stages.map((s, i) => (
              <div key={s.stage} className={styles.funnelRow}>
                <div className={styles.funnelLabel}>{s.label}</div>
                <div className={styles.funnelBar}>
                  <div
                    className={styles.funnelFill}
                    style={{ width: `${Math.round(s.count / maxStageCount * 100)}%` }}
                  />
                </div>
                <div className={styles.funnelCount}>{s.count}</div>
                {i > 0 && s.conversion_rate_pct != null && (
                  <div className={styles.funnelConv}>{s.conversion_rate_pct}%</div>
                )}
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* 档期空缺 */}
      <ZCard title={`档期空缺（未来30天）· ${gaps.length} 个空缺档期`}>
        {gaps.length === 0 ? (
          <ZEmpty title="近30天档期充足" description="利用率均高于30%" />
        ) : (
          <div className={styles.gapList}>
            {gaps.slice(0, 10).map(g => (
              <div key={g.date} className={styles.gapRow}>
                <div className={styles.gapDate}>{g.date}</div>
                <div className={styles.gapUtil}>{g.utilization_pct}% 利用</div>
                <ZBadge type="info" text={`建议折扣 ${g.suggested_discount_pct}%`} />
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* 追加销售机会 */}
      <ZCard title="追加销售机会 Top10">
        {upsells.length === 0 ? (
          <ZEmpty title="暂无追加销售机会" description="已确认订单套餐价格均高于中位价" />
        ) : (
          <div className={styles.upsellList}>
            {upsells.map(u => (
              <div key={u.order_id} className={styles.upsellRow}>
                <div className={styles.upsellInfo}>
                  <div className={styles.upsellDate}>{u.banquet_date} · {u.contact_name ?? '客户'}</div>
                  <div className={styles.upsellMeta}>
                    {u.table_count} 桌 · 现均 ¥{u.price_per_table_yuan}/桌 → 中位 ¥{u.median_price_yuan}/桌
                  </div>
                </div>
                <div className={styles.upsellAmt}>+¥{u.upsell_yuan.toLocaleString()}</div>
              </div>
            ))}
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 22: 套餐洞察 Tab ─── */
function MenuInsightTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';

  interface PkgPerfItem {
    package_id: string;
    name: string;
    banquet_type: string | null;
    price_yuan: number;
    cost_yuan: number;
    gross_margin_pct: number;
    order_count: number;
    revenue_yuan: number;
  }
  interface PeakMonth { month: number; label: string; count: number; pct: number; }
  interface PeakWeekday { weekday: number; label: string; count: number; pct: number; }
  interface PeakType { type: string; count: number; pct: number; }

  const [pkgs,    setPkgs]    = useState<PkgPerfItem[]>([]);
  const [byMonth, setByMonth] = useState<PeakMonth[]>([]);
  const [byWeek,  setByWeek]  = useState<PeakWeekday[]>([]);
  const [byType,  setByType]  = useState<PeakType[]>([]);
  const [peakInfo, setPeakInfo] = useState<{ peak_month: string; peak_weekday: string } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/menu-performance`),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/peak-analysis`),
    ]).then(([mp, pa]) => {
      if (mp.status === 'fulfilled') setPkgs(mp.value.data?.packages ?? []);
      if (pa.status === 'fulfilled') {
        setByMonth(pa.value.data?.by_month ?? []);
        setByWeek(pa.value.data?.by_weekday ?? []);
        setByType(pa.value.data?.by_type ?? []);
        setPeakInfo({ peak_month: pa.value.data?.peak_month, peak_weekday: pa.value.data?.peak_weekday });
      }
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <ZSkeleton rows={6} />;

  const maxMonth = Math.max(...byMonth.map(m => m.count), 1);
  const maxWeek  = Math.max(...byWeek.map(w => w.count), 1);

  return (
    <div className={styles.menuInsightTab}>
      {/* 套餐销售分析 */}
      <ZCard title="套餐销售分析">
        {pkgs.length === 0 ? (
          <ZEmpty title="暂无套餐数据" description="请先创建宴会套餐" />
        ) : (
          <div className={styles.pkgList}>
            <div className={styles.pkgHeader}>
              <span>套餐名称</span>
              <span>单价</span>
              <span>毛利率</span>
              <span>使用次数</span>
              <span>收入贡献</span>
            </div>
            {pkgs.map(p => (
              <div key={p.package_id} className={styles.pkgRow}>
                <div className={styles.pkgName}>
                  {p.name}
                  {p.banquet_type && <span className={styles.pkgType}>{p.banquet_type}</span>}
                </div>
                <div className={styles.pkgCell}>¥{p.price_yuan.toLocaleString()}</div>
                <div className={styles.pkgCell}>
                  <ZBadge
                    type={p.gross_margin_pct >= 40 ? 'success' : p.gross_margin_pct >= 25 ? 'info' : 'warning'}
                    text={`${p.gross_margin_pct}%`}
                  />
                </div>
                <div className={styles.pkgCell}>{p.order_count} 场</div>
                <div className={styles.pkgCell}>¥{p.revenue_yuan.toLocaleString()}</div>
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* 旺季分析 */}
      {peakInfo && (
        <ZCard title={`旺季分析 · 峰值月份：${peakInfo.peak_month} · 峰值星期：${peakInfo.peak_weekday}`}>
          <div className={styles.peakGrid}>
            <div>
              <div className={styles.peakSubTitle}>月份分布</div>
              <div className={styles.peakBars}>
                {byMonth.map(m => (
                  <div key={m.month} className={styles.peakBarItem}>
                    <div className={styles.peakBar} style={{ height: `${Math.round(m.count / maxMonth * 60)}px` }} />
                    <div className={styles.peakBarLabel}>{m.label.replace('月', '')}</div>
                    <div className={styles.peakBarCount}>{m.count}</div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className={styles.peakSubTitle}>星期分布</div>
              <div className={styles.peakBars}>
                {byWeek.map(w => (
                  <div key={w.weekday} className={styles.peakBarItem}>
                    <div className={styles.peakBar} style={{ height: `${Math.round(w.count / maxWeek * 60)}px`, background: 'var(--accent)' }} />
                    <div className={styles.peakBarLabel}>{w.label.replace('周', '')}</div>
                    <div className={styles.peakBarCount}>{w.count}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          {byType.length > 0 && (
            <div className={styles.typeList}>
              {byType.map(t => (
                <div key={t.type} className={styles.typeRow}>
                  <span className={styles.typeLabel}>{t.type}</span>
                  <div className={styles.typeBarWrap}>
                    <div className={styles.typeBar} style={{ width: `${t.pct}%` }} />
                  </div>
                  <span className={styles.typePct}>{t.pct}%</span>
                </div>
              ))}
            </div>
          )}
        </ZCard>
      )}
    </div>
  );
}

/* ─── Phase 22: 营收预测 Tab ─── */
function RevenueForecastTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';

  interface HistoryItem { month: string; revenue_yuan: number; order_count: number; }
  interface ForecastItem { month: string; forecast_revenue_yuan: number; forecast_orders: number; confidence: string; }
  interface LoyaltyData {
    total_customers: number;
    repeat_customers: number;
    repeat_rate_pct: number;
    avg_ltv_yuan: number;
    monthly_trend: Array<{ month: string; new_orders: number; repeat_orders: number }>;
  }
  interface PaymentData {
    total_orders: number;
    deposit_rate_pct: number;
    full_payment_rate_pct: number;
    collection_rate_pct: number;
    overdue_yuan: number;
    total_receivable_yuan: number;
    total_received_yuan: number;
  }

  const [history,  setHistory]  = useState<HistoryItem[]>([]);
  const [forecast, setForecast] = useState<ForecastItem[]>([]);
  const [loyalty,  setLoyalty]  = useState<LoyaltyData | null>(null);
  const [payment,  setPayment]  = useState<PaymentData | null>(null);
  const [loading,  setLoading]  = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/revenue-forecast`, { params: { months: 3 } }),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/loyalty-metrics`),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/payment-efficiency`),
    ]).then(([rf, lm, pe]) => {
      if (rf.status === 'fulfilled') {
        setHistory(rf.value.data?.history ?? []);
        setForecast(rf.value.data?.forecast ?? []);
      }
      if (lm.status === 'fulfilled') setLoyalty(lm.value.data);
      if (pe.status === 'fulfilled') setPayment(pe.value.data);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <ZSkeleton rows={6} />;

  const maxRevenue = Math.max(...history.map(h => h.revenue_yuan), ...forecast.map(f => f.forecast_revenue_yuan), 1);

  return (
    <div className={styles.revenueForecastTab}>
      {/* 营收趋势 + 预测 */}
      <ZCard title="营收趋势预测（移动平均3个月）">
        {history.length === 0 && forecast.length === 0 ? (
          <ZEmpty title="暂无历史数据" description="营收数据积累后自动生成预测" />
        ) : (
          <div className={styles.forecastChart}>
            {history.map(h => (
              <div key={h.month} className={styles.fcBarItem}>
                <div
                  className={styles.fcBarActual}
                  style={{ height: `${Math.round(h.revenue_yuan / maxRevenue * 80)}px` }}
                  title={`¥${h.revenue_yuan.toLocaleString()}`}
                />
                <div className={styles.fcLabel}>{h.month.slice(5)}</div>
              </div>
            ))}
            {forecast.map(f => (
              <div key={f.month} className={styles.fcBarItem}>
                <div
                  className={styles.fcBarForecast}
                  style={{ height: `${Math.round(f.forecast_revenue_yuan / maxRevenue * 80)}px` }}
                  title={`预测 ¥${f.forecast_revenue_yuan.toLocaleString()}`}
                />
                <div className={styles.fcLabel} style={{ color: '#94a3b8' }}>{f.month.slice(5)}~</div>
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* 忠诚度指标 */}
      {loyalty && (
        <ZCard title="客户忠诚度指标">
          <div className={styles.loyaltyGrid}>
            <div className={styles.loyaltyKpi}>
              <div className={styles.loyaltyValue}>{loyalty.repeat_rate_pct}%</div>
              <div className={styles.loyaltyLabel}>复购率</div>
            </div>
            <div className={styles.loyaltyKpi}>
              <div className={styles.loyaltyValue}>¥{loyalty.avg_ltv_yuan.toLocaleString()}</div>
              <div className={styles.loyaltyLabel}>客均LTV</div>
            </div>
            <div className={styles.loyaltyKpi}>
              <div className={styles.loyaltyValue}>{loyalty.repeat_customers}</div>
              <div className={styles.loyaltyLabel}>复购客户数</div>
            </div>
            <div className={styles.loyaltyKpi}>
              <div className={styles.loyaltyValue}>{loyalty.total_customers}</div>
              <div className={styles.loyaltyLabel}>总客户数</div>
            </div>
          </div>
        </ZCard>
      )}

      {/* 收款效率 */}
      {payment && (
        <ZCard title="收款效率">
          <div className={styles.paymentGrid}>
            <div className={styles.paymentItem}>
              <div className={styles.paymentLabel}>首付率</div>
              <div className={styles.paymentValue}>{payment.deposit_rate_pct}%</div>
            </div>
            <div className={styles.paymentItem}>
              <div className={styles.paymentLabel}>全额付款率</div>
              <div className={styles.paymentValue}>{payment.full_payment_rate_pct}%</div>
            </div>
            <div className={styles.paymentItem}>
              <div className={styles.paymentLabel}>回收率</div>
              <div className={styles.paymentValue}>{payment.collection_rate_pct}%</div>
            </div>
            <div className={styles.paymentItem}>
              <div className={styles.paymentLabel}>逾期应收</div>
              <div className={`${styles.paymentValue} ${payment.overdue_yuan > 0 ? styles.paymentOverdue : ''}`}>
                ¥{payment.overdue_yuan.toLocaleString()}
              </div>
            </div>
          </div>
        </ZCard>
      )}
    </div>
  );
}

/* ─── Phase 23: 员工绩效 & 异常分析 Tab ─── */
function StaffExceptionTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';

  interface StaffItem {
    owner_user_id: string | null;
    role: string;
    total_tasks: number;
    done_tasks: number;
    completion_pct: number;
  }
  interface ExcType { type: string; count: number; pct: number; }
  interface ExcSev  { severity: string; count: number; pct: number; }
  interface HallItem {
    hall_id: string;
    hall_name: string;
    capacity: number;
    booking_count: number;
    order_count: number;
    revenue_yuan: number;
    avg_price_per_table: number;
  }

  const [staff,      setStaff]      = useState<StaffItem[]>([]);
  const [excTypes,   setExcTypes]   = useState<ExcType[]>([]);
  const [excSevs,    setExcSevs]    = useState<ExcSev[]>([]);
  const [excTotal,   setExcTotal]   = useState(0);
  const [excResRate, setExcResRate] = useState(0);
  const [halls,      setHalls]      = useState<HallItem[]>([]);
  const [loading,    setLoading]    = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/staff/performance`, { params: { days: 30 } }),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/exception-summary`, { params: { days: 90 } }),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/hall-revenue-correlation`),
    ]).then(([sp, es, hr]) => {
      if (sp.status === 'fulfilled') setStaff(sp.value.data?.staff ?? []);
      if (es.status === 'fulfilled') {
        setExcTypes(es.value.data?.by_type ?? []);
        setExcSevs(es.value.data?.by_severity ?? []);
        setExcTotal(es.value.data?.total ?? 0);
        setExcResRate(es.value.data?.resolution_rate_pct ?? 0);
      }
      if (hr.status === 'fulfilled') setHalls(hr.value.data?.halls ?? []);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <ZSkeleton rows={6} />;

  const SEV_BADGE: Record<string, 'warning' | 'default' | 'info'> = {
    high: 'warning', medium: 'info', low: 'default',
  };

  return (
    <div className={styles.staffExceptionTab}>
      {/* 员工任务完成率 */}
      <ZCard title="员工任务绩效（近30天）">
        {staff.length === 0 ? (
          <ZEmpty title="暂无任务数据" description="任务分配后自动统计" />
        ) : (
          <div className={styles.staffList}>
            {staff.map((s, i) => (
              <div key={s.owner_user_id ?? s.role + i} className={styles.staffRow}>
                <div className={styles.staffInfo}>
                  <div className={styles.staffRole}>{s.role}</div>
                  <div className={styles.staffMeta}>{s.done_tasks}/{s.total_tasks} 完成</div>
                </div>
                <div className={styles.staffBarWrap}>
                  <div className={styles.staffBar} style={{ width: `${s.completion_pct}%` }} />
                </div>
                <div className={styles.staffPct}>{s.completion_pct}%</div>
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* 异常事件分析 */}
      <ZCard title={`异常事件汇总（近90天）· 共 ${excTotal} 条 · 解决率 ${excResRate}%`}>
        {excTotal === 0 ? (
          <ZEmpty title="近90天无异常记录" description="执行过程顺畅" />
        ) : (
          <div className={styles.excGrid}>
            <div>
              <div className={styles.excSubTitle}>类型分布</div>
              {excTypes.map(t => (
                <div key={t.type} className={styles.excRow}>
                  <span className={styles.excLabel}>{t.type}</span>
                  <span className={styles.excCount}>{t.count}</span>
                  <span className={styles.excPct}>{t.pct}%</span>
                </div>
              ))}
            </div>
            <div>
              <div className={styles.excSubTitle}>严重程度</div>
              {excSevs.map(s => (
                <div key={s.severity} className={styles.excRow}>
                  <ZBadge type={SEV_BADGE[s.severity] ?? 'default'} text={s.severity} />
                  <span className={styles.excCount}>{s.count}</span>
                  <span className={styles.excPct}>{s.pct}%</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      {/* 厅房收入关联 */}
      <ZCard title="厅房收入贡献">
        {halls.length === 0 ? (
          <ZEmpty title="暂无厅房数据" description="确认厅房信息已录入" />
        ) : (
          <div className={styles.hallList}>
            {halls.map(h => (
              <div key={h.hall_id} className={styles.hallRow}>
                <div className={styles.hallInfo}>
                  <div className={styles.hallName}>{h.hall_name}</div>
                  <div className={styles.hallMeta}>容纳 {h.capacity} 桌 · {h.order_count} 场宴会</div>
                </div>
                <div className={styles.hallRight}>
                  <div className={styles.hallRevenue}>¥{h.revenue_yuan.toLocaleString()}</div>
                  <div className={styles.hallPerTable}>均桌价 ¥{h.avg_price_per_table.toLocaleString()}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 23: 满意度 & 定金预测 Tab ─── */
function SatisfactionTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';

  interface TrendItem  { month: string; avg_rating: number; count: number; }
  interface TagItem    { tag: string; count: number; }
  interface ForecastItem { month: string; order_count: number; expected_yuan: number; deposit_yuan: number; }
  interface SizeItem   { label: string; count: number; pct: number; revenue_yuan: number; }

  const [trend,    setTrend]    = useState<TrendItem[]>([]);
  const [avgRating, setAvgRating] = useState<number | null>(null);
  const [ratingDist, setRatingDist] = useState<Record<string, number>>({});
  const [tags,     setTags]     = useState<TagItem[]>([]);
  const [forecast, setForecast] = useState<ForecastItem[]>([]);
  const [totalExpected, setTotalExpected] = useState(0);
  const [sizes,    setSizes]    = useState<SizeItem[]>([]);
  const [loading,  setLoading]  = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/satisfaction-trend`),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/review-tags`),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/deposit-forecast`, { params: { months: 3 } }),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/order-size-distribution`),
    ]).then(([st, rt, df, os]) => {
      if (st.status === 'fulfilled') {
        setTrend(st.value.data?.monthly_trend ?? []);
        setAvgRating(st.value.data?.avg_rating ?? null);
        setRatingDist(st.value.data?.rating_distribution ?? {});
      }
      if (rt.status === 'fulfilled') setTags(rt.value.data?.tags ?? []);
      if (df.status === 'fulfilled') {
        setForecast(df.value.data?.monthly_forecast ?? []);
        setTotalExpected(df.value.data?.total_expected_yuan ?? 0);
      }
      if (os.status === 'fulfilled') setSizes(os.value.data?.buckets ?? []);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <ZSkeleton rows={6} />;

  const maxCount = Math.max(...trend.map(t => t.count), 1);
  const totalReviews = Object.values(ratingDist).reduce((s, c) => s + c, 0);

  return (
    <div className={styles.satisfactionTab}>
      {/* 满意度趋势 */}
      <ZCard title={`满意度趋势${avgRating != null ? ` · 总均分 ${avgRating} ★` : ''}`}>
        {trend.length === 0 ? (
          <ZEmpty title="暂无评价数据" description="宴会结束后请引导客户评分" />
        ) : (
          <>
            <div className={styles.ratingTrend}>
              {trend.map(t => (
                <div key={t.month} className={styles.trendItem}>
                  <div className={styles.trendBar} style={{ height: `${Math.round(t.count / maxCount * 50)}px` }} />
                  <div className={styles.trendScore}>{t.avg_rating}</div>
                  <div className={styles.trendLabel}>{t.month.slice(5)}</div>
                </div>
              ))}
            </div>
            {totalReviews > 0 && (
              <div className={styles.ratingDist}>
                {['5','4','3','2','1'].map(star => {
                  const cnt = ratingDist[star] || 0;
                  return (
                    <div key={star} className={styles.ratingDistRow}>
                      <span className={styles.ratingStar}>{star}★</span>
                      <div className={styles.ratingDistBar}>
                        <div className={styles.ratingDistFill} style={{ width: `${Math.round(cnt / totalReviews * 100)}%` }} />
                      </div>
                      <span className={styles.ratingDistCnt}>{cnt}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </ZCard>

      {/* 差评标签 */}
      <ZCard title="高频差评标签">
        {tags.length === 0 ? (
          <ZEmpty title="暂无差评标签" description="顾客满意度良好" />
        ) : (
          <div className={styles.tagCloud}>
            {tags.slice(0, 12).map(t => (
              <ZBadge key={t.tag} type={t.count >= 3 ? 'warning' : 'default'} text={`${t.tag} ${t.count}`} />
            ))}
          </div>
        )}
      </ZCard>

      {/* 定金预测 */}
      <ZCard title={`未来3月预期收款 · 合计 ¥${totalExpected.toLocaleString()}`}>
        {forecast.length === 0 ? (
          <ZEmpty title="未来3月无已确认订单" description="确认订单后自动预测收款" />
        ) : (
          <div className={styles.forecastList}>
            {forecast.map(f => (
              <div key={f.month} className={styles.forecastRow}>
                <div className={styles.forecastMonth}>{f.month}</div>
                <div className={styles.forecastMeta}>{f.order_count} 场</div>
                <div className={styles.forecastAmt}>¥{f.expected_yuan.toLocaleString()}</div>
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* 订单规模分布 */}
      <ZCard title="订单规模分布">
        {sizes.length === 0 ? (
          <ZEmpty title="暂无订单数据" />
        ) : (
          <div className={styles.sizeList}>
            {sizes.map(s => (
              <div key={s.label} className={styles.sizeRow}>
                <div className={styles.sizeLabel}>{s.label}</div>
                <div className={styles.sizeBarWrap}>
                  <div className={styles.sizeBar} style={{ width: `${s.pct}%` }} />
                </div>
                <div className={styles.sizePct}>{s.pct}%</div>
                <div className={styles.sizeAmt}>¥{s.revenue_yuan.toLocaleString()}</div>
              </div>
            ))}
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 24: 年度对比 Tab ─── */
function YearOverYearTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';

  interface YoyMetric {
    metric: string;
    label: string;
    unit: string;
    this_year: number;
    last_year: number;
    yoy_pct: number | null;
  }
  interface AnnualRow {
    month: string;
    revenue_yuan: number;
    order_count: number;
    lead_count: number;
    gross_profit_yuan: number;
    gross_margin_pct: number;
  }
  interface TypeSeries {
    type: string;
    total: number;
    data: Array<{ month: string; count: number }>;
  }

  const [metrics,   setMetrics]   = useState<YoyMetric[]>([]);
  const [thisYear,  setThisYear]  = useState(0);
  const [lastYear,  setLastYear]  = useState(0);
  const [annualRows, setAnnualRows] = useState<AnnualRow[]>([]);
  const [typeSeries, setTypeSeries] = useState<TypeSeries[]>([]);
  const [loading,   setLoading]   = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/year-over-year`),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/annual-summary`),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/banquet-type-trend`, { params: { months: 12 } }),
    ]).then(([yoy, ann, tt]) => {
      if (yoy.status === 'fulfilled') {
        setMetrics(yoy.value.data?.metrics ?? []);
        setThisYear(yoy.value.data?.this_year ?? new Date().getFullYear());
        setLastYear(yoy.value.data?.last_year ?? new Date().getFullYear() - 1);
      }
      if (ann.status === 'fulfilled') setAnnualRows(ann.value.data?.monthly_rows ?? []);
      if (tt.status === 'fulfilled') setTypeSeries(tt.value.data?.series ?? []);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <ZSkeleton rows={6} />;

  return (
    <div className={styles.yoyTab}>
      {/* 同比对比卡片 */}
      <ZCard title={`年度同比：${thisYear} vs ${lastYear}`}>
        {metrics.length === 0 ? (
          <ZEmpty title="暂无历史KPI数据" description="KPI日报积累后自动生成同比" />
        ) : (
          <div className={styles.yoyGrid}>
            {metrics.map(m => (
              <div key={m.metric} className={styles.yoyCard}>
                <div className={styles.yoyLabel}>{m.label}</div>
                <div className={styles.yoyThis}>{m.this_year.toLocaleString()} {m.unit}</div>
                <div className={styles.yoyLast}>去年：{m.last_year.toLocaleString()}</div>
                {m.yoy_pct != null && (
                  <div className={`${styles.yoyDelta} ${m.yoy_pct >= 0 ? styles.yoyUp : styles.yoyDown}`}>
                    {m.yoy_pct >= 0 ? '▲' : '▼'} {Math.abs(m.yoy_pct)}%
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* 月度汇总表 */}
      <ZCard title={`${thisYear} 年月度汇总`}>
        {annualRows.length === 0 ? (
          <ZEmpty title="暂无月度数据" />
        ) : (
          <div className={styles.annualTable}>
            <div className={styles.annualHeader}>
              <span>月份</span><span>营业额</span><span>场次</span><span>毛利</span><span>毛利率</span>
            </div>
            {annualRows.map(r => (
              <div key={r.month} className={styles.annualRow}>
                <span>{r.month.slice(5)}</span>
                <span>¥{r.revenue_yuan.toLocaleString()}</span>
                <span>{r.order_count} 场</span>
                <span>¥{r.gross_profit_yuan.toLocaleString()}</span>
                <span>{r.gross_margin_pct}%</span>
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* 宴会类型趋势 */}
      <ZCard title="宴会类型构成趋势">
        {typeSeries.length === 0 ? (
          <ZEmpty title="暂无类型数据" />
        ) : (
          <div className={styles.typeSeriesList}>
            {typeSeries.map(s => (
              <div key={s.type} className={styles.typeSeriesRow}>
                <div className={styles.typeSeriesLabel}>{s.type}</div>
                <div className={styles.typeSeriesBar}>
                  <div className={styles.typeSeriesFill} style={{ width: `${Math.min(s.total * 5, 100)}%` }} />
                </div>
                <div className={styles.typeSeriesTotal}>{s.total} 场</div>
              </div>
            ))}
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 24: 预警中心 Tab ─── */
function AlertCenterTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';

  interface AlertItem {
    alert_id: string;
    type: string;
    severity: string;
    title: string;
    detail: string;
    created_at: string;
  }
  interface PriceItem { label: string; count: number; pct: number; }
  interface FreqItem  { label: string; customer_count: number; pct: number; revenue_yuan: number; }
  interface SourceItem { channel: string; lead_count: number; pct: number; won_count: number; win_rate_pct: number; avg_budget_yuan: number | null; }

  const [alerts,  setAlerts]  = useState<AlertItem[]>([]);
  const [prices,  setPrices]  = useState<PriceItem[]>([]);
  const [freqs,   setFreqs]   = useState<FreqItem[]>([]);
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/alerts/active`),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/pricing-ladder`),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/customer-frequency`),
      apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/lead-source-analysis`),
    ]).then(([al, pl, cf, ls]) => {
      if (al.status === 'fulfilled') setAlerts(al.value.data?.alerts ?? []);
      if (pl.status === 'fulfilled') setPrices(pl.value.data?.buckets ?? []);
      if (cf.status === 'fulfilled') setFreqs(cf.value.data?.buckets ?? []);
      if (ls.status === 'fulfilled') setSources(ls.value.data?.sources ?? []);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <ZSkeleton rows={6} />;

  const SEV_BADGE: Record<string, 'warning' | 'default' | 'info'> = {
    high: 'warning', medium: 'info', low: 'default',
  };
  const TYPE_LABEL: Record<string, string> = {
    exception: '异常未处理', overdue_task: '任务逾期', stale_lead: '线索停滞',
  };

  return (
    <div className={styles.alertCenterTab}>
      {/* 活跃预警 */}
      <ZCard title={`活跃预警${alerts.length > 0 ? ` · ${alerts.length} 条` : ''}`}>
        {alerts.length === 0 ? (
          <ZEmpty title="当前无活跃预警" description="运营状态良好" />
        ) : (
          <div className={styles.alertList}>
            {alerts.map(a => (
              <div key={a.alert_id} className={`${styles.alertRow} ${styles['alertSev_' + a.severity]}`}>
                <div className={styles.alertLeft}>
                  <ZBadge type={SEV_BADGE[a.severity] ?? 'default'} text={TYPE_LABEL[a.type] ?? a.type} />
                  <div className={styles.alertTitle}>{a.title}</div>
                  <div className={styles.alertDetail}>{a.detail}</div>
                </div>
                <div className={styles.alertTime}>{a.created_at}</div>
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* 定价阶梯 */}
      <ZCard title="成交桌单价分布">
        {prices.length === 0 ? (
          <ZEmpty title="暂无订单数据" />
        ) : (
          <div className={styles.priceList}>
            {prices.map(p => (
              <div key={p.label} className={styles.priceRow}>
                <div className={styles.priceLabel}>{p.label}</div>
                <div className={styles.priceBarWrap}>
                  <div className={styles.priceBarFill} style={{ width: `${p.pct}%` }} />
                </div>
                <div className={styles.pricePct}>{p.pct}%</div>
                <div className={styles.priceCnt}>{p.count}</div>
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* 消费频次 */}
      <ZCard title="客户消费频次分布">
        {freqs.length === 0 ? (
          <ZEmpty title="暂无客户数据" />
        ) : (
          <div className={styles.freqList}>
            {freqs.map(f => (
              <div key={f.label} className={styles.freqRow}>
                <div className={styles.freqLabel}>{f.label}</div>
                <div className={styles.freqBarWrap}>
                  <div className={styles.freqBar} style={{ width: `${f.pct}%` }} />
                </div>
                <div className={styles.freqPct}>{f.pct}%</div>
                <div className={styles.freqAmt}>¥{f.revenue_yuan.toLocaleString()}</div>
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* 线索来源 */}
      <ZCard title="线索渠道分析">
        {sources.length === 0 ? (
          <ZEmpty title="暂无线索来源数据" />
        ) : (
          <div className={styles.sourceList}>
            <div className={styles.sourceHeader}>
              <span>渠道</span><span>线索数</span><span>成交率</span><span>均预算</span>
            </div>
            {sources.map(s => (
              <div key={s.channel} className={styles.sourceRow}>
                <div className={styles.sourceChannel}>{s.channel}</div>
                <div className={styles.sourceCell}>{s.lead_count} <span className={styles.sourcePct}>({s.pct}%)</span></div>
                <div className={styles.sourceCell}>
                  <ZBadge type={s.win_rate_pct >= 30 ? 'success' : s.win_rate_pct >= 15 ? 'info' : 'default'}
                    text={`${s.win_rate_pct}%`} />
                </div>
                <div className={styles.sourceCell}>
                  {s.avg_budget_yuan != null ? `¥${s.avg_budget_yuan.toLocaleString()}` : '-'}
                </div>
              </div>
            ))}
          </div>
        )}
      </ZCard>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────────────────
// Phase 25 Tab 1 — PeriodComparisonTab「期间对比」
// ─────────────────────────────────────────────────────────────────────────────

interface PeriodMetric {
  metric: string;
  label: string;
  period_a: number | null;
  period_b: number | null;
  delta_pct: number | null;
}
interface PeriodComparisonData {
  period_a: { start: string; end: string };
  period_b: { start: string; end: string };
  metrics: PeriodMetric[];
}
interface TopSpender {
  customer_id: string;
  name: string;
  phone: string;
  order_count: number;
  total_yuan: number;
  avg_yuan: number;
  vip_level: number;
}

function PeriodComparisonTab() {
  const { storeId } = useStore();
  const today = new Date();
  const fmt = (d: Date) => d.toISOString().slice(0, 10);
  const offset = (d: Date, days: number) => { const n = new Date(d); n.setDate(n.getDate() + days); return n; };

  const [paStart, setPaStart] = React.useState(fmt(offset(today, -60)));
  const [paEnd,   setPaEnd]   = React.useState(fmt(offset(today, -31)));
  const [pbStart, setPbStart] = React.useState(fmt(offset(today, -120)));
  const [pbEnd,   setPbEnd]   = React.useState(fmt(offset(today, -91)));

  const [cmp,       setCmp]       = React.useState<PeriodComparisonData | null>(null);
  const [spenders,  setSpenders]  = React.useState<TopSpender[]>([]);
  const [loading,   setLoading]   = React.useState(false);

  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const [r1, r2] = await Promise.allSettled([
        apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/period-comparison?period_a_start=${paStart}&period_a_end=${paEnd}&period_b_start=${pbStart}&period_b_end=${pbEnd}`),
        apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/top-spenders?months=12&top_n=10`),
      ]);
      if (r1.status === 'fulfilled') setCmp(r1.value.data);
      if (r2.status === 'fulfilled') setSpenders(r2.value.data.ranking ?? []);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId, paStart, paEnd, pbStart, pbEnd]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={6} />;

  return (
    <div className={styles.periodCmpTab}>
      {/* Date range selectors */}
      <ZCard title="期间对比">
        <div className={styles.periodInputRow}>
          <span className={styles.periodLabel}>期间A</span>
          <input type="date" value={paStart} onChange={e => setPaStart(e.target.value)} className={styles.dateInput} />
          <span>~</span>
          <input type="date" value={paEnd}   onChange={e => setPaEnd(e.target.value)}   className={styles.dateInput} />
          <span className={styles.periodLabel}>期间B</span>
          <input type="date" value={pbStart} onChange={e => setPbStart(e.target.value)} className={styles.dateInput} />
          <span>~</span>
          <input type="date" value={pbEnd}   onChange={e => setPbEnd(e.target.value)}   className={styles.dateInput} />
          <ZButton size="sm" onClick={load}>对比</ZButton>
        </div>
        {cmp == null ? (
          <ZEmpty title="暂无数据" />
        ) : (
          <div className={styles.cmpTable}>
            <div className={styles.cmpHeader}>
              <span>指标</span>
              <span>期间A</span>
              <span>期间B</span>
              <span>变化</span>
            </div>
            {cmp.metrics.map(m => (
              <div key={m.metric} className={styles.cmpRow}>
                <div className={styles.cmpLabel}>{m.label}</div>
                <div className={styles.cmpVal}>{m.period_a != null ? m.period_a.toLocaleString() : '—'}</div>
                <div className={styles.cmpVal}>{m.period_b != null ? m.period_b.toLocaleString() : '—'}</div>
                <div className={`${styles.cmpDelta} ${m.delta_pct == null ? '' : m.delta_pct >= 0 ? styles.cmpUp : styles.cmpDown}`}>
                  {m.delta_pct == null ? '—' : `${m.delta_pct >= 0 ? '▲' : '▼'} ${Math.abs(m.delta_pct)}%`}
                </div>
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* Top spenders */}
      <ZCard title="高价值客户 Top 10（近12个月）">
        {spenders.length === 0 ? <ZEmpty title="暂无数据" /> : (
          <div className={styles.spenderList}>
            <div className={styles.spenderHeader}>
              <span>排名</span><span>客户</span><span>订单数</span><span>总消费</span><span>客单价</span>
            </div>
            {spenders.map((s, i) => (
              <div key={s.customer_id} className={styles.spenderRow}>
                <div className={styles.spenderRank}>{i + 1}</div>
                <div className={styles.spenderName}>{s.name || '—'}</div>
                <div className={styles.spenderCell}>{s.order_count} 单</div>
                <div className={styles.spenderCell}>¥{s.total_yuan.toLocaleString()}</div>
                <div className={styles.spenderCell}>¥{s.avg_yuan.toLocaleString()}</div>
              </div>
            ))}
          </div>
        )}
      </ZCard>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────────────────
// Phase 25 Tab 2 — OperationRiskTab「运营风险」
// ─────────────────────────────────────────────────────────────────────────────

interface DepositRiskItem {
  order_id: string;
  banquet_date: string;
  days_until_event: number;
  total_yuan: number;
  deposit_yuan: number;
  deposit_ratio_pct: number;
  contact_name: string;
}
interface TaskTrendPoint {
  week: string;
  total: number;
  completed: number;
  completion_rate_pct: number;
}

function OperationRiskTab() {
  const { storeId } = useStore();
  const [riskItems,  setRiskItems]  = React.useState<DepositRiskItem[]>([]);
  const [taskSeries, setTaskSeries] = React.useState<TaskTrendPoint[]>([]);
  const [avgRate,    setAvgRate]    = React.useState<number>(0);
  const [totalExp,   setTotalExp]   = React.useState<number>(0);
  const [loading,    setLoading]    = React.useState(false);

  useEffect(() => {
    if (!storeId) return;
    setLoading(true);
    Promise.allSettled([
      apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/deposit-risk?min_risk_pct=30`),
      apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/task-completion-trend?weeks=8`),
    ]).then(([r1, r2]) => {
      if (r1.status === 'fulfilled') {
        setRiskItems(r1.value.data.items ?? []);
        setTotalExp(r1.value.data.total_exposed_yuan ?? 0);
      }
      if (r2.status === 'fulfilled') {
        setTaskSeries(r2.value.data.series ?? []);
        setAvgRate(r2.value.data.avg_completion_rate_pct ?? 0);
      }
    }).catch(handleApiError).finally(() => setLoading(false));
  }, [storeId]);

  if (loading) return <ZSkeleton rows={6} />;

  return (
    <div className={styles.opRiskTab}>
      {/* Deposit Risk */}
      <ZCard title={`定金风险预警（风险敞口 ¥${totalExp.toLocaleString()}）`}>
        {riskItems.length === 0 ? (
          <ZEmpty title="暂无定金风险订单" />
        ) : (
          <div className={styles.riskList}>
            <div className={styles.riskHeader}>
              <span>宴会日期</span><span>距今</span><span>联系人</span>
              <span>总金额</span><span>已付定金</span><span>定金比例</span>
            </div>
            {riskItems.map(r => (
              <div key={r.order_id} className={`${styles.riskRow} ${r.deposit_ratio_pct < 10 ? styles.riskHigh : styles.riskMed}`}>
                <div>{r.banquet_date}</div>
                <div>{r.days_until_event}天</div>
                <div>{r.contact_name || '—'}</div>
                <div>¥{r.total_yuan.toLocaleString()}</div>
                <div>¥{r.deposit_yuan.toLocaleString()}</div>
                <div className={styles.riskRatio}>{r.deposit_ratio_pct}%</div>
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* Task Completion Trend */}
      <ZCard title={`任务完成趋势（8周均完成率 ${avgRate}%）`}>
        {taskSeries.length === 0 ? (
          <ZEmpty title="暂无任务数据" />
        ) : (
          <div className={styles.taskTrendList}>
            <div className={styles.taskTrendHeader}>
              <span>周次</span><span>总任务</span><span>已完成</span><span>完成率</span>
            </div>
            {taskSeries.map(w => (
              <div key={w.week} className={styles.taskTrendRow}>
                <div className={styles.taskWeek}>{w.week}</div>
                <div className={styles.taskCell}>{w.total}</div>
                <div className={styles.taskCell}>{w.completed}</div>
                <div className={styles.taskBarWrap}>
                  <div className={styles.taskBar}
                    style={{ width: `${Math.min(w.completion_rate_pct, 100)}%`,
                             background: w.completion_rate_pct >= 80 ? 'var(--green)' : w.completion_rate_pct >= 50 ? 'var(--yellow)' : 'var(--red)' }} />
                  <span className={styles.taskBarLabel}>{w.completion_rate_pct}%</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </ZCard>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────────────────
// Phase 26 Tab 1 — CancellationAnalysisTab「取消分析」
// ─────────────────────────────────────────────────────────────────────────────

interface CancelTypeRow { banquet_type: string; count: number; pct: number; }
interface CancelMonthRow { month: string; count: number; lost_yuan: number; }
interface CancellationData {
  total_cancelled: number;
  cancel_rate_pct: number | null;
  total_lost_yuan: number;
  by_type: CancelTypeRow[];
  by_month: CancelMonthRow[];
}

interface RevenuePerTableTypeRow { banquet_type: string; order_count: number; avg_per_table_yuan: number | null; }
interface RevenuePerTableMonthRow { month: string; avg_per_table_yuan: number | null; }
interface RevenuePerTableData {
  overall_avg_yuan: number | null;
  by_type: RevenuePerTableTypeRow[];
  by_month: RevenuePerTableMonthRow[];
}

function CancellationAnalysisTab() {
  const { storeId } = useStore();
  const [cancel, setCancel]   = React.useState<CancellationData | null>(null);
  const [rpt,    setRpt]      = React.useState<RevenuePerTableData | null>(null);
  const [loading, setLoading] = React.useState(false);

  useEffect(() => {
    if (!storeId) return;
    setLoading(true);
    Promise.allSettled([
      apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/cancellation-analysis?months=12`),
      apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/revenue-per-table?months=6`),
    ]).then(([r1, r2]) => {
      if (r1.status === 'fulfilled') setCancel(r1.value.data);
      if (r2.status === 'fulfilled') setRpt(r2.value.data);
    }).catch(handleApiError).finally(() => setLoading(false));
  }, [storeId]);

  if (loading) return <ZSkeleton rows={6} />;

  const TYPE_LABEL: Record<string, string> = {
    wedding: '婚宴', birthday: '寿宴', corporate: '商务', anniversary: '周年',
    other: '其他',
  };

  return (
    <div className={styles.cancelTab}>
      {/* Cancellation summary */}
      <ZCard title="取消订单分析（近12个月）">
        {!cancel || cancel.total_cancelled === 0 ? (
          <ZEmpty title="近12个月无取消订单" />
        ) : (
          <>
            <div className={styles.cancelKpiRow}>
              <div className={styles.cancelKpi}>
                <div className={styles.cancelKpiVal}>{cancel.total_cancelled}</div>
                <div className={styles.cancelKpiLabel}>取消订单数</div>
              </div>
              <div className={styles.cancelKpi}>
                <div className={`${styles.cancelKpiVal} ${styles.cancelRed}`}>
                  {cancel.cancel_rate_pct != null ? `${cancel.cancel_rate_pct}%` : '—'}
                </div>
                <div className={styles.cancelKpiLabel}>取消率</div>
              </div>
              <div className={styles.cancelKpi}>
                <div className={`${styles.cancelKpiVal} ${styles.cancelRed}`}>
                  ¥{cancel.total_lost_yuan.toLocaleString()}
                </div>
                <div className={styles.cancelKpiLabel}>损失金额</div>
              </div>
            </div>
            <div className={styles.cancelTypeRow}>
              {cancel.by_type.map(t => (
                <div key={t.banquet_type} className={styles.cancelTypeChip}>
                  <span>{TYPE_LABEL[t.banquet_type] ?? t.banquet_type}</span>
                  <strong>{t.count}次</strong>
                  <span className={styles.cancelTypePct}>{t.pct}%</span>
                </div>
              ))}
            </div>
            <div className={styles.cancelMonthList}>
              {cancel.by_month.map(m => (
                <div key={m.month} className={styles.cancelMonthRow}>
                  <span className={styles.cancelMonth}>{m.month}</span>
                  <span>{m.count}单</span>
                  <span className={styles.cancelLost}>损失 ¥{m.lost_yuan.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </ZCard>

      {/* Revenue per table */}
      <ZCard title={`桌均收入分析${rpt?.overall_avg_yuan != null ? `（均值 ¥${rpt.overall_avg_yuan.toLocaleString()}/桌）` : ''}`}>
        {!rpt || rpt.by_type.length === 0 ? (
          <ZEmpty title="暂无数据" />
        ) : (
          <>
            <div className={styles.rptTypeList}>
              <div className={styles.rptTypeHeader}>
                <span>类型</span><span>订单数</span><span>桌均价</span>
              </div>
              {rpt.by_type.map(t => (
                <div key={t.banquet_type} className={styles.rptTypeRow}>
                  <div>{TYPE_LABEL[t.banquet_type] ?? t.banquet_type}</div>
                  <div>{t.order_count}</div>
                  <div className={styles.rptAvg}>
                    {t.avg_per_table_yuan != null ? `¥${t.avg_per_table_yuan.toLocaleString()}` : '—'}
                  </div>
                </div>
              ))}
            </div>
            <div className={styles.rptMonthBars}>
              {rpt.by_month.map(m => {
                const maxVal = Math.max(...rpt.by_month.map(x => x.avg_per_table_yuan ?? 0));
                const pct = maxVal > 0 && m.avg_per_table_yuan != null
                  ? Math.round(m.avg_per_table_yuan / maxVal * 100)
                  : 0;
                return (
                  <div key={m.month} className={styles.rptMonthBar}>
                    <div className={styles.rptMonthLabel}>{m.month.slice(5)}</div>
                    <div className={styles.rptBarTrack}>
                      <div className={styles.rptBarFill} style={{ width: `${pct}%` }} />
                    </div>
                    <div className={styles.rptMonthVal}>
                      {m.avg_per_table_yuan != null ? `¥${m.avg_per_table_yuan}` : '—'}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </ZCard>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────────────────
// Phase 26 Tab 2 — LeadPipelineHealthTab「线索健康」
// ─────────────────────────────────────────────────────────────────────────────

interface LeadAgingBucket { label: string; count: number; pct: number; }
interface StaleLeadItem { lead_id: string; days_idle: number; stage: string; contact_name: string; }
interface WaitlistData {
  total_leads: number;
  waitlisted_count: number;
  converted_count: number;
  conversion_rate_pct: number | null;
  avg_wait_days: number | null;
}

function LeadPipelineHealthTab() {
  const { storeId } = useStore();
  const [agingBuckets, setAgingBuckets] = React.useState<LeadAgingBucket[]>([]);
  const [staleLeads,   setStaleLeads]   = React.useState<StaleLeadItem[]>([]);
  const [waitlist,     setWaitlist]     = React.useState<WaitlistData | null>(null);
  const [loading,      setLoading]      = React.useState(false);

  useEffect(() => {
    if (!storeId) return;
    setLoading(true);
    Promise.allSettled([
      apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/lead-aging`),
      apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/waitlist-conversion?months=6`),
    ]).then(([r1, r2]) => {
      if (r1.status === 'fulfilled') {
        setAgingBuckets(r1.value.data.buckets ?? []);
        setStaleLeads(r1.value.data.stale_leads ?? []);
      }
      if (r2.status === 'fulfilled') setWaitlist(r2.value.data);
    }).catch(handleApiError).finally(() => setLoading(false));
  }, [storeId]);

  if (loading) return <ZSkeleton rows={6} />;

  const STAGE_LABEL: Record<string, string> = {
    new: '新线索', contacted: '已联系', visit_scheduled: '预约看厅',
    quoted: '已报价', waiting_decision: '等待决策', deposit_pending: '待付定金',
  };

  return (
    <div className={styles.leadHealthTab}>
      {/* Lead aging buckets */}
      <ZCard title="线索停滞分析">
        {agingBuckets.length === 0 ? (
          <ZEmpty title="暂无活跃线索" />
        ) : (
          <div className={styles.agingBuckets}>
            {agingBuckets.map(b => (
              <div key={b.label} className={styles.agingBucket}>
                <div className={styles.agingLabel}>{b.label}</div>
                <div className={styles.agingBarTrack}>
                  <div className={styles.agingBarFill}
                    style={{ width: `${b.pct}%`,
                             background: b.label.includes('60') ? 'var(--red)' :
                                         b.label.includes('31') ? 'var(--yellow)' : 'var(--accent)' }} />
                </div>
                <div className={styles.agingCount}>{b.count} 条</div>
                <div className={styles.agingPct}>{b.pct}%</div>
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* Stale leads */}
      {staleLeads.length > 0 && (
        <ZCard title={`超期未跟进线索（${staleLeads.length} 条）`}>
          <div className={styles.staleList}>
            <div className={styles.staleHeader}>
              <span>联系人</span><span>当前阶段</span><span>停滞天数</span>
            </div>
            {staleLeads.map(l => (
              <div key={l.lead_id} className={styles.staleRow}>
                <div>{l.contact_name || '—'}</div>
                <div>{STAGE_LABEL[l.stage] ?? l.stage}</div>
                <div className={`${styles.staleDays} ${l.days_idle > 60 ? styles.staleDanger : styles.staleWarn}`}>
                  {l.days_idle}天
                </div>
              </div>
            ))}
          </div>
        </ZCard>
      )}

      {/* Waitlist conversion */}
      <ZCard title="候补转化（等待决策→签约）">
        {!waitlist || waitlist.waitlisted_count === 0 ? (
          <ZEmpty title="暂无候补数据" />
        ) : (
          <div className={styles.waitlistGrid}>
            <div className={styles.waitlistKpi}>
              <div className={styles.waitlistVal}>{waitlist.waitlisted_count}</div>
              <div className={styles.waitlistLabel}>候补线索</div>
            </div>
            <div className={styles.waitlistKpi}>
              <div className={styles.waitlistVal}>{waitlist.converted_count}</div>
              <div className={styles.waitlistLabel}>已转化</div>
            </div>
            <div className={styles.waitlistKpi}>
              <div className={`${styles.waitlistVal} ${styles.waitlistAccent}`}>
                {waitlist.conversion_rate_pct != null ? `${waitlist.conversion_rate_pct}%` : '—'}
              </div>
              <div className={styles.waitlistLabel}>转化率</div>
            </div>
            <div className={styles.waitlistKpi}>
              <div className={styles.waitlistVal}>
                {waitlist.avg_wait_days != null ? `${waitlist.avg_wait_days}天` : '—'}
              </div>
              <div className={styles.waitlistLabel}>平均等待</div>
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────────────────
// Phase 27 Tab 1 — RefundRiskTab「退款风险」
// ─────────────────────────────────────────────────────────────────────────────

interface RefundData {
  refund_orders: number;
  total_orders: number;
  refund_rate_pct: number | null;
  total_refund_yuan: number;
  avg_refund_yuan: number | null;
  by_type: { banquet_type: string; count: number; pct: number }[];
}
interface BundlePkg {
  package_id: string;
  package_name: string;
  order_count: number;
  total_revenue_yuan: number;
  avg_per_table_yuan: number | null;
  gross_margin_pct: number | null;
}

function RefundRiskTab() {
  const { storeId } = useStore();
  const [refund,   setRefund]  = React.useState<RefundData | null>(null);
  const [bundles,  setBundles] = React.useState<BundlePkg[]>([]);
  const [loading,  setLoading] = React.useState(false);

  useEffect(() => {
    if (!storeId) return;
    setLoading(true);
    Promise.allSettled([
      apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/refund-rate?months=6`),
      apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/bundle-performance?months=6`),
    ]).then(([r1, r2]) => {
      if (r1.status === 'fulfilled') setRefund(r1.value.data);
      if (r2.status === 'fulfilled') setBundles(r2.value.data.packages ?? []);
    }).catch(handleApiError).finally(() => setLoading(false));
  }, [storeId]);

  if (loading) return <ZSkeleton rows={6} />;

  const TYPE_LABEL: Record<string, string> = {
    wedding: '婚宴', birthday: '寿宴', corporate: '商务', anniversary: '周年', other: '其他',
  };

  return (
    <div className={styles.refundTab}>
      {/* Refund summary */}
      <ZCard title="退款风险分析（近6个月）">
        {!refund || refund.refund_orders === 0 ? (
          <ZEmpty title="近6个月无退款记录" />
        ) : (
          <>
            <div className={styles.refundKpiRow}>
              <div className={styles.refundKpi}>
                <div className={`${styles.refundKpiVal} ${styles.refundRed}`}>{refund.refund_orders}</div>
                <div className={styles.refundKpiLabel}>退款订单</div>
              </div>
              <div className={styles.refundKpi}>
                <div className={`${styles.refundKpiVal} ${styles.refundRed}`}>
                  {refund.refund_rate_pct != null ? `${refund.refund_rate_pct}%` : '—'}
                </div>
                <div className={styles.refundKpiLabel}>退款率</div>
              </div>
              <div className={styles.refundKpi}>
                <div className={styles.refundKpiVal}>¥{refund.total_refund_yuan.toLocaleString()}</div>
                <div className={styles.refundKpiLabel}>总退款额</div>
              </div>
              <div className={styles.refundKpi}>
                <div className={styles.refundKpiVal}>
                  {refund.avg_refund_yuan != null ? `¥${refund.avg_refund_yuan.toLocaleString()}` : '—'}
                </div>
                <div className={styles.refundKpiLabel}>均退款额</div>
              </div>
            </div>
            <div className={styles.refundTypeRow}>
              {refund.by_type.map(t => (
                <div key={t.banquet_type} className={styles.refundTypeChip}>
                  <span>{TYPE_LABEL[t.banquet_type] ?? t.banquet_type}</span>
                  <strong>{t.count}次</strong>
                  <span className={styles.refundTypePct}>{t.pct}%</span>
                </div>
              ))}
            </div>
          </>
        )}
      </ZCard>

      {/* Bundle performance */}
      <ZCard title="套餐销售效果（近6个月）">
        {bundles.length === 0 ? <ZEmpty title="暂无套餐数据" /> : (
          <div className={styles.bundleList}>
            <div className={styles.bundleHeader}>
              <span>套餐名称</span><span>订单数</span><span>总收入</span>
              <span>桌均价</span><span>毛利率</span>
            </div>
            {bundles.map(p => (
              <div key={p.package_id} className={styles.bundleRow}>
                <div className={styles.bundleName}>{p.package_name}</div>
                <div>{p.order_count}</div>
                <div>¥{p.total_revenue_yuan.toLocaleString()}</div>
                <div>{p.avg_per_table_yuan != null ? `¥${p.avg_per_table_yuan}` : '—'}</div>
                <div>
                  {p.gross_margin_pct != null ? (
                    <ZBadge type={p.gross_margin_pct >= 40 ? 'success' : p.gross_margin_pct >= 25 ? 'info' : 'default'}
                      text={`${p.gross_margin_pct}%`} />
                  ) : '—'}
                </div>
              </div>
            ))}
          </div>
        )}
      </ZCard>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────────────────
// Phase 27 Tab 2 — MonthlyTargetGapTab「目标达成」
// ─────────────────────────────────────────────────────────────────────────────

interface TargetRow {
  month: number;
  actual_yuan: number;
  target_yuan: number;
  gap_yuan: number | null;
  achievement_pct: number | null;
}
interface SentimentSummary { positive: number; neutral: number; negative: number; }
interface SentimentTrendPoint {
  month: string;
  positive: number;
  neutral: number;
  negative: number;
  avg_ai_score: number | null;
}

const MONTH_NAMES = ['','1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];

function MonthlyTargetGapTab() {
  const { storeId } = useStore();
  const [rows,       setRows]      = React.useState<TargetRow[]>([]);
  const [ytd,        setYtd]       = React.useState<number | null>(null);
  const [sentiment,  setSentiment] = React.useState<SentimentSummary | null>(null);
  const [sentTrend,  setSentTrend] = React.useState<SentimentTrendPoint[]>([]);
  const [loading,    setLoading]   = React.useState(false);

  useEffect(() => {
    if (!storeId) return;
    setLoading(true);
    Promise.allSettled([
      apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/monthly-target-gap?year=0`),
      apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/review-sentiment-trend?months=6`),
    ]).then(([r1, r2]) => {
      if (r1.status === 'fulfilled') {
        setRows(r1.value.data.monthly_rows ?? []);
        setYtd(r1.value.data.ytd_achievement_pct ?? null);
      }
      if (r2.status === 'fulfilled') {
        setSentiment(r2.value.data.sentiment_summary ?? null);
        setSentTrend(r2.value.data.monthly_trend ?? []);
      }
    }).catch(handleApiError).finally(() => setLoading(false));
  }, [storeId]);

  if (loading) return <ZSkeleton rows={6} />;

  return (
    <div className={styles.targetGapTab}>
      {/* Monthly target vs actual */}
      <ZCard title={`月度目标达成${ytd != null ? `（YTD ${ytd}%）` : ''}`}>
        {rows.length === 0 ? <ZEmpty title="暂无目标数据" /> : (
          <div className={styles.targetTable}>
            <div className={styles.targetHeader}>
              <span>月份</span><span>实际</span><span>目标</span>
              <span>缺口</span><span>达成率</span>
            </div>
            {rows.map(r => (
              <div key={r.month} className={styles.targetRow}>
                <div className={styles.targetMonth}>{MONTH_NAMES[r.month]}</div>
                <div>¥{r.actual_yuan.toLocaleString()}</div>
                <div className={styles.targetGoal}>
                  {r.target_yuan > 0 ? `¥${r.target_yuan.toLocaleString()}` : '—'}
                </div>
                <div className={`${styles.targetGap} ${r.gap_yuan != null && r.gap_yuan >= 0 ? styles.gapPos : styles.gapNeg}`}>
                  {r.gap_yuan != null ? `${r.gap_yuan >= 0 ? '+' : ''}¥${r.gap_yuan.toLocaleString()}` : '—'}
                </div>
                <div>
                  {r.achievement_pct != null ? (
                    <ZBadge
                      type={r.achievement_pct >= 100 ? 'success' : r.achievement_pct >= 80 ? 'info' : 'warning'}
                      text={`${r.achievement_pct}%`} />
                  ) : '—'}
                </div>
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* Sentiment summary */}
      <ZCard title="评价情绪分布（近6个月）">
        {!sentiment ? <ZEmpty title="暂无评价数据" /> : (
          <>
            <div className={styles.sentGrid}>
              <div className={`${styles.sentKpi} ${styles.sentPos}`}>
                <div className={styles.sentVal}>{sentiment.positive}</div>
                <div className={styles.sentLabel}>正面</div>
              </div>
              <div className={`${styles.sentKpi} ${styles.sentNeu}`}>
                <div className={styles.sentVal}>{sentiment.neutral}</div>
                <div className={styles.sentLabel}>中性</div>
              </div>
              <div className={`${styles.sentKpi} ${styles.sentNeg}`}>
                <div className={styles.sentVal}>{sentiment.negative}</div>
                <div className={styles.sentLabel}>负面</div>
              </div>
            </div>
            {sentTrend.length > 0 && (
              <div className={styles.sentTrendList}>
                {sentTrend.map(t => {
                  const total = t.positive + t.neutral + t.negative || 1;
                  return (
                    <div key={t.month} className={styles.sentTrendRow}>
                      <span className={styles.sentMonth}>{t.month}</span>
                      <div className={styles.sentBar}>
                        <div style={{ width: `${t.positive/total*100}%`, background: 'var(--green)', height: '100%' }} />
                        <div style={{ width: `${t.neutral/total*100}%`,  background: 'var(--yellow)', height: '100%' }} />
                        <div style={{ width: `${t.negative/total*100}%`, background: 'var(--red)',    height: '100%' }} />
                      </div>
                      {t.avg_ai_score != null && (
                        <span className={styles.sentAi}>AI {t.avg_ai_score}</span>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </ZCard>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────────────────
// Phase 28 Tab 1 — SeasonalPatternTab「季节规律」
// ─────────────────────────────────────────────────────────────────────────────

interface SeasonalRow {
  month: number;
  month_name: string;
  avg_revenue_yuan: number;
  is_peak: boolean;
  is_trough: boolean;
}
interface SizeGroup {
  label: string;
  order_count: number;
  avg_per_table_yuan: number | null;
  total_revenue_yuan: number;
}

function SeasonalPatternTab() {
  const { storeId } = useStore();
  const [pattern,    setPattern]   = React.useState<SeasonalRow[]>([]);
  const [peakMonth,  setPeakMonth] = React.useState<number | null>(null);
  const [sizeGroups, setSizeGroups] = React.useState<SizeGroup[]>([]);
  const [inflection, setInflection] = React.useState<string | null>(null);
  const [loading,    setLoading]   = React.useState(false);

  useEffect(() => {
    if (!storeId) return;
    setLoading(true);
    Promise.allSettled([
      apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/seasonal-revenue-pattern?years=2`),
      apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/banquet-size-revenue-correlation?months=12`),
    ]).then(([r1, r2]) => {
      if (r1.status === 'fulfilled') {
        setPattern(r1.value.data.monthly_pattern ?? []);
        setPeakMonth(r1.value.data.peak_month ?? null);
      }
      if (r2.status === 'fulfilled') {
        setSizeGroups(r2.value.data.size_groups ?? []);
        setInflection(r2.value.data.inflection_point ?? null);
      }
    }).catch(handleApiError).finally(() => setLoading(false));
  }, [storeId]);

  if (loading) return <ZSkeleton rows={6} />;

  const maxRev = Math.max(...pattern.map(r => r.avg_revenue_yuan), 1);

  return (
    <div className={styles.seasonalTab}>
      {/* Seasonal revenue */}
      <ZCard title={`季节性营收规律${peakMonth ? `（旺季：${peakMonth}月）` : ''}`}>
        {pattern.length === 0 ? <ZEmpty title="暂无历史数据" /> : (
          <div className={styles.seasonalBars}>
            {pattern.map(r => (
              <div key={r.month} className={`${styles.seasonBar} ${r.is_peak ? styles.seasonPeak : r.is_trough ? styles.seasonTrough : ''}`}>
                <div className={styles.seasonBarInner}>
                  <div className={styles.seasonBarFill}
                    style={{ height: `${Math.round(r.avg_revenue_yuan / maxRev * 100)}%` }} />
                </div>
                <div className={styles.seasonMonthLabel}>{r.month_name}</div>
                <div className={styles.seasonRevLabel}>¥{(r.avg_revenue_yuan / 1000).toFixed(1)}k</div>
              </div>
            ))}
          </div>
        )}
      </ZCard>

      {/* Size-revenue correlation */}
      <ZCard title={`规模收益分析${inflection ? `（最优规模：${inflection}）` : ''}`}>
        {sizeGroups.length === 0 ? <ZEmpty title="暂无数据" /> : (
          <div className={styles.sizeCorrelList}>
            <div className={styles.sizeCorrelHeader}>
              <span>规模</span><span>订单数</span><span>桌均价</span><span>总收入</span>
            </div>
            {sizeGroups.map(g => (
              <div key={g.label} className={`${styles.sizeCorrelRow} ${g.label === inflection ? styles.sizeOptimal : ''}`}>
                <div className={styles.sizeLabel}>{g.label}</div>
                <div>{g.order_count}</div>
                <div className={styles.sizeAvg}>
                  {g.avg_per_table_yuan != null ? `¥${g.avg_per_table_yuan.toLocaleString()}` : '—'}
                </div>
                <div>¥{g.total_revenue_yuan.toLocaleString()}</div>
              </div>
            ))}
          </div>
        )}
      </ZCard>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────────────────
// Phase 28 Tab 2 — CustomerLTVTab「客户LTV」
// ─────────────────────────────────────────────────────────────────────────────

interface LTVBucket { label: string; count: number; pct: number; }
interface LTVTop { customer_id: string; ltv_yuan: number; banquet_count: number; }
interface FollowUpRow {
  followup_bucket: string;
  total_leads: number;
  won_leads: number;
  win_rate_pct: number;
}

function CustomerLTVTab() {
  const { storeId } = useStore();
  const [buckets,  setBuckets]  = React.useState<LTVBucket[]>([]);
  const [top,      setTop]      = React.useState<LTVTop[]>([]);
  const [avgLtv,   setAvgLtv]   = React.useState<number | null>(null);
  const [fuRows,   setFuRows]   = React.useState<FollowUpRow[]>([]);
  const [optimal,  setOptimal]  = React.useState<string | null>(null);
  const [loading,  setLoading]  = React.useState(false);

  useEffect(() => {
    if (!storeId) return;
    setLoading(true);
    Promise.allSettled([
      apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/customer-lifetime-value?top_n=10`),
      apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/follow-up-effectiveness?months=6`),
    ]).then(([r1, r2]) => {
      if (r1.status === 'fulfilled') {
        setBuckets(r1.value.data.ltv_buckets ?? []);
        setTop(r1.value.data.top ?? []);
        setAvgLtv(r1.value.data.avg_ltv_yuan ?? null);
      }
      if (r2.status === 'fulfilled') {
        setFuRows(r2.value.data.rows ?? []);
        setOptimal(r2.value.data.optimal_followup_bucket ?? null);
      }
    }).catch(handleApiError).finally(() => setLoading(false));
  }, [storeId]);

  if (loading) return <ZSkeleton rows={6} />;

  return (
    <div className={styles.ltvTab}>
      {/* LTV distribution */}
      <ZCard title={`客户LTV分布${avgLtv != null ? `（均值 ¥${avgLtv.toLocaleString()}）` : ''}`}>
        {buckets.length === 0 ? <ZEmpty title="暂无客户数据" /> : (
          <div className={styles.ltvBuckets}>
            {buckets.map(b => (
              <div key={b.label} className={styles.ltvBucket}>
                <div className={styles.ltvBucketLabel}>{b.label}</div>
                <div className={styles.ltvBucketBarTrack}>
                  <div className={styles.ltvBucketBarFill} style={{ width: `${b.pct}%` }} />
                </div>
                <div className={styles.ltvBucketStats}>
                  <span>{b.count}人</span>
                  <span className={styles.ltvBucketPct}>{b.pct}%</span>
                </div>
              </div>
            ))}
            <div className={styles.ltvTopList}>
              {top.slice(0, 5).map((c, i) => (
                <div key={c.customer_id} className={styles.ltvTopRow}>
                  <span className={styles.ltvTopRank}>{i + 1}</span>
                  <span className={styles.ltvTopId}>{c.customer_id}</span>
                  <span>{c.banquet_count}次</span>
                  <span className={styles.ltvTopAmt}>¥{c.ltv_yuan.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      {/* Follow-up effectiveness */}
      <ZCard title={`跟进次数与转化率${optimal ? `（最优：${optimal}）` : ''}`}>
        {fuRows.length === 0 ? <ZEmpty title="暂无跟进数据" /> : (
          <div className={styles.fuList}>
            <div className={styles.fuHeader}>
              <span>跟进次数</span><span>线索数</span><span>成交数</span><span>成交率</span>
            </div>
            {fuRows.map(r => (
              <div key={r.followup_bucket}
                className={`${styles.fuRow} ${r.followup_bucket === optimal ? styles.fuOptimal : ''}`}>
                <div className={styles.fuBucket}>{r.followup_bucket}</div>
                <div>{r.total_leads}</div>
                <div>{r.won_leads}</div>
                <div>
                  <ZBadge
                    type={r.win_rate_pct >= 50 ? 'success' : r.win_rate_pct >= 25 ? 'info' : 'default'}
                    text={`${r.win_rate_pct}%`} />
                </div>
              </div>
            ))}
          </div>
        )}
      </ZCard>
    </div>
  );
}

// Phase 29 Tab 1 — RepeatCustomerTab「回头客」
function RepeatCustomerTab() {
  const { storeId } = useStore();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/repeat-customer-rate`);
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId]);
  useEffect(() => { load(); }, [load]);

  const [srcData, setSrcData] = useState<any>(null);
  const [srcLoading, setSrcLoading] = useState(false);
  const loadSrc = useCallback(async () => {
    if (!storeId) return;
    setSrcLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/lead-source-roi`);
      setSrcData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setSrcLoading(false); }
  }, [storeId]);
  useEffect(() => { loadSrc(); }, [loadSrc]);

  return (
    <div className={styles.repeatTab}>
      <ZCard title="回头客分析">
        {loading ? <ZSkeleton /> : !data ? <ZEmpty message="暂无数据" /> : (
          <div className={styles.repeatKpiRow}>
            <div className={styles.repeatKpi}>
              <div className={styles.repeatKpiVal}>{data.total_customers ?? '-'}</div>
              <div className={styles.repeatKpiLabel}>总客户数</div>
            </div>
            <div className={styles.repeatKpi}>
              <div className={styles.repeatKpiVal}>{data.repeat_customers ?? '-'}</div>
              <div className={styles.repeatKpiLabel}>回头客数</div>
            </div>
            <div className={`${styles.repeatKpi} ${styles.repeatAccent}`}>
              <div className={styles.repeatKpiVal}>{data.repeat_rate_pct != null ? `${data.repeat_rate_pct}%` : '-'}</div>
              <div className={styles.repeatKpiLabel}>回头客率</div>
            </div>
            <div className={styles.repeatKpi}>
              <div className={styles.repeatKpiVal}>¥{data.repeat_customer_revenue_yuan?.toLocaleString() ?? '-'}</div>
              <div className={styles.repeatKpiLabel}>回头客贡献</div>
            </div>
            <div className={styles.repeatKpi}>
              <div className={styles.repeatKpiVal}>¥{data.new_customer_revenue_yuan?.toLocaleString() ?? '-'}</div>
              <div className={styles.repeatKpiLabel}>新客贡献</div>
            </div>
          </div>
        )}
      </ZCard>
      <ZCard title="线索来源 ROI">
        {srcLoading ? <ZSkeleton /> : !srcData || srcData.sources.length === 0 ? <ZEmpty message="暂无数据" /> : (
          <div className={styles.srcRoiList}>
            <div className={styles.srcRoiHeader}>
              <span>来源渠道</span><span>线索数</span><span>签约数</span><span>转化率</span><span>平均预算</span>
            </div>
            {srcData.sources.map((s: any) => (
              <div key={s.source} className={`${styles.srcRoiRow} ${s.source === srcData.best_source ? styles.srcBest : ''}`}>
                <span className={styles.srcName}>{s.source}</span>
                <span>{s.lead_count}</span>
                <span>{s.won_count}</span>
                <span className={styles.srcRate}>{s.conversion_rate_pct}%</span>
                <span>¥{s.avg_budget_yuan?.toLocaleString()}</span>
              </div>
            ))}
          </div>
        )}
      </ZCard>
    </div>
  );
}

// Phase 29 Tab 2 — BookingLeadTimeTab「提前天数」
function BookingLeadTimeTab() {
  const { storeId } = useStore();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/advance-booking-lead-time`);
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId]);
  useEffect(() => { load(); }, [load]);

  const [collData, setCollData] = useState<any>(null);
  const [collLoading, setCollLoading] = useState(false);
  const loadColl = useCallback(async () => {
    if (!storeId) return;
    setCollLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/payment-collection-rate`);
      setCollData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setCollLoading(false); }
  }, [storeId]);
  useEffect(() => { loadColl(); }, [loadColl]);

  const maxCount = data?.buckets ? Math.max(...data.buckets.map((b: any) => b.count), 1) : 1;

  return (
    <div className={styles.leadTimeTab}>
      <ZCard title="提前预订天数分布">
        {loading ? <ZSkeleton /> : !data ? <ZEmpty message="暂无数据" /> : (
          <>
            <div className={styles.leadTimeKpiRow}>
              <div className={styles.leadTimeKpi}>
                <div className={styles.leadTimeVal}>{data.avg_lead_days ?? '-'}</div>
                <div className={styles.leadTimeLabel}>平均提前天数</div>
              </div>
              <div className={styles.leadTimeKpi}>
                <div className={styles.leadTimeVal}>{data.median_lead_days ?? '-'}</div>
                <div className={styles.leadTimeLabel}>中位数</div>
              </div>
              <div className={styles.leadTimeKpi}>
                <div className={styles.leadTimeVal}>{data.total_orders}</div>
                <div className={styles.leadTimeLabel}>订单总数</div>
              </div>
            </div>
            <div className={styles.leadTimeBuckets}>
              {data.buckets.map((b: any) => (
                <div key={b.bucket} className={styles.leadTimeBucket}>
                  <div className={styles.leadTimeBucketLabel}>{b.bucket}</div>
                  <div className={styles.leadTimeBucketTrack}>
                    <div className={styles.leadTimeBucketFill} style={{ width: `${b.count / maxCount * 100}%` }} />
                  </div>
                  <div className={styles.leadTimeBucketCount}>{b.count} ({b.pct}%)</div>
                </div>
              ))}
            </div>
          </>
        )}
      </ZCard>
      <ZCard title="回款率 & 欠款订单">
        {collLoading ? <ZSkeleton /> : !collData ? <ZEmpty message="暂无数据" /> : (
          <>
            <div className={styles.collKpiRow}>
              <div className={styles.collKpi}>
                <div className={styles.collKpiVal}>¥{collData.total_receivable_yuan?.toLocaleString() ?? '-'}</div>
                <div className={styles.collKpiLabel}>应收总额</div>
              </div>
              <div className={styles.collKpi}>
                <div className={styles.collKpiVal}>¥{collData.total_collected_yuan?.toLocaleString() ?? '-'}</div>
                <div className={styles.collKpiLabel}>已收总额</div>
              </div>
              <div className={`${styles.collKpi} ${(collData.collection_rate_pct ?? 100) < 80 ? styles.collRed : ''}`}>
                <div className={styles.collKpiVal}>{collData.collection_rate_pct != null ? `${collData.collection_rate_pct}%` : '-'}</div>
                <div className={styles.collKpiLabel}>回款率</div>
              </div>
              <div className={styles.collKpi}>
                <div className={styles.collKpiVal}>{collData.overdue_count}</div>
                <div className={styles.collKpiLabel}>欠款订单</div>
              </div>
            </div>
            {collData.overdue_orders.length > 0 && (
              <div className={styles.overdueList}>
                <div className={styles.overdueHeader}>
                  <span>订单</span><span>宴会日期</span><span>应收¥</span><span>已收¥</span><span>欠款¥</span>
                </div>
                {collData.overdue_orders.slice(0, 10).map((row: any) => (
                  <div key={row.order_id} className={styles.overdueRow}>
                    <span className={styles.overdueId}>{row.order_id.slice(-6)}</span>
                    <span>{row.banquet_date}</span>
                    <span>¥{row.total_yuan?.toLocaleString()}</span>
                    <span>¥{row.paid_yuan?.toLocaleString()}</span>
                    <span className={styles.overdueAmt}>¥{row.outstanding_yuan?.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </ZCard>
    </div>
  );
}

// Phase 30 Tab 1 — TableUtilizationTab「桌位利用率」
function TableUtilizationTab() {
  const { storeId } = useStore();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/table-utilization-rate`);
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId]);
  useEffect(() => { load(); }, [load]);

  const [peakData, setPeakData] = useState<any>(null);
  const [peakLoading, setPeakLoading] = useState(false);
  const loadPeak = useCallback(async () => {
    if (!storeId) return;
    setPeakLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/peak-day-revenue`);
      setPeakData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setPeakLoading(false); }
  }, [storeId]);
  useEffect(() => { loadPeak(); }, [loadPeak]);

  const maxRev = peakData?.by_weekday ? Math.max(...peakData.by_weekday.map((w: any) => w.total_revenue_yuan), 1) : 1;

  return (
    <div className={styles.tableUtilTab}>
      <ZCard title="桌位利用率">
        {loading ? <ZSkeleton /> : !data || data.halls.length === 0 ? <ZEmpty message="暂无数据" /> : (
          <>
            <div className={styles.tableUtilKpi}>
              <span>整体利用率</span>
              <span className={styles.tableUtilPct}>
                {data.overall_utilization_pct != null ? `${data.overall_utilization_pct}%` : '-'}
              </span>
            </div>
            <div className={styles.tableUtilList}>
              <div className={styles.tableUtilHeader}>
                <span>厅房</span><span>预订场次</span><span>实用桌数</span><span>利用率</span>
              </div>
              {data.halls.map((h: any) => (
                <div key={h.hall_id} className={styles.tableUtilRow}>
                  <span>{h.hall_name}</span>
                  <span>{h.booking_count}</span>
                  <span>{h.total_used_tables}</span>
                  <span className={styles.tableUtilPct}>{h.utilization_pct != null ? `${h.utilization_pct}%` : '-'}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </ZCard>
      <ZCard title="峰值收入日">
        {peakLoading ? <ZSkeleton /> : !peakData ? <ZEmpty message="暂无数据" /> : (
          <>
            {peakData.peak_weekday && (
              <div className={styles.peakBadge}>峰值：{peakData.peak_weekday}</div>
            )}
            <div className={styles.peakBars}>
              {peakData.by_weekday.map((w: any) => (
                <div key={w.weekday} className={`${styles.peakBar} ${w.weekday === peakData.peak_weekday ? styles.peakBarTop : ''}`}>
                  <div className={styles.peakBarInner}>
                    <div
                      className={styles.peakBarFill}
                      style={{ height: `${w.total_revenue_yuan / maxRev * 100}%` }}
                    />
                  </div>
                  <div className={styles.peakBarLabel}>{w.weekday}</div>
                  <div className={styles.peakBarVal}>¥{(w.total_revenue_yuan / 1000).toFixed(1)}k</div>
                </div>
              ))}
            </div>
          </>
        )}
      </ZCard>
    </div>
  );
}

// Phase 30 Tab 2 — SatisfactionReferralTab「满意度&转介绍」
function SatisfactionReferralTab() {
  const { storeId } = useStore();
  const [satData, setSatData] = useState<any>(null);
  const [satLoading, setSatLoading] = useState(false);
  const [refData, setRefData] = useState<any>(null);
  const [refLoading, setRefLoading] = useState(false);

  const loadSat = useCallback(async () => {
    if (!storeId) return;
    setSatLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/customer-satisfaction-score`);
      setSatData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setSatLoading(false); }
  }, [storeId]);

  const loadRef = useCallback(async () => {
    if (!storeId) return;
    setRefLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/referral-rate`);
      setRefData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setRefLoading(false); }
  }, [storeId]);

  useEffect(() => { loadSat(); loadRef(); }, [loadSat, loadRef]);

  return (
    <div className={styles.satRefTab}>
      <ZCard title="客户满意度">
        {satLoading ? <ZSkeleton /> : !satData ? <ZEmpty message="暂无数据" /> : (
          <>
            <div className={styles.satKpiRow}>
              <div className={styles.satKpi}>
                <div className={styles.satKpiVal}>{satData.avg_rating ?? '-'}</div>
                <div className={styles.satKpiLabel}>平均评分</div>
              </div>
              <div className={styles.satKpi}>
                <div className={styles.satKpiVal}>{satData.avg_ai_score ?? '-'}</div>
                <div className={styles.satKpiLabel}>AI评分</div>
              </div>
              <div className={styles.satKpi}>
                <div className={`${styles.satKpiVal} ${(satData.nps_estimate ?? 0) >= 50 ? styles.satGreen : ''}`}>
                  {satData.nps_estimate ?? '-'}
                </div>
                <div className={styles.satKpiLabel}>NPS估算</div>
              </div>
              <div className={styles.satKpi}>
                <div className={styles.satKpiVal}>{satData.total_reviews}</div>
                <div className={styles.satKpiLabel}>总评价数</div>
              </div>
            </div>
            {satData.by_month.length > 0 && (
              <div className={styles.satMonthList}>
                {satData.by_month.map((m: any) => (
                  <div key={m.month} className={styles.satMonthRow}>
                    <span className={styles.satMonth}>{m.month}</span>
                    <span>{m.review_count} 条</span>
                    <span>均分 {m.avg_rating ?? '-'}</span>
                    <span>AI {m.avg_ai_score ?? '-'}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </ZCard>
      <ZCard title="转介绍率">
        {refLoading ? <ZSkeleton /> : !refData ? <ZEmpty message="暂无数据" /> : (
          <div className={styles.refKpiRow}>
            <div className={styles.refKpi}>
              <div className={styles.refKpiVal}>{refData.total_leads}</div>
              <div className={styles.refKpiLabel}>总线索</div>
            </div>
            <div className={styles.refKpi}>
              <div className={styles.refKpiVal}>{refData.referral_count}</div>
              <div className={styles.refKpiLabel}>转介绍线索</div>
            </div>
            <div className={`${styles.refKpi} ${styles.refAccent}`}>
              <div className={styles.refKpiVal}>{refData.referral_rate_pct != null ? `${refData.referral_rate_pct}%` : '-'}</div>
              <div className={styles.refKpiLabel}>转介绍率</div>
            </div>
            <div className={styles.refKpi}>
              <div className={styles.refKpiVal}>{refData.referral_win_rate_pct != null ? `${refData.referral_win_rate_pct}%` : '-'}</div>
              <div className={styles.refKpiLabel}>转介绍签约率</div>
            </div>
            <div className={styles.refKpi}>
              <div className={styles.refKpiVal}>{refData.non_referral_win_rate_pct != null ? `${refData.non_referral_win_rate_pct}%` : '-'}</div>
              <div className={styles.refKpiLabel}>其他渠道签约率</div>
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

// Phase 31 Tab 1 — QuoteTurnaroundTab「报价周转」
function QuoteTurnaroundTab() {
  const { storeId } = useStore();
  const [qtData, setQtData] = useState<any>(null);
  const [qtLoading, setQtLoading] = useState(false);
  const [contractData, setContractData] = useState<any>(null);
  const [contractLoading, setContractLoading] = useState(false);

  const loadQt = useCallback(async () => {
    if (!storeId) return;
    setQtLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/quote-turnaround-time`);
      setQtData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setQtLoading(false); }
  }, [storeId]);

  const loadContract = useCallback(async () => {
    if (!storeId) return;
    setContractLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/contract-signed-rate`);
      setContractData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setContractLoading(false); }
  }, [storeId]);

  useEffect(() => { loadQt(); loadContract(); }, [loadQt, loadContract]);

  const maxQtCount = qtData?.buckets ? Math.max(...qtData.buckets.map((b: any) => b.count), 1) : 1;

  return (
    <div className={styles.qtTab}>
      <ZCard title="报价周转时间">
        {qtLoading ? <ZSkeleton /> : !qtData ? <ZEmpty message="暂无数据" /> : (
          <>
            <div className={styles.qtKpiRow}>
              <div className={styles.qtKpi}>
                <div className={styles.qtKpiVal}>{qtData.avg_days ?? '-'} 天</div>
                <div className={styles.qtKpiLabel}>平均周转</div>
              </div>
              <div className={styles.qtKpi}>
                <div className={styles.qtKpiVal}>{qtData.median_days ?? '-'} 天</div>
                <div className={styles.qtKpiLabel}>中位数</div>
              </div>
              <div className={styles.qtKpi}>
                <div className={styles.qtKpiVal}>{qtData.quoted_leads} / {qtData.total_leads}</div>
                <div className={styles.qtKpiLabel}>已报价/总线索</div>
              </div>
            </div>
            {qtData.buckets.length > 0 && (
              <div className={styles.qtBuckets}>
                {qtData.buckets.map((b: any) => (
                  <div key={b.bucket} className={styles.qtBucket}>
                    <div className={styles.qtBucketLabel}>{b.bucket}</div>
                    <div className={styles.qtBucketTrack}>
                      <div className={styles.qtBucketFill} style={{ width: `${b.count / maxQtCount * 100}%` }} />
                    </div>
                    <div className={styles.qtBucketCount}>{b.count} ({b.pct}%)</div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </ZCard>
      <ZCard title="合同签约率">
        {contractLoading ? <ZSkeleton /> : !contractData ? <ZEmpty message="暂无数据" /> : (
          <div className={styles.contractKpiRow}>
            <div className={styles.contractKpi}>
              <div className={styles.contractKpiVal}>{contractData.total_orders}</div>
              <div className={styles.contractKpiLabel}>总订单</div>
            </div>
            <div className={styles.contractKpi}>
              <div className={styles.contractKpiVal}>{contractData.with_contract}</div>
              <div className={styles.contractKpiLabel}>有合同</div>
            </div>
            <div className={`${styles.contractKpi} ${styles.contractAccent}`}>
              <div className={styles.contractKpiVal}>
                {contractData.contract_rate_pct != null ? `${contractData.contract_rate_pct}%` : '-'}
              </div>
              <div className={styles.contractKpiLabel}>签约率</div>
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

// Phase 31 Tab 2 — NewVsRepeatMonthlyTab「新客vs回头客」
function NewVsRepeatMonthlyTab() {
  const { storeId } = useStore();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [overdueData, setOverdueData] = useState<any>(null);
  const [overdueLoading, setOverdueLoading] = useState(false);

  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/monthly-new-vs-repeat`);
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId]);

  const loadOverdue = useCallback(async () => {
    if (!storeId) return;
    setOverdueLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/staff-task-overdue-rate`);
      setOverdueData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setOverdueLoading(false); }
  }, [storeId]);

  useEffect(() => { load(); loadOverdue(); }, [load, loadOverdue]);

  return (
    <div className={styles.newRepeatTab}>
      <ZCard title="月度新客 vs 回头客">
        {loading ? <ZSkeleton /> : !data || data.monthly.length === 0 ? <ZEmpty message="暂无数据" /> : (
          <div className={styles.nrTable}>
            <div className={styles.nrHeader}>
              <span>月份</span><span>新客单数</span><span>新客收入¥</span><span>回头客单数</span><span>回头客收入¥</span>
            </div>
            {data.monthly.map((m: any) => (
              <div key={m.month} className={styles.nrRow}>
                <span className={styles.nrMonth}>{m.month}</span>
                <span>{m.new_orders}</span>
                <span>¥{m.new_revenue_yuan?.toLocaleString()}</span>
                <span className={styles.nrRepeat}>{m.repeat_orders}</span>
                <span>¥{m.repeat_revenue_yuan?.toLocaleString()}</span>
              </div>
            ))}
          </div>
        )}
      </ZCard>
      <ZCard title="员工任务逾期率">
        {overdueLoading ? <ZSkeleton /> : !overdueData ? <ZEmpty message="暂无数据" /> : (
          <>
            <div className={styles.overdueKpiRow}>
              <div className={styles.overdueKpi}>
                <div className={styles.overdueKpiVal}>{overdueData.total_tasks}</div>
                <div className={styles.overdueKpiLabel}>总任务</div>
              </div>
              <div className={styles.overdueKpi}>
                <div className={`${styles.overdueKpiVal} ${overdueData.overdue_tasks > 0 ? styles.overdueRed : ''}`}>
                  {overdueData.overdue_tasks}
                </div>
                <div className={styles.overdueKpiLabel}>逾期任务</div>
              </div>
              <div className={styles.overdueKpi}>
                <div className={styles.overdueKpiVal}>
                  {overdueData.overall_overdue_rate_pct != null ? `${overdueData.overall_overdue_rate_pct}%` : '-'}
                </div>
                <div className={styles.overdueKpiLabel}>整体逾期率</div>
              </div>
            </div>
            {overdueData.by_staff.length > 0 && (
              <div className={styles.overdueStaffList}>
                <div className={styles.overdueStaffHeader}>
                  <span>员工</span><span>总任务</span><span>逾期数</span><span>逾期率</span>
                </div>
                {overdueData.by_staff.map((s: any) => (
                  <div key={s.user_id} className={`${styles.overdueStaffRow} ${s.overdue_rate_pct > 20 ? styles.overdueHighRow : ''}`}>
                    <span className={styles.overdueStaffId}>{s.user_id.slice(-6)}</span>
                    <span>{s.total_tasks}</span>
                    <span>{s.overdue_tasks}</span>
                    <span className={s.overdue_rate_pct > 20 ? styles.overdueRed : ''}>{s.overdue_rate_pct}%</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </ZCard>
    </div>
  );
}

// Phase 32 Tab 1 — OrderAmendmentTab「订单修改&套餐附加」
function OrderAmendmentTab() {
  const { storeId } = useStore();
  const [amendData, setAmendData] = useState<any>(null);
  const [amendLoading, setAmendLoading] = useState(false);
  const [attachData, setAttachData] = useState<any>(null);
  const [attachLoading, setAttachLoading] = useState(false);

  const loadAmend = useCallback(async () => {
    if (!storeId) return;
    setAmendLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/order-amendment-rate`);
      setAmendData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setAmendLoading(false); }
  }, [storeId]);

  const loadAttach = useCallback(async () => {
    if (!storeId) return;
    setAttachLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/package-attach-rate`);
      setAttachData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setAttachLoading(false); }
  }, [storeId]);

  useEffect(() => { loadAmend(); loadAttach(); }, [loadAmend, loadAttach]);

  return (
    <div className={styles.amendTab}>
      <ZCard title="订单修改率">
        {amendLoading ? <ZSkeleton /> : !amendData ? <ZEmpty message="暂无数据" /> : (
          <div className={styles.amendKpiRow}>
            <div className={styles.amendKpi}>
              <div className={styles.amendKpiVal}>{amendData.total_orders}</div>
              <div className={styles.amendKpiLabel}>总订单</div>
            </div>
            <div className={styles.amendKpi}>
              <div className={styles.amendKpiVal}>{amendData.amended_orders}</div>
              <div className={styles.amendKpiLabel}>修改订单</div>
            </div>
            <div className={`${styles.amendKpi} ${styles.amendAccent}`}>
              <div className={styles.amendKpiVal}>
                {amendData.amendment_rate_pct != null ? `${amendData.amendment_rate_pct}%` : '-'}
              </div>
              <div className={styles.amendKpiLabel}>修改率</div>
            </div>
          </div>
        )}
      </ZCard>
      <ZCard title="套餐附加率">
        {attachLoading ? <ZSkeleton /> : !attachData ? <ZEmpty message="暂无数据" /> : (
          <>
            <div className={styles.attachKpiRow}>
              <div className={styles.attachKpi}>
                <div className={styles.attachKpiVal}>{attachData.total_orders}</div>
                <div className={styles.attachKpiLabel}>总订单</div>
              </div>
              <div className={styles.attachKpi}>
                <div className={styles.attachKpiVal}>{attachData.with_package}</div>
                <div className={styles.attachKpiLabel}>含套餐</div>
              </div>
              <div className={`${styles.attachKpi} ${styles.attachAccent}`}>
                <div className={styles.attachKpiVal}>
                  {attachData.attach_rate_pct != null ? `${attachData.attach_rate_pct}%` : '-'}
                </div>
                <div className={styles.attachKpiLabel}>附加率</div>
              </div>
            </div>
            {attachData.top_packages.length > 0 && (
              <div className={styles.topPkgList}>
                {attachData.top_packages.map((p: any, i: number) => (
                  <div key={p.package_id} className={styles.topPkgRow}>
                    <span className={styles.topPkgRank}>#{i + 1}</span>
                    <span className={styles.topPkgId}>{p.package_id.slice(-8)}</span>
                    <span>{p.order_count} 单</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </ZCard>
    </div>
  );
}

// Phase 32 Tab 2 — ProfitabilityTab「盈利能力&执行评分」
function ProfitabilityTab() {
  const { storeId } = useStore();
  const [profData, setProfData] = useState<any>(null);
  const [profLoading, setProfLoading] = useState(false);
  const [execData, setExecData] = useState<any>(null);
  const [execLoading, setExecLoading] = useState(false);

  const loadProf = useCallback(async () => {
    if (!storeId) return;
    setProfLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/banquet-type-profitability`);
      setProfData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setProfLoading(false); }
  }, [storeId]);

  const loadExec = useCallback(async () => {
    if (!storeId) return;
    setExecLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/event-execution-score`);
      setExecData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setExecLoading(false); }
  }, [storeId]);

  useEffect(() => { loadProf(); loadExec(); }, [loadProf, loadExec]);

  return (
    <div className={styles.profTab}>
      <ZCard title="宴会类型盈利能力">
        {profLoading ? <ZSkeleton /> : !profData || profData.types.length === 0 ? <ZEmpty message="暂无数据" /> : (
          <div className={styles.profList}>
            <div className={styles.profHeader}>
              <span>类型</span><span>单数</span><span>收入¥</span><span>成本¥</span><span>毛利率</span>
            </div>
            {profData.types.map((t: any) => (
              <div key={t.banquet_type} className={`${styles.profRow} ${t.banquet_type === profData.most_profitable_type ? styles.profTop : ''}`}>
                <span className={styles.profType}>{t.banquet_type}</span>
                <span>{t.order_count}</span>
                <span>¥{t.total_revenue_yuan?.toLocaleString()}</span>
                <span>¥{t.total_cost_yuan?.toLocaleString()}</span>
                <span className={styles.profMargin}>{t.gross_margin_pct != null ? `${t.gross_margin_pct}%` : '-'}</span>
              </div>
            ))}
          </div>
        )}
      </ZCard>
      <ZCard title="宴会执行综合评分">
        {execLoading ? <ZSkeleton /> : !execData ? <ZEmpty message="暂无数据" /> : (
          <>
            <div className={styles.execKpiRow}>
              <div className={styles.execKpi}>
                <div className={styles.execKpiVal}>{execData.total_events}</div>
                <div className={styles.execKpiLabel}>已完成场次</div>
              </div>
              <div className={`${styles.execKpi} ${styles.execAccent}`}>
                <div className={styles.execKpiVal}>{execData.avg_execution_score ?? '-'}</div>
                <div className={styles.execKpiLabel}>平均执行评分</div>
              </div>
            </div>
            {execData.events.length > 0 && (
              <div className={styles.execList}>
                <div className={styles.execHeader}>
                  <span>宴会日期</span><span>任务完成率</span><span>异常数</span><span>评分</span>
                </div>
                {execData.events.slice(0, 8).map((e: any) => (
                  <div key={e.order_id} className={styles.execRow}>
                    <span>{e.banquet_date}</span>
                    <span>{e.task_completion_rate}%</span>
                    <span>{e.exception_count}</span>
                    <span className={e.execution_score >= 80 ? styles.execGood : styles.execWarn}>
                      {e.execution_score}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </ZCard>
    </div>
  );
}

// Phase 33 Tab 1 — CrossSellTab「交叉销售&规模趋势」
function CrossSellTab() {
  const { storeId } = useStore();
  const [crossData, setCrossData] = useState<any>(null);
  const [crossLoading, setCrossLoading] = useState(false);
  const [sizeData, setSizeData] = useState<any>(null);
  const [sizeLoading, setSizeLoading] = useState(false);

  const loadCross = useCallback(async () => {
    if (!storeId) return;
    setCrossLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/cross-sell-rate`);
      setCrossData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setCrossLoading(false); }
  }, [storeId]);

  const loadSize = useCallback(async () => {
    if (!storeId) return;
    setSizeLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/banquet-size-trend`);
      setSizeData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setSizeLoading(false); }
  }, [storeId]);

  useEffect(() => { loadCross(); loadSize(); }, [loadCross, loadSize]);

  return (
    <div className={styles.crossTab}>
      <ZCard title="交叉销售率">
        {crossLoading ? <ZSkeleton /> : !crossData ? <ZEmpty message="暂无数据" /> : (
          <div className={styles.crossKpiRow}>
            <div className={styles.crossKpi}>
              <div className={styles.crossKpiVal}>{crossData.total_customers}</div>
              <div className={styles.crossKpiLabel}>总客户数</div>
            </div>
            <div className={styles.crossKpi}>
              <div className={styles.crossKpiVal}>{crossData.cross_sell_customers}</div>
              <div className={styles.crossKpiLabel}>跨类型客户</div>
            </div>
            <div className={`${styles.crossKpi} ${styles.crossAccent}`}>
              <div className={styles.crossKpiVal}>
                {crossData.cross_sell_rate_pct != null ? `${crossData.cross_sell_rate_pct}%` : '-'}
              </div>
              <div className={styles.crossKpiLabel}>交叉销售率</div>
            </div>
          </div>
        )}
      </ZCard>
      <ZCard title="宴会规模趋势（平均桌数）">
        {sizeLoading ? <ZSkeleton /> : !sizeData || sizeData.monthly.length === 0 ? <ZEmpty message="暂无数据" /> : (
          <>
            <div className={styles.sizeOverallKpi}>
              整体均值 <span className={styles.sizeOverallVal}>{sizeData.overall_avg_tables ?? '-'} 桌</span>
            </div>
            <div className={styles.sizeTrendList}>
              {sizeData.monthly.map((m: any) => (
                <div key={m.month} className={styles.sizeTrendRow}>
                  <span className={styles.sizeTrendMonth}>{m.month}</span>
                  <span>{m.order_count} 单</span>
                  <span className={styles.sizeTrendAvg}>{m.avg_tables ?? '-'} 桌</span>
                  <span>¥{m.total_revenue_yuan?.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </ZCard>
    </div>
  );
}

// Phase 33 Tab 2 — VipSpendingTab「VIP消费&账龄」
function VipSpendingTab() {
  const { storeId } = useStore();
  const [vipData, setVipData] = useState<any>(null);
  const [vipLoading, setVipLoading] = useState(false);
  const [agingData, setAgingData] = useState<any>(null);
  const [agingLoading, setAgingLoading] = useState(false);

  const loadVip = useCallback(async () => {
    if (!storeId) return;
    setVipLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/vip-spending-trend`);
      setVipData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setVipLoading(false); }
  }, [storeId]);

  const loadAging = useCallback(async () => {
    if (!storeId) return;
    setAgingLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/payment-overdue-aging`);
      setAgingData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setAgingLoading(false); }
  }, [storeId]);

  useEffect(() => { loadVip(); loadAging(); }, [loadVip, loadAging]);

  return (
    <div className={styles.vipSpendTab}>
      <ZCard title="VIP 消费趋势">
        {vipLoading ? <ZSkeleton /> : !vipData || vipData.by_level.length === 0 ? <ZEmpty message="暂无VIP数据" /> : (
          <>
            <div className={styles.vipSpendKpi}>
              VIP 总数 <span className={styles.vipSpendVal}>{vipData.total_vip}</span>
            </div>
            <div className={styles.vipLevelList}>
              <div className={styles.vipLevelHeader}>
                <span>VIP等级</span><span>订单数</span><span>总收入¥</span><span>均单¥</span>
              </div>
              {vipData.by_level.map((v: any) => (
                <div key={v.vip_level} className={styles.vipLevelRow}>
                  <span className={styles.vipLevelBadge}>Lv.{v.vip_level}</span>
                  <span>{v.order_count}</span>
                  <span>¥{v.total_revenue_yuan?.toLocaleString()}</span>
                  <span className={styles.vipAvgOrder}>¥{v.avg_order_yuan?.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </ZCard>
      <ZCard title="欠款账龄分析">
        {agingLoading ? <ZSkeleton /> : !agingData ? <ZEmpty message="暂无数据" /> : agingData.total_overdue === 0 ? (
          <div className={styles.agingAllPaid}>✓ 无欠款订单</div>
        ) : (
          <>
            <div className={styles.agingKpiRow}>
              <div className={styles.agingKpi}>
                <div className={styles.agingKpiVal}>{agingData.total_overdue}</div>
                <div className={styles.agingKpiLabel}>欠款订单</div>
              </div>
              <div className={`${styles.agingKpi} ${styles.agingRed}`}>
                <div className={styles.agingKpiVal}>¥{agingData.total_overdue_yuan?.toLocaleString()}</div>
                <div className={styles.agingKpiLabel}>欠款总额</div>
              </div>
            </div>
            <div className={styles.agingBucketList}>
              {agingData.buckets.map((b: any) => (
                <div key={b.bucket} className={styles.agingBucketRow}>
                  <span className={styles.agingBucketLabel}>{b.bucket}</span>
                  <div className={styles.agingBucketTrack}>
                    <div className={styles.agingBucketFill} style={{ width: `${b.pct}%` }} />
                  </div>
                  <span className={styles.agingBucketStat}>{b.count} 单 ¥{b.amount_yuan?.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </ZCard>
    </div>
  );
}

// Phase 34 Tab 1 — LoyaltyRedemptionTab「积分兑换&菜单升级」
function LoyaltyRedemptionTab() {
  const { storeId } = useStore();
  const [loyaltyData, setLoyaltyData] = useState<any>(null);
  const [upgradeData, setUpgradeData] = useState<any>(null);
  const [channelData, setChannelData] = useState<any>(null);
  const [lLoading, setLLoading] = useState(false);
  const [uLoading, setULoading] = useState(false);
  const [cLoading, setCLoading] = useState(false);

  const loadLoyalty = useCallback(async () => {
    if (!storeId) return;
    setLLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/loyalty-points-redemption-rate`);
      setLoyaltyData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLLoading(false); }
  }, [storeId]);

  const loadUpgrade = useCallback(async () => {
    if (!storeId) return;
    setULoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/menu-upgrade-rate`);
      setUpgradeData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setULoading(false); }
  }, [storeId]);

  const loadChannel = useCallback(async () => {
    if (!storeId) return;
    setCLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/channel-conversion-funnel`);
      setChannelData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setCLoading(false); }
  }, [storeId]);

  useEffect(() => { loadLoyalty(); loadUpgrade(); loadChannel(); }, [loadLoyalty, loadUpgrade, loadChannel]);

  return (
    <div className={styles.loyaltyTab}>
      <ZCard title="积分兑换率">
        {lLoading ? <ZSkeleton /> : !loyaltyData ? <ZEmpty message="暂无数据" /> : (
          <div className={styles.loyaltyKpiRow}>
            <div className={styles.loyaltyKpi}>
              <div className={styles.loyaltyKpiVal}>{loyaltyData.total_customers}</div>
              <div className={styles.loyaltyKpiLabel}>客户总数</div>
            </div>
            <div className={`${styles.loyaltyKpi} ${styles.loyaltyAccent}`}>
              <div className={styles.loyaltyKpiVal}>{loyaltyData.redemption_rate_pct ?? '—'}%</div>
              <div className={styles.loyaltyKpiLabel}>兑换率</div>
            </div>
            <div className={styles.loyaltyKpi}>
              <div className={styles.loyaltyKpiVal}>{loyaltyData.avg_points_redeemed ?? '—'}</div>
              <div className={styles.loyaltyKpiLabel}>均兑积分</div>
            </div>
          </div>
        )}
      </ZCard>
      <ZCard title="菜单升级率">
        {uLoading ? <ZSkeleton /> : !upgradeData ? <ZEmpty message="暂无数据" /> : (
          <div className={styles.upgradeKpiRow}>
            <div className={styles.upgradeKpi}>
              <div className={styles.upgradeKpiVal}>{upgradeData.total_pkg_orders}</div>
              <div className={styles.upgradeKpiLabel}>套餐订单数</div>
            </div>
            <div className={`${styles.upgradeKpi} ${styles.upgradeAccent}`}>
              <div className={styles.upgradeKpiVal}>{upgradeData.upgrade_rate_pct ?? '—'}%</div>
              <div className={styles.upgradeKpiLabel}>升级率</div>
            </div>
            <div className={styles.upgradeKpi}>
              <div className={styles.upgradeKpiVal}>¥{upgradeData.avg_upgrade_yuan ?? '—'}</div>
              <div className={styles.upgradeKpiLabel}>均升级金额</div>
            </div>
          </div>
        )}
      </ZCard>
      <ZCard title="渠道转化漏斗">
        {cLoading ? <ZSkeleton /> : !channelData || channelData.channels?.length === 0 ? <ZEmpty message="暂无渠道数据" /> : (
          <>
            <div className={styles.channelBest}>
              最佳渠道 <ZBadge label={channelData.best_channel} variant="success" />
            </div>
            <div className={styles.channelList}>
              <div className={styles.channelHeader}>
                <span>渠道</span><span>总线索</span><span>成交</span><span>转化率</span>
              </div>
              {channelData.channels.map((c: any) => (
                <div key={c.channel} className={styles.channelRow}>
                  <span>{c.channel}</span>
                  <span>{c.total}</span>
                  <span>{c.signed}</span>
                  <span className={styles.channelRate}>{c.conversion_rate_pct ?? '—'}%</span>
                </div>
              ))}
            </div>
          </>
        )}
      </ZCard>
    </div>
  );
}

// Phase 34 Tab 2 — ForecastAccuracyTab「预测准确率&员工热力图」
function ForecastAccuracyTab() {
  const { storeId } = useStore();
  const [forecastData, setForecastData] = useState<any>(null);
  const [heatmapData, setHeatmapData] = useState<any>(null);
  const [ltData, setLtData] = useState<any>(null);
  const [fLoading, setFLoading] = useState(false);
  const [hLoading, setHLoading] = useState(false);
  const [ltLoading, setLtLoading] = useState(false);

  const loadForecast = useCallback(async () => {
    if (!storeId) return;
    setFLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/banquet-forecast-accuracy`);
      setForecastData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setFLoading(false); }
  }, [storeId]);

  const loadHeatmap = useCallback(async () => {
    if (!storeId) return;
    setHLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/staff-utilization-heatmap`);
      setHeatmapData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setHLoading(false); }
  }, [storeId]);

  const loadLt = useCallback(async () => {
    if (!storeId) return;
    setLtLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/customer-lifetime-event-count`);
      setLtData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLtLoading(false); }
  }, [storeId]);

  useEffect(() => { loadForecast(); loadHeatmap(); loadLt(); }, [loadForecast, loadHeatmap, loadLt]);

  return (
    <div className={styles.forecastTab}>
      <ZCard title="收入预测准确率">
        {fLoading ? <ZSkeleton /> : !forecastData || forecastData.monthly?.length === 0 ? <ZEmpty message="暂无目标数据" /> : (
          <>
            <div className={styles.forecastKpiRow}>
              <div className={`${styles.forecastKpi} ${styles.forecastAccent}`}>
                <div className={styles.forecastKpiVal}>{forecastData.avg_accuracy_pct ?? '—'}%</div>
                <div className={styles.forecastKpiLabel}>平均准确率</div>
              </div>
              <div className={styles.forecastKpi}>
                <div className={styles.forecastKpiVal}>{forecastData.avg_deviation_pct != null ? (forecastData.avg_deviation_pct > 0 ? '+' : '') + forecastData.avg_deviation_pct + '%' : '—'}</div>
                <div className={styles.forecastKpiLabel}>平均偏差</div>
              </div>
            </div>
            <div className={styles.forecastList}>
              <div className={styles.forecastHeader}>
                <span>月份</span><span>目标¥</span><span>实际¥</span><span>准确率</span>
              </div>
              {forecastData.monthly.map((m: any) => (
                <div key={`${m.year}-${m.month}`} className={`${styles.forecastRow} ${m.accuracy_pct && m.accuracy_pct >= 95 ? styles.forecastGood : ''}`}>
                  <span>{m.year}/{String(m.month).padStart(2, '0')}</span>
                  <span>¥{m.target_yuan?.toLocaleString()}</span>
                  <span>¥{m.actual_yuan?.toLocaleString()}</span>
                  <span className={styles.forecastAcc}>{m.accuracy_pct ?? '—'}%</span>
                </div>
              ))}
            </div>
          </>
        )}
      </ZCard>
      <ZCard title="员工任务热力图（峰值星期）">
        {hLoading ? <ZSkeleton /> : !heatmapData || heatmapData.staff?.length === 0 ? <ZEmpty message="暂无员工任务数据" /> : (
          <div className={styles.heatmapList}>
            <div className={styles.heatmapHeader}>
              <span>员工</span><span>总任务</span><span>峰值日</span>
            </div>
            {heatmapData.staff.map((s: any) => (
              <div key={s.user_id} className={styles.heatmapRow}>
                <span className={styles.heatmapId}>{s.user_id}</span>
                <span>{s.total_tasks}</span>
                <span className={styles.heatmapPeak}>{s.peak_weekday}</span>
              </div>
            ))}
          </div>
        )}
      </ZCard>
      <ZCard title="客户全生命周期宴会次数">
        {ltLoading ? <ZSkeleton /> : !ltData ? <ZEmpty message="暂无数据" /> : (
          <>
            <div className={styles.ltKpiRow}>
              <div className={styles.ltKpi}>
                <div className={styles.ltKpiVal}>{ltData.avg_events ?? '—'}</div>
                <div className={styles.ltKpiLabel}>平均次数</div>
              </div>
              <div className={styles.ltKpi}>
                <div className={styles.ltKpiVal}>{ltData.median_events ?? '—'}</div>
                <div className={styles.ltKpiLabel}>中位数</div>
              </div>
              <div className={styles.ltKpi}>
                <div className={styles.ltKpiVal}>{ltData.total_customers}</div>
                <div className={styles.ltKpiLabel}>客户数</div>
              </div>
            </div>
            <div className={styles.ltDistList}>
              {(ltData.distribution || []).map((b: any) => (
                <div key={b.bucket} className={styles.ltDistRow}>
                  <span className={styles.ltDistLabel}>{b.bucket}</span>
                  <div className={styles.ltDistTrack}>
                    <div className={styles.ltDistFill} style={{ width: `${b.pct}%` }} />
                  </div>
                  <span className={styles.ltDistStat}>{b.count}人 ({b.pct}%)</span>
                </div>
              ))}
            </div>
          </>
        )}
      </ZCard>
    </div>
  );
}

// Phase 35 Tab 1 — DepositRefundTab「定金退款&赢单比&VIP留存」
function DepositRefundTab() {
  const { storeId } = useStore();
  const [refundData, setRefundData] = useState<any>(null);
  const [ratioData, setRatioData] = useState<any>(null);
  const [retData, setRetData] = useState<any>(null);
  const [rLoading, setRLoading] = useState(false);
  const [wLoading, setWLoading] = useState(false);
  const [vLoading, setVLoading] = useState(false);

  const loadRefund = useCallback(async () => {
    if (!storeId) return;
    setRLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/deposit-refund-rate`);
      setRefundData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setRLoading(false); }
  }, [storeId]);

  const loadRatio = useCallback(async () => {
    if (!storeId) return;
    setWLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/lead-win-loss-ratio`);
      setRatioData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setWLoading(false); }
  }, [storeId]);

  const loadRet = useCallback(async () => {
    if (!storeId) return;
    setVLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/vip-retention-rate`);
      setRetData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setVLoading(false); }
  }, [storeId]);

  useEffect(() => { loadRefund(); loadRatio(); loadRet(); }, [loadRefund, loadRatio, loadRet]);

  return (
    <div className={styles.depositTab}>
      <ZCard title="定金退款率">
        {rLoading ? <ZSkeleton /> : !refundData ? <ZEmpty message="暂无数据" /> : (
          <div className={styles.depositKpiRow}>
            <div className={styles.depositKpi}>
              <div className={styles.depositKpiVal}>{refundData.total_cancelled}</div>
              <div className={styles.depositKpiLabel}>取消订单</div>
            </div>
            <div className={`${styles.depositKpi} ${styles.depositRed}`}>
              <div className={styles.depositKpiVal}>{refundData.refund_rate_pct ?? '—'}%</div>
              <div className={styles.depositKpiLabel}>定金退款率</div>
            </div>
            <div className={styles.depositKpi}>
              <div className={styles.depositKpiVal}>¥{refundData.avg_deposit_yuan ?? '—'}</div>
              <div className={styles.depositKpiLabel}>均退定金</div>
            </div>
          </div>
        )}
      </ZCard>
      <ZCard title="线索赢单/输单比">
        {wLoading ? <ZSkeleton /> : !ratioData ? <ZEmpty message="暂无数据" /> : (
          <div className={styles.winlossKpiRow}>
            <div className={`${styles.winlossKpi} ${styles.winGreen}`}>
              <div className={styles.winlossKpiVal}>{ratioData.won}</div>
              <div className={styles.winlossKpiLabel}>赢单</div>
            </div>
            <div className={`${styles.winlossKpi} ${styles.winRed}`}>
              <div className={styles.winlossKpiVal}>{ratioData.lost}</div>
              <div className={styles.winlossKpiLabel}>输单</div>
            </div>
            <div className={`${styles.winlossKpi} ${styles.winAccent}`}>
              <div className={styles.winlossKpiVal}>{ratioData.win_loss_ratio ?? '—'}</div>
              <div className={styles.winlossKpiLabel}>赢/输比</div>
            </div>
            <div className={styles.winlossKpi}>
              <div className={styles.winlossKpiVal}>{ratioData.win_rate_pct ?? '—'}%</div>
              <div className={styles.winlossKpiLabel}>赢单率</div>
            </div>
          </div>
        )}
      </ZCard>
      <ZCard title="VIP 客户留存率">
        {vLoading ? <ZSkeleton /> : !retData ? <ZEmpty message="暂无VIP数据" /> : (
          <>
            <div className={styles.retKpiRow}>
              <div className={styles.retKpi}>
                <div className={styles.retKpiVal}>{retData.total_vip}</div>
                <div className={styles.retKpiLabel}>VIP总数</div>
              </div>
              <div className={`${styles.retKpi} ${styles.retAccent}`}>
                <div className={styles.retKpiVal}>{retData.retention_rate_pct ?? '—'}%</div>
                <div className={styles.retKpiLabel}>留存率</div>
              </div>
            </div>
            {(retData.by_level || []).length > 0 && (
              <div className={styles.retLevelList}>
                <div className={styles.retLevelHeader}>
                  <span>VIP等级</span><span>总数</span><span>留存</span><span>留存率</span>
                </div>
                {retData.by_level.map((l: any) => (
                  <div key={l.vip_level} className={styles.retLevelRow}>
                    <span className={styles.retLevelBadge}>Lv.{l.vip_level}</span>
                    <span>{l.total}</span>
                    <span>{l.retained}</span>
                    <span className={styles.retRate}>{l.retention_rate_pct}%</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </ZCard>
    </div>
  );
}

// Phase 35 Tab 2 — SeasonalRevenueTab「季节收入指数&复购间隔&停用率」
function SeasonalRevenueTab() {
  const { storeId } = useStore();
  const [seasonData, setSeasonData] = useState<any>(null);
  const [intervalData, setIntervalData] = useState<any>(null);
  const [downtimeData, setDowntimeData] = useState<any>(null);
  const [sLoading, setSLoading] = useState(false);
  const [iLoading, setILoading] = useState(false);
  const [dLoading, setDLoading] = useState(false);

  const loadSeason = useCallback(async () => {
    if (!storeId) return;
    setSLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/seasonal-revenue-index`);
      setSeasonData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setSLoading(false); }
  }, [storeId]);

  const loadInterval = useCallback(async () => {
    if (!storeId) return;
    setILoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/banquet-repeat-interval`);
      setIntervalData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setILoading(false); }
  }, [storeId]);

  const loadDowntime = useCallback(async () => {
    if (!storeId) return;
    setDLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/hall-maintenance-downtime`);
      setDowntimeData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setDLoading(false); }
  }, [storeId]);

  useEffect(() => { loadSeason(); loadInterval(); loadDowntime(); }, [loadSeason, loadInterval, loadDowntime]);

  const MONTH_NAMES = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];

  return (
    <div className={styles.seasonalRevTab}>
      <ZCard title="季节收入指数">
        {sLoading ? <ZSkeleton /> : !seasonData || seasonData.monthly?.length === 0 ? <ZEmpty message="暂无数据" /> : (
          <>
            <div className={styles.seasonRevKpi}>
              峰值月 <strong>{seasonData.peak_month ? MONTH_NAMES[seasonData.peak_month - 1] : '—'}</strong>
              &nbsp;&nbsp;低谷月 <strong>{seasonData.trough_month ? MONTH_NAMES[seasonData.trough_month - 1] : '—'}</strong>
            </div>
            <div className={styles.seasonRevBars}>
              {seasonData.monthly.filter((m: any) => m.order_count > 0).map((m: any) => (
                <div key={m.month} className={`${styles.seasonRevBar} ${m.month === seasonData.peak_month ? styles.seasonRevPeak : ''}`}>
                  <div className={styles.seasonRevBarTrack}>
                    <div className={styles.seasonRevBarFill} style={{ height: `${Math.min((m.seasonal_index || 0) * 50, 100)}%` }} />
                  </div>
                  <div className={styles.seasonRevBarLabel}>{MONTH_NAMES[m.month - 1]}</div>
                  <div className={styles.seasonRevBarIdx}>{m.seasonal_index ?? '—'}</div>
                </div>
              ))}
            </div>
          </>
        )}
      </ZCard>
      <ZCard title="宴会复购间隔">
        {iLoading ? <ZSkeleton /> : !intervalData ? <ZEmpty message="暂无数据" /> : (
          <div className={styles.intervalKpiRow}>
            <div className={styles.intervalKpi}>
              <div className={styles.intervalKpiVal}>{intervalData.total_repeat_customers}</div>
              <div className={styles.intervalKpiLabel}>复购客户数</div>
            </div>
            <div className={`${styles.intervalKpi} ${styles.intervalAccent}`}>
              <div className={styles.intervalKpiVal}>{intervalData.avg_interval_days ?? '—'}</div>
              <div className={styles.intervalKpiLabel}>均间隔(天)</div>
            </div>
            <div className={styles.intervalKpi}>
              <div className={styles.intervalKpiVal}>{intervalData.median_interval_days ?? '—'}</div>
              <div className={styles.intervalKpiLabel}>中位间隔(天)</div>
            </div>
          </div>
        )}
      </ZCard>
      <ZCard title="厅房停用率">
        {dLoading ? <ZSkeleton /> : !downtimeData ? <ZEmpty message="暂无数据" /> : (
          <>
            <div className={styles.downtimeKpiRow}>
              <div className={styles.downtimeKpi}>
                <div className={styles.downtimeKpiVal}>{downtimeData.total_halls}</div>
                <div className={styles.downtimeKpiLabel}>厅房总数</div>
              </div>
              <div className={`${styles.downtimeKpi} ${styles.downtimeRed}`}>
                <div className={styles.downtimeKpiVal}>{downtimeData.downtime_rate_pct ?? '—'}%</div>
                <div className={styles.downtimeKpiLabel}>停用率</div>
              </div>
            </div>
            <div className={styles.downtimeHallList}>
              {(downtimeData.halls || []).map((h: any) => (
                <div key={h.hall_id} className={`${styles.downtimeHallRow} ${!h.is_active ? styles.downtimeInactive : ''}`}>
                  <span>{h.name}</span>
                  <ZBadge label={h.is_active ? '运营中' : '停用'} variant={h.is_active ? 'success' : 'error'} />
                </div>
              ))}
            </div>
          </>
        )}
      </ZCard>
    </div>
  );
}

// Phase 36 Tab 1 — CancellationReasonsTab「取消分析&报价接受率&客户流失」
function CancellationReasonsTab() {
  const { storeId } = useStore();
  const [cancelData, setCancelData] = useState<any>(null);
  const [acceptData, setAcceptData] = useState<any>(null);
  const [churnData, setChurnData] = useState<any>(null);
  const [c1Loading, setC1Loading] = useState(false);
  const [c2Loading, setC2Loading] = useState(false);
  const [c3Loading, setC3Loading] = useState(false);

  const loadCancel = useCallback(async () => {
    if (!storeId) return;
    setC1Loading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/banquet-cancellation-reasons`);
      setCancelData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setC1Loading(false); }
  }, [storeId]);

  const loadAccept = useCallback(async () => {
    if (!storeId) return;
    setC2Loading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/quote-acceptance-rate`);
      setAcceptData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setC2Loading(false); }
  }, [storeId]);

  const loadChurn = useCallback(async () => {
    if (!storeId) return;
    setC3Loading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/customer-churn-risk`);
      setChurnData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setC3Loading(false); }
  }, [storeId]);

  useEffect(() => { loadCancel(); loadAccept(); loadChurn(); }, [loadCancel, loadAccept, loadChurn]);

  return (
    <div className={styles.cancelTab}>
      <ZCard title="取消订单分析">
        {c1Loading ? <ZSkeleton /> : !cancelData || cancelData.total_cancelled === 0 ? <ZEmpty message="暂无取消订单" /> : (
          <>
            <div className={styles.cancelKpiRow}>
              <div className={`${styles.cancelKpi} ${styles.cancelRed}`}>
                <div className={styles.cancelKpiVal}>{cancelData.total_cancelled}</div>
                <div className={styles.cancelKpiLabel}>取消总数</div>
              </div>
              <div className={styles.cancelKpi}>
                <div className={styles.cancelKpiVal}>¥{cancelData.total_deposit_lost_yuan?.toLocaleString()}</div>
                <div className={styles.cancelKpiLabel}>定金损失</div>
              </div>
            </div>
            <div className={styles.cancelTypeList}>
              {cancelData.by_type.map((t: any) => (
                <div key={t.banquet_type} className={`${styles.cancelTypeRow} ${t.banquet_type === cancelData.top_cancel_type ? styles.cancelTopRow : ''}`}>
                  <span className={styles.cancelTypeName}>{t.banquet_type}</span>
                  <div className={styles.cancelTypeTrack}>
                    <div className={styles.cancelTypeFill} style={{ width: `${t.pct}%` }} />
                  </div>
                  <span className={styles.cancelTypeStat}>{t.count}单 ({t.pct}%)</span>
                </div>
              ))}
            </div>
          </>
        )}
      </ZCard>
      <ZCard title="报价接受率">
        {c2Loading ? <ZSkeleton /> : !acceptData ? <ZEmpty message="暂无数据" /> : (
          <div className={styles.acceptKpiRow}>
            <div className={styles.acceptKpi}>
              <div className={styles.acceptKpiVal}>{acceptData.total_quoted}</div>
              <div className={styles.acceptKpiLabel}>进入报价漏斗</div>
            </div>
            <div className={`${styles.acceptKpi} ${styles.acceptAccent}`}>
              <div className={styles.acceptKpiVal}>{acceptData.acceptance_rate_pct ?? '—'}%</div>
              <div className={styles.acceptKpiLabel}>接受率</div>
            </div>
            <div className={styles.acceptKpi}>
              <div className={styles.acceptKpiVal}>{acceptData.won_count}</div>
              <div className={styles.acceptKpiLabel}>成交</div>
            </div>
          </div>
        )}
      </ZCard>
      <ZCard title="客户流失风险">
        {c3Loading ? <ZSkeleton /> : !churnData ? <ZEmpty message="暂无数据" /> : (
          <div className={styles.churnKpiRow}>
            <div className={styles.churnKpi}>
              <div className={styles.churnKpiVal}>{churnData.total_customers}</div>
              <div className={styles.churnKpiLabel}>客户总数</div>
            </div>
            <div className={`${styles.churnKpi} ${styles.churnRed}`}>
              <div className={styles.churnKpiVal}>{churnData.at_risk_count}</div>
              <div className={styles.churnKpiLabel}>高风险客户</div>
            </div>
            <div className={styles.churnKpi}>
              <div className={styles.churnKpiVal}>{churnData.churn_risk_pct ?? '—'}%</div>
              <div className={styles.churnKpiLabel}>流失风险率</div>
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

// Phase 36 Tab 2 — WeekdayPatternTab「星期分布&套餐贡献&员工超时」
function WeekdayPatternTab() {
  const { storeId } = useStore();
  const [wdData, setWdData] = useState<any>(null);
  const [pkgData, setPkgData] = useState<any>(null);
  const [otData, setOtData] = useState<any>(null);
  const [w1Loading, setW1Loading] = useState(false);
  const [w2Loading, setW2Loading] = useState(false);
  const [w3Loading, setW3Loading] = useState(false);

  const loadWd = useCallback(async () => {
    if (!storeId) return;
    setW1Loading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/banquet-day-of-week-pattern`);
      setWdData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setW1Loading(false); }
  }, [storeId]);

  const loadPkg = useCallback(async () => {
    if (!storeId) return;
    setW2Loading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/package-revenue-contribution`);
      setPkgData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setW2Loading(false); }
  }, [storeId]);

  const loadOt = useCallback(async () => {
    if (!storeId) return;
    setW3Loading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/staff-overtime-rate`);
      setOtData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setW3Loading(false); }
  }, [storeId]);

  useEffect(() => { loadWd(); loadPkg(); loadOt(); }, [loadWd, loadPkg, loadOt]);

  return (
    <div className={styles.weekdayTab}>
      <ZCard title="宴会星期分布">
        {w1Loading ? <ZSkeleton /> : !wdData || wdData.by_weekday?.length === 0 ? <ZEmpty message="暂无数据" /> : (
          <>
            <div className={styles.wdPeak}>峰值 <strong>{wdData.peak_weekday}</strong> &nbsp; 总计 {wdData.total_orders} 单</div>
            <div className={styles.wdBars}>
              {(wdData.by_weekday || []).map((d: any) => {
                const maxCount = Math.max(...(wdData.by_weekday || []).map((x: any) => x.order_count));
                const pct = maxCount > 0 ? (d.order_count / maxCount) * 100 : 0;
                return (
                  <div key={d.weekday} className={`${styles.wdBar} ${d.weekday === wdData.peak_weekday ? styles.wdPeakBar : ''}`}>
                    <div className={styles.wdBarTrack}>
                      <div className={styles.wdBarFill} style={{ height: `${pct}%` }} />
                    </div>
                    <div className={styles.wdBarLabel}>{d.weekday.replace('周', '')}</div>
                    <div className={styles.wdBarCount}>{d.order_count}</div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </ZCard>
      <ZCard title="套餐收入贡献率">
        {w2Loading ? <ZSkeleton /> : !pkgData ? <ZEmpty message="暂无数据" /> : (
          <div className={styles.pkgContribRow}>
            <div className={styles.pkgContribKpi}>
              <div className={styles.pkgContribVal}>{pkgData.total_orders}</div>
              <div className={styles.pkgContribLabel}>总订单</div>
            </div>
            <div className={`${styles.pkgContribKpi} ${styles.pkgContribAccent}`}>
              <div className={styles.pkgContribVal}>{pkgData.pkg_revenue_pct ?? '—'}%</div>
              <div className={styles.pkgContribLabel}>套餐收入占比</div>
            </div>
            <div className={styles.pkgContribKpi}>
              <div className={styles.pkgContribVal}>¥{pkgData.pkg_revenue_yuan?.toLocaleString()}</div>
              <div className={styles.pkgContribLabel}>套餐收入</div>
            </div>
          </div>
        )}
      </ZCard>
      <ZCard title="员工任务超时率">
        {w3Loading ? <ZSkeleton /> : !otData ? <ZEmpty message="暂无数据" /> : (
          <div className={styles.otKpiRow}>
            <div className={styles.otKpi}>
              <div className={styles.otKpiVal}>{otData.total_completed}</div>
              <div className={styles.otKpiLabel}>已完成任务</div>
            </div>
            <div className={`${styles.otKpi} ${styles.otRed}`}>
              <div className={styles.otKpiVal}>{otData.overtime_rate_pct ?? '—'}%</div>
              <div className={styles.otKpiLabel}>超时率</div>
            </div>
            <div className={styles.otKpi}>
              <div className={styles.otKpiVal}>{otData.overtime_count}</div>
              <div className={styles.otKpiLabel}>超时次数</div>
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

// Phase 37 Tab 1 — RevenuePerTableTab「桌均收入&来源量&人均消费」
function RevenuePerTableTab() {
  const { storeId } = useStore();
  const [rptData, setRptData] = useState<any>(null);
  const [srcData, setSrcData] = useState<any>(null);
  const [spendData, setSpendData] = useState<any>(null);
  const [r1L, setR1L] = useState(false);
  const [r2L, setR2L] = useState(false);
  const [r3L, setR3L] = useState(false);

  const loadRpt = useCallback(async () => {
    if (!storeId) return; setR1L(true);
    try { const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/banquet-revenue-per-table`); setRptData(r.data); }
    catch (e) { handleApiError(e); } finally { setR1L(false); }
  }, [storeId]);

  const loadSrc = useCallback(async () => {
    if (!storeId) return; setR2L(true);
    try { const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/lead-source-volume`); setSrcData(r.data); }
    catch (e) { handleApiError(e); } finally { setR2L(false); }
  }, [storeId]);

  const loadSpend = useCallback(async () => {
    if (!storeId) return; setR3L(true);
    try { const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/customer-average-spend`); setSpendData(r.data); }
    catch (e) { handleApiError(e); } finally { setR3L(false); }
  }, [storeId]);

  useEffect(() => { loadRpt(); loadSrc(); loadSpend(); }, [loadRpt, loadSrc, loadSpend]);

  return (
    <div className={styles.rptTab}>
      <ZCard title="各宴会类型桌均收入">
        {r1L ? <ZSkeleton /> : !rptData ? <ZEmpty message="暂无数据" /> : (
          <>
            <div className={styles.rptOverall}>
              总体桌均 <span className={styles.rptOverallVal}>¥{rptData.overall_rev_per_table ?? '—'}</span>
            </div>
            <div className={styles.rptList}>
              <div className={styles.rptHeader}><span>类型</span><span>桌数</span><span>总收入</span><span>桌均¥</span></div>
              {(rptData.by_type || []).map((t: any) => (
                <div key={t.banquet_type} className={styles.rptRow}>
                  <span>{t.banquet_type}</span>
                  <span>{t.total_tables}</span>
                  <span>¥{t.total_revenue_yuan?.toLocaleString()}</span>
                  <span className={styles.rptVal}>¥{t.rev_per_table_yuan}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </ZCard>
      <ZCard title="线索来源量">
        {r2L ? <ZSkeleton /> : !srcData || srcData.total_leads === 0 ? <ZEmpty message="暂无线索数据" /> : (
          <>
            <div className={styles.srcVolKpi}>
              总线索 <span className={styles.srcVolVal}>{srcData.total_leads}</span>
              &nbsp;最多来源 <strong>{srcData.top_source}</strong>
            </div>
            <div className={styles.srcVolList}>
              {(srcData.sources || []).map((s: any) => (
                <div key={s.channel} className={styles.srcVolRow}>
                  <span className={styles.srcVolCh}>{s.channel}</span>
                  <div className={styles.srcVolTrack}>
                    <div className={styles.srcVolFill} style={{ width: `${s.pct}%` }} />
                  </div>
                  <span className={styles.srcVolStat}>{s.count}条 ({s.pct}%)</span>
                </div>
              ))}
            </div>
          </>
        )}
      </ZCard>
      <ZCard title="客户人均/桌均消费">
        {r3L ? <ZSkeleton /> : !spendData ? <ZEmpty message="暂无数据" /> : (
          <div className={styles.spendKpiRow}>
            <div className={styles.spendKpi}>
              <div className={styles.spendKpiVal}>¥{spendData.avg_spend_per_person_yuan ?? '—'}</div>
              <div className={styles.spendKpiLabel}>人均消费</div>
            </div>
            <div className={`${styles.spendKpi} ${styles.spendAccent}`}>
              <div className={styles.spendKpiVal}>¥{spendData.avg_spend_per_table_yuan ?? '—'}</div>
              <div className={styles.spendKpiLabel}>桌均消费</div>
            </div>
            <div className={styles.spendKpi}>
              <div className={styles.spendKpiVal}>{spendData.total_people?.toLocaleString()}</div>
              <div className={styles.spendKpiLabel}>总客数</div>
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

// Phase 37 Tab 2 — ReviewSentimentTab「评价情感&任务速度&月度增长」
function ReviewSentimentTab() {
  const { storeId } = useStore();
  const [sentData, setSentData] = useState<any>(null);
  const [speedData, setSpeedData] = useState<any>(null);
  const [growthData, setGrowthData] = useState<any>(null);
  const [s1L, setS1L] = useState(false);
  const [s2L, setS2L] = useState(false);
  const [s3L, setS3L] = useState(false);

  const loadSent = useCallback(async () => {
    if (!storeId) return; setS1L(true);
    try { const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/review-sentiment-breakdown`); setSentData(r.data); }
    catch (e) { handleApiError(e); } finally { setS1L(false); }
  }, [storeId]);

  const loadSpeed = useCallback(async () => {
    if (!storeId) return; setS2L(true);
    try { const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/task-completion-speed`); setSpeedData(r.data); }
    catch (e) { handleApiError(e); } finally { setS2L(false); }
  }, [storeId]);

  const loadGrowth = useCallback(async () => {
    if (!storeId) return; setS3L(true);
    try { const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/analytics/monthly-order-growth`); setGrowthData(r.data); }
    catch (e) { handleApiError(e); } finally { setS3L(false); }
  }, [storeId]);

  useEffect(() => { loadSent(); loadSpeed(); loadGrowth(); }, [loadSent, loadSpeed, loadGrowth]);

  return (
    <div className={styles.sentimentTab}>
      <ZCard title="评价情感分布">
        {s1L ? <ZSkeleton /> : !sentData || sentData.total_reviews === 0 ? <ZEmpty message="暂无评价数据" /> : (
          <>
            <div className={styles.sentKpiRow}>
              <div className={`${styles.sentKpi} ${styles.sentGreen}`}>
                <div className={styles.sentKpiVal}>{sentData.positive_pct ?? '—'}%</div>
                <div className={styles.sentKpiLabel}>好评 ({sentData.positive_count})</div>
              </div>
              <div className={styles.sentKpi}>
                <div className={styles.sentKpiVal}>{sentData.neutral_pct ?? '—'}%</div>
                <div className={styles.sentKpiLabel}>中评 ({sentData.neutral_count})</div>
              </div>
              <div className={`${styles.sentKpi} ${styles.sentRed}`}>
                <div className={styles.sentKpiVal}>{sentData.negative_pct ?? '—'}%</div>
                <div className={styles.sentKpiLabel}>差评 ({sentData.negative_count})</div>
              </div>
            </div>
            {sentData.top_improvement_tags?.length > 0 && (
              <div className={styles.sentTagList}>
                <div className={styles.sentTagTitle}>高频改进标签</div>
                {sentData.top_improvement_tags.map((t: any) => (
                  <span key={t.tag} className={styles.sentTag}>{t.tag} ({t.count})</span>
                ))}
              </div>
            )}
          </>
        )}
      </ZCard>
      <ZCard title="任务完成速度">
        {s2L ? <ZSkeleton /> : !speedData ? <ZEmpty message="暂无数据" /> : (
          <div className={styles.speedKpiRow}>
            <div className={styles.speedKpi}>
              <div className={styles.speedKpiVal}>{speedData.avg_hours ?? '—'}h</div>
              <div className={styles.speedKpiLabel}>平均耗时</div>
            </div>
            <div className={styles.speedKpi}>
              <div className={styles.speedKpiVal}>{speedData.median_hours ?? '—'}h</div>
              <div className={styles.speedKpiLabel}>中位耗时</div>
            </div>
            <div className={`${styles.speedKpi} ${styles.speedAccent}`}>
              <div className={styles.speedKpiVal}>{speedData.fast_pct ?? '—'}%</div>
              <div className={styles.speedKpiLabel}>24h内完成</div>
            </div>
          </div>
        )}
      </ZCard>
      <ZCard title="月度订单增长率">
        {s3L ? <ZSkeleton /> : !growthData || growthData.monthly?.length === 0 ? <ZEmpty message="暂无数据" /> : (
          <>
            <div className={styles.growthAvg}>
              均环比 <span className={styles.growthAvgVal}>{growthData.avg_growth_pct != null ? (growthData.avg_growth_pct > 0 ? '+' : '') + growthData.avg_growth_pct + '%' : '—'}</span>
            </div>
            <div className={styles.growthList}>
              <div className={styles.growthHeader}><span>月份</span><span>订单数</span><span>环比</span></div>
              {growthData.monthly.slice(-6).map((m: any) => (
                <div key={`${m.year}-${m.month}`} className={styles.growthRow}>
                  <span>{m.year}/{String(m.month).padStart(2,'0')}</span>
                  <span>{m.order_count}</span>
                  <span className={m.mom_growth_pct != null && m.mom_growth_pct > 0 ? styles.growthPos : styles.growthNeg}>
                    {m.mom_growth_pct != null ? (m.mom_growth_pct > 0 ? '+' : '') + m.mom_growth_pct + '%' : '—'}
                  </span>
                </div>
              ))}
            </div>
          </>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 38: 加购分析 Tab ─── */
function UpsellAnalysisTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [upsellData, setUpsellData]   = useState<any>(null);
  const [capData,    setCapData]      = useState<any>(null);
  const [refData,    setRefData]      = useState<any>(null);
  const [signData,   setSignData]     = useState<any>(null);
  const [loading,    setLoading]      = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [u, c, r, s] = await Promise.all([
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/upsell-success-rate?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/capacity-utilization?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/referral-conversion-rate?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/contract-signing-speed?months=6`),
      ]);
      setUpsellData((u as any).data);
      setCapData((c as any).data);
      setRefData((r as any).data);
      setSignData((s as any).data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={5} />;

  return (
    <div className={styles.upsell38Tab}>
      <ZCard title="加购成功率">
        {!upsellData || upsellData.upsell_rate_pct == null ? <ZEmpty /> : (
          <div className={styles.upsell38KpiRow}>
            <div className={`${styles.upsell38Kpi} ${styles.upsell38Accent}`}>
              <span className={styles.upsell38KpiVal}>{upsellData.upsell_rate_pct}%</span>
              <span className={styles.upsell38KpiLabel}>加购率</span>
            </div>
            <div className={styles.upsell38Kpi}>
              <span className={styles.upsell38KpiVal}>¥{upsellData.avg_upsell_yuan ?? '-'}</span>
              <span className={styles.upsell38KpiLabel}>平均加购额</span>
            </div>
            <div className={styles.upsell38Kpi}>
              <span className={styles.upsell38KpiVal}>{upsellData.upsell_count ?? 0}</span>
              <span className={styles.upsell38KpiLabel}>加购订单数</span>
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="容量利用率">
        {!capData || capData.overall_utilization_pct == null ? <ZEmpty /> : (
          <div className={styles.cap38Tab}>
            <div className={styles.cap38Overall}>
              <span className={styles.cap38OverallVal}>{capData.overall_utilization_pct}%</span>
              <span>综合利用率</span>
            </div>
            <div className={styles.cap38List}>
              <div className={styles.cap38Header}>
                <span style={{flex:2}}>厅房</span>
                <span style={{flex:1}}>预订场次</span>
                <span style={{flex:1}}>利用率</span>
              </div>
              {(capData.halls || []).map((h: any) => (
                <div key={h.hall_id} className={styles.cap38Row}>
                  <span style={{flex:2}}>{h.hall_name}</span>
                  <span style={{flex:1}}>{h.booking_count}</span>
                  <span style={{flex:1, fontWeight:600}}>{h.utilization_pct ?? '-'}%</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="转介绍转化率">
        {!refData || refData.conversion_rate_pct == null ? <ZEmpty /> : (
          <div className={styles.ref38KpiRow}>
            <div className={`${styles.ref38Kpi} ${styles.ref38Accent}`}>
              <span className={styles.ref38KpiVal}>{refData.conversion_rate_pct}%</span>
              <span className={styles.ref38KpiLabel}>转化率</span>
            </div>
            <div className={styles.ref38Kpi}>
              <span className={styles.ref38KpiVal}>{refData.total_referrals}</span>
              <span className={styles.ref38KpiLabel}>转介绍线索</span>
            </div>
            <div className={styles.ref38Kpi}>
              <span className={styles.ref38KpiVal}>{refData.won_count}</span>
              <span className={styles.ref38KpiLabel}>成单数</span>
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="签约速度">
        {!signData || signData.avg_days_to_sign == null ? <ZEmpty /> : (
          <div className={styles.sign38KpiRow}>
            <div className={`${styles.sign38Kpi} ${styles.sign38Accent}`}>
              <span className={styles.sign38KpiVal}>{signData.avg_days_to_sign}天</span>
              <span className={styles.sign38KpiLabel}>平均签约周期</span>
            </div>
            <div className={styles.sign38Kpi}>
              <span className={styles.sign38KpiVal}>{signData.fast_sign_pct}%</span>
              <span className={styles.sign38KpiLabel}>快速签约率(≤14天)</span>
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 38: 收入趋势 Tab ─── */
function RevenueTrendTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [trendData, setTrendData]     = useState<any>(null);
  const [reviewRate, setReviewRate]   = useState<any>(null);
  const [coordData,  setCoordData]    = useState<any>(null);
  const [leadData,   setLeadData]     = useState<any>(null);
  const [loading,    setLoading]      = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [t, r, c, l] = await Promise.all([
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/revenue-trend?months=12`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/post-event-review-rate?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/coordinator-performance?months=3`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/booking-lead-time?months=6`),
      ]);
      setTrendData((t as any).data);
      setReviewRate((r as any).data);
      setCoordData((c as any).data);
      setLeadData((l as any).data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={5} />;

  return (
    <div className={styles.revTrend38Tab}>
      <ZCard title="月度收入趋势">
        {!trendData || !trendData.monthly?.length ? <ZEmpty /> : (
          <>
            <div className={styles.revTrend38KpiRow}>
              <div className={`${styles.revTrend38Kpi} ${styles.revTrend38Accent}`}>
                <span className={styles.revTrend38KpiVal}>¥{trendData.total_revenue_yuan?.toLocaleString()}</span>
                <span className={styles.revTrend38KpiLabel}>累计收入</span>
              </div>
              <div className={styles.revTrend38Kpi}>
                <span className={styles.revTrend38KpiVal}>¥{trendData.avg_monthly_yuan?.toLocaleString()}</span>
                <span className={styles.revTrend38KpiLabel}>月均收入</span>
              </div>
            </div>
            <div className={styles.revTrend38List}>
              <div className={styles.revTrend38Header}>
                <span style={{flex:2}}>月份</span>
                <span style={{flex:2}}>收入(元)</span>
                <span style={{flex:1}}>环比</span>
              </div>
              {(trendData.monthly || []).slice(-6).map((m: any) => (
                <div key={m.month} className={styles.revTrend38Row}>
                  <span style={{flex:2}}>{m.month}</span>
                  <span style={{flex:2}}>¥{m.revenue_yuan?.toLocaleString()}</span>
                  <span style={{flex:1}} className={
                    m.mom_growth_pct == null ? '' :
                    m.mom_growth_pct >= 0 ? styles.revTrend38Pos : styles.revTrend38Neg
                  }>
                    {m.mom_growth_pct == null ? '-' : `${m.mom_growth_pct > 0 ? '+' : ''}${m.mom_growth_pct}%`}
                  </span>
                </div>
              ))}
            </div>
          </>
        )}
      </ZCard>

      <ZCard title="活动后评价率">
        {!reviewRate || reviewRate.review_rate_pct == null ? <ZEmpty /> : (
          <div className={styles.revRate38KpiRow}>
            <div className={`${styles.revRate38Kpi} ${styles.revRate38Accent}`}>
              <span className={styles.revRate38KpiVal}>{reviewRate.review_rate_pct}%</span>
              <span className={styles.revRate38KpiLabel}>评价率</span>
            </div>
            <div className={styles.revRate38Kpi}>
              <span className={styles.revRate38KpiVal}>{reviewRate.reviewed_count}</span>
              <span className={styles.revRate38KpiLabel}>已评价</span>
            </div>
            <div className={styles.revRate38Kpi}>
              <span className={styles.revRate38KpiVal}>{reviewRate.total_completed}</span>
              <span className={styles.revRate38KpiLabel}>总完成单</span>
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="协调员绩效">
        {!coordData || !coordData.coordinators?.length ? <ZEmpty /> : (
          <div className={styles.coord38Tab}>
            {coordData.top_coordinator && (
              <div className={styles.coord38Top}>TOP: {coordData.top_coordinator}</div>
            )}
            <div className={styles.coord38List}>
              <div className={styles.coord38Header}>
                <span style={{flex:2}}>协调员</span>
                <span style={{flex:1}}>完成单数</span>
                <span style={{flex:1}}>平均评分</span>
              </div>
              {(coordData.coordinators || []).map((c: any, i: number) => (
                <div key={i} className={styles.coord38Row}>
                  <span style={{flex:2}}>{c.coordinator}</span>
                  <span style={{flex:1}}>{c.completed_orders}</span>
                  <span style={{flex:1, fontWeight:600}}>{c.avg_rating ?? '-'}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="预订提前期">
        {!leadData || leadData.avg_lead_days == null ? <ZEmpty /> : (
          <div className={styles.leadTime38Tab}>
            <div className={styles.leadTime38Overall}>
              <span className={styles.leadTime38OverallVal}>{leadData.avg_lead_days}天</span>
              <span>平均提前天数</span>
            </div>
            <div className={styles.leadTime38DistList}>
              {(leadData.distribution || []).map((b: any) => (
                <div key={b.bucket} className={styles.leadTime38DistRow}>
                  <span className={styles.leadTime38DistLabel}>{b.bucket}</span>
                  <div className={styles.leadTime38DistTrack}>
                    <div className={styles.leadTime38DistFill} style={{width:`${b.pct}%`}} />
                  </div>
                  <span className={styles.leadTime38DistStat}>{b.count}单 ({b.pct}%)</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 39: 利润率 Tab ─── */
function ProfitMarginTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [marginData,  setMarginData]  = useState<any>(null);
  const [turnData,    setTurnData]    = useState<any>(null);
  const [payData,     setPayData]     = useState<any>(null);
  const [sizeData,    setSizeData]    = useState<any>(null);
  const [loading,     setLoading]     = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [m, t, p, s] = await Promise.all([
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/profit-margin?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/hall-turnover-rate?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/payment-method-breakdown?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/order-size-distribution?months=12`),
      ]);
      setMarginData((m as any).data);
      setTurnData((t as any).data);
      setPayData((p as any).data);
      setSizeData((s as any).data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={5} />;

  return (
    <div className={styles.profitMarginTab}>
      <ZCard title="宴会利润率">
        {!marginData || marginData.profit_margin_pct == null ? <ZEmpty /> : (
          <div className={styles.pmKpiRow}>
            <div className={`${styles.pmKpi} ${styles.pmAccent}`}>
              <span className={styles.pmKpiVal}>{marginData.profit_margin_pct}%</span>
              <span className={styles.pmKpiLabel}>利润率</span>
            </div>
            <div className={styles.pmKpi}>
              <span className={styles.pmKpiVal}>¥{marginData.total_revenue_yuan?.toLocaleString()}</span>
              <span className={styles.pmKpiLabel}>总收入</span>
            </div>
            <div className={styles.pmKpi}>
              <span className={styles.pmKpiVal}>¥{marginData.total_cost_yuan?.toLocaleString()}</span>
              <span className={styles.pmKpiLabel}>总成本</span>
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="厅房翻台率">
        {!turnData || !turnData.halls?.length ? <ZEmpty /> : (
          <div className={styles.turnTab}>
            <div className={styles.turnOverall}>
              综合翻台率 <strong>{turnData.overall_turnover_rate}</strong> 次/天
            </div>
            <div className={styles.turnList}>
              <div className={styles.turnHeader}>
                <span style={{flex:2}}>厅房</span>
                <span style={{flex:1}}>预订场次</span>
                <span style={{flex:1}}>翻台率</span>
              </div>
              {(turnData.halls || []).map((h: any) => (
                <div key={h.hall_id} className={styles.turnRow}>
                  <span style={{flex:2}}>{h.hall_name}</span>
                  <span style={{flex:1}}>{h.booking_count}</span>
                  <span style={{flex:1, fontWeight:600}}>{h.turnover_rate}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="支付方式分析">
        {!payData || !payData.methods?.length ? <ZEmpty /> : (
          <div className={styles.payMethodTab}>
            {payData.top_method && (
              <div className={styles.payMethodTop}>主要支付：{payData.top_method}</div>
            )}
            <div className={styles.payMethodList}>
              {(payData.methods || []).map((m: any) => (
                <div key={m.method} className={styles.payMethodRow}>
                  <span className={styles.payMethodName}>{m.method}</span>
                  <div className={styles.payMethodTrack}>
                    <div className={styles.payMethodFill} style={{width:`${m.pct}%`}} />
                  </div>
                  <span className={styles.payMethodStat}>{m.count}次 ({m.pct}%)</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="订单规模分布">
        {!sizeData || !sizeData.distribution?.length ? <ZEmpty /> : (
          <div className={styles.sizeDistTab}>
            <div className={styles.sizeDistAvg}>
              平均桌数：<strong>{sizeData.avg_tables}</strong> 桌
            </div>
            <div className={styles.sizeDistList}>
              {(sizeData.distribution || []).map((b: any) => (
                <div key={b.bucket} className={styles.sizeDistRow}>
                  <span className={styles.sizeDistLabel}>{b.bucket}</span>
                  <div className={styles.sizeDistTrack}>
                    <div className={styles.sizeDistFill}
                      style={{width:`${Math.round(b.count / sizeData.total_orders * 100)}%`}} />
                  </div>
                  <span className={styles.sizeDistStat}>{b.count}单</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 39: 类型趋势 Tab ─── */
function TypeTrendTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [typeData,   setTypeData]   = useState<any>(null);
  const [respData,   setRespData]   = useState<any>(null);
  const [satData,    setSatData]    = useState<any>(null);
  const [staffData,  setStaffData]  = useState<any>(null);
  const [loading,    setLoading]    = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ty, r, s, st] = await Promise.all([
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/banquet-type-trend?months=12`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/lead-response-time?months=3`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/customer-satisfaction-score?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/staff-task-distribution?months=3`),
      ]);
      setTypeData((ty as any).data);
      setRespData((r as any).data);
      setSatData((s as any).data);
      setStaffData((st as any).data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={5} />;

  return (
    <div className={styles.typeTrend39Tab}>
      <ZCard title="宴会类型趋势">
        {!typeData || !typeData.by_type?.length ? <ZEmpty /> : (
          <div className={styles.tt39List}>
            {typeData.top_type && (
              <div className={styles.tt39Top}>最热类型：{typeData.top_type}</div>
            )}
            <div className={styles.tt39TypeList}>
              <div className={styles.tt39Header}>
                <span style={{flex:2}}>类型</span>
                <span style={{flex:1}}>总单数</span>
              </div>
              {(typeData.by_type || []).map((t: any) => (
                <div key={t.banquet_type} className={styles.tt39Row}>
                  <span style={{flex:2}}>{t.banquet_type}</span>
                  <span style={{flex:1, fontWeight:600}}>{t.total}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="线索响应时间">
        {!respData || respData.avg_response_hours == null ? <ZEmpty /> : (
          <div className={styles.resp39KpiRow}>
            <div className={`${styles.resp39Kpi} ${styles.resp39Accent}`}>
              <span className={styles.resp39KpiVal}>{respData.avg_response_hours}h</span>
              <span className={styles.resp39KpiLabel}>平均响应</span>
            </div>
            <div className={styles.resp39Kpi}>
              <span className={styles.resp39KpiVal}>{respData.fast_response_pct}%</span>
              <span className={styles.resp39KpiLabel}>2h内响应率</span>
            </div>
            <div className={styles.resp39Kpi}>
              <span className={styles.resp39KpiVal}>{respData.responded_leads ?? 0}</span>
              <span className={styles.resp39KpiLabel}>已响应线索</span>
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="客户满意度趋势">
        {!satData || satData.overall_score == null ? <ZEmpty /> : (
          <div className={styles.sat39Tab}>
            <div className={styles.sat39Overall}>
              <span className={styles.sat39OverallVal}>{satData.overall_score}</span>
              <span>综合满意度（满分100）</span>
            </div>
            <div className={styles.sat39List}>
              <div className={styles.sat39Header}>
                <span style={{flex:2}}>月份</span>
                <span style={{flex:1}}>评价数</span>
                <span style={{flex:1}}>平均分</span>
              </div>
              {(satData.monthly || []).slice(-4).map((m: any) => (
                <div key={m.month} className={styles.sat39Row}>
                  <span style={{flex:2}}>{m.month}</span>
                  <span style={{flex:1}}>{m.count}</span>
                  <span style={{flex:1, fontWeight:600}}>{m.avg_score}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="员工任务分布">
        {!staffData || !staffData.staff?.length ? <ZEmpty /> : (
          <div className={styles.staff39Tab}>
            {staffData.busiest_staff && (
              <div className={styles.staff39Top}>最忙：{staffData.busiest_staff}</div>
            )}
            <div className={styles.staff39List}>
              <div className={styles.staff39Header}>
                <span style={{flex:2}}>员工ID</span>
                <span style={{flex:1}}>任务数</span>
                <span style={{flex:1}}>完成率</span>
              </div>
              {(staffData.staff || []).map((s: any) => (
                <div key={s.user_id} className={styles.staff39Row}>
                  <span style={{flex:2, fontSize:12}}>{s.user_id}</span>
                  <span style={{flex:1}}>{s.total_tasks}</span>
                  <span style={{flex:1, fontWeight:600}}>{s.completion_pct ?? '-'}%</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 40: 复购分析 Tab ─── */
function ReorderAnalysisTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [convData,   setConvData]   = useState<any>(null);
  const [reordData,  setReordData]  = useState<any>(null);
  const [ageData,    setAgeData]    = useState<any>(null);
  const [cancelData, setCancelData] = useState<any>(null);
  const [loading,    setLoading]    = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [c, r, a, cl] = await Promise.all([
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/booking-conversion-rate?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/customer-reorder-rate?months=12`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/lead-age-distribution?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/cancellation-lead-time?months=6`),
      ]);
      setConvData((c as any).data);
      setReordData((r as any).data);
      setAgeData((a as any).data);
      setCancelData((cl as any).data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={5} />;

  return (
    <div className={styles.reorder40Tab}>
      <ZCard title="线索转订单转化率">
        {!convData || convData.conversion_rate_pct == null ? <ZEmpty /> : (
          <div className={styles.conv40KpiRow}>
            <div className={`${styles.conv40Kpi} ${styles.conv40Accent}`}>
              <span className={styles.conv40KpiVal}>{convData.conversion_rate_pct}%</span>
              <span className={styles.conv40KpiLabel}>转化率</span>
            </div>
            <div className={styles.conv40Kpi}>
              <span className={styles.conv40KpiVal}>{convData.converted_count}</span>
              <span className={styles.conv40KpiLabel}>成单数</span>
            </div>
            <div className={styles.conv40Kpi}>
              <span className={styles.conv40KpiVal}>{convData.total_leads}</span>
              <span className={styles.conv40KpiLabel}>总线索</span>
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="客户复购率">
        {!reordData || reordData.reorder_rate_pct == null ? <ZEmpty /> : (
          <div className={styles.conv40KpiRow}>
            <div className={`${styles.conv40Kpi} ${styles.conv40Accent}`}>
              <span className={styles.conv40KpiVal}>{reordData.reorder_rate_pct}%</span>
              <span className={styles.conv40KpiLabel}>复购率</span>
            </div>
            <div className={styles.conv40Kpi}>
              <span className={styles.conv40KpiVal}>{reordData.reorder_customers}</span>
              <span className={styles.conv40KpiLabel}>复购客户</span>
            </div>
            <div className={styles.conv40Kpi}>
              <span className={styles.conv40KpiVal}>{reordData.total_customers}</span>
              <span className={styles.conv40KpiLabel}>总客户</span>
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="线索年龄分布">
        {!ageData || ageData.avg_age_days == null ? <ZEmpty /> : (
          <div className={styles.age40Tab}>
            <div className={styles.age40Avg}>
              平均年龄：<strong>{ageData.avg_age_days}</strong> 天
            </div>
            <div className={styles.age40DistList}>
              {(ageData.distribution || []).map((b: any) => (
                <div key={b.bucket} className={styles.age40DistRow}>
                  <span className={styles.age40DistLabel}>{b.bucket}</span>
                  <div className={styles.age40DistTrack}>
                    <div className={styles.age40DistFill} style={{width:`${b.pct}%`}} />
                  </div>
                  <span className={styles.age40DistStat}>{b.count}条 ({b.pct}%)</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="取消提前期分布">
        {!cancelData || cancelData.avg_days_before_event == null ? <ZEmpty /> : (
          <div className={styles.cancelLt40Tab}>
            <div className={styles.cancelLt40Avg}>
              平均提前：<strong>{cancelData.avg_days_before_event}</strong> 天
            </div>
            <div className={styles.cancelLt40DistList}>
              {(cancelData.distribution || []).map((b: any) => (
                <div key={b.bucket} className={styles.cancelLt40DistRow}>
                  <span className={styles.cancelLt40DistLabel}>{b.bucket}</span>
                  <div className={styles.cancelLt40DistTrack}>
                    <div className={styles.cancelLt40DistFill} style={{width:`${b.pct}%`}} />
                  </div>
                  <span className={styles.cancelLt40DistStat}>{b.count}单 ({b.pct}%)</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 40: 定金分析 Tab ─── */
function DepositAnalysisTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [depositData,  setDepositData]  = useState<any>(null);
  const [customData,   setCustomData]   = useState<any>(null);
  const [perfData,     setPerfData]     = useState<any>(null);
  const [seasonData,   setSeasonData]   = useState<any>(null);
  const [loading,      setLoading]      = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [d, c, p, s] = await Promise.all([
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/deposit-ratio-analysis?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/menu-customization-rate?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/staff-performance-score?months=3`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/hall-revenue-seasonality?months=24`),
      ]);
      setDepositData((d as any).data);
      setCustomData((c as any).data);
      setPerfData((p as any).data);
      setSeasonData((s as any).data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={5} />;

  return (
    <div className={styles.deposit40Tab}>
      <ZCard title="定金比例分析">
        {!depositData || depositData.avg_deposit_ratio_pct == null ? <ZEmpty /> : (
          <div className={styles.dep40Tab}>
            <div className={styles.dep40Avg}>
              平均定金比例：<strong>{depositData.avg_deposit_ratio_pct}%</strong>
            </div>
            <div className={styles.dep40DistList}>
              {(depositData.distribution || []).map((b: any) => (
                <div key={b.bucket} className={styles.dep40DistRow}>
                  <span className={styles.dep40DistLabel}>{b.bucket}</span>
                  <div className={styles.dep40DistTrack}>
                    <div className={styles.dep40DistFill} style={{width:`${b.pct}%`}} />
                  </div>
                  <span className={styles.dep40DistStat}>{b.count}单 ({b.pct}%)</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="菜单定制率">
        {!customData || customData.customization_rate_pct == null ? <ZEmpty /> : (
          <div className={styles.conv40KpiRow}>
            <div className={`${styles.conv40Kpi} ${styles.conv40Accent}`}>
              <span className={styles.conv40KpiVal}>{customData.customization_rate_pct}%</span>
              <span className={styles.conv40KpiLabel}>定制率</span>
            </div>
            <div className={styles.conv40Kpi}>
              <span className={styles.conv40KpiVal}>{customData.customized_count}</span>
              <span className={styles.conv40KpiLabel}>定制单数</span>
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="员工绩效评分">
        {!perfData || !perfData.staff?.length ? <ZEmpty /> : (
          <div className={styles.perf40Tab}>
            {perfData.top_performer && (
              <div className={styles.perf40Top}>TOP绩效：{perfData.top_performer}</div>
            )}
            <div className={styles.perf40List}>
              <div className={styles.perf40Header}>
                <span style={{flex:2}}>员工ID</span>
                <span style={{flex:1}}>任务数</span>
                <span style={{flex:1}}>绩效分</span>
              </div>
              {(perfData.staff || []).map((s: any) => (
                <div key={s.user_id} className={styles.perf40Row}>
                  <span style={{flex:2, fontSize:12}}>{s.user_id}</span>
                  <span style={{flex:1}}>{s.total_tasks}</span>
                  <span style={{flex:1, fontWeight:600}}>{s.performance_score}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="厅房收入季节性">
        {!seasonData || !seasonData.monthly?.length ? <ZEmpty /> : (
          <div className={styles.season40Tab}>
            <div className={styles.season40KpiRow}>
              <span>旺季：<strong>{seasonData.peak_month}月</strong></span>
              <span>淡季：<strong>{seasonData.trough_month}月</strong></span>
            </div>
            <div className={styles.season40Bars}>
              {(seasonData.monthly || []).map((m: any) => {
                const maxIdx = Math.max(...(seasonData.monthly || []).map((x: any) => x.seasonal_index || 0));
                const pct = maxIdx > 0 ? Math.round((m.seasonal_index || 0) / maxIdx * 100) : 0;
                return (
                  <div key={m.month} className={`${styles.season40Bar} ${m.month === seasonData.peak_month ? styles.season40PeakBar : ''}`}>
                    <div className={styles.season40BarTrack}>
                      <div className={styles.season40BarFill} style={{height:`${pct}%`}} />
                    </div>
                    <span className={styles.season40BarLabel}>{m.month}月</span>
                    <span className={styles.season40BarIdx}>{m.seasonal_index}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 41: 爽约分析 Tab ─── */
function NoShowAnalysisTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [noShowData,  setNoShowData]  = useState<any>(null);
  const [quoteData,   setQuoteData]   = useState<any>(null);
  const [slotData,    setSlotData]    = useState<any>(null);
  const [amendData,   setAmendData]   = useState<any>(null);
  const [loading,     setLoading]     = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [n, q, s, a] = await Promise.all([
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/no-show-rate?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/quote-revision-count?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/peak-booking-slots?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/order-amendment-frequency?months=6`),
      ]);
      setNoShowData((n as any).data);
      setQuoteData((q as any).data);
      setSlotData((s as any).data);
      setAmendData((a as any).data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={5} />;

  return (
    <div className={styles.noShow41Tab}>
      <ZCard title="宴会爽约率">
        {!noShowData || noShowData.no_show_rate_pct == null ? <ZEmpty /> : (
          <div className={styles.ns41KpiRow}>
            <div className={`${styles.ns41Kpi} ${styles.ns41Red}`}>
              <span className={styles.ns41KpiVal}>{noShowData.no_show_rate_pct}%</span>
              <span className={styles.ns41KpiLabel}>爽约率</span>
            </div>
            <div className={styles.ns41Kpi}>
              <span className={styles.ns41KpiVal}>{noShowData.no_show_count}</span>
              <span className={styles.ns41KpiLabel}>爽约单数</span>
            </div>
            <div className={styles.ns41Kpi}>
              <span className={styles.ns41KpiVal}>{noShowData.total_past_orders}</span>
              <span className={styles.ns41KpiLabel}>历史订单</span>
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="报价修改次数">
        {!quoteData || quoteData.avg_revisions_per_lead == null ? <ZEmpty /> : (
          <div className={styles.ns41KpiRow}>
            <div className={`${styles.ns41Kpi} ${styles.ns41Accent}`}>
              <span className={styles.ns41KpiVal}>{quoteData.avg_revisions_per_lead}</span>
              <span className={styles.ns41KpiLabel}>平均修改次数</span>
            </div>
            <div className={styles.ns41Kpi}>
              <span className={styles.ns41KpiVal}>{quoteData.multi_revision_pct}%</span>
              <span className={styles.ns41KpiLabel}>多次修改率</span>
            </div>
            <div className={styles.ns41Kpi}>
              <span className={styles.ns41KpiVal}>{quoteData.total_quotes}</span>
              <span className={styles.ns41KpiLabel}>总报价数</span>
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="高峰预订时段">
        {!slotData || !slotData.slots?.length ? <ZEmpty /> : (
          <div className={styles.slot41Tab}>
            {slotData.peak_slot && (
              <div className={styles.slot41Peak}>高峰时段：{slotData.peak_slot}</div>
            )}
            <div className={styles.slot41List}>
              {(slotData.slots || []).map((s: any) => (
                <div key={s.slot} className={styles.slot41Row}>
                  <span className={styles.slot41Name}>{s.slot}</span>
                  <div className={styles.slot41Track}>
                    <div className={styles.slot41Fill} style={{width:`${s.pct}%`}} />
                  </div>
                  <span className={styles.slot41Stat}>{s.count}场 ({s.pct}%)</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="订单修改频率">
        {!amendData || amendData.amendment_rate_pct == null ? <ZEmpty /> : (
          <div className={styles.ns41KpiRow}>
            <div className={`${styles.ns41Kpi} ${styles.ns41Red}`}>
              <span className={styles.ns41KpiVal}>{amendData.amendment_rate_pct}%</span>
              <span className={styles.ns41KpiLabel}>修改率</span>
            </div>
            <div className={styles.ns41Kpi}>
              <span className={styles.ns41KpiVal}>{amendData.amended_count}</span>
              <span className={styles.ns41KpiLabel}>修改单数</span>
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 41: 套餐热度 Tab ─── */
function PackagePopularityTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [pkgData,    setPkgData]    = useState<any>(null);
  const [acqData,    setAcqData]    = useState<any>(null);
  const [tpData,     setTpData]     = useState<any>(null);
  const [specData,   setSpecData]   = useState<any>(null);
  const [loading,    setLoading]    = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, a, t, s] = await Promise.all([
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/package-popularity?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/customer-acquisition-cost?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/lead-touchpoint-count?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/staff-specialization-index?months=6`),
      ]);
      setPkgData((p as any).data);
      setAcqData((a as any).data);
      setTpData((t as any).data);
      setSpecData((s as any).data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={5} />;

  return (
    <div className={styles.pkgPop41Tab}>
      <ZCard title="套餐受欢迎度">
        {!pkgData || !pkgData.packages?.length ? <ZEmpty /> : (
          <div className={styles.pkgPop41List}>
            {pkgData.top_package_id && (
              <div className={styles.pkgPop41Top}>最热套餐：{pkgData.top_package_id}</div>
            )}
            <div className={styles.pkgPop41Rows}>
              <div className={styles.pkgPop41Header}>
                <span style={{flex:2}}>套餐ID</span>
                <span style={{flex:1}}>选用次数</span>
                <span style={{flex:1}}>占比</span>
              </div>
              {(pkgData.packages || []).map((p: any) => (
                <div key={p.package_id} className={styles.pkgPop41Row}>
                  <span style={{flex:2, fontSize:12}}>{p.package_id}</span>
                  <span style={{flex:1}}>{p.order_count}</span>
                  <span style={{flex:1, fontWeight:600}}>{p.pct}%</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="获客渠道价值">
        {!acqData || acqData.avg_budget_yuan == null ? <ZEmpty /> : (
          <div className={styles.acq41Tab}>
            <div className={styles.acq41Avg}>
              平均预算：<strong>¥{acqData.avg_budget_yuan?.toLocaleString()}</strong>
            </div>
            <div className={styles.acq41List}>
              {(acqData.channels || []).map((c: any) => (
                <div key={c.channel} className={styles.acq41Row}>
                  <span className={styles.acq41Ch}>{c.channel}</span>
                  <span>{c.won_count}单</span>
                  <span className={styles.acq41Budget}>¥{c.avg_budget_yuan?.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="线索接触次数对比">
        {!tpData || tpData.avg_touchpoints == null ? <ZEmpty /> : (
          <div className={styles.ns41KpiRow}>
            <div className={`${styles.ns41Kpi} ${styles.ns41Accent}`}>
              <span className={styles.ns41KpiVal}>{tpData.avg_touchpoints}</span>
              <span className={styles.ns41KpiLabel}>平均接触次数</span>
            </div>
            <div className={styles.ns41Kpi}>
              <span className={styles.ns41KpiVal}>{tpData.won_avg ?? '-'}</span>
              <span className={styles.ns41KpiLabel}>成单均值</span>
            </div>
            <div className={styles.ns41Kpi}>
              <span className={styles.ns41KpiVal}>{tpData.lost_avg ?? '-'}</span>
              <span className={styles.ns41KpiLabel}>未成单均值</span>
            </div>
          </div>
        )}
      </ZCard>

      <ZCard title="员工专业化指数">
        {!specData || !specData.staff?.length ? <ZEmpty /> : (
          <div className={styles.spec41Tab}>
            {specData.most_specialized && (
              <div className={styles.spec41Top}>最专业：{specData.most_specialized}</div>
            )}
            <div className={styles.spec41List}>
              <div className={styles.spec41Header}>
                <span style={{flex:2}}>员工ID</span>
                <span style={{flex:1}}>主要类型</span>
                <span style={{flex:1}}>专业指数</span>
              </div>
              {(specData.staff || []).map((s: any) => (
                <div key={s.user_id} className={styles.spec41Row}>
                  <span style={{flex:2, fontSize:12}}>{s.user_id}</span>
                  <span style={{flex:1}}>{s.top_banquet_type}</span>
                  <span style={{flex:1, fontWeight:600}}>{s.specialization_idx}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 42: 人均消费 Tab ─── */
function GuestRevenueTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [rpgData,    setRpgData]    = useState<any>(null);
  const [densData,   setDensData]   = useState<any>(null);
  const [fbData,     setFbData]     = useState<any>(null);
  const [overdueData,setOverdueData]= useState<any>(null);
  const [loading,    setLoading]    = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2, r3, r4] = await Promise.all([
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/revenue-per-guest?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/hall-booking-density?months=3`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/feedback-response-rate?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/task-overdue-rate?months=3`),
      ]);
      setRpgData(r1.data);
      setDensData(r2.data);
      setFbData(r3.data);
      setOverdueData(r4.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>

      {/* 人均消费 */}
      <ZCard title="人均消费分析">
        {!rpgData || rpgData.overall_per_guest_yuan == null ? <ZEmpty /> : (
          <div className={styles.guestRev42Tab}>
            <div className={styles.gr42KpiRow}>
              <div className={`${styles.gr42Kpi} ${styles.gr42Accent}`}>
                <span className={styles.gr42KpiVal}>¥{rpgData.overall_per_guest_yuan?.toFixed(1)}</span>
                <span className={styles.gr42KpiLabel}>总体人均消费</span>
              </div>
              <div className={styles.gr42Kpi}>
                <span className={styles.gr42KpiVal}>{rpgData.total_orders}</span>
                <span className={styles.gr42KpiLabel}>订单数</span>
              </div>
            </div>
            {(rpgData.by_type || []).length > 0 && (
              <div className={styles.gr42TypeList}>
                <div className={styles.gr42TypeHeader}>
                  <span style={{flex:2}}>宴会类型</span>
                  <span style={{flex:1}}>订单</span>
                  <span style={{flex:1}}>人均¥</span>
                </div>
                {(rpgData.by_type || []).map((t: any) => (
                  <div key={t.banquet_type} className={styles.gr42TypeRow}>
                    <span style={{flex:2}}>{t.banquet_type}</span>
                    <span style={{flex:1}}>{t.order_count}</span>
                    <span style={{flex:1, color:'var(--accent)', fontWeight:600}}>
                      {t.per_guest_yuan?.toFixed(1)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </ZCard>

      {/* 厅房预订密度 */}
      <ZCard title="厅房预订密度">
        {!densData || !densData.halls?.length ? <ZEmpty /> : (
          <div className={styles.density42Tab}>
            {densData.overall_weekly_density != null && (
              <div className={styles.dens42Overall}>
                总体周均预订：<strong>{densData.overall_weekly_density?.toFixed(2)} 次/周</strong>
              </div>
            )}
            <div className={styles.dens42List}>
              <div className={styles.dens42Header}>
                <span style={{flex:2}}>厅房</span>
                <span style={{flex:1}}>预订数</span>
                <span style={{flex:1}}>周均</span>
              </div>
              {(densData.halls || []).map((h: any) => (
                <div key={h.hall_id} className={styles.dens42Row}>
                  <span style={{flex:2}}>{h.hall_name}</span>
                  <span style={{flex:1}}>{h.booking_count}</span>
                  <span style={{flex:1, fontWeight:600}}>{h.weekly_density?.toFixed(2)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      {/* 客户反馈响应率 */}
      <ZCard title="客户反馈响应率">
        {!fbData || fbData.response_rate_pct == null ? <ZEmpty /> : (
          <div className={styles.fbResp42KpiRow}>
            <div className={`${styles.fbResp42Kpi} ${styles.gr42Accent}`}>
              <span className={styles.gr42KpiVal}>{fbData.response_rate_pct?.toFixed(1)}%</span>
              <span className={styles.gr42KpiLabel}>投诉响应率</span>
            </div>
            <div className={styles.fbResp42Kpi}>
              <span className={styles.gr42KpiVal}>{fbData.resolved_count}</span>
              <span className={styles.gr42KpiLabel}>已处理</span>
            </div>
            <div className={styles.fbResp42Kpi}>
              <span className={styles.gr42KpiVal}>{fbData.total_complaints}</span>
              <span className={styles.gr42KpiLabel}>总投诉</span>
            </div>
          </div>
        )}
      </ZCard>

      {/* 任务逾期率 */}
      <ZCard title="员工任务逾期率">
        {!overdueData || overdueData.overdue_rate_pct == null ? <ZEmpty /> : (
          <div className={styles.overdueTab42}>
            <div className={styles.gr42KpiRow}>
              <div className={`${styles.gr42Kpi} ${overdueData.overdue_rate_pct > 20 ? styles.gr42Accent : ''}`}>
                <span className={styles.gr42KpiVal}>{overdueData.overdue_rate_pct?.toFixed(1)}%</span>
                <span className={styles.gr42KpiLabel}>逾期率</span>
              </div>
              <div className={styles.gr42Kpi}>
                <span className={styles.gr42KpiVal}>{overdueData.overdue_count}</span>
                <span className={styles.gr42KpiLabel}>逾期任务</span>
              </div>
              <div className={styles.gr42Kpi}>
                <span className={styles.gr42KpiVal}>{overdueData.total_completed}</span>
                <span className={styles.gr42KpiLabel}>已完成</span>
              </div>
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 42: VIP分析 Tab ─── */
function VipAnalysisTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [vipData,   setVipData]   = useState<any>(null);
  const [budgData,  setBudgData]  = useState<any>(null);
  const [addonData, setAddonData] = useState<any>(null);
  const [gapData,   setGapData]   = useState<any>(null);
  const [loading,   setLoading]   = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2, r3, r4] = await Promise.all([
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/vip-upgrade-rate?months=12`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/lead-budget-accuracy?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/addon-revenue?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/deposit-to-final-payment-gap?months=6`),
      ]);
      setVipData(r1.data);
      setBudgData(r2.data);
      setAddonData(r3.data);
      setGapData(r4.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>

      {/* VIP升级率 */}
      <ZCard title="VIP客户分析">
        {!vipData || vipData.vip_rate_pct == null ? <ZEmpty /> : (
          <div className={styles.vipAnal42Tab}>
            <div className={styles.vip42KpiRow}>
              <div className={`${styles.vip42Kpi} ${styles.vip42Accent}`}>
                <span className={styles.vip42KpiVal}>{vipData.vip_rate_pct?.toFixed(1)}%</span>
                <span className={styles.vip42KpiLabel}>VIP占比</span>
              </div>
              <div className={styles.vip42Kpi}>
                <span className={styles.vip42KpiVal}>{vipData.vip_count}</span>
                <span className={styles.vip42KpiLabel}>VIP客户</span>
              </div>
              <div className={styles.vip42Kpi}>
                <span className={styles.vip42KpiVal}>{vipData.total_customers}</span>
                <span className={styles.vip42KpiLabel}>总客户</span>
              </div>
            </div>
            {(vipData.by_level || []).length > 0 && (
              <div className={styles.vip42LevelList}>
                {(vipData.by_level || []).map((lv: any) => (
                  <div key={lv.vip_level} style={{
                    display:'flex', justifyContent:'space-between',
                    padding:'6px 0', borderBottom:'1px solid var(--border)', fontSize:13
                  }}>
                    <span>Lv{lv.vip_level}</span>
                    <span style={{fontWeight:600}}>{lv.count} 人</span>
                    <span style={{color:'var(--accent)'}}>{lv.pct?.toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </ZCard>

      {/* 线索预算准确率 */}
      <ZCard title="线索预算准确率">
        {!budgData || budgData.avg_deviation_pct == null ? <ZEmpty /> : (
          <div className={styles.budgetAcc42}>
            <div className={styles.vip42KpiRow}>
              <div className={`${styles.vip42Kpi} ${styles.vip42Accent}`}>
                <span className={styles.vip42KpiVal}>{budgData.accurate_pct?.toFixed(1)}%</span>
                <span className={styles.vip42KpiLabel}>预算准确率</span>
              </div>
              <div className={styles.vip42Kpi}>
                <span className={styles.vip42KpiVal}>{budgData.avg_deviation_pct?.toFixed(1)}%</span>
                <span className={styles.vip42KpiLabel}>平均偏差</span>
              </div>
              <div className={styles.vip42Kpi}>
                <span className={styles.vip42KpiVal}>{budgData.total_won}</span>
                <span className={styles.vip42KpiLabel}>成单线索</span>
              </div>
            </div>
          </div>
        )}
      </ZCard>

      {/* 加购收入 */}
      <ZCard title="套餐加购分析">
        {!addonData || addonData.total_addon_yuan == null ? <ZEmpty /> : (
          <div className={styles.addon42KpiRow}>
            <div className={`${styles.vip42Kpi} ${styles.vip42Accent}`}>
              <span className={styles.vip42KpiVal}>¥{addonData.total_addon_yuan?.toFixed(0)}</span>
              <span className={styles.vip42KpiLabel}>总加购金额</span>
            </div>
            <div className={styles.vip42Kpi}>
              <span className={styles.vip42KpiVal}>¥{addonData.avg_addon_yuan?.toFixed(0)}</span>
              <span className={styles.vip42KpiLabel}>均单加购</span>
            </div>
            <div className={styles.vip42Kpi}>
              <span className={styles.vip42KpiVal}>{addonData.addon_orders}</span>
              <span className={styles.vip42KpiLabel}>有加购订单</span>
            </div>
          </div>
        )}
      </ZCard>

      {/* 定金到尾款时长 */}
      <ZCard title="定金到尾款间隔">
        {!gapData || gapData.avg_gap_days == null ? <ZEmpty /> : (
          <div className={styles.payGap42KpiRow}>
            <div className={`${styles.vip42Kpi} ${styles.vip42Accent}`}>
              <span className={styles.vip42KpiVal}>{gapData.avg_gap_days?.toFixed(1)}</span>
              <span className={styles.vip42KpiLabel}>平均间隔(天)</span>
            </div>
            <div className={styles.vip42Kpi}>
              <span className={styles.vip42KpiVal}>{gapData.quick_payment_pct?.toFixed(1)}%</span>
              <span className={styles.vip42KpiLabel}>快速结清率</span>
            </div>
            <div className={styles.vip42Kpi}>
              <span className={styles.vip42KpiVal}>{gapData.total_orders}</span>
              <span className={styles.vip42KpiLabel}>已完成订单</span>
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 43: 每桌收入 Tab ─── */
function PerTableRevenueTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [rptData,  setRptData]  = useState<any>(null);
  const [roiData,  setRoiData]  = useState<any>(null);
  const [payData,  setPayData]  = useState<any>(null);
  const [riskData, setRiskData] = useState<any>(null);
  const [loading,  setLoading]  = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2, r3, r4] = await Promise.all([
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/revenue-per-table?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/lead-source-roi?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/payment-completion-rate?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/double-booking-risk?months=3`),
      ]);
      setRptData(r1.data);
      setRoiData(r2.data);
      setPayData(r3.data);
      setRiskData(r4.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>

      {/* 每桌收入 */}
      <ZCard title="每桌收入分析">
        {!rptData || rptData.overall_per_table_yuan == null ? <ZEmpty /> : (
          <div className={styles.perTable43Tab}>
            <div className={styles.pt43KpiRow}>
              <div className={`${styles.pt43Kpi} ${styles.pt43Accent}`}>
                <span className={styles.pt43KpiVal}>¥{rptData.overall_per_table_yuan?.toFixed(0)}</span>
                <span className={styles.pt43KpiLabel}>总体每桌收入</span>
              </div>
              <div className={styles.pt43Kpi}>
                <span className={styles.pt43KpiVal}>{rptData.total_orders}</span>
                <span className={styles.pt43KpiLabel}>订单数</span>
              </div>
            </div>
            {(rptData.by_type || []).length > 0 && (
              <div className={styles.pt43TypeList}>
                <div className={styles.pt43TypeHeader}>
                  <span style={{flex:2}}>宴会类型</span>
                  <span style={{flex:1}}>订单</span>
                  <span style={{flex:1}}>每桌¥</span>
                </div>
                {(rptData.by_type || []).map((t: any) => (
                  <div key={t.banquet_type} className={styles.pt43TypeRow}>
                    <span style={{flex:2}}>{t.banquet_type}</span>
                    <span style={{flex:1}}>{t.order_count}</span>
                    <span style={{flex:1, color:'var(--accent)', fontWeight:600}}>
                      {t.per_table_yuan?.toFixed(0)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </ZCard>

      {/* 线索渠道ROI */}
      <ZCard title="线索渠道ROI">
        {!roiData || !roiData.channels?.length ? <ZEmpty /> : (
          <div className={styles.roi43Tab}>
            {roiData.best_channel && (
              <div className={styles.roi43Best}>最优渠道：<strong>{roiData.best_channel}</strong></div>
            )}
            <div className={styles.roi43List}>
              <div className={styles.roi43Header}>
                <span style={{flex:2}}>渠道</span>
                <span style={{flex:1}}>成单</span>
                <span style={{flex:1}}>转化率</span>
              </div>
              {(roiData.channels || []).map((c: any) => (
                <div key={c.channel} className={styles.roi43Row}>
                  <span style={{flex:2}}>{c.channel}</span>
                  <span style={{flex:1}}>{c.won}/{c.total}</span>
                  <span style={{flex:1, color:'var(--accent)', fontWeight:600}}>
                    {c.win_rate_pct?.toFixed(1)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      {/* 付款完成率 */}
      <ZCard title="付款完成率">
        {!payData || payData.completion_rate_pct == null ? <ZEmpty /> : (
          <div className={styles.pay43KpiRow}>
            <div className={`${styles.pt43Kpi} ${styles.pt43Accent}`}>
              <span className={styles.pt43KpiVal}>{payData.completion_rate_pct?.toFixed(1)}%</span>
              <span className={styles.pt43KpiLabel}>全额付清率</span>
            </div>
            <div className={styles.pt43Kpi}>
              <span className={styles.pt43KpiVal}>{payData.fully_paid_count}</span>
              <span className={styles.pt43KpiLabel}>已全额付清</span>
            </div>
            <div className={styles.pt43Kpi}>
              <span className={styles.pt43KpiVal}>{payData.total_orders}</span>
              <span className={styles.pt43KpiLabel}>总订单</span>
            </div>
          </div>
        )}
      </ZCard>

      {/* 重复预订风险 */}
      <ZCard title="厅房重复预订风险">
        {!riskData || riskData.conflict_rate_pct == null ? <ZEmpty /> : (
          <div className={styles.risk43Tab}>
            <div className={styles.pt43KpiRow}>
              <div className={`${styles.pt43Kpi} ${riskData.conflict_days > 0 ? styles.pt43Accent : ''}`}>
                <span className={styles.pt43KpiVal}>{riskData.conflict_days}</span>
                <span className={styles.pt43KpiLabel}>冲突档期</span>
              </div>
              <div className={styles.pt43Kpi}>
                <span className={styles.pt43KpiVal}>{riskData.conflict_rate_pct?.toFixed(1)}%</span>
                <span className={styles.pt43KpiLabel}>冲突率</span>
              </div>
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 43: 客户价值 Tab ─── */
function CustomerLtvTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [ltvData,    setLtvData]    = useState<any>(null);
  const [seasonData, setSeasonData] = useState<any>(null);
  const [loadData,   setLoadData]   = useState<any>(null);
  const [venueData,  setVenueData]  = useState<any>(null);
  const [loading,    setLoading]    = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2, r3, r4] = await Promise.all([
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/customer-lifetime-value?months=24`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/seasonal-revenue-index?months=24`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/staff-order-load?months=3`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/repeat-venue-rate?months=12`),
      ]);
      setLtvData(r1.data);
      setSeasonData(r2.data);
      setLoadData(r3.data);
      setVenueData(r4.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>

      {/* 客户终身价值 */}
      <ZCard title="客户终身价值 (LTV)">
        {!ltvData || ltvData.avg_ltv_yuan == null ? <ZEmpty /> : (
          <div className={styles.ltv43Tab}>
            <div className={styles.ltv43KpiRow}>
              <div className={`${styles.ltv43Kpi} ${styles.ltv43Accent}`}>
                <span className={styles.ltv43KpiVal}>¥{ltvData.avg_ltv_yuan?.toFixed(0)}</span>
                <span className={styles.ltv43KpiLabel}>平均LTV</span>
              </div>
              <div className={styles.ltv43Kpi}>
                <span className={styles.ltv43KpiVal}>{ltvData.total_customers}</span>
                <span className={styles.ltv43KpiLabel}>活跃客户</span>
              </div>
            </div>
            {(ltvData.top_customers || []).length > 0 && (
              <div className={styles.ltv43TopList}>
                <div className={styles.ltv43TopHeader}>
                  <span style={{flex:2}}>客户ID</span>
                  <span style={{flex:1}}>LTV¥</span>
                </div>
                {(ltvData.top_customers || []).slice(0, 5).map((c: any) => (
                  <div key={c.customer_id} className={styles.ltv43TopRow}>
                    <span style={{flex:2, fontSize:12}}>{c.customer_id}</span>
                    <span style={{flex:1, color:'var(--accent)', fontWeight:600}}>
                      {c.ltv_yuan?.toFixed(0)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </ZCard>

      {/* 季度收入指数 */}
      <ZCard title="季度收入指数">
        {!seasonData || !seasonData.quarterly?.length ? <ZEmpty /> : (
          <div className={styles.season43Tab}>
            {seasonData.peak_quarter != null && (
              <div className={styles.season43Peak}>
                旺季：<strong>Q{seasonData.peak_quarter}</strong>
              </div>
            )}
            <div className={styles.season43List}>
              {(seasonData.quarterly || []).map((q: any) => (
                <div key={q.quarter} className={styles.season43Row}>
                  <span className={styles.season43Q}>Q{q.quarter}</span>
                  <span className={styles.season43Cnt}>{q.order_count} 单</span>
                  <span style={{
                    flex:1, textAlign:'right', fontWeight:600,
                    color: q.quarter === seasonData.peak_quarter ? 'var(--accent)' : 'var(--text-primary)'
                  }}>
                    ¥{q.revenue_yuan?.toFixed(0)}
                  </span>
                  <span className={styles.season43Idx}>×{q.seasonal_index}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      {/* 员工订单负荷 */}
      <ZCard title="员工订单负荷">
        {!loadData || !loadData.staff?.length ? <ZEmpty /> : (
          <div className={styles.load43Tab}>
            {loadData.busiest_staff && (
              <div className={styles.load43Top}>最忙员工：<strong>{loadData.busiest_staff}</strong></div>
            )}
            <div className={styles.load43List}>
              <div className={styles.load43Header}>
                <span style={{flex:2}}>员工ID</span>
                <span style={{flex:1}}>任务数</span>
                <span style={{flex:1}}>订单数</span>
              </div>
              {(loadData.staff || []).slice(0, 8).map((s: any) => (
                <div key={s.user_id} className={styles.load43Row}>
                  <span style={{flex:2, fontSize:12}}>{s.user_id}</span>
                  <span style={{flex:1, fontWeight:600}}>{s.task_count}</span>
                  <span style={{flex:1}}>{s.order_count}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      {/* 同场地重复预订率 */}
      <ZCard title="同场地重复预订率">
        {!venueData || venueData.repeat_rate_pct == null ? <ZEmpty /> : (
          <div className={styles.venue43Tab}>
            <div className={styles.ltv43KpiRow}>
              <div className={`${styles.ltv43Kpi} ${styles.ltv43Accent}`}>
                <span className={styles.ltv43KpiVal}>{venueData.repeat_rate_pct?.toFixed(1)}%</span>
                <span className={styles.ltv43KpiLabel}>重复预订率</span>
              </div>
              <div className={styles.ltv43Kpi}>
                <span className={styles.ltv43KpiVal}>{venueData.repeat_hall_count}</span>
                <span className={styles.ltv43KpiLabel}>高频厅房</span>
              </div>
            </div>
            {(venueData.repeat_halls || []).length > 0 && (
              <div style={{ marginTop: 8 }}>
                {(venueData.repeat_halls || []).slice(0, 5).map((h: any) => (
                  <div key={h.hall_id} style={{
                    display:'flex', justifyContent:'space-between',
                    padding:'6px 0', borderBottom:'1px solid var(--border)', fontSize:13
                  }}>
                    <span>{h.hall_id}</span>
                    <span style={{fontWeight:600, color:'var(--accent)'}}>
                      {h.booking_count} 次预订
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 44: 转化漏斗 Tab ─── */
function LeadFunnelTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [funnelData, setFunnelData] = useState<any>(null);
  const [winLossData,setWinLossData]= useState<any>(null);
  const [concData,   setConcData]   = useState<any>(null);
  const [growthData, setGrowthData] = useState<any>(null);
  const [loading,    setLoading]    = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2, r3, r4] = await Promise.all([
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/lead-conversion-funnel?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/lead-win-loss-ratio?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/order-value-concentration?months=12`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/customer-spend-growth?months=12`),
      ]);
      setFunnelData(r1.data);
      setWinLossData(r2.data);
      setConcData(r3.data);
      setGrowthData(r4.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>

      {/* 线索转化漏斗 */}
      <ZCard title="线索转化漏斗">
        {!funnelData || funnelData.win_rate_pct == null ? <ZEmpty /> : (
          <div className={styles.funnel44Tab}>
            <div className={styles.funnel44KpiRow}>
              <div className={`${styles.funnel44Kpi} ${styles.funnel44Accent}`}>
                <span className={styles.funnel44KpiVal}>{funnelData.win_rate_pct?.toFixed(1)}%</span>
                <span className={styles.funnel44KpiLabel}>整体转化率</span>
              </div>
              <div className={styles.funnel44Kpi}>
                <span className={styles.funnel44KpiVal}>{funnelData.total_leads}</span>
                <span className={styles.funnel44KpiLabel}>总线索数</span>
              </div>
            </div>
            <div className={styles.funnel44Stages}>
              {(funnelData.stages || []).filter((s: any) => s.count > 0).map((s: any) => (
                <div key={s.stage} className={styles.funnel44Stage}>
                  <span className={styles.funnel44StageName}>{s.stage}</span>
                  <div className={styles.funnel44Bar}>
                    <div className={styles.funnel44Fill} style={{width:`${s.pct}%`}} />
                  </div>
                  <span className={styles.funnel44Stat}>{s.count}({s.pct}%)</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      {/* 赢单/输单比 */}
      <ZCard title="赢单/输单比">
        {!winLossData || winLossData.win_loss_ratio == null ? <ZEmpty /> : (
          <div className={styles.winLoss44Tab}>
            <div className={styles.funnel44KpiRow}>
              <div className={`${styles.funnel44Kpi} ${styles.funnel44Accent}`}>
                <span className={styles.funnel44KpiVal}>{winLossData.win_loss_ratio}</span>
                <span className={styles.funnel44KpiLabel}>赢/输比</span>
              </div>
              <div className={styles.funnel44Kpi}>
                <span className={styles.funnel44KpiVal}>{winLossData.won}</span>
                <span className={styles.funnel44KpiLabel}>赢单</span>
              </div>
              <div className={styles.funnel44Kpi}>
                <span className={styles.funnel44KpiVal}>{winLossData.lost}</span>
                <span className={styles.funnel44KpiLabel}>输单</span>
              </div>
            </div>
          </div>
        )}
      </ZCard>

      {/* 订单金额集中度 */}
      <ZCard title="订单金额集中度">
        {!concData || concData.top20_pct_revenue == null ? <ZEmpty /> : (
          <div className={styles.conc44Tab}>
            <div className={styles.funnel44KpiRow}>
              <div className={`${styles.funnel44Kpi} ${styles.funnel44Accent}`}>
                <span className={styles.funnel44KpiVal}>{concData.top20_pct_revenue?.toFixed(1)}%</span>
                <span className={styles.funnel44KpiLabel}>Top20%收入占比</span>
              </div>
              <div className={styles.funnel44Kpi}>
                <span className={styles.funnel44KpiVal}>{concData.gini?.toFixed(3)}</span>
                <span className={styles.funnel44KpiLabel}>基尼系数</span>
              </div>
            </div>
          </div>
        )}
      </ZCard>

      {/* 客户消费增长 */}
      <ZCard title="客户消费增长率">
        {!growthData || growthData.avg_growth_pct == null ? <ZEmpty /> : (
          <div className={styles.funnel44KpiRow}>
            <div className={`${styles.funnel44Kpi} ${styles.funnel44Accent}`}>
              <span className={styles.funnel44KpiVal}>{growthData.avg_growth_pct?.toFixed(1)}%</span>
              <span className={styles.funnel44KpiLabel}>平均增长率</span>
            </div>
            <div className={styles.funnel44Kpi}>
              <span className={styles.funnel44KpiVal}>{growthData.growing_customers}</span>
              <span className={styles.funnel44KpiLabel}>增长客户数</span>
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 44: 退款分析 Tab ─── */
function RefundAnalysisTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [refundData,  setRefundData]  = useState<any>(null);
  const [upgradeData, setUpgradeData] = useState<any>(null);
  const [speedData,   setSpeedData]   = useState<any>(null);
  const [availData,   setAvailData]   = useState<any>(null);
  const [loading,     setLoading]     = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2, r3, r4] = await Promise.all([
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/banquet-refund-rate?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/menu-upgrade-rate?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/task-completion-speed?months=3`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/hall-slot-availability?months=3`),
      ]);
      setRefundData(r1.data);
      setUpgradeData(r2.data);
      setSpeedData(r3.data);
      setAvailData(r4.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>

      {/* 退款率 */}
      <ZCard title="宴会退款分析">
        {!refundData || refundData.refund_rate_pct == null ? <ZEmpty /> : (
          <div className={styles.refund44Tab}>
            <div className={styles.ref44KpiRow}>
              <div className={`${styles.ref44Kpi} ${refundData.refund_rate_pct > 20 ? styles.ref44Accent : ''}`}>
                <span className={styles.ref44KpiVal}>{refundData.refund_rate_pct?.toFixed(1)}%</span>
                <span className={styles.ref44KpiLabel}>需退款率</span>
              </div>
              <div className={styles.ref44Kpi}>
                <span className={styles.ref44KpiVal}>¥{refundData.total_refund_yuan?.toFixed(0)}</span>
                <span className={styles.ref44KpiLabel}>退款总额</span>
              </div>
              <div className={styles.ref44Kpi}>
                <span className={styles.ref44KpiVal}>{refundData.total_cancelled}</span>
                <span className={styles.ref44KpiLabel}>取消总数</span>
              </div>
            </div>
          </div>
        )}
      </ZCard>

      {/* 菜单升档率 */}
      <ZCard title="菜单升档率">
        {!upgradeData || upgradeData.upgrade_rate_pct == null ? <ZEmpty /> : (
          <div className={styles.ref44KpiRow}>
            <div className={`${styles.ref44Kpi} ${styles.ref44Accent}`}>
              <span className={styles.ref44KpiVal}>{upgradeData.upgrade_rate_pct?.toFixed(1)}%</span>
              <span className={styles.ref44KpiLabel}>升档率</span>
            </div>
            <div className={styles.ref44Kpi}>
              <span className={styles.ref44KpiVal}>{upgradeData.upgraded_count}</span>
              <span className={styles.ref44KpiLabel}>升档订单</span>
            </div>
            <div className={styles.ref44Kpi}>
              <span className={styles.ref44KpiVal}>{upgradeData.total_pkg_orders}</span>
              <span className={styles.ref44KpiLabel}>套餐订单</span>
            </div>
          </div>
        )}
      </ZCard>

      {/* 任务完成速度 */}
      <ZCard title="任务完成速度">
        {!speedData || speedData.avg_hours == null ? <ZEmpty /> : (
          <div className={styles.ref44KpiRow}>
            <div className={`${styles.ref44Kpi} ${styles.ref44Accent}`}>
              <span className={styles.ref44KpiVal}>{speedData.avg_hours?.toFixed(1)}h</span>
              <span className={styles.ref44KpiLabel}>平均完成时长</span>
            </div>
            <div className={styles.ref44Kpi}>
              <span className={styles.ref44KpiVal}>{speedData.fast_pct?.toFixed(1)}%</span>
              <span className={styles.ref44KpiLabel}>24h内完成率</span>
            </div>
          </div>
        )}
      </ZCard>

      {/* 厅房档期可用率 */}
      <ZCard title="厅房档期可用率">
        {!availData || !availData.halls?.length ? <ZEmpty /> : (
          <div className={styles.avail44Tab}>
            {availData.overall_occupancy_pct != null && (
              <div className={styles.avail44Overall}>
                整体入住率：<strong>{availData.overall_occupancy_pct?.toFixed(1)}%</strong>
              </div>
            )}
            <div className={styles.avail44List}>
              {(availData.halls || []).map((h: any) => (
                <div key={h.hall_id} className={styles.avail44Row}>
                  <span className={styles.avail44Name}>{h.hall_name}</span>
                  <div className={styles.avail44Track}>
                    <div className={styles.avail44Fill} style={{width:`${Math.min(h.occupancy_pct, 100)}%`}} />
                  </div>
                  <span className={styles.avail44Stat}>{h.occupancy_pct?.toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 45: 高峰日 Tab ─── */
function PeakDayTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [peakData,   setPeakData]   = useState<any>(null);
  const [sqmData,    setSqmData]    = useState<any>(null);
  const [nurData,    setNurData]    = useState<any>(null);
  const [tableData,  setTableData]  = useState<any>(null);
  const [loading,    setLoading]    = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2, r3, r4] = await Promise.all([
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/peak-day-analysis?months=12`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/hall-revenue-per-sqm?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/lead-nurturing-effectiveness?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/table-utilization?months=6`),
      ]);
      setPeakData(r1.data);
      setSqmData(r2.data);
      setNurData(r3.data);
      setTableData(r4.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>

      {/* 高峰日分析 */}
      <ZCard title="宴会高峰日分析">
        {!peakData || !peakData.by_weekday?.length ? <ZEmpty /> : (
          <div className={styles.peak45Tab}>
            {peakData.peak_weekday && (
              <div className={styles.peak45Top}>最热宴会日：<strong>{peakData.peak_weekday}</strong></div>
            )}
            <div className={styles.peak45List}>
              {(peakData.by_weekday || []).filter((d: any) => d.order_count > 0).map((d: any) => {
                const maxCnt = Math.max(...(peakData.by_weekday || []).map((x: any) => x.order_count));
                return (
                  <div key={d.weekday} className={styles.peak45Row}>
                    <span className={styles.peak45Name}>{d.name}</span>
                    <div className={styles.peak45Bar}>
                      <div className={styles.peak45Fill}
                        style={{width:`${maxCnt > 0 ? d.order_count/maxCnt*100 : 0}%`}} />
                    </div>
                    <span className={styles.peak45Stat}>{d.order_count}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </ZCard>

      {/* 厅房坪效 */}
      <ZCard title="厅房坪效 (元/㎡)">
        {!sqmData || !sqmData.halls?.length ? <ZEmpty /> : (
          <div className={styles.sqm45Tab}>
            {sqmData.overall_per_sqm != null && (
              <div className={styles.sqm45Overall}>
                整体坪效：<strong>¥{sqmData.overall_per_sqm?.toFixed(1)}/㎡</strong>
              </div>
            )}
            <div className={styles.sqm45List}>
              <div className={styles.sqm45Header}>
                <span style={{flex:2}}>厅房</span>
                <span style={{flex:1}}>面积㎡</span>
                <span style={{flex:1}}>坪效¥</span>
              </div>
              {(sqmData.halls || []).map((h: any) => (
                <div key={h.hall_id} className={styles.sqm45Row}>
                  <span style={{flex:2}}>{h.hall_name}</span>
                  <span style={{flex:1}}>{h.area_m2}</span>
                  <span style={{flex:1, color:'var(--accent)', fontWeight:600}}>
                    {h.per_sqm_yuan?.toFixed(1) ?? '-'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      {/* 线索培育效果 */}
      <ZCard title="线索培育效果">
        {!nurData || nurData.won_avg_followups == null ? <ZEmpty /> : (
          <div className={styles.nur45KpiRow}>
            <div className={`${styles.nur45Kpi} ${styles.nur45Accent}`}>
              <span className={styles.nur45KpiVal}>{nurData.won_avg_followups}</span>
              <span className={styles.nur45KpiLabel}>成单平均跟进</span>
            </div>
            <div className={styles.nur45Kpi}>
              <span className={styles.nur45KpiVal}>{nurData.lost_avg_followups ?? '-'}</span>
              <span className={styles.nur45KpiLabel}>未成单平均跟进</span>
            </div>
            <div className={styles.nur45Kpi}>
              <span className={styles.nur45KpiVal}>{nurData.total_leads}</span>
              <span className={styles.nur45KpiLabel}>总线索</span>
            </div>
          </div>
        )}
      </ZCard>

      {/* 桌位利用率 */}
      <ZCard title="桌位利用率">
        {!tableData || tableData.avg_utilization_pct == null ? <ZEmpty /> : (
          <div className={styles.table45Tab}>
            <div className={styles.nur45KpiRow}>
              <div className={`${styles.nur45Kpi} ${styles.nur45Accent}`}>
                <span className={styles.nur45KpiVal}>{tableData.avg_utilization_pct?.toFixed(1)}%</span>
                <span className={styles.nur45KpiLabel}>平均桌位利用率</span>
              </div>
              <div className={styles.nur45Kpi}>
                <span className={styles.nur45KpiVal}>{tableData.total_orders}</span>
                <span className={styles.nur45KpiLabel}>订单数</span>
              </div>
            </div>
            {(tableData.by_type || []).length > 0 && (
              <div className={styles.table45List}>
                {(tableData.by_type || []).map((t: any) => (
                  <div key={t.banquet_type} className={styles.table45Row}>
                    <span style={{flex:2}}>{t.banquet_type}</span>
                    <span style={{flex:1}}>{t.avg_tables} 桌</span>
                    <span style={{flex:1, color:'var(--accent)', fontWeight:600}}>
                      {t.utilization_pct?.toFixed(1) ?? '-'}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </ZCard>
    </div>
  );
}

/* ─── Phase 45: 风险预警 Tab ─── */
function EarlyWarningTab() {
  const STORE = localStorage.getItem('store_id') || 'S001';
  const [warnData,    setWarnData]    = useState<any>(null);
  const [staffData,   setStaffData]   = useState<any>(null);
  const [cmpData,     setCmpData]     = useState<any>(null);
  const [payChanData, setPayChanData] = useState<any>(null);
  const [loading,     setLoading]     = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2, r3, r4] = await Promise.all([
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/order-early-warning?days_ahead=14`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/staff-rating-by-order?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/customer-complaint-rate?months=6`),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/payment-channel-trend?months=6`),
      ]);
      setWarnData(r1.data);
      setStaffData(r2.data);
      setCmpData(r3.data);
      setPayChanData(r4.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [STORE]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>

      {/* 订单风险预警 */}
      <ZCard title="订单付款风险预警">
        {!warnData ? <ZEmpty /> : (
          <div className={styles.warn45Tab}>
            <div className={styles.warn45KpiRow}>
              <div className={`${styles.warn45Kpi} ${warnData.at_risk_count > 0 ? styles.warn45Danger : ''}`}>
                <span className={styles.warn45KpiVal}>{warnData.at_risk_count}</span>
                <span className={styles.warn45KpiLabel}>高风险订单</span>
              </div>
              <div className={styles.warn45Kpi}>
                <span className={styles.warn45KpiVal}>{warnData.total_confirmed}</span>
                <span className={styles.warn45KpiLabel}>14天内宴会</span>
              </div>
            </div>
            {(warnData.warnings || []).length > 0 && (
              <div className={styles.warn45List}>
                <div className={styles.warn45Header}>
                  <span style={{flex:2}}>订单ID</span>
                  <span style={{flex:1}}>距今</span>
                  <span style={{flex:1}}>未付¥</span>
                </div>
                {(warnData.warnings || []).map((w: any) => (
                  <div key={w.order_id} className={styles.warn45Row}>
                    <span style={{flex:2, fontSize:11}}>{w.order_id}</span>
                    <span style={{flex:1, color:'var(--accent)'}}>{w.days_until}天</span>
                    <span style={{flex:1, fontWeight:600, color:'#e53e3e'}}>
                      {w.unpaid_yuan?.toFixed(0)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </ZCard>

      {/* 员工评分 */}
      <ZCard title="员工评分排行">
        {!staffData || !staffData.staff?.length ? <ZEmpty /> : (
          <div className={styles.staff45Tab}>
            {staffData.top_rated && (
              <div className={styles.staff45Top}>评分最高：<strong>{staffData.top_rated}</strong></div>
            )}
            <div className={styles.staff45List}>
              <div className={styles.staff45Header}>
                <span style={{flex:2}}>员工</span>
                <span style={{flex:1}}>订单数</span>
                <span style={{flex:1}}>评分</span>
              </div>
              {(staffData.staff || []).slice(0, 8).map((s: any) => (
                <div key={s.name} className={styles.staff45Row}>
                  <span style={{flex:2}}>{s.name}</span>
                  <span style={{flex:1}}>{s.order_count}</span>
                  <span style={{flex:1, color:'var(--accent)', fontWeight:600}}>
                    {s.avg_rating?.toFixed(1) ?? '-'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>

      {/* 客户投诉率 */}
      <ZCard title="客户投诉率">
        {!cmpData || cmpData.complaint_rate_pct == null ? <ZEmpty /> : (
          <div className={styles.warn45KpiRow}>
            <div className={`${styles.warn45Kpi} ${cmpData.complaint_rate_pct > 5 ? styles.warn45Danger : ''}`}>
              <span className={styles.warn45KpiVal}>{cmpData.complaint_rate_pct?.toFixed(1)}%</span>
              <span className={styles.warn45KpiLabel}>投诉率</span>
            </div>
            <div className={styles.warn45Kpi}>
              <span className={styles.warn45KpiVal}>{cmpData.complaint_count}</span>
              <span className={styles.warn45KpiLabel}>投诉单数</span>
            </div>
            <div className={styles.warn45Kpi}>
              <span className={styles.warn45KpiVal}>{cmpData.total_completed}</span>
              <span className={styles.warn45KpiLabel}>完成订单</span>
            </div>
          </div>
        )}
      </ZCard>

      {/* 支付渠道 */}
      <ZCard title="支付渠道分布">
        {!payChanData || !payChanData.channels?.length ? <ZEmpty /> : (
          <div className={styles.payChan45Tab}>
            {payChanData.dominant_channel && (
              <div className={styles.payChan45Top}>主要渠道：<strong>{payChanData.dominant_channel}</strong></div>
            )}
            {(payChanData.channels || []).map((c: any) => (
              <div key={c.channel} className={styles.payChan45Row}>
                <span className={styles.payChan45Name}>{c.channel}</span>
                <div className={styles.payChan45Track}>
                  <div className={styles.payChan45Fill} style={{width:`${c.pct}%`}} />
                </div>
                <span className={styles.payChan45Stat}>{c.pct?.toFixed(1)}%</span>
              </div>
            ))}
          </div>
        )}
      </ZCard>
    </div>
  );
}

// ── Phase 46: AdvanceBookingTab ──────────────────────────────────────────────

function AdvanceBookingTab() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const storeId = localStorage.getItem('store_id') || '';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/advance-booking-rate?months=12`);
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  return (
    <div className={styles.p46Wrap}>
      <ZCard title="提前预订天数分布">
        {!data || data.total_orders === 0 ? <ZEmpty /> : (
          <div>
            <div className={styles.p46KpiRow}>
              <div className={styles.p46Kpi}>
                <span className={styles.p46KpiVal}>{data.avg_advance_days ?? '—'}</span>
                <span className={styles.p46KpiLabel}>平均提前天数</span>
              </div>
              <div className={styles.p46Kpi}>
                <span className={styles.p46KpiVal}>{data.total_orders}</span>
                <span className={styles.p46KpiLabel}>统计订单</span>
              </div>
            </div>
            <div className={styles.p46BucketList}>
              {(data.distribution || []).map((b: any) => (
                <div key={b.bucket} className={styles.p46BucketRow}>
                  <span className={styles.p46BucketLabel}>{b.bucket}</span>
                  <div className={styles.p46BucketTrack}>
                    <div className={styles.p46BucketFill}
                      style={{ width: `${b.count / data.total_orders * 100}%` }} />
                  </div>
                  <span className={styles.p46BucketStat}>{b.count} 单</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

// ── Phase 46: CancellationTypeTab ────────────────────────────────────────────

function CancellationTypeTab() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const storeId = localStorage.getItem('store_id') || '';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/cancellation-by-type?months=12`);
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  return (
    <div className={styles.p46Wrap}>
      <ZCard title="按宴会类型取消率">
        {!data || data.total_orders === 0 ? <ZEmpty /> : (
          <div>
            {data.overall_cancel_rate_pct != null && (
              <div className={styles.p46OverallRow}>
                综合取消率：<strong>{data.overall_cancel_rate_pct?.toFixed(1)}%</strong>
              </div>
            )}
            <div className={styles.p46TypeList}>
              {(data.by_type || []).map((t: any) => (
                <div key={t.banquet_type} className={styles.p46TypeRow}>
                  <span className={styles.p46TypeName}>{t.banquet_type}</span>
                  <div className={styles.p46TypeTrack}>
                    <div className={styles.p46TypeFill}
                      style={{ width: `${t.cancel_rate_pct}%` }} />
                  </div>
                  <span className={styles.p46TypeStat}>{t.cancel_rate_pct?.toFixed(1)}%</span>
                  <span className={styles.p46TypeCount}>({t.cancelled}/{t.total})</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

// ── Phase 47: MonthlyRevenueTrendTab ─────────────────────────────────────────

function MonthlyRevenueTrendTab() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const storeId = localStorage.getItem('store_id') || '';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/monthly-revenue-trend?months=12`);
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  const maxRev = data?.monthly?.length
    ? Math.max(...data.monthly.map((m: any) => m.revenue_yuan))
    : 1;

  return (
    <div className={styles.p47Wrap}>
      <ZCard title="月度宴会收入趋势">
        {!data || data.total_orders === 0 ? <ZEmpty /> : (
          <div>
            <div className={styles.p47KpiRow}>
              <div className={styles.p47Kpi}>
                <span className={styles.p47KpiVal}>¥{data.total_revenue_yuan?.toLocaleString()}</span>
                <span className={styles.p47KpiLabel}>周期总收入</span>
              </div>
              <div className={styles.p47Kpi}>
                <span className={styles.p47KpiVal}>{data.peak_month ?? '—'}</span>
                <span className={styles.p47KpiLabel}>收入峰值月</span>
              </div>
            </div>
            <div className={styles.p47BarChart}>
              {(data.monthly || []).map((m: any) => (
                <div key={m.month} className={styles.p47BarCol}>
                  <div className={styles.p47BarTrack}>
                    <div
                      className={styles.p47BarFill}
                      style={{ height: `${(m.revenue_yuan / maxRev) * 100}%` }}
                    />
                  </div>
                  <span className={styles.p47BarLabel}>{m.month.slice(5)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

// ── Phase 47: VipPremiumTab ───────────────────────────────────────────────────

function VipPremiumTab() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const storeId = localStorage.getItem('store_id') || '';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/vip-order-value-premium?months=12`);
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  return (
    <div className={styles.p47Wrap}>
      <ZCard title="VIP客户订单溢价">
        {!data || data.total_orders === 0 ? <ZEmpty /> : (
          <div className={styles.p47PremiumGrid}>
            <div className={styles.p47PremiumCard}>
              <span className={styles.p47PremiumVal}>
                {data.vip_avg_yuan != null ? `¥${data.vip_avg_yuan.toLocaleString()}` : '—'}
              </span>
              <span className={styles.p47PremiumLabel}>VIP 均单</span>
            </div>
            <div className={styles.p47PremiumCard}>
              <span className={styles.p47PremiumVal}>
                {data.normal_avg_yuan != null ? `¥${data.normal_avg_yuan.toLocaleString()}` : '—'}
              </span>
              <span className={styles.p47PremiumLabel}>普通均单</span>
            </div>
            <div className={styles.p47PremiumCard + ' ' + styles.p47PremiumHighlight}>
              <span className={styles.p47PremiumVal}>
                {data.premium_pct != null ? `+${data.premium_pct.toFixed(1)}%` : '—'}
              </span>
              <span className={styles.p47PremiumLabel}>溢价幅度</span>
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

// ── Phase 48: HighValueThresholdTab ──────────────────────────────────────────

function HighValueThresholdTab() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const storeId = localStorage.getItem('store_id') || '';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/high-value-order-threshold?months=12`);
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  return (
    <div className={styles.p48Wrap}>
      <ZCard title="高价值订单阈值">
        {!data || data.total_orders === 0 ? <ZEmpty /> : (
          <div className={styles.p48ThresholdGrid}>
            <div className={styles.p48ThreshCard}>
              <span className={styles.p48ThreshVal}>
                {data.top20_threshold_yuan != null
                  ? `¥${data.top20_threshold_yuan.toLocaleString()}`
                  : '—'}
              </span>
              <span className={styles.p48ThreshLabel}>Top 20% 起点</span>
            </div>
            <div className={styles.p48ThreshCard}>
              <span className={styles.p48ThreshVal}>{data.top20_count ?? '—'}</span>
              <span className={styles.p48ThreshLabel}>高价值订单数</span>
            </div>
            <div className={styles.p48ThreshCard + ' ' + styles.p48ThreshHighlight}>
              <span className={styles.p48ThreshVal}>
                {data.top20_revenue_pct != null
                  ? `${data.top20_revenue_pct.toFixed(1)}%`
                  : '—'}
              </span>
              <span className={styles.p48ThreshLabel}>收入贡献</span>
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

// ── Phase 48: ReferralLeadTab ─────────────────────────────────────────────────

function ReferralLeadTab() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const storeId = localStorage.getItem('store_id') || '';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/referral-lead-rate?months=12`);
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  return (
    <div className={styles.p48Wrap}>
      <ZCard title="转介绍线索分析">
        {!data || data.total_leads === 0 ? <ZEmpty /> : (
          <div>
            <div className={styles.p48RefKpiRow}>
              <div className={styles.p48RefKpi}>
                <span className={styles.p48RefKpiVal}>{data.referral_count ?? 0}</span>
                <span className={styles.p48RefKpiLabel}>转介绍线索</span>
              </div>
              <div className={styles.p48RefKpi}>
                <span className={styles.p48RefKpiVal}>
                  {data.referral_rate_pct != null ? `${data.referral_rate_pct.toFixed(1)}%` : '—'}
                </span>
                <span className={styles.p48RefKpiLabel}>占总线索比</span>
              </div>
              <div className={styles.p48RefKpi + ' ' + styles.p48RefHighlight}>
                <span className={styles.p48RefKpiVal}>
                  {data.referral_win_rate_pct != null ? `${data.referral_win_rate_pct.toFixed(1)}%` : '—'}
                </span>
                <span className={styles.p48RefKpiLabel}>转化率</span>
              </div>
            </div>
            <div className={styles.p48RefTotal}>
              共 {data.total_leads} 条线索，其中转介绍 {data.referral_count} 条
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

// ── Phase 49: SatisfactionTrendTab ───────────────────────────────────────────

function SatisfactionTrendTab() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const storeId = localStorage.getItem('store_id') || '';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/satisfaction-trend?months=12`);
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  const maxCount = data?.monthly?.length
    ? Math.max(...data.monthly.map((m: any) => m.count), 1)
    : 1;

  return (
    <div className={styles.p49Wrap}>
      <ZCard title="客户满意度月度趋势">
        {!data || data.total_reviews === 0 ? <ZEmpty /> : (
          <div>
            <div className={styles.p49KpiRow}>
              <div className={styles.p49Kpi}>
                <span className={styles.p49KpiVal}>{data.overall_avg?.toFixed(2) ?? '—'}</span>
                <span className={styles.p49KpiLabel}>综合评分</span>
              </div>
              <div className={styles.p49Kpi}>
                <span className={styles.p49KpiVal}>{data.total_reviews}</span>
                <span className={styles.p49KpiLabel}>总评价数</span>
              </div>
            </div>
            <div className={styles.p49MonthList}>
              {(data.monthly || []).map((m: any) => (
                <div key={m.month} className={styles.p49MonthRow}>
                  <span className={styles.p49MonthLabel}>{m.month.slice(5)}</span>
                  <div className={styles.p49MonthTrack}>
                    <div
                      className={styles.p49MonthFill}
                      style={{ width: `${(m.avg_rating / 5) * 100}%` }}
                    />
                  </div>
                  <span className={styles.p49MonthStat}>{m.avg_rating?.toFixed(1)} ★</span>
                  <span className={styles.p49MonthCount}>({m.count})</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

// ── Phase 49: ReviewScoreDistTab ──────────────────────────────────────────────

function ReviewScoreDistTab() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const storeId = localStorage.getItem('store_id') || '';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/review-score-distribution?months=12`);
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  const STARS = ['★★★★★','★★★★☆','★★★☆☆','★★☆☆☆','★☆☆☆☆'];

  return (
    <div className={styles.p49Wrap}>
      <ZCard title="评分分布">
        {!data || data.total_reviews === 0 ? <ZEmpty /> : (
          <div>
            <div className={styles.p49ScoreHeader}>
              <span className={styles.p49ScoreAvg}>{data.avg_score?.toFixed(2)}</span>
              <span className={styles.p49ScoreStars}>/ 5.0</span>
              <ZBadge label={`五星 ${data.five_star_pct?.toFixed(1)}%`} color="green" />
            </div>
            <div className={styles.p49ScoreList}>
              {(data.distribution || []).map((d: any, i: number) => (
                <div key={d.score} className={styles.p49ScoreRow}>
                  <span className={styles.p49ScoreLabel}>{STARS[5 - d.score] ?? d.score + '星'}</span>
                  <div className={styles.p49ScoreTrack}>
                    <div className={styles.p49ScoreFill} style={{ width: `${d.pct}%` }} />
                  </div>
                  <span className={styles.p49ScoreStat}>{d.count}条</span>
                  <span className={styles.p49ScorePct}>{d.pct}%</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

// ── Phase 50: WeekendVsWeekdayTab ─────────────────────────────────────────────

function WeekendVsWeekdayTab() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const storeId = localStorage.getItem('store_id') || '';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/weekend-vs-weekday?months=12`);
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  return (
    <div className={styles.p50Wrap}>
      <ZCard title="周末 vs 工作日对比">
        {!data || data.total_orders === 0 ? <ZEmpty /> : (
          <div>
            <div className={styles.p50RatioBar}>
              <div
                className={styles.p50RatioWeekend}
                style={{ width: `${data.weekend_ratio_pct ?? 0}%` }}
              />
            </div>
            <div className={styles.p50RatioLabels}>
              <span>周末 {data.weekend_ratio_pct?.toFixed(1)}%</span>
              <span>工作日 {(100 - (data.weekend_ratio_pct ?? 0)).toFixed(1)}%</span>
            </div>
            <div className={styles.p50CompareGrid}>
              <div className={styles.p50CompareCard}>
                <span className={styles.p50CompareTitle}>周末</span>
                <span className={styles.p50CompareVal}>{data.weekend?.count ?? 0} 单</span>
                <span className={styles.p50CompareSub}>
                  ¥{data.weekend?.avg_yuan?.toLocaleString() ?? '—'} / 单
                </span>
              </div>
              <div className={styles.p50CompareCard}>
                <span className={styles.p50CompareTitle}>工作日</span>
                <span className={styles.p50CompareVal}>{data.weekday?.count ?? 0} 单</span>
                <span className={styles.p50CompareSub}>
                  ¥{data.weekday?.avg_yuan?.toLocaleString() ?? '—'} / 单
                </span>
              </div>
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

// ── Phase 50: QuarterlyRevenueTab ─────────────────────────────────────────────

function QuarterlyRevenueTab() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const storeId = localStorage.getItem('store_id') || '';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/quarterly-revenue?months=12`);
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  const maxRev = data?.quarters?.length
    ? Math.max(...data.quarters.map((q: any) => q.revenue_yuan), 1)
    : 1;

  return (
    <div className={styles.p50Wrap}>
      <ZCard title="季度收入分析">
        {!data || data.total_orders === 0 ? <ZEmpty /> : (
          <div>
            {data.best_quarter && (
              <div className={styles.p50BestQ}>
                最优季度：<strong>{data.best_quarter}</strong>
              </div>
            )}
            <div className={styles.p50QBarChart}>
              {(data.quarters || []).map((q: any) => (
                <div key={q.quarter} className={styles.p50QBarCol}>
                  <div className={styles.p50QBarTrack}>
                    <div
                      className={styles.p50QBarFill + (q.quarter === data.best_quarter ? ' ' + styles.p50QBarBest : '')}
                      style={{ height: `${(q.revenue_yuan / maxRev) * 100}%` }}
                    />
                  </div>
                  <span className={styles.p50QBarLabel}>{q.quarter.slice(-2)}</span>
                  <span className={styles.p50QBarRev}>¥{(q.revenue_yuan / 10000).toFixed(1)}万</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

// ── Phase 51: TypeRevenueShareTab ─────────────────────────────────────────────

function TypeRevenueShareTab() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const storeId = localStorage.getItem('store_id') || '';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/type-revenue-share?months=12`);
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  return (
    <div className={styles.p51Wrap}>
      <ZCard title="各宴会类型收入占比">
        {!data || data.total_orders === 0 ? <ZEmpty /> : (
          <div>
            <div className={styles.p51TotalRow}>
              总收入：<strong>¥{data.total_revenue_yuan?.toLocaleString()}</strong>
              {data.top_type && <span className={styles.p51TopBadge}>主力：{data.top_type}</span>}
            </div>
            <div className={styles.p51TypeList}>
              {(data.by_type || []).map((t: any) => (
                <div key={t.banquet_type} className={styles.p51TypeRow}>
                  <span className={styles.p51TypeName}>{t.banquet_type}</span>
                  <div className={styles.p51TypeTrack}>
                    <div className={styles.p51TypeFill}
                      style={{ width: `${t.revenue_share_pct}%` }} />
                  </div>
                  <span className={styles.p51TypePct}>{t.revenue_share_pct}%</span>
                  <span className={styles.p51TypeRev}>¥{(t.revenue_yuan / 10000).toFixed(1)}万</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

// ── Phase 51: MonthlyLeadConversionTab ────────────────────────────────────────

function MonthlyLeadConversionTab() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const storeId = localStorage.getItem('store_id') || '';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiClient.get(`/api/v1/banquet-agent/stores/${storeId}/monthly-lead-conversion?months=6`);
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton />;

  return (
    <div className={styles.p51Wrap}>
      <ZCard title="月度线索转化率">
        {!data || data.total_leads === 0 ? <ZEmpty /> : (
          <div>
            <div className={styles.p51ConvKpiRow}>
              <div className={styles.p51ConvKpi}>
                <span className={styles.p51ConvKpiVal}>{data.total_leads}</span>
                <span className={styles.p51ConvKpiLabel}>总线索</span>
              </div>
              <div className={styles.p51ConvKpi}>
                <span className={styles.p51ConvKpiVal}>
                  {data.avg_conversion_pct != null ? `${data.avg_conversion_pct.toFixed(1)}%` : '—'}
                </span>
                <span className={styles.p51ConvKpiLabel}>平均转化率</span>
              </div>
            </div>
            <div className={styles.p51ConvMonthList}>
              {(data.monthly || []).map((m: any) => (
                <div key={m.month} className={styles.p51ConvMonthRow}>
                  <span className={styles.p51ConvMonthLabel}>{m.month.slice(5)}</span>
                  <div className={styles.p51ConvTrack}>
                    <div className={styles.p51ConvFill}
                      style={{ width: `${m.conversion_pct}%` }} />
                  </div>
                  <span className={styles.p51ConvStat}>{m.conversion_pct?.toFixed(1)}%</span>
                  <span className={styles.p51ConvCount}>({m.won}/{m.total})</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
}

// ── Phase 52: TypeCancellationRateTab ─────────────────────────────────────────
function TypeCancellationRateTab() {
  const storeId = localStorage.getItem('store_id') || '';
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [months, setMonths] = useState(12);

  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const r = await apiClient.get(
        `/api/v1/banquet-agent/stores/${storeId}/banquet-type-cancellation-rate?months=${months}`
      );
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId, months]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={5} />;
  if (!data || data.total_orders === 0) return <ZEmpty message="暂无订单数据" />;

  return (
    <div className={styles.p52Wrap}>
      <ZCard title="宴会类型取消率分析">
        <div className={styles.p52KpiRow}>
          <div className={styles.p52Kpi}>
            <span className={styles.p52KpiVal}>{data.total_orders}</span>
            <span className={styles.p52KpiLabel}>总订单数</span>
          </div>
          <div className={styles.p52Kpi}>
            <span className={styles.p52KpiVal}>{data.overall_cancellation_pct ?? '—'}%</span>
            <span className={styles.p52KpiLabel}>整体取消率</span>
          </div>
        </div>
        <div className={styles.p52TypeList}>
          {(data.by_type || []).map((t: any) => (
            <div key={t.banquet_type} className={styles.p52TypeRow}>
              <span className={styles.p52TypeName}>{t.banquet_type}</span>
              <div className={styles.p52Track}>
                <div className={styles.p52Fill} style={{ width: `${t.cancellation_pct}%` }} />
              </div>
              <span className={styles.p52Pct}>{t.cancellation_pct}%</span>
              <span className={styles.p52Count}>({t.cancelled}/{t.total})</span>
            </div>
          ))}
        </div>
      </ZCard>
    </div>
  );
}

// ── Phase 52: PeakBookingHourTab ──────────────────────────────────────────────
function PeakBookingHourTab() {
  const storeId = localStorage.getItem('store_id') || '';
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [months, setMonths] = useState(3);

  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const r = await apiClient.get(
        `/api/v1/banquet-agent/stores/${storeId}/peak-booking-hour?months=${months}`
      );
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId, months]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={5} />;
  if (!data || data.total_orders === 0) return <ZEmpty message="暂无预订数据" />;

  const maxCount = Math.max(...(data.by_hour || []).map((h: any) => h.count), 1);

  return (
    <div className={styles.p52Wrap}>
      <ZCard title="预订高峰小时分析">
        <div className={styles.p52KpiRow}>
          <div className={styles.p52Kpi}>
            <span className={styles.p52KpiVal}>{data.total_orders}</span>
            <span className={styles.p52KpiLabel}>总订单数</span>
          </div>
          <div className={styles.p52Kpi}>
            <span className={styles.p52KpiVal}>{data.peak_hour ?? '—'}:00</span>
            <span className={styles.p52KpiLabel}>高峰时段</span>
          </div>
        </div>
        <div className={styles.p52HourChart}>
          {(data.by_hour || []).map((h: any) => (
            <div key={h.hour} className={styles.p52HourCol}>
              <div className={styles.p52HourBar}>
                <div
                  className={styles.p52HourFill}
                  style={{
                    height: `${Math.round(h.count / maxCount * 100)}%`,
                    background: h.hour === data.peak_hour ? 'var(--accent)' : 'var(--accent-muted)',
                  }}
                />
              </div>
              <span className={styles.p52HourLabel}>{h.hour}</span>
            </div>
          ))}
        </div>
      </ZCard>
    </div>
  );
}

// ── Phase 53: CustomerLifetimeValueTab ───────────────────────────────────────
function CustomerLifetimeValueTab() {
  const storeId = localStorage.getItem('store_id') || '';
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [months, setMonths] = useState(24);

  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const r = await apiClient.get(
        `/api/v1/banquet-agent/stores/${storeId}/customer-lifetime-value?months=${months}`
      );
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId, months]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={4} />;
  if (!data || data.total_customers === 0) return <ZEmpty message="暂无客户数据" />;

  return (
    <div className={styles.p53Wrap}>
      <ZCard title="客户生命周期价值 (CLV)">
        <div className={styles.p53KpiRow}>
          <div className={styles.p53Kpi}>
            <span className={styles.p53KpiVal}>{data.total_customers}</span>
            <span className={styles.p53KpiLabel}>客户总数</span>
          </div>
          <div className={styles.p53Kpi}>
            <span className={styles.p53KpiVal}>¥{data.avg_clv_yuan ?? '—'}</span>
            <span className={styles.p53KpiLabel}>平均 CLV</span>
          </div>
          <div className={styles.p53Kpi}>
            <span className={styles.p53KpiVal}>{data.top10_count ?? '—'}</span>
            <span className={styles.p53KpiLabel}>Top 10% 客户</span>
          </div>
        </div>
        {data.top_customer && (
          <div className={styles.p53TopRow}>
            <span className={styles.p53TopLabel}>最高价值客户</span>
            <ZBadge color="accent">{data.top_customer}</ZBadge>
          </div>
        )}
      </ZCard>
    </div>
  );
}

// ── Phase 53: BanquetDatePopularityTab ────────────────────────────────────────
function BanquetDatePopularityTab() {
  const storeId = localStorage.getItem('store_id') || '';
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [months, setMonths] = useState(12);

  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const r = await apiClient.get(
        `/api/v1/banquet-agent/stores/${storeId}/banquet-date-popularity?months=${months}`
      );
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId, months]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={5} />;
  if (!data || data.total_orders === 0) return <ZEmpty message="暂无预订数据" />;

  const maxCount = Math.max(...(data.by_month || []).map((m: any) => m.count), 1);

  return (
    <div className={styles.p53Wrap}>
      <ZCard title="宴会日期受欢迎程度">
        <div className={styles.p53KpiRow}>
          <div className={styles.p53Kpi}>
            <span className={styles.p53KpiVal}>{data.total_orders}</span>
            <span className={styles.p53KpiLabel}>总预订数</span>
          </div>
          <div className={styles.p53Kpi}>
            <span className={styles.p53KpiVal}>{data.peak_month ?? '—'}</span>
            <span className={styles.p53KpiLabel}>最热月份</span>
          </div>
        </div>
        <div className={styles.p53MonthList}>
          {(data.by_month || []).map((m: any) => (
            <div key={m.month} className={styles.p53MonthRow}>
              <span className={styles.p53MonthLabel}>{m.month}</span>
              <div className={styles.p53Track}>
                <div
                  className={styles.p53Fill}
                  style={{
                    width: `${Math.round(m.count / maxCount * 100)}%`,
                    background: m.month === data.peak_month ? 'var(--accent)' : 'var(--accent-muted)',
                  }}
                />
              </div>
              <span className={styles.p53Count}>{m.count}</span>
            </div>
          ))}
        </div>
      </ZCard>
    </div>
  );
}

// ── Phase 54: PaymentMethodPreferenceTab ─────────────────────────────────────
function PaymentMethodPreferenceTab() {
  const storeId = localStorage.getItem('store_id') || '';
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [months, setMonths] = useState(6);

  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const r = await apiClient.get(
        `/api/v1/banquet-agent/stores/${storeId}/payment-method-preference?months=${months}`
      );
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId, months]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={4} />;
  if (!data || data.total_payments === 0) return <ZEmpty message="暂无支付数据" />;

  return (
    <div className={styles.p54Wrap}>
      <ZCard title="支付方式偏好分析">
        <div className={styles.p54KpiRow}>
          <div className={styles.p54Kpi}>
            <span className={styles.p54KpiVal}>{data.total_payments}</span>
            <span className={styles.p54KpiLabel}>总支付笔数</span>
          </div>
          <div className={styles.p54Kpi}>
            <span className={styles.p54KpiVal}>{data.preferred_method ?? '—'}</span>
            <span className={styles.p54KpiLabel}>最常用方式</span>
          </div>
        </div>
        <div className={styles.p54MethodList}>
          {(data.by_method || []).map((m: any) => (
            <div key={m.method} className={styles.p54MethodRow}>
              <span className={styles.p54MethodName}>{m.method}</span>
              <div className={styles.p54Track}>
                <div className={styles.p54Fill} style={{ width: `${m.count_pct}%` }} />
              </div>
              <span className={styles.p54Pct}>{m.count_pct}%</span>
              <span className={styles.p54Count}>{m.count}笔</span>
            </div>
          ))}
        </div>
      </ZCard>
    </div>
  );
}

// ── Phase 54: BanquetSeasonAnalysisTab ────────────────────────────────────────
function BanquetSeasonAnalysisTab() {
  const storeId = localStorage.getItem('store_id') || '';
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [months, setMonths] = useState(12);

  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const r = await apiClient.get(
        `/api/v1/banquet-agent/stores/${storeId}/banquet-season-analysis?months=${months}`
      );
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId, months]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={4} />;
  if (!data || data.total_orders === 0) return <ZEmpty message="暂无订单数据" />;

  const seasonColors: Record<string, string> = {
    春季: '#4ade80', 夏季: '#f59e0b', 秋季: '#f97316', 冬季: '#60a5fa',
  };
  const maxCount = Math.max(...(data.by_season || []).map((s: any) => s.count), 1);

  return (
    <div className={styles.p54Wrap}>
      <ZCard title="宴会季节性分析">
        <div className={styles.p54KpiRow}>
          <div className={styles.p54Kpi}>
            <span className={styles.p54KpiVal}>{data.total_orders}</span>
            <span className={styles.p54KpiLabel}>总订单数</span>
          </div>
          <div className={styles.p54Kpi}>
            <span className={styles.p54KpiVal}>{data.peak_season ?? '—'}</span>
            <span className={styles.p54KpiLabel}>旺季</span>
          </div>
        </div>
        <div className={styles.p54SeasonList}>
          {(data.by_season || []).map((s: any) => (
            <div key={s.season} className={styles.p54SeasonRow}>
              <span className={styles.p54SeasonName}>{s.season}</span>
              <div className={styles.p54Track}>
                <div
                  className={styles.p54Fill}
                  style={{
                    width: `${Math.round(s.count / maxCount * 100)}%`,
                    background: seasonColors[s.season] || 'var(--accent)',
                  }}
                />
              </div>
              <span className={styles.p54Count}>{s.count}单</span>
              <span className={styles.p54Rev}>¥{s.revenue_yuan}</span>
            </div>
          ))}
        </div>
      </ZCard>
    </div>
  );
}

// ── Phase 55: LeadWinLossRatioTab ─────────────────────────────────────────────
function LeadWinLossRatioTab() {
  const storeId = localStorage.getItem('store_id') || '';
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [months, setMonths] = useState(6);

  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const r = await apiClient.get(
        `/api/v1/banquet-agent/stores/${storeId}/lead-win-loss-ratio?months=${months}`
      );
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId, months]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={4} />;
  if (!data || data.total_leads === 0) return <ZEmpty message="暂无线索数据" />;

  return (
    <div className={styles.p55Wrap}>
      <ZCard title="线索赢单/输单比率">
        <div className={styles.p55KpiRow}>
          <div className={styles.p55Kpi}>
            <span className={styles.p55KpiVal}>{data.total_leads}</span>
            <span className={styles.p55KpiLabel}>总线索数</span>
          </div>
          <div className={styles.p55Kpi}>
            <span className={styles.p55KpiVal} style={{ color: 'var(--green,#22c55e)' }}>{data.won}</span>
            <span className={styles.p55KpiLabel}>赢单</span>
          </div>
          <div className={styles.p55Kpi}>
            <span className={styles.p55KpiVal} style={{ color: 'var(--red,#ef4444)' }}>{data.lost}</span>
            <span className={styles.p55KpiLabel}>输单</span>
          </div>
          <div className={styles.p55Kpi}>
            <span className={styles.p55KpiVal}>{data.win_loss_ratio ?? '—'}</span>
            <span className={styles.p55KpiLabel}>赢/输比</span>
          </div>
        </div>
        <div className={styles.p55RatioBar}>
          <div
            className={styles.p55WinFill}
            style={{ width: `${data.win_pct ?? 0}%` }}
            title={`赢单 ${data.win_pct}%`}
          />
          <div
            className={styles.p55LossFill}
            style={{ width: `${data.loss_pct ?? 0}%` }}
            title={`输单 ${data.loss_pct}%`}
          />
        </div>
        <div className={styles.p55RatioLegend}>
          <span className={styles.p55LegendWin}>赢单 {data.win_pct}%</span>
          <span className={styles.p55LegendLoss}>输单 {data.loss_pct}%</span>
        </div>
      </ZCard>
    </div>
  );
}

// ── Phase 55: MonthlyNewCustomersTab ──────────────────────────────────────────
function MonthlyNewCustomersTab() {
  const storeId = localStorage.getItem('store_id') || '';
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [months, setMonths] = useState(12);

  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const r = await apiClient.get(
        `/api/v1/banquet-agent/stores/${storeId}/monthly-new-customers?months=${months}`
      );
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId, months]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={5} />;
  if (!data || data.total_new_customers === 0) return <ZEmpty message="暂无客户数据" />;

  const maxCount = Math.max(...(data.monthly || []).map((m: any) => m.new_customers), 1);

  return (
    <div className={styles.p55Wrap}>
      <ZCard title="月度新客户增长">
        <div className={styles.p55KpiRow}>
          <div className={styles.p55Kpi}>
            <span className={styles.p55KpiVal}>{data.total_new_customers}</span>
            <span className={styles.p55KpiLabel}>新客户总数</span>
          </div>
          <div className={styles.p55Kpi}>
            <span className={styles.p55KpiVal}>{data.peak_month ?? '—'}</span>
            <span className={styles.p55KpiLabel}>新客高峰月</span>
          </div>
        </div>
        <div className={styles.p55MonthList}>
          {(data.monthly || []).map((m: any) => (
            <div key={m.month} className={styles.p55MonthRow}>
              <span className={styles.p55MonthLabel}>{m.month}</span>
              <div className={styles.p55Track}>
                <div
                  className={styles.p55Fill}
                  style={{
                    width: `${Math.round(m.new_customers / maxCount * 100)}%`,
                    background: m.month === data.peak_month ? 'var(--accent)' : 'var(--accent-muted)',
                  }}
                />
              </div>
              <span className={styles.p55Count}>{m.new_customers}</span>
            </div>
          ))}
        </div>
      </ZCard>
    </div>
  );
}

// ── Phase 56: LeadStageFunnelTab ──────────────────────────────────────────────
function LeadStageFunnelTab() {
  const storeId = localStorage.getItem('store_id') || '';
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [months, setMonths] = useState(6);

  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const r = await apiClient.get(
        `/api/v1/banquet-agent/stores/${storeId}/lead-stage-conversion-funnel?months=${months}`
      );
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId, months]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={5} />;
  if (!data || data.total_leads === 0) return <ZEmpty message="暂无线索数据" />;

  const stageLabels: Record<string, string> = {
    new: '初步询价', contacted: '已接触', quoted: '已报价',
    deposit_pending: '待定金', won: '已赢单',
  };
  const maxCount = Math.max(...(data.funnel || []).map((f: any) => f.count), 1);

  return (
    <div className={styles.p56Wrap}>
      <ZCard title="线索阶段转化漏斗">
        <div className={styles.p56KpiRow}>
          <div className={styles.p56Kpi}>
            <span className={styles.p56KpiVal}>{data.total_leads}</span>
            <span className={styles.p56KpiLabel}>总线索数</span>
          </div>
          <div className={styles.p56Kpi}>
            <span className={styles.p56KpiVal}>{data.overall_conversion_pct ?? '—'}%</span>
            <span className={styles.p56KpiLabel}>整体转化率</span>
          </div>
        </div>
        <div className={styles.p56FunnelList}>
          {(data.funnel || []).map((f: any) => (
            <div key={f.stage} className={styles.p56FunnelRow}>
              <span className={styles.p56StageName}>{stageLabels[f.stage] ?? f.stage}</span>
              <div className={styles.p56Track}>
                <div
                  className={styles.p56Fill}
                  style={{
                    width: `${maxCount > 0 ? Math.round(f.count / maxCount * 100) : 0}%`,
                    background: f.stage === 'won' ? 'var(--accent)' : 'var(--accent-muted)',
                  }}
                />
              </div>
              <span className={styles.p56Count}>{f.count}</span>
              <span className={styles.p56Pct}>{f.pct}%</span>
            </div>
          ))}
        </div>
      </ZCard>
    </div>
  );
}

// ── Phase 56: OrderValueTrendTab ──────────────────────────────────────────────
function OrderValueTrendTab() {
  const storeId = localStorage.getItem('store_id') || '';
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [months, setMonths] = useState(12);

  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const r = await apiClient.get(
        `/api/v1/banquet-agent/stores/${storeId}/order-value-trend?months=${months}`
      );
      setData(r.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, [storeId, months]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <ZSkeleton rows={5} />;
  if (!data || data.total_orders === 0) return <ZEmpty message="暂无订单数据" />;

  const maxAvg = Math.max(...(data.monthly || []).map((m: any) => m.avg_yuan), 1);

  return (
    <div className={styles.p56Wrap}>
      <ZCard title="订单客单价月度趋势">
        <div className={styles.p56KpiRow}>
          <div className={styles.p56Kpi}>
            <span className={styles.p56KpiVal}>{data.total_orders}</span>
            <span className={styles.p56KpiLabel}>总订单数</span>
          </div>
          <div className={styles.p56Kpi}>
            <span className={styles.p56KpiVal}>
              {data.trend_direction === 'up' ? '↑ 上升' : data.trend_direction === 'down' ? '↓ 下降' : '—'}
            </span>
            <span className={styles.p56KpiLabel}>趋势</span>
          </div>
        </div>
        <div className={styles.p56MonthList}>
          {(data.monthly || []).map((m: any) => (
            <div key={m.month} className={styles.p56MonthRow}>
              <span className={styles.p56MonthLabel}>{m.month}</span>
              <div className={styles.p56Track}>
                <div
                  className={styles.p56Fill}
                  style={{ width: `${Math.round(m.avg_yuan / maxAvg * 100)}%` }}
                />
              </div>
              <span className={styles.p56Rev}>¥{m.avg_yuan}</span>
              <span className={styles.p56SmCount}>{m.count}单</span>
            </div>
          ))}
        </div>
      </ZCard>
    </div>
  );
}
