/**
 * 楼面经理看板主屏
 * 路由：/floor
 * 数据：GET /api/v1/bff/floor/{store_id}
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty, ZTable,
} from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components/ZTable';
import apiClient from '../../services/api';
import styles from './FloorHome.module.css';

const STORE_ID = localStorage.getItem('store_id') || '';

interface Reservation {
  id:               string;
  guest_name:       string;
  party_size:       number;
  reserved_time: string;
  table_number:     string | null;
  status:           string;
}
interface ServiceAlert {
  alert_type:  string;
  severity:    string;
  description: string;
  created_at:  string;
}
interface FloorData {
  store_id:          string;
  queue_status:      null | { waiting_count: number; avg_wait_min: number };
  today_reservations: Reservation[];
  service_alerts:    ServiceAlert[];
}

const RESV_COLUMNS: ZTableColumn<Reservation>[] = [
  { key: 'reserved_time', title: '时间', render: (v) => v ? new Date(v).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '—' },
  { key: 'guest_name',       title: '客人' },
  { key: 'party_size',       title: '人数', align: 'center', render: (v) => `${v}人` },
  { key: 'table_number',     title: '桌号', align: 'center', render: (v) => v || '待分配' },
  { key: 'status',           title: '状态', align: 'center', render: (v) => (
    <ZBadge
      type={v === 'confirmed' ? 'success' : v === 'arrived' ? 'accent' : 'info'}
      text={v === 'confirmed' ? '已确认' : v === 'arrived' ? '已到店' : v}
    />
  )},
];

export default function FloorHome() {
  const [data,    setData]    = useState<FloorData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiClient.get(
        `/api/v1/bff/floor/${STORE_ID}${refresh ? '?refresh=true' : ''}`
      );
      setData(resp);
    } catch (e: any) {
      setError(e?.response?.data?.detail || '数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Auto-refresh every 60s
  useEffect(() => {
    const id = setInterval(() => load(), 60_000);
    return () => clearInterval(id);
  }, [load]);

  const q       = data?.queue_status;
  const alerts  = data?.service_alerts ?? [];
  const resvs   = data?.today_reservations ?? [];
  const criticals = alerts.filter(a => a.severity === 'critical').length;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>楼面看板</div>
        <div className={styles.headerRight}>
          {criticals > 0 && <ZBadge type="critical" text={`${criticals}项紧急`} />}
          <ZButton variant="ghost" size="sm" onClick={() => load(true)}>刷新</ZButton>
        </div>
      </div>

      {loading && !data ? (
        <div className={styles.body}><ZSkeleton block rows={3} style={{ gap: 16 }} /></div>
      ) : error ? (
        <div className={styles.body}>
          <ZEmpty icon="⚠️" title="加载失败" description={error} action={<ZButton size="sm" onClick={() => load()}>重试</ZButton>} />
        </div>
      ) : (
        <div className={styles.body}>
          {/* 排队状态 */}
          <ZCard title="当前排队">
            <div className={styles.queueRow}>
              <ZKpi
                value={q?.waiting_count ?? 0}
                label="等候桌数"
                unit="组"
                size="lg"
              />
              <ZKpi
                value={q?.avg_wait_min ?? 0}
                label="平均等待"
                unit="分钟"
                size="lg"
              />
            </div>
          </ZCard>

          {/* 今日预订 */}
          <ZCard
            title="今日预订"
            subtitle={`共 ${resvs.length} 组`}
          >
            <ZTable
              columns={RESV_COLUMNS}
              data={resvs}
              rowKey="id"
              emptyText="今日暂无预订"
            />
          </ZCard>

          {/* 服务告警 */}
          {alerts.length > 0 && (
            <ZCard
              title="服务告警"
              extra={<ZBadge type="warning" text={`${alerts.length}项`} />}
            >
              <div className={styles.alertList}>
                {alerts.map((a, i) => (
                  <div key={i} className={styles.alertRow}>
                    <ZBadge type={a.severity === 'critical' ? 'critical' : 'warning'} text={a.severity === 'critical' ? '紧急' : '告警'} />
                    <div className={styles.alertContent}>
                      <div className={styles.alertType}>{a.alert_type}</div>
                      <div className={styles.alertDesc}>{a.description}</div>
                    </div>
                    <div className={styles.alertTime}>
                      {new Date(a.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                    </div>
                  </div>
                ))}
              </div>
            </ZCard>
          )}
        </div>
      )}
    </div>
  );
}
