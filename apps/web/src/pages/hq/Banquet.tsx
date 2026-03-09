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
  ZCard, ZKpi, ZBadge, ZSkeleton, ZEmpty, ZSelect, ZTabs, ZButton, ZInput,
} from '../../design-system/components';
import apiClient from '../../services/api';
import { handleApiError } from '../../utils/message';
import styles from './Banquet.module.css';

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
  useEffect(() => { loadFunnel(); loadOrders(); }, [loadFunnel, loadOrders]);

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
        ]}
      />
    </div>
  );
}
