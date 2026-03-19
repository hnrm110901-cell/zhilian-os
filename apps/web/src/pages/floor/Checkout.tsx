/**
 * 收银结账 — 楼面经理平板端
 * 订单结账、待结队列
 */
import React, { useState, useEffect } from 'react';
import { ZCard, ZBadge, ZButton, ZEmpty, ZSkeleton, ZTable } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import { apiClient } from '../../services/api';
import styles from './Checkout.module.css';

interface PendingOrder {
  order_id: string;
  table_no: string;
  guest_count: number;
  total_yuan: number;
  item_count: number;
  duration_min: number;
  status: string;
}

export default function Checkout() {
  const [orders, setOrders] = useState<PendingOrder[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const storeId = localStorage.getItem('store_id') || '';
    apiClient.get<{ orders: PendingOrder[] }>(`/api/v1/bff/floor/${storeId}?section=checkout`)
      .then((data) => setOrders(data.orders || []))
      .catch(() => setOrders([]))
      .finally(() => setLoading(false));
  }, []);

  const totalAmount = orders.reduce((sum, o) => sum + (o.total_yuan || 0), 0);

  const columns: ZTableColumn<PendingOrder>[] = [
    {
      key: 'table_no',
      title: '桌号',
      width: 80,
      render: (row) => <span className={styles.tableNoCell}>{row.table_no}</span>,
    },
    {
      key: 'guest_count',
      title: '人数',
      width: 70,
      render: (row) => `${row.guest_count} 人`,
    },
    {
      key: 'item_count',
      title: '菜品',
      width: 70,
      render: (row) => `${row.item_count} 道`,
    },
    {
      key: 'total_yuan',
      title: '金额',
      width: 110,
      render: (row) => (
        <span className={styles.amountCell}>¥{(row.total_yuan ?? 0).toFixed(2)}</span>
      ),
    },
    {
      key: 'duration_min',
      title: '用时',
      width: 90,
      render: (row) => {
        const overdue = row.duration_min > 90;
        return (
          <span className={overdue ? styles.durationOverdue : styles.durationNormal}>
            {row.duration_min} 分钟
          </span>
        );
      },
    },
    {
      key: 'status',
      title: '状态',
      width: 90,
      render: (row) => <ZBadge type="warning" text={row.status || '待结'} />,
    },
    {
      key: 'action',
      title: '操作',
      width: 90,
      render: () => (
        <ZButton size="sm" variant="primary">结账</ZButton>
      ),
    },
  ];

  return (
    <div className={styles.container}>
      {/* 页头 */}
      <div className={styles.header}>
        <h2 className={styles.title}>收银结账</h2>
        <div className={styles.headerRight}>
          {!loading && (
            <>
              <ZBadge type="info" text={`${orders.length} 单待结`} />
              <span className={styles.totalLabel}>
                合计 <strong>¥{totalAmount.toFixed(2)}</strong>
              </span>
            </>
          )}
        </div>
      </div>

      {/* 表格 */}
      {loading ? (
        <ZSkeleton rows={5} />
      ) : orders.length === 0 ? (
        <ZEmpty text="暂无待结订单" />
      ) : (
        <ZCard className={styles.tableCard}>
          <ZTable
            columns={columns}
            dataSource={orders}
            rowKey="order_id"
          />
        </ZCard>
      )}
    </div>
  );
}
