/**
 * 厨房出品 — 楼面经理平板端
 * 出品队列、出品速度监控
 */
import React, { useState, useEffect } from 'react';
import { ZCard, ZBadge, ZEmpty, ZSkeleton } from '../../design-system/components';
import { apiClient } from '../../services/api';
import styles from './Kitchen.module.css';

interface KitchenOrder {
  order_id: string;
  table_no: string;
  dish_name: string;
  quantity: number;
  elapsed_min: number;
  target_min: number;
  status: 'queued' | 'cooking' | 'ready' | 'served';
}

const STATUS_MAP: Record<string, { type: 'info' | 'success' | 'warning' | 'default'; label: string }> = {
  queued:  { type: 'default', label: '排队中' },
  cooking: { type: 'info',    label: '制作中' },
  ready:   { type: 'success', label: '待上菜' },
  served:  { type: 'default', label: '已上菜' },
};

export default function Kitchen() {
  const [orders, setOrders] = useState<KitchenOrder[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const storeId = localStorage.getItem('store_id') || '';
    apiClient.get<{ items: KitchenOrder[] }>(`/api/v1/bff/floor/${storeId}?section=kitchen`)
      .then((data) => setOrders(data.items || []))
      .catch(() => setOrders([]))
      .finally(() => setLoading(false));
  }, []);

  const active = orders.filter(o => o.status !== 'served');
  const cookingCount = orders.filter(o => o.status === 'cooking').length;
  const readyCount   = orders.filter(o => o.status === 'ready').length;
  const queuedCount  = orders.filter(o => o.status === 'queued').length;

  return (
    <div className={styles.container}>
      {/* 页头 */}
      <div className={styles.header}>
        <h2 className={styles.title}>厨房出品</h2>
        <div className={styles.summary}>
          <span className={`${styles.pill} ${styles.pillCooking}`}>制作中 {cookingCount}</span>
          <span className={`${styles.pill} ${styles.pillReady}`}>待上菜 {readyCount}</span>
          <span className={`${styles.pill} ${styles.pillQueued}`}>排队 {queuedCount}</span>
        </div>
      </div>

      {/* 列表 */}
      {loading ? (
        <ZSkeleton rows={5} />
      ) : active.length === 0 ? (
        <ZEmpty text="暂无出品任务" />
      ) : (
        <div className={styles.list}>
          {active.map((item) => {
            const st = STATUS_MAP[item.status] || STATUS_MAP.queued;
            const pct = Math.min(100, Math.round((item.elapsed_min / Math.max(item.target_min, 1)) * 100));
            const overdue = item.elapsed_min > item.target_min;

            return (
              <ZCard key={`${item.order_id}-${item.dish_name}`} className={styles.itemCard}>
                <div className={styles.itemRow}>
                  {/* 左侧信息 */}
                  <div className={styles.itemLeft}>
                    <ZBadge type={st.type} text={st.label} />
                    <span className={styles.tableTag}>{item.table_no}</span>
                    <span className={styles.dishName}>
                      {item.dish_name}
                      <span className={styles.qty}> ×{item.quantity}</span>
                    </span>
                  </div>

                  {/* 右侧进度 */}
                  <div className={styles.progressWrap}>
                    <div className={styles.progressTimeLabel}>
                      <span className={overdue ? styles.timeOverdue : styles.timeNormal}>
                        {item.elapsed_min}/{item.target_min}分
                      </span>
                    </div>
                    <div className={styles.progressTrack}>
                      <div
                        className={`${styles.progressBar} ${overdue ? styles.progressOverdue : ''}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                </div>
              </ZCard>
            );
          })}
        </div>
      )}
    </div>
  );
}
