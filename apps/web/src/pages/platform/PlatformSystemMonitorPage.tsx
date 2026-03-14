/**
 * PlatformSystemMonitorPage — /platform/monitoring
 *
 * 系统监控大屏：平台基础服务健康 + 门店运维分层监控 + 活跃告警
 * 后端 API:
 *   GET /api/v1/health                                   — 平台健康检查
 *   GET /api/v1/merchants?page=1&page_size=50            — 品牌列表（含门店）
 *   GET /api/v1/ops/dashboard/{store_id}?window_minutes= — 门店运维大屏
 *   GET /api/v1/ops/events?store_id=&status=open&limit=  — 活跃告警
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  ZCard, ZBadge, ZButton, ZEmpty, ZSkeleton,
} from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import { apiClient } from '../../services/api';
import styles from './PlatformSystemMonitorPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface HealthService {
  status: string;
  latency_ms?: number;
  message?: string;
}

interface PlatformHealth {
  status: string;
  services?: Record<string, HealthService | string>;
  database?: string | HealthService;
  redis?: string | HealthService;
  qdrant?: string | HealthService;
  api?: string | HealthService;
}

interface StoreOption {
  id: string;
  name: string;
}

interface BrandOption {
  brand_id: string;
  name: string;
  stores?: StoreOption[];
}

interface LayerStatus {
  score: number;
  status: 'healthy' | 'warning' | 'critical';
  alert_count: number;
  [key: string]: unknown;
}

interface OpsDashboard {
  store_id: string;
  overall_status: 'healthy' | 'warning' | 'critical';
  overall_score: number;
  active_alerts: number;
  window_minutes: number;
  layers: {
    l1_device?: LayerStatus & { total_readings?: number };
    l2_network?: LayerStatus & { availability_pct?: number };
    l3_system?: LayerStatus & { uptime_pct?: number; down_systems?: number; total_systems?: number };
  };
  food_safety?: {
    total_checks: number;
    violations: number;
    compliance_rate_pct: number;
    status: string;
  };
  llm_summary?: string;
}

interface AlertRecord {
  id?: string;
  store_id: string;
  component: string;
  description: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  event_type: string;
  created_at: string;
}

// ── 工具函数 ─────────────────────────────────────────────────────────────────

const statusType = (s: string): 'success' | 'warning' | 'error' | 'default' => {
  if (s === 'healthy' || s === 'ok' || s === 'up') return 'success';
  if (s === 'warning' || s === 'degraded') return 'warning';
  if (s === 'critical' || s === 'down' || s === 'error') return 'error';
  return 'default';
};

const statusLabel = (s: string) => {
  if (s === 'healthy' || s === 'ok' || s === 'up') return '正常';
  if (s === 'warning' || s === 'degraded') return '告警';
  if (s === 'critical' || s === 'down' || s === 'error') return '故障';
  return s;
};

const severityType = (sev: string): 'error' | 'warning' | 'info' | 'default' => {
  if (sev === 'critical') return 'error';
  if (sev === 'high') return 'error';
  if (sev === 'medium') return 'warning';
  return 'info';
};

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('zh-CN', {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  } catch { return iso; }
}

function getServiceStatus(val: unknown): string {
  if (!val) return 'unknown';
  if (typeof val === 'string') return val;
  if (typeof val === 'object' && val !== null) {
    return (val as HealthService).status ?? 'unknown';
  }
  return 'unknown';
}

// ── 服务健康条目 ──────────────────────────────────────────────────────────────

function ServiceRow({ name, value }: { name: string; value: unknown }) {
  const st = getServiceStatus(value);
  const latency = typeof value === 'object' && value !== null
    ? (value as HealthService).latency_ms
    : undefined;
  return (
    <div className={styles.serviceRow}>
      <span className={styles.serviceName}>{name}</span>
      <div className={styles.serviceRight}>
        {latency != null && (
          <span className={styles.latency}>{latency}ms</span>
        )}
        <ZBadge type={statusType(st)} text={statusLabel(st)} />
      </div>
    </div>
  );
}

// ── 指标格子 ─────────────────────────────────────────────────────────────────

function MetricCell({
  label, value, unit, color,
}: { label: string; value: string | number | undefined; unit?: string; color?: string }) {
  return (
    <div className={styles.metricCell}>
      <div className={styles.metricVal} style={color ? { color } : undefined}>
        {value ?? '—'}{unit && <span className={styles.metricUnit}>{unit}</span>}
      </div>
      <div className={styles.metricLabel}>{label}</div>
    </div>
  );
}

// ── 三层状态行 ────────────────────────────────────────────────────────────────

function LayerRow({
  icon, label, layer,
}: { icon: string; label: string; layer: LayerStatus | undefined }) {
  if (!layer) return null;
  return (
    <div className={styles.layerRow}>
      <span className={styles.layerIcon}>{icon}</span>
      <span className={styles.layerLabel}>{label}</span>
      <div className={styles.layerScore}>
        <div
          className={styles.scoreBar}
          style={{ width: `${Math.min(100, layer.score)}%` }}
          data-status={layer.status}
        />
      </div>
      <span className={styles.layerScoreNum}>{layer.score}</span>
      <ZBadge type={statusType(layer.status)} text={statusLabel(layer.status)} />
      {layer.alert_count > 0 && (
        <span className={styles.alertCount}>{layer.alert_count} 告警</span>
      )}
    </div>
  );
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

const WINDOW_OPTIONS = [
  { value: 15, label: '15 分钟' },
  { value: 30, label: '30 分钟' },
  { value: 60, label: '1 小时' },
];

export default function PlatformSystemMonitorPage() {
  const [health, setHealth] = useState<PlatformHealth | null>(null);
  const [loadingHealth, setLoadingHealth] = useState(true);

  const [brands, setBrands] = useState<BrandOption[]>([]);
  const [selectedBrand, setSelectedBrand] = useState('');
  const [stores, setStores] = useState<StoreOption[]>([]);
  const [selectedStore, setSelectedStore] = useState('');
  const [loadingBrands, setLoadingBrands] = useState(true);

  const [dashboard, setDashboard] = useState<OpsDashboard | null>(null);
  const [loadingDash, setLoadingDash] = useState(false);

  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [loadingAlerts, setLoadingAlerts] = useState(false);

  const [windowMin, setWindowMin] = useState(30);
  const [lastRefreshed, setLastRefreshed] = useState('');

  // ── 加载平台健康 ──
  const loadHealth = useCallback(async () => {
    setLoadingHealth(true);
    try {
      const res = await apiClient.get('/api/v1/health');
      setHealth(res);
    } catch {
      setHealth({ status: 'unknown' });
    } finally {
      setLoadingHealth(false);
    }
  }, []);

  // ── 加载品牌 + 门店 ──
  useEffect(() => {
    (async () => {
      setLoadingBrands(true);
      try {
        const res = await apiClient.get('/api/v1/merchants?page=1&page_size=50');
        const list: any[] = res?.merchants ?? res?.items ?? (Array.isArray(res) ? res : []);
        const mapped: BrandOption[] = list.map((m: any) => ({
          brand_id: m.brand_id ?? m.id,
          name: m.name,
          stores: (m.stores ?? []).map((s: any) => ({ id: s.id, name: s.name })),
        }));
        setBrands(mapped);
        if (mapped.length > 0) {
          setSelectedBrand(mapped[0].brand_id);
          const firstStores = mapped[0].stores ?? [];
          setStores(firstStores);
          if (firstStores.length > 0) setSelectedStore(firstStores[0].id);
        }
      } catch {
        setBrands([]);
      } finally {
        setLoadingBrands(false);
      }
    })();
  }, []);

  // 品牌切换 → 更新门店列表
  useEffect(() => {
    const brand = brands.find(b => b.brand_id === selectedBrand);
    const brandStores = brand?.stores ?? [];
    setStores(brandStores);
    setSelectedStore(brandStores.length > 0 ? brandStores[0].id : '');
  }, [selectedBrand, brands]);

  // ── 加载门店运维大屏 ──
  const loadDashboard = useCallback(async () => {
    if (!selectedStore) return;
    setLoadingDash(true);
    try {
      const res = await apiClient.get(
        `/api/v1/ops/dashboard/${selectedStore}?window_minutes=${windowMin}`
      );
      setDashboard(res?.data ?? res);
      setLastRefreshed(new Date().toLocaleTimeString('zh-CN'));
    } catch {
      setDashboard(null);
    } finally {
      setLoadingDash(false);
    }
  }, [selectedStore, windowMin]);

  // ── 加载活跃告警 ──
  const loadAlerts = useCallback(async () => {
    if (!selectedStore) return;
    setLoadingAlerts(true);
    try {
      const res = await apiClient.get(
        `/api/v1/ops/events?store_id=${selectedStore}&status=open&limit=30`
      );
      setAlerts(res?.data?.items ?? res?.data ?? res?.items ?? []);
    } catch {
      setAlerts([]);
    } finally {
      setLoadingAlerts(false);
    }
  }, [selectedStore]);

  // 初始化 & 刷新
  useEffect(() => { loadHealth(); }, [loadHealth]);
  useEffect(() => {
    if (selectedStore) {
      loadDashboard();
      loadAlerts();
    }
  }, [selectedStore, windowMin, loadDashboard, loadAlerts]);

  const handleRefresh = () => {
    loadHealth();
    loadDashboard();
    loadAlerts();
  };

  // ── 告警表格列 ──
  const alertColumns: ZTableColumn<AlertRecord>[] = [
    {
      key: 'severity',
      title: '级别',
      width: 90,
      render: (_, row) => (
        <ZBadge type={severityType(row.severity)} text={row.severity.toUpperCase()} />
      ),
    },
    {
      key: 'component',
      title: '组件',
      width: 130,
      render: (_, row) => <span className={styles.componentCell}>{row.component}</span>,
    },
    {
      key: 'description',
      title: '描述',
      render: (_, row) => <span className={styles.descCell}>{row.description}</span>,
    },
    {
      key: 'event_type',
      title: '类型',
      width: 120,
      render: (_, row) => <span className={styles.eventType}>{row.event_type}</span>,
    },
    {
      key: 'created_at',
      title: '时间',
      width: 80,
      render: (_, row) => <span className={styles.timeCell}>{fmtTime(row.created_at)}</span>,
    },
  ];

  // ── 平台服务数据整理 ──
  const serviceEntries: [string, unknown][] = [];
  if (health) {
    const { status: _st, ...rest } = health;
    if (health.database)       serviceEntries.push(['数据库 PostgreSQL', health.database]);
    if (health.redis)          serviceEntries.push(['缓存 Redis', health.redis]);
    if (health.qdrant)         serviceEntries.push(['向量库 Qdrant', health.qdrant]);
    if (health.api)            serviceEntries.push(['API 网关', health.api]);
    if (health.services) {
      Object.entries(health.services).forEach(([k, v]) => serviceEntries.push([k, v]));
    }
    if (serviceEntries.length === 0) {
      Object.entries(rest).forEach(([k, v]) => {
        if (k !== 'status') serviceEntries.push([k, v]);
      });
    }
  }

  const overallHealthStatus = health?.status ?? 'unknown';

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>系统监控</h1>
          <p className={styles.pageSubtitle}>
            平台基础服务健康 + 门店运维分层实时监控
            {lastRefreshed && <span className={styles.refreshTime}> · 上次刷新 {lastRefreshed}</span>}
          </p>
        </div>
        <ZButton size="sm" variant="ghost" onClick={handleRefresh}>
          刷新
        </ZButton>
      </div>

      {/* 平台健康行 */}
      <div className={styles.topRow}>
        {/* 平台基础服务 */}
        <ZCard className={styles.healthCard}>
          <div className={styles.healthCardTitle}>
            <span>🏗️ 平台基础服务</span>
            {loadingHealth ? (
              <ZBadge type="default" text="检查中…" />
            ) : (
              <ZBadge type={statusType(overallHealthStatus)} text={statusLabel(overallHealthStatus)} />
            )}
          </div>
          {loadingHealth ? (
            <ZSkeleton rows={4} />
          ) : serviceEntries.length > 0 ? (
            <div className={styles.serviceList}>
              {serviceEntries.map(([name, val]) => (
                <ServiceRow key={name} name={name} value={val} />
              ))}
            </div>
          ) : (
            <div className={styles.healthSimple}>
              <ZBadge type={statusType(overallHealthStatus)} text={statusLabel(overallHealthStatus)} />
              <span className={styles.healthNote}>健康检查返回简单状态</span>
            </div>
          )}
        </ZCard>

        {/* 门店选择 */}
        <ZCard className={styles.storePickerCard}>
          <div className={styles.healthCardTitle}>🏪 监控对象选择</div>
          {loadingBrands ? (
            <ZSkeleton rows={3} />
          ) : (
            <>
              <div className={styles.pickerSection}>
                <span className={styles.pickerLabel}>品牌</span>
                <div className={styles.tabGroup}>
                  {brands.map(b => (
                    <button
                      key={b.brand_id}
                      className={`${styles.tabBtn} ${selectedBrand === b.brand_id ? styles.tabBtnActive : ''}`}
                      onClick={() => setSelectedBrand(b.brand_id)}
                    >
                      {b.name}
                    </button>
                  ))}
                  {brands.length === 0 && <span className={styles.noData}>暂无品牌</span>}
                </div>
              </div>
              <div className={styles.pickerSection}>
                <span className={styles.pickerLabel}>门店</span>
                <div className={styles.tabGroup}>
                  {stores.map(s => (
                    <button
                      key={s.id}
                      className={`${styles.tabBtn} ${selectedStore === s.id ? styles.tabBtnActive : ''}`}
                      onClick={() => setSelectedStore(s.id)}
                    >
                      {s.name}
                    </button>
                  ))}
                  {stores.length === 0 && <span className={styles.noData}>该品牌暂无门店</span>}
                </div>
              </div>
              <div className={styles.pickerSection}>
                <span className={styles.pickerLabel}>时间窗口</span>
                <div className={styles.tabGroup}>
                  {WINDOW_OPTIONS.map(opt => (
                    <button
                      key={opt.value}
                      className={`${styles.tabBtn} ${windowMin === opt.value ? styles.tabBtnActive : ''}`}
                      onClick={() => setWindowMin(opt.value)}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}
        </ZCard>
      </div>

      {/* 门店运维大屏 */}
      {selectedStore && (
        <>
          {/* KPI 行 */}
          {loadingDash ? (
            <div className={styles.kpiRow}>
              {[1, 2, 3, 4].map(i => (
                <ZCard key={i} className={styles.kpiCard}><ZSkeleton rows={2} /></ZCard>
              ))}
            </div>
          ) : dashboard ? (
            <div className={styles.kpiRow}>
              <ZCard className={styles.kpiCard}>
                <div className={`${styles.kpiNum} ${styles[dashboard.overall_status]}`}>
                  {dashboard.overall_score}
                </div>
                <div className={styles.kpiLabel}>综合健康分</div>
              </ZCard>
              <ZCard className={styles.kpiCard}>
                <div className={`${styles.kpiNum} ${dashboard.active_alerts > 0 ? styles.kpiRed : styles.kpiGreen}`}>
                  {dashboard.active_alerts}
                </div>
                <div className={styles.kpiLabel}>活跃告警数</div>
              </ZCard>
              <ZCard className={styles.kpiCard}>
                <div className={styles.kpiNum}>
                  {dashboard.food_safety?.compliance_rate_pct != null
                    ? `${dashboard.food_safety.compliance_rate_pct.toFixed(1)}%`
                    : '—'}
                </div>
                <div className={styles.kpiLabel}>食安合规率</div>
              </ZCard>
              <ZCard className={styles.kpiCard}>
                <div className={`${styles.kpiNum} ${dashboard.overall_status === 'healthy' ? styles.kpiGreen : styles.kpiOrange}`}>
                  {statusLabel(dashboard.overall_status)}
                </div>
                <div className={styles.kpiLabel}>整体状态</div>
              </ZCard>
            </div>
          ) : null}

          {/* 分层监控 */}
          {dashboard && (
            <ZCard className={styles.layerCard}>
              <div className={styles.layerCardTitle}>🔬 分层健康监控</div>
              <LayerRow icon="📱" label="L1 设备层" layer={dashboard.layers?.l1_device} />
              <LayerRow icon="🌐" label="L2 网络层" layer={dashboard.layers?.l2_network} />
              <LayerRow icon="⚙️" label="L3 系统层" layer={dashboard.layers?.l3_system} />
              {dashboard.layers?.l3_system?.down_systems != null && (
                <div className={styles.sysDetail}>
                  系统: {dashboard.layers.l3_system.down_systems} 宕机 /
                  {dashboard.layers.l3_system.total_systems ?? '—'} 总计
                </div>
              )}
              {dashboard.llm_summary && (
                <div className={styles.llmSummary}>
                  <span className={styles.llmIcon}>🤖</span>
                  {dashboard.llm_summary}
                </div>
              )}
            </ZCard>
          )}

          {/* 活跃告警 */}
          <ZCard className={styles.alertCard}>
            <div className={styles.alertCardTitle}>
              <span>⚠️ 活跃告警</span>
              <ZBadge type={alerts.length > 0 ? 'error' : 'success'} text={`${alerts.length} 条`} />
            </div>
            {loadingAlerts ? (
              <ZSkeleton rows={4} />
            ) : alerts.length === 0 ? (
              <ZEmpty text="当前无活跃告警 🎉" />
            ) : (
              <ZTable<AlertRecord>
                columns={alertColumns}
                data={alerts}
                rowKey={(row, i) => row.id ?? `${row.store_id}-${i}`}
              />
            )}
          </ZCard>
        </>
      )}

      {!selectedStore && !loadingBrands && (
        <ZCard>
          <ZEmpty text="请先选择品牌和门店以查看运维大屏" />
        </ZCard>
      )}
    </div>
  );
}
