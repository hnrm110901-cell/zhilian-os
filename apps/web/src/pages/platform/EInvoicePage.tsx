/**
 * EInvoicePage — /platform/e-invoices
 *
 * 电子发票管理：创建/提交/作废/查询发票，对接诺诺/百旺平台
 * 后端 API:
 *   GET    /api/v1/e-invoices            — 发票列表
 *   GET    /api/v1/e-invoices/stats      — 统计概览
 *   POST   /api/v1/e-invoices            — 创建发票（草稿）
 *   POST   /api/v1/e-invoices/{id}/submit — 提交开票
 *   POST   /api/v1/e-invoices/{id}/void   — 作废
 */
import React, { useState, useEffect, useCallback } from 'react';
import { message } from 'antd';
import {
  ZCard, ZBadge, ZButton, ZEmpty, ZAlert, ZSkeleton, ZModal,
} from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import { apiClient } from '../../services/api';
import styles from './EInvoicePage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface Invoice {
  id: string;
  brand_id: string;
  store_id?: string;
  order_id?: string;
  invoice_type: string;
  invoice_code?: string;
  invoice_number?: string;
  buyer_name: string;
  buyer_tax_number?: string;
  seller_name: string;
  total_amount_fen: number;
  tax_amount_fen: number;
  platform: string;
  status: string;
  pdf_url?: string;
  issued_at?: string;
  created_at?: string;
  operator?: string;
}

interface InvoiceStats {
  [status: string]: { count: number; total_fen: number };
}

interface InvoiceItemForm {
  item_name: string;
  unit: string;
  quantity: string;
  amount_fen: string;
}

const EMPTY_ITEM: InvoiceItemForm = { item_name: '', unit: '', quantity: '', amount_fen: '' };

// ── 工具函数 ─────────────────────────────────────────────────────────────────

function fmtYuan(fen: number): string {
  return `\u00A5${(fen / 100).toFixed(2)}`;
}

function fmtTime(iso?: string): string {
  if (!iso) return '\u2014';
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

const STATUS_MAP: Record<string, { label: string; variant: 'default' | 'success' | 'warning' | 'error' | 'info' }> = {
  draft:        { label: '草稿',   variant: 'default' },
  issuing:      { label: '开票中', variant: 'info' },
  issued:       { label: '已开票', variant: 'success' },
  void_pending: { label: '作废中', variant: 'warning' },
  voided:       { label: '已作废', variant: 'error' },
  red_pending:  { label: '红冲中', variant: 'warning' },
  red_issued:   { label: '已红冲', variant: 'error' },
};

const TYPE_LABELS: Record<string, string> = {
  normal_electronic: '普电',
  special_electronic: '专电',
  normal_paper: '纸质',
};

// ── 组件 ─────────────────────────────────────────────────────────────────────

const EInvoicePage: React.FC = () => {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [stats, setStats] = useState<InvoiceStats>({});
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('');
  const [searchText, setSearchText] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [createErr, setCreateErr] = useState('');

  // 创建表单
  const [buyerName, setBuyerName] = useState('');
  const [buyerTax, setBuyerTax] = useState('');
  const [sellerName, setSellerName] = useState('');
  const [sellerTax, setSellerTax] = useState('');
  const [totalYuan, setTotalYuan] = useState('');
  const [taxYuan, setTaxYuan] = useState('');
  const [remark, setRemark] = useState('');
  const [items, setItems] = useState<InvoiceItemForm[]>([{ ...EMPTY_ITEM }]);

  const brandId = 'default'; // 从上下文获取

  // ── 数据加载 ────────────────────────────────────────────────────────────

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [listRes, statsRes] = await Promise.all([
        apiClient.get<Invoice[]>('/api/v1/e-invoices', {
          params: { brand_id: brandId, status: filterStatus || undefined, limit: 100 },
        }),
        apiClient.get<InvoiceStats>('/api/v1/e-invoices/stats', {
          params: { brand_id: brandId },
        }),
      ]);
      setInvoices(listRes);
      setStats(statsRes);
    } catch (err) {
      message.error('加载发票数据失败');
    } finally {
      setLoading(false);
    }
  }, [brandId, filterStatus]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // ── 操作 ────────────────────────────────────────────────────────────────

  const handleSubmitInvoice = async (id: string) => {
    try {
      await apiClient.post(`/api/v1/e-invoices/${id}/submit`);
      fetchData();
    } catch (err) {
      message.error('提交开票失败');
    }
  };

  const handleVoidInvoice = async (id: string) => {
    try {
      await apiClient.post(`/api/v1/e-invoices/${id}/void`);
      fetchData();
    } catch (err) {
      message.error('作废失败');
    }
  };

  const handleDownloadPdf = (url?: string) => {
    if (url) window.open(url, '_blank');
  };

  // ── 创建发票 ────────────────────────────────────────────────────────────

  const resetForm = () => {
    setBuyerName(''); setBuyerTax(''); setSellerName(''); setSellerTax('');
    setTotalYuan(''); setTaxYuan(''); setRemark('');
    setItems([{ ...EMPTY_ITEM }]);
    setCreateErr('');
  };

  const handleCreate = async () => {
    if (!buyerName.trim() || !sellerName.trim() || !sellerTax.trim() || !totalYuan.trim()) {
      setCreateErr('请填写必填字段：购方名称、销方名称、销方税号、总金额');
      return;
    }
    const totalFen = Math.round(parseFloat(totalYuan) * 100);
    const taxFen = taxYuan ? Math.round(parseFloat(taxYuan) * 100) : 0;
    if (isNaN(totalFen) || totalFen <= 0) {
      setCreateErr('总金额格式不正确');
      return;
    }
    const validItems = items.filter(it => it.item_name.trim());
    if (validItems.length === 0) {
      setCreateErr('至少需要一项发票明细');
      return;
    }

    setSubmitting(true);
    setCreateErr('');
    try {
      await apiClient.post('/api/v1/e-invoices', {
        brand_id: brandId,
        buyer_name: buyerName.trim(),
        buyer_tax_number: buyerTax.trim() || undefined,
        seller_name: sellerName.trim(),
        seller_tax_number: sellerTax.trim(),
        total_amount_fen: totalFen,
        tax_amount_fen: taxFen,
        remark: remark.trim() || undefined,
        items: validItems.map(it => ({
          item_name: it.item_name.trim(),
          unit: it.unit.trim() || undefined,
          quantity: it.quantity ? parseInt(it.quantity, 10) : undefined,
          amount_fen: it.amount_fen ? Math.round(parseFloat(it.amount_fen) * 100) : totalFen,
        })),
      });
      setShowCreate(false);
      resetForm();
      fetchData();
    } catch (err: any) {
      setCreateErr(err?.message || '创建失败');
    } finally {
      setSubmitting(false);
    }
  };

  // ── 明细行管理 ──────────────────────────────────────────────────────────

  const updateItem = (idx: number, field: keyof InvoiceItemForm, val: string) => {
    setItems(prev => prev.map((it, i) => i === idx ? { ...it, [field]: val } : it));
  };

  const addItem = () => setItems(prev => [...prev, { ...EMPTY_ITEM }]);

  const removeItem = (idx: number) => {
    if (items.length <= 1) return;
    setItems(prev => prev.filter((_, i) => i !== idx));
  };

  // ── 统计计算 ────────────────────────────────────────────────────────────

  const statIssued = stats['issued'] || { count: 0, total_fen: 0 };
  const statIssuing = stats['issuing'] || { count: 0, total_fen: 0 };
  const statVoided = (stats['voided'] || { count: 0, total_fen: 0 });
  const totalFenAll = Object.values(stats).reduce((s, v) => s + v.total_fen, 0);

  // ── 表格过滤 ────────────────────────────────────────────────────────────

  const filtered = searchText.trim()
    ? invoices.filter(inv =>
        inv.buyer_name.includes(searchText) ||
        (inv.invoice_number || '').includes(searchText) ||
        (inv.order_id || '').includes(searchText)
      )
    : invoices;

  // ── 表格列 ──────────────────────────────────────────────────────────────

  const columns: ZTableColumn<Invoice>[] = [
    {
      key: 'buyer',
      title: '购方',
      render: (inv) => (
        <div className={styles.buyerCell}>
          <span className={styles.buyerName}>{inv.buyer_name}</span>
          {inv.buyer_tax_number && <span className={styles.buyerTax}>{inv.buyer_tax_number}</span>}
        </div>
      ),
    },
    {
      key: 'type',
      title: '类型',
      render: (inv) => TYPE_LABELS[inv.invoice_type] || inv.invoice_type,
    },
    {
      key: 'invoice_number',
      title: '发票号码',
      render: (inv) => inv.invoice_number
        ? <span className={styles.invoiceNo}>{inv.invoice_code}-{inv.invoice_number}</span>
        : <span className={styles.timeCell}>{'\u2014'}</span>,
    },
    {
      key: 'amount',
      title: '金额',
      render: (inv) => <span className={styles.amountCell}>{fmtYuan(inv.total_amount_fen)}</span>,
    },
    {
      key: 'status',
      title: '状态',
      render: (inv) => {
        const s = STATUS_MAP[inv.status] || { label: inv.status, variant: 'default' as const };
        return <ZBadge type={s.variant} text={s.label} />;
      },
    },
    {
      key: 'platform',
      title: '平台',
      render: (inv) => inv.platform === 'nuonuo' ? '诺诺' : inv.platform === 'baiwang' ? '百旺' : inv.platform,
    },
    {
      key: 'created_at',
      title: '创建时间',
      render: (inv) => <span className={styles.timeCell}>{fmtTime(inv.created_at)}</span>,
    },
    {
      key: 'actions',
      title: '',
      render: (inv) => (
        <div className={styles.actionGroup}>
          {inv.status === 'draft' && (
            <ZButton size="sm" onClick={() => handleSubmitInvoice(inv.id)}>提交开票</ZButton>
          )}
          {inv.status === 'issued' && (
            <>
              <ZButton size="sm" variant="ghost" onClick={() => handleDownloadPdf(inv.pdf_url)}>PDF</ZButton>
              <ZButton size="sm" variant="danger" onClick={() => handleVoidInvoice(inv.id)}>作废</ZButton>
            </>
          )}
        </div>
      ),
    },
  ];

  // ── 渲染 ────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>电子发票管理</h1>
          <p className={styles.pageSubtitle}>创建/提交/查询/作废电子发票，对接诺诺/百旺平台</p>
        </div>
        <div className={styles.headerActions}>
          <ZButton onClick={() => { resetForm(); setShowCreate(true); }}>开票</ZButton>
          <ZButton variant="ghost" onClick={fetchData}>刷新</ZButton>
        </div>
      </div>

      {/* 统计卡片 */}
      {loading ? (
        <ZSkeleton height={90} />
      ) : (
        <div className={styles.statsRow}>
          <ZCard className={styles.statCard}>
            <div className={`${styles.statNum} ${styles.statGreen}`}>{statIssued.count}</div>
            <div className={styles.statLabel}>已开票</div>
          </ZCard>
          <ZCard className={styles.statCard}>
            <div className={`${styles.statNum} ${styles.statOrange}`}>{statIssuing.count}</div>
            <div className={styles.statLabel}>开票中</div>
          </ZCard>
          <ZCard className={styles.statCard}>
            <div className={`${styles.statNum} ${styles.statRed}`}>{statVoided.count}</div>
            <div className={styles.statLabel}>已作废</div>
          </ZCard>
          <ZCard className={styles.statCard}>
            <div className={`${styles.statNum} ${styles.statBlue}`}>{fmtYuan(totalFenAll)}</div>
            <div className={styles.statLabel}>累计金额</div>
          </ZCard>
        </div>
      )}

      {/* 筛选工具栏 */}
      <div className={styles.toolbar}>
        <select
          className={styles.filterSelect}
          value={filterStatus}
          onChange={e => setFilterStatus(e.target.value)}
        >
          <option value="">全部状态</option>
          <option value="draft">草稿</option>
          <option value="issuing">开票中</option>
          <option value="issued">已开票</option>
          <option value="voided">已作废</option>
          <option value="red_issued">已红冲</option>
        </select>
        <input
          className={styles.searchInput}
          placeholder="搜索购方名称 / 发票号码 / 订单号"
          value={searchText}
          onChange={e => setSearchText(e.target.value)}
        />
        <div className={styles.toolbarSpacer} />
      </div>

      {/* 发票表格 */}
      <ZCard className={styles.tableCard}>
        {loading ? (
          <ZSkeleton rows={6} />
        ) : filtered.length === 0 ? (
          <ZEmpty description="暂无发票记录" />
        ) : (
          <ZTable<Invoice> columns={columns} data={filtered} rowKey="id" />
        )}
      </ZCard>

      {/* 创建发票 Modal */}
      <ZModal
        open={showCreate}
        title="创建发票"
        onClose={() => setShowCreate(false)}
        footer={
          <div className={styles.modalFooter}>
            <ZButton variant="ghost" onClick={() => setShowCreate(false)}>取消</ZButton>
            <ZButton onClick={handleCreate} disabled={submitting}>
              {submitting ? '创建中...' : '创建草稿'}
            </ZButton>
          </div>
        }
      >
        <div className={styles.modalBody}>
          {createErr && <ZAlert variant="error">{createErr}</ZAlert>}

          {/* 购方信息 */}
          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                购方名称<span className={styles.fieldRequired}>*</span>
              </label>
              <input className={styles.fieldInput} value={buyerName}
                onChange={e => setBuyerName(e.target.value)} placeholder="公司全称" />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>购方税号</label>
              <input className={styles.fieldInput} value={buyerTax}
                onChange={e => setBuyerTax(e.target.value)} placeholder="纳税人识别号" />
            </div>
          </div>

          {/* 销方信息 */}
          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                销方名称<span className={styles.fieldRequired}>*</span>
              </label>
              <input className={styles.fieldInput} value={sellerName}
                onChange={e => setSellerName(e.target.value)} placeholder="己方公司名称" />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                销方税号<span className={styles.fieldRequired}>*</span>
              </label>
              <input className={styles.fieldInput} value={sellerTax}
                onChange={e => setSellerTax(e.target.value)} placeholder="己方税号" />
            </div>
          </div>

          {/* 金额 */}
          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                总金额（元）<span className={styles.fieldRequired}>*</span>
              </label>
              <input className={styles.fieldInput} type="number" step="0.01"
                value={totalYuan} onChange={e => setTotalYuan(e.target.value)} placeholder="含税总额" />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>税额（元）</label>
              <input className={styles.fieldInput} type="number" step="0.01"
                value={taxYuan} onChange={e => setTaxYuan(e.target.value)} placeholder="默认0" />
            </div>
          </div>

          {/* 备注 */}
          <div className={styles.fieldRow}>
            <label className={styles.fieldLabel}>备注</label>
            <input className={styles.fieldInput} value={remark}
              onChange={e => setRemark(e.target.value)} placeholder="可选" />
          </div>

          {/* 发票明细 */}
          <div className={styles.itemsSection}>
            <div className={styles.itemsSectionHeader}>
              <span className={styles.itemsSectionTitle}>发票明细</span>
              <ZButton size="sm" variant="ghost" onClick={addItem}>+ 添加行</ZButton>
            </div>
            <div className={styles.itemLabels}>
              <span>商品名称 *</span>
              <span>单位</span>
              <span>数量</span>
              <span>金额（元）</span>
              <span />
            </div>
            {items.map((item, idx) => (
              <div key={idx} className={styles.itemRow}>
                <input className={styles.itemInput} placeholder="商品/服务名称"
                  value={item.item_name} onChange={e => updateItem(idx, 'item_name', e.target.value)} />
                <input className={styles.itemInput} placeholder="份/kg"
                  value={item.unit} onChange={e => updateItem(idx, 'unit', e.target.value)} />
                <input className={styles.itemInput} type="number" placeholder="0"
                  value={item.quantity} onChange={e => updateItem(idx, 'quantity', e.target.value)} />
                <input className={styles.itemInput} type="number" step="0.01" placeholder="0.00"
                  value={item.amount_fen} onChange={e => updateItem(idx, 'amount_fen', e.target.value)} />
                <button className={styles.removeItemBtn} onClick={() => removeItem(idx)}
                  title="删除此行" disabled={items.length <= 1}>&times;</button>
              </div>
            ))}
          </div>
        </div>
      </ZModal>
    </div>
  );
};

export default EInvoicePage;
