/**
 * 客户自助预订H5页面 — 移动优先，5步流程
 * 不使用 Ant Design，纯 HTML/CSS 实现（微信 WebView 兼容）
 */
import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../../utils/apiClient';
import styles from './BookingH5.module.css';

// Types
interface StoreInfo {
  id: string;
  name: string;
  address: string;
  phone: string;
}

interface TimeSlot {
  time: string;
  meal_period: string;
  booked: number;
  available: number;
}

interface Availability {
  store_id: string;
  date: string;
  slots: TimeSlot[];
  table_types: { type: string; min_size: number; max_size: number }[];
}

type Step = 'store' | 'datetime' | 'info' | 'verify' | 'confirm';

const STEPS: Step[] = ['store', 'datetime', 'info', 'verify', 'confirm'];

const BookingH5: React.FC = () => {
  // State
  const [step, setStep] = useState<Step>('store');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Data
  const [stores, setStores] = useState<StoreInfo[]>([]);
  const [availability, setAvailability] = useState<Availability | null>(null);

  // Selections
  const [selectedStore, setSelectedStore] = useState<StoreInfo | null>(null);
  const [selectedDate, setSelectedDate] = useState<string>('');
  const [selectedTime, setSelectedTime] = useState<string>('');
  const [customerName, setCustomerName] = useState('');
  const [partySize, setPartySize] = useState(2);
  const [tableType, setTableType] = useState('大厅');
  const [specialRequests, setSpecialRequests] = useState('');

  // Phone verification
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [phoneToken, setPhoneToken] = useState('');
  const [countdown, setCountdown] = useState(0);
  const [verified, setVerified] = useState(false);

  // Success state
  const [bookingResult, setBookingResult] = useState<any>(null);

  // Load stores on mount
  useEffect(() => {
    loadStores();
  }, []);

  // Countdown timer
  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setTimeout(() => setCountdown(c => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  const loadStores = async () => {
    setLoading(true);
    try {
      const data = await apiClient.get<StoreInfo[]>('/api/v1/public/stores');
      setStores(data);
    } catch (e: any) {
      setError('加载门店失败，请刷新重试');
    } finally {
      setLoading(false);
    }
  };

  const loadAvailability = async (storeId: string, date: string) => {
    setLoading(true);
    try {
      const data = await apiClient.get<Availability>(
        `/api/v1/public/stores/${storeId}/availability?target_date=${date}`
      );
      setAvailability(data);
    } catch (e: any) {
      setError('加载可用时段失败');
    } finally {
      setLoading(false);
    }
  };

  const sendCode = async () => {
    if (phone.length !== 11) {
      setError('请输入正确的手机号');
      return;
    }
    setError('');
    try {
      await apiClient.post('/api/v1/public/sms/send-code', { phone });
      setCountdown(60);
    } catch (e: any) {
      setError(e?.response?.data?.detail || '发送失败');
    }
  };

  const verifyCode = async () => {
    setError('');
    try {
      const data = await apiClient.post<{ token: string }>('/api/v1/public/sms/verify', { phone, code });
      setPhoneToken(data.token);
      setVerified(true);
      setStep('confirm');
    } catch (e: any) {
      setError(e?.response?.data?.detail || '验证失败');
    }
  };

  const submitBooking = async () => {
    setError('');
    setLoading(true);
    try {
      const data = await apiClient.request('/api/v1/public/reservations', {
        method: 'POST',
        body: JSON.stringify({
          store_id: selectedStore!.id,
          customer_name: customerName,
          party_size: partySize,
          reservation_date: selectedDate,
          reservation_time: selectedTime + ':00',
          table_type: tableType,
          special_requests: specialRequests || undefined,
        }),
        requiresAuth: false,
        headers: { 'X-Phone-Token': phoneToken },
      });
      setBookingResult(data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || '预订失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  // Generate next 14 days
  const getDateOptions = () => {
    const dates = [];
    const today = new Date();
    for (let i = 0; i < 14; i++) {
      const d = new Date(today);
      d.setDate(d.getDate() + i);
      const dateStr = d.toISOString().split('T')[0];
      const dayNames = ['日', '一', '二', '三', '四', '五', '六'];
      dates.push({
        date: dateStr,
        label: i === 0 ? '今天' : i === 1 ? '明天' : `${d.getMonth() + 1}/${d.getDate()}`,
        day: dayNames[d.getDay()],
        isToday: i === 0,
      });
    }
    return dates;
  };

  const stepIndex = STEPS.indexOf(step);

  // ── Success page ──
  if (bookingResult) {
    return (
      <div className={styles.container}>
        <div className={styles.header}>
          <h1>预订成功</h1>
        </div>
        <div className={styles.successContainer}>
          <div className={styles.successIcon}>✓</div>
          <h2 className={styles.successTitle}>预订已提交</h2>
          <p className={styles.successSubtitle}>
            餐厅将在确认后通知您
          </p>
          <div className={styles.confirmCard}>
            <div className={styles.confirmRow}>
              <span className={styles.confirmLabel}>预订号</span>
              <span className={styles.confirmValue}>{bookingResult.id}</span>
            </div>
            <div className={styles.confirmRow}>
              <span className={styles.confirmLabel}>餐厅</span>
              <span className={styles.confirmValue}>{selectedStore?.name}</span>
            </div>
            <div className={styles.confirmRow}>
              <span className={styles.confirmLabel}>日期</span>
              <span className={styles.confirmValue}>{selectedDate}</span>
            </div>
            <div className={styles.confirmRow}>
              <span className={styles.confirmLabel}>时间</span>
              <span className={styles.confirmValue}>{selectedTime}</span>
            </div>
            <div className={styles.confirmRow}>
              <span className={styles.confirmLabel}>人数</span>
              <span className={styles.confirmValue}>{partySize}人</span>
            </div>
            <div className={styles.confirmRow}>
              <span className={styles.confirmLabel}>状态</span>
              <span className={styles.confirmValue}>待确认</span>
            </div>
          </div>
          <a href="/my-booking" style={{ color: '#0AAF9A', fontSize: 14 }}>
            查看我的预订 →
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <h1>在线预订</h1>
        <p>选择餐厅和时间，轻松预订</p>
      </div>

      {/* Progress */}
      <div className={styles.progress}>
        {STEPS.map((_, i) => (
          <div
            key={i}
            className={`${styles.progressStep} ${i <= stepIndex ? styles.progressStepActive : ''}`}
          />
        ))}
      </div>

      {/* Error */}
      {error && <div className={styles.step}><div className={styles.error}>{error}</div></div>}

      {/* Loading */}
      {loading && (
        <div className={styles.loading}>
          <div className={styles.spinner} />
        </div>
      )}

      {/* Step 1: Select Store */}
      {step === 'store' && !loading && (
        <div className={styles.step}>
          <h2 className={styles.stepTitle}>选择餐厅</h2>
          <div className={styles.storeList}>
            {stores.map(store => (
              <div
                key={store.id}
                className={`${styles.storeCard} ${selectedStore?.id === store.id ? styles.storeCardSelected : ''}`}
                onClick={() => setSelectedStore(store)}
              >
                <p className={styles.storeName}>{store.name}</p>
                <p className={styles.storeAddress}>{store.address}</p>
              </div>
            ))}
          </div>
          <div className={styles.actions}>
            <button
              className={styles.btnPrimary}
              disabled={!selectedStore}
              onClick={() => setStep('datetime')}
            >
              下一步
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Date & Time */}
      {step === 'datetime' && !loading && (
        <div className={styles.step}>
          <h2 className={styles.stepTitle}>选择日期和时间</h2>
          <div className={styles.dateGrid}>
            {getDateOptions().map(d => (
              <div
                key={d.date}
                className={`${styles.dateCell} ${selectedDate === d.date ? styles.dateCellSelected : ''} ${d.isToday ? styles.dateCellToday : ''}`}
                onClick={() => {
                  setSelectedDate(d.date);
                  setSelectedTime('');
                  if (selectedStore) loadAvailability(selectedStore.id, d.date);
                }}
              >
                <div style={{ fontSize: 11, color: selectedDate === d.date ? '#fff' : '#999' }}>
                  周{d.day}
                </div>
                <div>{d.label}</div>
              </div>
            ))}
          </div>

          {availability && selectedDate && (
            <>
              {['午餐', '晚餐'].map(meal => {
                const slots = availability.slots.filter(s => s.meal_period === meal && s.available > 0);
                if (slots.length === 0) return null;
                return (
                  <div key={meal}>
                    <div className={styles.mealLabel}>{meal}</div>
                    <div className={styles.timeSlots}>
                      {slots.map(s => (
                        <div
                          key={s.time}
                          className={`${styles.timeSlot} ${selectedTime === s.time ? styles.timeSlotSelected : ''}`}
                          onClick={() => setSelectedTime(s.time)}
                        >
                          {s.time}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </>
          )}

          <div className={styles.actions}>
            <button className={styles.btnSecondary} onClick={() => setStep('store')}>上一步</button>
            <button
              className={styles.btnPrimary}
              disabled={!selectedDate || !selectedTime}
              onClick={() => setStep('info')}
            >
              下一步
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Guest Info */}
      {step === 'info' && (
        <div className={styles.step}>
          <h2 className={styles.stepTitle}>就餐信息</h2>
          <div className={styles.formGroup}>
            <label className={styles.label}>姓名</label>
            <input
              className={styles.input}
              placeholder="请输入您的姓名"
              value={customerName}
              onChange={e => setCustomerName(e.target.value)}
            />
          </div>
          <div className={styles.formGroup}>
            <label className={styles.label}>用餐人数</label>
            <div className={styles.partySizeRow}>
              {[1, 2, 3, 4, 5, 6, 8, 10, 12].map(n => (
                <button
                  key={n}
                  className={`${styles.partySizeBtn} ${partySize === n ? styles.partySizeBtnSelected : ''}`}
                  onClick={() => setPartySize(n)}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>
          <div className={styles.formGroup}>
            <label className={styles.label}>桌型</label>
            <div className={styles.partySizeRow}>
              {['大厅', '包厢'].map(t => (
                <button
                  key={t}
                  className={`${styles.partySizeBtn} ${tableType === t ? styles.partySizeBtnSelected : ''}`}
                  style={{ width: 'auto', padding: '0 20px' }}
                  onClick={() => setTableType(t)}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
          <div className={styles.formGroup}>
            <label className={styles.label}>特殊要求（选填）</label>
            <textarea
              className={styles.textarea}
              placeholder="如：靠窗位置、儿童椅、生日布置等"
              value={specialRequests}
              onChange={e => setSpecialRequests(e.target.value)}
            />
          </div>
          <div className={styles.actions}>
            <button className={styles.btnSecondary} onClick={() => setStep('datetime')}>上一步</button>
            <button
              className={styles.btnPrimary}
              disabled={!customerName}
              onClick={() => setStep('verify')}
            >
              下一步
            </button>
          </div>
        </div>
      )}

      {/* Step 4: Phone Verify */}
      {step === 'verify' && (
        <div className={styles.step}>
          <h2 className={styles.stepTitle}>验证手机号</h2>
          <p style={{ fontSize: 14, color: '#999', marginBottom: 20 }}>
            我们需要验证您的手机号，以便餐厅联系您
          </p>
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
          <div className={styles.actions}>
            <button className={styles.btnSecondary} onClick={() => setStep('info')}>上一步</button>
            <button
              className={styles.btnPrimary}
              disabled={code.length !== 6}
              onClick={verifyCode}
            >
              验证并继续
            </button>
          </div>
        </div>
      )}

      {/* Step 5: Confirm */}
      {step === 'confirm' && (
        <div className={styles.step}>
          <h2 className={styles.stepTitle}>确认预订</h2>
          <div className={styles.confirmCard}>
            <div className={styles.confirmRow}>
              <span className={styles.confirmLabel}>餐厅</span>
              <span className={styles.confirmValue}>{selectedStore?.name}</span>
            </div>
            <div className={styles.confirmRow}>
              <span className={styles.confirmLabel}>日期</span>
              <span className={styles.confirmValue}>{selectedDate}</span>
            </div>
            <div className={styles.confirmRow}>
              <span className={styles.confirmLabel}>时间</span>
              <span className={styles.confirmValue}>{selectedTime}</span>
            </div>
            <div className={styles.confirmRow}>
              <span className={styles.confirmLabel}>姓名</span>
              <span className={styles.confirmValue}>{customerName}</span>
            </div>
            <div className={styles.confirmRow}>
              <span className={styles.confirmLabel}>人数</span>
              <span className={styles.confirmValue}>{partySize}人</span>
            </div>
            <div className={styles.confirmRow}>
              <span className={styles.confirmLabel}>桌型</span>
              <span className={styles.confirmValue}>{tableType}</span>
            </div>
            <div className={styles.confirmRow}>
              <span className={styles.confirmLabel}>手机号</span>
              <span className={styles.confirmValue}>{phone.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2')}</span>
            </div>
            {specialRequests && (
              <div className={styles.confirmRow}>
                <span className={styles.confirmLabel}>特殊要求</span>
                <span className={styles.confirmValue}>{specialRequests}</span>
              </div>
            )}
          </div>
          <div className={styles.actions}>
            <button className={styles.btnSecondary} onClick={() => setStep('verify')}>返回</button>
            <button
              className={styles.btnPrimary}
              disabled={loading}
              onClick={submitBooking}
            >
              {loading ? '提交中...' : '确认预订'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default BookingH5;
