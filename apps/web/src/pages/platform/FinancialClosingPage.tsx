/**
 * FinancialClosingPage — /platform/financial-closing
 *
 * 日清日结：自动化每日对账（支付/银行/发票），P&L 汇总，异常告警
 *
 * 后端 API:
 *   POST /api/v1/financial-closing/run              — 执行日结
 *   GET  /api/v1/financial-closing/reports           — 报告列表
 *   GET  /api/v1/financial-closing/reports/:id       — 报告详情
 *   POST /api/v1/financial-closing/reports/:id/rerun — 重新执行
 *   GET  /api/v1/financial-closing/monthly           — 月度汇总
 *   GET  /api/v1/financial-closing/calendar          — 日历视图
 *   GET  /api/v1/financial-closing/anomalies         — 异常告警
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  ZCard, ZBadge, ZButton, ZEmpty, ZSkeleton,
} from '../../design-system/components';
import { apiClient } from '../../services/api';
import styles from './FinancialClosingPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface ClosingReport {
  id: string;
  brand_id: string;
  store_id: string | null;
  closing_date: string;
  status: string;
  total_revenue_yuan: number;
  total_cost_yuan: number;
  gross_profit_yuan: number;
  payment_recon_status: string;
  bank_recon_status: string;
  invoice_status: string;
  tri_recon_match_rate: number | null;
  order_count: number;
  avg_order_yuan: number;
  channel_breakdown: Record<string, { revenue_fen: number; orders: number }>;
  anomalies: AnomalyItem[] | null;
  completed_at: string | null;
  created_at: string | null;
}

interface CalendarDay {
  date: string;
  status: string;
  revenue_yuan: number;
  profit_yuan: number;
  order_count: number;
  report_id: string;
}

interface MonthlySummary {
  year: number;
  month: number;
  total_revenue_yuan: number;
  total_cost_yuan: number;
  total_profit_yuan: number;
  gross_margin_pct: number;
  total_orders: number;
  closing_days: number;
  channel_summary: Record<string, { revenue_yuan: number; orders: number }>;
  daily: DailyRow[];
}

interface DailyRow {
  date: string;
  revenue_yuan: number;
  cost_yuan: number;
  profit_yuan: number;
  order_count: number;
  status: string;
}

interface AnomalyItem {
  type: string;
  description: string;
  amount_fen: number;
  severity?: string;
  closing_date?: string;
  report_id?: string;
  store_id?: string | null;
}

// ── 常量 ─────────────────────────────────────────────────────────────────────

const BRAND_ID = 'default';
const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六'];

const STATUS_LABEL: Record<string, string> = {
  completed: '已完成',
  warning: '有异常',
  error: '执行失败',
  pending: '待执行',
  processing: '执行中',
};

const RECON_LABEL: Record<string, string> = {
  matched: '已匹配',
  has_diff: '有差异',
  pending: '待对账',
  all_issued: '全部开票',
  partial: '部分开票',
  none: '未开票',
};

const ANOMALY_ICON: Record<string, string> = {
  revenue_drop: '\u{1F4C9}',
  payment_mismatch: '\u{1F4B3}',
  bank_mismatch: '\u{1F3E6}',
  unreconciled_amount: '\u{26A0}',
  cost_spike: '\u{1F4C8}',
  system_error: '\u{274C}',
};

const CHANNEL_LABEL: Record<string, string> = {
  dine_in: '堂食',
  eleme: '饿了么',
  meituan: '美团',
  douyin: '抖音',
  wechat: '微信',
  other: '其他',
};

// ── 辅助函数 ─────────────────────────────────────────────────────────────────

function formatYuan(val: number): string {
  return `\u00A5${val.toFixed(2)}`;
}

function getToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function getStatusBadgeClass(status: string): string {
  switch (status) {
    case 'completed': return styles.badgeGreen;
    case 'warning': return styles.badgeYellow;
    case 'error': return styles.badgeRed;
    case 'processing': return styles.badgeBlue;
    default: return styles.badgeGray;
  }
}

function getCalendarDayClass(status: string): string {
  switch (status) {
    case 'completed': return styles.statusCompleted;
    case 'warning': return styles.statusWarning;
    case 'error': return styles.statusError;
    case 'processing': return styles.statusProcessing;
    default: return styles.statusPending;
  }
}

// ── 主组件 ───────────────────────────────────────────────────────────────────

function FinancialClosingPage() {
  const [activeTab, setActiveTab] = useState<'daily' | 'monthly' | 'anomaly'>('daily');

  // 日结报告 Tab
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [runDate, setRunDate] = useState(getToday());
  const [calYear, setCalYear] = useState(new Date().getFullYear());
  const [calMonth, setCalMonth] = useState(new Date().getMonth() + 1);
  const [calendar, setCalendar] = useState<CalendarDay[]>([]);
  const [todayReport, setTodayReport] = useState<ClosingReport | null>(null);

  // 详情抽屉
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [detail, setDetail] = useState<ClosingReport | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // 月度汇总 Tab
  const [monthYear, setMonthYear] = useState(new Date().getFullYear());
  const [monthMonth, setMonthMonth] = useState(new Date().getMonth() + 1);
  const [monthly, setMonthly] = useState<MonthlySummary | null>(null);
  const [monthlyLoading, setMonthlyLoading] = useState(false);

  // 异常告警 Tab
  const [anomalies, setAnomalies] = useState<AnomalyItem[]>([]);
  const [anomalyLoading, setAnomalyLoading] = useState(false);

  // ── 数据加载 ───────────────────────────────────────────────────────────

  const fetchCalendar = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get<{ success: boolean; data: CalendarDay[] }>(
        `/api/v1/financial-closing/calendar?brand_id=${BRAND_ID}&year=${calYear}&month=${calMonth}`
      );
      setCalendar(resp.data);
    } catch {
      setCalendar([]);
    } finally {
      setLoading(false);
    }
  }, [calYear, calMonth]);

  const fetchTodayReport = useCallback(async () => {
    try {
      const today = getToday();
      const resp = await apiClient.get<{ success: boolean; data: { items: ClosingReport[] } }>(
        `/api/v1/financial-closing/reports?brand_id=${BRAND_ID}&start_date=${today}&end_date=${today}&page_size=1`
      );
      setTodayReport(resp.data.items.length > 0 ? resp.data.items[0] : null);
    } catch {
      setTodayReport(null);
    }
  }, []);

  const fetchMonthly = useCallback(async () => {
    setMonthlyLoading(true);
    try {
      const resp = await apiClient.get<{ success: boolean; data: MonthlySummary }>(
        `/api/v1/financial-closing/monthly?brand_id=${BRAND_ID}&year=${monthYear}&month=${monthMonth}`
      );
      setMonthly(resp.data);
    } catch {
      setMonthly(null);
    } finally {
      setMonthlyLoading(false);
    }
  }, [monthYear, monthMonth]);

  const fetchAnomalies = useCallback(async () => {
    setAnomalyLoading(true);
    try {
      const resp = await apiClient.get<{ success: boolean; data: AnomalyItem[] }>(
        `/api/v1/financial-closing/anomalies?brand_id=${BRAND_ID}`
      );
      setAnomalies(resp.data);
    } catch {
      setAnomalies([]);
    } finally {
      setAnomalyLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'daily') {
      fetchCalendar();
      fetchTodayReport();
    } else if (activeTab === 'monthly') {
      fetchMonthly();
    } else if (activeTab === 'anomaly') {
      fetchAnomalies();
    }
  }, [activeTab, fetchCalendar, fetchTodayReport, fetchMonthly, fetchAnomalies]);

  // ── 执行日结 ───────────────────────────────────────────────────────────

  const handleRun = async () => {
    if (!runDate) return;
    setRunning(true);
    try {
      await apiClient.post('/api/v1/financial-closing/run', {
        brand_id: BRAND_ID,
        closing_date: runDate,
      });
      await Promise.all([fetchCalendar(), fetchTodayReport()]);
    } catch {
      // 静默处理
    } finally {
      setRunning(false);
    }
  };

  // ── 查看详情 ───────────────────────────────────────────────────────────

  const openDetail = async (reportId: string) => {
    setDrawerOpen(true);
    setDetailLoading(true);
    try {
      const resp = await apiClient.get<{ success: boolean; data: ClosingReport }>(
        `/api/v1/financial-closing/reports/${reportId}`
      );
      setDetail(resp.data);
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleRerun = async () => {
    if (!detail) return;
    setDetailLoading(true);
    try {
      await apiClient.post(`/api/v1/financial-closing/reports/${detail.id}/rerun`);
      await openDetail(detail.id);
      await fetchCalendar();
    } catch {
      // 静默处理
    }
  };

  // ── 日历构建 ───────────────────────────────────────────────────────────

  const buildCalendarGrid = () => {
    const firstDay = new Date(calYear, calMonth - 1, 1);
    const lastDay = new Date(calYear, calMonth, 0);
    const startPad = firstDay.getDay();
    const totalDays = lastDay.getDate();

    const calendarMap = new Map<string, CalendarDay>();
    for (const d of calendar) {
      calendarMap.set(d.date, d);
    }

    const cells: React.ReactNode[] = [];

    // 前置空白
    for (let i = 0; i < startPad; i++) {
      cells.push(<div key={`pad-${i}`} className={styles.calendarDayEmpty} />);
    }

    // 每日
    for (let d = 1; d <= totalDays; d++) {
      const dateStr = `${calYear}-${String(calMonth).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      const dayData = calendarMap.get(dateStr);

      if (dayData) {
        cells.push(
          <div
            key={dateStr}
            className={`${styles.calendarDay} ${getCalendarDayClass(dayData.status)}`}
            onClick={() => openDetail(dayData.report_id)}
          >
            <div className={styles.calendarDayNum}>{d}</div>
            <div className={styles.calendarDayRevenue}>{formatYuan(dayData.revenue_yuan)}</div>
            <div className={styles.calendarDayOrders}>{dayData.order_count}单</div>
          </div>
        );
      } else {
        cells.push(
          <div key={dateStr} className={styles.calendarDayEmpty}>
            <div className={styles.calendarDayNum} style={{ color: '#d1d5db' }}>{d}</div>
          </div>
        );
      }
    }

    return cells;
  };

  const prevMonth = () => {
    if (calMonth === 1) { setCalYear(calYear - 1); setCalMonth(12); }
    else { setCalMonth(calMonth - 1); }
  };

  const nextMonth = () => {
    if (calMonth === 12) { setCalYear(calYear + 1); setCalMonth(1); }
    else { setCalMonth(calMonth + 1); }
  };

  // ── 渲染：日结报告 Tab ─────────────────────────────────────────────────

  const renderDailyTab = () => (
    <>
      {/* 统计行 */}
      <div className={styles.statsRow}>
        <ZCard className={styles.statCard}>
          <div className={styles.statNumGreen}>
            {todayReport ? formatYuan(todayReport.total_revenue_yuan) : '-'}
          </div>
          <div className={styles.statLabel}>今日营收</div>
        </ZCard>
        <ZCard className={styles.statCard}>
          <div className={styles.statNum}>
            {todayReport ? formatYuan(todayReport.gross_profit_yuan) : '-'}
          </div>
          <div className={styles.statLabel}>今日毛利</div>
        </ZCard>
        <ZCard className={styles.statCard}>
          <div className={todayReport ? getStatusBadgeClass(todayReport.status) : styles.badgeGray}
               style={{ fontSize: 20, fontWeight: 700, padding: '4px 12px' }}>
            {todayReport ? (STATUS_LABEL[todayReport.status] || todayReport.status) : '未执行'}
          </div>
          <div className={styles.statLabel}>今日状态</div>
        </ZCard>
        <ZCard className={styles.statCard}>
          <div className={styles.statNum}>
            {todayReport?.tri_recon_match_rate !== null && todayReport?.tri_recon_match_rate !== undefined
              ? `${todayReport.tri_recon_match_rate}%`
              : '-'}
          </div>
          <div className={styles.statLabel}>对账匹配率</div>
        </ZCard>
      </div>

      {/* 日历视图 */}
      <ZCard>
        <div className={styles.calendarContainer}>
          <div className={styles.calendarNav}>
            <ZButton size="sm" variant="ghost" onClick={prevMonth}>&lt;</ZButton>
            <span className={styles.calendarMonth}>{calYear}年{calMonth}月</span>
            <ZButton size="sm" variant="ghost" onClick={nextMonth}>&gt;</ZButton>
          </div>

          {loading ? (
            <ZSkeleton lines={6} />
          ) : (
            <div className={styles.calendarGrid}>
              {WEEKDAYS.map((w) => (
                <div key={w} className={styles.calendarWeekday}>{w}</div>
              ))}
              {buildCalendarGrid()}
            </div>
          )}
        </div>
      </ZCard>
    </>
  );

  // ── 渲染：月度汇总 Tab ─────────────────────────────────────────────────

  const renderMonthlyTab = () => (
    <>
      {/* 月份选择 */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center' }}>
        <select
          value={monthYear}
          onChange={(e) => setMonthYear(Number(e.target.value))}
          style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
        >
          {[2024, 2025, 2026].map((y) => (
            <option key={y} value={y}>{y}年</option>
          ))}
        </select>
        <select
          value={monthMonth}
          onChange={(e) => setMonthMonth(Number(e.target.value))}
          style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
        >
          {Array.from({ length: 12 }, (_, i) => (
            <option key={i + 1} value={i + 1}>{i + 1}月</option>
          ))}
        </select>
      </div>

      {monthlyLoading ? (
        <ZSkeleton lines={8} />
      ) : !monthly ? (
        <ZEmpty description="暂无月度数据" />
      ) : (
        <>
          {/* P&L 汇总 */}
          <div className={styles.plSummary}>
            <ZCard className={styles.plCard}>
              <div className={styles.plLabel}>月度营收</div>
              <div className={styles.plValue}>{formatYuan(monthly.total_revenue_yuan)}</div>
            </ZCard>
            <ZCard className={styles.plCard}>
              <div className={styles.plLabel}>月度成本</div>
              <div className={styles.plValueRed}>{formatYuan(monthly.total_cost_yuan)}</div>
            </ZCard>
            <ZCard className={styles.plCard}>
              <div className={styles.plLabel}>月度毛利</div>
              <div className={styles.plValueGreen}>{formatYuan(monthly.total_profit_yuan)}</div>
            </ZCard>
            <ZCard className={styles.plCard}>
              <div className={styles.plLabel}>毛利率</div>
              <div className={styles.plValue}>{monthly.gross_margin_pct}%</div>
            </ZCard>
          </div>

          {/* 渠道明细 */}
          <ZCard style={{ marginBottom: 16 }}>
            <h3 style={{ margin: '0 0 8px', fontSize: 15, fontWeight: 600 }}>渠道分布</h3>
            <table className={styles.channelTable}>
              <thead>
                <tr>
                  <th>渠道</th>
                  <th>营收</th>
                  <th>订单数</th>
                  <th>占比</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(monthly.channel_summary).map(([ch, data]) => (
                  <tr key={ch}>
                    <td>{CHANNEL_LABEL[ch] || ch}</td>
                    <td>{formatYuan(data.revenue_yuan)}</td>
                    <td>{data.orders}</td>
                    <td>
                      {monthly.total_revenue_yuan > 0
                        ? `${(data.revenue_yuan / monthly.total_revenue_yuan * 100).toFixed(1)}%`
                        : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ZCard>

          {/* 每日明细 */}
          <ZCard>
            <h3 style={{ margin: '0 0 8px', fontSize: 15, fontWeight: 600 }}>
              每日明细（{monthly.closing_days}天已结）
            </h3>
            <div style={{ overflowX: 'auto' }}>
              <table className={styles.dailyTable}>
                <thead>
                  <tr>
                    <th>日期</th>
                    <th>营收</th>
                    <th>成本</th>
                    <th>毛利</th>
                    <th>订单数</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {monthly.daily.map((row) => (
                    <tr key={row.date}>
                      <td>{row.date.slice(5)}</td>
                      <td>{formatYuan(row.revenue_yuan)}</td>
                      <td>{formatYuan(row.cost_yuan)}</td>
                      <td style={{ color: row.profit_yuan >= 0 ? '#10b981' : '#ef4444' }}>
                        {formatYuan(row.profit_yuan)}
                      </td>
                      <td>{row.order_count}</td>
                      <td>
                        <span className={getStatusBadgeClass(row.status)}>
                          {STATUS_LABEL[row.status] || row.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </ZCard>
        </>
      )}
    </>
  );

  // ── 渲染：异常告警 Tab ─────────────────────────────────────────────────

  const renderAnomalyTab = () => (
    <>
      {anomalyLoading ? (
        <ZSkeleton lines={6} />
      ) : anomalies.length === 0 ? (
        <ZEmpty description="暂无异常告警" />
      ) : (
        <div className={styles.anomalyList}>
          {anomalies.map((a, i) => {
            const iconClass =
              a.severity === 'high' ? styles.iconHigh :
              a.severity === 'medium' ? styles.iconMedium :
              styles.iconLow;

            return (
              <div key={`${a.report_id}-${i}`} className={styles.anomalyCard}>
                <div className={iconClass}>
                  {ANOMALY_ICON[a.type] || '\u{26A0}'}
                </div>
                <div className={styles.anomalyBody}>
                  <div className={styles.anomalyDesc}>{a.description}</div>
                  <div className={styles.anomalyMeta}>
                    <span>{a.closing_date}</span>
                    {a.store_id && <span>门店: {a.store_id}</span>}
                    <span className={getStatusBadgeClass(a.severity === 'high' ? 'error' : 'warning')}>
                      {a.severity === 'high' ? '高危' : a.severity === 'medium' ? '中等' : '低'}
                    </span>
                  </div>
                </div>
                {a.amount_fen > 0 && (
                  <div className={styles.anomalyAmount}>
                    {formatYuan(a.amount_fen / 100)}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </>
  );

  // ── 渲染 ───────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>日清日结</h1>
          <p className={styles.pageSubtitle}>
            自动化每日对账：支付 / 银行 / 发票三方匹配，P&L 汇总与异常检测
          </p>
        </div>
        <div className={styles.headerActions}>
          <input
            type="date"
            value={runDate}
            onChange={(e) => setRunDate(e.target.value)}
            style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
          />
          <ZButton variant="primary" onClick={handleRun} disabled={running}>
            {running ? '执行中...' : '执行日结'}
          </ZButton>
        </div>
      </div>

      {/* Tabs */}
      <div className={styles.tabs}>
        <button
          className={activeTab === 'daily' ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab('daily')}
        >
          日结报告
        </button>
        <button
          className={activeTab === 'monthly' ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab('monthly')}
        >
          月度汇总
        </button>
        <button
          className={activeTab === 'anomaly' ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab('anomaly')}
        >
          异常告警
        </button>
      </div>

      {/* Tab 内容 */}
      {activeTab === 'daily' && renderDailyTab()}
      {activeTab === 'monthly' && renderMonthlyTab()}
      {activeTab === 'anomaly' && renderAnomalyTab()}

      {/* 详情抽屉 */}
      {drawerOpen && (
        <>
          <div className={styles.detailOverlay} onClick={() => setDrawerOpen(false)} />
          <div className={styles.detailDrawer}>
            <div className={styles.detailHeader}>
              <h3 className={styles.detailTitle}>日结报告详情</h3>
              <ZButton size="sm" variant="ghost" onClick={() => setDrawerOpen(false)}>关闭</ZButton>
            </div>

            {detailLoading ? (
              <ZSkeleton lines={10} />
            ) : detail ? (
              <>
                {/* 基本信息 */}
                <div className={styles.detailSection}>
                  <div className={styles.detailSectionTitle}>基本信息</div>
                  <div className={styles.detailGrid}>
                    <div className={styles.detailItem}>
                      <span className={styles.detailLabel}>日期</span>
                      <span className={styles.detailValue}>{detail.closing_date}</span>
                    </div>
                    <div className={styles.detailItem}>
                      <span className={styles.detailLabel}>状态</span>
                      <span className={getStatusBadgeClass(detail.status)}>
                        {STATUS_LABEL[detail.status] || detail.status}
                      </span>
                    </div>
                    <div className={styles.detailItem}>
                      <span className={styles.detailLabel}>门店</span>
                      <span className={styles.detailValue}>{detail.store_id || '全品牌'}</span>
                    </div>
                    <div className={styles.detailItem}>
                      <span className={styles.detailLabel}>完成时间</span>
                      <span className={styles.detailValue}>{detail.completed_at || '-'}</span>
                    </div>
                  </div>
                </div>

                {/* 财务数据 */}
                <div className={styles.detailSection}>
                  <div className={styles.detailSectionTitle}>财务数据</div>
                  <div className={styles.detailGrid}>
                    <div className={styles.detailItem}>
                      <span className={styles.detailLabel}>营收</span>
                      <span className={styles.detailValue}>{formatYuan(detail.total_revenue_yuan)}</span>
                    </div>
                    <div className={styles.detailItem}>
                      <span className={styles.detailLabel}>成本</span>
                      <span className={styles.detailValue}>{formatYuan(detail.total_cost_yuan)}</span>
                    </div>
                    <div className={styles.detailItem}>
                      <span className={styles.detailLabel}>毛利</span>
                      <span className={styles.detailValue} style={{ color: detail.gross_profit_yuan >= 0 ? '#10b981' : '#ef4444' }}>
                        {formatYuan(detail.gross_profit_yuan)}
                      </span>
                    </div>
                    <div className={styles.detailItem}>
                      <span className={styles.detailLabel}>订单数</span>
                      <span className={styles.detailValue}>{detail.order_count}</span>
                    </div>
                    <div className={styles.detailItem}>
                      <span className={styles.detailLabel}>客单价</span>
                      <span className={styles.detailValue}>{formatYuan(detail.avg_order_yuan)}</span>
                    </div>
                  </div>
                </div>

                {/* 对账状态 */}
                <div className={styles.detailSection}>
                  <div className={styles.detailSectionTitle}>对账状态</div>
                  <div className={styles.detailGrid}>
                    <div className={styles.detailItem}>
                      <span className={styles.detailLabel}>支付对账</span>
                      <span className={
                        detail.payment_recon_status === 'matched' ? styles.badgeGreen :
                        detail.payment_recon_status === 'has_diff' ? styles.badgeRed :
                        styles.badgeGray
                      }>
                        {RECON_LABEL[detail.payment_recon_status] || detail.payment_recon_status}
                      </span>
                    </div>
                    <div className={styles.detailItem}>
                      <span className={styles.detailLabel}>银行对账</span>
                      <span className={
                        detail.bank_recon_status === 'matched' ? styles.badgeGreen :
                        detail.bank_recon_status === 'has_diff' ? styles.badgeRed :
                        styles.badgeGray
                      }>
                        {RECON_LABEL[detail.bank_recon_status] || detail.bank_recon_status}
                      </span>
                    </div>
                    <div className={styles.detailItem}>
                      <span className={styles.detailLabel}>发票</span>
                      <span className={
                        detail.invoice_status === 'all_issued' ? styles.badgeGreen :
                        detail.invoice_status === 'partial' ? styles.badgeYellow :
                        styles.badgeGray
                      }>
                        {RECON_LABEL[detail.invoice_status] || detail.invoice_status}
                      </span>
                    </div>
                    <div className={styles.detailItem}>
                      <span className={styles.detailLabel}>三角匹配率</span>
                      <span className={styles.detailValue}>
                        {detail.tri_recon_match_rate !== null ? `${detail.tri_recon_match_rate}%` : '-'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* 渠道明细 */}
                {detail.channel_breakdown && Object.keys(detail.channel_breakdown).length > 0 && (
                  <div className={styles.detailSection}>
                    <div className={styles.detailSectionTitle}>渠道明细</div>
                    {Object.entries(detail.channel_breakdown).map(([ch, data]) => (
                      <div key={ch} className={styles.detailItem}>
                        <span className={styles.detailLabel}>{CHANNEL_LABEL[ch] || ch}</span>
                        <span className={styles.detailValue}>
                          {formatYuan(data.revenue_fen / 100)} / {data.orders}单
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {/* 异常 */}
                {detail.anomalies && detail.anomalies.length > 0 && (
                  <div className={styles.detailSection}>
                    <div className={styles.detailSectionTitle}>异常告警</div>
                    {detail.anomalies.map((a, i) => (
                      <div key={i} style={{
                        padding: '8px 12px', marginBottom: 6, borderRadius: 6,
                        background: a.severity === 'high' ? '#fef2f2' : '#fffbeb',
                        fontSize: 13,
                      }}>
                        <span style={{ marginRight: 8 }}>{ANOMALY_ICON[a.type] || '\u{26A0}'}</span>
                        {a.description}
                        {a.amount_fen > 0 && (
                          <span style={{ marginLeft: 8, fontWeight: 600, color: '#ef4444' }}>
                            {formatYuan(a.amount_fen / 100)}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* 操作 */}
                <div style={{ marginTop: 16 }}>
                  <ZButton variant="primary" onClick={handleRerun}>
                    重新执行日结
                  </ZButton>
                </div>
              </>
            ) : (
              <ZEmpty description="加载失败" />
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default FinancialClosingPage;
