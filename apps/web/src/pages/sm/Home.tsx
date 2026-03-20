import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, InputNumber, message, Modal, Select } from 'antd';
import { useAuth } from '../../contexts/AuthContext';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty, HealthRing, UrgencyList,
} from '../../design-system/components';
import { queryHomeSummary } from '../../services/mobile.query.service';
import type { MobileHomeSummaryResponse } from '../../services/mobile.types';
import { apiClient } from '../../services/api';
import { handleApiError, showInfo, showSuccess } from '../../utils/message';
import RecommendationCard from '../../components/RecommendationCard';
import styles from './Home.module.css';

interface DailyDecision {
  has_decision: boolean;
  message?: string;
  decision?: {
    title: string;
    action: string;
    expected_saving_yuan: number;
    confidence_pct: number;
    severity: string;
    detail: string;
    executor: string;
    deadline_hours: number;
    category: string;
    source: string;
  };
  cumulative_saving_yuan?: number;
}

const SEVERITY_STYLE: Record<string, { bg: string; border: string; accent: string; label: string }> = {
  critical: { bg: '#FFF0F0', border: '#FFCDD2', accent: '#C53030', label: '紧急' },
  warning:  { bg: '#FFF3E0', border: '#FFE0B2', accent: '#8B5E00', label: '重要' },
  watch:    { bg: '#EDFCF9', border: '#B3EDE4', accent: '#066E5D', label: '关注' },
  ok:       { bg: '#EDFAF3', border: '#C8E6C9', accent: '#1A7A52', label: '正常' },
};

function greeting(): string {
  const h = new Date().getHours();
  if (h < 6) return '凌晨好';
  if (h < 11) return '早上好';
  if (h < 14) return '中午好';
  if (h < 18) return '下午好';
  return '晚上好';
}

const HEALTH_LEVEL_MAP: Record<string, { label: string; type: 'success' | 'info' | 'warning' | 'critical' }> = {
  excellent: { label: '优秀', type: 'success' },
  good: { label: '良好', type: 'info' },
  warning: { label: '需关注', type: 'warning' },
  critical: { label: '危险', type: 'critical' },
};

type AdviceStatus = 'pending' | 'confirmed' | 'rejected';

interface StaffingAdvicePayload {
  exists: boolean;
  advice_date: string;
  meal_period: 'morning' | 'lunch' | 'dinner' | 'all_day';
  status?: AdviceStatus;
  recommended_headcount?: number;
  current_scheduled_headcount?: number;
  estimated_saving_yuan?: number;
  estimated_overspend_yuan?: number;
  confidence_score?: number;
  position_breakdown?: Record<string, any>;
}

interface AdviceCardData {
  date: string;
  meal_period: 'morning' | 'lunch' | 'dinner' | 'all_day';
  recommended_headcount: number;
  confidence_score: number;
  position_requirements: Record<string, number>;
  estimated_labor_cost_yuan: number;
  status: AdviceStatus;
  source: 'advice' | 'forecast';
}

interface AdviceHistoryItem {
  advice_date: string;
  action?: 'confirmed' | 'modified' | 'rejected';
  rejection_reason_code?: string;
  rejection_reason_text?: string;
  rejection_reason?: string;
}

interface AdviceHistoryResp {
  total: number;
  confirmed_count: number;
  modified_count: number;
  rejected_count: number;
  rejection_reasons_top: string[];
  items: AdviceHistoryItem[];
}

const REJECT_REASON_OPTIONS = [
  { value: 'traffic_drop', label: '客流低于预期' },
  { value: 'budget_control', label: '预算压缩' },
  { value: 'staff_unavailable', label: '人手临时不可用' },
  { value: 'special_event', label: '临时活动调整' },
  { value: 'other', label: '其他' },
];

export default function SmHome() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const storeId = user?.store_id ?? '';
  const [data, setData] = useState<MobileHomeSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adviceLoading, setAdviceLoading] = useState(false);
  const [adviceSubmitting, setAdviceSubmitting] = useState(false);
  const [adviceModal, setAdviceModal] = useState(false);
  const [adviceForm] = Form.useForm();
  const [adviceMap, setAdviceMap] = useState<Record<'today' | 'tomorrow', AdviceCardData | null>>({
    today: null,
    tomorrow: null,
  });
  const [adviceHistory, setAdviceHistory] = useState<AdviceHistoryResp | null>(null);
  const [adviceKey, setAdviceKey] = useState<'today' | 'tomorrow'>('tomorrow');
  const [dailyDecision, setDailyDecision] = useState<DailyDecision | null>(null);
  const [decisionLoading, setDecisionLoading] = useState(true);
  const normalizePositionRequirements = (raw: Record<string, any> | undefined): Record<string, number> => {
    if (!raw) return {};
    const keys = ['morning', 'lunch', 'dinner'];
    if (keys.some((k) => typeof raw[k] === 'object' && raw[k] !== null)) {
      const merged: Record<string, number> = {};
      keys.forEach((k) => {
        const bucket = raw[k] || {};
        Object.entries(bucket).forEach(([name, count]) => {
          const n = Number(count || 0);
          merged[name] = (merged[name] || 0) + n;
        });
      });
      return merged;
    }
    return Object.fromEntries(
      Object.entries(raw).map(([k, v]) => [k, Number(v || 0)])
    );
  };

  const queryAdviceByDate = useCallback(async (dateStr: string): Promise<AdviceCardData | null> => {
    if (!storeId) return null;
    try {
      const adviceResp = await apiClient.get<StaffingAdvicePayload>(`/api/v1/workforce/stores/${storeId}/staffing-advice`, {
        params: { date: dateStr, meal_period: 'all_day' },
      });
      if (adviceResp.exists) {
        const savings = Number(adviceResp.estimated_saving_yuan || 0);
        const overspend = Number(adviceResp.estimated_overspend_yuan || 0);
        return {
          date: dateStr,
          meal_period: adviceResp.meal_period,
          recommended_headcount: Number(adviceResp.recommended_headcount || 0),
          confidence_score: Number(adviceResp.confidence_score || 0),
          position_requirements: normalizePositionRequirements(adviceResp.position_breakdown),
          estimated_labor_cost_yuan: Math.max(savings, overspend),
          status: (adviceResp.status as AdviceStatus) || 'pending',
          source: 'advice',
        };
      }
    } catch {
      // fallback to forecast
    }

    try {
      const forecast = await apiClient.get<any>(`/api/v1/workforce/stores/${storeId}/labor-forecast`, {
        params: { date: dateStr },
      });
      const periods = forecast?.periods || {};
      const selectedPeriod = periods.lunch ? 'lunch' : periods.dinner ? 'dinner' : 'morning';
      const period = periods[selectedPeriod] || {};
      return {
        date: dateStr,
        meal_period: selectedPeriod,
        recommended_headcount: Number(period.recommended_headcount ?? period.total_headcount_needed ?? 0),
        confidence_score: Number(period.confidence_score ?? forecast?.confidence ?? 0),
        position_requirements: normalizePositionRequirements(period.position_breakdown ?? period.position_requirements),
        estimated_labor_cost_yuan: Number(forecast?.estimated_labor_cost_yuan ?? 0),
        status: 'pending',
        source: 'forecast',
      };
    } catch {
      return null;
    }
  }, [storeId]);

  const loadStaffingAdvice = useCallback(async () => {
    if (!storeId) return;
    setAdviceLoading(true);
    try {
      const now = new Date();
      const today = now.toISOString().slice(0, 10);
      const tomorrow = new Date(now.getTime() + 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
      const [todayAdvice, tomorrowAdvice] = await Promise.all([
        queryAdviceByDate(today),
        queryAdviceByDate(tomorrow),
      ]);
      const history = await apiClient.get<AdviceHistoryResp>(`/api/v1/workforce/stores/${storeId}/staffing-advice/history`, {
        params: { days: 7 },
      });
      setAdviceMap({
        today: todayAdvice,
        tomorrow: tomorrowAdvice,
      });
      setAdviceHistory(history);
    } catch {
      setAdviceMap({ today: null, tomorrow: null });
      setAdviceHistory(null);
      message.warning('人力建议数据加载失败，已显示缓存');
    } finally {
      setAdviceLoading(false);
    }
  }, [queryAdviceByDate, storeId]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await queryHomeSummary();
      setData(resp);
    } catch {
      setError('数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDailyDecision = useCallback(async () => {
    if (!storeId) return;
    setDecisionLoading(true);
    try {
      const resp = await apiClient.get<DailyDecision>(`/api/v1/brain/stores/${storeId}/today`);
      setDailyDecision(resp);
    } catch {
      setDailyDecision(null);
    } finally {
      setDecisionLoading(false);
    }
  }, [storeId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadStaffingAdvice(); }, [loadStaffingAdvice]);
  useEffect(() => { loadDailyDecision(); }, [loadDailyDecision]);

  const submitAdvice = useCallback(async () => {
    const advice = adviceMap[adviceKey];
    if (!advice) return;
    if (advice.source !== 'advice') {
      showInfo('当前仅为预测视图，待 07:00 生成正式建议后可提交确认');
      return;
    }
    if (advice.status !== 'pending') {
      showInfo('该建议已处理，无需重复提交');
      return;
    }
    try {
      const values = await adviceForm.validateFields();
      setAdviceSubmitting(true);
      const resp = await apiClient.post<any>(`/api/v1/workforce/stores/${storeId}/staffing-advice/confirm`, {
        advice_date: advice.date,
        meal_period: advice.meal_period,
        action: values.action,
        modified_headcount: values.action === 'modified' ? values.modified_headcount : undefined,
        rejection_reason_code: values.action === 'rejected' ? values.rejection_reason_code : undefined,
        rejection_reason: values.action === 'rejected'
          ? values.rejection_reason_code === 'other'
            ? values.rejection_reason
            : REJECT_REASON_OPTIONS.find((x) => x.value === values.rejection_reason_code)?.label
          : undefined,
      });
      const impact = Number(resp?.cost_impact_yuan || 0);
      const impactLabel = impact === 0 ? '无额外成本影响' : impact > 0 ? `成本 +¥${Math.abs(impact).toFixed(0)}` : `成本 -¥${Math.abs(impact).toFixed(0)}`;
      showSuccess(`${resp?.message || '提交成功'}（${impactLabel}）`);
      setAdviceModal(false);
      adviceForm.resetFields();
      loadStaffingAdvice();
    } catch (err) {
      handleApiError(err, '提交人力建议失败');
    } finally {
      setAdviceSubmitting(false);
    }
  }, [adviceForm, adviceKey, adviceMap, loadStaffingAdvice, storeId]);

  const today = new Date().toLocaleDateString('zh-CN', {
    month: 'long', day: 'numeric', weekday: 'short',
  });

  const urgencyItems = (data?.top_tasks || []).map((t) => ({
    id: t.task_id,
    title: t.task_title,
    description: `截止 ${new Date(t.deadline_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`,
    urgency: (t.priority === 'p0_urgent' ? 'critical' : t.priority === 'p1_high' ? 'warning' : 'info') as 'critical' | 'warning' | 'info',
    action_label: t.task_status === 'in_progress' ? '去提交' : '去处理',
    onAction: () => navigate('/sm/tasks'),
  }));

  const selectedAdvice = adviceMap[adviceKey];
  const selectedAdviceDateLabel = adviceKey === 'today' ? '今日建议' : '明日建议';
  const statusTextMap: Record<AdviceStatus, string> = {
    pending: '待处理',
    confirmed: '已确认',
    rejected: '已拒绝',
  };
  const statusTypeMap: Record<AdviceStatus, 'success' | 'warning' | 'critical'> = {
    pending: 'warning',
    confirmed: 'success',
    rejected: 'critical',
  };
  const canSubmitAdvice = !!selectedAdvice && selectedAdvice.source === 'advice' && selectedAdvice.status === 'pending';
  const todayAdvice = adviceMap.today;
  const todayAdvicePending = !!todayAdvice && todayAdvice.source === 'advice' && todayAdvice.status === 'pending';
  const todayAdviceHandled = !!todayAdvice && todayAdvice.source === 'advice' && todayAdvice.status !== 'pending';
  const rejectionBreakdown = (() => {
    const list = (adviceHistory?.items || [])
      .filter((x) => x.action === 'rejected')
      .map((x) => x.rejection_reason_text || x.rejection_reason)
      .filter((x): x is string => !!x);
    if (!list.length) return [];
    const total = list.length;
    const map: Record<string, number> = {};
    list.forEach((x) => { map[x] = (map[x] || 0) + 1; });
    return Object.entries(map)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4)
      .map(([reason, count]) => ({
        reason,
        count,
        pct: Math.round((count / total) * 100),
      }));
  })();

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <div className={styles.greeting}>{greeting()}，{data?.role_name || '店长'}</div>
          <div className={styles.date}>{today} · {storeId}</div>
        </div>
        <ZButton variant="ghost" size="sm" onClick={() => { load(); loadStaffingAdvice(); loadDailyDecision(); }}>↺ 刷新</ZButton>
      </div>

      {loading && !data ? (
        <div className={styles.body}>
          <ZSkeleton block rows={3} style={{ gap: 16 }} />
        </div>
      ) : error ? (
        <div className={styles.body}>
          <ZEmpty
            icon="⚠️"
            title="加载失败"
            description={error}
            action={<ZButton size="sm" onClick={load}>重试</ZButton>}
          />
        </div>
      ) : (
        <div className={styles.body}>
          {(data?.unread_alerts_count || 0) > 0 && (
            <button className={styles.alertBanner} onClick={() => navigate('/sm/alerts')}>
              <span className={styles.alertIcon}>‼</span>
              <span className={styles.alertText}>{data?.unread_alerts_count} 条运营告警待处理，点击查看</span>
              <span className={styles.alertArrow}>›</span>
            </button>
          )}

          {(data?.edge_hub_status && (!data.edge_hub_status.hub_online || data.edge_hub_status.p1_alert_count > 0)) && (
            <button className={styles.alertBanner} onClick={() => navigate('/edge-hub/dashboard')}>
              <span className={styles.alertIcon}>📡</span>
              <span className={styles.alertText}>
                {!data.edge_hub_status.hub_online
                  ? '边缘主机离线，请检查硬件状态'
                  : `${data.edge_hub_status.p1_alert_count} 条P1硬件告警待处理`}
              </span>
              <span className={styles.alertArrow}>›</span>
            </button>
          )}

          {todayAdvicePending && (
            <button
              className={styles.adviceBannerPending}
              onClick={() => setAdviceKey('today')}
              type="button"
            >
              <span className={styles.alertIcon}>🧭</span>
              <span className={styles.alertText}>今日人力建议待处理，点击跳转处理</span>
              <span className={styles.alertArrow}>›</span>
            </button>
          )}

          {todayAdviceHandled && (
            <div className={styles.adviceBannerDone}>
              <span className={styles.alertIcon}>✅</span>
              <span className={styles.alertText}>
                今日人力建议已{todayAdvice?.status === 'confirmed' ? '确认' : todayAdvice?.status === 'rejected' ? '拒绝' : '处理'}
              </span>
            </div>
          )}

          {/* P1: 每日1决策 Hero Card */}
          {decisionLoading ? (
            <ZSkeleton block rows={3} />
          ) : dailyDecision?.has_decision && dailyDecision.decision ? (() => {
            const d = dailyDecision.decision;
            const sev = SEVERITY_STYLE[d.severity] || SEVERITY_STYLE.watch;
            return (
              <div
                className={styles.decisionHero}
                style={{ background: sev.bg, borderColor: sev.border }}
              >
                <div className={styles.decisionHeader}>
                  <ZBadge type={d.severity === 'critical' ? 'critical' : d.severity === 'warning' ? 'warning' : 'info'} text={sev.label} />
                  <span className={styles.decisionDeadline}>{d.deadline_hours}h 内完成</span>
                </div>
                <div className={styles.decisionTitle} style={{ color: sev.accent }}>{d.title}</div>
                <div className={styles.decisionAction}>{d.action}</div>
                <div className={styles.decisionMeta}>
                  <span className={styles.decisionSaving}>预计月省 ¥{d.expected_saving_yuan.toLocaleString()}</span>
                  <span className={styles.decisionConfidence}>置信度 {d.confidence_pct}%</span>
                  <span className={styles.decisionExecutor}>{d.executor}</span>
                </div>
                {d.detail && <div className={styles.decisionDetail}>{d.detail}</div>}
                {(dailyDecision.cumulative_saving_yuan || 0) > 0 && (
                  <div className={styles.decisionCumulative}>
                    本月AI累计帮您省：¥{dailyDecision.cumulative_saving_yuan!.toLocaleString()}
                  </div>
                )}
              </div>
            );
          })() : dailyDecision && !dailyDecision.has_decision ? (
            <div className={styles.decisionOk}>
              <span className={styles.decisionOkIcon}>&#10004;</span>
              <span>{dailyDecision.message || '今日经营状况良好'}</span>
            </div>
          ) : null}

          <div className={styles.kpiGrid}>
            <div className={styles.kpiCell}>
              <ZKpi label="今日营收" value={Math.round(data?.today_revenue_yuan || 0)} unit="元" size="md" />
            </div>
            <div className={styles.kpiCell}>
              <ZKpi label="食材成本率" value={data?.food_cost_pct ?? 0} unit="%" size="md" />
            </div>
            <div className={`${styles.kpiCell} ${(data?.pending_approvals_count || 0) > 0 ? styles.kpiCellAlert : ''}`}>
              <ZKpi label="待审批" value={data?.pending_approvals_count ?? 0} unit="项" size="md" />
            </div>
            <div className={styles.kpiCell}>
              <ZKpi label="排队等候" value={data?.waiting_count ?? 0} unit="组" size="md" />
            </div>
          </div>

          <ZCard
            title="门店健康指数"
            extra={data ? (
              <ZBadge
                type={HEALTH_LEVEL_MAP[data.health_level]?.type ?? 'info'}
                text={HEALTH_LEVEL_MAP[data.health_level]?.label ?? data.health_level}
              />
            ) : null}
          >
            <div className={styles.healthRow}>
              <HealthRing score={data?.health_score ?? 0} size={96} label="综合评分" />
              <div className={styles.healthMeta}>
                {data?.weakest_dimension && (
                  <div className={styles.weakDim}>
                    <span className={styles.weakLabel}>最弱维度</span>
                    <span className={styles.weakValue}>{data.weakest_dimension}</span>
                  </div>
                )}
                <div className={styles.healthStats}>
                  <div className={styles.statItem}>
                    <span className={styles.statValue}>{data?.today_shift ? `${data.today_shift.start_time}-${data.today_shift.end_time}` : '休息'}</span>
                    <span className={styles.statLabel}>今日班次</span>
                  </div>
                </div>
              </div>
            </div>
          </ZCard>

          <ZCard
            title="今日行动清单"
            subtitle={urgencyItems.length > 0 ? `${urgencyItems.length} 项待处理` : '暂无待处理'}
            extra={urgencyItems.length > 0 ? <ZButton variant="ghost" size="sm" onClick={() => navigate('/sm/tasks')}>全部 ›</ZButton> : null}
          >
            <UrgencyList items={urgencyItems} maxItems={3} />
          </ZCard>

          <ZCard title="人力建议卡（P1）" subtitle={selectedAdvice ? `${selectedAdvice.meal_period} 时段` : '暂无建议数据'}>
            <div className={styles.adviceSwitchRow}>
              <button
                className={`${styles.adviceSwitchBtn} ${adviceKey === 'today' ? styles.adviceSwitchBtnActive : ''}`}
                onClick={() => setAdviceKey('today')}
                type="button"
              >
                今日
              </button>
              <button
                className={`${styles.adviceSwitchBtn} ${adviceKey === 'tomorrow' ? styles.adviceSwitchBtnActive : ''}`}
                onClick={() => setAdviceKey('tomorrow')}
                type="button"
              >
                明日
              </button>
              {selectedAdvice && (
                <ZBadge type={statusTypeMap[selectedAdvice.status]} text={`${selectedAdviceDateLabel} · ${statusTextMap[selectedAdvice.status]}`} />
              )}
            </div>
            {adviceLoading ? (
              <ZSkeleton rows={3} />
            ) : !selectedAdvice ? (
              <ZEmpty title="暂无建议数据" />
            ) : (
              <div className={styles.staffingCard}>
                <div className={styles.staffingMetaRow}>
                  <span>建议排班人数</span>
                  <strong>{selectedAdvice.recommended_headcount} 人</strong>
                </div>
                <div className={styles.staffingMetaRow}>
                  <span>预测置信度</span>
                  <strong>{Math.round((selectedAdvice.confidence_score || 0) * 100)}%</strong>
                </div>
                <div className={styles.staffingMetaRow}>
                  <span>{selectedAdvice.source === 'advice' ? '预估节省/成本影响' : '预估人工成本'}</span>
                  <strong>¥{Math.round(selectedAdvice.estimated_labor_cost_yuan || 0).toLocaleString()}</strong>
                </div>
                {selectedAdvice.source !== 'advice' && (
                  <div className={styles.adviceHint}>当前为预测视图，尚未生成可确认建议（等待 07:00 推送）</div>
                )}
                <div className={styles.positionChips}>
                  {Object.entries(selectedAdvice.position_requirements || {}).map(([k, v]) => (
                    <span key={k} className={styles.positionChip}>{k} {v}人</span>
                  ))}
                </div>
                <div className={styles.staffingActions}>
                  <ZButton size="sm" variant="primary" disabled={!canSubmitAdvice} onClick={() => {
                    adviceForm.setFieldsValue({ action: 'confirmed' });
                    setAdviceModal(true);
                  }}>✅ 一键确认</ZButton>
                  <ZButton size="sm" variant="ghost" disabled={!canSubmitAdvice} onClick={() => {
                    adviceForm.setFieldsValue({ action: 'modified', modified_headcount: selectedAdvice.recommended_headcount });
                    setAdviceModal(true);
                  }}>✏️ 修改人数</ZButton>
                  <ZButton size="sm" variant="ghost" disabled={!canSubmitAdvice} onClick={() => {
                    adviceForm.setFieldsValue({ action: 'rejected' });
                    setAdviceModal(true);
                  }}>❌ 拒绝</ZButton>
                </div>
              </div>
            )}
          </ZCard>

          <ZCard title="近7天建议处理概览" subtitle={adviceHistory ? `${adviceHistory.total} 条记录` : '暂无记录'}>
            {adviceLoading ? (
              <ZSkeleton rows={2} />
            ) : !adviceHistory ? (
              <ZEmpty title="暂无处理记录" />
            ) : (
              <div className={styles.historyWrap}>
                <div className={styles.historyKpis}>
                  <span>确认 {adviceHistory.confirmed_count}</span>
                  <span>修改 {adviceHistory.modified_count}</span>
                  <span>拒绝 {adviceHistory.rejected_count}</span>
                </div>
                {adviceHistory.rejection_reasons_top.length > 0 && (
                  <div className={styles.historyReasons}>
                    高频拒绝原因：{adviceHistory.rejection_reasons_top.join('；')}
                  </div>
                )}
                {rejectionBreakdown.length > 0 && (
                  <div className={styles.reasonBars}>
                    {rejectionBreakdown.map((x) => (
                      <div key={x.reason} className={styles.reasonBarItem}>
                        <div className={styles.reasonBarHead}>
                          <span>{x.reason}</span>
                          <span>{x.pct}%</span>
                        </div>
                        <div className={styles.reasonBarTrack}>
                          <div className={styles.reasonBarFill} style={{ width: `${x.pct}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                <div className={styles.historyList}>
                  {adviceHistory.items.slice(0, 3).map((x, i) => (
                    <div key={`${x.advice_date}-${i}`} className={styles.historyItem}>
                      <span>{x.advice_date}</span>
                      <span>{x.action === 'confirmed' ? '已确认' : x.action === 'modified' ? '已修改确认' : x.action === 'rejected' ? '已拒绝' : '待处理'}</span>
                      {x.action === 'rejected' && (x.rejection_reason_text || x.rejection_reason)
                        ? <span className={styles.historyReasonTag}>{x.rejection_reason_text || x.rejection_reason}</span>
                        : <span>-</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </ZCard>

          <ZCard title="快捷操作">
            <div className={styles.quickGrid}>
              <button className={styles.quickBtn} onClick={() => navigate('/sm/shifts')}>
                <span className={styles.quickIcon}>🕒</span>
                <span className={styles.quickLabel}>班次打卡</span>
              </button>
              <button className={styles.quickBtn} onClick={() => navigate('/sm/tasks')}>
                <span className={styles.quickIcon}>✅</span>
                <span className={styles.quickLabel}>任务执行</span>
              </button>
              <button className={styles.quickBtn} onClick={() => navigate('/sm/decisions')}>
                <span className={styles.quickIcon}>📋</span>
                <span className={styles.quickLabel}>审批决策</span>
                {(data?.pending_approvals_count || 0) > 0 && <span className={styles.quickBadge}>{data?.pending_approvals_count}</span>}
              </button>
              <button className={styles.quickBtn} onClick={() => navigate('/sm/alerts')}>
                <span className={styles.quickIcon}>🔔</span>
                <span className={styles.quickLabel}>告警管理</span>
                {(data?.unread_alerts_count || 0) > 0 && <span className={styles.quickBadge}>{data?.unread_alerts_count}</span>}
              </button>
              <button className={styles.quickBtn} onClick={() => navigate('/edge-hub/dashboard')}>
                <span className={styles.quickIcon}>📡</span>
                <span className={styles.quickLabel}>硬件状态</span>
                {(data?.edge_hub_status?.p1_alert_count || 0) > 0 && (
                  <span className={`${styles.quickBadge} ${styles.quickBadgeWarn}`}>
                    {data!.edge_hub_status!.p1_alert_count}
                  </span>
                )}
              </button>
            </div>
          </ZCard>
        </div>
      )}

      {/* AI 经营推荐 */}
      <div style={{ margin: '0 12px 12px' }}>
        <RecommendationCard storeId={storeId} compact maxItems={3} />
      </div>

      <Modal
        title="处理人力建议"
        open={adviceModal}
        onCancel={() => setAdviceModal(false)}
        onOk={submitAdvice}
        confirmLoading={adviceSubmitting}
      >
        <Form form={adviceForm} layout="vertical" initialValues={{ action: 'confirmed' }}>
          <Form.Item label="处理动作" name="action" rules={[{ required: true }]}>
            <Select>
              <Select.Option value="confirmed">直接确认</Select.Option>
              <Select.Option value="modified">修改后确认</Select.Option>
              <Select.Option value="rejected">拒绝</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item noStyle shouldUpdate>
            {({ getFieldValue }) => (
              <>
                {getFieldValue('action') === 'modified' ? (
                  <>
                    <Form.Item label="修改后人数" name="modified_headcount" rules={[{ required: true, message: '请输入人数' }]}>
                      <InputNumber min={1} style={{ width: '100%' }} />
                    </Form.Item>
                    <div className={styles.modalHint}>
                      预计成本影响：
                      {(() => {
                        const base = selectedAdvice?.recommended_headcount || 0;
                        const modified = Number(getFieldValue('modified_headcount') || base);
                        const diff = (modified - base) * 200;
                        if (diff === 0) return ' 无变化';
                        return diff > 0 ? ` +¥${Math.abs(diff)}（增配）` : ` -¥${Math.abs(diff)}（降配）`;
                      })()}
                    </div>
                  </>
                ) : null}
                {getFieldValue('action') === 'rejected' ? (
                  <>
                    <Form.Item label="拒绝原因类型" name="rejection_reason_code" rules={[{ required: true, message: '请选择拒绝原因' }]}>
                      <Select placeholder="请选择原因">
                        {REJECT_REASON_OPTIONS.map((x) => (
                          <Select.Option key={x.value} value={x.value}>{x.label}</Select.Option>
                        )) : null}
                      </Select>
                    </Form.Item>
                    {getFieldValue('rejection_reason_code') === 'other' ? (
                      <Form.Item label="补充说明" name="rejection_reason" rules={[{ required: true, message: '请输入补充说明' }]}>
                        <Input placeholder="请输入原因" />
                      </Form.Item>
                    ) : null}
                  </>
                ) : null}
              </>
            )}
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
