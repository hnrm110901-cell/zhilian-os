import React, { useState, useEffect, useCallback } from 'react';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty } from '../design-system/components';
import { apiClient, handleApiError } from '../services/api';
import styles from './FinancialAlertsPage.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

interface AlertRule {
  id: string;
  store_id: string;
  metric: string;
  threshold_type: string;
  threshold_value: number;
  severity: string;
  enabled: boolean;
  cooldown_minutes: number;
  created_at: string;
}

interface AlertEvent {
  id: string;
  rule_id: string;
  store_id: string;
  metric: string;
  current_value: number;
  threshold_value: number;
  severity: string;
  message: string;
  status: string;
  period: string | null;
  triggered_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const STORE_ID = localStorage.getItem('store_id') || 'store-demo-001';
const today    = new Date().toISOString().slice(0, 10);
const period   = today.slice(0, 7);

const SEV_BADGE: Record<string, 'neutral' | 'warning' | 'error'> = {
  info: 'neutral', warning: 'warning', critical: 'error',
};
const SEV_LABEL: Record<string, string> = {
  info: '提示', warning: '告警', critical: '严重',
};
const STATUS_BADGE: Record<string, 'neutral' | 'warning' | 'success'> = {
  open: 'warning', acknowledged: 'neutral', resolved: 'success',
};
const STATUS_LABEL: Record<string, string> = {
  open: '待处理', acknowledged: '已确认', resolved: '已解决',
};
const METRIC_LABELS: Record<string, string> = {
  profit_margin_pct:    '利润率',
  food_cost_rate:       '食材成本率',
  net_revenue_yuan:     '净收入',
  gross_profit_yuan:    '毛利润',
  cash_gap_days:        '现金缺口天数',
  settlement_high_risk: '高风险结算笔数',
  tax_deviation_pct:    '税务偏差率',
};
const THRESHOLD_TYPE_LABELS: Record<string, string> = {
  above: '超过', below: '低于', abs_above: '绝对值超过',
};

const SUPPORTED_METRICS = Object.keys(METRIC_LABELS);

// ── Component ─────────────────────────────────────────────────────────────────

const FinancialAlertsPage: React.FC = () => {
  const [events,      setEvents]     = useState<AlertEvent[]>([]);
  const [rules,       setRules]      = useState<AlertRule[]>([]);
  const [loading,     setLoading]    = useState(false);
  const [evaluating,  setEvaluating] = useState(false);
  const [activeTab,   setActiveTab]  = useState<'events' | 'rules'>('events');
  const [eventFilter, setEventFilter] = useState('');

  // New rule form
  const [ruleForm, setRuleForm] = useState({
    metric:           SUPPORTED_METRICS[0],
    threshold_type:   'below',
    threshold_value:  '',
    severity:         'warning',
    cooldown_minutes: '60',
  });
  const [submittingRule, setSubmittingRule] = useState(false);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [evRes, ruRes] = await Promise.allSettled([
        apiClient.get('/api/v1/fin-alerts/events', {
          params: { store_id: STORE_ID, limit: 100 },
        }),
        apiClient.get('/api/v1/fin-alerts/rules', {
          params: { store_id: STORE_ID },
        }),
      ]);
      if (evRes.status === 'fulfilled') setEvents(evRes.value.data.events || []);
      if (ruRes.status === 'fulfilled') setRules(ruRes.value.data.rules || []);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const handleEvaluate = async () => {
    setEvaluating(true);
    try {
      await apiClient.post('/api/v1/fin-alerts/evaluate', null, {
        params: { store_id: STORE_ID, period },
      });
      await loadAll();
    } catch (e) { handleApiError(e); }
    finally { setEvaluating(false); }
  };

  const handleTransitionEvent = async (alertId: string, action: 'acknowledge' | 'resolve') => {
    try {
      await apiClient.post(`/api/v1/fin-alerts/events/${alertId}/${action}`);
      await loadAll();
    } catch (e) { handleApiError(e); }
  };

  const handleDisableRule = async (ruleId: string) => {
    try {
      await apiClient.delete(`/api/v1/fin-alerts/rules/${ruleId}`, {
        params: { store_id: STORE_ID },
      });
      await loadAll();
    } catch (e) { handleApiError(e); }
  };

  const handleCreateRule = async () => {
    setSubmittingRule(true);
    try {
      await apiClient.post('/api/v1/fin-alerts/rules', {
        store_id:         STORE_ID,
        metric:           ruleForm.metric,
        threshold_type:   ruleForm.threshold_type,
        threshold_value:  Number(ruleForm.threshold_value),
        severity:         ruleForm.severity,
        cooldown_minutes: Number(ruleForm.cooldown_minutes),
      });
      await loadAll();
      setRuleForm({
        metric: SUPPORTED_METRICS[0], threshold_type: 'below',
        threshold_value: '', severity: 'warning', cooldown_minutes: '60',
      });
    } catch (e) { handleApiError(e); }
    finally { setSubmittingRule(false); }
  };

  // Derived
  const openEvents     = events.filter(e => e.status === 'open');
  const criticalEvents = events.filter(e => e.severity === 'critical' && e.status === 'open');
  const ackedEvents    = events.filter(e => e.status === 'acknowledged');
  const filteredEvents = eventFilter
    ? events.filter(e => e.status === eventFilter)
    : events;

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>财务预警</h1>
          <p className={styles.pageSub}>多维指标监控 · 冷却期去重 · 告警事件追踪 · {period}</p>
        </div>
        <div className={styles.headerActions}>
          <ZButton onClick={handleEvaluate} disabled={evaluating}>
            {evaluating ? '评估中…' : '触发评估'}
          </ZButton>
          <ZButton onClick={loadAll}>刷新</ZButton>
        </div>
      </div>

      {/* KPI row */}
      <div className={styles.kpiGrid}>
        {loading ? (
          [...Array(4)].map((_, i) => <ZSkeleton key={i} height={88} />)
        ) : (
          <>
            <ZCard>
              <ZKpi label="开放告警" value={openEvents.length} unit="条" />
              <div className={openEvents.length > 0 ? styles.kpiSubWarn : styles.kpiSub}>
                {openEvents.length > 0 ? '需处理' : '全部清零'}
              </div>
            </ZCard>
            <ZCard>
              <ZKpi label="严重告警" value={criticalEvents.length} unit="条" />
              <div className={criticalEvents.length > 0 ? styles.kpiSubWarn : styles.kpiSub}>
                {criticalEvents.length > 0 ? '⚠ 需立即处理' : '无严重告警'}
              </div>
            </ZCard>
            <ZCard>
              <ZKpi label="已确认" value={ackedEvents.length} unit="条" />
              <div className={styles.kpiSub}>待解决</div>
            </ZCard>
            <ZCard>
              <ZKpi label="预警规则" value={rules.length} unit="条" />
              <div className={styles.kpiSub}>
                已启用 {rules.filter(r => r.enabled).length} 条
              </div>
            </ZCard>
          </>
        )}
      </div>

      {/* Main tabs */}
      <ZCard>
        <div className={styles.tabBar}>
          {(['events', 'rules'] as const).map(tab => (
            <button
              key={tab}
              className={`${styles.tab} ${activeTab === tab ? styles.tabActive : ''}`}
              onClick={() => setActiveTab(tab)}
            >
              {tab === 'events'
                ? `告警事件 (${openEvents.length} 待处理)`
                : `规则配置 (${rules.length})`}
            </button>
          ))}
        </div>

        {/* Alert events */}
        {activeTab === 'events' && (
          <div>
            <div className={styles.filterRow}>
              <select
                className={styles.filterSelect}
                value={eventFilter}
                onChange={e => setEventFilter(e.target.value)}
              >
                <option value="">全部状态</option>
                <option value="open">待处理</option>
                <option value="acknowledged">已确认</option>
                <option value="resolved">已解决</option>
              </select>
            </div>
            {loading ? <ZSkeleton height={200} /> :
             filteredEvents.length > 0 ? (
              <div className={styles.alertList}>
                {filteredEvents.map(ev => (
                  <div key={ev.id} className={`${styles.alertCard} ${ev.severity === 'critical' ? styles.alertCardCritical : ''} ${ev.status === 'resolved' ? styles.alertDone : ''}`}>
                    <div className={styles.alertHeader}>
                      <ZBadge type={SEV_BADGE[ev.severity] || 'neutral'} text={SEV_LABEL[ev.severity] || ev.severity} />
                      <ZBadge type={STATUS_BADGE[ev.status] || 'neutral'} text={STATUS_LABEL[ev.status] || ev.status} />
                      <span className={styles.alertMetric}>{METRIC_LABELS[ev.metric] || ev.metric}</span>
                      <span style={{ flex: 1 }} />
                      <span className={styles.mono} style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                        {ev.triggered_at?.slice(0, 16).replace('T', ' ')}
                      </span>
                    </div>
                    <div className={styles.alertMsg}>{ev.message}</div>
                    {ev.status !== 'resolved' && (
                      <div className={styles.alertActions}>
                        {ev.status === 'open' && (
                          <ZButton onClick={() => handleTransitionEvent(ev.id, 'acknowledge')}>确认</ZButton>
                        )}
                        <ZButton onClick={() => handleTransitionEvent(ev.id, 'resolve')}>标记解决</ZButton>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : <ZEmpty text="暂无告警事件" />}
          </div>
        )}

        {/* Rules config */}
        {activeTab === 'rules' && (
          <div>
            {loading ? <ZSkeleton height={200} /> :
             rules.length > 0 ? (
              <div className={styles.ruleList}>
                {rules.map(r => (
                  <div key={r.id} className={`${styles.ruleRow} ${!r.enabled ? styles.ruleDisabled : ''}`}>
                    <ZBadge type={SEV_BADGE[r.severity] || 'neutral'} text={SEV_LABEL[r.severity] || r.severity} />
                    <span className={styles.ruleMetric}>{METRIC_LABELS[r.metric] || r.metric}</span>
                    <span className={styles.ruleThreshold}>
                      {THRESHOLD_TYPE_LABELS[r.threshold_type]} {r.threshold_value}
                    </span>
                    <span className={styles.ruleCooldown}>冷却 {r.cooldown_minutes}分钟</span>
                    <span style={{ flex: 1 }} />
                    {r.enabled && (
                      <ZButton onClick={() => handleDisableRule(r.id)}>禁用</ZButton>
                    )}
                    {!r.enabled && (
                      <span className={styles.ruleStatus}>已禁用</span>
                    )}
                  </div>
                ))}
              </div>
            ) : <ZEmpty text="暂无预警规则" />}

            {/* New rule form */}
            <div className={styles.ruleForm}>
              <div className={styles.ruleFormTitle}>新建预警规则</div>
              <div className={styles.formGrid}>
                <div className={styles.formRow}>
                  <label className={styles.formLabel}>监控指标</label>
                  <select
                    className={styles.formSelect}
                    value={ruleForm.metric}
                    onChange={e => setRuleForm(f => ({ ...f, metric: e.target.value }))}
                  >
                    {SUPPORTED_METRICS.map(m => (
                      <option key={m} value={m}>{METRIC_LABELS[m] || m}</option>
                    ))}
                  </select>
                </div>
                <div className={styles.formRow}>
                  <label className={styles.formLabel}>触发条件</label>
                  <select
                    className={styles.formSelect}
                    value={ruleForm.threshold_type}
                    onChange={e => setRuleForm(f => ({ ...f, threshold_type: e.target.value }))}
                  >
                    <option value="above">超过</option>
                    <option value="below">低于</option>
                    <option value="abs_above">绝对值超过</option>
                  </select>
                </div>
                <div className={styles.formRow}>
                  <label className={styles.formLabel}>阈值</label>
                  <input
                    className={styles.formInput}
                    type="number"
                    value={ruleForm.threshold_value}
                    onChange={e => setRuleForm(f => ({ ...f, threshold_value: e.target.value }))}
                    placeholder="例: 10"
                  />
                </div>
                <div className={styles.formRow}>
                  <label className={styles.formLabel}>严重度</label>
                  <select
                    className={styles.formSelect}
                    value={ruleForm.severity}
                    onChange={e => setRuleForm(f => ({ ...f, severity: e.target.value }))}
                  >
                    <option value="info">提示</option>
                    <option value="warning">告警</option>
                    <option value="critical">严重</option>
                  </select>
                </div>
                <div className={styles.formRow}>
                  <label className={styles.formLabel}>冷却 (分钟)</label>
                  <input
                    className={styles.formInput}
                    type="number"
                    value={ruleForm.cooldown_minutes}
                    onChange={e => setRuleForm(f => ({ ...f, cooldown_minutes: e.target.value }))}
                    placeholder="60"
                  />
                </div>
              </div>
              <div className={styles.formActions}>
                <ZButton onClick={handleCreateRule} disabled={submittingRule || !ruleForm.threshold_value}>
                  {submittingRule ? '创建中…' : '创建规则'}
                </ZButton>
              </div>
            </div>
          </div>
        )}
      </ZCard>
    </div>
  );
};

export default FinancialAlertsPage;
