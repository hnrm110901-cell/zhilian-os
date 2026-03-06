/**
 * 店长手机主屏
 * 路由：/sm
 *
 * 数据来源：GET /api/v1/bff/sm/{store_id}
 * 展示：健康指数 + Top3决策 + 排队状态 + 待审批数
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty,
  HealthRing, UrgencyList,
} from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './Home.module.css';

const STORE_ID = localStorage.getItem('store_id') || 'S001';

interface BffSmData {
  store_id:                string;
  as_of:                   string;
  health_score:            null | { score: number; level: string; weakest_dimension?: string };
  top3_decisions:          Array<{
    rank:                  number;
    title:                 string;
    action:                string;
    expected_saving_yuan:  number;
    confidence_pct:        number;
    urgency_hours:         number;
  }>;
  queue_status:            null | { waiting_count: number; avg_wait_min: number };
  pending_approvals_count: number;
}

export default function SmHome() {
  const [data,    setData]    = useState<BffSmData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiClient.get(
        `/api/v1/bff/sm/${STORE_ID}${refresh ? '?refresh=true' : ''}`
      );
      setData(resp.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || '数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const decisions = data?.top3_decisions ?? [];
  const urgencyItems = decisions.map(d => ({
    id:            String(d.rank),
    title:         d.title,
    description:   d.action,
    urgency:       (d.urgency_hours <= 4 ? 'critical' : d.urgency_hours <= 12 ? 'warning' : 'info') as 'critical' | 'warning' | 'info',
    amount_yuan:   d.expected_saving_yuan,
    action_label:  '去处理',
  }));

  const health = data?.health_score;

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.header}>
        <div>
          <div className={styles.greeting}>今日经营</div>
          <div className={styles.date}>{new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' })}</div>
        </div>
        <ZButton variant="ghost" size="sm" onClick={() => load(true)}>
          刷新
        </ZButton>
      </div>

      {loading && !data ? (
        <div className={styles.body}>
          <ZSkeleton block rows={3} style={{ gap: 16 }} />
        </div>
      ) : error ? (
        <div className={styles.body}>
          <ZEmpty icon="⚠️" title="加载失败" description={error} action={<ZButton size="sm" onClick={() => load()}>重试</ZButton>} />
        </div>
      ) : (
        <div className={styles.body}>
          {/* 健康指数卡 */}
          <ZCard
            title="门店健康指数"
            extra={health ? <ZBadge type={health.level === 'excellent' ? 'success' : health.level === 'good' ? 'info' : health.level === 'warning' ? 'warning' : 'critical'} text={health.level === 'excellent' ? '优秀' : health.level === 'good' ? '良好' : health.level === 'warning' ? '需关注' : '危险'} /> : null}
          >
            <div className={styles.healthRow}>
              <HealthRing score={health?.score ?? 0} size={88} />
              <div className={styles.healthMeta}>
                {health?.weakest_dimension && (
                  <div className={styles.weakDim}>
                    <span className={styles.weakLabel}>最弱维度</span>
                    <span className={styles.weakValue}>{health.weakest_dimension}</span>
                  </div>
                )}
                <div className={styles.kpiRow}>
                  <ZKpi value={data?.pending_approvals_count ?? 0} label="待审批" size="sm" />
                  <ZKpi
                    value={data?.queue_status?.waiting_count ?? 0}
                    label="排队桌"
                    unit="组"
                    size="sm"
                  />
                  <ZKpi
                    value={data?.queue_status?.avg_wait_min ?? 0}
                    label="平均等待"
                    unit="分"
                    size="sm"
                  />
                </div>
              </div>
            </div>
          </ZCard>

          {/* Top3 决策 */}
          <ZCard title="今日行动清单" subtitle={`${urgencyItems.length} 项待处理`}>
            <UrgencyList items={urgencyItems} />
          </ZCard>
        </div>
      )}
    </div>
  );
}
