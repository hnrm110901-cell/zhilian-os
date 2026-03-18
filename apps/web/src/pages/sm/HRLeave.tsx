import React, { useCallback, useEffect, useState } from 'react';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty, ZInput } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './HRLeave.module.css';

interface BalanceData {
  leave_type: string;
  total_days: number;
  used_days: number;
  remaining_days: number;
}

interface SimResult {
  sufficient: boolean;
  current_remaining: number;
  shortfall: number;
}

const LEAVE_TYPE_LABELS: Record<string, string> = {
  annual: '年假',
  sick: '病假',
  personal: '事假',
  marriage: '婚假',
  maternity: '产假',
  paternity: '陪产假',
  bereavement: '丧假',
};

export default function HRLeave() {
  const [balances, setBalances] = useState<BalanceData[]>([]);
  const [loading, setLoading] = useState(true);
  const [leaveType, setLeaveType] = useState('annual');
  const [days, setDays] = useState('1');
  const [reason, setReason] = useState('');
  const [simResult, setSimResult] = useState<SimResult | null>(null);
  const [submitMsg, setSubmitMsg] = useState('');
  const assignmentId = localStorage.getItem('assignment_id') || '';
  const year = new Date().getFullYear();

  const loadBalances = useCallback(async () => {
    setLoading(true);
    try {
      const types = ['annual', 'sick', 'personal'];
      const results = await Promise.allSettled(
        types.map(t => apiClient.get(`/api/v1/hr/leave/balance?assignment_id=${assignmentId}&leave_type=${t}&year=${year}`))
      );
      const data = results
        .filter((r): r is PromiseFulfilledResult<any> => r.status === 'fulfilled')
        .map(r => r.value as BalanceData)
        .filter(b => b.remaining_days !== undefined);
      setBalances(data);
    } catch {
      setBalances([]);
    } finally {
      setLoading(false);
    }
  }, [assignmentId, year]);

  useEffect(() => { loadBalances(); }, [loadBalances]);

  const handleSimulate = async () => {
    try {
      const resp = await apiClient.get(
        `/api/v1/hr/leave/simulate?assignment_id=${assignmentId}&leave_type=${leaveType}&days=${days}&year=${year}`
      );
      setSimResult(resp as SimResult);
    } catch {
      setSimResult(null);
    }
  };

  const handleSubmit = async () => {
    const now = new Date().toISOString();
    const end = new Date(Date.now() + parseFloat(days) * 86400000).toISOString();
    try {
      await apiClient.post('/api/v1/hr/leave/apply', {
        assignment_id: assignmentId,
        leave_type: leaveType,
        start_datetime: now,
        end_datetime: end,
        days: parseFloat(days),
        reason: reason || '请假',
        created_by: localStorage.getItem('username') || 'self',
      });
      setSubmitMsg('申请已提交，等待审批');
      setSimResult(null);
    } catch {
      setSubmitMsg('提交失败，请稍后重试');
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <span className={styles.title}>假期管理</span>
      </div>

      {/* 余额卡片 */}
      <div className={styles.balanceRow}>
        {loading ? <ZSkeleton rows={2} /> : balances.length === 0 ? (
          <ZEmpty title="暂无假期余额" description="假期配额尚未发放" />
        ) : balances.map(b => (
          <ZCard key={b.leave_type}>
            <ZKpi
              value={b.remaining_days}
              label={LEAVE_TYPE_LABELS[b.leave_type] ?? b.leave_type}
              unit={`/ ${b.total_days}天`}
            />
          </ZCard>
        ))}
      </div>

      {/* 申请表单 */}
      <ZCard title="申请请假">
        <div className={styles.form}>
          <div className={styles.field}>
            <label className={styles.label}>假期类型</label>
            <select className={styles.select} value={leaveType} onChange={e => setLeaveType(e.target.value)}>
              {Object.entries(LEAVE_TYPE_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
          <div className={styles.field}>
            <label className={styles.label}>天数</label>
            <ZInput value={days} onChange={(e: any) => setDays(e.target.value)} placeholder="请假天数" />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>原因</label>
            <ZInput value={reason} onChange={(e: any) => setReason(e.target.value)} placeholder="请假原因" />
          </div>
          <div className={styles.btnRow}>
            <ZButton variant="ghost" size="sm" onClick={handleSimulate}>模拟计算</ZButton>
            <ZButton variant="primary" size="sm" onClick={handleSubmit}>提交申请</ZButton>
          </div>
        </div>

        {simResult && (
          <div className={styles.simResult}>
            <ZBadge
              type={simResult.sufficient ? 'success' : 'critical'}
              text={simResult.sufficient ? `余额充足（剩${simResult.current_remaining}天）` : `余额不足（差${simResult.shortfall}天）`}
            />
          </div>
        )}
        {submitMsg && <div className={styles.submitMsg}>{submitMsg}</div>}
      </ZCard>
    </div>
  );
}
