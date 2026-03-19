import React, { useCallback, useEffect, useState } from 'react';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty, ZTable } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './HRApprovals.module.css';

interface ApprovalItem {
  id: string;
  resource_type: string;
  resource_id: string;
  status: string;
  current_step: number;
  created_by: string;
  created_at?: string;
}

interface StepRecord {
  step: number;
  approver_id: string;
  approver_name: string;
  action: string;
  comment?: string;
  acted_at?: string;
}

interface ApprovalDetail {
  instance_id: string;
  resource_type: string;
  resource_id: string;
  status: string;
  current_step: number;
  created_by: string;
  created_at?: string;
  steps: StepRecord[];
}

const RESOURCE_TYPE_LABELS: Record<string, string> = {
  onboarding: '入职审批',
  offboarding: '离职审批',
  transfer: '调岗审批',
};

const STATUS_BADGE: Record<string, 'critical' | 'warning' | 'info' | 'success'> = {
  pending: 'warning',
  approved: 'success',
  rejected: 'critical',
  cancelled: 'info',
  delegated: 'info',
};

const ACTION_LABELS: Record<string, string> = {
  pending: '待处理',
  approved: '已通过',
  rejected: '已驳回',
  delegated: '已委托',
};

const COLS: ZTableColumn[] = [
  { key: 'resource_type_label', title: '类型' },
  { key: 'created_by', title: '申请人' },
  { key: 'current_step_label', title: '当前步骤' },
  { key: 'created_at_fmt', title: '申请时间' },
  { key: 'status_badge', title: '状态' },
  { key: 'actions', title: '操作' },
];

export default function HRApprovals() {
  const [items, setItems] = useState<ApprovalItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedDetail, setSelectedDetail] = useState<ApprovalDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const approverId = localStorage.getItem('user_id') || 'admin';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/hr/approvals/pending?approver_id=${approverId}`);
      setItems((resp as any).items ?? []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [approverId]);

  useEffect(() => { load(); }, [load]);

  const loadDetail = async (instanceId: string) => {
    setDetailLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/hr/approvals/${instanceId}`);
      setSelectedDetail(resp as ApprovalDetail);
    } catch {
      setSelectedDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleApprove = async (instanceId: string) => {
    try {
      await apiClient.post(`/api/v1/hr/approvals/${instanceId}/approve`, {
        approver_id: approverId,
        action: 'approved',
      });
      await load();
      setSelectedDetail(null);
    } catch { /* 静默 */ }
  };

  const handleReject = async (instanceId: string) => {
    try {
      await apiClient.post(`/api/v1/hr/approvals/${instanceId}/reject`, {
        approver_id: approverId,
        action: 'rejected',
        comment: '驳回',
      });
      await load();
      setSelectedDetail(null);
    } catch { /* 静默 */ }
  };

  const tableRows = items.map((item) => ({
    ...item,
    resource_type_label: (
      <ZBadge type="info" text={RESOURCE_TYPE_LABELS[item.resource_type] ?? item.resource_type} />
    ),
    current_step_label: `第${item.current_step}步`,
    created_at_fmt: item.created_at ? new Date(item.created_at).toLocaleDateString('zh-CN') : '—',
    status_badge: <ZBadge type={STATUS_BADGE[item.status] ?? 'info'} text={ACTION_LABELS[item.status] ?? item.status} />,
    actions: (
      <div className={styles.actionBtns}>
        <ZButton variant="primary" size="sm" onClick={() => handleApprove(item.id)}>通过</ZButton>
        <ZButton variant="ghost" size="sm" onClick={() => handleReject(item.id)}>驳回</ZButton>
        <ZButton variant="ghost" size="sm" onClick={() => loadDetail(item.id)}>详情</ZButton>
      </div>
    ),
  }));

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <span className={styles.title}>审批中心</span>
        <ZButton variant="ghost" size="sm" onClick={load}>刷新</ZButton>
      </div>

      <div className={styles.kpiRow}>
        <ZCard>
          <ZKpi value={items.length} label="待审批" unit="件" />
        </ZCard>
        <ZCard>
          <ZKpi value="—" label="平均处理时长" unit="小时" />
        </ZCard>
      </div>

      <ZCard title="待我审批">
        {loading ? (
          <ZSkeleton rows={4} />
        ) : items.length === 0 ? (
          <ZEmpty title="暂无待审批事项" description="所有审批已处理完毕" />
        ) : (
          <ZTable columns={COLS} data={tableRows} />
        )}
      </ZCard>

      {/* 审批详情面板 */}
      {selectedDetail && (
        <ZCard title="审批详情" extra={<ZButton variant="ghost" size="sm" onClick={() => setSelectedDetail(null)}>关闭</ZButton>}>
          {detailLoading ? (
            <ZSkeleton rows={3} />
          ) : (
            <div className={styles.timeline}>
              <div className={styles.detailMeta}>
                <span>类型：{RESOURCE_TYPE_LABELS[selectedDetail.resource_type] ?? selectedDetail.resource_type}</span>
                <span>申请人：{selectedDetail.created_by}</span>
                <span>状态：<ZBadge type={STATUS_BADGE[selectedDetail.status] ?? 'info'} text={ACTION_LABELS[selectedDetail.status] ?? selectedDetail.status} /></span>
              </div>
              <div className={styles.steps}>
                {selectedDetail.steps.map((s, idx) => (
                  <div key={idx} className={styles.step}>
                    <div className={`${styles.stepDot} ${s.action === 'approved' ? styles.stepApproved : s.action === 'rejected' ? styles.stepRejected : styles.stepPending}`} />
                    <div className={styles.stepContent}>
                      <span className={styles.stepLabel}>第{s.step}步 · {s.approver_name}</span>
                      <ZBadge type={STATUS_BADGE[s.action] ?? 'info'} text={ACTION_LABELS[s.action] ?? s.action} />
                      {s.comment && <span className={styles.stepComment}>{s.comment}</span>}
                      {s.acted_at && <span className={styles.stepTime}>{new Date(s.acted_at).toLocaleString('zh-CN')}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </ZCard>
      )}
    </div>
  );
}
