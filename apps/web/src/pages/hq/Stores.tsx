/**
 * 总部门店列表页
 * 路由：/hq/stores
 * 数据：GET /api/v1/bff/hq（复用 hq_summary + stores_health_ranking）
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  ZCard, ZBadge, ZButton, ZSkeleton, ZEmpty, ZInput, ZModal, ZKpi,
} from '../../design-system/components';
import { HealthRing } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './Stores.module.css';

interface StoreHealth {
  store_id:          string;
  store_name:        string;
  score:             number;
  level:             string;
  rank:              number;
  revenue_yuan:      number;
  weakest_dimension?: string;
  dimensions?:       Record<string, { score: number | null }>;
}

const LEVEL_MAP: Record<string, { label: string; type: 'success'|'info'|'warning'|'critical' }> = {
  excellent: { label: '优秀',   type: 'success'  },
  good:      { label: '良好',   type: 'info'     },
  warning:   { label: '需关注', type: 'warning'  },
  critical:  { label: '危险',   type: 'critical' },
};

const DIM_LABELS: Record<string, string> = {
  revenue_completion: '营收完成率',
  table_turnover:     '翻台率',
  cost_rate:          '成本率',
  complaint_rate:     '客诉率',
  staff_efficiency:   '人效',
};

export default function HQStores() {
  const [stores,  setStores]  = useState<StoreHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);
  const [search,  setSearch]  = useState('');
  const [detail,  setDetail]  = useState<StoreHealth | null>(null);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiClient.get(`/api/v1/bff/hq${refresh ? '?refresh=true' : ''}`);
      setStores(resp.data.stores_health_ranking ?? []);
    } catch (e: any) {
      setError(e?.response?.data?.detail || '数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = stores.filter(s =>
    !search || s.store_name?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>门店列表</div>
        <ZButton variant="ghost" size="sm" onClick={() => load(true)}>刷新</ZButton>
      </div>

      <div className={styles.searchBar}>
        <ZInput
          placeholder="搜索门店名称…"
          value={search}
          onChange={setSearch}
          onClear={() => setSearch('')}
        />
      </div>

      {loading ? (
        <div className={styles.body}><ZSkeleton avatar rows={5} style={{ gap: 12 }} /></div>
      ) : error ? (
        <div className={styles.body}>
          <ZEmpty icon="⚠️" title="加载失败" description={error} action={<ZButton size="sm" onClick={() => load()}>重试</ZButton>} />
        </div>
      ) : filtered.length === 0 ? (
        <div className={styles.body}><ZEmpty title="未找到匹配门店" /></div>
      ) : (
        <div className={styles.body}>
          <ZCard subtitle={`共 ${filtered.length} 家门店`}>
            {filtered.map((store) => {
              const meta = LEVEL_MAP[store.level] ?? LEVEL_MAP.good;
              return (
                <div key={store.store_id} className={styles.row} onClick={() => setDetail(store)}>
                  <div className={styles.rank}>#{store.rank}</div>
                  <HealthRing score={store.score} size={44} strokeWidth={4} />
                  <div className={styles.info}>
                    <div className={styles.name}>{store.store_name}</div>
                    <div className={styles.sub}>
                      {store.weakest_dimension ? `最弱：${DIM_LABELS[store.weakest_dimension] ?? store.weakest_dimension}` : '各维度正常'}
                    </div>
                  </div>
                  <div className={styles.right}>
                    <ZBadge type={meta.type} text={meta.label} />
                    <span className={styles.chevron}>›</span>
                  </div>
                </div>
              );
            })}
          </ZCard>
        </div>
      )}

      {/* 门店健康维度 Modal */}
      <ZModal
        open={!!detail}
        title={detail?.store_name ?? '门店详情'}
        onClose={() => setDetail(null)}
      >
        {detail && (
          <div className={styles.detailWrap}>
            <div className={styles.scoreRow}>
              <HealthRing score={detail.score} size={72} label="综合健康分" />
              <div className={styles.scoreKpis}>
                <ZKpi value={detail.score.toFixed(1)} label="健康分" size="lg" />
                {detail.revenue_yuan > 0 && (
                  <ZKpi value={`¥${detail.revenue_yuan.toLocaleString()}`} label="今日营收" size="sm" />
                )}
              </div>
            </div>
            {detail.dimensions && (
              <div className={styles.dims}>
                <div className={styles.dimsTitle}>各维度评分</div>
                {Object.entries(detail.dimensions).map(([key, val]) => (
                  <div key={key} className={styles.dimRow}>
                    <span className={styles.dimLabel}>{DIM_LABELS[key] ?? key}</span>
                    <div className={styles.dimBar}>
                      <div
                        className={styles.dimFill}
                        style={{
                          width: `${val.score ?? 0}%`,
                          background: (val.score ?? 0) >= 90 ? 'var(--green)' : (val.score ?? 0) >= 70 ? 'var(--blue)' : 'var(--accent)',
                        }}
                      />
                    </div>
                    <span className={styles.dimScore}>{val.score?.toFixed(0) ?? '—'}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </ZModal>
    </div>
  );
}
