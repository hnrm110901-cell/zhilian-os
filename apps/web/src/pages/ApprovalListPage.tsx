import React, { useState, useCallback, useEffect } from 'react';
import { DatePicker, Drawer } from 'antd';
import { ReloadOutlined, EyeOutlined } from '@ant-design/icons';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZSelect, ZTable, ZInput,
} from '../design-system/components';
import type { ZTableColumn } from '../design-system/components/ZTable';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';
import styles from './ApprovalListPage.module.css';

const { RangePicker } = DatePicker;

const STATUS_BADGE_TYPE: Record<string, 'warning' | 'success' | 'critical' | 'info' | 'default'> = {
  pending:  'warning',
  approved: 'success',
  rejected: 'critical',
  modified: 'info',
};
const STATUS_LABEL: Record<string, string> = {
  pending:  '待审批',
  approved: '已批准',
  rejected: '已拒绝',
  modified: '已修改',
};

const DECISION_TYPE_LABEL: Record<string, string> = {
  inventory_adjustment: '库存调整',
  price_change:         '价格变更',
  staff_scheduling:     '排班调整',
  promotion:            '促销决策',
  menu_change:          '菜单变更',
  supplier_change:      '供应商变更',
};

interface Approval {
  id: string;
  decision_id: string;
  store_id: string;
  decision_type: string;
  description: string;
  confidence: number;
  status: string;
  reason?: string;
  modified_decision?: string;
  original_value?: any;
  suggested_value?: any;
  impact_level?: string;
  approved_by?: string;
  rejected_by?: string;
  created_at: string;
  updated_at: string;
}

const ApprovalListPage: React.FC = () => {
  const [approvals, setApprovals]     = useState<Approval[]>([]);
  const [loading, setLoading]         = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [storeFilter, setStoreFilter] = useState('');
  const [typeFilter, setTypeFilter]   = useState<string>('all');
  const [dateRange, setDateRange]     = useState<[any, any] | null>(null);
  const [drawerOpen, setDrawerOpen]   = useState(false);
  const [selected, setSelected]       = useState<Approval | null>(null);

  const loadApprovals = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, any> = {};
      if (statusFilter !== 'all') params.status = statusFilter;
      if (storeFilter) params.store_id = storeFilter;
      if (typeFilter !== 'all') params.decision_type = typeFilter;
      if (dateRange) {
        params.start_date = dateRange[0]?.format('YYYY-MM-DD');
        params.end_date   = dateRange[1]?.format('YYYY-MM-DD');
      }
      const res = await apiClient.get('/api/v1/approvals', { params });
      setApprovals(res.data?.approvals || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载审批列表失败');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, storeFilter, typeFilter, dateRange]);

  useEffect(() => { loadApprovals(); }, [loadApprovals]);

  const openDetail = (record: Approval) => {
    setSelected(record);
    setDrawerOpen(true);
  };

  const counts = {
    all:      approvals.length,
    pending:  approvals.filter(a => a.status === 'pending').length,
    approved: approvals.filter(a => a.status === 'approved').length,
    rejected: approvals.filter(a => a.status === 'rejected').length,
    modified: approvals.filter(a => a.status === 'modified').length,
  };

  const approvalRate = counts.all
    ? ((counts.approved + counts.modified) / counts.all * 100).toFixed(1)
    : '0.0';

  const columns: ZTableColumn<Approval>[] = [
    {
      key:    'decision_id',
      title:  '决策ID',
      width:  180,
      render: (v: string) => (
        <span title={v} style={{ fontFamily: 'monospace', fontSize: 12 }}>
          {v?.slice(0, 16)}…
        </span>
      ),
    },
    { key: 'store_id',  title: '门店',     width: 120 },
    {
      key:    'decision_type',
      title:  '决策类型',
      width:  120,
      render: (v: string) => DECISION_TYPE_LABEL[v] || v,
    },
    {
      key:    'description',
      title:  '描述',
      render: (v: string) => (
        <span className={styles.ellipsis} title={v}>{v}</span>
      ),
    },
    {
      key:    'confidence',
      title:  '置信度',
      width:  80,
      align:  'right',
      render: (v: number) => v != null ? `${(v * 100).toFixed(0)}%` : '—',
    },
    {
      key:    'status',
      title:  '状态',
      width:  90,
      align:  'center',
      render: (v: string) => (
        <ZBadge type={STATUS_BADGE_TYPE[v] ?? 'default'} text={STATUS_LABEL[v] || v} />
      ),
    },
    {
      key:    'created_at',
      title:  '创建时间',
      width:  160,
      render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '—',
    },
    {
      key:    'id',
      title:  '操作',
      width:  80,
      align:  'center',
      render: (_: any, row: Approval) => (
        <ZButton size="sm" icon={<EyeOutlined />} onClick={() => openDetail(row)}>
          详情
        </ZButton>
      ),
    },
  ];

  const statusOptions = [
    { value: 'all',      label: '全部' },
    { value: 'pending',  label: '待审批' },
    { value: 'approved', label: '已批准' },
    { value: 'rejected', label: '已拒绝' },
    { value: 'modified', label: '已修改' },
  ];

  const typeOptions = [
    { value: 'all', label: '全部类型' },
    ...Object.entries(DECISION_TYPE_LABEL).map(([k, v]) => ({ value: k, label: v })),
  ];

  return (
    <div className={styles.page}>
      {/* KPI 汇总 */}
      <div className={styles.kpiGrid}>
        <ZCard><ZKpi value={counts.all}      label="全部" /></ZCard>
        <ZCard><ZKpi value={counts.pending}  label="待审批" /></ZCard>
        <ZCard><ZKpi value={counts.approved} label="已批准" /></ZCard>
        <ZCard><ZKpi value={counts.rejected} label="已拒绝" /></ZCard>
        <ZCard><ZKpi value={counts.modified} label="已修改" /></ZCard>
        <ZCard><ZKpi value={approvalRate}    label="批准率" unit="%" /></ZCard>
      </div>

      {/* 筛选栏 */}
      <ZCard style={{ marginBottom: 14 }}>
        <div className={styles.filterRow}>
          <span className={styles.filterLabel}>状态：</span>
          <ZSelect
            value={statusFilter}
            options={statusOptions}
            onChange={(v) => setStatusFilter(v as string)}
            style={{ width: 120 }}
          />
          <span className={styles.filterLabel}>门店：</span>
          <ZInput
            placeholder="输入门店ID"
            value={storeFilter}
            onChange={setStoreFilter}
            onClear={() => setStoreFilter('')}
            style={{ width: 160 }}
          />
          <span className={styles.filterLabel}>类型：</span>
          <ZSelect
            value={typeFilter}
            options={typeOptions}
            onChange={(v) => setTypeFilter(v as string)}
            style={{ width: 130 }}
          />
          <span className={styles.filterLabel}>时间：</span>
          <RangePicker onChange={(v: any) => setDateRange(v)} />
          <ZButton icon={<ReloadOutlined />} onClick={loadApprovals}>刷新</ZButton>
        </div>
      </ZCard>

      {/* 表格 */}
      <ZCard>
        {loading ? (
          <ZSkeleton rows={6} block />
        ) : (
          <ZTable<Approval>
            columns={columns}
            data={approvals}
            rowKey={(r) => r.decision_id || r.id}
            emptyText="暂无审批数据"
          />
        )}
      </ZCard>

      {/* 详情抽屉 */}
      <Drawer
        title="审批详情"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={560}
      >
        {selected && (
          <div className={styles.drawerContent}>
            <dl className={styles.descList}>
              <div className={styles.descRow}>
                <dt>决策ID</dt>
                <dd><span style={{ fontFamily: 'monospace', fontSize: 12 }}>{selected.decision_id}</span></dd>
              </div>
              <div className={styles.descRow}>
                <dt>门店</dt>
                <dd>{selected.store_id}</dd>
              </div>
              <div className={styles.descRow}>
                <dt>决策类型</dt>
                <dd>{DECISION_TYPE_LABEL[selected.decision_type] || selected.decision_type}</dd>
              </div>
              <div className={styles.descRow}>
                <dt>状态</dt>
                <dd>
                  <ZBadge
                    type={STATUS_BADGE_TYPE[selected.status] ?? 'default'}
                    text={STATUS_LABEL[selected.status] || selected.status}
                  />
                </dd>
              </div>
              <div className={styles.descRow}>
                <dt>置信度</dt>
                <dd>{selected.confidence != null ? `${(selected.confidence * 100).toFixed(1)}%` : '—'}</dd>
              </div>
              {selected.impact_level && (
                <div className={styles.descRow}>
                  <dt>影响级别</dt>
                  <dd>
                    <ZBadge
                      type={selected.impact_level === 'high' ? 'critical' : selected.impact_level === 'medium' ? 'warning' : 'info'}
                      text={selected.impact_level === 'high' ? '高' : selected.impact_level === 'medium' ? '中' : '低'}
                    />
                  </dd>
                </div>
              )}
            </dl>

            <div className={styles.drawerSection}>
              <div className={styles.drawerSectionTitle}>决策描述</div>
              <p style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{selected.description || '—'}</p>
            </div>

            {(selected.original_value != null || selected.suggested_value != null) && (
              <div className={styles.drawerSection}>
                <div className={styles.drawerSectionTitle}>数值变化</div>
                <dl className={styles.descList}>
                  <div className={styles.descRow}>
                    <dt>原始值</dt>
                    <dd><code style={{ fontSize: 12 }}>{JSON.stringify(selected.original_value)}</code></dd>
                  </div>
                  <div className={styles.descRow}>
                    <dt>建议值</dt>
                    <dd><code style={{ fontSize: 12 }}>{JSON.stringify(selected.suggested_value)}</code></dd>
                  </div>
                </dl>
              </div>
            )}

            {selected.reason && (
              <div className={styles.drawerSection}>
                <div className={styles.drawerSectionTitle}>审批意见</div>
                <p style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{selected.reason}</p>
              </div>
            )}

            {selected.modified_decision && (
              <div className={styles.drawerSection}>
                <div className={styles.drawerSectionTitle}>修改后决策</div>
                <p style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{selected.modified_decision}</p>
              </div>
            )}

            <div className={styles.drawerSection}>
              <div className={styles.drawerSectionTitle}>时间信息</div>
              <dl className={styles.descList}>
                <div className={styles.descRow}>
                  <dt>创建时间</dt>
                  <dd>{selected.created_at ? new Date(selected.created_at).toLocaleString('zh-CN') : '—'}</dd>
                </div>
                <div className={styles.descRow}>
                  <dt>更新时间</dt>
                  <dd>{selected.updated_at ? new Date(selected.updated_at).toLocaleString('zh-CN') : '—'}</dd>
                </div>
                {selected.approved_by && (
                  <div className={styles.descRow}><dt>批准人</dt><dd>{selected.approved_by}</dd></div>
                )}
                {selected.rejected_by && (
                  <div className={styles.descRow}><dt>拒绝人</dt><dd>{selected.rejected_by}</dd></div>
                )}
              </dl>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default ApprovalListPage;
