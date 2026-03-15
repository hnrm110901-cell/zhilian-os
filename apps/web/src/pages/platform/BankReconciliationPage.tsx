/**
 * BankReconciliationPage — /platform/bank-reconciliation
 *
 * 银行流水对账管理：导入银行流水、执行对账、流水分类与匹配、现金流概览
 *
 * 后端 API:
 *   POST /api/v1/bank-recon/import         — 导入银行流水
 *   POST /api/v1/bank-recon/run            — 执行对账
 *   GET  /api/v1/bank-recon/batches        — 批次列表
 *   GET  /api/v1/bank-recon/batches/:id    — 批次详情
 *   GET  /api/v1/bank-recon/statements     — 流水列表
 *   POST /api/v1/bank-recon/statements/:id/categorize — 分类
 *   POST /api/v1/bank-recon/statements/:id/match      — 匹配
 *   GET  /api/v1/bank-recon/stats          — 统计概览
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  ZCard, ZBadge, ZButton, ZEmpty, ZSkeleton,
} from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import { apiClient } from '../../services/api';
import styles from './BankReconciliationPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface StatsData {
  total_credit_yuan: number;
  total_debit_yuan: number;
  balance_yuan: number;
  total_count: number;
  unmatched_amount_yuan: number;
  unmatched_count: number;
}

interface StatementItem {
  id: string;
  bank_name: string;
  account_number: string;
  transaction_date: string;
  transaction_type: string;
  amount_yuan: number;
  counterparty: string | null;
  reference_number: string | null;
  description: string | null;
  category: string | null;
  is_matched: boolean;
  matched_order_id: string | null;
  import_batch_id: string | null;
}

interface BatchItem {
  id: string;
  bank_name: string;
  period_start: string;
  period_end: string;
  status: string;
  total_credit_yuan: number;
  total_debit_yuan: number;
  matched_count: number;
  unmatched_count: number;
  diff_yuan: number;
  completed_at: string | null;
  created_at: string | null;
}

interface BatchDetail {
  batch: BatchItem;
  statements: StatementItem[];
  statement_count: number;
}

// ── 常量 ─────────────────────────────────────────────────────────────────────

const BANK_OPTIONS = [
  { value: '', label: '全部银行' },
  { value: '工商银行', label: '工商银行' },
  { value: '建设银行', label: '建设银行' },
  { value: '农业银行', label: '农业银行' },
  { value: '中国银行', label: '中国银行' },
  { value: '招商银行', label: '招商银行' },
  { value: '交通银行', label: '交通银行' },
  { value: '民生银行', label: '民生银行' },
  { value: '其他', label: '其他' },
];

const CATEGORY_OPTIONS = [
  { value: '', label: '全部分类' },
  { value: 'sales', label: '销售收入' },
  { value: 'purchase', label: '采购支出' },
  { value: 'salary', label: '工资薪酬' },
  { value: 'rent', label: '租金物业' },
  { value: 'tax', label: '税费' },
  { value: 'other', label: '其他' },
];

const CATEGORY_LABEL: Record<string, string> = {
  sales: '销售收入',
  purchase: '采购支出',
  salary: '工资薪酬',
  rent: '租金物业',
  tax: '税费',
  other: '其他',
};

const STATUS_MAP: Record<string, { label: string; cls: string }> = {
  pending: { label: '等待中', cls: 'statusPending' },
  processing: { label: '进行中', cls: 'statusProcessing' },
  completed: { label: '已完成', cls: 'statusCompleted' },
  error: { label: '失败', cls: 'statusError' },
};

// ── 工具函数 ─────────────────────────────────────────────────────────────────

function fmtYuan(v?: number | null): string {
  if (v == null) return '--';
  return `¥${v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtDate(iso?: string | null): string {
  if (!iso) return '--';
  return iso.slice(0, 10);
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function thirtyDaysAgo(): string {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  return d.toISOString().slice(0, 10);
}

// ── 主组件 ───────────────────────────────────────────────────────────────────

const BankReconciliationPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'statements' | 'reconcile' | 'cashflow'>('statements');
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<StatsData | null>(null);

  // Tab 1: 流水管理
  const [statements, setStatements] = useState<StatementItem[]>([]);
  const [stmtTotal, setStmtTotal] = useState(0);
  const [stmtPage, setStmtPage] = useState(1);
  const [filterBank, setFilterBank] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [filterMatched, setFilterMatched] = useState('');
  const [filterStartDate, setFilterStartDate] = useState(thirtyDaysAgo());
  const [filterEndDate, setFilterEndDate] = useState(today());

  // Tab 2: 银行对账
  const [batches, setBatches] = useState<BatchItem[]>([]);
  const [batchTotal, setBatchTotal] = useState(0);
  const [batchPage, setBatchPage] = useState(1);
  const [selectedBatch, setSelectedBatch] = useState<BatchDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // 模态框
  const [showUpload, setShowUpload] = useState(false);
  const [uploadBank, setUploadBank] = useState('招商银行');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

  const [showRunModal, setShowRunModal] = useState(false);
  const [runBank, setRunBank] = useState('招商银行');
  const [runStart, setRunStart] = useState(thirtyDaysAgo());
  const [runEnd, setRunEnd] = useState(today());
  const [running, setRunning] = useState(false);

  // 分类弹窗
  const [categorizingId, setCategorizingId] = useState<string | null>(null);
  const [categorizeValue, setCategorizeValue] = useState('sales');

  // ── 数据加载 ─────────────────────────────────────────────────────────────

  const fetchStats = useCallback(async () => {
    try {
      const resp = await apiClient.get<{ success: boolean; data: StatsData }>(
        '/api/v1/bank-recon/stats'
      );
      if (resp.success) setStats(resp.data);
    } catch (err) {
      console.error('获取统计失败', err);
    }
  }, []);

  const fetchStatements = useCallback(async (page = 1) => {
    try {
      const params = new URLSearchParams();
      if (filterBank) params.set('bank_name', filterBank);
      if (filterCategory) params.set('category', filterCategory);
      if (filterMatched === 'true') params.set('is_matched', 'true');
      if (filterMatched === 'false') params.set('is_matched', 'false');
      if (filterStartDate) params.set('start_date', filterStartDate);
      if (filterEndDate) params.set('end_date', filterEndDate);
      params.set('page', String(page));
      params.set('page_size', '20');

      const resp = await apiClient.get<{
        success: boolean;
        data: { statements: StatementItem[]; total: number };
      }>(`/api/v1/bank-recon/statements?${params}`);
      if (resp.success) {
        setStatements(resp.data.statements);
        setStmtTotal(resp.data.total);
      }
    } catch (err) {
      console.error('获取流水失败', err);
    }
  }, [filterBank, filterCategory, filterMatched, filterStartDate, filterEndDate]);

  const fetchBatches = useCallback(async (page = 1) => {
    try {
      const params = new URLSearchParams();
      params.set('page', String(page));
      params.set('page_size', '20');

      const resp = await apiClient.get<{
        success: boolean;
        data: { batches: BatchItem[]; total: number };
      }>(`/api/v1/bank-recon/batches?${params}`);
      if (resp.success) {
        setBatches(resp.data.batches);
        setBatchTotal(resp.data.total);
      }
    } catch (err) {
      console.error('获取批次失败', err);
    }
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([fetchStats(), fetchStatements(1), fetchBatches(1)]);
    setStmtPage(1);
    setBatchPage(1);
    setLoading(false);
  }, [fetchStats, fetchStatements, fetchBatches]);

  useEffect(() => { loadAll(); }, [loadAll]);

  // ── 操作 ─────────────────────────────────────────────────────────────────

  const openBatchDetail = useCallback(async (batchId: string) => {
    setDetailLoading(true);
    try {
      const resp = await apiClient.get<{ success: boolean; data: BatchDetail }>(
        `/api/v1/bank-recon/batches/${batchId}`
      );
      if (resp.success) setSelectedBatch(resp.data);
    } catch (err) {
      console.error('获取批次详情失败', err);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const handleUpload = useCallback(async () => {
    if (!uploadFile) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      formData.append('bank_name', uploadBank);

      const resp = await apiClient.post<{
        success: boolean;
        data: { imported: number; errors: string[] };
        message: string;
      }>(
        '/api/v1/bank-recon/import',
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );

      if (resp.success) {
        const errMsg = resp.data.errors.length > 0
          ? '\n部分行解析失败: ' + resp.data.errors.slice(0, 3).join('; ')
          : '';
        alert(`${resp.message}${errMsg}`);
        setShowUpload(false);
        setUploadFile(null);
        loadAll();
      }
    } catch (err: any) {
      alert('导入失败: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setUploading(false);
    }
  }, [uploadFile, uploadBank, loadAll]);

  const handleRun = useCallback(async () => {
    setRunning(true);
    try {
      const resp = await apiClient.post<{ success: boolean; message: string; data: any }>(
        '/api/v1/bank-recon/run',
        { bank_name: runBank, period_start: runStart, period_end: runEnd }
      );

      if (resp.success) {
        alert(resp.message);
        setShowRunModal(false);
        loadAll();
      }
    } catch (err: any) {
      alert('对账失败: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setRunning(false);
    }
  }, [runBank, runStart, runEnd, loadAll]);

  const handleCategorize = useCallback(async () => {
    if (!categorizingId) return;
    try {
      const resp = await apiClient.post<{ success: boolean }>(
        `/api/v1/bank-recon/statements/${categorizingId}/categorize`,
        { category: categorizeValue }
      );
      if (resp.success) {
        setCategorizingId(null);
        fetchStatements(stmtPage);
      }
    } catch (err) {
      console.error('分类失败', err);
    }
  }, [categorizingId, categorizeValue, fetchStatements, stmtPage]);

  const handleMatch = useCallback(async (statementId: string) => {
    const orderId = prompt('请输入要匹配的内部单据ID:');
    if (!orderId) return;
    try {
      const resp = await apiClient.post<{ success: boolean }>(
        `/api/v1/bank-recon/statements/${statementId}/match`,
        { order_id: orderId }
      );
      if (resp.success) {
        fetchStatements(stmtPage);
        fetchStats();
      }
    } catch (err) {
      console.error('匹配失败', err);
    }
  }, [fetchStatements, fetchStats, stmtPage]);

  // ── 流水表格列 ──────────────────────────────────────────────────────────

  const stmtColumns: ZTableColumn<StatementItem>[] = [
    {
      key: 'transaction_date',
      title: '日期',
      render: (_v, row) => fmtDate(row.transaction_date),
      width: 100,
    },
    {
      key: 'transaction_type',
      title: '类型',
      render: (_v, row) => (
        <span className={row.transaction_type === 'credit' ? styles.tagCredit : styles.tagDebit}>
          {row.transaction_type === 'credit' ? '收入' : '支出'}
        </span>
      ),
      width: 70,
    },
    {
      key: 'amount_yuan',
      title: '金额',
      render: (_v, row) => (
        <span style={{
          color: row.transaction_type === 'credit' ? '#10b981' : '#ef4444',
          fontWeight: 600,
        }}>
          {row.transaction_type === 'credit' ? '+' : '-'}{fmtYuan(row.amount_yuan)}
        </span>
      ),
      width: 120,
    },
    {
      key: 'counterparty',
      title: '对方户名',
      render: (_v, row) => row.counterparty || '--',
      width: 140,
    },
    {
      key: 'description',
      title: '摘要',
      render: (_v, row) => row.description || '--',
    },
    {
      key: 'category',
      title: '分类',
      render: (_v, row) => row.category
        ? <span className={styles.tagCategory}>{CATEGORY_LABEL[row.category] || row.category}</span>
        : <span style={{ color: '#9ca3af' }}>未分类</span>,
      width: 90,
    },
    {
      key: 'is_matched',
      title: '匹配',
      render: (_v, row) => (
        <span className={row.is_matched ? styles.tagMatched : styles.tagUnmatched}>
          {row.is_matched ? '已匹配' : '未匹配'}
        </span>
      ),
      width: 80,
    },
    {
      key: 'action',
      title: '操作',
      render: (_v, row) => (
        <div style={{ display: 'flex', gap: 4 }}>
          <ZButton size="sm" variant="ghost" onClick={() => {
            setCategorizingId(row.id);
            setCategorizeValue(row.category || 'sales');
          }}>
            分类
          </ZButton>
          {!row.is_matched && (
            <ZButton size="sm" variant="ghost" onClick={() => handleMatch(row.id)}>
              匹配
            </ZButton>
          )}
        </div>
      ),
      width: 120,
    },
  ];

  // ── 批次表格列 ──────────────────────────────────────────────────────────

  const batchColumns: ZTableColumn<BatchItem>[] = [
    {
      key: 'period',
      title: '对账周期',
      render: (_v, row) => `${fmtDate(row.period_start)} ~ ${fmtDate(row.period_end)}`,
      width: 200,
    },
    {
      key: 'bank_name',
      title: '银行',
      render: (_v, row) => row.bank_name,
      width: 100,
    },
    {
      key: 'status',
      title: '状态',
      render: (_v, row) => {
        const s = STATUS_MAP[row.status] || { label: row.status, cls: 'statusPending' };
        return <span className={styles[s.cls as keyof typeof styles]}>{s.label}</span>;
      },
      width: 80,
    },
    {
      key: 'total_credit_yuan',
      title: '收入',
      render: (_v, row) => (
        <span style={{ color: '#10b981', fontWeight: 600 }}>
          {fmtYuan(row.total_credit_yuan)}
        </span>
      ),
      width: 120,
    },
    {
      key: 'total_debit_yuan',
      title: '支出',
      render: (_v, row) => (
        <span style={{ color: '#ef4444', fontWeight: 600 }}>
          {fmtYuan(row.total_debit_yuan)}
        </span>
      ),
      width: 120,
    },
    {
      key: 'matched_count',
      title: '已匹配',
      render: (_v, row) => row.matched_count,
      width: 70,
    },
    {
      key: 'unmatched_count',
      title: '未匹配',
      render: (_v, row) => (
        <span style={{ color: row.unmatched_count > 0 ? '#f59e0b' : undefined, fontWeight: 600 }}>
          {row.unmatched_count}
        </span>
      ),
      width: 70,
    },
    {
      key: 'diff_yuan',
      title: '净额',
      render: (_v, row) => (
        <span style={{ fontWeight: 600 }}>{fmtYuan(row.diff_yuan)}</span>
      ),
      width: 100,
    },
    {
      key: 'action',
      title: '操作',
      render: (_v, row) => (
        <ZButton size="sm" variant="ghost" onClick={() => openBatchDetail(row.id)}>
          查看
        </ZButton>
      ),
      width: 70,
    },
  ];

  // ── 渲染 ──────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className={styles.page}>
        <ZSkeleton rows={8} />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>银行流水对账</h1>
          <p className={styles.pageSubtitle}>
            导入银行流水，自动分类与匹配内部单据，掌握真实现金流
          </p>
        </div>
        <div className={styles.headerActions}>
          <ZButton variant="secondary" onClick={() => setShowUpload(true)}>
            导入流水
          </ZButton>
          <ZButton variant="primary" onClick={() => setShowRunModal(true)}>
            执行对账
          </ZButton>
        </div>
      </div>

      {/* 统计卡片 */}
      {stats && (
        <div className={styles.statsRow}>
          <ZCard className={styles.statCard}>
            <div className={styles.statNumGreen}>{fmtYuan(stats.total_credit_yuan)}</div>
            <div className={styles.statLabel}>总收入</div>
          </ZCard>
          <ZCard className={styles.statCard}>
            <div className={styles.statNumRed}>{fmtYuan(stats.total_debit_yuan)}</div>
            <div className={styles.statLabel}>总支出</div>
          </ZCard>
          <ZCard className={styles.statCard}>
            <div className={styles.statNum}>{fmtYuan(stats.balance_yuan)}</div>
            <div className={styles.statLabel}>净余额</div>
          </ZCard>
          <ZCard className={styles.statCard}>
            <div className={stats.unmatched_count > 0 ? styles.statNumWarn : styles.statNumGreen}>
              {stats.unmatched_count}
            </div>
            <div className={styles.statLabel}>未匹配笔数</div>
          </ZCard>
        </div>
      )}

      {/* Tab 栏 */}
      <div className={styles.tabBar}>
        <button
          className={activeTab === 'statements' ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab('statements')}
        >
          流水管理
        </button>
        <button
          className={activeTab === 'reconcile' ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab('reconcile')}
        >
          银行对账
        </button>
        <button
          className={activeTab === 'cashflow' ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab('cashflow')}
        >
          现金流
        </button>
      </div>

      {/* ── Tab 1: 流水管理 ─────────────────────────────────────────────────── */}
      {activeTab === 'statements' && (
        <>
          <div className={styles.toolbar}>
            <select
              value={filterBank}
              onChange={(e) => setFilterBank(e.target.value)}
              style={{ padding: '6px 12px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
            >
              {BANK_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
            <select
              value={filterCategory}
              onChange={(e) => setFilterCategory(e.target.value)}
              style={{ padding: '6px 12px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
            >
              {CATEGORY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
            <select
              value={filterMatched}
              onChange={(e) => setFilterMatched(e.target.value)}
              style={{ padding: '6px 12px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
            >
              <option value="">全部状态</option>
              <option value="true">已匹配</option>
              <option value="false">未匹配</option>
            </select>
            <input
              type="date"
              value={filterStartDate}
              onChange={(e) => setFilterStartDate(e.target.value)}
              style={{ padding: '6px 12px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
            />
            <span style={{ color: '#9ca3af' }}>~</span>
            <input
              type="date"
              value={filterEndDate}
              onChange={(e) => setFilterEndDate(e.target.value)}
              style={{ padding: '6px 12px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
            />
            <div className={styles.toolbarRight}>
              <ZButton size="sm" variant="secondary" onClick={() => { setStmtPage(1); fetchStatements(1); }}>
                查询
              </ZButton>
            </div>
          </div>

          <ZCard className={styles.tableCard}>
            {statements.length === 0 ? (
              <ZEmpty description="暂无流水记录" />
            ) : (
              <ZTable<StatementItem>
                columns={stmtColumns}
                data={statements}
                rowKey="id"
              />
            )}
            {stmtTotal > 20 && (
              <div style={{ textAlign: 'center', padding: '12px 0' }}>
                <ZButton
                  size="sm"
                  variant="secondary"
                  disabled={stmtPage <= 1}
                  onClick={() => { const p = stmtPage - 1; setStmtPage(p); fetchStatements(p); }}
                >
                  上一页
                </ZButton>
                <span style={{ margin: '0 12px', fontSize: 13, color: '#6b7280' }}>
                  第 {stmtPage} 页 / 共 {Math.ceil(stmtTotal / 20)} 页
                </span>
                <ZButton
                  size="sm"
                  variant="secondary"
                  disabled={stmtPage >= Math.ceil(stmtTotal / 20)}
                  onClick={() => { const p = stmtPage + 1; setStmtPage(p); fetchStatements(p); }}
                >
                  下一页
                </ZButton>
              </div>
            )}
          </ZCard>
        </>
      )}

      {/* ── Tab 2: 银行对账 ─────────────────────────────────────────────────── */}
      {activeTab === 'reconcile' && (
        <>
          <ZCard className={styles.tableCard}>
            {batches.length === 0 ? (
              <ZEmpty description="暂无对账记录" />
            ) : (
              <ZTable<BatchItem>
                columns={batchColumns}
                data={batches}
                rowKey="id"
              />
            )}
            {batchTotal > 20 && (
              <div style={{ textAlign: 'center', padding: '12px 0' }}>
                <ZButton
                  size="sm"
                  variant="secondary"
                  disabled={batchPage <= 1}
                  onClick={() => { const p = batchPage - 1; setBatchPage(p); fetchBatches(p); }}
                >
                  上一页
                </ZButton>
                <span style={{ margin: '0 12px', fontSize: 13, color: '#6b7280' }}>
                  第 {batchPage} 页 / 共 {Math.ceil(batchTotal / 20)} 页
                </span>
                <ZButton
                  size="sm"
                  variant="secondary"
                  disabled={batchPage >= Math.ceil(batchTotal / 20)}
                  onClick={() => { const p = batchPage + 1; setBatchPage(p); fetchBatches(p); }}
                >
                  下一页
                </ZButton>
              </div>
            )}
          </ZCard>

          {/* 批次详情 */}
          {detailLoading && <ZSkeleton rows={4} />}
          {selectedBatch && !detailLoading && (
            <ZCard className={styles.detailPanel}>
              <div className={styles.detailHeader}>
                <span className={styles.detailTitle}>
                  对账详情 - {selectedBatch.batch.bank_name} ({fmtDate(selectedBatch.batch.period_start)} ~ {fmtDate(selectedBatch.batch.period_end)})
                </span>
                <ZButton size="sm" variant="secondary" onClick={() => setSelectedBatch(null)}>
                  关闭
                </ZButton>
              </div>
              <div className={styles.detailStats}>
                <div className={styles.detailStat}>
                  <div className={styles.detailStatNum} style={{ color: '#10b981' }}>
                    {fmtYuan(selectedBatch.batch.total_credit_yuan)}
                  </div>
                  <div className={styles.detailStatLabel}>收入合计</div>
                </div>
                <div className={styles.detailStat}>
                  <div className={styles.detailStatNum} style={{ color: '#ef4444' }}>
                    {fmtYuan(selectedBatch.batch.total_debit_yuan)}
                  </div>
                  <div className={styles.detailStatLabel}>支出合计</div>
                </div>
                <div className={styles.detailStat}>
                  <div className={styles.detailStatNum}>{selectedBatch.batch.matched_count}</div>
                  <div className={styles.detailStatLabel}>已匹配</div>
                </div>
                <div className={styles.detailStat}>
                  <div className={styles.detailStatNum} style={{ color: selectedBatch.batch.unmatched_count > 0 ? '#f59e0b' : undefined }}>
                    {selectedBatch.batch.unmatched_count}
                  </div>
                  <div className={styles.detailStatLabel}>未匹配</div>
                </div>
              </div>

              {selectedBatch.statements.length === 0 ? (
                <ZEmpty description="无流水记录" />
              ) : (
                <ZTable<StatementItem>
                  columns={stmtColumns}
                  data={selectedBatch.statements}
                  rowKey="id"
                />
              )}
            </ZCard>
          )}
        </>
      )}

      {/* ── Tab 3: 现金流 ───────────────────────────────────────────────────── */}
      {activeTab === 'cashflow' && stats && (
        <>
          <div className={styles.cashFlowRow}>
            <ZCard className={styles.cashFlowCard}>
              <div className={styles.cashFlowTitle}>总收入</div>
              <div className={styles.cashFlowAmountGreen}>{fmtYuan(stats.total_credit_yuan)}</div>
            </ZCard>
            <ZCard className={styles.cashFlowCard}>
              <div className={styles.cashFlowTitle}>总支出</div>
              <div className={styles.cashFlowAmountRed}>{fmtYuan(stats.total_debit_yuan)}</div>
            </ZCard>
            <ZCard className={styles.cashFlowCard}>
              <div className={styles.cashFlowTitle}>净现金流</div>
              <div className={stats.balance_yuan >= 0 ? styles.cashFlowAmountGreen : styles.cashFlowAmountRed}>
                {fmtYuan(stats.balance_yuan)}
              </div>
            </ZCard>
          </div>

          <ZCard className={styles.tableCard}>
            <div style={{ padding: '16px 20px' }}>
              <h3 style={{ fontSize: 16, fontWeight: 600, margin: '0 0 16px', color: '#111827' }}>
                分类汇总
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
                {Object.entries(CATEGORY_LABEL).map(([key, label]) => (
                  <div key={key} style={{
                    padding: '12px 16px', background: '#f9fafb', borderRadius: 8,
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  }}>
                    <span className={styles.tagCategory}>{label}</span>
                    <ZButton
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setActiveTab('statements');
                        setFilterCategory(key);
                        setStmtPage(1);
                        fetchStatements(1);
                      }}
                    >
                      查看明细
                    </ZButton>
                  </div>
                ))}
              </div>
            </div>
          </ZCard>

          <ZCard className={styles.tableCard}>
            <div style={{ padding: '16px 20px' }}>
              <h3 style={{ fontSize: 16, fontWeight: 600, margin: '0 0 12px', color: '#111827' }}>
                未匹配流水
              </h3>
              <p style={{ fontSize: 14, color: '#6b7280', margin: '0 0 12px' }}>
                共 {stats.unmatched_count} 笔未匹配，金额合计 {fmtYuan(stats.unmatched_amount_yuan)}
              </p>
              <ZButton
                size="sm"
                variant="secondary"
                onClick={() => {
                  setActiveTab('statements');
                  setFilterMatched('false');
                  setStmtPage(1);
                  fetchStatements(1);
                }}
              >
                查看未匹配流水
              </ZButton>
            </div>
          </ZCard>
        </>
      )}

      {/* ── 导入流水模态 ────────────────────────────────────────────────────── */}
      {showUpload && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 1000,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
          onClick={() => setShowUpload(false)}
        >
          <div
            style={{
              background: '#fff', borderRadius: 12, padding: 24, width: 420,
              boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: '0 0 16px', fontSize: 18, fontWeight: 600 }}>导入银行流水</h3>

            <div className={styles.formItem}>
              <label className={styles.formLabel}>银行名称</label>
              <select
                value={uploadBank}
                onChange={(e) => setUploadBank(e.target.value)}
                style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 14 }}
              >
                {BANK_OPTIONS.filter((o) => o.value).map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            <div className={styles.formItem}>
              <label className={styles.formLabel}>流水文件（CSV）</label>
              <input
                type="file"
                accept=".csv,.txt,.xls,.xlsx"
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                style={{ fontSize: 13 }}
              />
              <p className={styles.uploadHint}>
                支持银行导出的CSV格式流水文件（UTF-8或GBK编码）。
                需包含: 交易日期、金额、交易类型等列。
              </p>
            </div>

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 20 }}>
              <ZButton variant="secondary" onClick={() => setShowUpload(false)}>取消</ZButton>
              <ZButton
                onClick={handleUpload}
                disabled={!uploadFile || uploading}
              >
                {uploading ? '导入中...' : '开始导入'}
              </ZButton>
            </div>
          </div>
        </div>
      )}

      {/* ── 执行对账模态 ────────────────────────────────────────────────────── */}
      {showRunModal && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 1000,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
          onClick={() => setShowRunModal(false)}
        >
          <div
            style={{
              background: '#fff', borderRadius: 12, padding: 24, width: 400,
              boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: '0 0 16px', fontSize: 18, fontWeight: 600 }}>执行银行对账</h3>

            <div className={styles.formItem}>
              <label className={styles.formLabel}>银行名称</label>
              <select
                value={runBank}
                onChange={(e) => setRunBank(e.target.value)}
                style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 14 }}
              >
                {BANK_OPTIONS.filter((o) => o.value).map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            <div className={styles.formItem}>
              <label className={styles.formLabel}>开始日期</label>
              <input
                type="date"
                value={runStart}
                onChange={(e) => setRunStart(e.target.value)}
                style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 14 }}
              />
            </div>

            <div className={styles.formItem}>
              <label className={styles.formLabel}>结束日期</label>
              <input
                type="date"
                value={runEnd}
                onChange={(e) => setRunEnd(e.target.value)}
                style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 14 }}
              />
            </div>

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 20 }}>
              <ZButton variant="secondary" onClick={() => setShowRunModal(false)}>取消</ZButton>
              <ZButton
                onClick={handleRun}
                disabled={running}
              >
                {running ? '对账中...' : '开始对账'}
              </ZButton>
            </div>
          </div>
        </div>
      )}

      {/* ── 分类模态 ────────────────────────────────────────────────────────── */}
      {categorizingId && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 1000,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
          onClick={() => setCategorizingId(null)}
        >
          <div
            style={{
              background: '#fff', borderRadius: 12, padding: 24, width: 360,
              boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: '0 0 16px', fontSize: 18, fontWeight: 600 }}>设置分类</h3>

            <div className={styles.formItem}>
              <label className={styles.formLabel}>选择分类</label>
              <select
                value={categorizeValue}
                onChange={(e) => setCategorizeValue(e.target.value)}
                style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 14 }}
              >
                {CATEGORY_OPTIONS.filter((o) => o.value).map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 20 }}>
              <ZButton variant="secondary" onClick={() => setCategorizingId(null)}>取消</ZButton>
              <ZButton onClick={handleCategorize}>确认</ZButton>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default BankReconciliationPage;
