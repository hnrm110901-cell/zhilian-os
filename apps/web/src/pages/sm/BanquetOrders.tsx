/**
 * SM 全部订单页
 * 路由：/sm/banquet-orders
 * 数据：GET /api/v1/banquet-agent/stores/{id}/orders?status=
 *      POST /api/v1/banquet-agent/stores/{id}/orders/{order_id}/payment
 *      GET /api/v1/banquet-agent/stores/{id}/contracts/pending-sign  (Phase 14)
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import {
  ZCard, ZBadge, ZButton, ZSkeleton, ZEmpty, ZModal, ZSelect, ZInput,
} from '../../design-system/components';
import apiClient from '../../services/api';
import { handleApiError } from '../../utils/message';
import styles from './BanquetOrders.module.css';

const STORE_ID = localStorage.getItem('store_id') || 'S001';

const STATUS_FILTERS = [
  { value: '',           label: '全部' },
  { value: 'draft',      label: '待确认' },
  { value: 'confirmed',  label: '已确认' },
  { value: 'completed',  label: '已完成' },
  { value: 'cancelled',  label: '已取消' },
];

const PAYMENT_METHODS = [
  { value: 'cash',     label: '现金' },
  { value: 'transfer', label: '转账' },
  { value: 'wechat',   label: '微信' },
  { value: 'alipay',   label: '支付宝' },
];

const STATUS_BADGE: Record<string, { text: string; type: 'success' | 'info' | 'warning' | 'default' }> = {
  draft:       { text: '待确认', type: 'warning' },
  confirmed:   { text: '已确认', type: 'success' },
  preparing:   { text: '准备中', type: 'info'    },
  in_progress: { text: '进行中', type: 'info'    },
  completed:   { text: '已完成', type: 'info'    },
  settled:     { text: '已结算', type: 'success' },
  closed:      { text: '已关闭', type: 'default' },
  cancelled:   { text: '已取消', type: 'default' },
};

interface OrderItem {
  banquet_id:   string;
  banquet_type: string;
  banquet_date: string;
  table_count:  number;
  amount_yuan:  number;
  paid_yuan?:   number;
  status:       string;
}

interface PendingContract {
  contract_id:   string;
  contract_no:   string;
  order_id:      string;
  banquet_date:  string;
  banquet_type:  string;
  total_yuan:    number;
  contact_name:  string | null;
  days_until:    number;
}

export default function SmBanquetOrders() {
  const navigate = useNavigate();

  const [statusFilter,      setStatusFilter]      = useState('');
  const [orders,            setOrders]            = useState<OrderItem[]>([]);
  const [loading,           setLoading]           = useState(true);
  const [pendingContracts,  setPendingContracts]  = useState<PendingContract[]>([]);

  // Modal state
  const [modalOrder,   setModalOrder]   = useState<OrderItem | null>(null);
  const [payAmount,    setPayAmount]    = useState('');
  const [payMethod,    setPayMethod]    = useState('wechat');
  const [submitting,   setSubmitting]   = useState(false);

  const loadOrders = useCallback(async (status: string) => {
    setLoading(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/orders`,
        status ? { params: { status } } : undefined,
      );
      const raw = resp.data;
      setOrders(Array.isArray(raw) ? raw : (raw?.items ?? raw?.orders ?? []));
    } catch {
      setOrders([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadOrders(statusFilter); }, [loadOrders, statusFilter]);

  useEffect(() => {
    apiClient.get(`/api/v1/banquet-agent/stores/${STORE_ID}/contracts/pending-sign`)
      .then(r => setPendingContracts(r.data?.items ?? []))
      .catch(() => setPendingContracts([]));
  }, []);

  const openPayModal = (order: OrderItem) => {
    setModalOrder(order);
    setPayAmount('');
    setPayMethod('wechat');
  };

  const handlePaySubmit = async () => {
    if (!modalOrder || !payAmount) return;
    const amount = parseFloat(payAmount);
    if (isNaN(amount) || amount <= 0) {
      handleApiError(null, '请输入有效金额');
      return;
    }
    setSubmitting(true);
    try {
      await apiClient.post(
        `/api/v1/banquet-agent/stores/${STORE_ID}/orders/${modalOrder.banquet_id}/payment`,
        { amount_yuan: amount, payment_method: payMethod },
      );
      setModalOrder(null);
      loadOrders(statusFilter);
    } catch (e) {
      handleApiError(e, '登记付款失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <button className={styles.back} onClick={() => navigate('/sm/banquet')}>← 返回</button>
        <div className={styles.title}>全部订单</div>
      </div>

      {/* 待签约合同横幅 */}
      {pendingContracts.length > 0 && (
        <div className={styles.pendingBanner}>
          <span className={styles.pendingIcon}>📋</span>
          <span className={styles.pendingText}>
            {pendingContracts.length} 份合同待签约：
            {pendingContracts.slice(0, 2).map(c => (
              <span key={c.contract_id} className={styles.pendingItem}>
                {c.banquet_type}（{dayjs(c.banquet_date).format('MM-DD')}，{c.days_until}天后）
              </span>
            ))}
            {pendingContracts.length > 2 && `等${pendingContracts.length}份`}
          </span>
        </div>
      )}

      {/* 状态 Chip 过滤行 */}
      <div className={styles.chipBar}>
        {STATUS_FILTERS.map(f => (
          <button
            key={f.value}
            className={`${styles.chip} ${statusFilter === f.value ? styles.chipActive : ''}`}
            onClick={() => setStatusFilter(f.value)}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className={styles.body}>
        <ZCard>
          {loading ? (
            <ZSkeleton rows={4} />
          ) : !orders.length ? (
            <ZEmpty title="暂无订单" description="当前状态下没有订单数据" />
          ) : (
            <div className={styles.list}>
              {orders.map(order => {
                const s = STATUS_BADGE[order.status] ?? { text: order.status, type: 'default' as const };
                const balance = order.paid_yuan != null
                  ? order.amount_yuan - order.paid_yuan
                  : null;
                return (
                  <div key={order.banquet_id} className={styles.row}>
                    <div className={styles.info}>
                      <div className={styles.type}>{order.banquet_type}</div>
                      <div className={styles.meta}>
                        {dayjs(order.banquet_date).format('MM-DD')}
                        {` · ${order.table_count}桌`}
                      </div>
                    </div>
                    <div className={styles.right}>
                      <div className={styles.amountBlock}>
                        <span className={styles.amount}>¥{order.amount_yuan.toLocaleString()}</span>
                        {balance != null && balance > 0 && (
                          <span className={styles.balance}>待收¥{balance.toLocaleString()}</span>
                        )}
                      </div>
                      <ZBadge type={s.type} text={s.text} />
                      <ZButton variant="ghost" size="sm" onClick={() => navigate(`/sm/banquet-orders/${order.banquet_id}`)}>
                        详情
                      </ZButton>
                      {order.status === 'confirmed' && (
                        <ZButton variant="ghost" size="sm" onClick={() => openPayModal(order)}>
                          登记付款
                        </ZButton>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </ZCard>
      </div>

      {/* 登记付款 Modal */}
      <ZModal
        open={!!modalOrder}
        title={`登记付款：${modalOrder?.banquet_type ?? ''}`}
        onClose={() => setModalOrder(null)}
        footer={
          <div className={styles.modalFooter}>
            <ZButton variant="ghost" onClick={() => setModalOrder(null)}>取消</ZButton>
            <ZButton
              variant="primary"
              onClick={handlePaySubmit}
              disabled={!payAmount || submitting}
            >
              {submitting ? '提交中…' : '确认登记'}
            </ZButton>
          </div>
        }
      >
        <div className={styles.modalBody}>
          <div className={styles.field}>
            <label className={styles.label}>付款金额（元）</label>
            <ZInput
              type="number"
              value={payAmount}
              onChange={e => setPayAmount(e.target.value)}
              placeholder="请输入金额"
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>支付方式</label>
            <ZSelect
              value={payMethod}
              options={PAYMENT_METHODS}
              onChange={v => setPayMethod(v as string)}
            />
          </div>
        </div>
      </ZModal>
    </div>
  );
}
