/**
 * ComplianceEnginePage — /platform/compliance-engine
 *
 * 合规引擎仪表盘：综合评分、评级分布、告警面板、门店评分表、自动操作日志
 * 后端 API:
 *   POST   /api/v1/compliance-engine/compute        — 批量计算评分
 *   GET    /api/v1/compliance-engine/scores          — 门店评分列表
 *   GET    /api/v1/compliance-engine/scores/:id      — 评分详情
 *   POST   /api/v1/compliance-engine/alerts/generate — 生成告警
 *   GET    /api/v1/compliance-engine/alerts          — 告警列表
 *   POST   /api/v1/compliance-engine/alerts/:id/resolve — 处置告警
 *   POST   /api/v1/compliance-engine/auto-actions    — 执行自动操作
 *   GET    /api/v1/compliance-engine/dashboard       — 仪表盘
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  ZCard, ZBadge, ZButton, ZEmpty, ZSkeleton,
} from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import { apiClient } from '../../services/api';
import styles from './ComplianceEnginePage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface ComplianceScore {
  id: string;
  brand_id: string;
  store_id: string;
  score_date: string;
  health_cert_score: number;
  food_safety_score: number;
  license_score: number;
  hygiene_score: number;
  overall_score: number;
  grade: string;
  risk_items: RiskItem[];
  auto_actions_taken?: ActionEntry[];
  created_at?: string;
}

interface RiskItem {
  type: string;
  description: string;
  severity: string;
  deadline: string;
}

interface ComplianceAlert {
  id: string;
  brand_id: string;
  store_id: string;
  alert_type: string;
  severity: string;
  title: string;
  description?: string;
  related_entity_id?: string;
  is_resolved: boolean;
  resolved_by?: string;
  resolved_at?: string;
  auto_action?: string;
  created_at?: string;
}

interface ActionEntry {
  action: string;
  alert_id?: string;
  store_id: string;
  timestamp: string;
  result: string;
  description: string;
}

interface Dashboard {
  avg_score: number;
  avg_grade: string;
  store_count: number;
  grade_distribution: Record<string, number>;
  alert_counts: {
    critical: number;
    high: number;
    medium: number;
    low: number;
    total: number;
  };
  trend: Array<{ date: string; avg_score: number | null }>;
  recent_actions: ActionEntry[];
}

interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ── 常量 ─────────────────────────────────────────────────────────────────────

const GRADE_COLORS: Record<string, string> = {
  'A+': styles.gradeAPlus,
  'A': styles.gradeA,
  'B': styles.gradeB,
  'C': styles.gradeC,
  'D': styles.gradeD,
  'F': styles.gradeF,
};

const GRADE_BADGE_COLORS: Record<string, string> = {
  'A+': styles.gradeBadgeAPlus,
  'A': styles.gradeBadgeA,
  'B': styles.gradeBadgeB,
  'C': styles.gradeBadgeC,
  'D': styles.gradeBadgeD,
  'F': styles.gradeBadgeF,
};

const SEVERITY_DOT: Record<string, string> = {
  critical: styles.severityCritical,
  high: styles.severityHigh,
  medium: styles.severityMedium,
  low: styles.severityLow,
};

const SEVERITY_LABELS: Record<string, string> = {
  critical: '严重',
  high: '高',
  medium: '中',
  low: '低',
};

const ALERT_TYPE_LABELS: Record<string, string> = {
  cert_expired: '健康证过期',
  cert_expiring: '健康证即将过期',
  inspection_failed: '检查未通过',
  license_expiring: '证照即将过期',
  trace_gap: '溯源缺口',
  score_drop: '评分骤降',
};

// ── 工具函数 ─────────────────────────────────────────────────────────────────

function fmtDate(iso?: string): string {
  if (!iso) return '\u2014';
  try {
    return new Date(iso).toLocaleDateString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
    });
  } catch { return iso; }
}

function fmtTime(iso?: string): string {
  if (!iso) return '\u2014';
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

function scoreColor(score: number): string {
  if (score >= 85) return '#22c55e';
  if (score >= 70) return '#3b82f6';
  if (score >= 55) return '#FF6B2C';
  if (score >= 40) return '#f59e0b';
  return '#ef4444';
}

// ── 组件 ─────────────────────────────────────────────────────────────────────

const ComplianceEnginePage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);

  // 门店评分表
  const [scores, setScores] = useState<ComplianceScore[]>([]);
  const [scoresTotal, setScoresTotal] = useState(0);
  const [scoresPage, setScoresPage] = useState(1);
  const [filterGrade, setFilterGrade] = useState('');
  const [searchStore, setSearchStore] = useState('');

  // 告警列表
  const [alerts, setAlerts] = useState<ComplianceAlert[]>([]);
  const [alertsTotal, setAlertsTotal] = useState(0);

  // 操作状态
  const [computing, setComputing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [resolving, setResolving] = useState<string | null>(null);

  const brandId = 'default';
  const PAGE_SIZE = 20;

  // ── 数据加载 ────────────────────────────────────────────────────────────

  const fetchDashboard = useCallback(async () => {
    try {
      const data = await apiClient.get<Dashboard>(
        `/api/v1/compliance-engine/dashboard?brand_id=${brandId}`
      );
      setDashboard(data);
    } catch (err) {
      console.error('加载仪表盘失败', err);
    }
  }, [brandId]);

  const fetchScores = useCallback(async () => {
    try {
      let url = `/api/v1/compliance-engine/scores?brand_id=${brandId}&page=${scoresPage}&page_size=${PAGE_SIZE}`;
      if (filterGrade) url += `&grade=${filterGrade}`;
      const data = await apiClient.get<PaginatedResponse<ComplianceScore>>(url);
      setScores(data.items);
      setScoresTotal(data.total);
    } catch (err) {
      console.error('加载评分列表失败', err);
    }
  }, [brandId, scoresPage, filterGrade]);

  const fetchAlerts = useCallback(async () => {
    try {
      const data = await apiClient.get<PaginatedResponse<ComplianceAlert>>(
        `/api/v1/compliance-engine/alerts?brand_id=${brandId}&is_resolved=false&page=1&page_size=50`
      );
      setAlerts(data.items);
      setAlertsTotal(data.total);
    } catch (err) {
      console.error('加载告警失败', err);
    }
  }, [brandId]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([fetchDashboard(), fetchScores(), fetchAlerts()]);
    setLoading(false);
  }, [fetchDashboard, fetchScores, fetchAlerts]);

  useEffect(() => { loadAll(); }, [loadAll]);
  useEffect(() => { fetchScores(); }, [fetchScores]);

  // ── 操作 ────────────────────────────────────────────────────────────────

  const handleCompute = async () => {
    setComputing(true);
    try {
      await apiClient.post('/api/v1/compliance-engine/compute', { brand_id: brandId });
      await loadAll();
    } catch (err) {
      console.error('计算评分失败', err);
    } finally {
      setComputing(false);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      await apiClient.post('/api/v1/compliance-engine/alerts/generate', { brand_id: brandId });
      await fetchAlerts();
      await fetchDashboard();
    } catch (err) {
      console.error('生成告警失败', err);
    } finally {
      setGenerating(false);
    }
  };

  const handleAutoActions = async () => {
    setExecuting(true);
    try {
      await apiClient.post('/api/v1/compliance-engine/auto-actions', { brand_id: brandId });
      await loadAll();
    } catch (err) {
      console.error('执行自动操作失败', err);
    } finally {
      setExecuting(false);
    }
  };

  const handleResolve = async (alertId: string) => {
    setResolving(alertId);
    try {
      await apiClient.post(`/api/v1/compliance-engine/alerts/${alertId}/resolve`, {
        resolved_by: 'admin',
      });
      await fetchAlerts();
      await fetchDashboard();
    } catch (err) {
      console.error('处置告警失败', err);
    } finally {
      setResolving(null);
    }
  };

  // ── 表格列定义 ──────────────────────────────────────────────────────────

  const scoreColumns: ZTableColumn<ComplianceScore>[] = [
    {
      key: 'store_id',
      title: '门店',
      width: 120,
      render: (_v, row) => <span style={{ fontWeight: 600 }}>{row.store_id}</span>,
    },
    {
      key: 'overall_score',
      title: '综合评分',
      width: 180,
      render: (_v, row) => (
        <div className={styles.scoreBar}>
          <div className={styles.scoreBarTrack}>
            <div
              className={styles.scoreBarFill}
              style={{
                width: `${row.overall_score}%`,
                background: scoreColor(row.overall_score),
              }}
            />
          </div>
          <span className={styles.scoreBarValue} style={{ color: scoreColor(row.overall_score) }}>
            {row.overall_score}
          </span>
        </div>
      ),
    },
    {
      key: 'grade',
      title: '评级',
      width: 60,
      render: (_v, row) => (
        <span className={`${styles.gradeBadge} ${GRADE_BADGE_COLORS[row.grade] || ''}`}>
          {row.grade}
        </span>
      ),
    },
    {
      key: 'health_cert_score',
      title: '健康证',
      width: 70,
      render: (_v, row) => (
        <span style={{ color: scoreColor(row.health_cert_score), fontWeight: 600, fontSize: 13 }}>
          {row.health_cert_score}
        </span>
      ),
    },
    {
      key: 'food_safety_score',
      title: '食安',
      width: 70,
      render: (_v, row) => (
        <span style={{ color: scoreColor(row.food_safety_score), fontWeight: 600, fontSize: 13 }}>
          {row.food_safety_score}
        </span>
      ),
    },
    {
      key: 'license_score',
      title: '证照',
      width: 70,
      render: (_v, row) => (
        <span style={{ color: scoreColor(row.license_score), fontWeight: 600, fontSize: 13 }}>
          {row.license_score}
        </span>
      ),
    },
    {
      key: 'hygiene_score',
      title: '卫生',
      width: 70,
      render: (_v, row) => (
        <span style={{ color: scoreColor(row.hygiene_score), fontWeight: 600, fontSize: 13 }}>
          {row.hygiene_score}
        </span>
      ),
    },
    {
      key: 'risk_items',
      title: '风险项',
      width: 70,
      render: (_v, row) => {
        const count = row.risk_items?.length || 0;
        return count > 0
          ? <ZBadge type="error" text={`${count} 项`} />
          : <span style={{ color: '#9ca3af', fontSize: 12 }}>无</span>;
      },
    },
    {
      key: 'score_date',
      title: '评分日期',
      width: 100,
      render: (_v, row) => <span style={{ fontSize: 12, color: '#6b7280' }}>{fmtDate(row.score_date)}</span>,
    },
  ];

  // ── 渲染 ────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className={styles.page}>
        <ZSkeleton lines={8} />
      </div>
    );
  }

  const d = dashboard;

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>合规引擎</h1>
          <p className={styles.pageSubtitle}>
            统一合规评分系统 -- 健康证 / 食品安全 / 证照 / 卫生检查
          </p>
        </div>
        <div className={styles.headerActions}>
          <ZButton size="sm" onClick={handleCompute} loading={computing}>
            重新计算
          </ZButton>
          <ZButton size="sm" onClick={handleGenerate} loading={generating}>
            生成告警
          </ZButton>
          <ZButton size="sm" variant="primary" onClick={handleAutoActions} loading={executing}>
            执行自动操作
          </ZButton>
        </div>
      </div>

      {/* 综合评分 + 评级分布 */}
      {d && (
        <div className={styles.gaugeRow}>
          <ZCard className={styles.gaugeCard}>
            <div className={`${styles.gaugeScore} ${GRADE_COLORS[d.avg_grade] || ''}`}>
              {d.avg_score}
            </div>
            <div className={`${styles.gaugeGrade} ${GRADE_COLORS[d.avg_grade] || ''}`}>
              {d.avg_grade}
            </div>
            <div className={styles.gaugeLabel}>
              品牌平均合规分（{d.store_count} 门店）
            </div>
          </ZCard>

          <div className={styles.gradeCards}>
            {(['A+', 'A', 'B', 'C', 'D', 'F'] as const).map((g) => (
              <ZCard
                key={g}
                className={styles.gradeCardItem}
                onClick={() => {
                  setFilterGrade(filterGrade === g ? '' : g);
                  setScoresPage(1);
                }}
                style={filterGrade === g ? { boxShadow: '0 0 0 2px var(--accent, #FF6B2C)' } : undefined}
              >
                <div className={`${styles.gradeCardLabel} ${GRADE_COLORS[g] || ''}`}>
                  {g}
                </div>
                <div className={styles.gradeCardCount}>
                  {d.grade_distribution[g] || 0}
                </div>
                <div className={styles.gradeCardUnit}>家门店</div>
              </ZCard>
            ))}
          </div>
        </div>
      )}

      {/* 告警面板 */}
      <div className={styles.alertSection}>
        <h2 className={styles.sectionTitle}>
          合规告警
          {d && d.alert_counts.total > 0 && (
            <span style={{ marginLeft: 8 }}>
              <span className={`${styles.alertCountBadge} ${styles.alertCountCritical}`}>
                严重 {d.alert_counts.critical}
              </span>{' '}
              <span className={`${styles.alertCountBadge} ${styles.alertCountHigh}`}>
                高 {d.alert_counts.high}
              </span>{' '}
              <span className={`${styles.alertCountBadge} ${styles.alertCountMedium}`}>
                中 {d.alert_counts.medium}
              </span>{' '}
              <span className={`${styles.alertCountBadge} ${styles.alertCountLow}`}>
                低 {d.alert_counts.low}
              </span>
            </span>
          )}
        </h2>

        {alerts.length === 0 ? (
          <ZEmpty description="暂无未处理告警" />
        ) : (
          <div className={styles.alertList}>
            {alerts.slice(0, 10).map((a) => (
              <ZCard key={a.id} className={styles.alertRow}>
                <div className={`${styles.alertSeverity} ${SEVERITY_DOT[a.severity] || ''}`} />
                <div className={styles.alertContent}>
                  <div className={styles.alertTitle}>
                    [{SEVERITY_LABELS[a.severity] || a.severity}] {a.title}
                  </div>
                  <div className={styles.alertMeta}>
                    {ALERT_TYPE_LABELS[a.alert_type] || a.alert_type} | 门店 {a.store_id} | {fmtTime(a.created_at)}
                  </div>
                </div>
                <div className={styles.alertActions}>
                  <ZButton
                    size="sm"
                    onClick={() => handleResolve(a.id)}
                    loading={resolving === a.id}
                  >
                    处置
                  </ZButton>
                </div>
              </ZCard>
            ))}
            {alertsTotal > 10 && (
              <div style={{ textAlign: 'center', fontSize: 12, color: '#9ca3af', padding: 8 }}>
                还有 {alertsTotal - 10} 条告警未显示
              </div>
            )}
          </div>
        )}
      </div>

      {/* 门店评分表 */}
      <h2 className={styles.sectionTitle}>门店合规评分</h2>
      <div className={styles.toolbar}>
        <select
          className={styles.filterSelect}
          value={filterGrade}
          onChange={(e) => { setFilterGrade(e.target.value); setScoresPage(1); }}
        >
          <option value="">全部评级</option>
          {['A+', 'A', 'B', 'C', 'D', 'F'].map((g) => (
            <option key={g} value={g}>{g}</option>
          ))}
        </select>
        <input
          className={styles.searchInput}
          placeholder="搜索门店..."
          value={searchStore}
          onChange={(e) => setSearchStore(e.target.value)}
        />
        <div className={styles.toolbarSpacer} />
      </div>

      <ZCard className={styles.tableCard}>
        {scores.length === 0 ? (
          <div className={styles.centered}>
            <ZEmpty description="暂无评分数据，请先点击「重新计算」" />
          </div>
        ) : (
          <ZTable<ComplianceScore>
            columns={scoreColumns}
            data={
              searchStore
                ? scores.filter((s) =>
                    s.store_id.toLowerCase().includes(searchStore.toLowerCase())
                  )
                : scores
            }
            rowKey="id"
            pagination={{
              current: scoresPage,
              total: scoresTotal,
              pageSize: PAGE_SIZE,
              onChange: setScoresPage,
            }}
          />
        )}
      </ZCard>

      {/* 自动操作日志 */}
      {d && d.recent_actions.length > 0 && (
        <>
          <h2 className={styles.sectionTitle}>最近自动操作</h2>
          <div className={styles.actionsLog}>
            {d.recent_actions.map((a, i) => (
              <ZCard key={i} className={styles.actionItem}>
                <span className={styles.actionTime}>{fmtTime(a.timestamp)}</span>
                <span className={styles.actionDesc}>{a.description}</span>
                <span
                  className={`${styles.actionResult} ${
                    a.result === 'executed' ? styles.actionExecuted : styles.actionSkipped
                  }`}
                >
                  {a.result === 'executed' ? '已执行' : '已跳过'}
                </span>
              </ZCard>
            ))}
          </div>
        </>
      )}
    </div>
  );
};

export default ComplianceEnginePage;
