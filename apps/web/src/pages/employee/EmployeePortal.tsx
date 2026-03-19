/**
 * 员工H5自助首页 — 卡片式快捷入口 + 当月摘要
 * 路由：/emp
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../../services/api';
import styles from './EmployeePortal.module.css';

const EMP_ID = localStorage.getItem('employee_id') || 'EMP_001';

interface SummaryData {
  attendance_days: number;
  late_count: number;
  leave_balance_annual: number;
  pending_courses: number;
}

const QUICK_ENTRIES = [
  { key: 'payslip',    icon: '💰', label: '我的工资条', path: '/emp/payslip' },
  { key: 'attendance', icon: '📅', label: '我的考勤',   path: '/emp/attendance' },
  { key: 'leave',      icon: '📝', label: '请假申请',   path: '/emp/leave' },
  { key: 'training',   icon: '📚', label: '我的培训',   path: '/emp/training' },
  { key: 'contract',   icon: '📄', label: '我的合同',   path: '/emp/profile' },
  { key: 'profile',    icon: '👤', label: '个人信息',   path: '/emp/profile' },
];

const EmployeePortal: React.FC = () => {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [profileName, setProfileName] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const now = new Date();
      const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;

      const [profileRes, attendanceRes, balanceRes, coursesRes] = await Promise.all([
        apiClient.get<{ code: number; data: { name: string } }>(`/api/v1/hr/self-service/my-profile?employee_id=${EMP_ID}`),
        apiClient.get<{ code: number; data: { stats: { total_days: number; late: number } } }>(`/api/v1/hr/self-service/my-attendance/${month}?employee_id=${EMP_ID}`),
        apiClient.get<{ code: number; data: Array<{ leave_category: string; remaining_days: number }> }>(`/api/v1/hr/self-service/my-leave-balance?employee_id=${EMP_ID}`),
        apiClient.get<{ code: number; data: Array<{ status: string }> }>(`/api/v1/hr/self-service/my-courses?employee_id=${EMP_ID}`),
      ]);

      setProfileName(profileRes.data?.name || '员工');

      const annualBalance = (balanceRes.data || []).find(
        (b) => b.leave_category === 'annual'
      );
      const pendingCourses = (coursesRes.data || []).filter(
        (c) => c.status === 'in_progress' || c.status === 'enrolled'
      );

      setSummary({
        attendance_days: attendanceRes.data?.stats?.total_days || 0,
        late_count: attendanceRes.data?.stats?.late || 0,
        leave_balance_annual: annualBalance?.remaining_days || 0,
        pending_courses: pendingCourses.length,
      });
    } catch {
      /* 降级处理 — 显示空状态 */
      setProfileName('员工');
      setSummary({ attendance_days: 0, late_count: 0, leave_balance_annual: 0, pending_courses: 0 });
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return <div className={styles.page}><div className={styles.loading}>加载中...</div></div>;
  }

  return (
    <div className={styles.page}>
      {/* 欢迎头部 */}
      <div className={styles.header}>
        <div className={styles.greeting}>你好，{profileName}</div>
        <div className={styles.dateLine}>
          {new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}
        </div>
      </div>

      {/* 本月摘要 */}
      {summary && (
        <div className={styles.summaryCard}>
          <div className={styles.summaryTitle}>本月概览</div>
          <div className={styles.summaryGrid}>
            <div className={styles.summaryItem}>
              <div className={styles.summaryNum}>{summary.attendance_days}</div>
              <div className={styles.summaryLabel}>出勤天数</div>
            </div>
            <div className={styles.summaryItem}>
              <div className={`${styles.summaryNum} ${summary.late_count > 0 ? styles.numWarn : ''}`}>
                {summary.late_count}
              </div>
              <div className={styles.summaryLabel}>迟到</div>
            </div>
            <div className={styles.summaryItem}>
              <div className={styles.summaryNum}>{summary.leave_balance_annual}</div>
              <div className={styles.summaryLabel}>年假余额</div>
            </div>
            <div className={styles.summaryItem}>
              <div className={`${styles.summaryNum} ${summary.pending_courses > 0 ? styles.numMint : ''}`}>
                {summary.pending_courses}
              </div>
              <div className={styles.summaryLabel}>待学课程</div>
            </div>
          </div>
        </div>
      )}

      {/* 快捷入口 */}
      <div className={styles.quickGrid}>
        {QUICK_ENTRIES.map((entry) => (
          <button
            key={entry.key}
            className={styles.quickBtn}
            onClick={() => navigate(entry.path)}
          >
            <span className={styles.quickIcon}>{entry.icon}</span>
            <span className={styles.quickLabel}>{entry.label}</span>
          </button>
        ))}
      </div>

      {/* 温馨提示 */}
      <div className={styles.tipsCard}>
        <div className={styles.tipsTitle}>温馨提示</div>
        <div className={styles.tipsContent}>
          工资条发放后请及时确认，如有疑问请联系门店负责人。
        </div>
      </div>
    </div>
  );
};

export default EmployeePortal;
