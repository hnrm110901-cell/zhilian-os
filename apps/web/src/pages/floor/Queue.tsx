/**
 * 楼面排队管理页
 * 路由：/floor/queue
 * 数据：GET /api/v1/bff/floor/{store_id}
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty,
} from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './Queue.module.css';

const STORE_ID = localStorage.getItem('store_id') || 'S001';

interface QueueStatus {
  waiting_count:     number;
  avg_wait_min:      number;
  served_today:      number;
  queue_items?:      QueueItem[];
}

interface QueueItem {
  ticket_no:   string;
  party_size:  number;
  wait_min:    number;
  status:      string;
}

const STATUS_MAP: Record<string, { label: string; type: 'info' | 'warning' | 'success' | 'critical' }> = {
  waiting:  { label: '等位中', type: 'warning' },
  called:   { label: '已叫号', type: 'info'    },
  seated:   { label: '已就坐', type: 'success' },
  canceled: { label: '已取消', type: 'critical'},
};

export default function FloorQueue() {
  const [queue,   setQueue]   = useState<QueueStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiClient.get(
        `/api/v1/bff/floor/${STORE_ID}${refresh ? '?refresh=true' : ''}`,
      );
      setQueue(resp.queue_status ?? null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || '数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Auto-refresh every 60s
  useEffect(() => {
    const id = setInterval(() => load(true), 60_000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>排队管理</div>
        <ZButton variant="ghost" size="sm" onClick={() => load(true)}>刷新</ZButton>
      </div>

      {loading ? (
        <div className={styles.body}><ZSkeleton rows={4} /></div>
      ) : error ? (
        <div className={styles.body}>
          <ZEmpty icon="⚠️" title="加载失败" description={error} action={<ZButton size="sm" onClick={() => load()}>重试</ZButton>} />
        </div>
      ) : !queue ? (
        <div className={styles.body}><ZEmpty icon="✅" title="暂无排队数据" /></div>
      ) : (
        <div className={styles.body}>
          <div className={styles.kpiRow}>
            <ZCard style={{ flex: 1 }}>
              <ZKpi value={String(queue.waiting_count)} label="当前等位" size="lg" />
            </ZCard>
            <ZCard style={{ flex: 1 }}>
              <ZKpi value={`${queue.avg_wait_min}分`} label="平均等待" size="lg" />
            </ZCard>
            <ZCard style={{ flex: 1 }}>
              <ZKpi value={String(queue.served_today)} label="今日服务" size="lg" />
            </ZCard>
          </div>

          {queue.queue_items && queue.queue_items.length > 0 && (
            <ZCard subtitle="当前队列">
              {queue.queue_items.map(item => {
                const s = STATUS_MAP[item.status] ?? STATUS_MAP.waiting;
                return (
                  <div key={item.ticket_no} className={styles.queueRow}>
                    <div className={styles.queueLeft}>
                      <div className={styles.queueNum}>{item.ticket_no}</div>
                      <div className={styles.queueSub}>{item.party_size}人 · 已等{item.wait_min}分钟</div>
                    </div>
                    <ZBadge type={s.type} text={s.label} />
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
