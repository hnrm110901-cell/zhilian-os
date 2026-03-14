/**
 * 桌台管理 — 楼面经理平板端
 * 桌台状态实时看板、翻台管理
 */
import React, { useState, useEffect } from 'react';
import { Card, Tag, Empty, Spin, Badge } from 'antd';
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

const STATUS_CONFIG: Record<string, { color: string; label: string; badge: string }> = {
  idle:     { color: '#27AE60', label: '空闲', badge: 'success' },
  occupied: { color: '#0AAF9A', label: '用餐中', badge: 'processing' },
  reserved: { color: '#2D9CDB', label: '已预订', badge: 'warning' },
  cleaning: { color: '#F2994A', label: '清理中', badge: 'default' },
};

export default function Tables() {
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const storeId = localStorage.getItem('store_id') || 'STORE001';
    apiClient.get<{ tables: TableInfo[] }>(`/api/v1/bff/floor/${storeId}?section=tables`)
      .then((data) => setTables(data.tables || []))
      .catch(() => setTables([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin style={{ display: 'flex', justifyContent: 'center', padding: 40 }} />;
  if (!tables.length) return <Empty description="暂无桌台数据" style={{ padding: 40 }} />;

  return (
    <div className={styles.container}>
      <h2 className={styles.title}>桌台管理</h2>
      <div className={styles.summary}>
        {Object.entries(STATUS_CONFIG).map(([key, cfg]) => {
          const count = tables.filter(t => t.status === key).length;
          return <Tag key={key} color={cfg.color}>{cfg.label} {count}</Tag>;
        })}
      </div>
      <div className={styles.grid}>
        {tables.map((t) => {
          const cfg = STATUS_CONFIG[t.status] || STATUS_CONFIG.idle;
          return (
            <Badge.Ribbon key={t.table_id} text={cfg.label} color={cfg.color}>
              <Card className={styles.tableCard} size="small">
                <div className={styles.tableNo}>{t.table_no}</div>
                <div className={styles.seats}>{t.seats}座</div>
                {t.duration_min != null && (
                  <div className={styles.duration}>{t.duration_min}分钟</div>
                )}
              </Card>
            </Badge.Ribbon>
          );
        })}
      </div>
    </div>
  );
}
