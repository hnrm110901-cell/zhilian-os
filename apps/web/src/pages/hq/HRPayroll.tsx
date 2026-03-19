import React, { useCallback, useEffect, useState } from 'react';
import { ZCard, ZKpi, ZButton, ZEmpty, ZTable, ZBadge } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './HRPayroll.module.css';

interface PayrollBatch {
  id: string;
  org_node_id: string;
  period_year: number;
  period_month: number;
  status: string;
  total_gross_fen: number;
  total_net_fen: number;
  created_at: string;
}

const STATUS_MAP: Record<string, { type: 'info' | 'warning' | 'success' | 'critical'; text: string }> = {
  draft: { type: 'info', text: '草稿' },
  calculated: { type: 'warning', text: '已计算' },
  approved: { type: 'success', text: '已审批' },
  rejected: { type: 'critical', text: '已驳回' },
};

function fenToYuan(fen: number): string {
  return `¥${(fen / 100).toFixed(2)}`;
}

export default function HRPayroll() {
  const [year] = useState(new Date().getFullYear());
  const [month] = useState(new Date().getMonth() + 1);
  const [batches, setBatches] = useState<PayrollBatch[]>([]);
  const [loading, setLoading] = useState(false);
  const orgNodeId = localStorage.getItem('org_node_id') || 'xj-s01';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/hr/payroll/batches?org_node_id=${orgNodeId}`);
      setBatches(Array.isArray(resp) ? resp : []);
    } catch {
      setBatches([]);
    } finally {
      setLoading(false);
    }
  }, [orgNodeId]);

  useEffect(() => { load(); }, [load]);

  const createBatch = async () => {
    try {
      await apiClient.post('/api/v1/hr/payroll/batch', {
        org_node_id: orgNodeId,
        year,
        month,
        created_by: 'admin',
      });
      load();
    } catch (e) {
      console.error('创建批次失败', e);
    }
  };

  const calculateBatch = async (batchId: string) => {
    try {
      await apiClient.post(`/api/v1/hr/payroll/batch/${batchId}/calculate`);
      load();
    } catch (e) {
      console.error('计算失败', e);
    }
  };

  const approveBatch = async (batchId: string) => {
    try {
      await apiClient.post(`/api/v1/hr/payroll/batch/${batchId}/approve`, { approved_by: 'admin' });
      load();
    } catch (e) {
      console.error('审批失败', e);
    }
  };

  const exportBatch = (batchId: string) => {
    window.open(`/api/v1/hr/payroll/${batchId}/export`, '_blank');
  };

  const totalGross = batches.reduce((s, b) => s + (b.total_gross_fen || 0), 0);
  const totalNet = batches.reduce((s, b) => s + (b.total_net_fen || 0), 0);

  const columns: ZTableColumn<PayrollBatch>[] = [
    {
      key: 'period',
      title: '期间',
      render: (r) => `${r.period_year}年${r.period_month}月`,
    },
    {
      key: 'status',
      title: '状态',
      render: (r) => {
        const s = STATUS_MAP[r.status] || { type: 'info' as const, text: r.status };
        return <ZBadge type={s.type} text={s.text} />;
      },
    },
    {
      key: 'gross',
      title: '税前总额',
      render: (r) => fenToYuan(r.total_gross_fen || 0),
    },
    {
      key: 'net',
      title: '实发总额',
      render: (r) => fenToYuan(r.total_net_fen || 0),
    },
    {
      key: 'actions',
      title: '操作',
      render: (r) => (
        <div className={styles.actions}>
          {r.status === 'draft' && (
            <ZButton variant="ghost" size="sm" onClick={() => calculateBatch(r.id)}>
              计算
            </ZButton>
          )}
          {r.status === 'calculated' && (
            <ZButton variant="ghost" size="sm" onClick={() => approveBatch(r.id)}>
              审批
            </ZButton>
          )}
          {(r.status === 'calculated' || r.status === 'approved') && (
            <ZButton variant="ghost" size="sm" onClick={() => exportBatch(r.id)}>
              导出
            </ZButton>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <span className={styles.title}>薪资管理 · {year}年{month}月</span>
        <ZButton variant="primary" size="sm" onClick={createBatch}>创建批次</ZButton>
      </div>

      <div className={styles.kpiRow}>
        <ZCard><ZKpi value={batches.length} label="本月批次" unit="个" /></ZCard>
        <ZCard><ZKpi value={fenToYuan(totalGross)} label="税前总额" /></ZCard>
        <ZCard><ZKpi value={fenToYuan(totalNet)} label="实发总额" /></ZCard>
      </div>

      <ZCard title="薪资批次">
        {batches.length === 0 && !loading ? (
          <ZEmpty title="暂无薪资批次" description="点击「创建批次」开始本月薪资核算" />
        ) : (
          <ZTable data={batches} columns={columns} rowKey="id" />
        )}
      </ZCard>
    </div>
  );
}
