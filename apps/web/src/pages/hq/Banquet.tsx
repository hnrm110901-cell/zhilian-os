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
      setDashboard(resp.data);
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
      setFunnel(resp.data);
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
      setOrders(Array.isArray(resp.data) ? resp.data : (resp.data?.items ?? []));
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
              itemStyle: { color: '#ff6b2c' },
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
                  { name: '实际', type: 'bar' as const,  data: targetTrend.map(r => r.actual_yuan), itemStyle: { color: 'var(--accent, #FF6B2C)' } },
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
            onChange={e => setTargetInput(e.target.value)}
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
                onChange={e => setRecPeople(e.target.value)}
                placeholder="如：200"
              />
            </div>
            <div className={styles.aiField}>
              <label className={styles.aiLabel}>预算上限（元）</label>
              <ZInput
                type="number"
                value={recBudget}
                onChange={e => setRecBudget(e.target.value)}
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
                onChange={e => setHallDate(e.target.value)}
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
                onChange={e => setHallPeople(e.target.value)}
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
            <ZInput value={fName} onChange={e => setFName(e.target.value)} placeholder="如：一号宴会厅" />
          </div>
          <div className={styles.resField}>
            <label className={styles.resLabel}>厅房类型</label>
            <ZSelect value={fType} options={HALL_TYPE_OPTIONS} onChange={v => setFType(v as string)} />
          </div>
          <div className={styles.resFieldRow}>
            <div className={styles.resField}>
              <label className={styles.resLabel}>最多桌数</label>
              <ZInput type="number" value={fMaxTables} onChange={e => setFMaxTables(e.target.value)} placeholder="如：20" />
            </div>
            <div className={styles.resField}>
              <label className={styles.resLabel}>最多人数</label>
              <ZInput type="number" value={fMaxPeople} onChange={e => setFMaxPeople(e.target.value)} placeholder="如：200" />
            </div>
          </div>
          <div className={styles.resFieldRow}>
            <div className={styles.resField}>
              <label className={styles.resLabel}>最低消费（元）</label>
              <ZInput type="number" value={fMinSpend} onChange={e => setFMinSpend(e.target.value)} placeholder="如：20000" />
            </div>
            <div className={styles.resField}>
              <label className={styles.resLabel}>面积（m²，选填）</label>
              <ZInput type="number" value={fArea} onChange={e => setFArea(e.target.value)} placeholder="如：500" />
            </div>
          </div>
          <div className={styles.resField}>
            <label className={styles.resLabel}>备注（选填）</label>
            <ZInput value={fDesc} onChange={e => setFDesc(e.target.value)} placeholder="厅房介绍…" />
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
            <ZInput value={fName} onChange={e => setFName(e.target.value)} placeholder="如：经典婚宴套餐" />
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
              <ZInput type="number" value={fPrice} onChange={e => setFPrice(e.target.value)} placeholder="如：30000" />
            </div>
            <div className={styles.resField}>
              <label className={styles.resLabel}>估算成本（元，选填）</label>
              <ZInput type="number" value={fCost} onChange={e => setFCost(e.target.value)} placeholder="如：12000" />
            </div>
          </div>
          <div className={styles.resFieldRow}>
            <div className={styles.resField}>
              <label className={styles.resLabel}>最少人数</label>
              <ZInput type="number" value={fPeopleMin} onChange={e => setFPeopleMin(e.target.value)} placeholder="1" />
            </div>
            <div className={styles.resField}>
              <label className={styles.resLabel}>最多人数</label>
              <ZInput type="number" value={fPeopleMax} onChange={e => setFPeopleMax(e.target.value)} placeholder="999" />
            </div>
          </div>
          <div className={styles.resField}>
            <label className={styles.resLabel}>套餐描述（选填）</label>
            <ZInput value={fDesc} onChange={e => setFDesc(e.target.value)} placeholder="套餐包含内容…" />
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
            <ZInput value={fName} onChange={e => setFName(e.target.value)} placeholder="如：婚宴标准执行模板" />
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
                    onChange={e => updateTaskDef(i, 'task_name', e.target.value)}
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
                    onChange={e => updateTaskDef(i, 'days_before', parseInt(e.target.value, 10) || 1)}
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
      itemStyle: { color: 'var(--accent, #ff6b2c)' },
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
          onChange={e => setMonth(e.target.value)}
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
} */

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
          onChange={e => setQ(e.target.value)}
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
        <ZInput type="month" value={month} onChange={e => setMonth(e.target.value)} />
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
        ]}
      />
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
