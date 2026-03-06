/**
 * 总部桌面大屏总览
 * 路由：/hq
 * 数据：GET /api/v1/bff/hq
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty, ZTable,
} from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components/ZTable';
import { HealthRing } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './HQHome.module.css';

interface StoreHealth {
  store_id:          string;
  store_name:        string;
  score:             number;
  level:             string;
  rank:              number;
  revenue_yuan:      number;
  weakest_dimension?: string;
}
interface FcRanking {
  store_id:        string;
  store_name:      string;
  actual_cost_pct: number;
  variance_pct:    number;
}
interface HQData {
  as_of:                   string;
  stores_health_ranking:   StoreHealth[];
  food_cost_ranking:       FcRanking[];
  pending_approvals_count: number;
  hq_summary: {
    store_count:      number;
    avg_health_score: number;
  };
}

const HEALTH_COLS: ZTableColumn<StoreHealth>[] = [
  { key: 'rank',       title: '排名', align: 'center', width: 60 },
  { key: 'store_name', title: '门店' },
  { key: 'score',      title: '健康分', align: 'center', render: (v, row) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'center' }}>
      <HealthRing score={v} size={36} strokeWidth={4} />
    </div>
  )},
  { key: 'level',      title: '状态', align: 'center', render: (v) => (
    <ZBadge
      type={v === 'excellent' ? 'success' : v === 'good' ? 'info' : v === 'warning' ? 'warning' : 'critical'}
      text={v === 'excellent' ? '优秀' : v === 'good' ? '良好' : v === 'warning' ? '需关注' : '危险'}
    />
  )},
  { key: 'revenue_yuan', title: '今日营收', align: 'right', render: (v) => v ? `¥${Number(v).toLocaleString()}` : '—' },
  { key: 'weakest_dimension', title: '最弱维度', render: (v) => v || '—' },
];

const FC_COLS: ZTableColumn<FcRanking>[] = [
  { key: 'store_name',  title: '门店' },
  { key: 'actual_cost_pct',  title: '实际成本率', align: 'right', render: (v) => `${Number(v).toFixed(1)}%` },
  { key: 'variance_pct', title: '与目标差', align: 'right', render: (v) => (
    <span style={{ color: v > 0 ? 'var(--red)' : 'var(--green)', fontWeight: 600 }}>
      {v > 0 ? '+' : ''}{Number(v).toFixed(1)}%
    </span>
  )},
];

export default function HQHome() {
  const [data,    setData]    = useState<HQData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiClient.get(`/api/v1/bff/hq${refresh ? '?refresh=true' : ''}`);
      setData(resp.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || '数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const summary = data?.hq_summary;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <div className={styles.title}>总部总览</div>
          <div className={styles.sub}>
            {data?.as_of ? new Date(data.as_of).toLocaleString('zh-CN') : ''}
          </div>
        </div>
        <ZButton variant="ghost" size="sm" onClick={() => load(true)}>刷新</ZButton>
      </div>

      {loading && !data ? (
        <div className={styles.body}><ZSkeleton block rows={3} style={{ gap: 20 }} /></div>
      ) : error ? (
        <div className={styles.body}>
          <ZEmpty icon="⚠️" title="加载失败" description={error} action={<ZButton size="sm" onClick={() => load()}>重试</ZButton>} />
        </div>
      ) : (
        <div className={styles.body}>
          {/* KPI 行 */}
          <div className={styles.kpiRow}>
            <ZCard>
              <ZKpi value={summary?.store_count ?? 0} label="活跃门店" unit="家" size="lg" />
            </ZCard>
            <ZCard>
              <ZKpi value={summary?.avg_health_score ?? 0} label="平均健康分" size="lg" />
            </ZCard>
            <ZCard>
              <ZKpi
                value={data?.pending_approvals_count ?? 0}
                label="待审批决策"
                size="lg"
              />
            </ZCard>
          </div>

          {/* 门店健康排名 */}
          <ZCard title="门店健康排名">
            <ZTable
              columns={HEALTH_COLS}
              data={data?.stores_health_ranking ?? []}
              rowKey="store_id"
              emptyText="暂无门店数据"
            />
          </ZCard>

          {/* 食材成本排名 */}
          <ZCard title="食材成本率排名" subtitle="近7天，按超标幅度降序">
            <ZTable
              columns={FC_COLS}
              data={data?.food_cost_ranking ?? []}
              rowKey="store_id"
              emptyText="暂无成本数据"
            />
          </ZCard>
        </div>
      )}
    </div>
  );
}
