import React, { useState, useEffect, useCallback } from 'react';
import {
  ZCard, ZBadge, ZButton, ZSkeleton, ZEmpty, HealthRing,
} from '../../design-system/components';
import { apiClient } from '../../services/api';
import { handleApiError } from '../../utils/message';
import styles from './PrivateDomainHealthPage.module.css';

// ── 类型定义 ──────────────────────────────────────────────────────────────────

interface Dimension {
  key:    string;
  label:  string;
  score:  number;
  max:    number;
  rate:   number;
  detail: string;
}

interface TopAction {
  dimension: string;
  score_pct: string;
  action:    string;
  urgency:   'high' | 'medium';
}

interface Grade {
  level: string;
  color: string;
  desc:  string;
}

interface HealthData {
  store_id:    string;
  as_of:       string;
  total_score: number;
  grade:       Grade;
  dimensions:  Dimension[];
  top_actions: TopAction[];
}

// ── 辅助 ─────────────────────────────────────────────────────────────────────

const STORE_ID = localStorage.getItem('store_id') || '';

const gradeColor = (color: string): string => {
  const map: Record<string, string> = {
    green:  'success',
    blue:   'info',
    orange: 'warning',
    red:    'danger',
  };
  return map[color] ?? 'default';
};

const urgencyBadge = (u: 'high' | 'medium') =>
  u === 'high' ? 'danger' : 'warning';

function DimBar({ dim }: { dim: Dimension }) {
  const pct = dim.max > 0 ? (dim.score / dim.max) * 100 : 0;
  const color =
    pct >= 85 ? 'var(--green)' :
    pct >= 70 ? '#007AFF' :
    pct >= 50 ? 'var(--accent)' :
    'var(--red)';

  return (
    <div className={styles.dimRow}>
      <div className={styles.dimHeader}>
        <span className={styles.dimLabel}>{dim.label}</span>
        <span className={styles.dimScore} style={{ color }}>
          {dim.score}<span className={styles.dimMax}>/{dim.max}</span>
        </span>
      </div>
      <div className={styles.barTrack}>
        <div
          className={styles.barFill}
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className={styles.dimDetail}>{dim.detail}</span>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PrivateDomainHealthPage
// ════════════════════════════════════════════════════════════════════════════

const PrivateDomainHealthPage: React.FC = () => {
  const [loading,  setLoading]  = useState(false);
  const [data,     setData]     = useState<HealthData | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/private-domain/health/${STORE_ID}`);
      setData(res.data);
    } catch (err: any) {
      handleApiError(err, '加载私域健康分失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const asOf = data
    ? new Date(data.as_of).toLocaleString('zh-CN', { hour12: false })
    : '';

  return (
    <div className={styles.page}>
      {/* ── 页头 ── */}
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>私域健康分</h2>
          {asOf && <span className={styles.asOf}>更新于 {asOf}</span>}
        </div>
        <ZButton size="sm" onClick={load} loading={loading}>刷新</ZButton>
      </div>

      {loading && !data ? (
        <ZSkeleton rows={6} />
      ) : !data ? (
        <ZEmpty description="暂无数据" />
      ) : (
        <div className={styles.body}>

          {/* ── 综合评分卡 ── */}
          <ZCard className={styles.scoreCard}>
            <div className={styles.scoreInner}>
              <HealthRing score={data.total_score} size={120} strokeWidth={10} />
              <div className={styles.scoreInfo}>
                <ZBadge
                  type={gradeColor(data.grade.color) as any}
                  text={data.grade.level}
                />
                <p className={styles.gradeDesc}>{data.grade.desc}</p>
                <div className={styles.totalScore}>
                  综合得分 <strong>{data.total_score}</strong> / 100
                </div>
              </div>
            </div>
          </ZCard>

          {/* ── 五维度明细 ── */}
          <ZCard title="维度明细" className={styles.dimCard}>
            {data.dimensions.map(d => <DimBar key={d.key} dim={d} />)}
          </ZCard>

          {/* ── Top3 行动建议 ── */}
          <ZCard title="改善建议" className={styles.actionsCard}>
            {data.top_actions.length === 0 ? (
              <ZEmpty description="暂无建议" />
            ) : (
              <ol className={styles.actionList}>
                {data.top_actions.map((a, i) => (
                  <li key={i} className={styles.actionItem}>
                    <div className={styles.actionHeader}>
                      <span className={styles.actionDim}>{a.dimension}</span>
                      <ZBadge type={urgencyBadge(a.urgency) as any} text={a.urgency === 'high' ? '紧急' : '建议'} />
                      <span className={styles.actionPct}>{a.score_pct}</span>
                    </div>
                    <p className={styles.actionText}>{a.action}</p>
                  </li>
                ))}
              </ol>
            )}
          </ZCard>

        </div>
      )}
    </div>
  );
};

export default PrivateDomainHealthPage;
