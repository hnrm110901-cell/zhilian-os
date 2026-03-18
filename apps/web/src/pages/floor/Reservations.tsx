/**
 * 楼面今日预订页
 * 路由：/floor/reservations
 * 数据：GET /api/v1/bff/floor/{store_id}
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty,
} from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './Reservations.module.css';

const STORE_ID = localStorage.getItem('store_id') || '';

interface ReservationItem {
  id:            string;
  guest_name:    string;
  party_size:    number;
  reserved_time: string;
  table_number?: string;
  status:        string;
  notes?:        string;
}

const STATUS_MAP: Record<string, { label: string; type: 'info' | 'success' | 'warning' | 'critical' }> = {
  confirmed:  { label: '已确认', type: 'success'  },
  pending:    { label: '待确认', type: 'warning'  },
  seated:     { label: '已就坐', type: 'info'     },
  no_show:    { label: '未到店', type: 'critical' },
  canceled:   { label: '已取消', type: 'critical' },
};

export default function FloorReservations() {
  const [items,   setItems]   = useState<ReservationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiClient.get(
        `/api/v1/bff/floor/${STORE_ID}${refresh ? '?refresh=true' : ''}`,
      );
      setItems(resp.today_reservations ?? []);
    } catch (e: any) {
      setError(e?.response?.data?.detail || '数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const confirmedCount = items.filter(r => r.status === 'confirmed' || r.status === 'seated').length;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>今日预订</div>
        <ZButton variant="ghost" size="sm" onClick={() => load(true)}>刷新</ZButton>
      </div>

      {loading ? (
        <div className={styles.body}><ZSkeleton rows={5} avatar /></div>
      ) : error ? (
        <div className={styles.body}>
          <ZEmpty icon="⚠️" title="加载失败" description={error} action={<ZButton size="sm" onClick={() => load()}>重试</ZButton>} />
        </div>
      ) : (
        <div className={styles.body}>
          <ZCard>
            <ZKpi value={String(items.length)} label="今日预订" size="lg" />
          </ZCard>

          {items.length === 0 ? (
            <ZEmpty icon="📅" title="今日暂无预订" />
          ) : (
            <ZCard subtitle={`已确认 ${confirmedCount} 桌`}>
              {items.map(item => {
                const s = STATUS_MAP[item.status] ?? STATUS_MAP.pending;
                const time = item.reserved_time
                  ? new Date(item.reserved_time).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
                  : '—';
                return (
                  <div key={item.id} className={styles.row}>
                    <div className={styles.time}>{time}</div>
                    <div className={styles.info}>
                      <div className={styles.name}>{item.guest_name}</div>
                      <div className={styles.sub}>
                        {item.party_size}人
                        {item.table_number && ` · ${item.table_number}桌`}
                        {item.notes && ` · ${item.notes}`}
                      </div>
                    </div>
                    <div className={styles.right}>
                      <ZBadge type={s.type} text={s.label} />
                    </div>
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
