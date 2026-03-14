/**
 * 厨房出品 — 楼面经理平板端
 * 出品队列、出品速度监控
 */
import React, { useState, useEffect } from 'react';
import { Card, List, Tag, Progress, Empty, Spin } from 'antd';
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

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  queued:  { color: 'default',    label: '排队中' },
  cooking: { color: 'processing', label: '制作中' },
  ready:   { color: 'success',    label: '待上菜' },
  served:  { color: 'default',    label: '已上菜' },
};

export default function Kitchen() {
  const [orders, setOrders] = useState<KitchenOrder[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const storeId = localStorage.getItem('store_id') || 'STORE001';
    apiClient.get<{ items: KitchenOrder[] }>(`/api/v1/bff/floor/${storeId}?section=kitchen`)
      .then((data) => setOrders(data.items || []))
      .catch(() => setOrders([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin style={{ display: 'flex', justifyContent: 'center', padding: 40 }} />;

  return (
    <div className={styles.container}>
      <h2 className={styles.title}>厨房出品</h2>
      <div className={styles.summary}>
        <Tag color="#0AAF9A">{orders.filter(o => o.status === 'cooking').length} 道制作中</Tag>
        <Tag color="#27AE60">{orders.filter(o => o.status === 'ready').length} 道待上菜</Tag>
        <Tag>{orders.filter(o => o.status === 'queued').length} 道排队</Tag>
      </div>
      <List
        dataSource={orders.filter(o => o.status !== 'served')}
        locale={{ emptyText: <Empty description="暂无出品任务" /> }}
        renderItem={(item) => {
          const st = STATUS_MAP[item.status] || STATUS_MAP.queued;
          const pct = Math.min(100, Math.round((item.elapsed_min / item.target_min) * 100));
          const overdue = item.elapsed_min > item.target_min;
          return (
            <Card className={styles.itemCard} size="small" key={item.order_id + item.dish_name}>
              <div className={styles.itemRow}>
                <div>
                  <Tag color={st.color}>{st.label}</Tag>
                  <span className={styles.tableBadge}>{item.table_no}</span>
                  <span className={styles.dishName}>{item.dish_name} x{item.quantity}</span>
                </div>
                <Progress
                  percent={pct}
                  size="small"
                  strokeColor={overdue ? '#EB5757' : '#0AAF9A'}
                  format={() => `${item.elapsed_min}/${item.target_min}分`}
                  style={{ width: 120 }}
                />
              </div>
            </Card>
          );
        }}
      />
    </div>
  );
}
