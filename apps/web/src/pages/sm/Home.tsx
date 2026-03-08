import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty, HealthRing, UrgencyList,
} from '../../design-system/components';
import { queryHomeSummary } from '../../services/mobile.query.service';
import type { MobileHomeSummaryResponse } from '../../services/mobile.types';
import styles from './Home.module.css';

const STORE_ID = localStorage.getItem('store_id') || 'STORE001';

function greeting(): string {
  const h = new Date().getHours();
  if (h < 6) return '凌晨好';
  if (h < 11) return '早上好';
  if (h < 14) return '中午好';
  if (h < 18) return '下午好';
  return '晚上好';
}

const HEALTH_LEVEL_MAP: Record<string, { label: string; type: 'success' | 'info' | 'warning' | 'critical' }> = {
  excellent: { label: '优秀', type: 'success' },
  good: { label: '良好', type: 'info' },
  warning: { label: '需关注', type: 'warning' },
  critical: { label: '危险', type: 'critical' },
};

export default function SmHome() {
  const navigate = useNavigate();
  const [data, setData] = useState<MobileHomeSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await queryHomeSummary();
      setData(resp);
    } catch {
      setError('数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const today = new Date().toLocaleDateString('zh-CN', {
    month: 'long', day: 'numeric', weekday: 'short',
  });

  const urgencyItems = (data?.top_tasks || []).map((t) => ({
    id: t.task_id,
    title: t.task_title,
    description: `截止 ${new Date(t.deadline_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`,
    urgency: (t.priority === 'p0_urgent' ? 'critical' : t.priority === 'p1_high' ? 'warning' : 'info') as 'critical' | 'warning' | 'info',
    action_label: t.task_status === 'in_progress' ? '去提交' : '去处理',
    onAction: () => navigate('/sm/tasks'),
  }));

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <div className={styles.greeting}>{greeting()}，{data?.role_name || '店长'}</div>
          <div className={styles.date}>{today} · {STORE_ID}</div>
        </div>
        <ZButton variant="ghost" size="sm" onClick={load}>↺ 刷新</ZButton>
      </div>

      {loading && !data ? (
        <div className={styles.body}>
          <ZSkeleton block rows={3} style={{ gap: 16 }} />
        </div>
      ) : error ? (
        <div className={styles.body}>
          <ZEmpty
            icon="⚠️"
            title="加载失败"
            description={error}
            action={<ZButton size="sm" onClick={load}>重试</ZButton>}
          />
        </div>
      ) : (
        <div className={styles.body}>
          {(data?.unread_alerts_count || 0) > 0 && (
            <button className={styles.alertBanner} onClick={() => navigate('/sm/alerts')}>
              <span className={styles.alertIcon}>‼</span>
              <span className={styles.alertText}>{data?.unread_alerts_count} 条运营告警待处理，点击查看</span>
              <span className={styles.alertArrow}>›</span>
            </button>
          )}

          <div className={styles.kpiGrid}>
            <div className={styles.kpiCell}>
              <ZKpi label="今日营收" value={Math.round(data?.today_revenue_yuan || 0)} unit="元" size="md" />
            </div>
            <div className={styles.kpiCell}>
              <ZKpi label="食材成本率" value={data?.food_cost_pct ?? 0} unit="%" size="md" />
            </div>
            <div className={`${styles.kpiCell} ${(data?.pending_approvals_count || 0) > 0 ? styles.kpiCellAlert : ''}`}>
              <ZKpi label="待审批" value={data?.pending_approvals_count ?? 0} unit="项" size="md" />
            </div>
            <div className={styles.kpiCell}>
              <ZKpi label="排队等候" value={data?.waiting_count ?? 0} unit="组" size="md" />
            </div>
          </div>

          <ZCard
            title="门店健康指数"
            extra={data ? (
              <ZBadge
                type={HEALTH_LEVEL_MAP[data.health_level]?.type ?? 'info'}
                text={HEALTH_LEVEL_MAP[data.health_level]?.label ?? data.health_level}
              />
            ) : null}
          >
            <div className={styles.healthRow}>
              <HealthRing score={data?.health_score ?? 0} size={96} label="综合评分" />
              <div className={styles.healthMeta}>
                {data?.weakest_dimension && (
                  <div className={styles.weakDim}>
                    <span className={styles.weakLabel}>最弱维度</span>
                    <span className={styles.weakValue}>{data.weakest_dimension}</span>
                  </div>
                )}
                <div className={styles.healthStats}>
                  <div className={styles.statItem}>
                    <span className={styles.statValue}>{data?.today_shift ? `${data.today_shift.start_time}-${data.today_shift.end_time}` : '休息'}</span>
                    <span className={styles.statLabel}>今日班次</span>
                  </div>
                </div>
              </div>
            </div>
          </ZCard>

          <ZCard
            title="今日行动清单"
            subtitle={urgencyItems.length > 0 ? `${urgencyItems.length} 项待处理` : '暂无待处理'}
            extra={urgencyItems.length > 0 ? <ZButton variant="ghost" size="sm" onClick={() => navigate('/sm/tasks')}>全部 ›</ZButton> : null}
          >
            <UrgencyList items={urgencyItems} maxItems={3} />
          </ZCard>

          <ZCard title="快捷操作">
            <div className={styles.quickGrid}>
              <button className={styles.quickBtn} onClick={() => navigate('/sm/shifts')}>
                <span className={styles.quickIcon}>🕒</span>
                <span className={styles.quickLabel}>班次打卡</span>
              </button>
              <button className={styles.quickBtn} onClick={() => navigate('/sm/tasks')}>
                <span className={styles.quickIcon}>✅</span>
                <span className={styles.quickLabel}>任务执行</span>
              </button>
              <button className={styles.quickBtn} onClick={() => navigate('/sm/decisions')}>
                <span className={styles.quickIcon}>📋</span>
                <span className={styles.quickLabel}>审批决策</span>
                {(data?.pending_approvals_count || 0) > 0 && <span className={styles.quickBadge}>{data?.pending_approvals_count}</span>}
              </button>
              <button className={styles.quickBtn} onClick={() => navigate('/sm/alerts')}>
                <span className={styles.quickIcon}>🔔</span>
                <span className={styles.quickLabel}>告警管理</span>
                {(data?.unread_alerts_count || 0) > 0 && <span className={styles.quickBadge}>{data?.unread_alerts_count}</span>}
              </button>
            </div>
          </ZCard>
        </div>
      )}
    </div>
  );
}
