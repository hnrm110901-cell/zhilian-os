import React, { useCallback, useEffect, useState } from 'react';
import {
  ControlOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  BugOutlined,
  DatabaseOutlined,
  ApiOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../services/api';
import { ZCard, ZBadge, ZButton, ZSkeleton } from '../design-system/components';
import css from './PlatformHubPage.module.css';

// ── Types ───────────────────────────────────────────────────────────────────

interface ErrorSummary {
  total_errors: number;
  critical_errors: number;
  warnings: number;
  error_rate: number;    // errors/min
}

interface PerfSummary {
  avg_response_ms: number;
  p99_response_ms: number;
  requests_per_sec: number;
  cpu_usage_pct: number;
  memory_usage_pct: number;
}

interface SchedulerHealth {
  status: string;        // healthy / degraded / down
  active_tasks: number;
  pending_tasks: number;
  failed_tasks: number;
}

interface ApprovalItem {
  id: string;
  decision_type: string;
  store_id: string;
  created_at: string;
}

interface BackupJob {
  id: string;
  status: string;       // completed / pending / failed
  backup_type: string;
  created_at: string;
}

// ── Nav groups ────────────────────────────────────────────────────────────────

const NAV_GROUPS = [
  {
    title: '组织与权限',
    items: [
      { icon: '👤', label: '用户管理',   route: '/users' },
      { icon: '🏪', label: '门店管理',   route: '/stores' },
      { icon: '🏬', label: '多门店管理', route: '/multi-store' },
      { icon: '✅', label: '审批管理',   route: '/approval' },
      { icon: '📋', label: '审批列表',   route: '/approval-list' },
      { icon: '📝', label: '审计日志',   route: '/audit' },
      { icon: '🔒', label: '数据安全',   route: '/data-security' },
    ],
  },
  {
    title: '集成与适配',
    items: [
      { icon: '🔌', label: '外部集成',   route: '/integrations' },
      { icon: '🔧', label: '适配器管理', route: '/adapters' },
      { icon: '🏢', label: '企业集成',   route: '/enterprise' },
    ],
  },
  {
    title: '模型与知识',
    items: [
      { icon: '🧠', label: 'LLM配置',   route: '/llm-config' },
      { icon: '🛒', label: '模型市场',   route: '/model-marketplace' },
      { icon: '💻', label: '硬件管理',   route: '/hardware' },
    ],
  },
  {
    title: '系统监控',
    items: [
      { icon: '📡', label: '系统监控',   route: '/monitoring' },
      { icon: '💚', label: '系统健康',   route: '/system-health' },
      { icon: '⏱',  label: '调度管理',  route: '/scheduler' },
      { icon: '📊', label: '基准测试',   route: '/benchmark' },
    ],
  },
  {
    title: '数据与配置',
    items: [
      { icon: '💾', label: '数据备份',   route: '/backup' },
      { icon: '📤', label: '导出任务',   route: '/export-jobs' },
      { icon: '📁', label: '数据导入导出', route: '/data-import-export' },
      { icon: '📥', label: '批量导入',   route: '/bulk-import' },
      { icon: '📄', label: '报表模板',   route: '/report-templates' },
      { icon: '💰', label: 'RaaS定价',  route: '/raas' },
      { icon: '🌐', label: '开放平台',   route: '/open-platform' },
    ],
  },
];

// ── Demo fallback data ────────────────────────────────────────────────────────

const DEMO_ERRORS: ErrorSummary = {
  total_errors: 3,
  critical_errors: 0,
  warnings: 3,
  error_rate: 0.02,
};

const DEMO_PERF: PerfSummary = {
  avg_response_ms: 142,
  p99_response_ms: 680,
  requests_per_sec: 23.4,
  cpu_usage_pct: 38,
  memory_usage_pct: 55,
};

const DEMO_SCHEDULER: SchedulerHealth = {
  status: 'healthy',
  active_tasks: 4,
  pending_tasks: 2,
  failed_tasks: 0,
};

const DEMO_APPROVALS: ApprovalItem[] = [];

const DEMO_AUDIT = [
  { text: '用户 admin 登录系统',               time: '10分钟前', color: '#1A7A52' },
  { text: '更新 LLM 配置（gpt-4o-mini）',     time: '1小时前',  color: '#0AAF9A' },
  { text: '导出报表：月度经营报告',              time: '2小时前',  color: '#0AAF9A' },
  { text: '备份任务完成（全量）',               time: '6小时前',  color: '#1A7A52' },
  { text: '集成状态更新：天财商龙',             time: '昨天',     color: '#8c8c8c' },
];

const DEMO_INTEGRATIONS = [
  { icon: '🏮', name: '天财商龙 POS', status: 'ok',   meta: '上次同步 5 分钟前' },
  { icon: '💬', name: '企业微信',     status: 'ok',   meta: '消息通道正常' },
  { icon: '📦', name: '供应商系统',   status: 'warn', meta: '响应延迟 +200ms' },
  { icon: '📊', name: '美团外卖',     status: 'ok',   meta: '今日订单 124 单' },
];

const DEMO_BACKUP: BackupJob = {
  id: 'bk1',
  status: 'completed',
  backup_type: 'full',
  created_at: new Date(Date.now() - 6 * 3600000).toISOString(),
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function statusColor(s: string): string {
  if (s === 'healthy' || s === 'ok' || s === 'completed') return '#1A7A52';
  if (s === 'degraded' || s === 'warn' || s === 'pending') return '#C8923A';
  return '#C53030';
}

function statusLabel(s: string): string {
  const m: Record<string, string> = {
    healthy: '健康', ok: '正常', completed: '已完成',
    degraded: '降级', warn: '告警', pending: '进行中',
    down: '宕机', failed: '失败',
  };
  return m[s] ?? s;
}

function relativeTime(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60)   return `${Math.round(diff)}秒前`;
  if (diff < 3600) return `${Math.round(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.round(diff / 3600)}小时前`;
  return `${Math.round(diff / 86400)}天前`;
}

function usageColor(pct: number): string {
  if (pct >= 85) return '#C53030';
  if (pct >= 70) return '#C8923A';
  return '#1A7A52';
}

function statusBadgeType(s: string): 'success' | 'warning' | 'critical' {
  if (s === 'ok' || s === 'healthy') return 'success';
  if (s === 'warn' || s === 'degraded') return 'warning';
  return 'critical';
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function PlatformHubPage() {
  const navigate = useNavigate();

  const [errors,    setErrors]    = useState<ErrorSummary | null>(null);
  const [perf,      setPerf]      = useState<PerfSummary | null>(null);
  const [scheduler, setScheduler] = useState<SchedulerHealth | null>(null);
  const [approvals, setApprovals] = useState<ApprovalItem[] | null>(null);
  const [backup,    setBackup]    = useState<BackupJob | null>(null);
  const [loading,   setLoading]   = useState(true);

  const loadErrors = useCallback(async () => {
    try {
      const r = await apiClient.get('/api/v1/monitoring/errors/summary');
      setErrors(r.data);
    } catch { setErrors(null); }
  }, []);

  const loadPerf = useCallback(async () => {
    try {
      const r = await apiClient.get('/api/v1/monitoring/performance/summary');
      setPerf(r.data);
    } catch { setPerf(null); }
  }, []);

  const loadScheduler = useCallback(async () => {
    try {
      const r = await apiClient.get('/api/v1/monitoring/scheduler/health');
      setScheduler(r.data);
    } catch { setScheduler(null); }
  }, []);

  const loadApprovals = useCallback(async () => {
    try {
      const r = await apiClient.get('/api/v1/approvals?status=pending&limit=5');
      const items: ApprovalItem[] = (r.data?.items ?? r.data ?? []).slice(0, 5);
      setApprovals(items);
    } catch { setApprovals(null); }
  }, []);

  const loadBackup = useCallback(async () => {
    try {
      const r = await apiClient.get('/api/v1/backups/?limit=1&status=completed');
      const items: BackupJob[] = r.data?.items ?? [];
      setBackup(items[0] ?? null);
    } catch { setBackup(null); }
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    await Promise.all([loadErrors(), loadPerf(), loadScheduler(), loadApprovals(), loadBackup()]);
    setLoading(false);
  }, [loadErrors, loadPerf, loadScheduler, loadApprovals, loadBackup]);

  useEffect(() => { refresh(); }, [refresh]);

  // Resolve display data
  const e  = errors    ?? DEMO_ERRORS;
  const p  = perf      ?? DEMO_PERF;
  const sc = scheduler ?? DEMO_SCHEDULER;
  const ap = approvals && approvals.length > 0 ? approvals : DEMO_APPROVALS;
  const bk = backup    ?? DEMO_BACKUP;

  const systemStatus = e.critical_errors > 0 ? 'down' : e.warnings > 0 ? 'warn' : 'ok';

  const KPI_ITEMS = [
    {
      icon: '⚡', bg: '#e6f4ff',
      label: '系统状态',
      value: statusLabel(systemStatus),
      sub: systemStatus === 'ok' ? '所有服务正常' : `${e.critical_errors} 个严重错误`,
      subClass: systemStatus === 'ok' ? css.kpiOk : css.kpiErr,
    },
    {
      icon: '🚨', bg: 'rgba(200,146,58,0.08)',
      label: '今日错误',
      value: String(e.total_errors),
      unit: '次',
      sub: `${e.warnings} 个告警`,
      subClass: e.warnings > 0 ? css.kpiWarn : css.kpiOk,
    },
    {
      icon: '⏱', bg: '#f9f0ff',
      label: 'API 平均响应',
      value: String(p.avg_response_ms),
      unit: 'ms',
      sub: `P99: ${p.p99_response_ms}ms`,
      subClass: p.avg_response_ms > 500 ? css.kpiWarn : css.kpiOk,
    },
    {
      icon: '✅', bg: '#fffbe6',
      label: '待审批',
      value: String(ap.length),
      unit: '项',
      sub: ap.length > 0 ? '需处理' : '无待办',
      subClass: ap.length > 0 ? css.kpiWarn : css.kpiOk,
    },
    {
      icon: '💾', bg: 'rgba(26,122,82,0.08)',
      label: '备份状态',
      value: statusLabel(bk.status),
      sub: bk.status === 'completed' ? relativeTime(bk.created_at) : '检查备份',
      subClass: bk.status === 'completed' ? css.kpiOk : css.kpiWarn,
    },
  ];

  return (
    <div className={css.page}>
      {/* Header */}
      <div className={css.pageHeader}>
        <div className={css.pageHeaderLeft}>
          <h4 className={css.pageTitle}>平台与治理中心</h4>
          <span className={css.pageSub}>系统健康 · 审批审计 · 集成管理</span>
        </div>
        <span title="刷新数据">
          <ZButton size="sm" icon={<ReloadOutlined />} onClick={refresh} loading={loading} />
        </span>
      </div>

      {/* KPI Strip */}
      {loading ? (
        <ZSkeleton rows={2} block style={{ marginBottom: 16 }} />
      ) : (
        <div className={css.kpiStrip}>
          {KPI_ITEMS.map(k => (
            <div key={k.label} className={css.kpiItem}>
              <div className={css.kpiIconWrap} style={{ background: k.bg }}>{k.icon}</div>
              <div className={css.kpiBody}>
                <div className={css.kpiLabel}>{k.label}</div>
                <div className={css.kpiValue}>
                  {k.value}
                  {'unit' in k && k.unit && <span className={css.kpiUnit}>{k.unit}</span>}
                </div>
                <div className={k.subClass}>{k.sub}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 3-col main */}
      <div className={css.mainGrid}>
        {/* Col 1: 系统状态 */}
        <ZCard
          title={<div style={{ display:'flex', alignItems:'center', gap:6 }}><BugOutlined style={{ color: '#0AAF9A' }} /><span>系统状态</span></div>}
          extra={<a onClick={() => navigate('/monitoring')} style={{ fontSize: 12 }}>监控详情</a>}
        >
          <div className={css.healthList}>
            {[
              { name: 'API 服务',    status: systemStatus,  value: `${p.requests_per_sec.toFixed(1)} req/s` },
              { name: '调度器',      status: sc.status,     value: `活跃 ${sc.active_tasks} 个任务` },
              { name: '数据库',      status: 'ok',          value: '连接池正常' },
              { name: 'Redis 缓存',  status: 'ok',          value: '响应 < 1ms' },
              { name: '消息队列',    status: sc.failed_tasks > 0 ? 'warn' : 'ok', value: `失败 ${sc.failed_tasks} 个` },
            ].map(row => (
              <div key={row.name} className={css.healthRow}>
                <div className={css.healthDot} style={{ background: statusColor(row.status) }} />
                <span className={css.healthName}>{row.name}</span>
                <ZBadge
                  type={statusBadgeType(row.status)}
                  text={statusLabel(row.status)}
                />
                <span className={css.healthMeta}>{row.value}</span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 12, borderTop: '1px solid var(--border)', paddingTop: 10 }}>
            {[
              { label: 'CPU 使用率',    value: `${p.cpu_usage_pct}%`,    color: usageColor(p.cpu_usage_pct) },
              { label: '内存使用率',    value: `${p.memory_usage_pct}%`, color: usageColor(p.memory_usage_pct) },
              { label: '平均响应时间',  value: `${p.avg_response_ms}ms`, color: p.avg_response_ms > 500 ? '#C8923A' : '#1A7A52' },
            ].map(row => (
              <div key={row.label} className={css.perfRow}>
                <span className={css.perfLabel}>{row.label}</span>
                <span className={css.perfValue} style={{ color: row.color }}>{row.value}</span>
              </div>
            ))}
          </div>
        </ZCard>

        {/* Col 2: 审批与审计 */}
        <ZCard
          title={<div style={{ display:'flex', alignItems:'center', gap:6 }}><CheckCircleOutlined style={{ color: '#C8923A' }} /><span>审批与审计</span></div>}
          extra={<a onClick={() => navigate('/approval-list')} style={{ fontSize: 12 }}>全部审批</a>}
        >
          <div className={css.approvalSummary}>
            <div>
              <div className={css.approvalNum}>{ap.length}</div>
              <div className={css.approvalDesc}>项待审批</div>
            </div>
            <ZButton
              variant="primary"
              size="sm"
              onClick={() => navigate('/approval-list')}
              disabled={ap.length === 0}
            >
              立即处理
            </ZButton>
          </div>

          {ap.length > 0 && (
            <div className={css.approvalList}>
              {ap.slice(0, 3).map(item => (
                <div key={item.id} className={css.approvalRow} onClick={() => navigate('/approval-list')}>
                  <ZBadge type="warning" text={item.decision_type} />
                  <span className={css.approvalTitle}>{item.store_id}</span>
                  <span className={css.approvalMeta}>{relativeTime(item.created_at)}</span>
                </div>
              ))}
            </div>
          )}

          <div style={{ marginTop: 10, borderTop: '1px solid var(--border)', paddingTop: 6 }}>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>近期操作日志</div>
            <div className={css.auditList}>
              {DEMO_AUDIT.slice(0, 4).map((a, i) => (
                <div key={i} className={css.auditRow}>
                  <div className={css.auditDot} style={{ background: a.color }} />
                  <span className={css.auditText}>{a.text}</span>
                  <span className={css.auditTime}>{a.time}</span>
                </div>
              ))}
            </div>
          </div>
        </ZCard>

        {/* Col 3: 集成与备份 */}
        <ZCard
          title={<div style={{ display:'flex', alignItems:'center', gap:6 }}><ApiOutlined style={{ color: '#722ed1' }} /><span>集成与数据</span></div>}
          extra={<a onClick={() => navigate('/integrations')} style={{ fontSize: 12 }}>集成管理</a>}
        >
          <div className={css.integrationList}>
            {DEMO_INTEGRATIONS.map(intg => (
              <div key={intg.name} className={css.integrationRow}>
                <div className={css.integrationIcon} style={{ background: intg.status === 'ok' ? 'rgba(26,122,82,0.08)' : 'rgba(200,146,58,0.08)' }}>
                  {intg.icon}
                </div>
                <span className={css.integrationName}>{intg.name}</span>
                <ZBadge
                  type={intg.status === 'ok' ? 'success' : 'warning'}
                  text={intg.status === 'ok' ? '正常' : '告警'}
                />
                <span className={css.integrationMeta}>{intg.meta}</span>
              </div>
            ))}
          </div>

          <div
            className={`${css.backupSummary} ${bk.status !== 'completed' ? css.backupSummaryWarn : ''}`}
            style={{ cursor: 'pointer' }}
            onClick={() => navigate('/backup')}
          >
            <div>
              <div className={css.backupSummaryLabel}>
                <DatabaseOutlined style={{ marginRight: 4 }} />
                最近备份：{bk.backup_type === 'full' ? '全量' : '增量'}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <ZBadge
                type={bk.status === 'completed' ? 'success' : 'warning'}
                text={statusLabel(bk.status)}
              />
              <div className={css.backupSummaryTime}>{relativeTime(bk.created_at)}</div>
            </div>
          </div>
        </ZCard>
      </div>

      {/* Quick Nav — grouped */}
      <ZCard title="管理入口">
        <div className={css.navGroups}>
          {NAV_GROUPS.map(group => (
            <div key={group.title} className={css.navGroup}>
              <div className={css.navGroupTitle}>{group.title}</div>
              <div className={css.navGroupItems}>
                {group.items.map(n => (
                  <button
                    key={n.route}
                    className={css.navItem}
                    onClick={() => navigate(n.route)}
                  >
                    <span className={css.navItemIcon}>{n.icon}</span>
                    <span className={css.navItemLabel}>{n.label}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </ZCard>
    </div>
  );
}
