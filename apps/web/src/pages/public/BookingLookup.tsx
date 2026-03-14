/**
 * 预订查询页 — 手机号验证 → 预订列表 → 取消操作
 */
import React, { useState, useEffect } from 'react';
import { apiClient } from '../../utils/apiClient';
import styles from './BookingH5.module.css';

interface Booking {
  id: string;
  store_id: string;
  customer_name: string;
  customer_phone: string;
  party_size: number;
  reservation_date: string;
  reservation_time: string;
  reservation_type: string;
  status: string;
  table_type?: string;
  created_at?: string;
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: '待确认', color: '#FF9800' },
  confirmed: { label: '已确认', color: '#4CAF50' },
  arrived: { label: '已到店', color: '#2196F3' },
  seated: { label: '已入座', color: '#9C27B0' },
  completed: { label: '已完成', color: '#607D8B' },
  cancelled: { label: '已取消', color: '#9E9E9E' },
  no_show: { label: '未到店', color: '#F44336' },
};

const BookingLookup: React.FC = () => {
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [countdown, setCountdown] = useState(0);
  const [token, setToken] = useState('');
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setTimeout(() => setCountdown(c => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  const sendCode = async () => {
    if (phone.length !== 11) return;
    setError('');
    try {
      await apiClient.post('/api/v1/public/sms/send-code', { phone });
      setCountdown(60);
    } catch (e: any) {
      setError(e?.response?.data?.detail || '发送失败');
    }
  };

  const verify = async () => {
    setError('');
    try {
      const data = await apiClient.post<{ token: string }>('/api/v1/public/sms/verify', { phone, code });
      setToken(data.token);
      loadBookings(data.token);
    } catch (e: any) {
      setError(e?.response?.data?.detail || '验证失败');
    }
  };

  const loadBookings = async (t: string) => {
    setLoading(true);
    try {
      const data = await apiClient.request<Booking[]>('/api/v1/public/reservations', {
        method: 'GET',
        requiresAuth: false,
        headers: { 'X-Phone-Token': t },
      });
      setBookings(data);
    } catch (e: any) {
      setError('加载预订列表失败');
    } finally {
      setLoading(false);
    }
  };

  const cancelBooking = async (id: string) => {
    if (!confirm('确定要取消这个预订吗？')) return;
    setError('');
    try {
      await apiClient.request(`/api/v1/public/reservations/${id}/cancel`, {
        method: 'POST',
        requiresAuth: false,
        headers: { 'X-Phone-Token': token },
      });
      loadBookings(token);
    } catch (e: any) {
      setError(e?.response?.data?.detail || '取消失败');
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>我的预订</h1>
        <p>查看和管理您的预订</p>
      </div>

      {error && <div className={styles.step}><div className={styles.error}>{error}</div></div>}

      {!token ? (
        <div className={styles.step}>
          <h2 className={styles.stepTitle}>验证手机号</h2>
          <div className={styles.formGroup}>
            <label className={styles.label}>手机号</label>
            <div className={styles.phoneRow}>
              <input
                className={styles.phoneInput}
                type="tel"
                maxLength={11}
                placeholder="请输入手机号"
                value={phone}
                onChange={e => setPhone(e.target.value.replace(/\D/g, ''))}
              />
              <button
                className={styles.sendCodeBtn}
                disabled={phone.length !== 11 || countdown > 0}
                onClick={sendCode}
              >
                {countdown > 0 ? `${countdown}s` : '获取验证码'}
              </button>
            </div>
          </div>
          <div className={styles.formGroup}>
            <label className={styles.label}>验证码</label>
            <input
              className={styles.codeInput}
              type="tel"
              maxLength={6}
              placeholder="------"
              value={code}
              onChange={e => setCode(e.target.value.replace(/\D/g, ''))}
            />
          </div>
          <button
            className={styles.btnPrimary}
            disabled={code.length !== 6}
            onClick={verify}
            style={{ width: '100%', marginTop: 12 }}
          >
            查询预订
          </button>
        </div>
      ) : (
        <div className={styles.step}>
          <h2 className={styles.stepTitle}>预订记录</h2>
          {loading ? (
            <div className={styles.loading}><div className={styles.spinner} /></div>
          ) : bookings.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
              暂无预订记录
            </div>
          ) : (
            <div className={styles.storeList}>
              {bookings.map(b => {
                const st = STATUS_MAP[b.status] || { label: b.status, color: '#999' };
                const canCancel = ['pending', 'confirmed'].includes(b.status);
                return (
                  <div key={b.id} className={styles.storeCard}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                      <p className={styles.storeName}>{b.reservation_date} {b.reservation_time}</p>
                      <span style={{
                        fontSize: 12,
                        padding: '2px 8px',
                        borderRadius: 4,
                        background: st.color + '15',
                        color: st.color,
                      }}>
                        {st.label}
                      </span>
                    </div>
                    <p className={styles.storeAddress}>
                      {b.customer_name} · {b.party_size}人 · {b.table_type || ''}
                    </p>
                    <p className={styles.storeAddress}>预订号：{b.id}</p>
                    {canCancel && (
                      <button
                        onClick={() => cancelBooking(b.id)}
                        style={{
                          marginTop: 8,
                          padding: '6px 16px',
                          border: '1px solid #d32f2f',
                          color: '#d32f2f',
                          background: 'transparent',
                          borderRadius: 6,
                          fontSize: 13,
                          cursor: 'pointer',
                        }}
                      >
                        取消预订
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          <div style={{ textAlign: 'center', marginTop: 20 }}>
            <a href="/book" style={{ color: '#0AAF9A', fontSize: 14 }}>去预订 →</a>
          </div>
        </div>
      )}
    </div>
  );
};

export default BookingLookup;
