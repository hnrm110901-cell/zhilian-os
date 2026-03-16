/**
 * PaymentReconciliationPage — /platform/payment-reconciliation
 *
 * 支付对账管理：导入渠道账单、执行对账、查看对账批次与差异
 *
 * 后端 API:
 *   POST /api/v1/payment-reconciliation/import    — 导入账单
 *   POST /api/v1/payment-reconciliation/run       — 执行对账
 *   GET  /api/v1/payment-reconciliation/batches   — 批次列表
 *   GET  /api/v1/payment-reconciliation/batches/:id — 批次详情+差异
 *   GET  /api/v1/payment-reconciliation/summary   — 汇总统计
 *   POST /api/v1/payment-reconciliation/diffs/:id/resolve — 标记已处理
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  ZCard, ZBadge, ZButton, ZEmpty, ZSkeleton,
} from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import { apiClient } from '../../services/api';
import styles from './PaymentReconciliationPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface SummaryData {
  period_days: number;
  total_batches: number;
  completed_count: number;
  total_pos_yuan: number;
  total_channel_yuan: number;
  total_diff_yuan: number;
  total_fee_yuan: number;
  total_matched: number;
  avg_match_rate: number;
  unresolved_diffs: number;
}

interface BatchItem {
  id: string;
  brand_id: string;
  channel: string;
  reconcile_date: string;
  pos_total_count: number;
  pos_total_fen: number;
  pos_total_yuan: number;
  channel_total_count: number;
  channel_total_fen: number;
  channel_total_yuan: number;
  channel_fee_yuan: number;
  matched_count: number;
  unmatched_pos_count: number;
  unmatched_channel_count: number;
  diff_fen: number;
  diff_yuan: number;
  match_rate: number | null;
  status: string;
  error_message: string | null;
  created_at: string | null;
}

interface DiffItem {
  id: string;
  diff_type: string;
  trade_no: string | null;
  pos_amount_yuan: number | null;
  channel_amount_yuan: number | null;
  diff_amount_yuan: number | null;
  order_id: string | null;
  description: string | null;
  resolved: boolean;
  resolved_by: string | null;
  resolved_at: string | null;
}

interface BatchDetail {
  batch: BatchItem;
  diffs: DiffItem[];
  diff_count: number;
}

// ── 常量 ─────────────────────────────────────────────────────────────────────

const CHANNEL_OPTIONS = [
  { value: '', label: '全部渠道' },
  { value: 'wechat', label: '微信支付' },
  { value: 'alipay', label: '支付宝' },
  { value: 'meituan', label: '美团' },
  { value: 'eleme', label: '饿了么' },
  { value: 'douyin', label: '抖音' },
  { value: 'cash', label: '现金' },
  { value: 'card', label: '银行卡' },
  { value: 'union_pay', label: '银联' },
];

const CHANNEL_LABEL: Record<string, string> = {
  wechat: '微信支付',
  alipay: '支付宝',
  meituan: '美团',
  eleme: '饿了么',
  douyin: '抖音',
  cash: '现金',
  card: '银行卡',
  union_pay: '银联',
  other: '其他',
};

const STATUS_LABEL: Record<string, string> = {
  pending: '等待中',
  running: '进行中',
  completed: '已完成',
  failed: '失败',
};

const STATUS_TYPE: Record<string, 'success' | 'warning' | 'error' | 'default' | 'info'> = {
  pending: 'default',
  running: 'warning',
  completed: 'success',
  failed: 'error',
};

const DIFF_TYPE_LABEL: Record<string, string> = {
  pos_only: 'POS多出',
  channel_only: '渠道多出',
  amount_mismatch: '金额不符',
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

function fmtTime(iso?: string | null): string {
  if (!iso) return '--';
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function sevenDaysAgo(): string {
  const d = new Date();
  d.setDate(d.getDate() - 7);
  return d.toISOString().slice(0, 10);
}

// ── 匹配率条 ─────────────────────────────────────────────────────────────────

function MatchRateBar({ rate }: { rate: number | null }) {
  if (rate == null) return <span>--</span>;
  const pct = Math.round(rate * 100);
  let fillClass = styles.rateFillGood;
  if (pct < 80) fillClass = styles.rateFillBad;
  else if (pct < 95) fillClass = styles.rateFillWarn;

  return (
    <div className={styles.rateBar}>
      <div className={styles.rateTrack}>
        <div className={fillClass} style={{ width: `${pct}%` }} />
      </div>
      <span className={styles.rateText}>{pct}%</span>
    </div>
  );
}

// ── 主组件 ───────────────────────────────────────────────────────────────────

const PaymentReconciliationPage: React.FC = () => {
  // 状态
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [batches, setBatches] = useState<BatchItem[]>([]);
  const [batchTotal, setBatchTotal] = useState(0);
  const [batchPage, setBatchPage] = useState(1);

  // 筛选
  const [filterChannel, setFilterChannel] = useState('');
  const [filterStartDate, setFilterStartDate] = useState(sevenDaysAgo());
  const [filterEndDate, setFilterEndDate] = useState(today());

  // 详情
  const [selectedBatch, setSelectedBatch] = useState<BatchDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // 上传模态
  const [showUpload, setShowUpload] = useState(false);
  const [uploadChannel, setUploadChannel] = useState('wechat');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

  // 执行对账模态
  const [showRunModal, setShowRunModal] = useState(false);
  const [runChannel, setRunChannel] = useState('wechat');
  const [runDate, setRunDate] = useState(today());
  const [running, setRunning] = useState(false);

  // ── 加载数据 ────────────────────────────────────────────────────────────

  const fetchSummary = useCallback(async () => {
    try {
      const resp = await apiClient.get<{ success: boolean; data: SummaryData }>(
        '/api/v1/payment-reconciliation/summary?days=30'
      );
      if (resp.success) setSummary(resp.data);
    } catch (err) {
      console.error('获取对账汇总失败', err);
    }
  }, []);

  const fetchBatches = useCallback(async (page = 1) => {
    try {
      const params = new URLSearchParams();
      if (filterChannel) params.set('channel', filterChannel);
      if (filterStartDate) params.set('start_date', filterStartDate);
      if (filterEndDate) params.set('end_date', filterEndDate);
      params.set('page', String(page));
      params.set('page_size', '20');

      const resp = await apiClient.get<{ success: boolean; data: { batches: BatchItem[]; total: number } }>(
        `/api/v1/payment-reconciliation/batches?${params}`
      );
      if (resp.success) {
        setBatches(resp.data.batches);
        setBatchTotal(resp.data.total);
      }
    } catch (err) {
      console.error('获取对账批次失败', err);
    }
  }, [filterChannel, filterStartDate, filterEndDate]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([fetchSummary(), fetchBatches(1)]);
    setBatchPage(1);
    setLoading(false);
  }, [fetchSummary, fetchBatches]);

  useEffect(() => { loadAll(); }, [loadAll]);

  // ── 查看批次详情 ────────────────────────────────────────────────────────

  const openBatchDetail = useCallback(async (batchId: string) => {
    setDetailLoading(true);
    try {
      const resp = await apiClient.get<{ success: boolean; data: BatchDetail }>(
        `/api/v1/payment-reconciliation/batches/${batchId}`
      );
      if (resp.success) setSelectedBatch(resp.data);
    } catch (err) {
      console.error('获取批次详情失败', err);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  // ── 导入账单 ────────────────────────────────────────────────────────────

  const handleUpload = useCallback(async () => {
    if (!uploadFile) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      formData.append('channel', uploadChannel);

      const resp = await apiClient.post<{ success: boolean; data: { imported: number; errors: string[] }; message: string }>(
        '/api/v1/payment-reconciliation/import',
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );

      if (resp.success) {
        alert(`${resp.message}\n${resp.data.errors.length > 0 ? '部分行解析失败: ' + resp.data.errors.slice(0, 3).join('; ') : ''}`);
        setShowUpload(false);
        setUploadFile(null);
        loadAll();
      }
    } catch (err: any) {
      alert('导入失败: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setUploading(false);
    }
  }, [uploadFile, uploadChannel, loadAll]);

  // ── 执行对账 ────────────────────────────────────────────────────────────

  const handleRun = useCallback(async () => {
    setRunning(true);
    try {
      const resp = await apiClient.post<{ success: boolean; message: string; data: any }>(
        '/api/v1/payment-reconciliation/run',
        { channel: runChannel, reconcile_date: runDate }
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
  }, [runChannel, runDate, loadAll]);

  // ── 标记差异已处理 ──────────────────────────────────────────────────────

  const handleResolveDiff = useCallback(async (diffId: string) => {
    try {
      const resp = await apiClient.post<{ success: boolean }>(
        `/api/v1/payment-reconciliation/diffs/${diffId}/resolve`
      );
      if (resp.success && selectedBatch) {
        // 刷新详情
        openBatchDetail(selectedBatch.batch.id);
        fetchSummary();
      }
    } catch (err) {
      console.error('标记处理失败', err);
    }
  }, [selectedBatch, openBatchDetail, fetchSummary]);

  // ── 批次表格列 ─────────────────────────────────────────────────────────

  const batchColumns: ZTableColumn<BatchItem>[] = [
    {
      key: 'reconcile_date',
      title: '日期',
      render: (_v, row) => fmtDate(row.reconcile_date),
      width: 110,
    },
    {
      key: 'channel',
      title: '渠道',
      render: (_v, row) => CHANNEL_LABEL[row.channel] || row.channel,
      width: 90,
    },
    {
      key: 'pos_total_yuan',
      title: 'POS金额',
      render: (_v, row) => fmtYuan(row.pos_total_yuan),
      width: 120,
    },
    {
      key: 'channel_total_yuan',
      title: '渠道金额',
      render: (_v, row) => fmtYuan(row.channel_total_yuan),
      width: 120,
    },
    {
      key: 'diff_yuan',
      title: '差异',
      render: (_v, row) => (
        <span style={{ color: row.diff_yuan > 0 ? '#ef4444' : undefined, fontWeight: 600 }}>
          {fmtYuan(row.diff_yuan)}
        </span>
      ),
      width: 100,
    },
    {
      key: 'match_rate',
      title: '匹配率',
      render: (_v, row) => <MatchRateBar rate={row.match_rate} />,
      width: 140,
    },
    {
      key: 'status',
      title: '状态',
      render: (_v, row) => (
        <ZBadge type={STATUS_TYPE[row.status] || 'default'} text={STATUS_LABEL[row.status] || row.status} />
      ),
      width: 80,
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

  // ── 差异表格列 ─────────────────────────────────────────────────────────

  const diffColumns: ZTableColumn<DiffItem>[] = [
    {
      key: 'diff_type',
      title: '类型',
      render: (_v, row) => {
        const cls = row.diff_type === 'pos_only'
          ? styles.diffTypePosOnly
          : row.diff_type === 'channel_only'
            ? styles.diffTypeChannelOnly
            : styles.diffTypeAmountMismatch;
        return <span className={cls}>{DIFF_TYPE_LABEL[row.diff_type] || row.diff_type}</span>;
      },
      width: 100,
    },
    {
      key: 'trade_no',
      title: '交易号',
      render: (_v, row) => row.trade_no || '--',
      width: 180,
    },
    {
      key: 'pos_amount_yuan',
      title: 'POS金额',
      render: (_v, row) => fmtYuan(row.pos_amount_yuan),
      width: 100,
    },
    {
      key: 'channel_amount_yuan',
      title: '渠道金额',
      render: (_v, row) => fmtYuan(row.channel_amount_yuan),
      width: 100,
    },
    {
      key: 'diff_amount_yuan',
      title: '差异金额',
      render: (_v, row) => (
        <span style={{ color: '#ef4444', fontWeight: 600 }}>
          {fmtYuan(row.diff_amount_yuan)}
        </span>
      ),
      width: 100,
    },
    {
      key: 'description',
      title: '说明',
      render: (_v, row) => row.description || '--',
    },
    {
      key: 'action',
      title: '操作',
      render: (_v, row) => {
        if (row.resolved) {
          return (
            <ZBadge type="success" text={`已处理${row.resolved_by ? ` (${row.resolved_by})` : ''}`} />
          );
        }
        return (
          <ZButton size="sm" onClick={() => handleResolveDiff(row.id)}>
            标记已处理
          </ZButton>
        );
      },
      width: 130,
    },
  ];

  // ── 渲染 ───────────────────────────────────────────────────────────────

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
          <h1 className={styles.pageTitle}>支付对账</h1>
          <p className={styles.pageSubtitle}>
            导入渠道账单，自动匹配POS订单，发现差异并跟踪处理
          </p>
        </div>
        <div className={styles.headerActions}>
          <ZButton variant="secondary" onClick={() => setShowUpload(true)}>
            导入账单
          </ZButton>
          <ZButton variant="primary" onClick={() => setShowRunModal(true)}>
            执行对账
          </ZButton>
        </div>
      </div>

      {/* 统计卡片 */}
      {summary && (
        <div className={styles.statsRow}>
          <ZCard className={styles.statCard}>
            <div className={styles.statNum}>{fmtYuan(summary.total_channel_yuan)}</div>
            <div className={styles.statLabel}>总交易额（近30天）</div>
          </ZCard>
          <ZCard className={styles.statCard}>
            <div className={styles.statNumGreen}>{summary.completed_count}</div>
            <div className={styles.statLabel}>已对账批次</div>
          </ZCard>
          <ZCard className={styles.statCard}>
            <div className={styles.statNumWarn}>{fmtYuan(summary.total_diff_yuan)}</div>
            <div className={styles.statLabel}>差异金额</div>
          </ZCard>
          <ZCard className={styles.statCard}>
            <div className={summary.avg_match_rate >= 0.95 ? styles.statNumGreen : styles.statNumWarn}>
              {(summary.avg_match_rate * 100).toFixed(1)}%
            </div>
            <div className={styles.statLabel}>平均匹配率</div>
          </ZCard>
        </div>
      )}

      {/* 工具栏 */}
      <div className={styles.toolbar}>
        <select
          value={filterChannel}
          onChange={(e) => setFilterChannel(e.target.value)}
          style={{ padding: '6px 12px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
        >
          {CHANNEL_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
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
          <ZButton size="sm" variant="secondary" onClick={() => { loadAll(); }}>
            查询
          </ZButton>
        </div>
      </div>

      {/* 批次表格 */}
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

      {/* 批次详情 + 差异列表 */}
      {detailLoading && <ZSkeleton rows={4} />}
      {selectedBatch && !detailLoading && (
        <ZCard className={styles.detailPanel}>
          <div className={styles.detailHeader}>
            <span className={styles.detailTitle}>
              对账详情 - {fmtDate(selectedBatch.batch.reconcile_date)} {CHANNEL_LABEL[selectedBatch.batch.channel] || selectedBatch.batch.channel}
            </span>
            <ZButton size="sm" variant="secondary" onClick={() => setSelectedBatch(null)}>
              关闭
            </ZButton>
          </div>

          <div className={styles.detailStats}>
            <div className={styles.detailStat}>
              <div className={styles.detailStatNum}>{selectedBatch.batch.matched_count}</div>
              <div className={styles.detailStatLabel}>已匹配</div>
            </div>
            <div className={styles.detailStat}>
              <div className={styles.detailStatNum}>{selectedBatch.batch.unmatched_pos_count}</div>
              <div className={styles.detailStatLabel}>POS多出</div>
            </div>
            <div className={styles.detailStat}>
              <div className={styles.detailStatNum}>{selectedBatch.batch.unmatched_channel_count}</div>
              <div className={styles.detailStatLabel}>渠道多出</div>
            </div>
          </div>

          {selectedBatch.diffs.length === 0 ? (
            <ZEmpty description="无差异记录" />
          ) : (
            <ZTable<DiffItem>
              columns={diffColumns}
              data={selectedBatch.diffs}
              rowKey="id"
            />
          )}
        </ZCard>
      )}

      {/* 导入账单模态 */}
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
            <h3 style={{ margin: '0 0 16px', fontSize: 18, fontWeight: 600 }}>导入渠道账单</h3>

            <div className={styles.formItem}>
              <label className={styles.formLabel}>支付渠道</label>
              <select
                value={uploadChannel}
                onChange={(e) => setUploadChannel(e.target.value)}
                style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 14 }}
              >
                {CHANNEL_OPTIONS.filter((o) => o.value).map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            <div className={styles.formItem}>
              <label className={styles.formLabel}>账单文件（CSV）</label>
              <input
                type="file"
                accept=".csv,.txt"
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                style={{ fontSize: 13 }}
              />
              <p className={styles.uploadHint}>
                支持微信支付、支付宝标准账单CSV格式。文件大小限制10MB。
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

      {/* 执行对账模态 */}
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
            <h3 style={{ margin: '0 0 16px', fontSize: 18, fontWeight: 600 }}>执行对账</h3>

            <div className={styles.formItem}>
              <label className={styles.formLabel}>支付渠道</label>
              <select
                value={runChannel}
                onChange={(e) => setRunChannel(e.target.value)}
                style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 14 }}
              >
                {CHANNEL_OPTIONS.filter((o) => o.value).map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            <div className={styles.formItem}>
              <label className={styles.formLabel}>对账日期</label>
              <input
                type="date"
                value={runDate}
                onChange={(e) => setRunDate(e.target.value)}
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
    </div>
  );
};

export default PaymentReconciliationPage;
