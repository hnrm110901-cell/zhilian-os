/**
 * 巡店检查 — 店长移动端
 * 门店日常巡检记录、整改跟踪
 * API: GET /api/v1/bff/sm/{store_id}?section=patrol → { items: PatrolItem[] }
 */
import React, { useState, useEffect } from 'react';
import { ZCard, ZBadge, ZButton, ZEmpty, ZSkeleton } from '../../design-system/components';
import HealthRing from '../../design-system/components/HealthRing';
import { apiClient } from '../../services/api';
import styles from './Patrol.module.css';

interface PatrolItem {
  id: string;
  category: string;
  title: string;
  status: 'pending' | 'pass' | 'fail' | 'rectified';
  score: number;
  inspector?: string;
  created_at: string;
}

const STATUS_BADGE: Record<string, 'default' | 'success' | 'error' | 'info'> = {
  pending:   'default',
  pass:      'success',
  fail:      'error',
  rectified: 'info',
};
const STATUS_LABEL: Record<string, string> = {
  pending:   '待检',
  pass:      '合格',
  fail:      '不合格',
  rectified: '已整改',
};

const CATEGORY_ICONS: Record<string, string> = {
  '卫生': '🧹',
  '安全': '🔒',
  '服务': '👨‍🍳',
  '设备': '🔧',
  '食材': '🥬',
  '消防': '🧯',
};

type FilterKey = 'all' | 'pending' | 'pass' | 'fail' | 'rectified';

export default function Patrol() {
  const [items, setItems] = useState<PatrolItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterKey>('all');

  useEffect(() => {
    const storeId = localStorage.getItem('store_id') || '';
    apiClient.get(`/api/v1/bff/sm/${storeId}?section=patrol`)
      .then((data: any) => setItems(data?.items ?? []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  const passCount    = items.filter(i => i.status === 'pass' || i.status === 'rectified').length;
  const failCount    = items.filter(i => i.status === 'fail').length;
  const pendingCount = items.filter(i => i.status === 'pending').length;
  const score = items.length > 0 ? Math.round((passCount / items.length) * 100) : 0;

  const filtered = filter === 'all' ? items : items.filter(i => i.status === filter);

  const TABS: Array<{ key: FilterKey; label: string }> = [
    { key: 'all',       label: `全部 (${items.length})` },
    { key: 'pending',   label: `待检 (${pendingCount})` },
    { key: 'fail',      label: `不合格 (${failCount})` },
    { key: 'rectified', label: '已整改' },
  ];

  return (
    <div className={styles.container}>
      {/* 页头 */}
      <div className={styles.header}>
        <h2 className={styles.title}>巡店检查</h2>
        <ZButton size="sm" variant="primary">+ 新建巡检</ZButton>
      </div>

      {/* 得分卡 */}
      {!loading && items.length > 0 && (
        <ZCard className={styles.scoreCard}>
          <div className={styles.scoreRow}>
            <HealthRing score={score} size={64} label="" />
            <div className={styles.scoreMeta}>
              <div className={styles.scoreLabel}>今日巡检得分</div>
              <div className={styles.scoreDetail}>{passCount}/{items.length} 项合格</div>
              {failCount > 0 && (
                <div className={styles.failHint}>⚠️ {failCount} 项不合格待整改</div>
              )}
            </div>
            <div className={styles.scoreStats}>
              <div className={styles.statPill}>✅ {items.filter(i => i.status === 'pass').length}</div>
              <div className={`${styles.statPill} ${styles.statFail}`}>❌ {failCount}</div>
            </div>
          </div>
        </ZCard>
      )}

      {/* 状态筛选 Tab */}
      {!loading && items.length > 0 && (
        <div className={styles.tabBar}>
          {TABS.map(t => (
            <button
              key={t.key}
              className={`${styles.tab} ${filter === t.key ? styles.tabActive : ''}`}
              onClick={() => setFilter(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}

      {/* 列表 */}
      {loading ? (
        <ZSkeleton rows={5} />
      ) : filtered.length === 0 ? (
        <ZEmpty text={items.length === 0 ? '暂无巡检记录' : '该状态下无记录'} />
      ) : (
        <div className={styles.list}>
          {filtered.map(item => (
            <ZCard key={item.id} className={styles.itemCard}>
              <div className={styles.itemRow}>
                <div className={styles.itemLeft}>
                  <span className={styles.itemIcon}>
                    {CATEGORY_ICONS[item.category] ?? '📋'}
                  </span>
                  <div>
                    <div className={styles.itemCategory}>{item.category}</div>
                    <div className={styles.itemTitle}>{item.title}</div>
                    {item.inspector && (
                      <div className={styles.itemMeta}>👤 {item.inspector}</div>
                    )}
                  </div>
                </div>
                <ZBadge
                  type={STATUS_BADGE[item.status] ?? 'default'}
                  text={STATUS_LABEL[item.status] ?? item.status}
                />
              </div>
            </ZCard>
          ))}
        </div>
      )}
    </div>
  );
}
