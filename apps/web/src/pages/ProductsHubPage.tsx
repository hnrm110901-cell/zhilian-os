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
  Card, Select, Button, Tag, Spin, Typography, Space, Divider, Tooltip,
  Progress,
} from 'antd';
import {
  ReloadOutlined, WarningOutlined, ShoppingOutlined, FireOutlined,
  InboxOutlined, DollarOutlined, ArrowRightOutlined, BulbOutlined,
  CheckCircleOutlined, ShoppingCartOutlined, ExperimentOutlined,
  FileExcelOutlined, BarChartOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';
import styles from './ProductsHubPage.module.css';

const { Text, Title } = Typography;
const { Option } = Select;

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
  alert_items: Array<{
    id: string; name: string; status: string;
    current_quantity: number; min_quantity: number; unit: string;
  }>;
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

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className={styles.pageHeader}>
        <div className={styles.pageHeaderLeft}>
          <Title level={4} style={{ margin: 0 }}>商品与供应链中心</Title>
          <Text type="secondary" style={{ fontSize: 13 }}>
            {new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' })}
          </Text>
        </div>
        <Space>
          <Select value={selectedStore} onChange={setSelectedStore} style={{ width: 160 }}>
            {stores.length > 0
              ? stores.map((s: any) => (
                  <Option key={s.store_id || s.id} value={s.store_id || s.id}>
                    {s.name || s.store_id || s.id}
                  </Option>
                ))
              : <Option value="S001">S001 示例门店</Option>}
          </Select>
          <Button icon={<ReloadOutlined />} onClick={refresh}>刷新</Button>
        </Space>
      </div>

      <Spin spinning={loading}>

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
          <Card
            title={<Space><InboxOutlined style={{ color: '#1890ff' }} /><span>库存状态</span></Space>}
            extra={
              <Space size={6}>
                {totalValueYuan > 0 && (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    总值 ¥{totalValueYuan.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}
                  </Text>
                )}
                <Button type="link" size="small" style={{ padding: 0 }} onClick={() => navigate('/inventory')}>
                  库存管理 <ArrowRightOutlined />
                </Button>
              </Space>
            }
            bodyStyle={{ padding: '12px 16px' }}
          >
            {/* Status distribution */}
            <div style={{ marginBottom: 10 }}>
              {[
                { key: 'out_of_stock', label: '已断货', count: statusDist.out_of_stock, color: '#f5222d', bg: '#fff1f0' },
                { key: 'critical',     label: '即将断货', count: statusDist.critical,   color: '#fa8c16', bg: '#fff7e6' },
                { key: 'low',          label: '库存偏低', count: statusDist.low,         color: '#faad14', bg: '#fffbe6' },
                { key: 'normal',       label: '正常',    count: statusDist.normal,       color: '#52c41a', bg: '#f6ffed' },
              ].map(row => (
                <div key={row.key} className={styles.statusRow}>
                  <div className={styles.statusDot} style={{ background: row.color }} />
                  <span className={styles.statusLabel}>{row.label}</span>
                  <span className={styles.statusCount} style={{ color: row.count > 0 && row.key !== 'normal' ? row.color : '#262626' }}>
                    {row.count}
                  </span>
                  <Tag color={row.key !== 'normal' && row.count > 0 ? 'error' : 'default'}
                    style={{ marginLeft: 8, fontSize: 10, padding: '0 4px', lineHeight: '16px' }}>
                    {row.count > 0 ? '项' : '—'}
                  </Tag>
                </div>
              ))}
            </div>

            {/* Top alert items */}
            {invStats?.alert_items && invStats.alert_items.length > 0 && (
              <>
                <Divider style={{ margin: '8px 0' }} />
                <div style={{ fontSize: 11, color: '#8c8c8c', marginBottom: 6 }}>预警品项（Top 5）</div>
                <div className={styles.alertItems}>
                  {invStats.alert_items.slice(0, 5).map(item => {
                    const color = invStatusColor(item.status);
                    const bg    = item.status === 'out_of_stock' ? '#fff1f0'
                                : item.status === 'critical'     ? '#fff7e6'
                                : '#fffbe6';
                    return (
                      <div key={item.id} className={styles.alertRow}
                        style={{ background: bg, borderLeftColor: color }}>
                        <span className={styles.alertItemName}>{item.name}</span>
                        <Tag color={item.status === 'out_of_stock' ? 'error' : item.status === 'critical' ? 'warning' : 'gold'}
                          style={{ fontSize: 10, padding: '0 4px', lineHeight: '16px', flexShrink: 0 }}>
                          {invStatusLabel(item.status)}
                        </Tag>
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
              <div style={{ textAlign: 'center', padding: '12px 0', color: '#8c8c8c', fontSize: 13 }}>
                <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 6 }} />
                库存状态正常
              </div>
            )}
          </Card>

          {/* ── 损耗 Top5 ───────────────────────────────────────────────────── */}
          <Card
            title={<Space><FireOutlined style={{ color: '#fa8c16' }} /><span>本周损耗 Top5</span></Space>}
            extra={
              <Button type="link" size="small" style={{ padding: 0 }} onClick={() => navigate('/waste-reasoning')}>
                损耗分析 <ArrowRightOutlined />
              </Button>
            }
            bodyStyle={{ padding: '12px 16px' }}
          >
            {/* Summary row */}
            {wasteSummary && (
              <>
                <div className={styles.wasteSummaryRow}>
                  <Text type="secondary" style={{ fontSize: 12 }}>本周总损耗</Text>
                  <Text strong style={{ fontSize: 15, color: '#fa8c16' }}>
                    ¥{totalWasteYuan > 0 ? Math.round(totalWasteYuan / 100).toLocaleString() : '—'}
                  </Text>
                </div>
                {wasteSummary.waste_rate_pct != null && (
                  <div className={styles.wasteSummaryRow}>
                    <Text type="secondary" style={{ fontSize: 12 }}>损耗率</Text>
                    <Space size={6}>
                      <Text strong style={{ fontSize: 13, color: (wasteSummary.waste_rate_pct ?? 0) > 5 ? '#f5222d' : '#52c41a' }}>
                        {wasteSummary.waste_rate_pct.toFixed(1)}%
                      </Text>
                      {wasteSummary.mom_change_pct != null && (
                        <Tag color={(wasteSummary.mom_change_pct ?? 0) > 0 ? 'error' : 'success'} style={{ fontSize: 10, padding: '0 4px' }}>
                          {wasteSummary.mom_change_pct > 0 ? '+' : ''}{wasteSummary.mom_change_pct.toFixed(1)}%
                        </Tag>
                      )}
                    </Space>
                  </div>
                )}
                <Divider style={{ margin: '8px 0' }} />
              </>
            )}

            {/* Top 5 waste items */}
            {wasteTop5.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '20px 0', color: '#8c8c8c', fontSize: 13 }}>
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
                    <Tooltip title={item.cause || item.ingredient_name}>
                      <span className={styles.wasteName}>{item.ingredient_name}</span>
                    </Tooltip>
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
          </Card>

          {/* ── 采购建议 ────────────────────────────────────────────────────── */}
          <Card
            title={<Space><ShoppingCartOutlined style={{ color: '#52c41a' }} /><span>待采购清单</span></Space>}
            extra={
              <Button type="link" size="small" style={{ padding: 0 }} onClick={() => navigate('/inventory')}>
                采购管理 <ArrowRightOutlined />
              </Button>
            }
            bodyStyle={{ padding: '12px 16px' }}
          >
            {purchaseList.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '20px 0', color: '#8c8c8c', fontSize: 13 }}>
                <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 6 }} />
                暂无待采购项目
              </div>
            ) : (
              <div className={styles.purchaseItems}>
                {purchaseList.slice(0, 6).map((item, i) => {
                  const levelColor = item.alert_level === 'critical' ? '#f5222d'
                                   : item.alert_level === 'urgent'   ? '#fa8c16'
                                   : '#faad14';
                  return (
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
                          <Text strong style={{ fontSize: 13, color: '#262626' }}>
                            +{item.recommended_quantity}{item.unit}
                          </Text>
                        )}
                        {item.alert_level && (
                          <Tag color={item.alert_level === 'critical' ? 'error' : 'warning'}
                            style={{ fontSize: 10, padding: '0 4px', lineHeight: '16px', margin: 0 }}>
                            {item.alert_level === 'critical' ? '紧急' : item.alert_level === 'urgent' ? '较急' : '建议'}
                          </Tag>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {purchaseList.length > 6 && (
              <Button
                type="dashed"
                block
                size="small"
                style={{ marginTop: 8 }}
                onClick={() => navigate('/inventory')}
              >
                查看全部 {purchaseList.length} 项
              </Button>
            )}
          </Card>

        </div>

        {/* ── 食材成本率详情 ──────────────────────────────────────────────────── */}
        <Card
          title={<Space><DollarOutlined style={{ color: '#722ed1' }} /><span>食材成本率分析</span></Space>}
          extra={
            <Button type="link" size="small" style={{ padding: 0 }} onClick={() => navigate('/profit-dashboard')}>
              成本看板 <ArrowRightOutlined />
            </Button>
          }
          bodyStyle={{ padding: '16px 20px' }}
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
                <Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                  目标 {foodCost.target_pct.toFixed(1)}%
                </Text>
                <div style={{ flex: 1 }}>
                  <Progress
                    percent={Math.min(foodCost.actual_cost_pct, 60)}
                    success={{ percent: Math.min(foodCost.target_pct, 60) }}
                    strokeColor={costColor(foodCost.variance_status)}
                    showInfo={false}
                    size="small"
                  />
                </div>
                <Tag
                  color={foodCost.variance_status === 'critical' ? 'error'
                       : foodCost.variance_status === 'warning'  ? 'warning' : 'success'}
                >
                  {foodCost.variance_status === 'critical' ? '超标'
                 : foodCost.variance_status === 'warning'  ? '偏高' : '正常'}
                </Tag>
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
            <div style={{ textAlign: 'center', padding: '20px 0', color: '#8c8c8c', fontSize: 13 }}>
              暂无食材成本数据
            </div>
          )}
        </Card>

        {/* ── 快捷导航 ────────────────────────────────────────────────────────── */}
        <Card
          title={<Space><ShoppingOutlined style={{ color: '#8c8c8c' }} /><span>商品与供应链功能导航</span></Space>}
          bodyStyle={{ padding: '12px 16px' }}
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
        </Card>

      </Spin>
    </div>
  );
};

export default ProductsHubPage;
