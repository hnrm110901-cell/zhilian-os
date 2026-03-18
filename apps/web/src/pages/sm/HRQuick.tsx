/**
 * 店长HR快捷操作页（移动端）
 * 路由：/sm/hr
 * 功能：待审批列表（一键批/驳）+ 今日出勤概览 + 快捷入口
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../../services/api';
import styles from './HRQuick.module.css';

const STORE_ID = localStorage.getItem('store_id') || '';

interface PendingLeave {
  id: string;
  employee_id: string;
  employee_name: string;
  leave_category: string;
  start_date: string;
  end_date: string;
  leave_days: number;
  reason: string;
}

interface HRStats {
  total_active_employees: number;
  pending_leave_requests: number;
  contracts_expiring_30d: number;
  month_onboard: number;
  month_resign: number;
  attendance_rate_pct: number;
}

const LEAVE_LABELS: Record<string, string> = {
  annual: '年假', sick: '病假', personal: '事假',
  maternity: '产假', paternity: '陪产假', marriage: '婚假',
  bereavement: '丧假', compensatory: '调休', other: '其他',
};

const SmHRQuick: React.FC = () => {
  const navigate = useNavigate();
  const [stats, setStats] = useState<HRStats | null>(null);
  const [pendingLeaves, setPendingLeaves] = useState<PendingLeave[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [overview, leaves] = await Promise.all([
        apiClient.get<HRStats>(`/api/v1/hr/dashboard/overview?store_id=${STORE_ID}`),
        apiClient.get<{ items: PendingLeave[] }>(`/api/v1/hr/leave/requests?store_id=${STORE_ID}&status=pending`),
      ]);
      setStats(overview);
      setPendingLeaves(leaves.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleApprove = async (id: string) => {
    try {
      await apiClient.post(`/api/v1/hr/leave/requests/${id}/approve`, {
        approver_id: 'current_user',
      });
      setPendingLeaves(prev => prev.filter(l => l.id !== id));
    } catch { /* silent */ }
  };

  const handleReject = async (id: string) => {
    try {
      await apiClient.post(`/api/v1/hr/leave/requests/${id}/reject`, {
        approver_id: 'current_user',
        reason: '店长驳回',
      });
      setPendingLeaves(prev => prev.filter(l => l.id !== id));
    } catch { /* silent */ }
  };

  if (loading) {
    return <div className={styles.page}><div className={styles.empty}>加载中...</div></div>;
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>人力管理</h1>
        <p className={styles.subtitle}>员工假勤 · 审批 · 人力概况</p>
      </div>

      {/* 关键指标 */}
      {stats && (
        <div className={styles.statRow}>
          <div className={styles.statItem}>
            <div className={styles.statNum}>{stats.total_active_employees}</div>
            <div className={styles.statLabel}>在职</div>
          </div>
          <div className={styles.statItem}>
            <div className={`${styles.statNum} ${styles.statNumMint}`}>
              {stats.attendance_rate_pct}%
            </div>
            <div className={styles.statLabel}>出勤率</div>
          </div>
          <div className={styles.statItem}>
            <div className={`${styles.statNum} ${stats.pending_leave_requests > 0 ? styles.statNumWarn : ''}`}>
              {stats.pending_leave_requests}
            </div>
            <div className={styles.statLabel}>待审批</div>
          </div>
        </div>
      )}

      {/* 快捷入口 */}
      <div className={styles.quickGrid}>
        <button className={styles.quickBtn} onClick={() => navigate('/employee-roster')}>
          <span className={styles.quickIcon}>👥</span>
          <span className={styles.quickLabel}>花名册</span>
        </button>
        <button className={styles.quickBtn} onClick={() => navigate('/leave-management')}>
          <span className={styles.quickIcon}>📋</span>
          <span className={styles.quickLabel}>假勤</span>
        </button>
        <button className={styles.quickBtn} onClick={() => navigate('/attendance-report')}>
          <span className={styles.quickIcon}>📊</span>
          <span className={styles.quickLabel}>考勤</span>
        </button>
        <button className={styles.quickBtn} onClick={() => navigate('/employee-lifecycle')}>
          <span className={styles.quickIcon}>🔄</span>
          <span className={styles.quickLabel}>入离职</span>
        </button>
      </div>

      {/* 待审批假条 */}
      <div className={styles.card}>
        <div className={styles.cardTitle}>
          待审批假条 ({pendingLeaves.length})
        </div>
        {pendingLeaves.length === 0 ? (
          <div className={styles.empty}>暂无待审批假条</div>
        ) : (
          pendingLeaves.map(leave => (
            <div key={leave.id} className={styles.approvalItem}>
              <div className={styles.approvalInfo}>
                <div className={styles.approvalName}>
                  {leave.employee_name}
                  <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.38)', marginLeft: 6 }}>
                    {LEAVE_LABELS[leave.leave_category] || leave.leave_category}
                  </span>
                </div>
                <div className={styles.approvalMeta}>
                  {leave.start_date} ~ {leave.end_date} · {leave.leave_days}天
                </div>
                <div className={styles.approvalMeta}>
                  {leave.reason}
                </div>
              </div>
              <div className={styles.approvalBtns}>
                <button className={styles.btnApprove} onClick={() => handleApprove(leave.id)}>
                  批准
                </button>
                <button className={styles.btnReject} onClick={() => handleReject(leave.id)}>
                  驳回
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* 人力异常提醒 */}
      {stats && (stats.contracts_expiring_30d > 0 || stats.month_resign > 0) && (
        <div className={styles.card} style={{ borderColor: 'rgba(235, 87, 87, 0.15)' }}>
          <div className={styles.cardTitle} style={{ color: '#EB5757' }}>人力提醒</div>
          {stats.contracts_expiring_30d > 0 && (
            <div className={styles.approvalItem}>
              <div className={styles.approvalInfo}>
                <div className={styles.approvalName}>合同即将到期</div>
                <div className={styles.approvalMeta}>
                  {stats.contracts_expiring_30d} 份合同将在30天内到期
                </div>
              </div>
              <button className={styles.btnApprove} onClick={() => navigate('/contract-management')}
                style={{ background: 'rgba(242, 153, 74, 0.15)', color: '#F2994A' }}>
                查看
              </button>
            </div>
          )}
          {stats.month_resign > 0 && (
            <div className={styles.approvalItem}>
              <div className={styles.approvalInfo}>
                <div className={styles.approvalName}>本月离职</div>
                <div className={styles.approvalMeta}>
                  本月已有 {stats.month_resign} 人离职
                </div>
              </div>
              <button className={styles.btnApprove} onClick={() => navigate('/employee-lifecycle')}
                style={{ background: 'rgba(242, 153, 74, 0.15)', color: '#F2994A' }}>
                查看
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default SmHRQuick;
