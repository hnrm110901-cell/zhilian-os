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

function ResourceTab() {
  const [subTab, setSubTab] = useState<'halls' | 'packages'>('halls');

  return (
    <div className={styles.tabContent}>
      <div className={styles.resChipBar}>
        {(['halls', 'packages'] as const).map(t => (
          <button
            key={t}
            className={`${styles.resChip} ${subTab === t ? styles.resChipActive : ''}`}
            onClick={() => setSubTab(t)}
          >
            {t === 'halls' ? '厅房' : '套餐'}
          </button>
        ))}
      </div>
      <ZCard>
        {subTab === 'halls' ? <HallsSection /> : <PackagesSection />}
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

function AnalyticsTab() {
  const [month,    setMonth]    = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });
  const [funnel,       setFunnel]       = useState<FunnelResp | null>(null);
  const [forecast,     setForecast]     = useState<ForecastBucket[]>([]);
  const [lostData,     setLostData]     = useState<LostReason[]>([]);
  const [receivables,  setReceivables]  = useState<ReceivablesData | null>(null);
  const [loading,      setLoading]      = useState(false);

  const load = useCallback(async (m: string) => {
    setLoading(true);
    try {
      const STORE = localStorage.getItem('store_id') || 'S001';
      const [funnelR, forecastR, lostR, arR] = await Promise.allSettled([
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/funnel`, { params: { month: m } }),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/revenue-forecast`, { params: { months: 3 } }),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/analytics/lost-analysis`, { params: { month: m } }),
        apiClient.get(`/api/v1/banquet-agent/stores/${STORE}/receivables`),
      ]);
      if (funnelR.status === 'fulfilled')   setFunnel(funnelR.value.data);
      if (forecastR.status === 'fulfilled') setForecast(forecastR.value.data?.forecast ?? []);
      if (lostR.status === 'fulfilled')     setLostData(lostR.value.data?.reasons ?? []);
      if (arR.status === 'fulfilled')       setReceivables(arR.value.data);
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
        </>
      )}
    </div>
  );
}

/* ─── Tab7: 客户档案 ─── */

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
export default function HQBanquet() {
  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>宴会经营仪表盘</div>
      </div>
      <ZTabs
        items={[
          { key: 'dashboard', label: '仪表盘',  children: <DashboardTab /> },
          { key: 'pipeline',  label: '销售管道', children: <PipelineTab /> },
          { key: 'calendar',  label: '销控日历', children: <AvailabilityTab /> },
          { key: 'ai',        label: 'AI 建议',  children: <AITab /> },
          { key: 'profit',    label: '利润复盘', children: <ProfitTab /> },
          { key: 'resource',  label: '资源配置', children: <ResourceTab /> },
          { key: 'customers', label: '客户档案', children: <CustomerTab /> },
          { key: 'analytics', label: '转化分析', children: <AnalyticsTab /> },
        ]}
      />
    </div>
  );
}
