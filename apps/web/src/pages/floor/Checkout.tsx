/**
 * 收银结账 — 楼面经理平板端
 * 订单结账、支付方式选择
 */
import React, { useState, useEffect } from 'react';
import { Card, Table, Tag, Button, Empty, Spin } from 'antd';
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

const columns = [
  { title: '桌号', dataIndex: 'table_no', key: 'table_no', width: 80 },
  { title: '人数', dataIndex: 'guest_count', key: 'guest_count', width: 60 },
  { title: '菜品', dataIndex: 'item_count', key: 'item_count', width: 60 },
  {
    title: '金额',
    dataIndex: 'total_yuan',
    key: 'total_yuan',
    width: 100,
    render: (v: number) => <span style={{ fontWeight: 600 }}>¥{v?.toFixed(2) ?? '—'}</span>,
  },
  {
    title: '用时',
    dataIndex: 'duration_min',
    key: 'duration_min',
    width: 80,
    render: (v: number) => `${v}分钟`,
  },
  {
    title: '操作',
    key: 'action',
    width: 100,
    render: () => <Button type="primary" size="small">结账</Button>,
  },
];

export default function Checkout() {
  const [orders, setOrders] = useState<PendingOrder[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const storeId = localStorage.getItem('store_id') || 'STORE001';
    apiClient.get<{ orders: PendingOrder[] }>(`/api/v1/bff/floor/${storeId}?section=checkout`)
      .then((data) => setOrders(data.orders || []))
      .catch(() => setOrders([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2 className={styles.title}>收银结账</h2>
        <Tag color="#0AAF9A">{orders.length} 单待结</Tag>
      </div>
      <Card className={styles.card} size="small">
        <Table
          columns={columns}
          dataSource={orders}
          rowKey="order_id"
          loading={loading}
          pagination={false}
          size="small"
          locale={{ emptyText: <Empty description="暂无待结订单" /> }}
        />
      </Card>
    </div>
  );
}
