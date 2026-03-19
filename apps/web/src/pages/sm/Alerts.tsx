/**
 * 店长告警页
 * 路由：/sm/alerts
 * 数据：GET /api/v1/stores/health（过滤当前门店）
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  ZCard, ZBadge, ZButton, ZSkeleton, ZEmpty, ZKpi,
} from '../../design-system/components';
import { HealthRing } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './Alerts.module.css';

const STORE_ID = localStorage.getItem('store_id') || '';

const DIM_LABELS: Record<string, string> = {
  revenue_completion: '营收完成率',
  table_turnover:     '翻台率',
  cost_rate:          '成本率',
  complaint_rate:     '客诉率',
  staff_efficiency:   '人效',
};

const LEVEL_MAP = {
  excellent: { label: '优秀',   type: 'success'  as const },
  good:      { label: '良好',   type: 'info'     as const },
  warning:   { label: '需关注', type: 'warning'  as const },
  critical:  { label: '危险',   type: 'critical' as const },
};

interface StoreHealth {
  store_id:    string;
  score:       number;
  level:       string;
  dimensions?: Record<string, { score: number | null }>;
}

export default function SmAlerts() {
  const [health,  setHealth]  = useState<StoreHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiClient.get('/api/v1/stores/health');
      const stores: StoreHealth[] = resp.stores ?? [];
      setHealth(stores.find(s => s.store_id === STORE_ID) ?? null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || '数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const meta = LEVEL_MAP[(health?.level ?? 'good') as keyof typeof LEVEL_MAP] ?? LEVEL_MAP.good;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>运营告警</div>
        <ZButton variant="ghost" size="sm" onClick={load}>刷新</ZButton>
      </div>

      {loading ? (
        <div className={styles.body}><ZSkeleton rows={5} /></div>
      ) : error ? (
        <div className={styles.body}>
          <ZEmpty icon="⚠️" title="加载失败" description={error} action={<ZButton size="sm" onClick={load}>重试</ZButton>} />
        </div>
      ) : !health ? (
        <div className={styles.body}>
          <ZEmpty icon="✅" title="无告警数据" description="当前门店暂无健康指数数据" />
        </div>
      ) : (
        <div className={styles.body}>
          <ZCard>
            <div className={styles.scoreRow}>
              <HealthRing score={health.score} size={64} label="综合健康分" />
              <div className={styles.scoreInfo}>
                <ZKpi value={health.score.toFixed(1)} label="健康分" size="lg" />
                <ZBadge type={meta.type} text={meta.label} />
              </div>
            </div>
          </ZCard>

          {health.dimensions && (
            <ZCard subtitle="各维度状态">
              {Object.entries(health.dimensions).map(([key, val]) => {
                const score = val.score ?? 0;
                const level = score >= 90 ? 'excellent' : score >= 70 ? 'good' : score >= 50 ? 'warning' : 'critical';
                const dimMeta = LEVEL_MAP[level];
                return (
                  <div key={key} className={styles.dimRow}>
                    <span className={styles.dimLabel}>{DIM_LABELS[key] ?? key}</span>
                    <div className={styles.dimBar}>
                      <div
                        className={styles.dimFill}
                        style={{
                          width: `${score}%`,
                          background: score >= 90 ? 'var(--green)' : score >= 70 ? 'var(--blue)' : score >= 50 ? 'var(--accent)' : 'var(--red)',
                        }}
                      />
                    </div>
                    <span className={styles.dimScore}>{val.score?.toFixed(0) ?? '—'}</span>
                    <ZBadge type={dimMeta.type} text={dimMeta.label} />
                  </div>
                );
              })}
            </ZCard>
          )}
        </div>
      )}
    </div>
  );
}
