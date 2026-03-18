/**
 * 请假申请 — 员工H5端
 * 路由：/emp/leave
 * 功能：假期余额展示、请假表单、历史记录
 */
import React, { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../../services/api';
import styles from './LeaveRequestPage.module.css';

const EMP_ID = localStorage.getItem('employee_id') || 'EMP_001';
const STORE_ID = localStorage.getItem('store_id') || '';

interface LeaveBalance {
  leave_category: string;
  total_days: number;
  used_days: number;
  remaining_days: number;
}

interface LeaveRecord {
  id: string;
  leave_category: string;
  start_date: string;
  end_date: string;
  leave_days: number;
  reason: string;
  status: string;
  created_at: string;
}

const LEAVE_TYPES = [
  { value: 'annual',       label: '年假' },
  { value: 'sick',         label: '病假' },
  { value: 'personal',     label: '事假' },
  { value: 'compensatory', label: '调休' },
  { value: 'maternity',    label: '产假' },
  { value: 'paternity',    label: '陪产假' },
  { value: 'marriage',     label: '婚假' },
  { value: 'bereavement',  label: '丧假' },
  { value: 'other',        label: '其他' },
];

const LEAVE_LABELS: Record<string, string> = Object.fromEntries(
  LEAVE_TYPES.map((t) => [t.value, t.label])
);

const STATUS_MAP: Record<string, { label: string; cls: string }> = {
  pending:  { label: '审批中', cls: 'statusPending' },
  approved: { label: '已批准', cls: 'statusApproved' },
  rejected: { label: '已驳回', cls: 'statusRejected' },
};

const LeaveRequestPage: React.FC = () => {
  const [balances, setBalances] = useState<LeaveBalance[]>([]);
  const [records, setRecords] = useState<LeaveRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [showForm, setShowForm] = useState(false);

  // 表单状态
  const [formType, setFormType] = useState('annual');
  const [formStart, setFormStart] = useState('');
  const [formEnd, setFormEnd] = useState('');
  const [formReason, setFormReason] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [balRes, recRes] = await Promise.all([
        apiClient.get<{ code: number; data: LeaveBalance[] }>(`/api/v1/hr/self-service/my-leave-balance?employee_id=${EMP_ID}`),
        apiClient.get<{ code: number; data: LeaveRecord[] }>(`/api/v1/hr/self-service/my-leaves?employee_id=${EMP_ID}`),
      ]);
      setBalances(balRes.data || []);
      setRecords(recRes.data || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSubmit = async () => {
    if (!formStart || !formEnd || !formReason.trim()) return;
    setSubmitting(true);
    try {
      await apiClient.post('/api/v1/hr/self-service/leave-request', {
        employee_id: EMP_ID,
        store_id: STORE_ID,
        leave_category: formType,
        start_date: formStart,
        end_date: formEnd,
        reason: formReason.trim(),
      });
      setShowForm(false);
      setFormReason('');
      setFormStart('');
      setFormEnd('');
      await loadData();
    } catch { /* silent */ }
    setSubmitting(false);
  };

  if (loading) {
    return <div className={styles.page}><div className={styles.loading}>加载中...</div></div>;
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>请假申请</h1>
        {!showForm && (
          <button className={styles.newBtn} onClick={() => setShowForm(true)}>
            + 新建
          </button>
        )}
      </div>

      {/* 假期余额 */}
      {balances.length > 0 && (
        <div className={styles.balanceCard}>
          <div className={styles.cardTitle}>假期余额</div>
          <div className={styles.balanceGrid}>
            {balances.map((b) => (
              <div key={b.leave_category} className={styles.balanceItem}>
                <div className={styles.balanceNum}>{b.remaining_days}</div>
                <div className={styles.balanceLabel}>
                  {LEAVE_LABELS[b.leave_category] || b.leave_category}
                </div>
                <div className={styles.balanceSub}>
                  共{b.total_days}天 · 已用{b.used_days}天
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 请假表单 */}
      {showForm && (
        <div className={styles.formCard}>
          <div className={styles.cardTitle}>新建请假</div>

          <div className={styles.formGroup}>
            <label className={styles.formLabel}>请假类型</label>
            <select
              className={styles.formSelect}
              value={formType}
              onChange={(e) => setFormType(e.target.value)}
            >
              {LEAVE_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          <div className={styles.formRow}>
            <div className={styles.formGroup}>
              <label className={styles.formLabel}>开始日期</label>
              <input
                type="date"
                className={styles.formInput}
                value={formStart}
                onChange={(e) => setFormStart(e.target.value)}
              />
            </div>
            <div className={styles.formGroup}>
              <label className={styles.formLabel}>结束日期</label>
              <input
                type="date"
                className={styles.formInput}
                value={formEnd}
                onChange={(e) => setFormEnd(e.target.value)}
              />
            </div>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.formLabel}>请假原因</label>
            <textarea
              className={styles.formTextarea}
              value={formReason}
              onChange={(e) => setFormReason(e.target.value)}
              placeholder="请填写请假原因..."
              rows={3}
            />
          </div>

          <div className={styles.formActions}>
            <button
              className={styles.cancelBtn}
              onClick={() => setShowForm(false)}
            >
              取消
            </button>
            <button
              className={styles.submitBtn}
              onClick={handleSubmit}
              disabled={submitting || !formStart || !formEnd || !formReason.trim()}
            >
              {submitting ? '提交中...' : '提交申请'}
            </button>
          </div>
        </div>
      )}

      {/* 请假记录 */}
      <div className={styles.card}>
        <div className={styles.cardTitle}>请假记录</div>
        {records.length === 0 ? (
          <div className={styles.empty}>暂无请假记录</div>
        ) : (
          records.map((r) => {
            const st = STATUS_MAP[r.status] || { label: r.status, cls: 'statusPending' };
            return (
              <div key={r.id} className={styles.recordItem}>
                <div className={styles.recordInfo}>
                  <div className={styles.recordType}>
                    {LEAVE_LABELS[r.leave_category] || r.leave_category}
                    <span className={styles.recordDays}>{r.leave_days}天</span>
                  </div>
                  <div className={styles.recordDates}>
                    {r.start_date} ~ {r.end_date}
                  </div>
                  <div className={styles.recordReason}>{r.reason}</div>
                </div>
                <span className={styles[st.cls]}>{st.label}</span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

export default LeaveRequestPage;
