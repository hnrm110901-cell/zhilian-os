/**
 * 桌台管理 — 楼面经理平板端
 * 桌台状态实时看板、翻台管理
 */
import React, { useState, useEffect } from 'react';
import { ZCard, ZBadge, ZEmpty, ZSkeleton } from '../../design-system/components';
import { apiClient } from '../../services/api';
import styles from './Tables.module.css';

interface TableInfo {
  table_id: string;
  table_no: string;
  seats: number;
  status: 'idle' | 'occupied' | 'reserved' | 'cleaning';
  order_id?: string;
  guest_count?: number;
  duration_min?: number;
}

type StatusKey = 'idle' | 'occupied' | 'reserved' | 'cleaning';

const STATUS_CONFIG: Record<StatusKey, {
  label: string;
  badgeType: 'success' | 'info' | 'warning' | 'default';
  cardClass: string;
}> = {
  idle:     { label: '空闲',  badgeType: 'success', cardClass: styles.cardIdle },
  occupied: { label: '用餐中', badgeType: 'info',    cardClass: styles.cardOccupied },
  reserved: { label: '已预订', badgeType: 'warning',  cardClass: styles.cardReserved },
  cleaning: { label: '清理中', badgeType: 'default',  cardClass: styles.cardCleaning },
};

export default function Tables() {
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const storeId = localStorage.getItem('store_id') || '';
    apiClient.get<{ tables: TableInfo[] }>(`/api/v1/bff/floor/${storeId}?section=tables`)
      .then((data) => setTables(data.tables || []))
      .catch(() => setTables([]))
      .finally(() => setLoading(false));
  }, []);

  const idleCount    = tables.filter(t => t.status === 'idle').length;
  const occupiedCount = tables.filter(t => t.status === 'occupied').length;
  const reservedCount = tables.filter(t => t.status === 'reserved').length;
  const cleaningCount = tables.filter(t => t.status === 'cleaning').length;

  return (
    <div className={styles.container}>
      {/* 页头 */}
      <div className={styles.header}>
        <h2 className={styles.title}>桌台管理</h2>
        <div className={styles.summary}>
          <span className={`${styles.pill} ${styles.pillIdle}`}>空闲 {idleCount}</span>
          <span className={`${styles.pill} ${styles.pillOccupied}`}>用餐中 {occupiedCount}</span>
          <span className={`${styles.pill} ${styles.pillReserved}`}>已预订 {reservedCount}</span>
          {cleaningCount > 0 && (
            <span className={`${styles.pill} ${styles.pillCleaning}`}>清理中 {cleaningCount}</span>
          )}
        </div>
      </div>

      {/* 桌台网格 */}
      {loading ? (
        <ZSkeleton rows={6} />
      ) : tables.length === 0 ? (
        <ZEmpty text="暂无桌台数据" />
      ) : (
        <div className={styles.grid}>
          {tables.map((t) => {
            const cfg = STATUS_CONFIG[t.status] || STATUS_CONFIG.idle;
            return (
              <ZCard key={t.table_id} className={`${styles.tableCard} ${cfg.cardClass}`}>
                <div className={styles.tableInner}>
                  <div className={styles.tableNo}>{t.table_no}</div>
                  <div className={styles.seats}>{t.seats} 座</div>
                  <div className={styles.badgeWrap}>
                    <ZBadge type={cfg.badgeType} text={cfg.label} />
                  </div>
                  {t.guest_count != null && (
                    <div className={styles.guestCount}>👥 {t.guest_count} 人</div>
                  )}
                  {t.duration_min != null && (
                    <div className={styles.duration}>⏱ {t.duration_min} 分钟</div>
                  )}
                </div>
              </ZCard>
            );
          })}
        </div>
      )}
    </div>
  );
}
