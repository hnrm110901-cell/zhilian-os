/**
 * CommandCenterPage — /platform/command-center
 *
 * 指挥中心：跨系统实时运营仪表盘（Palantir 作战指挥台）
 * 后端 API:
 *   GET  /api/v1/command-center/overview      — 实时概览
 *   GET  /api/v1/command-center/event-stream   — 跨系统事件流
 *   GET  /api/v1/command-center/kpi-matrix     — KPI 矩阵
 *   POST /api/v1/command-center/dispatch       — 行动调度
 *   GET  /api/v1/command-center/pulse          — 系统脉搏
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiClient } from '../../services/api';
import styles from './CommandCenterPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface LiveOverview {
  timestamp: string;
  brand_id: string;
  revenue_today_yuan: number;
  order_count_today: number;
  avg_order_value_yuan: number;
  integration_health: IntegrationHealth;
  compliance_score: number;
  compliance_grade: string;
  active_alerts: number;
  pending_procurement: number;
  unread_reviews: number;
  unresolved_reconciliation: number;
}

interface IntegrationHealth {
  total: number;
  healthy: number;
  degraded: number;
  error: number;
  rate: number;
}

interface EventItem {
  timestamp: string;
  source_system: string;
  event_type: string;
  title: string;
  detail: string;
  severity: string;
  entity_id: string;
}

interface KpiMatrix {
  revenue: {
    daily_yuan: number;
    weekly_yuan: number;
    monthly_yuan: number;
  };
  operations: {
    order_fulfillment_rate: number;
    completed_orders: number;
    total_orders: number;
  };
  compliance: {
    overall_score: number;
    grade: string;
    active_alerts: number;
  };
  integration: {
    total_integrations: number;
    sync_count_today: number;
    error_count_today: number;
    success_rate: number;
  };
}

interface SystemPulse {
  total_brands: number;
  total_stores: number;
  total_orders_today: number;
  total_revenue_today_yuan: number;
  integration_summary: Record<string, number>;
  recent_errors: Array<{
    integration: string;
    error: string;
    at: string | null;
  }>;
}

interface DispatchResult {
  success: boolean;
  message: string;
  [key: string]: unknown;
}

// ── 常量 ─────────────────────────────────────────────────────────────────────

const BRAND_ID = 'BRD_CZYZ0001';
const REFRESH_OVERVIEW_MS = 15_000;
const REFRESH_EVENTS_MS = 10_000;

const ACTION_DEFS = [
  { key: 'sync_all', label: '全量同步', icon: '⟳' },
  { key: 'run_closing', label: '执行日结', icon: '☰' },
  { key: 'check_procurement', label: '检查采购', icon: '⊞' },
  { key: 'generate_alerts', label: '生成告警', icon: '⚡' },
] as const;

// ── 工具函数 ──────────────────────────────────────────────────────────────────

function formatTime(iso: string | null | undefined): string {
  if (!iso) return '--';
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
}

function formatCurrency(yuan: number): string {
  if (yuan >= 10000) return `${(yuan / 10000).toFixed(1)}万`;
  return yuan.toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function severityDotClass(severity: string): string {
  if (severity === 'critical') return styles.dotCritical;
  if (severity === 'warning' || severity === 'high') return styles.dotWarning;
  return styles.dotInfo;
}

function healthDotClass(status: string): string {
  if (status === 'healthy') return styles.healthDotHealthy;
  if (status === 'degraded') return styles.healthDotDegraded;
  if (status === 'error') return styles.healthDotError;
  return styles.healthDotDisconnected;
}

// ── 组件 ─────────────────────────────────────────────────────────────────────

const CommandCenterPage: React.FC = () => {
  const [overview, setOverview] = useState<LiveOverview | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [kpis, setKpis] = useState<KpiMatrix | null>(null);
  const [pulse, setPulse] = useState<SystemPulse | null>(null);
  const [loading, setLoading] = useState(true);
  const [clock, setClock] = useState(new Date());
  const [dispatchLoading, setDispatchLoading] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const overviewTimer = useRef<ReturnType<typeof setInterval>>(undefined);
  const eventsTimer = useRef<ReturnType<typeof setInterval>>(undefined);
  const clockTimer = useRef<ReturnType<typeof setInterval>>(undefined);

  // ── 数据拉取 ────────────────────────────────────────────────────────────

  const fetchOverview = useCallback(async () => {
    try {
      const data = await apiClient.get<LiveOverview>(
        `/api/v1/command-center/overview?brand_id=${BRAND_ID}`
      );
      setOverview(data);
    } catch {
      /* 静默降级 */
    }
  }, []);

  const fetchEvents = useCallback(async () => {
    try {
      const data = await apiClient.get<EventItem[]>(
        `/api/v1/command-center/event-stream?brand_id=${BRAND_ID}&limit=50`
      );
      setEvents(data);
    } catch {
      /* 静默降级 */
    }
  }, []);

  const fetchKpis = useCallback(async () => {
    try {
      const data = await apiClient.get<KpiMatrix>(
        `/api/v1/command-center/kpi-matrix?brand_id=${BRAND_ID}`
      );
      setKpis(data);
    } catch {
      /* 静默降级 */
    }
  }, []);

  const fetchPulse = useCallback(async () => {
    try {
      const data = await apiClient.get<SystemPulse>(
        '/api/v1/command-center/pulse'
      );
      setPulse(data);
    } catch {
      /* 静默降级 */
    }
  }, []);

  // ── 初始化 + 定时刷新 ──────────────────────────────────────────────────

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await Promise.allSettled([
        fetchOverview(),
        fetchEvents(),
        fetchKpis(),
        fetchPulse(),
      ]);
      setLoading(false);
    };
    init();

    overviewTimer.current = setInterval(() => {
      fetchOverview();
      fetchKpis();
      fetchPulse();
    }, REFRESH_OVERVIEW_MS);

    eventsTimer.current = setInterval(fetchEvents, REFRESH_EVENTS_MS);

    clockTimer.current = setInterval(() => setClock(new Date()), 1000);

    return () => {
      clearInterval(overviewTimer.current);
      clearInterval(eventsTimer.current);
      clearInterval(clockTimer.current);
    };
  }, [fetchOverview, fetchEvents, fetchKpis, fetchPulse]);

  // ── 行动调度 ────────────────────────────────────────────────────────────

  const handleDispatch = async (actionType: string) => {
    setDispatchLoading(actionType);
    try {
      const result = await apiClient.post<DispatchResult>(
        `/api/v1/command-center/dispatch?brand_id=${BRAND_ID}`,
        { action_type: actionType, params: {} }
      );
      setToast(result.message);
      fetchOverview();
    } catch (err: any) {
      const msg = err?.response?.data?.detail || '操作失败';
      setToast(msg);
    } finally {
      setDispatchLoading(null);
      setTimeout(() => setToast(null), 4000);
    }
  };

  // ── 时钟格式 ────────────────────────────────────────────────────────────

  const clockStr = `${clock.getFullYear()}-${String(clock.getMonth() + 1).padStart(2, '0')}-${String(clock.getDate()).padStart(2, '0')} ${String(clock.getHours()).padStart(2, '0')}:${String(clock.getMinutes()).padStart(2, '0')}:${String(clock.getSeconds()).padStart(2, '0')}`;

  // ── 异常焦点：取事件中 severity 最高的 3 条 ─────────────────────────────

  const anomalies = events
    .filter((e) => e.severity === 'critical' || e.severity === 'warning' || e.severity === 'high')
    .slice(0, 3);

  // ── 集成健康列表（从 pulse） ────────────────────────────────────────────

  const integrationEntries = pulse
    ? Object.entries(pulse.integration_summary).map(([status, count]) => ({
        status,
        count,
      }))
    : [];

  // ── 渲染 ────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.loading}>
          <div className={styles.spinner} />
          正在连接指挥中心...
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      {/* Toast */}
      {toast && (
        <div
          style={{
            position: 'fixed',
            top: 20,
            right: 24,
            zIndex: 1000,
            background: '#0D2029',
            border: '1px solid rgba(255,107,44,0.4)',
            borderRadius: 8,
            padding: '10px 18px',
            fontSize: 13,
            color: '#FF6B2C',
            maxWidth: 400,
          }}
        >
          {toast}
        </div>
      )}

      {/* ── 顶部横幅 ─────────────────────────────────────────────── */}
      <header className={styles.topBanner}>
        <div className={styles.bannerLeft}>
          <div>
            <h1 className={styles.bannerTitle}>指挥中心</h1>
            <p className={styles.bannerSub}>
              跨系统实时运营态势感知
              {pulse && ` | ${pulse.total_stores} 门店在线`}
            </p>
          </div>
        </div>
        <div className={styles.bannerRight}>
          <span className={styles.clock}>{clockStr}</span>
          <div className={styles.statusDot} title="系统正常" />
        </div>
      </header>

      {/* ── KPI 行 ───────────────────────────────────────────────── */}
      <section className={styles.kpiRow}>
        <div className={styles.kpiCard}>
          <span className={styles.kpiLabel}>今日营收</span>
          <span className={styles.kpiValue}>
            <span className={styles.kpiAccent}>
              {overview ? `¥${formatCurrency(overview.revenue_today_yuan)}` : '--'}
            </span>
          </span>
        </div>

        <div className={styles.kpiCard}>
          <span className={styles.kpiLabel}>订单数</span>
          <span className={styles.kpiValue}>
            {overview?.order_count_today ?? '--'}
            <span className={styles.kpiUnit}>单</span>
          </span>
        </div>

        <div className={styles.kpiCard}>
          <span className={styles.kpiLabel}>客单价</span>
          <span className={styles.kpiValue}>
            ¥{overview?.avg_order_value_yuan?.toFixed(0) ?? '--'}
          </span>
        </div>

        <div className={styles.kpiCard}>
          <span className={styles.kpiLabel}>合规评分</span>
          <span className={styles.kpiValue}>
            <span className={
              (overview?.compliance_score ?? 0) >= 85
                ? styles.kpiAccent
                : (overview?.compliance_score ?? 0) >= 55
                  ? styles.kpiWarn
                  : styles.kpiDanger
            }>
              {overview?.compliance_score ?? '--'}
            </span>
            <span className={styles.kpiUnit}>{overview?.compliance_grade ?? ''}</span>
          </span>
        </div>

        <div className={styles.kpiCard}>
          <span className={styles.kpiLabel}>集成健康</span>
          <span className={styles.kpiValue}>
            <span className={
              (overview?.integration_health?.rate ?? 100) >= 90
                ? styles.kpiAccent
                : styles.kpiWarn
            }>
              {overview?.integration_health?.rate?.toFixed(0) ?? '--'}%
            </span>
          </span>
        </div>

        <div className={styles.kpiCard}>
          <span className={styles.kpiLabel}>待处理</span>
          <span className={styles.kpiValue}>
            <span className={
              (overview?.active_alerts ?? 0) > 0 ? styles.kpiDanger : styles.kpiAccent
            }>
              {(overview
                ? overview.active_alerts +
                  overview.unread_reviews +
                  overview.unresolved_reconciliation
                : '--'
              )}
            </span>
            <span className={styles.kpiUnit}>项</span>
          </span>
        </div>
      </section>

      {/* ── 主体区域 ─────────────────────────────────────────────── */}
      <section className={styles.mainGrid}>
        {/* 左侧：事件流 */}
        <div className={styles.eventPanel}>
          <div className={styles.panelHeader}>
            <h3 className={styles.panelTitle}>实时事件流</h3>
            <span className={styles.panelBadge}>
              {events.length} 条 / 24h
            </span>
          </div>
          <div className={styles.eventList}>
            {events.length === 0 && (
              <div className={styles.loading}>暂无事件</div>
            )}
            {events.map((ev, idx) => (
              <div key={`${ev.entity_id}-${idx}`} className={styles.eventItem}>
                <div
                  className={`${styles.eventDot} ${severityDotClass(ev.severity)}`}
                />
                <div className={styles.eventBody}>
                  <div className={styles.eventTitle}>{ev.title}</div>
                  <div className={styles.eventDetail}>{ev.detail}</div>
                </div>
                <span className={styles.eventTime}>
                  {formatTime(ev.timestamp)}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* 右侧面板组 */}
        <div className={styles.rightStack}>
          {/* 快捷操作 */}
          <div className={styles.actionsPanel}>
            <h3 className={styles.panelTitle}>快捷操作</h3>
            <div className={styles.actionsGrid}>
              {ACTION_DEFS.map((a) => (
                <button
                  key={a.key}
                  className={styles.actionBtn}
                  disabled={dispatchLoading !== null}
                  onClick={() => handleDispatch(a.key)}
                >
                  <span className={styles.actionIcon}>
                    {dispatchLoading === a.key ? (
                      <span className={styles.spinner} />
                    ) : (
                      a.icon
                    )}
                  </span>
                  {a.label}
                </button>
              ))}
            </div>
          </div>

          {/* 集成健康网格 */}
          <div className={styles.healthPanel}>
            <h3 className={styles.panelTitle}>集成健康</h3>
            <div className={styles.healthGrid}>
              {integrationEntries.length === 0 && (
                <div className={styles.loading}>暂无集成数据</div>
              )}
              {integrationEntries.map((entry) => (
                <div key={entry.status} className={styles.healthCard}>
                  <div
                    className={`${styles.healthDot} ${healthDotClass(entry.status)}`}
                  />
                  <span className={styles.healthName}>
                    {entry.status} ({entry.count})
                  </span>
                </div>
              ))}
              {pulse?.recent_errors?.slice(0, 3).map((err, i) => (
                <div key={i} className={styles.healthCard}>
                  <div className={`${styles.healthDot} ${styles.healthDotError}`} />
                  <span className={styles.healthName} title={err.error ?? ''}>
                    {err.integration}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* KPI 补充指标 */}
          {kpis && (
            <div className={styles.healthPanel}>
              <h3 className={styles.panelTitle}>运营指标</h3>
              <div className={styles.healthGrid}>
                <div className={styles.healthCard}>
                  <div className={`${styles.healthDot} ${styles.healthDotHealthy}`} />
                  <span className={styles.healthName}>
                    周营收 ¥{formatCurrency(kpis.revenue.weekly_yuan)}
                  </span>
                </div>
                <div className={styles.healthCard}>
                  <div className={`${styles.healthDot} ${styles.healthDotHealthy}`} />
                  <span className={styles.healthName}>
                    月营收 ¥{formatCurrency(kpis.revenue.monthly_yuan)}
                  </span>
                </div>
                <div className={styles.healthCard}>
                  <div className={`${styles.healthDot} ${
                    kpis.operations.order_fulfillment_rate >= 90
                      ? styles.healthDotHealthy
                      : styles.healthDotDegraded
                  }`} />
                  <span className={styles.healthName}>
                    履约率 {kpis.operations.order_fulfillment_rate}%
                  </span>
                </div>
                <div className={styles.healthCard}>
                  <div className={`${styles.healthDot} ${
                    kpis.integration.success_rate >= 95
                      ? styles.healthDotHealthy
                      : styles.healthDotDegraded
                  }`} />
                  <span className={styles.healthName}>
                    同步成功率 {kpis.integration.success_rate}%
                  </span>
                </div>
                <div className={styles.healthCard}>
                  <div className={`${styles.healthDot} ${styles.healthDotHealthy}`} />
                  <span className={styles.healthName}>
                    今日同步 {kpis.integration.sync_count_today} 次
                  </span>
                </div>
                <div className={styles.healthCard}>
                  <div className={`${styles.healthDot} ${
                    kpis.integration.error_count_today > 0
                      ? styles.healthDotError
                      : styles.healthDotHealthy
                  }`} />
                  <span className={styles.healthName}>
                    今日错误 {kpis.integration.error_count_today} 次
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ── 异常焦点 ─────────────────────────────────────────────── */}
      <section className={styles.anomalyPanel}>
        <h3 className={styles.panelTitle}>异常焦点</h3>
        {anomalies.length === 0 ? (
          <div className={styles.loading}>当前无紧急异常</div>
        ) : (
          <div className={styles.anomalyList}>
            {anomalies.map((a, idx) => (
              <div
                key={`${a.entity_id}-${idx}`}
                className={`${styles.anomalyCard} ${
                  a.severity === 'critical'
                    ? styles.anomalyCardCritical
                    : styles.anomalyCardWarning
                }`}
              >
                <div className={styles.anomalyHeader}>
                  <span
                    className={`${styles.severityTag} ${
                      a.severity === 'critical'
                        ? styles.severityCritical
                        : a.severity === 'high'
                          ? styles.severityHigh
                          : styles.severityWarning
                    }`}
                  >
                    {a.severity}
                  </span>
                  <span className={styles.anomalyTitle}>{a.source_system}</span>
                </div>
                <div className={styles.anomalyTitle}>{a.title}</div>
                <div className={styles.anomalyDesc}>{a.detail}</div>
                <button className={styles.anomalyAction}>
                  处理 →
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
};

export default CommandCenterPage;
