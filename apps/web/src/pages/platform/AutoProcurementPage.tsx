/**
 * AutoProcurementPage — /platform/auto-procurement
 *
 * 智能采购：自动检测库存阈值生成采购建议，规则管理，执行记录
 * 后端 API:
 *   POST   /api/v1/auto-procurement/check              — 触发库存检查
 *   GET    /api/v1/auto-procurement/suggestions         — 待处理建议
 *   POST   /api/v1/auto-procurement/suggestions/{id}/approve — 审批
 *   POST   /api/v1/auto-procurement/suggestions/{id}/skip    — 跳过
 *   POST   /api/v1/auto-procurement/rules               — 创建规则
 *   GET    /api/v1/auto-procurement/rules               — 规则列表
 *   PUT    /api/v1/auto-procurement/rules/{id}          — 更新规则
 *   DELETE /api/v1/auto-procurement/rules/{id}          — 删除规则
 *   GET    /api/v1/auto-procurement/executions           — 执行记录
 *   GET    /api/v1/auto-procurement/stats               — 统计概览
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  ZCard, ZBadge, ZButton, ZEmpty, ZAlert, ZSkeleton, ZModal,
} from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import { apiClient } from '../../services/api';
import styles from './AutoProcurementPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface Stats {
  active_rules: number;
  pending_suggestions: number;
  monthly_ordered: number;
  monthly_skipped: number;
}

interface Suggestion {
  id: string;
  rule_id?: string;
  brand_id: string;
  store_id: string;
  trigger_type: string;
  ingredient_name: string;
  quantity: number;
  status: string;
  reason?: string;
  executed_at?: string;
  supplier_name?: string;
  supplier_id?: string;
  unit?: string;
  unit_price_fen?: number;
  min_stock_qty?: number;
  current_stock?: number;
  estimated_cost_fen?: number;
}

interface ProcurementRule {
  id: string;
  brand_id: string;
  store_id?: string;
  ingredient_id: string;
  ingredient_name: string;
  supplier_id: string;
  supplier_name: string;
  min_stock_qty: number;
  reorder_qty: number;
  unit: string;
  unit_price_fen: number;
  lead_days: number;
  is_enabled: boolean;
  last_triggered_at?: string;
  created_at?: string;
}

interface Execution {
  id: string;
  rule_id?: string;
  brand_id: string;
  store_id: string;
  trigger_type: string;
  ingredient_name: string;
  quantity: number;
  generated_order_id?: string;
  status: string;
  reason?: string;
  executed_at?: string;
}

interface RuleForm {
  ingredient_id: string;
  ingredient_name: string;
  supplier_id: string;
  supplier_name: string;
  min_stock_qty: string;
  reorder_qty: string;
  unit: string;
  unit_price_yuan: string;
  lead_days: string;
}

const BRAND_ID = 'BRD_CZYZ0001';

const TRIGGER_MAP: Record<string, string> = {
  auto_low_stock: '低库存',
  auto_forecast: '预测触发',
  manual: '手动',
};

const STATUS_MAP: Record<string, { label: string; type: 'success' | 'warning' | 'info' | 'error' | 'default' }> = {
  suggested: { label: '待处理', type: 'warning' },
  approved: { label: '已审批', type: 'info' },
  ordered: { label: '已下单', type: 'success' },
  skipped: { label: '已跳过', type: 'default' },
};

const emptyRuleForm: RuleForm = {
  ingredient_id: '',
  ingredient_name: '',
  supplier_id: '',
  supplier_name: '',
  min_stock_qty: '',
  reorder_qty: '',
  unit: 'kg',
  unit_price_yuan: '',
  lead_days: '1',
};

// ── 工具函数 ─────────────────────────────────────────────────────────────────

function fenToYuan(fen: number): string {
  return (fen / 100).toFixed(2);
}

function fmtTime(iso?: string): string {
  if (!iso) return '-';
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

// ── 组件 ─────────────────────────────────────────────────────────────────────

export default function AutoProcurementPage() {
  const [activeTab, setActiveTab] = useState<'suggestions' | 'rules' | 'executions'>('suggestions');
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState('');

  // 建议
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [checking, setChecking] = useState(false);

  // 规则
  const [rules, setRules] = useState<ProcurementRule[]>([]);
  const [rulesTotal, setRulesTotal] = useState(0);
  const [rulesPage, setRulesPage] = useState(1);
  const [showRuleModal, setShowRuleModal] = useState(false);
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const [ruleForm, setRuleForm] = useState<RuleForm>(emptyRuleForm);
  const [ruleErr, setRuleErr] = useState('');
  const [ruleSaving, setRuleSaving] = useState(false);

  // 执行记录
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [execTotal, setExecTotal] = useState(0);
  const [execPage, setExecPage] = useState(1);
  const [execStatusFilter, setExecStatusFilter] = useState('');
  const [execTriggerFilter, setExecTriggerFilter] = useState('');

  // ── 数据加载 ───────────────────────────────────────────────────────────────

  const loadStats = useCallback(async () => {
    try {
      const res = await apiClient.get<{ success: boolean; data: Stats }>(
        `/api/v1/auto-procurement/stats?brand_id=${BRAND_ID}`
      );
      setStats(res.data);
    } catch {
      /* 降级处理 */
    }
  }, []);

  const loadSuggestions = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get<{ success: boolean; data: { items: Suggestion[]; total: number } }>(
        `/api/v1/auto-procurement/suggestions?brand_id=${BRAND_ID}&page=1&page_size=50`
      );
      setSuggestions(res.data.items);
    } catch {
      setError('加载采购建议失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadRules = useCallback(async (page = 1) => {
    setLoading(true);
    try {
      const res = await apiClient.get<{ success: boolean; data: { items: ProcurementRule[]; total: number } }>(
        `/api/v1/auto-procurement/rules?brand_id=${BRAND_ID}&page=${page}&page_size=20`
      );
      setRules(res.data.items);
      setRulesTotal(res.data.total);
      setRulesPage(page);
    } catch {
      setError('加载采购规则失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadExecutions = useCallback(async (page = 1) => {
    setLoading(true);
    try {
      let url = `/api/v1/auto-procurement/executions?brand_id=${BRAND_ID}&page=${page}&page_size=20`;
      if (execStatusFilter) url += `&status=${execStatusFilter}`;
      if (execTriggerFilter) url += `&trigger_type=${execTriggerFilter}`;
      const res = await apiClient.get<{ success: boolean; data: { items: Execution[]; total: number } }>(url);
      setExecutions(res.data.items);
      setExecTotal(res.data.total);
      setExecPage(page);
    } catch {
      setError('加载执行记录失败');
    } finally {
      setLoading(false);
    }
  }, [execStatusFilter, execTriggerFilter]);

  useEffect(() => {
    loadStats();
    loadSuggestions();
  }, [loadStats, loadSuggestions]);

  useEffect(() => {
    if (activeTab === 'rules') loadRules();
    if (activeTab === 'executions') loadExecutions();
  }, [activeTab, loadRules, loadExecutions]);

  // ── 操作 ───────────────────────────────────────────────────────────────────

  const handleCheck = async () => {
    setChecking(true);
    setError('');
    try {
      await apiClient.post('/api/v1/auto-procurement/check', { brand_id: BRAND_ID });
      await loadSuggestions();
      await loadStats();
    } catch {
      setError('检查库存失败，请重试');
    } finally {
      setChecking(false);
    }
  };

  const handleApprove = async (id: string) => {
    try {
      await apiClient.post(`/api/v1/auto-procurement/suggestions/${id}/approve`);
      await loadSuggestions();
      await loadStats();
    } catch {
      setError('审批失败');
    }
  };

  const handleSkip = async (id: string) => {
    try {
      await apiClient.post(`/api/v1/auto-procurement/suggestions/${id}/skip`, {});
      await loadSuggestions();
      await loadStats();
    } catch {
      setError('跳过失败');
    }
  };

  const handleToggleRule = async (rule: ProcurementRule) => {
    try {
      await apiClient.put(`/api/v1/auto-procurement/rules/${rule.id}`, {
        is_enabled: !rule.is_enabled,
      });
      await loadRules(rulesPage);
      await loadStats();
    } catch {
      setError('更新规则失败');
    }
  };

  const handleDeleteRule = async (id: string) => {
    if (!window.confirm('确认删除该规则？')) return;
    try {
      await apiClient.delete(`/api/v1/auto-procurement/rules/${id}`);
      await loadRules(rulesPage);
      await loadStats();
    } catch {
      setError('删除规则失败');
    }
  };

  const openCreateRule = () => {
    setEditingRuleId(null);
    setRuleForm(emptyRuleForm);
    setRuleErr('');
    setShowRuleModal(true);
  };

  const openEditRule = (rule: ProcurementRule) => {
    setEditingRuleId(rule.id);
    setRuleForm({
      ingredient_id: rule.ingredient_id,
      ingredient_name: rule.ingredient_name,
      supplier_id: rule.supplier_id,
      supplier_name: rule.supplier_name,
      min_stock_qty: String(rule.min_stock_qty),
      reorder_qty: String(rule.reorder_qty),
      unit: rule.unit,
      unit_price_yuan: fenToYuan(rule.unit_price_fen),
      lead_days: String(rule.lead_days),
    });
    setRuleErr('');
    setShowRuleModal(true);
  };

  const handleSaveRule = async () => {
    const { ingredient_id, ingredient_name, supplier_id, supplier_name, min_stock_qty, reorder_qty, unit_price_yuan } = ruleForm;
    if (!ingredient_id || !ingredient_name || !supplier_id || !supplier_name) {
      setRuleErr('请填写所有必填字段');
      return;
    }
    if (!min_stock_qty || !reorder_qty || !unit_price_yuan) {
      setRuleErr('请填写数量和单价');
      return;
    }

    setRuleSaving(true);
    setRuleErr('');
    try {
      const payload = {
        brand_id: BRAND_ID,
        ingredient_id: ruleForm.ingredient_id,
        ingredient_name: ruleForm.ingredient_name,
        supplier_id: ruleForm.supplier_id,
        supplier_name: ruleForm.supplier_name,
        min_stock_qty: parseFloat(ruleForm.min_stock_qty),
        reorder_qty: parseFloat(ruleForm.reorder_qty),
        unit: ruleForm.unit,
        unit_price_fen: Math.round(parseFloat(ruleForm.unit_price_yuan) * 100),
        lead_days: parseInt(ruleForm.lead_days, 10) || 1,
      };

      if (editingRuleId) {
        await apiClient.put(`/api/v1/auto-procurement/rules/${editingRuleId}`, payload);
      } else {
        await apiClient.post('/api/v1/auto-procurement/rules', payload);
      }
      setShowRuleModal(false);
      await loadRules(rulesPage);
      await loadStats();
    } catch {
      setRuleErr('保存失败，请重试');
    } finally {
      setRuleSaving(false);
    }
  };

  // ── 规则表列定义 ───────────────────────────────────────────────────────────

  const ruleColumns: ZTableColumn<ProcurementRule>[] = [
    { title: '食材', dataIndex: 'ingredient_name', width: 140 },
    { title: '供应商', dataIndex: 'supplier_name', width: 120 },
    {
      title: '最低库存',
      dataIndex: 'min_stock_qty',
      width: 100,
      align: 'right',
      render: (v: number, row) => `${v} ${row.unit}`,
    },
    {
      title: '补货数量',
      dataIndex: 'reorder_qty',
      width: 100,
      align: 'right',
      render: (v: number, row) => `${v} ${row.unit}`,
    },
    {
      title: '单价',
      dataIndex: 'unit_price_fen',
      width: 90,
      align: 'right',
      render: (v: number) => <span className={styles.amountCell}>&yen;{fenToYuan(v)}</span>,
    },
    {
      title: '交货天数',
      dataIndex: 'lead_days',
      width: 80,
      align: 'center',
      render: (v: number) => `${v}天`,
    },
    {
      title: '启用',
      dataIndex: 'is_enabled',
      width: 70,
      align: 'center',
      render: (_: boolean, row) => (
        <button
          className={row.is_enabled ? styles.switchOn : styles.switch}
          onClick={() => handleToggleRule(row)}
          aria-label={row.is_enabled ? '禁用' : '启用'}
        />
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      align: 'right',
      render: (_: any, row) => (
        <div className={styles.actionGroup}>
          <ZButton size="sm" variant="ghost" onClick={() => openEditRule(row)}>编辑</ZButton>
          <ZButton size="sm" variant="ghost" onClick={() => handleDeleteRule(row.id)}>删除</ZButton>
        </div>
      ),
    },
  ];

  // ── 执行记录表列定义 ───────────────────────────────────────────────────────

  const execColumns: ZTableColumn<Execution>[] = [
    {
      title: '时间',
      dataIndex: 'executed_at',
      width: 120,
      render: (v: string) => <span className={styles.timeCell}>{fmtTime(v)}</span>,
    },
    { title: '食材', dataIndex: 'ingredient_name', width: 120 },
    {
      title: '数量',
      dataIndex: 'quantity',
      width: 80,
      align: 'right',
    },
    {
      title: '触发类型',
      dataIndex: 'trigger_type',
      width: 90,
      render: (v: string) => TRIGGER_MAP[v] || v,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      render: (v: string) => {
        const s = STATUS_MAP[v] || { label: v, type: 'default' as const };
        return <ZBadge type={s.type} text={s.label} />;
      },
    },
    {
      title: '关联采购单',
      dataIndex: 'generated_order_id',
      width: 100,
      render: (v: string | null) => v ? v.slice(0, 8) + '...' : '-',
    },
    {
      title: '原因',
      dataIndex: 'reason',
      render: (v: string | null) => v || '-',
    },
  ];

  // ── 渲染 ───────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>智能采购</h1>
          <p className={styles.pageSubtitle}>
            自动监控库存阈值，智能生成采购建议，一键转为B2B采购单
          </p>
        </div>
        {activeTab === 'suggestions' && (
          <div className={styles.headerActions}>
            <ZButton variant="primary" onClick={handleCheck} disabled={checking}>
              {checking ? '检查中...' : '检查库存'}
            </ZButton>
          </div>
        )}
        {activeTab === 'rules' && (
          <div className={styles.headerActions}>
            <ZButton variant="primary" onClick={openCreateRule}>新建规则</ZButton>
          </div>
        )}
      </div>

      {error && (
        <ZAlert variant="error" style={{ marginBottom: 12 }}>{error}</ZAlert>
      )}

      {/* 统计概览 */}
      <div className={styles.statsRow}>
        <ZCard className={styles.statCard}>
          <div className={`${styles.statNum} ${styles.statOrange}`}>
            {stats?.pending_suggestions ?? '-'}
          </div>
          <div className={styles.statLabel}>待处理建议</div>
        </ZCard>
        <ZCard className={styles.statCard}>
          <div className={`${styles.statNum} ${styles.statGreen}`}>
            {stats?.monthly_ordered ?? '-'}
          </div>
          <div className={styles.statLabel}>本月自动下单</div>
        </ZCard>
        <ZCard className={styles.statCard}>
          <div className={`${styles.statNum} ${styles.statBlue}`}>
            {stats?.active_rules ?? '-'}
          </div>
          <div className={styles.statLabel}>活跃规则</div>
        </ZCard>
        <ZCard className={styles.statCard}>
          <div className={`${styles.statNum}`}>
            {stats?.monthly_skipped ?? '-'}
          </div>
          <div className={styles.statLabel}>本月跳过</div>
        </ZCard>
      </div>

      {/* Tab 栏 */}
      <div className={styles.tabs}>
        <button
          className={activeTab === 'suggestions' ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab('suggestions')}
        >
          采购建议
        </button>
        <button
          className={activeTab === 'rules' ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab('rules')}
        >
          采购规则
        </button>
        <button
          className={activeTab === 'executions' ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab('executions')}
        >
          执行记录
        </button>
      </div>

      {/* Tab 1: 采购建议 */}
      {activeTab === 'suggestions' && (
        <>
          {loading ? (
            <ZSkeleton lines={4} />
          ) : suggestions.length === 0 ? (
            <div className={styles.emptyWrap}>
              <ZEmpty description="暂无采购建议，点击「检查库存」触发检测" />
            </div>
          ) : (
            <div className={styles.suggestionGrid}>
              {suggestions.map((s) => (
                <ZCard key={s.id} className={styles.suggestionCard}>
                  <div className={styles.suggestionHeader}>
                    <span className={styles.ingredientName}>{s.ingredient_name}</span>
                    <span className={styles.triggerBadge}>
                      {TRIGGER_MAP[s.trigger_type] || s.trigger_type}
                    </span>
                  </div>
                  <div className={styles.suggestionMeta}>
                    <span className={styles.metaLabel}>当前库存</span>
                    <span className={styles.metaValueWarn}>
                      {s.current_stock ?? '-'} {s.unit || ''}
                    </span>
                    <span className={styles.metaLabel}>最低阈值</span>
                    <span className={styles.metaValue}>
                      {s.min_stock_qty ?? '-'} {s.unit || ''}
                    </span>
                    <span className={styles.metaLabel}>补货数量</span>
                    <span className={styles.metaValue}>
                      {s.quantity} {s.unit || ''}
                    </span>
                    <span className={styles.metaLabel}>供应商</span>
                    <span className={styles.metaValue}>{s.supplier_name || '-'}</span>
                  </div>
                  <div className={styles.costLine}>
                    <span className={styles.costAmount}>
                      &yen;{s.estimated_cost_fen != null ? fenToYuan(s.estimated_cost_fen) : '-'}
                    </span>
                    <div className={styles.cardActions}>
                      <ZButton size="sm" variant="ghost" onClick={() => handleSkip(s.id)}>
                        跳过
                      </ZButton>
                      <ZButton size="sm" variant="primary" onClick={() => handleApprove(s.id)}>
                        审批下单
                      </ZButton>
                    </div>
                  </div>
                </ZCard>
              ))}
            </div>
          )}
        </>
      )}

      {/* Tab 2: 采购规则 */}
      {activeTab === 'rules' && (
        <ZCard className={styles.tableCard}>
          {loading ? (
            <ZSkeleton lines={6} />
          ) : rules.length === 0 ? (
            <div className={styles.emptyWrap}>
              <ZEmpty description="暂无采购规则，点击「新建规则」开始配置" />
            </div>
          ) : (
            <ZTable<ProcurementRule>
              columns={ruleColumns}
              dataSource={rules}
              rowKey="id"
            />
          )}
        </ZCard>
      )}

      {/* Tab 3: 执行记录 */}
      {activeTab === 'executions' && (
        <>
          <div className={styles.toolbar}>
            <select
              className={styles.filterSelect}
              value={execStatusFilter}
              onChange={(e) => { setExecStatusFilter(e.target.value); setExecPage(1); }}
            >
              <option value="">全部状态</option>
              <option value="suggested">待处理</option>
              <option value="ordered">已下单</option>
              <option value="skipped">已跳过</option>
            </select>
            <select
              className={styles.filterSelect}
              value={execTriggerFilter}
              onChange={(e) => { setExecTriggerFilter(e.target.value); setExecPage(1); }}
            >
              <option value="">全部类型</option>
              <option value="auto_low_stock">低库存</option>
              <option value="auto_forecast">预测触发</option>
              <option value="manual">手动</option>
            </select>
            <div className={styles.toolbarSpacer} />
          </div>
          <ZCard className={styles.tableCard}>
            {loading ? (
              <ZSkeleton lines={6} />
            ) : executions.length === 0 ? (
              <div className={styles.emptyWrap}>
                <ZEmpty description="暂无执行记录" />
              </div>
            ) : (
              <ZTable<Execution>
                columns={execColumns}
                dataSource={executions}
                rowKey="id"
              />
            )}
          </ZCard>
        </>
      )}

      {/* 新建/编辑规则 Modal */}
      <ZModal
        open={showRuleModal}
        title={editingRuleId ? '编辑采购规则' : '新建采购规则'}
        onClose={() => setShowRuleModal(false)}
      >
        <div className={styles.modalBody}>
          {ruleErr && <ZAlert variant="error" style={{ marginBottom: 12 }}>{ruleErr}</ZAlert>}

          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                食材ID<span className={styles.fieldRequired}>*</span>
              </label>
              <input
                className={styles.fieldInput}
                value={ruleForm.ingredient_id}
                onChange={(e) => setRuleForm({ ...ruleForm, ingredient_id: e.target.value })}
                placeholder="如 ING_001"
              />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                食材名称<span className={styles.fieldRequired}>*</span>
              </label>
              <input
                className={styles.fieldInput}
                value={ruleForm.ingredient_name}
                onChange={(e) => setRuleForm({ ...ruleForm, ingredient_name: e.target.value })}
                placeholder="如 五花肉"
              />
            </div>
          </div>

          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                供应商ID<span className={styles.fieldRequired}>*</span>
              </label>
              <input
                className={styles.fieldInput}
                value={ruleForm.supplier_id}
                onChange={(e) => setRuleForm({ ...ruleForm, supplier_id: e.target.value })}
                placeholder="如 SUP_001"
              />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                供应商名称<span className={styles.fieldRequired}>*</span>
              </label>
              <input
                className={styles.fieldInput}
                value={ruleForm.supplier_name}
                onChange={(e) => setRuleForm({ ...ruleForm, supplier_name: e.target.value })}
                placeholder="如 湖南鲜达配送"
              />
            </div>
          </div>

          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                最低库存阈值<span className={styles.fieldRequired}>*</span>
              </label>
              <input
                className={styles.fieldInput}
                type="number"
                step="0.1"
                value={ruleForm.min_stock_qty}
                onChange={(e) => setRuleForm({ ...ruleForm, min_stock_qty: e.target.value })}
                placeholder="低于此数量触发采购"
              />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                补货数量<span className={styles.fieldRequired}>*</span>
              </label>
              <input
                className={styles.fieldInput}
                type="number"
                step="0.1"
                value={ruleForm.reorder_qty}
                onChange={(e) => setRuleForm({ ...ruleForm, reorder_qty: e.target.value })}
                placeholder="每次补货量"
              />
            </div>
          </div>

          <div className={styles.fieldGrid}>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>单位</label>
              <input
                className={styles.fieldInput}
                value={ruleForm.unit}
                onChange={(e) => setRuleForm({ ...ruleForm, unit: e.target.value })}
                placeholder="kg"
              />
            </div>
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>
                单价（元）<span className={styles.fieldRequired}>*</span>
              </label>
              <input
                className={styles.fieldInput}
                type="number"
                step="0.01"
                value={ruleForm.unit_price_yuan}
                onChange={(e) => setRuleForm({ ...ruleForm, unit_price_yuan: e.target.value })}
                placeholder="元/单位"
              />
            </div>
          </div>

          <div className={styles.fieldRow}>
            <label className={styles.fieldLabel}>交货天数</label>
            <input
              className={styles.fieldInput}
              type="number"
              min="1"
              value={ruleForm.lead_days}
              onChange={(e) => setRuleForm({ ...ruleForm, lead_days: e.target.value })}
              placeholder="1"
              style={{ maxWidth: 120 }}
            />
          </div>

          <div className={styles.modalFooter}>
            <ZButton variant="ghost" onClick={() => setShowRuleModal(false)}>取消</ZButton>
            <ZButton variant="primary" onClick={handleSaveRule} disabled={ruleSaving}>
              {ruleSaving ? '保存中...' : '保存'}
            </ZButton>
          </div>
        </div>
      </ZModal>
    </div>
  );
}
