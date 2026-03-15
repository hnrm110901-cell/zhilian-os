import React, { useState, useCallback, useEffect } from 'react';
import { apiClient } from '../../services/api';
import styles from './HRPages.module.css';

interface LeaveItem {
  id: string;
  employee_id: string;
  employee_name: string;
  leave_category: string;
  status: string;
  start_date: string;
  end_date: string;
  leave_days: number;
  reason: string;
  created_at: string;
}

const CATEGORY_LABELS: Record<string, string> = {
  annual: '年假', sick: '病假', personal: '事假',
  maternity: '产假', paternity: '陪产假', marriage: '婚假',
  bereavement: '丧假', compensatory: '调休', other: '其他',
};

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: '#F2994A' },
  pending: { label: '审批中', color: '#2D9CDB' },
  approved: { label: '已通过', color: '#27AE60' },
  rejected: { label: '已驳回', color: '#EB5757' },
  cancelled: { label: '已取消', color: 'rgba(255,255,255,0.38)' },
};

const LeaveManagementPage: React.FC = () => {
  const [storeId] = useState('STORE_001');
  const [tab, setTab] = useState<'all' | 'pending'>('all');
  const [items, setItems] = useState<LeaveItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ store_id: storeId });
      if (tab === 'pending') params.append('status', 'pending');
      const res = await apiClient.get(`/api/v1/hr/leave/list?${params}`);
      setItems(res.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, [storeId, tab]);

  useEffect(() => { load(); }, [load]);

  const handleApprove = async (id: string) => {
    try {
      await apiClient.post(`/api/v1/hr/leave/${id}/approve`, {
        approver_id: 'current_user',
        approver_name: '当前用户',
      });
      await load();
    } catch { /* silent */ }
  };

  const handleReject = async (id: string) => {
    const reason = prompt('请输入驳回理由');
    if (reason === null) return;
    try {
      await apiClient.post(`/api/v1/hr/leave/${id}/reject`, {
        approver_id: 'current_user',
        reason,
      });
      await load();
    } catch { /* silent */ }
  };

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>假勤管理</h1>
          <p className={styles.pageDesc}>请假申请、审批与假期余额</p>
        </div>
      </div>

      {/* Tab */}
      <div className={styles.tabBar}>
        <button className={`${styles.tab} ${tab === 'all' ? styles.tabActive : ''}`} onClick={() => setTab('all')}>全部</button>
        <button className={`${styles.tab} ${tab === 'pending' ? styles.tabActive : ''}`} onClick={() => setTab('pending')}>待审批</button>
      </div>

      <div className={styles.section}>
        {loading ? (
          <div className={styles.loadingWrap}>加载中...</div>
        ) : items.length === 0 ? (
          <div className={styles.emptyWrap}>暂无请假记录</div>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>员工</th>
                  <th>假别</th>
                  <th>起止日期</th>
                  <th>天数</th>
                  <th>事由</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map(item => {
                  const st = STATUS_LABELS[item.status] || STATUS_LABELS.draft;
                  return (
                    <tr key={item.id}>
                      <td className={styles.cellName}>{item.employee_name}</td>
                      <td>{CATEGORY_LABELS[item.leave_category] || item.leave_category}</td>
                      <td>{item.start_date} ~ {item.end_date}</td>
                      <td>{item.leave_days}天</td>
                      <td className={styles.cellReason}>{item.reason}</td>
                      <td>
                        <span className={styles.badge} style={{ color: st.color, borderColor: st.color }}>
                          {st.label}
                        </span>
                      </td>
                      <td>
                        {item.status === 'pending' && (
                          <div className={styles.actionBtns}>
                            <button className={styles.btnSmallApprove} onClick={() => handleApprove(item.id)}>通过</button>
                            <button className={styles.btnSmallReject} onClick={() => handleReject(item.id)}>驳回</button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default LeaveManagementPage;
