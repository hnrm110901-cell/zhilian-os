/**
 * FoodSafetyPage — /platform/food-safety
 *
 * 食品安全追溯：食材溯源记录 + 安全检查管理 + 预警中心
 * 后端 API:
 *   GET    /api/v1/food-safety/traces           — 溯源记录列表
 *   POST   /api/v1/food-safety/traces           — 新建溯源记录
 *   GET    /api/v1/food-safety/traces/:id       — 溯源详情
 *   PUT    /api/v1/food-safety/traces/:id/status — 更新状态（召回等）
 *   GET    /api/v1/food-safety/traces/expiring  — 即将过期
 *   GET    /api/v1/food-safety/inspections      — 检查记录列表
 *   POST   /api/v1/food-safety/inspections      — 新建检查
 *   GET    /api/v1/food-safety/inspections/:id  — 检查详情
 *   GET    /api/v1/food-safety/stats            — 统计概览
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Alert } from 'antd';
import {
  ZCard, ZBadge, ZButton, ZEmpty, ZSkeleton, ZModal,
} from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import { apiClient } from '../../services/api';
import styles from './FoodSafetyPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface TraceRecord {
  id: string;
  brand_id: string;
  store_id: string;
  ingredient_name: string;
  ingredient_id?: string;
  batch_number: string;
  supplier_name: string;
  supplier_id?: string;
  production_date?: string;
  expiry_date?: string;
  receive_date?: string;
  quantity: number;
  unit: string;
  origin?: string;
  certificate_url?: string;
  qr_code?: string;
  temperature_on_receive?: number;
  status: string;
  notes?: string;
  created_at?: string;
}

interface Inspection {
  id: string;
  brand_id: string;
  store_id: string;
  inspection_type: string;
  inspector_name: string;
  inspection_date?: string;
  score?: number;
  status: string;
  items: Array<{ item: string; result: string; notes?: string }>;
  photos?: string[];
  corrective_actions?: string;
  next_inspection_date?: string;
  created_at?: string;
}

interface FoodSafetyStats {
  total_trace_records: number;
  expiring_count: number;
  recalled_count: number;
  inspection_total: number;
  inspection_pass_rate: number;
  latest_inspection_date?: string;
}

interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ── 常量 ─────────────────────────────────────────────────────────────────────

const TRACE_STATUS_MAP: Record<string, { label: string; variant: 'default' | 'success' | 'warning' | 'error' }> = {
  normal:   { label: '正常',   variant: 'success' },
  warning:  { label: '预警',   variant: 'warning' },
  recalled: { label: '已召回', variant: 'error' },
  expired:  { label: '已过期', variant: 'error' },
};

const INSPECTION_STATUS_MAP: Record<string, { label: string; variant: 'default' | 'success' | 'warning' | 'error' }> = {
  passed:            { label: '通过',     variant: 'success' },
  failed:            { label: '未通过',   variant: 'error' },
  pending:           { label: '待检查',   variant: 'default' },
  needs_improvement: { label: '需整改',   variant: 'warning' },
};

const INSPECTION_TYPE_LABELS: Record<string, string> = {
  daily:       '日常检查',
  weekly:      '周检',
  monthly:     '月检',
  government:  '政府检查',
  third_party: '第三方检查',
};

type TabKey = 'traces' | 'inspections' | 'alerts';

// ── 工具函数 ─────────────────────────────────────────────────────────────────

function fmtDate(iso?: string): string {
  if (!iso) return '\u2014';
  try {
    return new Date(iso).toLocaleDateString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
    });
  } catch { return iso; }
}

function daysUntil(dateStr?: string): number | null {
  if (!dateStr) return null;
  const target = new Date(dateStr);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  target.setHours(0, 0, 0, 0);
  return Math.ceil((target.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
}

// ── 组件 ─────────────────────────────────────────────────────────────────────

const FoodSafetyPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabKey>('traces');
  const [loading, setLoading] = useState(true);

  // 统计
  const [stats, setStats] = useState<FoodSafetyStats | null>(null);

  // 溯源记录
  const [traces, setTraces] = useState<TraceRecord[]>([]);
  const [traceTotal, setTraceTotal] = useState(0);
  const [tracePage, setTracePage] = useState(1);
  const [filterStatus, setFilterStatus] = useState('');
  const [searchIngredient, setSearchIngredient] = useState('');

  // 检查记录
  const [inspections, setInspections] = useState<Inspection[]>([]);
  const [inspectionTotal, setInspectionTotal] = useState(0);
  const [inspectionPage, setInspectionPage] = useState(1);
  const [filterInspType, setFilterInspType] = useState('');

  // 预警
  const [expiringItems, setExpiringItems] = useState<TraceRecord[]>([]);

  // 弹窗
  const [showTraceModal, setShowTraceModal] = useState(false);
  const [showInspModal, setShowInspModal] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formErr, setFormErr] = useState('');

  // 溯源表单
  const [traceForm, setTraceForm] = useState({
    ingredient_name: '', batch_number: '', supplier_name: '',
    receive_date: '', expiry_date: '', production_date: '',
    quantity: '', unit: 'kg', origin: '', qr_code: '',
    temperature_on_receive: '', notes: '', store_id: '',
  });

  // 检查表单
  const [inspForm, setInspForm] = useState({
    inspection_type: 'daily', inspector_name: '', inspection_date: '',
    score: '', status: 'pending', corrective_actions: '', store_id: '',
  });

  const brandId = 'default';
  const PAGE_SIZE = 20;

  // ── 数据加载 ────────────────────────────────────────────────────────────

  const fetchStats = useCallback(async () => {
    try {
      const res = await apiClient.get<FoodSafetyStats>('/api/v1/food-safety/stats', {
        params: { brand_id: brandId },
      });
      setStats(res);
    } catch (err) {
      console.error('加载统计数据失败', err);
    }
  }, [brandId]);

  const fetchTraces = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get<PaginatedResponse<TraceRecord>>('/api/v1/food-safety/traces', {
        params: {
          brand_id: brandId,
          page: tracePage,
          page_size: PAGE_SIZE,
          status: filterStatus || undefined,
          ingredient_name: searchIngredient || undefined,
        },
      });
      setTraces(res.items);
      setTraceTotal(res.total);
    } catch (err) {
      console.error('加载溯源记录失败', err);
    } finally {
      setLoading(false);
    }
  }, [brandId, tracePage, filterStatus, searchIngredient]);

  const fetchInspections = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get<PaginatedResponse<Inspection>>('/api/v1/food-safety/inspections', {
        params: {
          brand_id: brandId,
          page: inspectionPage,
          page_size: PAGE_SIZE,
          inspection_type: filterInspType || undefined,
        },
      });
      setInspections(res.items);
      setInspectionTotal(res.total);
    } catch (err) {
      console.error('加载检查记录失败', err);
    } finally {
      setLoading(false);
    }
  }, [brandId, inspectionPage, filterInspType]);

  const fetchExpiring = useCallback(async () => {
    try {
      const res = await apiClient.get<{ items: TraceRecord[] }>('/api/v1/food-safety/traces/expiring', {
        params: { brand_id: brandId, days_ahead: 14 },
      });
      setExpiringItems(res.items);
    } catch (err) {
      console.error('加载预警数据失败', err);
    }
  }, [brandId]);

  useEffect(() => { fetchStats(); }, [fetchStats]);

  useEffect(() => {
    if (activeTab === 'traces') fetchTraces();
    else if (activeTab === 'inspections') fetchInspections();
    else if (activeTab === 'alerts') fetchExpiring();
  }, [activeTab, fetchTraces, fetchInspections, fetchExpiring]);

  // ── 操作 ────────────────────────────────────────────────────────────────

  const handleRecall = async (id: string) => {
    try {
      await apiClient.put(`/api/v1/food-safety/traces/${id}/status`, {
        status: 'recalled', notes: '手动召回',
      });
      fetchTraces();
      fetchStats();
    } catch (err) {
      console.error('召回失败', err);
    }
  };

  // ── 新建溯源 ──────────────────────────────────────────────────────────

  const resetTraceForm = () => {
    setTraceForm({
      ingredient_name: '', batch_number: '', supplier_name: '',
      receive_date: '', expiry_date: '', production_date: '',
      quantity: '', unit: 'kg', origin: '', qr_code: '',
      temperature_on_receive: '', notes: '', store_id: '',
    });
    setFormErr('');
  };

  const handleCreateTrace = async () => {
    const f = traceForm;
    if (!f.ingredient_name.trim() || !f.batch_number.trim() || !f.supplier_name.trim() || !f.receive_date) {
      setFormErr('请填写必填字段：食材名称、批次号、供应商、收货日期');
      return;
    }
    if (!f.quantity || isNaN(parseFloat(f.quantity)) || parseFloat(f.quantity) <= 0) {
      setFormErr('数量格式不正确');
      return;
    }

    setSubmitting(true);
    setFormErr('');
    try {
      await apiClient.post('/api/v1/food-safety/traces', {
        brand_id: brandId,
        store_id: f.store_id || 'default',
        ingredient_name: f.ingredient_name.trim(),
        batch_number: f.batch_number.trim(),
        supplier_name: f.supplier_name.trim(),
        receive_date: f.receive_date,
        expiry_date: f.expiry_date || undefined,
        production_date: f.production_date || undefined,
        quantity: parseFloat(f.quantity),
        unit: f.unit,
        origin: f.origin.trim() || undefined,
        qr_code: f.qr_code.trim() || undefined,
        temperature_on_receive: f.temperature_on_receive ? parseFloat(f.temperature_on_receive) : undefined,
        notes: f.notes.trim() || undefined,
      });
      setShowTraceModal(false);
      resetTraceForm();
      fetchTraces();
      fetchStats();
    } catch (err: any) {
      setFormErr(err?.message || '创建失败');
    } finally {
      setSubmitting(false);
    }
  };

  // ── 新建检查 ──────────────────────────────────────────────────────────

  const resetInspForm = () => {
    setInspForm({
      inspection_type: 'daily', inspector_name: '', inspection_date: '',
      score: '', status: 'pending', corrective_actions: '', store_id: '',
    });
    setFormErr('');
  };

  const handleCreateInspection = async () => {
    const f = inspForm;
    if (!f.inspector_name.trim() || !f.inspection_date) {
      setFormErr('请填写必填字段：检查人、检查日期');
      return;
    }

    setSubmitting(true);
    setFormErr('');
    try {
      await apiClient.post('/api/v1/food-safety/inspections', {
        brand_id: brandId,
        store_id: f.store_id || 'default',
        inspection_type: f.inspection_type,
        inspector_name: f.inspector_name.trim(),
        inspection_date: f.inspection_date,
        score: f.score ? parseInt(f.score, 10) : undefined,
        status: f.status,
        corrective_actions: f.corrective_actions.trim() || undefined,
        items: [],
      });
      setShowInspModal(false);
      resetInspForm();
      fetchInspections();
      fetchStats();
    } catch (err: any) {
      setFormErr(err?.message || '创建失败');
    } finally {
      setSubmitting(false);
    }
  };

  // ── 表格列定义 ─────────────────────────────────────────────────────────

  const traceColumns: ZTableColumn<TraceRecord>[] = [
    {
      key: 'ingredient_name',
      title: '食材名称',
      dataIndex: 'ingredient_name',
      render: (_v: any, row: TraceRecord) => (
        <span style={{ fontWeight: 600 }}>{row.ingredient_name}</span>
      ),
    },
    { key: 'batch_number', title: '批次号', dataIndex: 'batch_number' },
    { key: 'supplier_name', title: '供应商', dataIndex: 'supplier_name' },
    {
      key: 'receive_date', title: '收货日期', dataIndex: 'receive_date',
      render: (v: any) => <span className={styles.timeCell}>{fmtDate(v)}</span>,
    },
    {
      key: 'expiry_date', title: '保质期至', dataIndex: 'expiry_date',
      render: (v: any) => {
        const days = daysUntil(v);
        const isUrgent = days !== null && days <= 3;
        return (
          <span className={styles.timeCell} style={isUrgent ? { color: '#ef4444', fontWeight: 700 } : undefined}>
            {fmtDate(v)}
            {days !== null && days >= 0 ? ` (${days}天)` : ''}
          </span>
        );
      },
    },
    { key: 'origin', title: '产地', dataIndex: 'origin', render: (v: any) => v || '\u2014' },
    {
      key: 'status', title: '状态', dataIndex: 'status',
      render: (v: any) => {
        const s = TRACE_STATUS_MAP[v] || { label: v, variant: 'default' as const };
        return <ZBadge type={s.variant} text={s.label} />;
      },
    },
    {
      key: 'actions', title: '',
      render: (_v: any, row: TraceRecord) => (
        <div className={styles.actionGroup}>
          {row.status === 'normal' && (
            <ZButton size="sm" variant="ghost" onClick={() => handleRecall(row.id)}>
              召回
            </ZButton>
          )}
        </div>
      ),
    },
  ];

  const inspectionColumns: ZTableColumn<Inspection>[] = [
    {
      key: 'inspection_date', title: '检查日期', dataIndex: 'inspection_date',
      render: (v: any) => <span className={styles.timeCell}>{fmtDate(v)}</span>,
    },
    {
      key: 'inspection_type', title: '类型', dataIndex: 'inspection_type',
      render: (v: any) => INSPECTION_TYPE_LABELS[v] || v,
    },
    { key: 'inspector_name', title: '检查人', dataIndex: 'inspector_name' },
    {
      key: 'score', title: '评分', dataIndex: 'score',
      render: (v: any) => {
        if (v == null) return '\u2014';
        const color = v >= 90 ? '#22c55e' : v >= 70 ? 'var(--accent, #FF6B2C)' : '#ef4444';
        return <span style={{ fontWeight: 700, color }}>{v}</span>;
      },
    },
    {
      key: 'status', title: '结果', dataIndex: 'status',
      render: (v: any) => {
        const s = INSPECTION_STATUS_MAP[v] || { label: v, variant: 'default' as const };
        return <ZBadge type={s.variant} text={s.label} />;
      },
    },
    {
      key: 'corrective_actions', title: '整改措施', dataIndex: 'corrective_actions',
      render: (v: any) => v ? <span style={{ fontSize: 12 }}>{v}</span> : '\u2014',
    },
  ];

  // ── 渲染 ────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>食品安全追溯</h1>
          <p className={styles.pageSubtitle}>食材溯源 / 安全检查 / 预警监控</p>
        </div>
        <div className={styles.headerActions}>
          {activeTab === 'traces' && (
            <ZButton variant="primary" onClick={() => { resetTraceForm(); setShowTraceModal(true); }}>
              录入溯源
            </ZButton>
          )}
          {activeTab === 'inspections' && (
            <ZButton variant="primary" onClick={() => { resetInspForm(); setShowInspModal(true); }}>
              新建检查
            </ZButton>
          )}
        </div>
      </div>

      {/* 统计行 */}
      <div className={styles.statsRow}>
        <ZCard className={styles.statCard}>
          <div className={`${styles.statNum} ${styles.statBlue}`}>{stats?.total_trace_records ?? '-'}</div>
          <div className={styles.statLabel}>溯源记录</div>
        </ZCard>
        <ZCard className={styles.statCard}>
          <div className={`${styles.statNum} ${styles.statOrange}`}>{stats?.expiring_count ?? '-'}</div>
          <div className={styles.statLabel}>即将过期</div>
        </ZCard>
        <ZCard className={styles.statCard}>
          <div className={`${styles.statNum} ${styles.statRed}`}>{stats?.recalled_count ?? '-'}</div>
          <div className={styles.statLabel}>已召回</div>
        </ZCard>
        <ZCard className={styles.statCard}>
          <div className={`${styles.statNum} ${styles.statGreen}`}>
            {stats ? `${stats.inspection_pass_rate}%` : '-'}
          </div>
          <div className={styles.statLabel}>检查通过率</div>
        </ZCard>
      </div>

      {/* Tab 栏 */}
      <div className={styles.tabBar}>
        {([
          ['traces', '食材溯源'],
          ['inspections', '安全检查'],
          ['alerts', '预警中心'],
        ] as [TabKey, string][]).map(([key, label]) => (
          <button
            key={key}
            className={`${styles.tabItem} ${activeTab === key ? styles.tabItemActive : ''}`}
            onClick={() => setActiveTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── Tab 1: 食材溯源 ──────────────────────────────────────────────── */}
      {activeTab === 'traces' && (
        <>
          <div className={styles.toolbar}>
            <input
              className={styles.searchInput}
              placeholder="搜索食材名称..."
              value={searchIngredient}
              onChange={e => { setSearchIngredient(e.target.value); setTracePage(1); }}
            />
            <select
              className={styles.filterSelect}
              value={filterStatus}
              onChange={e => { setFilterStatus(e.target.value); setTracePage(1); }}
            >
              <option value="">全部状态</option>
              <option value="normal">正常</option>
              <option value="warning">预警</option>
              <option value="recalled">已召回</option>
              <option value="expired">已过期</option>
            </select>
          </div>

          {loading ? (
            <ZSkeleton lines={8} />
          ) : traces.length === 0 ? (
            <ZEmpty description="暂无溯源记录" />
          ) : (
            <ZCard className={styles.tableCard}>
              <ZTable<TraceRecord>
                columns={traceColumns}
                data={traces}
                rowKey="id"
              />
            </ZCard>
          )}

          {traceTotal > PAGE_SIZE && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 12 }}>
              <ZButton
                size="sm"
                variant="ghost"
                disabled={tracePage <= 1}
                onClick={() => setTracePage(p => Math.max(1, p - 1))}
              >
                上一页
              </ZButton>
              <span style={{ lineHeight: '32px', fontSize: 13, color: 'var(--text-secondary, #6b7280)' }}>
                {tracePage} / {Math.ceil(traceTotal / PAGE_SIZE)}
              </span>
              <ZButton
                size="sm"
                variant="ghost"
                disabled={tracePage >= Math.ceil(traceTotal / PAGE_SIZE)}
                onClick={() => setTracePage(p => p + 1)}
              >
                下一页
              </ZButton>
            </div>
          )}
        </>
      )}

      {/* ── Tab 2: 安全检查 ──────────────────────────────────────────────── */}
      {activeTab === 'inspections' && (
        <>
          <div className={styles.toolbar}>
            <select
              className={styles.filterSelect}
              value={filterInspType}
              onChange={e => { setFilterInspType(e.target.value); setInspectionPage(1); }}
            >
              <option value="">全部类型</option>
              <option value="daily">日常检查</option>
              <option value="weekly">周检</option>
              <option value="monthly">月检</option>
              <option value="government">政府检查</option>
              <option value="third_party">第三方检查</option>
            </select>
          </div>

          {loading ? (
            <ZSkeleton lines={8} />
          ) : inspections.length === 0 ? (
            <ZEmpty description="暂无检查记录" />
          ) : (
            <ZCard className={styles.tableCard}>
              <ZTable<Inspection>
                columns={inspectionColumns}
                data={inspections}
                rowKey="id"
              />
            </ZCard>
          )}

          {inspectionTotal > PAGE_SIZE && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 12 }}>
              <ZButton
                size="sm"
                variant="ghost"
                disabled={inspectionPage <= 1}
                onClick={() => setInspectionPage(p => Math.max(1, p - 1))}
              >
                上一页
              </ZButton>
              <span style={{ lineHeight: '32px', fontSize: 13, color: 'var(--text-secondary, #6b7280)' }}>
                {inspectionPage} / {Math.ceil(inspectionTotal / PAGE_SIZE)}
              </span>
              <ZButton
                size="sm"
                variant="ghost"
                disabled={inspectionPage >= Math.ceil(inspectionTotal / PAGE_SIZE)}
                onClick={() => setInspectionPage(p => p + 1)}
              >
                下一页
              </ZButton>
            </div>
          )}
        </>
      )}

      {/* ── Tab 3: 预警中心 ──────────────────────────────────────────────── */}
      {activeTab === 'alerts' && (
        <>
          {expiringItems.length === 0 ? (
            <ZEmpty description="暂无预警项目" />
          ) : (
            <div className={styles.alertGrid}>
              {expiringItems.map(item => {
                const days = daysUntil(item.expiry_date);
                const isUrgent = days !== null && days <= 3;
                return (
                  <ZCard key={item.id} className={styles.alertCard}>
                    <div className={styles.alertCardHeader}>
                      <span className={styles.alertCardName}>{item.ingredient_name}</span>
                      <span className={`${styles.alertCountdown} ${isUrgent ? styles.alertUrgent : styles.alertWarn}`}>
                        {days !== null ? (days <= 0 ? '已过期' : `${days}天后过期`) : '--'}
                      </span>
                    </div>
                    <div className={styles.alertCardMeta}>
                      <div>批次: {item.batch_number}</div>
                      <div>供应商: {item.supplier_name}</div>
                      <div>数量: {item.quantity} {item.unit}</div>
                      <div>保质期至: {fmtDate(item.expiry_date)}</div>
                      {item.origin && <div>产地: {item.origin}</div>}
                    </div>
                    <div style={{ marginTop: 8 }}>
                      <ZButton size="sm" variant="ghost" onClick={() => handleRecall(item.id)}>
                        召回
                      </ZButton>
                    </div>
                  </ZCard>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* ── 录入溯源 Modal ──────────────────────────────────────────────── */}
      <ZModal
        open={showTraceModal}
        title="录入食材溯源"
        onClose={() => setShowTraceModal(false)}
      >
        <div className={styles.modalBody}>
          {formErr && <Alert type="error" message={formErr} className={styles.modalErr} />}

          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                食材名称<span className={styles.fieldRequired}>*</span>
              </label>
              <input
                className={styles.fieldInput}
                value={traceForm.ingredient_name}
                onChange={e => setTraceForm(p => ({ ...p, ingredient_name: e.target.value }))}
                placeholder="如：五花肉"
              />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                批次号<span className={styles.fieldRequired}>*</span>
              </label>
              <input
                className={styles.fieldInput}
                value={traceForm.batch_number}
                onChange={e => setTraceForm(p => ({ ...p, batch_number: e.target.value }))}
                placeholder="如：20260315-001"
              />
            </div>
          </div>

          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                供应商<span className={styles.fieldRequired}>*</span>
              </label>
              <input
                className={styles.fieldInput}
                value={traceForm.supplier_name}
                onChange={e => setTraceForm(p => ({ ...p, supplier_name: e.target.value }))}
                placeholder="供应商名称"
              />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>门店ID</label>
              <input
                className={styles.fieldInput}
                value={traceForm.store_id}
                onChange={e => setTraceForm(p => ({ ...p, store_id: e.target.value }))}
                placeholder="门店编号"
              />
            </div>
          </div>

          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                收货日期<span className={styles.fieldRequired}>*</span>
              </label>
              <input
                className={styles.fieldInput}
                type="date"
                value={traceForm.receive_date}
                onChange={e => setTraceForm(p => ({ ...p, receive_date: e.target.value }))}
              />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>保质期至</label>
              <input
                className={styles.fieldInput}
                type="date"
                value={traceForm.expiry_date}
                onChange={e => setTraceForm(p => ({ ...p, expiry_date: e.target.value }))}
              />
            </div>
          </div>

          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>生产日期</label>
              <input
                className={styles.fieldInput}
                type="date"
                value={traceForm.production_date}
                onChange={e => setTraceForm(p => ({ ...p, production_date: e.target.value }))}
              />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>产地</label>
              <input
                className={styles.fieldInput}
                value={traceForm.origin}
                onChange={e => setTraceForm(p => ({ ...p, origin: e.target.value }))}
                placeholder="如：湖南长沙"
              />
            </div>
          </div>

          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                数量<span className={styles.fieldRequired}>*</span>
              </label>
              <input
                className={styles.fieldInput}
                type="number"
                step="0.01"
                value={traceForm.quantity}
                onChange={e => setTraceForm(p => ({ ...p, quantity: e.target.value }))}
                placeholder="数量"
              />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>单位</label>
              <select
                className={styles.filterSelect}
                value={traceForm.unit}
                onChange={e => setTraceForm(p => ({ ...p, unit: e.target.value }))}
                style={{ width: '100%' }}
              >
                <option value="kg">千克(kg)</option>
                <option value="g">克(g)</option>
                <option value="箱">箱</option>
                <option value="份">份</option>
                <option value="瓶">瓶</option>
                <option value="袋">袋</option>
              </select>
            </div>
          </div>

          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>收货温度</label>
              <input
                className={styles.fieldInput}
                type="number"
                step="0.1"
                value={traceForm.temperature_on_receive}
                onChange={e => setTraceForm(p => ({ ...p, temperature_on_receive: e.target.value }))}
                placeholder="摄氏度"
              />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>追溯码</label>
              <input
                className={styles.fieldInput}
                value={traceForm.qr_code}
                onChange={e => setTraceForm(p => ({ ...p, qr_code: e.target.value }))}
                placeholder="追溯码/二维码"
              />
            </div>
          </div>

          <div className={styles.fieldRow}>
            <label className={styles.fieldLabel}>备注</label>
            <textarea
              className={styles.fieldTextarea}
              value={traceForm.notes}
              onChange={e => setTraceForm(p => ({ ...p, notes: e.target.value }))}
              placeholder="备注信息"
            />
          </div>

          <div className={styles.modalFooter}>
            <ZButton variant="ghost" onClick={() => setShowTraceModal(false)}>取消</ZButton>
            <ZButton variant="primary" onClick={handleCreateTrace} disabled={submitting}>
              {submitting ? '提交中...' : '提交'}
            </ZButton>
          </div>
        </div>
      </ZModal>

      {/* ── 新建检查 Modal ──────────────────────────────────────────────── */}
      <ZModal
        open={showInspModal}
        title="新建食品安全检查"
        onClose={() => setShowInspModal(false)}
      >
        <div className={styles.modalBody}>
          {formErr && <Alert type="error" message={formErr} className={styles.modalErr} />}

          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                检查类型<span className={styles.fieldRequired}>*</span>
              </label>
              <select
                className={styles.filterSelect}
                value={inspForm.inspection_type}
                onChange={e => setInspForm(p => ({ ...p, inspection_type: e.target.value }))}
                style={{ width: '100%' }}
              >
                <option value="daily">日常检查</option>
                <option value="weekly">周检</option>
                <option value="monthly">月检</option>
                <option value="government">政府检查</option>
                <option value="third_party">第三方检查</option>
              </select>
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                检查人<span className={styles.fieldRequired}>*</span>
              </label>
              <input
                className={styles.fieldInput}
                value={inspForm.inspector_name}
                onChange={e => setInspForm(p => ({ ...p, inspector_name: e.target.value }))}
                placeholder="检查人姓名"
              />
            </div>
          </div>

          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                检查日期<span className={styles.fieldRequired}>*</span>
              </label>
              <input
                className={styles.fieldInput}
                type="date"
                value={inspForm.inspection_date}
                onChange={e => setInspForm(p => ({ ...p, inspection_date: e.target.value }))}
              />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>评分 (0-100)</label>
              <input
                className={styles.fieldInput}
                type="number"
                min="0"
                max="100"
                value={inspForm.score}
                onChange={e => setInspForm(p => ({ ...p, score: e.target.value }))}
                placeholder="0-100"
              />
            </div>
          </div>

          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>检查结果</label>
              <select
                className={styles.filterSelect}
                value={inspForm.status}
                onChange={e => setInspForm(p => ({ ...p, status: e.target.value }))}
                style={{ width: '100%' }}
              >
                <option value="pending">待检查</option>
                <option value="passed">通过</option>
                <option value="failed">未通过</option>
                <option value="needs_improvement">需整改</option>
              </select>
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>门店ID</label>
              <input
                className={styles.fieldInput}
                value={inspForm.store_id}
                onChange={e => setInspForm(p => ({ ...p, store_id: e.target.value }))}
                placeholder="门店编号"
              />
            </div>
          </div>

          <div className={styles.fieldRow}>
            <label className={styles.fieldLabel}>整改措施</label>
            <textarea
              className={styles.fieldTextarea}
              value={inspForm.corrective_actions}
              onChange={e => setInspForm(p => ({ ...p, corrective_actions: e.target.value }))}
              placeholder="如需整改，请填写整改措施"
            />
          </div>

          <div className={styles.modalFooter}>
            <ZButton variant="ghost" onClick={() => setShowInspModal(false)}>取消</ZButton>
            <ZButton variant="primary" onClick={handleCreateInspection} disabled={submitting}>
              {submitting ? '提交中...' : '提交'}
            </ZButton>
          </div>
        </div>
      </ZModal>
    </div>
  );
};

export default FoodSafetyPage;
