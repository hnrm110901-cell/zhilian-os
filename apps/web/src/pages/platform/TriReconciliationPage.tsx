/**
 * TriReconciliationPage — /platform/tri-reconciliation
 *
 * 三角对账引擎：Order ↔ Payment ↔ Bank Statement ↔ Invoice 四方自动匹配
 *
 * 后端 API:
 *   POST /api/v1/tri-recon/run                        — 执行对账
 *   GET  /api/v1/tri-recon/records                    — 记录列表
 *   GET  /api/v1/tri-recon/records/:id                — 记录详情
 *   POST /api/v1/tri-recon/records/:id/manual-match   — 手动匹配
 *   POST /api/v1/tri-recon/records/:id/resolve        — 解决争议
 *   GET  /api/v1/tri-recon/summary                    — 汇总统计
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  ZCard, ZBadge, ZButton, ZEmpty, ZSkeleton,
} from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import { apiClient } from '../../services/api';
import styles from './TriReconciliationPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface SummaryData {
  total: number;
  full_match: number;
  triple_match: number;
  double_match: number;
  single: number;
  full_match_rate: number;
  triple_match_rate: number;
  double_match_rate: number;
  single_rate: number;
  total_discrepancy_yuan: number;
  trend: TrendItem[];
  top_unmatched: RecordItem[];
}

interface TrendItem {
  date: string;
  total: number;
  full_match: number;
  match_rate: number;
}

interface RecordItem {
  id: string;
  brand_id: string;
  store_id: string | null;
  match_date: string;
  order_id: string | null;
  order_amount_yuan: number | null;
  payment_id: string | null;
  payment_amount_yuan: number | null;
  bank_statement_id: string | null;
  bank_amount_yuan: number | null;
  invoice_id: string | null;
  invoice_amount_yuan: number | null;
  match_level: string;
  discrepancy_yuan: number;
  status: string;
  notes: string | null;
  matched_at: string | null;
}

interface RecordDetail extends RecordItem {
  order_detail?: {
    id: string;
    status: string;
    total_amount_yuan: number;
    order_time: string | null;
    channel: string | null;
  };
  payment_detail?: {
    id: string;
    channel: string;
    trade_no: string;
    amount_yuan: number;
    fee_yuan: number;
    trade_time: string | null;
  };
  bank_detail?: {
    id: string;
    bank_name: string;
    reference_number: string | null;
    amount_yuan: number;
    counterparty: string | null;
    transaction_date: string | null;
  };
  invoice_detail?: {
    id: string;
    invoice_number: string | null;
    buyer_name: string;
    amount_yuan: number;
    status: string;
    issued_at: string | null;
  };
}

interface RecordsResponse {
  total: number;
  page: number;
  page_size: number;
  items: RecordItem[];
}

// ── 常量 ─────────────────────────────────────────────────────────────────────

const MATCH_LEVEL_MAP: Record<string, { label: string; className: string }> = {
  full_match: { label: '完全匹配', className: styles.levelFull },
  triple_match: { label: '三方匹配', className: styles.levelTriple },
  double_match: { label: '双方匹配', className: styles.levelDouble },
  single: { label: '未匹配', className: styles.levelSingle },
};

const STATUS_MAP: Record<string, { label: string; className: string }> = {
  auto_matched: { label: '自动匹配', className: styles.statusAuto },
  manual_matched: { label: '手动匹配', className: styles.statusManual },
  disputed: { label: '有争议', className: styles.statusDisputed },
  resolved: { label: '已解决', className: styles.statusResolved },
};

// ── 辅助函数 ─────────────────────────────────────────────────────────────────

function formatYuan(val: number | null): string {
  if (val === null || val === undefined) return '-';
  return `¥${val.toFixed(2)}`;
}

function getToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function getLast7Days(): { start: string; end: string } {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 6);
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}

// ── 匹配流程可视化组件 ─────────────────────────────────────────────────────

function MatchFlowInline({ record }: { record: RecordItem }) {
  const nodes = [
    { label: '订单', amount: record.order_amount_yuan, has: !!record.order_id },
    { label: '支付', amount: record.payment_amount_yuan, has: !!record.payment_id },
    { label: '银行', amount: record.bank_amount_yuan, has: !!record.bank_statement_id },
    { label: '发票', amount: record.invoice_amount_yuan, has: !!record.invoice_id },
  ];

  const arrowClass =
    record.match_level === 'full_match' ? styles.arrowGreen :
    record.match_level === 'triple_match' ? styles.arrowGreen :
    record.match_level === 'double_match' ? styles.arrowYellow :
    styles.arrowGray;

  return (
    <div className={styles.matchFlow}>
      {nodes.map((node, i) => (
        <React.Fragment key={node.label}>
          <span className={node.has ? styles.matchNodeActive : styles.matchNodeEmpty}>
            {node.label}
            {node.has && node.amount !== null ? ` ${formatYuan(node.amount)}` : ''}
          </span>
          {i < nodes.length - 1 && (
            <span className={`${styles.matchArrow} ${node.has && nodes[i + 1].has ? arrowClass : styles.arrowGray}`} />
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

// ── 详情流程可视化组件 ─────────────────────────────────────────────────────

function DetailFlowViz({ record }: { record: RecordItem }) {
  const nodes = [
    { label: '订单', amount: record.order_amount_yuan, has: !!record.order_id },
    { label: '支付', amount: record.payment_amount_yuan, has: !!record.payment_id },
    { label: '银行', amount: record.bank_amount_yuan, has: !!record.bank_statement_id },
    { label: '发票', amount: record.invoice_amount_yuan, has: !!record.invoice_id },
  ];

  return (
    <div className={styles.detailFlow}>
      {nodes.map((node, i) => (
        <React.Fragment key={node.label}>
          <div className={node.has ? styles.detailNodeActive : styles.detailNodeEmpty}>
            <span className={styles.detailNodeLabel}>{node.label}</span>
            {node.has && node.amount !== null ? (
              <span className={styles.detailNodeAmount}>{formatYuan(node.amount)}</span>
            ) : (
              <span className={styles.detailNodeAmountEmpty}>--</span>
            )}
          </div>
          {i < nodes.length - 1 && (
            <span className={`${styles.detailArrow} ${node.has && nodes[i + 1].has ? styles.detailArrowMatch : ''}`} />
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

// ── 主组件 ──────────────────────────────────────────────────────────────────

function TriReconciliationPage() {
  // 状态
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [records, setRecords] = useState<RecordItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 20;

  // 筛选
  const [filterDate, setFilterDate] = useState(getToday());
  const [filterLevel, setFilterLevel] = useState('');
  const [filterStatus, setFilterStatus] = useState('');

  // 对账执行日期
  const [runDate, setRunDate] = useState(getToday());

  // 详情抽屉
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [detail, setDetail] = useState<RecordDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // 手动匹配
  const [manualOrderId, setManualOrderId] = useState('');
  const [manualPaymentId, setManualPaymentId] = useState('');
  const [manualBankId, setManualBankId] = useState('');
  const [manualInvoiceId, setManualInvoiceId] = useState('');

  // 争议解决
  const [resolveNotes, setResolveNotes] = useState('');

  // ── 数据加载 ───────────────────────────────────────────────────────────

  const fetchSummary = useCallback(async () => {
    try {
      const range = getLast7Days();
      const resp = await apiClient.get<{ success: boolean; data: SummaryData }>(
        `/api/v1/tri-recon/summary?brand_id=default&start_date=${range.start}&end_date=${range.end}`
      );
      setSummary(resp.data);
    } catch {
      setSummary(null);
    }
  }, []);

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        brand_id: 'default',
        page: String(page),
        page_size: String(pageSize),
      });
      if (filterDate) params.set('target_date', filterDate);
      if (filterLevel) params.set('match_level', filterLevel);
      if (filterStatus) params.set('status', filterStatus);

      const resp = await apiClient.get<{ success: boolean; data: RecordsResponse }>(
        `/api/v1/tri-recon/records?${params.toString()}`
      );
      setRecords(resp.data.items);
      setTotal(resp.data.total);
    } catch {
      setRecords([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [page, filterDate, filterLevel, filterStatus]);

  useEffect(() => { fetchSummary(); }, [fetchSummary]);
  useEffect(() => { fetchRecords(); }, [fetchRecords]);

  // ── 执行对账 ───────────────────────────────────────────────────────────

  const handleRun = async () => {
    if (!runDate) return;
    setRunning(true);
    try {
      await apiClient.post('/api/v1/tri-recon/run', {
        brand_id: 'default',
        target_date: runDate,
      });
      await Promise.all([fetchSummary(), fetchRecords()]);
    } catch {
      // 静默处理
    } finally {
      setRunning(false);
    }
  };

  // ── 查看详情 ───────────────────────────────────────────────────────────

  const openDetail = async (recordId: string) => {
    setDrawerOpen(true);
    setDetailLoading(true);
    setManualOrderId('');
    setManualPaymentId('');
    setManualBankId('');
    setManualInvoiceId('');
    setResolveNotes('');
    try {
      const resp = await apiClient.get<{ success: boolean; data: RecordDetail }>(
        `/api/v1/tri-recon/records/${recordId}`
      );
      setDetail(resp.data);
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  // ── 手动匹配 ───────────────────────────────────────────────────────────

  const handleManualMatch = async () => {
    if (!detail) return;
    const body: Record<string, string> = {};
    if (manualOrderId) body.order_id = manualOrderId;
    if (manualPaymentId) body.payment_id = manualPaymentId;
    if (manualBankId) body.bank_id = manualBankId;
    if (manualInvoiceId) body.invoice_id = manualInvoiceId;
    if (Object.keys(body).length === 0) return;

    try {
      await apiClient.post(`/api/v1/tri-recon/records/${detail.id}/manual-match`, body);
      await openDetail(detail.id);
      await fetchRecords();
    } catch {
      // 静默处理
    }
  };

  // ── 解决争议 ───────────────────────────────────────────────────────────

  const handleResolve = async () => {
    if (!detail || !resolveNotes.trim()) return;
    try {
      await apiClient.post(`/api/v1/tri-recon/records/${detail.id}/resolve`, {
        notes: resolveNotes,
      });
      await openDetail(detail.id);
      await fetchRecords();
    } catch {
      // 静默处理
    }
  };

  // ── 表格列定义 ─────────────────────────────────────────────────────────

  const columns: ZTableColumn<RecordItem>[] = [
    {
      title: '日期',
      dataIndex: 'match_date',
      key: 'match_date',
      width: 100,
    },
    {
      title: '匹配流程',
      dataIndex: 'id',
      key: 'flow',
      width: 340,
      render: (_: string, record: RecordItem) => <MatchFlowInline record={record} />,
    },
    {
      title: '匹配级别',
      dataIndex: 'match_level',
      key: 'match_level',
      width: 100,
      render: (val: string) => {
        const cfg = MATCH_LEVEL_MAP[val] || { label: val, className: styles.levelSingle };
        return <span className={cfg.className}>{cfg.label}</span>;
      },
    },
    {
      title: '差异',
      dataIndex: 'discrepancy_yuan',
      key: 'discrepancy_yuan',
      width: 100,
      render: (val: number) => (
        <span style={{ color: val > 0 ? '#ef4444' : '#10b981', fontWeight: 600 }}>
          {formatYuan(val)}
        </span>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (val: string) => {
        const cfg = STATUS_MAP[val] || { label: val, className: styles.statusAuto };
        return <span className={cfg.className}>{cfg.label}</span>;
      },
    },
    {
      title: '操作',
      dataIndex: 'id',
      key: 'actions',
      width: 80,
      render: (id: string) => (
        <ZButton size="sm" variant="ghost" onClick={() => openDetail(id)}>
          详情
        </ZButton>
      ),
    },
  ];

  // ── 渲染 ───────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>三角对账引擎</h1>
          <p className={styles.pageSubtitle}>
            Order / Payment / Bank Statement / Invoice 四方自动匹配与差异追踪
          </p>
        </div>
        <div className={styles.headerActions}>
          <input
            type="date"
            value={runDate}
            onChange={(e) => setRunDate(e.target.value)}
            style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
          />
          <ZButton variant="primary" onClick={handleRun} disabled={running}>
            {running ? '对账中...' : '执行对账'}
          </ZButton>
        </div>
      </div>

      {/* 统计行 */}
      <div className={styles.statsRow}>
        <ZCard className={styles.statCard}>
          <div className={styles.statNumGreen}>
            {summary ? `${summary.full_match_rate}%` : '-'}
          </div>
          <div className={styles.statLabel}>完全匹配率</div>
        </ZCard>
        <ZCard className={styles.statCard}>
          <div className={styles.statNum}>
            {summary ? summary.total : '-'}
          </div>
          <div className={styles.statLabel}>总记录数</div>
        </ZCard>
        <ZCard className={styles.statCard}>
          <div className={styles.statNumWarn}>
            {summary ? formatYuan(summary.total_discrepancy_yuan) : '-'}
          </div>
          <div className={styles.statLabel}>差异总额</div>
        </ZCard>
        <ZCard className={styles.statCard}>
          <div className={styles.statNumRed}>
            {summary ? summary.single : '-'}
          </div>
          <div className={styles.statLabel}>未匹配数</div>
        </ZCard>
      </div>

      {/* 汇总趋势 */}
      {summary && summary.trend.length > 0 && (
        <div className={styles.summaryRow}>
          <ZCard className={styles.summaryCard}>
            <div className={styles.summaryTitle}>三方匹配</div>
            <div className={styles.summaryValue}>{summary.triple_match}</div>
          </ZCard>
          <ZCard className={styles.summaryCard}>
            <div className={styles.summaryTitle}>双方匹配</div>
            <div className={styles.summaryValue}>{summary.double_match}</div>
          </ZCard>
          <ZCard className={styles.summaryCard}>
            <div className={styles.summaryTitle}>匹配趋势（近7日）</div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', height: 40, marginTop: 8 }}>
              {summary.trend.map((t) => (
                <div
                  key={t.date}
                  style={{
                    flex: 1,
                    background: t.match_rate >= 80 ? '#10b981' : t.match_rate >= 50 ? '#f59e0b' : '#ef4444',
                    borderRadius: 3,
                    height: `${Math.max(4, t.match_rate * 0.4)}px`,
                  }}
                  title={`${t.date}: ${t.match_rate}%`}
                />
              ))}
            </div>
          </ZCard>
        </div>
      )}

      {/* 筛选工具栏 */}
      <div className={styles.toolbar}>
        <input
          type="date"
          value={filterDate}
          onChange={(e) => { setFilterDate(e.target.value); setPage(1); }}
          style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
        />
        <select
          value={filterLevel}
          onChange={(e) => { setFilterLevel(e.target.value); setPage(1); }}
          style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
        >
          <option value="">全部级别</option>
          <option value="full_match">完全匹配</option>
          <option value="triple_match">三方匹配</option>
          <option value="double_match">双方匹配</option>
          <option value="single">未匹配</option>
        </select>
        <select
          value={filterStatus}
          onChange={(e) => { setFilterStatus(e.target.value); setPage(1); }}
          style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
        >
          <option value="">全部状态</option>
          <option value="auto_matched">自动匹配</option>
          <option value="manual_matched">手动匹配</option>
          <option value="disputed">有争议</option>
          <option value="resolved">已解决</option>
        </select>
        <div className={styles.toolbarRight}>
          <ZButton size="sm" variant="ghost" onClick={() => { setFilterDate(getToday()); setFilterLevel(''); setFilterStatus(''); setPage(1); }}>
            重置
          </ZButton>
        </div>
      </div>

      {/* 记录表格 */}
      <ZCard className={styles.tableCard}>
        {loading ? (
          <ZSkeleton lines={8} />
        ) : records.length === 0 ? (
          <ZEmpty description="暂无对账记录，请先执行对账" />
        ) : (
          <>
            <ZTable<RecordItem>
              columns={columns}
              dataSource={records}
              rowKey="id"
            />
            {/* 分页 */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 0' }}>
              <span style={{ fontSize: 13, color: '#9ca3af' }}>
                共 {total} 条，第 {page}/{Math.ceil(total / pageSize) || 1} 页
              </span>
              <div style={{ display: 'flex', gap: 8 }}>
                <ZButton size="sm" variant="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                  上一页
                </ZButton>
                <ZButton size="sm" variant="ghost" disabled={page * pageSize >= total} onClick={() => setPage(page + 1)}>
                  下一页
                </ZButton>
              </div>
            </div>
          </>
        )}
      </ZCard>

      {/* 详情抽屉 */}
      {drawerOpen && (
        <div
          style={{
            position: 'fixed', top: 0, right: 0, bottom: 0,
            width: 520, background: '#fff', boxShadow: '-4px 0 24px rgba(0,0,0,0.12)',
            zIndex: 1000, overflowY: 'auto', padding: 24,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>对账记录详情</h3>
            <ZButton size="sm" variant="ghost" onClick={() => setDrawerOpen(false)}>关闭</ZButton>
          </div>

          {detailLoading ? (
            <ZSkeleton lines={10} />
          ) : detail ? (
            <>
              {/* 匹配流程可视化 */}
              <div className={styles.drawerSection}>
                <div className={styles.drawerSectionTitle}>匹配流程</div>
                <DetailFlowViz record={detail} />
                <div style={{ textAlign: 'center', marginTop: 8 }}>
                  <span className={MATCH_LEVEL_MAP[detail.match_level]?.className || styles.levelSingle}>
                    {MATCH_LEVEL_MAP[detail.match_level]?.label || detail.match_level}
                  </span>
                  {detail.discrepancy_yuan > 0 && (
                    <span style={{ marginLeft: 12, color: '#ef4444', fontWeight: 600, fontSize: 14 }}>
                      差异 {formatYuan(detail.discrepancy_yuan)}
                    </span>
                  )}
                </div>
              </div>

              {/* 订单详情 */}
              {detail.order_detail && (
                <div className={styles.drawerSection}>
                  <div className={styles.drawerSectionTitle}>订单信息</div>
                  <div className={styles.detailInfoGrid}>
                    <div className={styles.detailInfoItem}>
                      <span className={styles.detailInfoLabel}>订单ID</span>
                      <span className={styles.detailInfoValue}>{detail.order_id}</span>
                    </div>
                    <div className={styles.detailInfoItem}>
                      <span className={styles.detailInfoLabel}>金额</span>
                      <span className={styles.detailInfoValue}>{formatYuan(detail.order_detail.total_amount_yuan)}</span>
                    </div>
                    <div className={styles.detailInfoItem}>
                      <span className={styles.detailInfoLabel}>状态</span>
                      <span className={styles.detailInfoValue}>{detail.order_detail.status}</span>
                    </div>
                    <div className={styles.detailInfoItem}>
                      <span className={styles.detailInfoLabel}>渠道</span>
                      <span className={styles.detailInfoValue}>{detail.order_detail.channel || '-'}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* 支付详情 */}
              {detail.payment_detail && (
                <div className={styles.drawerSection}>
                  <div className={styles.drawerSectionTitle}>支付信息</div>
                  <div className={styles.detailInfoGrid}>
                    <div className={styles.detailInfoItem}>
                      <span className={styles.detailInfoLabel}>交易号</span>
                      <span className={styles.detailInfoValue}>{detail.payment_detail.trade_no}</span>
                    </div>
                    <div className={styles.detailInfoItem}>
                      <span className={styles.detailInfoLabel}>金额</span>
                      <span className={styles.detailInfoValue}>{formatYuan(detail.payment_detail.amount_yuan)}</span>
                    </div>
                    <div className={styles.detailInfoItem}>
                      <span className={styles.detailInfoLabel}>渠道</span>
                      <span className={styles.detailInfoValue}>{detail.payment_detail.channel}</span>
                    </div>
                    <div className={styles.detailInfoItem}>
                      <span className={styles.detailInfoLabel}>手续费</span>
                      <span className={styles.detailInfoValue}>{formatYuan(detail.payment_detail.fee_yuan)}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* 银行流水详情 */}
              {detail.bank_detail && (
                <div className={styles.drawerSection}>
                  <div className={styles.drawerSectionTitle}>银行流水</div>
                  <div className={styles.detailInfoGrid}>
                    <div className={styles.detailInfoItem}>
                      <span className={styles.detailInfoLabel}>银行</span>
                      <span className={styles.detailInfoValue}>{detail.bank_detail.bank_name}</span>
                    </div>
                    <div className={styles.detailInfoItem}>
                      <span className={styles.detailInfoLabel}>金额</span>
                      <span className={styles.detailInfoValue}>{formatYuan(detail.bank_detail.amount_yuan)}</span>
                    </div>
                    <div className={styles.detailInfoItem}>
                      <span className={styles.detailInfoLabel}>流水号</span>
                      <span className={styles.detailInfoValue}>{detail.bank_detail.reference_number || '-'}</span>
                    </div>
                    <div className={styles.detailInfoItem}>
                      <span className={styles.detailInfoLabel}>对方户名</span>
                      <span className={styles.detailInfoValue}>{detail.bank_detail.counterparty || '-'}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* 发票详情 */}
              {detail.invoice_detail && (
                <div className={styles.drawerSection}>
                  <div className={styles.drawerSectionTitle}>发票信息</div>
                  <div className={styles.detailInfoGrid}>
                    <div className={styles.detailInfoItem}>
                      <span className={styles.detailInfoLabel}>发票号</span>
                      <span className={styles.detailInfoValue}>{detail.invoice_detail.invoice_number || '-'}</span>
                    </div>
                    <div className={styles.detailInfoItem}>
                      <span className={styles.detailInfoLabel}>金额</span>
                      <span className={styles.detailInfoValue}>{formatYuan(detail.invoice_detail.amount_yuan)}</span>
                    </div>
                    <div className={styles.detailInfoItem}>
                      <span className={styles.detailInfoLabel}>购方</span>
                      <span className={styles.detailInfoValue}>{detail.invoice_detail.buyer_name}</span>
                    </div>
                    <div className={styles.detailInfoItem}>
                      <span className={styles.detailInfoLabel}>状态</span>
                      <span className={styles.detailInfoValue}>{detail.invoice_detail.status}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* 手动匹配表单 */}
              {(detail.match_level === 'single' || detail.match_level === 'double_match') && (
                <div className={styles.drawerSection}>
                  <div className={styles.drawerSectionTitle}>手动匹配</div>
                  <div className={styles.manualMatchForm}>
                    {!detail.order_id && (
                      <div className={styles.formItem}>
                        <label className={styles.formLabel}>订单ID</label>
                        <input
                          type="text"
                          value={manualOrderId}
                          onChange={(e) => setManualOrderId(e.target.value)}
                          placeholder="输入订单ID"
                          style={{ width: '100%', padding: '6px 10px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
                        />
                      </div>
                    )}
                    {!detail.payment_id && (
                      <div className={styles.formItem}>
                        <label className={styles.formLabel}>支付ID</label>
                        <input
                          type="text"
                          value={manualPaymentId}
                          onChange={(e) => setManualPaymentId(e.target.value)}
                          placeholder="输入支付记录ID"
                          style={{ width: '100%', padding: '6px 10px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
                        />
                      </div>
                    )}
                    {!detail.bank_statement_id && (
                      <div className={styles.formItem}>
                        <label className={styles.formLabel}>银行流水ID</label>
                        <input
                          type="text"
                          value={manualBankId}
                          onChange={(e) => setManualBankId(e.target.value)}
                          placeholder="输入银行流水ID"
                          style={{ width: '100%', padding: '6px 10px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
                        />
                      </div>
                    )}
                    {!detail.invoice_id && (
                      <div className={styles.formItem}>
                        <label className={styles.formLabel}>发票ID</label>
                        <input
                          type="text"
                          value={manualInvoiceId}
                          onChange={(e) => setManualInvoiceId(e.target.value)}
                          placeholder="输入发票ID"
                          style={{ width: '100%', padding: '6px 10px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
                        />
                      </div>
                    )}
                    <ZButton variant="primary" onClick={handleManualMatch} style={{ marginTop: 8 }}>
                      确认匹配
                    </ZButton>
                  </div>
                </div>
              )}

              {/* 争议解决 */}
              {detail.status === 'disputed' && (
                <div className={styles.drawerSection}>
                  <div className={styles.drawerSectionTitle}>解决争议</div>
                  <div className={styles.manualMatchForm}>
                    <div className={styles.formItem}>
                      <label className={styles.formLabel}>处理说明</label>
                      <textarea
                        value={resolveNotes}
                        onChange={(e) => setResolveNotes(e.target.value)}
                        placeholder="请输入争议处理说明..."
                        rows={3}
                        style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13, resize: 'vertical' }}
                      />
                    </div>
                    <ZButton variant="primary" onClick={handleResolve}>
                      标记已解决
                    </ZButton>
                  </div>
                </div>
              )}

              {/* 备注 */}
              {detail.notes && (
                <div className={styles.drawerSection}>
                  <div className={styles.drawerSectionTitle}>备注</div>
                  <p style={{ fontSize: 13, color: '#4b5563', lineHeight: 1.6 }}>{detail.notes}</p>
                </div>
              )}
            </>
          ) : (
            <ZEmpty description="加载失败" />
          )}
        </div>
      )}

      {/* 抽屉遮罩 */}
      {drawerOpen && (
        <div
          style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.3)', zIndex: 999,
          }}
          onClick={() => setDrawerOpen(false)}
        />
      )}
    </div>
  );
}

export default TriReconciliationPage;
