/**
 * SupplierB2BPage — /platform/supplier-b2b
 *
 * 供应商B2B采购单管理：创建/提交/收货/取消，统计概览
 * 后端 API:
 *   GET    /api/v1/supplier-b2b/orders            — 采购单列表
 *   GET    /api/v1/supplier-b2b/orders/{id}       — 采购单详情
 *   POST   /api/v1/supplier-b2b/orders            — 创建采购单
 *   POST   /api/v1/supplier-b2b/orders/{id}/submit  — 提交给供应商
 *   POST   /api/v1/supplier-b2b/orders/{id}/receive — 收货确认
 *   POST   /api/v1/supplier-b2b/orders/{id}/cancel  — 取消
 *   GET    /api/v1/supplier-b2b/stats             — 统计概览
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  ZCard, ZBadge, ZButton, ZEmpty, ZAlert, ZSkeleton, ZModal,
} from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import { apiClient } from '../../services/api';
import styles from './SupplierB2BPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface PurchaseItem {
  id: string;
  order_id: string;
  ingredient_name: string;
  ingredient_id?: string;
  quantity: number;
  unit: string;
  unit_price_fen: number;
  amount_fen: number;
  received_quantity?: number;
  quality_status?: string;
}

interface PurchaseOrder {
  id: string;
  brand_id: string;
  store_id: string;
  supplier_id: string;
  supplier_name: string;
  order_number: string;
  status: string;
  total_amount_fen: number;
  expected_delivery_date?: string;
  actual_delivery_date?: string;
  notes?: string;
  submitted_at?: string;
  confirmed_at?: string;
  received_at?: string;
  created_at?: string;
  updated_at?: string;
  items: PurchaseItem[];
}

interface Stats {
  draft_count: number;
  pending_count: number;
  shipping_count: number;
  completed_count: number;
  monthly_spend_fen: number;
  monthly_completed: number;
  [key: string]: number;
}

interface ItemForm {
  ingredient_name: string;
  unit: string;
  quantity: string;
  unit_price_yuan: string;
}

interface ReceivedItemForm {
  item_id: string;
  ingredient_name: string;
  ordered_qty: number;
  received_quantity: string;
  quality_status: string;
}

const EMPTY_ITEM: ItemForm = { ingredient_name: '', unit: 'kg', quantity: '', unit_price_yuan: '' };

// ── 工具函数 ─────────────────────────────────────────────────────────────────

function fmtYuan(fen: number): string {
  return `\u00A5${(fen / 100).toFixed(2)}`;
}

function fmtDate(iso?: string): string {
  if (!iso) return '\u2014';
  try {
    return new Date(iso).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
  } catch { return iso; }
}

function fmtTime(iso?: string): string {
  if (!iso) return '\u2014';
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

const STATUS_MAP: Record<string, { label: string; variant: 'default' | 'success' | 'warning' | 'error' | 'processing' }> = {
  draft:     { label: '草稿',   variant: 'default' },
  submitted: { label: '已提交', variant: 'processing' },
  confirmed: { label: '已确认', variant: 'processing' },
  shipping:  { label: '运输中', variant: 'warning' },
  received:  { label: '已收货', variant: 'success' },
  completed: { label: '已完成', variant: 'success' },
  cancelled: { label: '已取消', variant: 'error' },
};

const STATUS_FLOW = ['draft', 'submitted', 'confirmed', 'shipping', 'received', 'completed'];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const SupplierB2BPage: React.FC = () => {
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filterStatus, setFilterStatus] = useState('');
  const [searchText, setSearchText] = useState('');

  // 创建 Modal
  const [showCreate, setShowCreate] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [createErr, setCreateErr] = useState('');
  const [supplierName, setSupplierName] = useState('');
  const [supplierId, setSupplierId] = useState('');
  const [storeId, setStoreId] = useState('');
  const [expectedDate, setExpectedDate] = useState('');
  const [orderNotes, setOrderNotes] = useState('');
  const [items, setItems] = useState<ItemForm[]>([{ ...EMPTY_ITEM }]);

  // 详情 Drawer
  const [detailOrder, setDetailOrder] = useState<PurchaseOrder | null>(null);
  const [showDetail, setShowDetail] = useState(false);

  // 收货 Modal
  const [showReceive, setShowReceive] = useState(false);
  const [receiveOrder, setReceiveOrderData] = useState<PurchaseOrder | null>(null);
  const [receiveItems, setReceiveItems] = useState<ReceivedItemForm[]>([]);
  const [receiveSubmitting, setReceiveSubmitting] = useState(false);

  const brandId = 'default';

  // ── 数据加载 ────────────────────────────────────────────────────────────

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [listRes, statsRes] = await Promise.all([
        apiClient.get<{ data: { items: PurchaseOrder[]; total: number } }>('/api/v1/supplier-b2b/orders', {
          params: { brand_id: brandId, page, page_size: 20, status: filterStatus || undefined },
        }),
        apiClient.get<{ data: Stats }>('/api/v1/supplier-b2b/stats', {
          params: { brand_id: brandId },
        }),
      ]);
      // apiClient.get<T>() returns T directly (response.data already unwrapped)
      const listData = (listRes as any).data || listRes;
      const statsData = (statsRes as any).data || statsRes;
      setOrders(listData.items || []);
      setTotal(listData.total || 0);
      setStats(statsData);
    } catch (err) {
      console.error('加载采购单数据失败', err);
    } finally {
      setLoading(false);
    }
  }, [brandId, page, filterStatus]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // ── 操作 ────────────────────────────────────────────────────────────────

  const handleSubmitOrder = async (id: string) => {
    try {
      await apiClient.post(`/api/v1/supplier-b2b/orders/${id}/submit`);
      fetchData();
    } catch (err) {
      console.error('提交采购单失败', err);
    }
  };

  const handleCancelOrder = async (id: string) => {
    try {
      await apiClient.post(`/api/v1/supplier-b2b/orders/${id}/cancel`, { reason: '手动取消' });
      fetchData();
    } catch (err) {
      console.error('取消采购单失败', err);
    }
  };

  const handleViewDetail = async (id: string) => {
    try {
      const res = await apiClient.get<{ data: PurchaseOrder }>(`/api/v1/supplier-b2b/orders/${id}`);
      const data = (res as any).data || res;
      setDetailOrder(data);
      setShowDetail(true);
    } catch (err) {
      console.error('获取采购单详情失败', err);
    }
  };

  const openReceiveModal = (order: PurchaseOrder) => {
    setReceiveOrderData(order);
    setReceiveItems(
      order.items.map(item => ({
        item_id: item.id,
        ingredient_name: item.ingredient_name,
        ordered_qty: item.quantity,
        received_quantity: String(item.quantity),
        quality_status: 'accepted',
      }))
    );
    setShowReceive(true);
  };

  const handleReceiveConfirm = async () => {
    if (!receiveOrder) return;
    setReceiveSubmitting(true);
    try {
      await apiClient.post(`/api/v1/supplier-b2b/orders/${receiveOrder.id}/receive`, {
        received_items: receiveItems.map(ri => ({
          item_id: ri.item_id,
          received_quantity: parseFloat(ri.received_quantity) || 0,
          quality_status: ri.quality_status,
        })),
      });
      setShowReceive(false);
      fetchData();
    } catch (err) {
      console.error('收货确认失败', err);
    } finally {
      setReceiveSubmitting(false);
    }
  };

  // ── 创建采购单 ────────────────────────────────────────────────────────────

  const resetForm = () => {
    setSupplierName(''); setSupplierId(''); setStoreId('');
    setExpectedDate(''); setOrderNotes('');
    setItems([{ ...EMPTY_ITEM }]);
    setCreateErr('');
  };

  const handleCreate = async () => {
    if (!supplierName.trim() || !supplierId.trim()) {
      setCreateErr('请填写供应商名称和供应商ID');
      return;
    }
    const validItems = items.filter(it => it.ingredient_name.trim());
    if (validItems.length === 0) {
      setCreateErr('至少需要一项采购明细');
      return;
    }

    setSubmitting(true);
    setCreateErr('');
    try {
      await apiClient.post('/api/v1/supplier-b2b/orders', {
        brand_id: brandId,
        store_id: storeId.trim() || 'default',
        supplier_id: supplierId.trim(),
        supplier_name: supplierName.trim(),
        expected_delivery_date: expectedDate || undefined,
        notes: orderNotes.trim() || undefined,
        items: validItems.map(it => ({
          ingredient_name: it.ingredient_name.trim(),
          unit: it.unit.trim() || 'kg',
          quantity: parseFloat(it.quantity) || 0,
          unit_price_fen: Math.round((parseFloat(it.unit_price_yuan) || 0) * 100),
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

  const updateItem = (idx: number, field: keyof ItemForm, val: string) => {
    setItems(prev => prev.map((it, i) => i === idx ? { ...it, [field]: val } : it));
  };

  const addItem = () => setItems(prev => [...prev, { ...EMPTY_ITEM }]);

  const removeItem = (idx: number) => {
    if (items.length <= 1) return;
    setItems(prev => prev.filter((_, i) => i !== idx));
  };

  // ── 过滤 ────────────────────────────────────────────────────────────────

  const filtered = searchText.trim()
    ? orders.filter(o =>
        o.supplier_name.includes(searchText) ||
        o.order_number.includes(searchText)
      )
    : orders;

  // ── 状态流可视化 ─────────────────────────────────────────────────────────

  const renderStatusFlow = (currentStatus: string) => {
    const currentIdx = STATUS_FLOW.indexOf(currentStatus);
    const isCancelled = currentStatus === 'cancelled';

    return (
      <div className={styles.statusFlow}>
        {STATUS_FLOW.map((s, idx) => {
          let cls = styles.statusStep;
          if (!isCancelled) {
            if (idx < currentIdx) cls = styles.statusStepDone;
            else if (idx === currentIdx) cls = styles.statusStepActive;
          }
          return (
            <React.Fragment key={s}>
              {idx > 0 && <span className={styles.statusArrow}>&rarr;</span>}
              <span className={cls}>
                {STATUS_MAP[s]?.label || s}
              </span>
            </React.Fragment>
          );
        })}
        {isCancelled && (
          <>
            <span className={styles.statusArrow}>|</span>
            <span className={styles.statusStepActive}>{STATUS_MAP.cancelled.label}</span>
          </>
        )}
      </div>
    );
  };

  // ── 表格列 ──────────────────────────────────────────────────────────────

  const columns: ZTableColumn<PurchaseOrder>[] = [
    {
      key: 'order_number',
      title: '采购单号',
      render: (o) => (
        <span className={styles.orderNumber} onClick={() => handleViewDetail(o.id)}>
          {o.order_number}
        </span>
      ),
    },
    {
      key: 'supplier',
      title: '供应商',
      render: (o) => <span className={styles.supplierCell}>{o.supplier_name}</span>,
    },
    {
      key: 'amount',
      title: '金额',
      render: (o) => <span className={styles.amountCell}>{fmtYuan(o.total_amount_fen)}</span>,
    },
    {
      key: 'status',
      title: '状态',
      render: (o) => {
        const s = STATUS_MAP[o.status] || { label: o.status, variant: 'default' as const };
        return <ZBadge variant={s.variant}>{s.label}</ZBadge>;
      },
    },
    {
      key: 'expected',
      title: '预计交货',
      render: (o) => <span className={styles.timeCell}>{fmtDate(o.expected_delivery_date)}</span>,
    },
    {
      key: 'created_at',
      title: '创建时间',
      render: (o) => <span className={styles.timeCell}>{fmtTime(o.created_at)}</span>,
    },
    {
      key: 'actions',
      title: '',
      render: (o) => (
        <div className={styles.actionGroup}>
          <ZButton size="xs" variant="ghost" onClick={() => handleViewDetail(o.id)}>详情</ZButton>
          {o.status === 'draft' && (
            <ZButton size="xs" onClick={() => handleSubmitOrder(o.id)}>提交</ZButton>
          )}
          {(o.status === 'shipping' || o.status === 'confirmed') && (
            <ZButton size="xs" onClick={() => openReceiveModal(o)}>收货</ZButton>
          )}
          {['draft', 'submitted', 'confirmed'].includes(o.status) && (
            <ZButton size="xs" variant="danger" onClick={() => handleCancelOrder(o.id)}>取消</ZButton>
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
          <h1 className={styles.pageTitle}>供应商B2B采购</h1>
          <p className={styles.pageSubtitle}>管理采购单：创建、提交、跟踪交货、收货确认</p>
        </div>
        <div className={styles.headerActions}>
          <ZButton onClick={() => { resetForm(); setShowCreate(true); }}>创建采购单</ZButton>
          <ZButton variant="ghost" onClick={fetchData}>刷新</ZButton>
        </div>
      </div>

      {/* 统计卡片 */}
      {loading ? (
        <ZSkeleton height={90} />
      ) : stats && (
        <div className={styles.statsRow}>
          <ZCard className={styles.statCard}>
            <div className={`${styles.statNum} ${styles.statOrange}`}>{stats.draft_count}</div>
            <div className={styles.statLabel}>草稿</div>
          </ZCard>
          <ZCard className={styles.statCard}>
            <div className={`${styles.statNum} ${styles.statBlue}`}>{stats.pending_count}</div>
            <div className={styles.statLabel}>待处理/运输中</div>
          </ZCard>
          <ZCard className={styles.statCard}>
            <div className={`${styles.statNum} ${styles.statGreen}`}>{fmtYuan(stats.monthly_spend_fen)}</div>
            <div className={styles.statLabel}>本月采购额</div>
          </ZCard>
          <ZCard className={styles.statCard}>
            <div className={`${styles.statNum} ${styles.statGreen}`}>{stats.monthly_completed}</div>
            <div className={styles.statLabel}>本月已完成</div>
          </ZCard>
        </div>
      )}

      {/* 筛选工具栏 */}
      <div className={styles.toolbar}>
        <select
          className={styles.filterSelect}
          value={filterStatus}
          onChange={e => { setFilterStatus(e.target.value); setPage(1); }}
        >
          <option value="">全部状态</option>
          <option value="draft">草稿</option>
          <option value="submitted">已提交</option>
          <option value="confirmed">已确认</option>
          <option value="shipping">运输中</option>
          <option value="received">已收货</option>
          <option value="completed">已完成</option>
          <option value="cancelled">已取消</option>
        </select>
        <input
          className={styles.searchInput}
          placeholder="搜索供应商名称 / 采购单号"
          value={searchText}
          onChange={e => setSearchText(e.target.value)}
        />
        <div className={styles.toolbarSpacer} />
        <span className={styles.timeCell}>共 {total} 条</span>
      </div>

      {/* 采购单表格 */}
      <ZCard className={styles.tableCard}>
        {loading ? (
          <ZSkeleton rows={6} />
        ) : filtered.length === 0 ? (
          <ZEmpty description="暂无采购单记录" />
        ) : (
          <ZTable<PurchaseOrder> columns={columns} data={filtered} rowKey="id" />
        )}
      </ZCard>

      {/* 创建采购单 Modal */}
      <ZModal
        open={showCreate}
        title="创建采购单"
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
          {createErr && <ZAlert type="error" className={styles.modalErr}>{createErr}</ZAlert>}

          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                供应商名称<span className={styles.fieldRequired}>*</span>
              </label>
              <input className={styles.fieldInput} value={supplierName}
                onChange={e => setSupplierName(e.target.value)} placeholder="供应商全称" />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                供应商ID<span className={styles.fieldRequired}>*</span>
              </label>
              <input className={styles.fieldInput} value={supplierId}
                onChange={e => setSupplierId(e.target.value)} placeholder="供应商编号" />
            </div>
          </div>

          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>门店ID</label>
              <input className={styles.fieldInput} value={storeId}
                onChange={e => setStoreId(e.target.value)} placeholder="下单门店（可选）" />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>预计交货日期</label>
              <input className={styles.fieldInput} type="date" value={expectedDate}
                onChange={e => setExpectedDate(e.target.value)} />
            </div>
          </div>

          <div className={styles.fieldRow}>
            <label className={styles.fieldLabel}>备注</label>
            <input className={styles.fieldInput} value={orderNotes}
              onChange={e => setOrderNotes(e.target.value)} placeholder="可选" />
          </div>

          {/* 采购明细 */}
          <div className={styles.itemsSection}>
            <div className={styles.itemsSectionHeader}>
              <span className={styles.itemsSectionTitle}>采购明细</span>
              <ZButton size="xs" variant="ghost" onClick={addItem}>+ 添加行</ZButton>
            </div>
            <div className={styles.itemLabels}>
              <span>食材名称 *</span>
              <span>单位</span>
              <span>数量</span>
              <span>单价（元）</span>
              <span />
            </div>
            {items.map((item, idx) => (
              <div key={idx} className={styles.itemRow}>
                <input className={styles.itemInput} placeholder="食材名称"
                  value={item.ingredient_name} onChange={e => updateItem(idx, 'ingredient_name', e.target.value)} />
                <input className={styles.itemInput} placeholder="kg"
                  value={item.unit} onChange={e => updateItem(idx, 'unit', e.target.value)} />
                <input className={styles.itemInput} type="number" placeholder="0"
                  value={item.quantity} onChange={e => updateItem(idx, 'quantity', e.target.value)} />
                <input className={styles.itemInput} type="number" step="0.01" placeholder="0.00"
                  value={item.unit_price_yuan} onChange={e => updateItem(idx, 'unit_price_yuan', e.target.value)} />
                <button className={styles.removeItemBtn} onClick={() => removeItem(idx)}
                  title="删除此行" disabled={items.length <= 1}>&times;</button>
              </div>
            ))}
          </div>
        </div>
      </ZModal>

      {/* 详情 Drawer（用 Modal 模拟） */}
      <ZModal
        open={showDetail}
        title={`采购单详情 ${detailOrder?.order_number || ''}`}
        onClose={() => setShowDetail(false)}
        footer={
          <div className={styles.modalFooter}>
            <ZButton variant="ghost" onClick={() => setShowDetail(false)}>关闭</ZButton>
          </div>
        }
      >
        {detailOrder && (
          <div className={styles.modalBody}>
            {/* 状态流 */}
            {renderStatusFlow(detailOrder.status)}

            {/* 基本信息 */}
            <div className={styles.detailSection}>
              <div className={styles.detailSectionTitle}>基本信息</div>
              <div className={styles.detailGrid}>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>采购单号</span>
                  <span className={styles.detailValue}>{detailOrder.order_number}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>供应商</span>
                  <span className={styles.detailValue}>{detailOrder.supplier_name}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>总金额</span>
                  <span className={styles.detailValue}>{fmtYuan(detailOrder.total_amount_fen)}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>状态</span>
                  <span className={styles.detailValue}>
                    {STATUS_MAP[detailOrder.status]?.label || detailOrder.status}
                  </span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>预计交货</span>
                  <span className={styles.detailValue}>{fmtDate(detailOrder.expected_delivery_date)}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>实际交货</span>
                  <span className={styles.detailValue}>{fmtDate(detailOrder.actual_delivery_date)}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>创建时间</span>
                  <span className={styles.detailValue}>{fmtTime(detailOrder.created_at)}</span>
                </div>
                <div className={styles.detailItem}>
                  <span className={styles.detailLabel}>提交时间</span>
                  <span className={styles.detailValue}>{fmtTime(detailOrder.submitted_at)}</span>
                </div>
              </div>
              {detailOrder.notes && (
                <div className={styles.detailItem} style={{ marginTop: 10 }}>
                  <span className={styles.detailLabel}>备注</span>
                  <span className={styles.detailValue}>{detailOrder.notes}</span>
                </div>
              )}
            </div>

            {/* 明细表 */}
            <div className={styles.detailSection}>
              <div className={styles.detailSectionTitle}>采购明细</div>
              <ZTable<PurchaseItem>
                columns={[
                  { key: 'name', title: '食材', render: (it) => it.ingredient_name },
                  { key: 'qty', title: '数量', render: (it) => `${it.quantity} ${it.unit}` },
                  { key: 'price', title: '单价', render: (it) => fmtYuan(it.unit_price_fen) },
                  { key: 'amount', title: '小计', render: (it) => <span className={styles.amountCell}>{fmtYuan(it.amount_fen)}</span> },
                  { key: 'received', title: '收货数量', render: (it) => it.received_quantity != null ? `${it.received_quantity} ${it.unit}` : '\u2014' },
                  {
                    key: 'quality', title: '质量',
                    render: (it) => {
                      if (!it.quality_status) return '\u2014';
                      const qMap: Record<string, { label: string; variant: 'success' | 'error' | 'warning' }> = {
                        accepted: { label: '合格', variant: 'success' },
                        rejected: { label: '拒收', variant: 'error' },
                        partial:  { label: '部分合格', variant: 'warning' },
                      };
                      const q = qMap[it.quality_status] || { label: it.quality_status, variant: 'default' as any };
                      return <ZBadge variant={q.variant}>{q.label}</ZBadge>;
                    },
                  },
                ]}
                data={detailOrder.items}
                rowKey="id"
              />
            </div>
          </div>
        )}
      </ZModal>

      {/* 收货确认 Modal */}
      <ZModal
        open={showReceive}
        title={`收货确认 ${receiveOrder?.order_number || ''}`}
        onClose={() => setShowReceive(false)}
        footer={
          <div className={styles.modalFooter}>
            <ZButton variant="ghost" onClick={() => setShowReceive(false)}>取消</ZButton>
            <ZButton onClick={handleReceiveConfirm} disabled={receiveSubmitting}>
              {receiveSubmitting ? '确认中...' : '确认收货'}
            </ZButton>
          </div>
        }
      >
        <div className={styles.modalBody}>
          <div className={styles.receiveHeader}>
            <span>食材</span>
            <span>订购数量</span>
            <span>收货数量</span>
            <span>质量状态</span>
          </div>
          {receiveItems.map((ri, idx) => (
            <div key={ri.item_id} className={styles.receiveRow}>
              <span>{ri.ingredient_name}</span>
              <span>{ri.ordered_qty}</span>
              <input
                className={styles.receiveInput}
                type="number"
                step="0.01"
                value={ri.received_quantity}
                onChange={e => {
                  const val = e.target.value;
                  setReceiveItems(prev => prev.map((r, i) => i === idx ? { ...r, received_quantity: val } : r));
                }}
              />
              <select
                className={styles.filterSelect}
                value={ri.quality_status}
                onChange={e => {
                  const val = e.target.value;
                  setReceiveItems(prev => prev.map((r, i) => i === idx ? { ...r, quality_status: val } : r));
                }}
              >
                <option value="accepted">合格</option>
                <option value="partial">部分合格</option>
                <option value="rejected">拒收</option>
              </select>
            </div>
          ))}
        </div>
      </ZModal>
    </div>
  );
};

export default SupplierB2BPage;
