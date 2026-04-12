/**
 * POS 收银台
 * 路由：/sm/pos
 * 数据：/api/v1/pos-terminal/*
 */
import React, { useEffect, useState, useCallback } from 'react';
import { message } from 'antd';
import { ZCard, ZButton, ZBadge, ZEmpty } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './PosTerminal.module.css';

interface BillItem {
  id: string;
  dish_name: string;
  price: number;
  quantity: number;
}

interface Bill {
  id: string;
  table_name: string;
  items_count: number;
  subtotal: number;
  status: string;
  created_at: string;
  items?: BillItem[];
}

interface DishOption {
  id: string;
  name: string;
  price: number;
}

const STORE_ID = localStorage.getItem('store_id') || '';

const DISCOUNTS: { label: string; value: number }[] = [
  { label: '9折', value: 0.9 },
  { label: '85折', value: 0.85 },
  { label: '8折', value: 0.8 },
];

const PAYMENT_METHODS = [
  { key: 'wechat', label: '微信' },
  { key: 'alipay', label: '支付宝' },
  { key: 'cash', label: '现金' },
  { key: 'bank_card', label: '银行卡' },
  { key: 'member_card', label: '会员卡' },
];

export default function PosTerminal() {
  const [bills, setBills] = useState<Bill[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeBill, setActiveBill] = useState<Bill | null>(null);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [searchResults, setSearchResults] = useState<DishOption[]>([]);
  const [addQty, setAddQty] = useState(1);
  const [discount, setDiscount] = useState<number | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<string>('wechat');
  const [submitting, setSubmitting] = useState(false);

  /* 加载账单列表 */
  const loadBills = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/pos-terminal/bills?store_id=${STORE_ID}`);
      setBills(resp.bills ?? []);
    } catch {
      message.error('加载账单失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadBills(); }, [loadBills]);

  /* 开台 */
  const handleOpenTable = async () => {
    try {
      const resp = await apiClient.post('/api/v1/pos-terminal/bills', { store_id: STORE_ID });
      message.success('开台成功');
      if (resp.bill) {
        setBills(prev => [resp.bill, ...prev]);
      } else {
        loadBills();
      }
    } catch {
      message.error('开台失败');
    }
  };

  /* 打开账单详情 */
  const openBillDetail = async (bill: Bill) => {
    try {
      const resp = await apiClient.get(`/api/v1/pos-terminal/bills/${bill.id}`);
      setActiveBill(resp.bill ?? { ...bill, items: [] });
      setDiscount(null);
      setPaymentMethod('wechat');
    } catch {
      message.error('加载账单详情失败');
    }
  };

  /* 搜索菜品 */
  const handleSearch = async () => {
    if (!searchKeyword.trim()) return;
    try {
      const resp = await apiClient.get(
        `/api/v1/pos-terminal/dishes?store_id=${STORE_ID}&keyword=${encodeURIComponent(searchKeyword)}`
      );
      setSearchResults(resp.dishes ?? []);
    } catch {
      message.error('搜索菜品失败');
    }
  };

  /* 添加菜品到账单 */
  const handleAddItem = async (dish: DishOption) => {
    if (!activeBill) return;
    try {
      const resp = await apiClient.post(`/api/v1/pos-terminal/bills/${activeBill.id}/items`, {
        dish_id: dish.id,
        quantity: addQty,
      });
      setActiveBill(resp.bill ?? activeBill);
      setSearchKeyword('');
      setSearchResults([]);
      setAddQty(1);
      message.success('已添加');
    } catch {
      message.error('添加失败');
    }
  };

  /* 删除菜品 */
  const handleRemoveItem = async (itemId: string) => {
    if (!activeBill) return;
    try {
      const resp = await apiClient.delete(`/api/v1/pos-terminal/bills/${activeBill.id}/items/${itemId}`);
      setActiveBill(resp.bill ?? activeBill);
    } catch {
      message.error('删除失败');
    }
  };

  /* 结算 */
  const handleSettle = async () => {
    if (!activeBill) return;
    setSubmitting(true);
    try {
      await apiClient.post(`/api/v1/pos-terminal/bills/${activeBill.id}/settle`, {
        payment_method: paymentMethod,
        discount: discount,
      });
      message.success('结算成功');
      setActiveBill(null);
      loadBills();
    } catch {
      message.error('结算失败');
    } finally {
      setSubmitting(false);
    }
  };

  /* 计算小计 */
  const rawTotal = activeBill?.items?.reduce((sum, item) => sum + item.price * item.quantity, 0) ?? 0;
  const finalTotal = discount ? rawTotal * discount : rawTotal;

  const yuan = (v: number) => `¥${v.toFixed(2)}`;

  /* 账单详情视图 */
  if (activeBill) {
    return (
      <div className={styles.detailOverlay}>
        <div className={styles.detailHeader}>
          <button className={styles.backBtn} onClick={() => { setActiveBill(null); loadBills(); }}>
            {'<'}
          </button>
          <span className={styles.detailTitle}>{activeBill.table_name || '账单详情'}</span>
        </div>

        {/* 搜索添加菜品 */}
        <div className={styles.searchBox}>
          <input
            className={styles.searchInput}
            placeholder="搜索菜品名称"
            value={searchKeyword}
            onChange={e => setSearchKeyword(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
          />
          <button className={styles.searchBtn} onClick={handleSearch}>搜索</button>
        </div>

        {searchResults.length > 0 && (
          <div className={styles.searchResults}>
            {searchResults.map(dish => (
              <div key={dish.id} className={styles.searchItem}>
                <div className={styles.searchItemInfo}>
                  <div className={styles.searchItemName}>{dish.name}</div>
                  <div className={styles.searchItemPrice}>{yuan(dish.price)}</div>
                </div>
                <div className={styles.qtyControl}>
                  <button className={styles.qtyBtn} onClick={() => setAddQty(Math.max(1, addQty - 1))}>-</button>
                  <span className={styles.qtyValue}>{addQty}</span>
                  <button className={styles.qtyBtn} onClick={() => setAddQty(addQty + 1)}>+</button>
                </div>
                <button className={styles.addItemBtn} onClick={() => handleAddItem(dish)}>加入</button>
              </div>
            ))}
          </div>
        )}

        {/* 已点菜品 */}
        <div className={styles.sectionTitle}>已点菜品</div>
        {(!activeBill.items || activeBill.items.length === 0) ? (
          <div className={styles.emptyWrap}>
            <ZEmpty title="暂无菜品" description="请搜索并添加菜品" />
          </div>
        ) : (
          <div className={styles.itemsList}>
            {activeBill.items.map(item => (
              <div key={item.id} className={styles.itemRow}>
                <span className={styles.itemName}>{item.dish_name}</span>
                <span className={styles.itemQty}>x{item.quantity}</span>
                <span className={styles.itemPrice}>{yuan(item.price * item.quantity)}</span>
                <button className={styles.removeBtn} onClick={() => handleRemoveItem(item.id)}>x</button>
              </div>
            ))}
          </div>
        )}

        {/* 折扣 */}
        <div className={styles.sectionTitle}>折扣</div>
        <div className={styles.discountRow}>
          <button
            className={`${styles.discountBtn} ${discount === null ? styles.discountActive : ''}`}
            onClick={() => setDiscount(null)}
          >
            无折扣
          </button>
          {DISCOUNTS.map(d => (
            <button
              key={d.value}
              className={`${styles.discountBtn} ${discount === d.value ? styles.discountActive : ''}`}
              onClick={() => setDiscount(d.value)}
            >
              {d.label}
            </button>
          ))}
        </div>

        {/* 小计 */}
        <div className={styles.subtotalRow}>
          <span className={styles.subtotalLabel}>
            应付金额{discount ? `（${DISCOUNTS.find(d => d.value === discount)?.label}）` : ''}
          </span>
          <span className={styles.subtotalValue}>{yuan(finalTotal)}</span>
        </div>

        {/* 支付方式 */}
        <div className={styles.paymentSection}>
          <div className={styles.sectionTitle}>支付方式</div>
          <div className={styles.paymentGrid}>
            {PAYMENT_METHODS.map(pm => (
              <button
                key={pm.key}
                className={`${styles.paymentBtn} ${paymentMethod === pm.key ? styles.paymentActive : ''}`}
                onClick={() => setPaymentMethod(pm.key)}
              >
                {pm.label}
              </button>
            ))}
          </div>
        </div>

        {/* 底部结算栏 */}
        <div className={styles.bottomBar}>
          <button
            className={styles.settleBtn}
            onClick={handleSettle}
            disabled={submitting || !activeBill.items?.length}
          >
            {submitting ? '结算中...' : `结算 ${yuan(finalTotal)}`}
          </button>
        </div>
      </div>
    );
  }

  /* 账单列表视图 */
  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <span className={styles.title}>收银台</span>
        <div className={styles.headerRight}>
          <button className={styles.openTableBtn} onClick={handleOpenTable}>开台</button>
        </div>
      </div>

      {loading ? (
        <div className={styles.skeleton} />
      ) : bills.length === 0 ? (
        <div className={styles.emptyWrap}>
          <ZEmpty title="暂无账单" description="点击右上角「开台」开始收银" />
        </div>
      ) : (
        <div className={styles.billList}>
          {bills.map(bill => (
            <div key={bill.id} className={styles.billCard} onClick={() => openBillDetail(bill)}>
              <div className={styles.billCardHeader}>
                <span className={styles.tableName}>{bill.table_name}</span>
                <span className={styles.billTime}>{bill.created_at}</span>
              </div>
              <div className={styles.billCardBody}>
                <span className={styles.billMeta}>{bill.items_count}道菜</span>
                <span className={styles.billAmount}>{yuan(bill.subtotal)}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className={styles.bottomBar}>
        <ZButton variant="ghost" size="sm" onClick={loadBills}>刷新列表</ZButton>
      </div>
    </div>
  );
}
