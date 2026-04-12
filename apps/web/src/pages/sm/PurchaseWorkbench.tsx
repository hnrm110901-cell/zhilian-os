/**
 * 采购工作台
 * 路由：/sm/purchase
 * 数据：/api/v1/purchase/*
 */
import React, { useEffect, useState, useCallback } from 'react';
import { message } from 'antd';
import { ZCard, ZButton, ZBadge, ZEmpty } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './PurchaseWorkbench.module.css';

interface POItem {
  id: string;
  ingredient_name: string;
  quantity: number;
  unit: string;
  unit_price: number;
  received_qty?: number;
  quality_ok?: boolean;
}

interface PurchaseOrder {
  id: string;
  po_number: string;
  supplier_name: string;
  status: string;
  items_count: number;
  total_amount: number;
  created_at: string;
  items?: POItem[];
}

interface Supplier {
  id: string;
  name: string;
}

interface IngredientOption {
  id: string;
  name: string;
  unit: string;
  unit_price: number;
}

const STORE_ID = localStorage.getItem('store_id') || '';

const STATUS_TABS = [
  { key: 'all', label: '全部' },
  { key: 'draft', label: '草稿' },
  { key: 'pending_confirm', label: '待确认' },
  { key: 'pending_receive', label: '待收货' },
  { key: 'completed', label: '已完成' },
];

const STATUS_MAP: Record<string, { label: string; type: 'success' | 'info' | 'warning' | 'critical' }> = {
  draft: { label: '草稿', type: 'info' },
  pending_confirm: { label: '待确认', type: 'warning' },
  pending_receive: { label: '待收货', type: 'warning' },
  completed: { label: '已完成', type: 'success' },
  cancelled: { label: '已取消', type: 'critical' },
};

export default function PurchaseWorkbench() {
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');

  /* 创建采购单 */
  const [showCreate, setShowCreate] = useState(false);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [selectedSupplier, setSelectedSupplier] = useState('');
  const [ingredientSearch, setIngredientSearch] = useState('');
  const [ingredientResults, setIngredientResults] = useState<IngredientOption[]>([]);
  const [newItems, setNewItems] = useState<POItem[]>([]);
  const [submitting, setSubmitting] = useState(false);

  /* 详情/收货 */
  const [activeOrder, setActiveOrder] = useState<PurchaseOrder | null>(null);
  const [receiveItems, setReceiveItems] = useState<POItem[]>([]);

  /* 加载采购单列表 */
  const loadOrders = useCallback(async () => {
    setLoading(true);
    try {
      const params = statusFilter === 'all' ? '' : `&status=${statusFilter}`;
      const resp = await apiClient.get(`/api/v1/purchase/orders?store_id=${STORE_ID}${params}`);
      setOrders(resp.orders ?? []);
    } catch {
      message.error('加载采购单失败');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { loadOrders(); }, [loadOrders]);

  /* 加载供应商列表 */
  const loadSuppliers = async () => {
    try {
      const resp = await apiClient.get(`/api/v1/purchase/suppliers?store_id=${STORE_ID}`);
      setSuppliers(resp.suppliers ?? []);
    } catch {
      message.error('加载供应商失败');
    }
  };

  /* 搜索食材 */
  const handleIngredientSearch = async () => {
    if (!ingredientSearch.trim()) return;
    try {
      const resp = await apiClient.get(
        `/api/v1/purchase/ingredients?store_id=${STORE_ID}&keyword=${encodeURIComponent(ingredientSearch)}`
      );
      setIngredientResults(resp.ingredients ?? []);
    } catch {
      message.error('搜索食材失败');
    }
  };

  /* 添加食材到新采购单 */
  const addIngredientToOrder = (ing: IngredientOption) => {
    if (newItems.find(i => i.id === ing.id)) {
      message.warning('该食材已添加');
      return;
    }
    setNewItems(prev => [...prev, {
      id: ing.id,
      ingredient_name: ing.name,
      quantity: 1,
      unit: ing.unit,
      unit_price: ing.unit_price,
    }]);
    setIngredientSearch('');
    setIngredientResults([]);
  };

  /* 更新新采购单中食材数量 */
  const updateNewItemQty = (id: string, qty: number) => {
    setNewItems(prev => prev.map(i => i.id === id ? { ...i, quantity: Math.max(0, qty) } : i));
  };

  /* 删除新采购单中食材 */
  const removeNewItem = (id: string) => {
    setNewItems(prev => prev.filter(i => i.id !== id));
  };

  /* 提交新采购单 */
  const handleCreateOrder = async () => {
    if (!selectedSupplier) {
      message.error('请选择供应商');
      return;
    }
    if (newItems.length === 0) {
      message.error('请至少添加一项食材');
      return;
    }
    setSubmitting(true);
    try {
      await apiClient.post('/api/v1/purchase/orders', {
        store_id: STORE_ID,
        supplier_id: selectedSupplier,
        items: newItems.map(i => ({
          ingredient_id: i.id,
          quantity: i.quantity,
          unit: i.unit,
        })),
      });
      message.success('采购单创建成功');
      setShowCreate(false);
      setNewItems([]);
      setSelectedSupplier('');
      loadOrders();
    } catch {
      message.error('创建失败');
    } finally {
      setSubmitting(false);
    }
  };

  /* 打开采购单详情 */
  const openOrderDetail = async (order: PurchaseOrder) => {
    try {
      const resp = await apiClient.get(`/api/v1/purchase/orders/${order.id}`);
      const detail = resp.order ?? { ...order, items: [] };
      setActiveOrder(detail);
      if (detail.status === 'pending_receive') {
        setReceiveItems((detail.items ?? []).map((item: POItem) => ({
          ...item,
          received_qty: item.quantity,
          quality_ok: true,
        })));
      }
    } catch {
      message.error('加载详情失败');
    }
  };

  /* 更新收货数量 */
  const updateReceiveQty = (id: string, qty: number) => {
    setReceiveItems(prev => prev.map(i => i.id === id ? { ...i, received_qty: Math.max(0, qty) } : i));
  };

  /* 更新质量状态 */
  const toggleQualityOk = (id: string) => {
    setReceiveItems(prev => prev.map(i => i.id === id ? { ...i, quality_ok: !i.quality_ok } : i));
  };

  /* 提交收货 */
  const handleReceive = async () => {
    if (!activeOrder) return;
    setSubmitting(true);
    try {
      await apiClient.post(`/api/v1/purchase/orders/${activeOrder.id}/receive`, {
        items: receiveItems.map(i => ({
          item_id: i.id,
          received_qty: i.received_qty,
          quality_ok: i.quality_ok,
        })),
      });
      message.success('收货确认成功');
      setActiveOrder(null);
      loadOrders();
    } catch {
      message.error('收货确认失败');
    } finally {
      setSubmitting(false);
    }
  };

  /* 确认采购单 */
  const handleConfirm = async () => {
    if (!activeOrder) return;
    setSubmitting(true);
    try {
      await apiClient.post(`/api/v1/purchase/orders/${activeOrder.id}/confirm`);
      message.success('采购单已确认');
      setActiveOrder(null);
      loadOrders();
    } catch {
      message.error('确认失败');
    } finally {
      setSubmitting(false);
    }
  };

  const yuan = (v: number) => `¥${v.toFixed(2)}`;

  const newOrderTotal = newItems.reduce((sum, i) => sum + i.quantity * i.unit_price, 0);

  /* 创建采购单视图 */
  if (showCreate) {
    return (
      <div className={styles.overlay}>
        <div className={styles.overlayHeader}>
          <button className={styles.backBtn} onClick={() => setShowCreate(false)}>{'<'}</button>
          <span className={styles.overlayTitle}>新建采购单</span>
        </div>

        <div className={styles.formSection}>
          <div className={styles.field}>
            <label className={styles.label}>供应商 <span className={styles.required}>*</span></label>
            <select
              className={styles.select}
              value={selectedSupplier}
              onChange={e => setSelectedSupplier(e.target.value)}
            >
              <option value="">请选择供应商</option>
              {suppliers.map(s => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
        </div>

        <div className={styles.formSection}>
          <div className={styles.sectionTitle}>添加食材</div>
          <div className={styles.searchRow}>
            <input
              className={styles.input}
              placeholder="搜索食材名称"
              value={ingredientSearch}
              onChange={e => setIngredientSearch(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleIngredientSearch()}
            />
            <ZButton size="sm" onClick={handleIngredientSearch}>搜索</ZButton>
          </div>

          {ingredientResults.map(ing => (
            <div key={ing.id} className={styles.addRow}>
              <span className={styles.addRowName}>{ing.name}</span>
              <span className={styles.addRowUnit}>{yuan(ing.unit_price)}/{ing.unit}</span>
              <button className={styles.addRowBtn} onClick={() => addIngredientToOrder(ing)}>添加</button>
            </div>
          ))}
        </div>

        {newItems.length > 0 && (
          <div className={styles.formSection}>
            <div className={styles.sectionTitle}>已添加食材</div>
            <div className={styles.itemsList}>
              {newItems.map(item => (
                <div key={item.id} className={styles.itemRow}>
                  <span className={styles.itemName}>{item.ingredient_name}</span>
                  <input
                    className={styles.addRowInput}
                    type="number"
                    min="0"
                    value={item.quantity}
                    onChange={e => updateNewItemQty(item.id, Number(e.target.value))}
                  />
                  <span className={styles.addRowUnit}>{item.unit}</span>
                  <span className={styles.itemAmount}>{yuan(item.quantity * item.unit_price)}</span>
                  <button className={styles.removeBtn} onClick={() => removeNewItem(item.id)}>x</button>
                </div>
              ))}
            </div>
            <div className={styles.totalRow}>
              <span className={styles.totalLabel}>合计</span>
              <span className={styles.totalValue}>{yuan(newOrderTotal)}</span>
            </div>
          </div>
        )}

        <div className={styles.bottomBar}>
          <button className={styles.secondaryBtn} onClick={() => setShowCreate(false)}>取消</button>
          <button
            className={styles.submitBtn}
            onClick={handleCreateOrder}
            disabled={submitting}
          >
            {submitting ? '提交中...' : '提交采购单'}
          </button>
        </div>
      </div>
    );
  }

  /* 采购单详情视图 */
  if (activeOrder) {
    const statusInfo = STATUS_MAP[activeOrder.status] ?? { label: activeOrder.status, type: 'info' as const };
    return (
      <div className={styles.overlay}>
        <div className={styles.overlayHeader}>
          <button className={styles.backBtn} onClick={() => setActiveOrder(null)}>{'<'}</button>
          <span className={styles.overlayTitle}>{activeOrder.po_number}</span>
          <ZBadge type={statusInfo.type} text={statusInfo.label} />
        </div>

        <div className={styles.formSection}>
          <div className={styles.field}>
            <span className={styles.label}>供应商</span>
            <span>{activeOrder.supplier_name}</span>
          </div>
          <div className={styles.field}>
            <span className={styles.label}>创建时间</span>
            <span>{activeOrder.created_at}</span>
          </div>
        </div>

        {/* 收货模式 */}
        {activeOrder.status === 'pending_receive' ? (
          <div className={styles.formSection}>
            <div className={styles.sectionTitle}>收货确认</div>
            <div className={styles.receiveSection}>
              {receiveItems.map(item => (
                <div key={item.id} className={styles.receiveItem}>
                  <span className={styles.receiveItemName}>{item.ingredient_name}</span>
                  <span className={styles.receiveExpected}>应收 {item.quantity}{item.unit}</span>
                  <input
                    className={styles.receiveInput}
                    type="number"
                    min="0"
                    value={item.received_qty ?? 0}
                    onChange={e => updateReceiveQty(item.id, Number(e.target.value))}
                  />
                  <span className={styles.addRowUnit}>{item.unit}</span>
                  <input
                    type="checkbox"
                    className={styles.checkbox}
                    checked={item.quality_ok ?? true}
                    onChange={() => toggleQualityOk(item.id)}
                  />
                  <span className={styles.checkLabel}>合格</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className={styles.formSection}>
            <div className={styles.sectionTitle}>采购明细</div>
            <div className={styles.itemsList}>
              {(activeOrder.items ?? []).map(item => (
                <div key={item.id} className={styles.itemRow}>
                  <span className={styles.itemName}>{item.ingredient_name}</span>
                  <span className={styles.itemQty}>{item.quantity}{item.unit}</span>
                  <span className={styles.itemAmount}>{yuan(item.quantity * item.unit_price)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className={styles.totalRow}>
          <span className={styles.totalLabel}>合计金额</span>
          <span className={styles.totalValue}>{yuan(activeOrder.total_amount)}</span>
        </div>

        <div className={styles.bottomBar}>
          {activeOrder.status === 'draft' && (
            <button className={styles.submitBtn} onClick={handleConfirm} disabled={submitting}>
              {submitting ? '提交中...' : '提交确认'}
            </button>
          )}
          {activeOrder.status === 'pending_confirm' && (
            <button className={styles.submitBtn} onClick={handleConfirm} disabled={submitting}>
              {submitting ? '确认中...' : '确认采购单'}
            </button>
          )}
          {activeOrder.status === 'pending_receive' && (
            <button className={styles.submitBtn} onClick={handleReceive} disabled={submitting}>
              {submitting ? '提交中...' : '确认收货'}
            </button>
          )}
          {activeOrder.status === 'completed' && (
            <button className={styles.secondaryBtn} onClick={() => setActiveOrder(null)}>返回</button>
          )}
        </div>
      </div>
    );
  }

  /* 采购单列表视图 */
  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <span className={styles.title}>采购工作台</span>
        <button className={styles.createBtn} onClick={() => { setShowCreate(true); loadSuppliers(); }}>
          新建采购单
        </button>
      </div>

      <div className={styles.tabs}>
        {STATUS_TABS.map(tab => (
          <button
            key={tab.key}
            className={`${styles.tab} ${statusFilter === tab.key ? styles.tabActive : ''}`}
            onClick={() => setStatusFilter(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className={styles.skeleton} />
      ) : orders.length === 0 ? (
        <div className={styles.emptyWrap}>
          <ZEmpty title="暂无采购单" description="点击右上角新建采购单" />
        </div>
      ) : (
        <div className={styles.poList}>
          {orders.map(order => {
            const statusInfo = STATUS_MAP[order.status] ?? { label: order.status, type: 'info' as const };
            return (
              <div key={order.id} className={styles.poCard} onClick={() => openOrderDetail(order)}>
                <div className={styles.poCardHeader}>
                  <span className={styles.poNumber}>{order.po_number}</span>
                  <ZBadge type={statusInfo.type} text={statusInfo.label} />
                </div>
                <div className={styles.poCardBody}>
                  <div>
                    <div className={styles.poSupplier}>{order.supplier_name}</div>
                    <div className={styles.poItemCount}>{order.items_count}项食材</div>
                  </div>
                  <span className={styles.poAmount}>{yuan(order.total_amount)}</span>
                </div>
                <div className={styles.poDate}>{order.created_at}</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
