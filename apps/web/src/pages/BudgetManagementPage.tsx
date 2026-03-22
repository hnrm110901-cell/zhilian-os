import React, { useState, useEffect, useCallback, useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZTable, ZEmpty } from '../design-system/components';
import type { ZTableColumn } from '../design-system/components';
import { apiClient, handleApiError } from '../services/api';
import styles from './BudgetManagementPage.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

interface BudgetPlan {
  id: string;
  store_id: string;
  period: string;
  period_type: string;
  status: string;
  total_revenue_budget: number;
  total_cost_budget: number;
  profit_budget: number;
  notes: string | null;
  approved_at: string | null;
}

interface VarianceItem {
  category: string;
  sub_category: string | null;
  budget_yuan: number;
  actual_yuan: number;
  variance_yuan: number;
  variance_pct: number;
}

interface BudgetVariance {
  plan_id: string;
  store_id: string;
  period: string;
  status: string;
  summary: {
    revenue_budget: number;
    revenue_actual: number;
    revenue_variance: { variance_yuan: number; variance_pct: number };
    profit_budget: number;
    profit_actual: number;
    profit_variance: { variance_yuan: number; variance_pct: number };
    profit_margin_pct: number;
  };
  line_items: VarianceItem[];
}

// ── Constants ─────────────────────────────────────────────────────────────────

const STORE_ID = localStorage.getItem('store_id') || 'store-demo-001';
const today    = new Date().toISOString().slice(0, 10);
const period   = today.slice(0, 7);

const STATUS_LABELS: Record<string, string> = {
  draft: '草稿', approved: '已审批', active: '执行中', closed: '已关闭',
};
const STATUS_BADGE: Record<string, 'neutral' | 'warning' | 'success' | 'error'> = {
  draft: 'neutral', approved: 'warning', active: 'success', closed: 'neutral',
};
const CATEGORY_LABELS: Record<string, string> = {
  revenue: '营收', food_cost: '食材成本', labor_cost: '人工成本',
  platform_commission: '平台抽佣', waste: '损耗', other_expense: '其他费用', tax: '税费',
};

// ── Plan table columns ─────────────────────────────────────────────────────────

const planColumns: ZTableColumn<BudgetPlan>[] = [
  { key: 'period',       title: '期间', render: (v) => <span className={styles.mono}>{v}</span> },
  { key: 'period_type',  title: '类型', render: (v) => v === 'monthly' ? '月度' : v },
  {
    key:    'status',
    title:  '状态',
    align:  'center',
    render: (v) => <ZBadge type={STATUS_BADGE[v] || 'neutral'} text={STATUS_LABELS[v] || v} />,
  },
  {
    key:    'total_revenue_budget',
    title:  '预算收入',
    align:  'right',
    render: (v) => <span className={styles.mono}>¥{Number(v).toFixed(0)}</span>,
  },
  {
    key:    'profit_budget',
    title:  '预算利润',
    align:  'right',
    render: (v) => <span className={styles.amount}>¥{Number(v).toFixed(0)}</span>,
  },
];

// ── Component ─────────────────────────────────────────────────────────────────

const BudgetManagementPage: React.FC = () => {
  const [plans,       setPlans]       = useState<BudgetPlan[]>([]);
  const [variance,    setVariance]    = useState<BudgetVariance | null>(null);
  const [selectedId,  setSelectedId]  = useState<string | null>(null);
  const [loading,     setLoading]     = useState(false);
  const [activeTab,   setActiveTab]   = useState<'plans' | 'variance' | 'new'>('plans');

  // New plan form state
  const [form, setForm] = useState({
    period:               period,
    total_revenue_budget: '',
    total_cost_budget:    '',
    profit_budget:        '',
    notes:                '',
  });
  const [submitting, setSubmitting] = useState(false);

  const loadPlans = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/api/v1/budget/plans', {
        params: { store_id: STORE_ID, limit: 20 },
      });
      setPlans(res.data.plans || []);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, []);

  const loadVariance = useCallback(async (planId: string) => {
    try {
      const res = await apiClient.get(`/api/v1/budget/plans/${planId}/variance`);
      setVariance(res.data);
    } catch (e) { handleApiError(e); }
  }, []);

  useEffect(() => { loadPlans(); }, [loadPlans]);

  const handleSelectPlan = (plan: BudgetPlan) => {
    setSelectedId(plan.id);
    setActiveTab('variance');
    loadVariance(plan.id);
  };

  const handleTransition = async (planId: string, action: 'approve' | 'activate' | 'close') => {
    try {
      await apiClient.post(`/api/v1/budget/plans/${planId}/${action}`);
      await loadPlans();
      if (selectedId === planId) loadVariance(planId);
    } catch (e) { handleApiError(e); }
  };

  const handleCreate = async () => {
    setSubmitting(true);
    try {
      await apiClient.post('/api/v1/budget/plans', {
        store_id:             STORE_ID,
        period:               form.period,
        total_revenue_budget: Number(form.total_revenue_budget) || 0,
        total_cost_budget:    Number(form.total_cost_budget) || 0,
        profit_budget:        Number(form.profit_budget) || 0,
        notes:                form.notes || null,
        line_items:           [],
      });
      await loadPlans();
      setActiveTab('plans');
      setForm({ period, total_revenue_budget: '', total_cost_budget: '', profit_budget: '', notes: '' });
    } catch (e) { handleApiError(e); }
    finally { setSubmitting(false); }
  };

  // ── Variance chart ──────────────────────────────────────────────────────────

  const varianceChartOption = useMemo(() => {
    if (!variance?.line_items.length) return {};
    const items = variance.line_items;
    return {
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0, itemHeight: 10, textStyle: { fontSize: 11 } },
      grid:   { top: 12, bottom: 50, left: 64, right: 16 },
      xAxis: {
        type: 'category',
        data: items.map(i => CATEGORY_LABELS[i.category] || i.category),
        axisLabel: { fontSize: 10, rotate: 20 },
      },
      yAxis: {
        type: 'value',
        axisLabel: { fontSize: 10, formatter: (v: number) => `¥${(v / 1000).toFixed(0)}k` },
      },
      series: [
        {
          name: '预算',
          type: 'bar',
          data: items.map(i => i.budget_yuan),
          itemStyle: { color: 'rgba(255,107,44,0.3)' },
          barMaxWidth: 28,
        },
        {
          name: '实际',
          type: 'bar',
          data: items.map(i => i.actual_yuan),
          itemStyle: { color: '#FF6B2C' },
          barMaxWidth: 28,
        },
      ],
    };
  }, [variance]);

  const s = variance?.summary;

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>预算管理</h1>
          <p className={styles.pageSub}>预算编制 · 偏差分析 · FSM 审批流 · {period}</p>
        </div>
        <div className={styles.headerActions}>
          <ZButton onClick={() => setActiveTab('new')}>新建预算</ZButton>
          <ZButton onClick={loadPlans}>刷新</ZButton>
        </div>
      </div>

      {/* KPI row — shown when variance is loaded */}
      {s && (
        <div className={styles.kpiGrid}>
          <ZCard>
            <ZKpi label="预算收入" value={`¥${(s.revenue_budget / 10000).toFixed(1)}万`} />
            <div className={styles.kpiSub}>实际 ¥{(s.revenue_actual / 10000).toFixed(1)}万</div>
          </ZCard>
          <ZCard>
            <ZKpi label="收入偏差" value={`${s.revenue_variance.variance_pct >= 0 ? '+' : ''}${s.revenue_variance.variance_pct.toFixed(1)}%`} />
            <div className={s.revenue_variance.variance_yuan < 0 ? styles.kpiSubWarn : styles.kpiSub}>
              ¥{s.revenue_variance.variance_yuan.toFixed(0)}
            </div>
          </ZCard>
          <ZCard>
            <ZKpi label="预算利润" value={`¥${(s.profit_budget / 10000).toFixed(1)}万`} />
            <div className={styles.kpiSub}>实际 ¥{(s.profit_actual / 10000).toFixed(1)}万</div>
          </ZCard>
          <ZCard>
            <ZKpi label="利润偏差" value={`${s.profit_variance.variance_pct >= 0 ? '+' : ''}${s.profit_variance.variance_pct.toFixed(1)}%`} />
            <div className={s.profit_variance.variance_yuan < 0 ? styles.kpiSubWarn : styles.kpiSub}>
              利润率 {s.profit_margin_pct.toFixed(1)}%
            </div>
          </ZCard>
        </div>
      )}

      {/* Main tabs */}
      <ZCard>
        <div className={styles.tabBar}>
          {(['plans', 'variance', 'new'] as const).map(tab => (
            <button
              key={tab}
              className={`${styles.tab} ${activeTab === tab ? styles.tabActive : ''}`}
              onClick={() => setActiveTab(tab)}
            >
              {{ plans: `预算计划 (${plans.length})`, variance: '偏差分析', new: '+ 新建预算' }[tab]}
            </button>
          ))}
        </div>

        {/* Plan list */}
        {activeTab === 'plans' && (
          loading ? <ZSkeleton height={200} /> :
          plans.length > 0 ? (
            <div>
              {plans.map(p => (
                <div
                  key={p.id}
                  className={`${styles.planRow} ${selectedId === p.id ? styles.planRowActive : ''}`}
                  onClick={() => handleSelectPlan(p)}
                >
                  <ZBadge type={STATUS_BADGE[p.status] || 'neutral'} text={STATUS_LABELS[p.status] || p.status} />
                  <span className={styles.planPeriod}>{p.period}</span>
                  <span className={styles.planLabel}>预算收入</span>
                  <span className={styles.mono}>¥{Number(p.total_revenue_budget).toFixed(0)}</span>
                  <span className={styles.planLabel}>预算利润</span>
                  <span className={styles.amount}>¥{Number(p.profit_budget).toFixed(0)}</span>
                  <span style={{ flex: 1 }} />
                  <div className={styles.planActions} onClick={e => e.stopPropagation()}>
                    {p.status === 'draft'    && <ZButton onClick={() => handleTransition(p.id, 'approve')}>审批</ZButton>}
                    {p.status === 'approved' && <ZButton onClick={() => handleTransition(p.id, 'activate')}>激活</ZButton>}
                    {p.status === 'active'   && <ZButton onClick={() => handleTransition(p.id, 'close')}>关闭</ZButton>}
                  </div>
                </div>
              ))}
            </div>
          ) : <ZEmpty text="暂无预算计划" />
        )}

        {/* Variance detail */}
        {activeTab === 'variance' && (
          !variance ? (
            <ZEmpty text="请从「预算计划」选择一个计划查看偏差分析" />
          ) : (
            <div>
              <div className={styles.varChart}>
                <ReactECharts option={varianceChartOption} style={{ height: '100%' }} />
              </div>
              <div className={styles.varTable}>
                {variance.line_items.map((item, i) => (
                  <div key={i} className={styles.varRow}>
                    <span className={styles.varCat}>{CATEGORY_LABELS[item.category] || item.category}</span>
                    <span className={styles.mono}>预 ¥{item.budget_yuan.toFixed(0)}</span>
                    <span className={styles.mono}>实 ¥{item.actual_yuan.toFixed(0)}</span>
                    <span style={{ flex: 1 }} />
                    <span className={item.variance_yuan > 0 ? styles.varPositive : item.variance_yuan < 0 ? styles.varNegative : styles.mono}>
                      {item.variance_yuan > 0 ? '+' : ''}¥{item.variance_yuan.toFixed(0)}
                      <span style={{ fontSize: 10, marginLeft: 4 }}>({item.variance_pct.toFixed(1)}%)</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )
        )}

        {/* New plan form */}
        {activeTab === 'new' && (
          <div className={styles.formCard}>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>期间 (YYYY-MM)</label>
              <input
                className={styles.formInput}
                value={form.period}
                onChange={e => setForm(f => ({ ...f, period: e.target.value }))}
                placeholder="2026-03"
              />
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>预算收入 (元)</label>
              <input
                className={styles.formInput}
                type="number"
                value={form.total_revenue_budget}
                onChange={e => setForm(f => ({ ...f, total_revenue_budget: e.target.value }))}
                placeholder="500000"
              />
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>预算成本 (元)</label>
              <input
                className={styles.formInput}
                type="number"
                value={form.total_cost_budget}
                onChange={e => setForm(f => ({ ...f, total_cost_budget: e.target.value }))}
                placeholder="300000"
              />
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>预算利润 (元)</label>
              <input
                className={styles.formInput}
                type="number"
                value={form.profit_budget}
                onChange={e => setForm(f => ({ ...f, profit_budget: e.target.value }))}
                placeholder="200000"
              />
            </div>
            <div className={styles.formRow}>
              <label className={styles.formLabel}>备注</label>
              <input
                className={styles.formInput}
                value={form.notes}
                onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                placeholder="可选"
              />
            </div>
            <div className={styles.formActions}>
              <ZButton onClick={handleCreate} disabled={submitting}>
                {submitting ? '提交中…' : '创建预算'}
              </ZButton>
              <ZButton onClick={() => setActiveTab('plans')}>取消</ZButton>
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
};

export default BudgetManagementPage;
