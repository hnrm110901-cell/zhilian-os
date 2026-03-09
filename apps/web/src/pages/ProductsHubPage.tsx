/**
 * 商品与供应链中心 — /products-hub
 *
 * 把菜品、库存、损耗、采购整成一条线，一页总览供应链健康状态。
 *
 * 数据来源：
 *   GET /api/v1/bff/sm/{store_id}          → 食材成本率
 *   GET /api/v1/inventory-stats?store_id=  → 库存状态分布 + 告警品
 *   GET /api/v1/waste/top5?store_id=       → Top5 损耗食材 + ¥
 *   GET /api/v1/waste/summary?store_id=    → 损耗率汇总
 *   GET /api/v1/daily-hub/{store_id}       → 待采购清单
 */
import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ReloadOutlined, WarningOutlined, ShoppingOutlined, FireOutlined,
  InboxOutlined, DollarOutlined, ArrowRightOutlined, BulbOutlined,
  CheckCircleOutlined, ShoppingCartOutlined, ExperimentOutlined,
  FileExcelOutlined, BarChartOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';
import { ZCard, ZBadge, ZButton, ZSkeleton, ZSelect, DetailDrawer } from '../design-system/components';
import styles from './ProductsHubPage.module.css';

// ── Types ──────────────────────────────────────────────────────────────────────

interface FoodCost {
  actual_cost_pct:  number;
  target_pct:       number;
  variance_pct:     number;
  variance_status:  'ok' | 'warning' | 'critical';
}

interface InvStats {
  total_items: number;
  total_value: number;   // 分
  status_distribution: { normal: number; low: number; critical: number; out_of_stock: number };
  alert_items: InvAlertItem[];
}

interface InvAlertItem {
  id: string; name: string; status: string;
  current_quantity: number; min_quantity: number; unit: string;
}

interface WasteItem {
  ingredient_name: string;
  total_waste_yuan: number;
  waste_rate_pct?:  number;
  cause?:           string;
}

interface WasteSummary {
  waste_rate_pct?: number;
  total_waste_yuan?: number;
  mom_change_pct?: number;   // month-over-month
}

interface PurchaseItem {
  item_name:             string;
  current_stock?:        number;
  recommended_quantity?: number;
  alert_level?:          string;
  supplier_name?:        string;
  unit?:                 string;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function costColor(status: FoodCost['variance_status'] | null): string {
  if (status === 'critical') return '#f5222d';
  if (status === 'warning')  return '#fa8c16';
  return '#52c41a';
}

function invStatusColor(status: string): string {
  if (status === 'out_of_stock') return '#f5222d';
  if (status === 'critical')     return '#fa8c16';
  if (status === 'low')          return '#faad14';
  return '#52c41a';
}

function invStatusLabel(status: string): string {
  return { out_of_stock: '已断货', critical: '即将断货', low: '库存偏低', normal: '正常' }[status] ?? status;
}

function invStatusBadgeType(status: string): 'critical' | 'warning' | 'default' {
  if (status === 'out_of_stock' || status === 'critical') return 'critical';
  if (status === 'low') return 'warning';
  return 'default';
}

function wasteRankColor(i: number): string {
  return ['#f5222d', '#fa8c16', '#faad14', '#1890ff', '#52c41a'][i] ?? '#8c8c8c';
}

// ── Component ──────────────────────────────────────────────────────────────────

const ProductsHubPage: React.FC = () => {
  const navigate = useNavigate();

  const [stores,        setStores]        = useState<any[]>([]);
  const [selectedStore, setSelectedStore] = useState(localStorage.getItem('store_id') || 'S001');

  const [bffLoading,   setBffLoading]   = useState(true);
  const [foodCost,     setFoodCost]     = useState<FoodCost | null>(null);

  const [invLoading,   setInvLoading]   = useState(true);
  const [invStats,     setInvStats]     = useState<InvStats | null>(null);

  const [wasteLoading, setWasteLoading] = useState(true);
  const [wasteTop5,    setWasteTop5]    = useState<WasteItem[]>([]);
  const [wasteSummary, setWasteSummary] = useState<WasteSummary | null>(null);

  const [boardLoading, setBoardLoading] = useState(true);
  const [purchaseList, setPurchaseList] = useState<PurchaseItem[]>([]);

  const [selectedAlert, setSelectedAlert] = useState<InvAlertItem | null>(null);

  // ── Loaders ──────────────────────────────────────────────────────────────────

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.data?.stores || res.data || []);
    } catch { /* silent */ }
  }, []);

  const loadBff = useCallback(async () => {
    setBffLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/bff/sm/${selectedStore}`);
      setFoodCost(res.data?.food_cost_summary ?? null);
    } catch {
      setFoodCost(null);
    } finally {
      setBffLoading(false);
    }
  }, [selectedStore]);

  const loadInv = useCallback(async () => {
    setInvLoading(true);
    try {
      const res = await apiClient.get('/api/v1/inventory-stats', { params: { store_id: selectedStore } });
      setInvStats(res.data);
    } catch {
      setInvStats(null);
    } finally {
      setInvLoading(false);
    }
  }, [selectedStore]);

  const loadWaste = useCallback(async () => {
    setWasteLoading(true);
    try {
      const [t5, sum] = await Promise.all([
        apiClient.get('/api/v1/waste/top5',   { params: { store_id: selectedStore } }),
        apiClient.get('/api/v1/waste/summary', { params: { store_id: selectedStore } }),
      ]);
      setWasteTop5(t5.data?.top5 ?? t5.data ?? []);
      setWasteSummary(sum.data ?? null);
    } catch {
      setWasteTop5([]);
      setWasteSummary(null);
    } finally {
      setWasteLoading(false);
    }
  }, [selectedStore]);

  const loadBoard = useCallback(async () => {
    setBoardLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/daily-hub/${selectedStore}`);
      setPurchaseList(res.data?.purchase_order ?? []);
    } catch {
      setPurchaseList([]);
    } finally {
      setBoardLoading(false);
    }
  }, [selectedStore]);

  const refresh = useCallback(() => {
    loadBff(); loadInv(); loadWaste(); loadBoard();
  }, [loadBff, loadInv, loadWaste, loadBoard]);

  useEffect(() => { loadStores(); }, [loadStores]);
  useEffect(() => { refresh(); }, [refresh]);

  // ── Derived values ────────────────────────────────────────────────────────────

  const alertCount    = invStats?.alert_items?.length ?? 0;
  const totalItems    = invStats?.total_items ?? 0;
  const totalValueYuan = (invStats?.total_value ?? 0) / 100;
  const statusDist    = invStats?.status_distribution ?? { normal: 0, low: 0, critical: 0, out_of_stock: 0 };

  const maxWasteYuan  = Math.max(1, ...wasteTop5.map(w => w.total_waste_yuan));
  const totalWasteYuan = wasteSummary?.total_waste_yuan
    ?? wasteTop5.reduce((s, w) => s + w.total_waste_yuan, 0);

  // KPI strip items
  const kpiItems = [
    {
      label: '库存品类',
      value: totalItems || '—', unit: '种',
      iconBg: '#e6f7ff', iconColor: '#1890ff', icon: <InboxOutlined />,
    },
    {
      label: '库存预警',
      value: alertCount || 0, unit: '项',
      iconBg: alertCount > 0 ? '#fff1f0' : '#f6ffed',
      iconColor: alertCount > 0 ? '#f5222d' : '#52c41a',
      icon: <WarningOutlined />,
    },
    {
      label: '食材成本率',
      value: foodCost ? foodCost.actual_cost_pct.toFixed(1) : '—', unit: '%',
      iconBg: foodCost?.variance_status === 'critical' ? '#fff1f0'
            : foodCost?.variance_status === 'warning'  ? '#fff7e6' : '#f6ffed',
      iconColor: costColor(foodCost?.variance_status ?? null),
      icon: <DollarOutlined />,
    },
    {
      label: '本周损耗',
      value: totalWasteYuan > 0 ? `¥${Math.round(totalWasteYuan / 100).toLocaleString()}` : '—',
      unit: '',
      iconBg: '#fff7e6', iconColor: '#fa8c16', icon: <FireOutlined />,
    },
    {
      label: '待采购',
      value: purchaseList.length || 0, unit: '项',
      iconBg: purchaseList.length > 0 ? '#fff7e6' : '#f6ffed',
      iconColor: purchaseList.length > 0 ? '#fa8c16' : '#52c41a',
      icon: <ShoppingCartOutlined />,
    },
  ];

  // ── Quick nav items (all 11 nav-products pages) ────────────────────────────────

  const quickNavItems = [
    { icon: '🍽',  label: '菜品管理',    route: '/dishes' },
    { icon: '📋',  label: 'BOM配方',    route: '/bom-management' },
    { icon: '📦',  label: '库存管理',    route: '/inventory' },
    { icon: '🛒',  label: '订单协同',    route: '/order' },
    { icon: '🔥',  label: '损耗分析',    route: '/waste-reasoning' },
    { icon: '📊',  label: '损耗事件',    route: '/waste-events' },
    { icon: '💰',  label: '菜品成本',    route: '/dish-cost' },
    { icon: '🔔',  label: '告警阈值',    route: '/alert-thresholds' },
    { icon: '🚚',  label: '供应链管理',  route: '/supply-chain' },
    { icon: '📁',  label: '对账管理',    route: '/reconciliation' },
    { icon: '💲',  label: '动态定价',    route: '/dynamic-pricing' },
  ];

  const loading = bffLoading || invLoading || wasteLoading || boardLoading;

  const storeOptions = stores.length > 0
    ? stores.map((s: any) => ({ value: s.store_id || s.id, label: s.name || s.store_id || s.id }))
    : [{ value: 'S001', label: 'S001 示例门店' }];

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className={styles.pageHeader}>
        <div className={styles.pageHeaderLeft}>
          <h4 className={styles.pageTitle}>商品与供应链中心</h4>
          <span className={styles.pageSub}>
            {new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' })}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <ZSelect
            value={selectedStore}
            onChange={(v) => setSelectedStore(v as string)}
            style={{ width: 160 }}
            options={storeOptions}
          />
          <ZButton icon={<ReloadOutlined />} onClick={refresh} loading={loading}>刷新</ZButton>
        </div>
      </div>

      {loading ? (
        <ZSkeleton rows={8} block />
      ) : (
        <>
          {/* ── KPI strip ──────────────────────────────────────────────────────── */}
          <div className={styles.kpiStrip}>
            {kpiItems.map((item, idx) => (
              <div key={idx} className={styles.kpiItem}>
                <div className={styles.kpiIconWrap} style={{ background: item.iconBg, color: item.iconColor }}>
                  {item.icon}
                </div>
                <div className={styles.kpiBody}>
                  <div className={styles.kpiLabel}>{item.label}</div>
                  <div className={styles.kpiValue} style={{ color: item.iconColor }}>
                    {item.value}<span className={styles.kpiUnit}>{item.unit}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* ── 3-col main ─────────────────────────────────────────────────────── */}
          <div className={styles.mainGrid}>

            {/* ── 库存状态 ────────────────────────────────────────────────────── */}
            <ZCard
              title={<div style={{ display:'flex', alignItems:'center', gap:6 }}><InboxOutlined style={{ color: '#1890ff' }} /><span>库存状态</span></div>}
              extra={
                <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                  {totalValueYuan > 0 && (
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                      总值 ¥{totalValueYuan.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}
                    </span>
                  )}
                  <ZButton variant="ghost" size="sm" onClick={() => navigate('/inventory')}>
                    库存管理 <ArrowRightOutlined />
                  </ZButton>
                </div>
              }
            >
              {/* Status distribution */}
              <div style={{ marginBottom: 10 }}>
                {[
                  { key: 'out_of_stock', label: '已断货', count: statusDist.out_of_stock, color: '#f5222d' },
                  { key: 'critical',     label: '即将断货', count: statusDist.critical,   color: '#fa8c16' },
                  { key: 'low',          label: '库存偏低', count: statusDist.low,         color: '#faad14' },
                  { key: 'normal',       label: '正常',    count: statusDist.normal,       color: '#52c41a' },
                ].map(row => (
                  <div key={row.key} className={styles.statusRow}>
                    <div className={styles.statusDot} style={{ background: row.color }} />
                    <span className={styles.statusLabel}>{row.label}</span>
                    <span className={styles.statusCount} style={{ color: row.count > 0 && row.key !== 'normal' ? row.color : 'var(--text-primary)' }}>
                      {row.count}
                    </span>
                    <ZBadge
                      type={row.key !== 'normal' && row.count > 0 ? 'critical' : 'default'}
                      text={row.count > 0 ? '项' : '—'}
                    />
                  </div>
                ))}
              </div>

              {/* Top alert items */}
              {invStats?.alert_items && invStats.alert_items.length > 0 && (
                <>
                  <div style={{ borderTop: '1px solid var(--border)', margin: '8px 0' }} />
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6 }}>预警品项（Top 5）</div>
                  <div className={styles.alertItems}>
                    {invStats.alert_items.slice(0, 5).map(item => {
                      const color = invStatusColor(item.status);
                      const bg    = item.status === 'out_of_stock' ? '#fff1f0'
                                  : item.status === 'critical'     ? '#fff7e6'
                                  : '#fffbe6';
                      return (
                        <div key={item.id} className={styles.alertRow}
                          style={{ background: bg, borderLeftColor: color, cursor: 'pointer' }}
                          onClick={() => setSelectedAlert(item)}>
                          <span className={styles.alertItemName}>{item.name}</span>
                          <ZBadge
                            type={invStatusBadgeType(item.status)}
                            text={invStatusLabel(item.status)}
                          />
                          <span className={styles.alertItemQty}>
                            {item.current_quantity}{item.unit}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </>
              )}

              {(!invStats || invStats.alert_items?.length === 0) && (
                <div style={{ textAlign: 'center', padding: '12px 0', color: 'var(--text-secondary)', fontSize: 13 }}>
                  <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 6 }} />
                  库存状态正常
                </div>
              )}
            </ZCard>

            {/* ── 损耗 Top5 ───────────────────────────────────────────────────── */}
            <ZCard
              title={<div style={{ display:'flex', alignItems:'center', gap:6 }}><FireOutlined style={{ color: '#fa8c16' }} /><span>本周损耗 Top5</span></div>}
              extra={
                <ZButton variant="ghost" size="sm" onClick={() => navigate('/waste-reasoning')}>
                  损耗分析 <ArrowRightOutlined />
                </ZButton>
              }
            >
              {/* Summary row */}
              {wasteSummary && (
                <>
                  <div className={styles.wasteSummaryRow}>
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>本周总损耗</span>
                    <strong style={{ fontSize: 15, color: '#fa8c16' }}>
                      ¥{totalWasteYuan > 0 ? Math.round(totalWasteYuan / 100).toLocaleString() : '—'}
                    </strong>
                  </div>
                  {wasteSummary.waste_rate_pct != null && (
                    <div className={styles.wasteSummaryRow}>
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>损耗率</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <strong style={{ fontSize: 13, color: (wasteSummary.waste_rate_pct ?? 0) > 5 ? '#f5222d' : '#52c41a' }}>
                          {wasteSummary.waste_rate_pct.toFixed(1)}%
                        </strong>
                        {wasteSummary.mom_change_pct != null && (
                          <ZBadge
                            type={(wasteSummary.mom_change_pct ?? 0) > 0 ? 'critical' : 'success'}
                            text={`${wasteSummary.mom_change_pct > 0 ? '+' : ''}${wasteSummary.mom_change_pct.toFixed(1)}%`}
                          />
                        )}
                      </div>
                    </div>
                  )}
                  <div style={{ borderTop: '1px solid var(--border)', margin: '8px 0' }} />
                </>
              )}

              {/* Top 5 waste items */}
              {wasteTop5.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-secondary)', fontSize: 13 }}>
                  <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 6 }} />
                  本周暂无损耗记录
                </div>
              ) : (
                <div className={styles.wasteItems}>
                  {wasteTop5.map((item, i) => (
                    <div key={i} className={styles.wasteRow}>
                      <div className={styles.wasteRank} style={{ background: wasteRankColor(i) }}>
                        {i + 1}
                      </div>
                      <span className={styles.wasteName} title={item.cause || item.ingredient_name}>
                        {item.ingredient_name}
                      </span>
                      <div className={styles.wasteBarTrack}>
                        <div
                          className={styles.wasteBarFill}
                          style={{
                            width: `${(item.total_waste_yuan / maxWasteYuan) * 100}%`,
                            background: wasteRankColor(i),
                          }}
                        />
                      </div>
                      <span className={styles.wasteAmount} style={{ color: wasteRankColor(i) }}>
                        ¥{(item.total_waste_yuan / 100).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </ZCard>

            {/* ── 采购建议 ────────────────────────────────────────────────────── */}
            <ZCard
              title={<div style={{ display:'flex', alignItems:'center', gap:6 }}><ShoppingCartOutlined style={{ color: '#52c41a' }} /><span>待采购清单</span></div>}
              extra={
                <ZButton variant="ghost" size="sm" onClick={() => navigate('/inventory')}>
                  采购管理 <ArrowRightOutlined />
                </ZButton>
              }
            >
              {purchaseList.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-secondary)', fontSize: 13 }}>
                  <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 6 }} />
                  暂无待采购项目
                </div>
              ) : (
                <div className={styles.purchaseItems}>
                  {purchaseList.slice(0, 6).map((item, i) => (
                    <div key={i} className={styles.purchaseRow}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div className={styles.purchaseName}>{item.item_name}</div>
                        <div className={styles.purchaseMeta}>
                          {item.supplier_name && <span>{item.supplier_name}</span>}
                          {item.current_stock != null && (
                            <span>现存 {item.current_stock}{item.unit}</span>
                          )}
                        </div>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 3 }}>
                        {item.recommended_quantity != null && (
                          <strong style={{ fontSize: 13, color: 'var(--text-primary)' }}>
                            +{item.recommended_quantity}{item.unit}
                          </strong>
                        )}
                        {item.alert_level && (
                          <ZBadge
                            type={item.alert_level === 'critical' ? 'critical' : 'warning'}
                            text={item.alert_level === 'critical' ? '紧急' : item.alert_level === 'urgent' ? '较急' : '建议'}
                          />
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {purchaseList.length > 6 && (
                <ZButton
                  variant="secondary"
                  onClick={() => navigate('/inventory')}
                  style={{ marginTop: 8, width: '100%' }}
                >
                  查看全部 {purchaseList.length} 项
                </ZButton>
              )}
            </ZCard>

          </div>

          {/* ── 食材成本率详情 ──────────────────────────────────────────────────── */}
          <ZCard
            title={<div style={{ display:'flex', alignItems:'center', gap:6 }}><DollarOutlined style={{ color: '#722ed1' }} /><span>食材成本率分析</span></div>}
            extra={
              <ZButton variant="ghost" size="sm" onClick={() => navigate('/profit-dashboard')}>
                成本看板 <ArrowRightOutlined />
              </ZButton>
            }
            style={{ marginBottom: 14 }}
          >
            {foodCost ? (
              <>
                <div className={styles.costRow}>
                  <div className={styles.costCell}>
                    <span className={styles.costCellValue} style={{ color: costColor(foodCost.variance_status) }}>
                      {foodCost.actual_cost_pct.toFixed(1)}%
                    </span>
                    <span className={styles.costCellLabel}>实际成本率</span>
                  </div>
                  <div className={styles.costCell}>
                    <span className={styles.costCellValue} style={{ color: '#1890ff' }}>
                      {foodCost.target_pct.toFixed(1)}%
                    </span>
                    <span className={styles.costCellLabel}>目标成本率</span>
                  </div>
                  <div className={styles.costCell}>
                    <span className={styles.costCellValue}
                      style={{ color: foodCost.variance_pct > 0 ? '#f5222d' : '#52c41a' }}>
                      {foodCost.variance_pct > 0 ? '+' : ''}{foodCost.variance_pct.toFixed(1)}%
                    </span>
                    <span className={styles.costCellLabel}>较目标偏差</span>
                  </div>
                </div>

                <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
                  <span style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                    目标 {foodCost.target_pct.toFixed(1)}%
                  </span>
                  <div style={{ flex: 1 }}>
                    <div className={styles.costBar}>
                      <div
                        className={styles.costBarFill}
                        style={{
                          width: `${Math.min(foodCost.actual_cost_pct, 60) / 60 * 100}%`,
                          background: costColor(foodCost.variance_status),
                        }}
                      />
                    </div>
                  </div>
                  <ZBadge
                    type={foodCost.variance_status === 'critical' ? 'critical' : foodCost.variance_status === 'warning' ? 'warning' : 'success'}
                    text={foodCost.variance_status === 'critical' ? '超标' : foodCost.variance_status === 'warning' ? '偏高' : '正常'}
                  />
                </div>

                {foodCost.variance_status !== 'ok' && (
                  <div style={{
                    marginTop: 10,
                    padding: '8px 12px',
                    background: foodCost.variance_status === 'critical' ? '#fff1f0' : '#fff7e6',
                    border: `1px solid ${foodCost.variance_status === 'critical' ? '#ffccc7' : '#ffd591'}`,
                    borderRadius: 6,
                    fontSize: 12,
                    color: costColor(foodCost.variance_status),
                  }}>
                    <BulbOutlined style={{ marginRight: 6 }} />
                    建议核查损耗原因并优化采购量，
                    {foodCost.variance_pct > 0 && `超标 ${foodCost.variance_pct.toFixed(1)}%，`}
                    点击"损耗分析"了解明细。
                  </div>
                )}
              </>
            ) : (
              <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-secondary)', fontSize: 13 }}>
                暂无食材成本数据
              </div>
            )}
          </ZCard>

          {/* ── 快捷导航 ────────────────────────────────────────────────────────── */}
          <ZCard
            title={<div style={{ display:'flex', alignItems:'center', gap:6 }}><ShoppingOutlined style={{ color: '#8c8c8c' }} /><span>商品与供应链功能导航</span></div>}
          >
            <div className={styles.quickNav}>
              {quickNavItems.map(item => (
                <button
                  key={item.route}
                  className={styles.quickNavItem}
                  onClick={() => navigate(item.route)}
                >
                  <span className={styles.quickNavIcon}>{item.icon}</span>
                  <span className={styles.quickNavLabel}>{item.label}</span>
                </button>
              ))}
            </div>
          </ZCard>
        </>
      )}

      {/* ── 库存预警详情侧边抽屉 ─────────────────────────────────────────────── */}
      <DetailDrawer
        open={!!selectedAlert}
        onClose={() => setSelectedAlert(null)}
        title={selectedAlert?.name ?? ''}
        subtitle="库存预警详情"
        status={selectedAlert ? {
          label: invStatusLabel(selectedAlert.status),
          type:  invStatusBadgeType(selectedAlert.status),
        } : undefined}
        metrics={selectedAlert ? [
          { label: '当前库存',   value: `${selectedAlert.current_quantity} ${selectedAlert.unit}`,
            valueColor: invStatusColor(selectedAlert.status) },
          { label: '安全库存',   value: `${selectedAlert.min_quantity} ${selectedAlert.unit}` },
          { label: '缺口',       value: `${Math.max(0, selectedAlert.min_quantity - selectedAlert.current_quantity)} ${selectedAlert.unit}`,
            valueColor: selectedAlert.current_quantity < selectedAlert.min_quantity ? '#f5222d' : '#52c41a' },
        ] : []}
        sections={selectedAlert ? [
          {
            title: '建议处置',
            content: (
              <p style={{ margin: 0, lineHeight: 1.7 }}>
                {selectedAlert.status === 'out_of_stock'
                  ? `【${selectedAlert.name}】已断货，请立即联系供应商紧急补货，避免影响今日营业。`
                  : selectedAlert.status === 'critical'
                  ? `【${selectedAlert.name}】库存极低，建议今日下班前完成采购备货。`
                  : `【${selectedAlert.name}】库存偏低，建议明日采购补充至安全库存水位以上。`}
              </p>
            ),
          },
        ] : []}
        actions={selectedAlert ? [
          {
            label:   '前往采购',
            type:    'primary',
            onClick: () => { navigate('/inventory'); setSelectedAlert(null); },
          },
          {
            label:   '关闭',
            type:    'default',
            onClick: () => setSelectedAlert(null),
          },
        ] : []}
      />
    </div>
  );
};

export default ProductsHubPage;
