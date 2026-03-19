import React, { useCallback, useEffect, useState } from 'react';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty, ZTable } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './HRLifecycle.module.css';

type TabKey = 'onboarding' | 'offboarding' | 'transfer';

interface OnboardingRow {
  id: string;
  person_name?: string;
  org_node_id: string;
  status: string;
  planned_start_date?: string;
}

interface OffboardingRow {
  id: string;
  assignment_id: string;
  reason: string;
  status: string;
  planned_last_day?: string;
  skill_loss_yuan?: number;
}

interface TransferRow {
  id: string;
  person_id: string;
  transfer_type: string;
  status: string;
  effective_date?: string;
  revenue_impact_yuan?: number;
}

const STATUS_BADGE: Record<string, 'critical' | 'warning' | 'info' | 'success'> = {
  draft: 'info',
  pending: 'warning',
  pending_review: 'warning',
  approved: 'success',
  active: 'success',
  completed: 'success',
  rejected: 'critical',
  cancelled: 'critical',
};

const ONBOARDING_COLS: ZTableColumn[] = [
  { key: 'person_name', title: '姓名' },
  { key: 'org_node_id', title: '组织节点' },
  { key: 'planned_start_date', title: '计划入职' },
  { key: 'status_badge', title: '状态' },
];

const OFFBOARDING_COLS: ZTableColumn[] = [
  { key: 'assignment_id', title: '在岗ID' },
  { key: 'reason', title: '离职原因' },
  { key: 'planned_last_day', title: '最后工作日' },
  { key: 'skill_loss_yuan_fmt', title: '技能损失¥' },
  { key: 'status_badge', title: '状态' },
];

const TRANSFER_COLS: ZTableColumn[] = [
  { key: 'person_id', title: '员工ID' },
  { key: 'transfer_type', title: '调动类型' },
  { key: 'effective_date', title: '生效日期' },
  { key: 'revenue_impact_fmt', title: '预期¥影响' },
  { key: 'status_badge', title: '状态' },
];

const TAB_LABELS: Record<TabKey, string> = {
  onboarding: '入职流程',
  offboarding: '离职流程',
  transfer: '调岗流程',
};

export default function HRLifecycle() {
  const [activeTab, setActiveTab] = useState<TabKey>('onboarding');
  const [onboardingRows, setOnboardingRows] = useState<OnboardingRow[]>([]);
  const [offboardingRows, setOffboardingRows] = useState<OffboardingRow[]>([]);
  const [transferRows, setTransferRows] = useState<TransferRow[]>([]);
  const [loading, setLoading] = useState(false);
  const orgNodeId = localStorage.getItem('org_node_id') || 'ROOT';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ob, off, tr] = await Promise.allSettled([
        apiClient.get(`/api/v1/hr/onboarding?org_node_id=${orgNodeId}`),
        apiClient.get(`/api/v1/hr/offboarding?org_node_id=${orgNodeId}`),
        apiClient.get(`/api/v1/hr/transfers?org_node_id=${orgNodeId}`),
      ]);
      setOnboardingRows(ob.status === 'fulfilled' ? ((ob.value as any).items ?? []) : []);
      setOffboardingRows(off.status === 'fulfilled' ? ((off.value as any).items ?? []) : []);
      setTransferRows(tr.status === 'fulfilled' ? ((tr.value as any).items ?? []) : []);
    } finally {
      setLoading(false);
    }
  }, [orgNodeId]);

  useEffect(() => { load(); }, [load]);

  const onboardingTableRows = onboardingRows.map((r) => ({
    ...r,
    person_name: r.person_name || '—',
    status_badge: <ZBadge type={STATUS_BADGE[r.status] ?? 'info'} text={r.status} />,
  }));

  const offboardingTableRows = offboardingRows.map((r) => ({
    ...r,
    skill_loss_yuan_fmt: r.skill_loss_yuan != null ? `¥${r.skill_loss_yuan.toFixed(0)}` : '—',
    status_badge: <ZBadge type={STATUS_BADGE[r.status] ?? 'info'} text={r.status} />,
  }));

  const transferTableRows = transferRows.map((r) => ({
    ...r,
    revenue_impact_fmt: r.revenue_impact_yuan != null
      ? (r.revenue_impact_yuan >= 0 ? `+¥${r.revenue_impact_yuan.toFixed(0)}` : `¥${r.revenue_impact_yuan.toFixed(0)}`)
      : '—',
    status_badge: <ZBadge type={STATUS_BADGE[r.status] ?? 'info'} text={r.status} />,
  }));

  const counts = {
    onboarding: onboardingRows.length,
    offboarding: offboardingRows.length,
    transfer: transferRows.length,
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <span className={styles.title}>生命周期管理</span>
        <ZButton variant="ghost" size="sm" onClick={load}>刷新</ZButton>
      </div>

      {/* 汇总KPI行 */}
      <div className={styles.kpiRow}>
        <ZCard>
          <ZKpi value={counts.onboarding} label="入职流程" unit="个" />
        </ZCard>
        <ZCard>
          <ZKpi value={counts.offboarding} label="离职流程" unit="个" />
        </ZCard>
        <ZCard>
          <ZKpi value={counts.transfer} label="调岗流程" unit="个" />
        </ZCard>
      </div>

      {/* Tab切换 */}
      <div className={styles.tabs}>
        {(Object.keys(TAB_LABELS) as TabKey[]).map((key) => (
          <button
            key={key}
            className={`${styles.tab} ${activeTab === key ? styles.tabActive : ''}`}
            onClick={() => setActiveTab(key)}
          >
            {TAB_LABELS[key]}
            {counts[key] > 0 && (
              <span className={styles.tabBadge}>{counts[key]}</span>
            )}
          </button>
        ))}
      </div>

      {/* 内容区 */}
      <ZCard>
        {loading ? (
          <ZSkeleton rows={4} />
        ) : (
          <>
            {activeTab === 'onboarding' && (
              onboardingTableRows.length === 0
                ? <ZEmpty title="暂无入职流程" description="当前无进行中的入职申请" />
                : <ZTable columns={ONBOARDING_COLS} data={onboardingTableRows} />
            )}
            {activeTab === 'offboarding' && (
              offboardingTableRows.length === 0
                ? <ZEmpty title="暂无离职流程" description="当前无进行中的离职申请" />
                : <ZTable columns={OFFBOARDING_COLS} data={offboardingTableRows} />
            )}
            {activeTab === 'transfer' && (
              transferTableRows.length === 0
                ? <ZEmpty title="暂无调岗流程" description="当前无进行中的调岗申请" />
                : <ZTable columns={TRANSFER_COLS} data={transferTableRows} />
            )}
          </>
        )}
      </ZCard>
    </div>
  );
}
