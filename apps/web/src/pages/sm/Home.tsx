import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, InputNumber, Modal, Select } from 'antd';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty, HealthRing, UrgencyList,
} from '../../design-system/components';
import { queryHomeSummary } from '../../services/mobile.query.service';
import type { MobileHomeSummaryResponse } from '../../services/mobile.types';
import { apiClient } from '../../services/api';
import { handleApiError, showSuccess } from '../../utils/message';
import styles from './Home.module.css';

const STORE_ID = localStorage.getItem('store_id') || 'STORE001';

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

export default function SmHome() {
  const navigate = useNavigate();
  const [data, setData] = useState<MobileHomeSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adviceLoading, setAdviceLoading] = useState(false);
  const [adviceSubmitting, setAdviceSubmitting] = useState(false);
  const [adviceModal, setAdviceModal] = useState(false);
  const [adviceForm] = Form.useForm();
  const [advice, setAdvice] = useState<{
    date: string;
    meal_period: 'morning' | 'lunch' | 'dinner';
    recommended_headcount: number;
    confidence_score?: number;
    position_requirements?: Record<string, number>;
    estimated_labor_cost_yuan?: number;
  } | null>(null);

  const loadStaffingAdvice = useCallback(async () => {
    setAdviceLoading(true);
    try {
      const targetDate = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
      const resp = await apiClient.get<any>(`/api/v1/workforce/stores/${STORE_ID}/labor-forecast`, {
        params: { date: targetDate },
      });
      const periods = resp?.periods || {};
      const selectedPeriod = periods.lunch ? 'lunch' : periods.dinner ? 'dinner' : 'morning';
      const period = periods[selectedPeriod] || {};
      const recommended = Number(period.recommended_headcount ?? period.total_headcount_needed ?? 0);
      setAdvice({
        date: targetDate,
        meal_period: selectedPeriod,
        recommended_headcount: recommended,
        confidence_score: Number(period.confidence_score ?? resp?.confidence ?? 0),
        position_requirements: period.position_breakdown ?? period.position_requirements ?? {},
        estimated_labor_cost_yuan: Number(resp?.estimated_labor_cost_yuan ?? 0),
      });
    } catch {
      setAdvice(null);
    } finally {
      setAdviceLoading(false);
    }
  }, []);

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

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadStaffingAdvice(); }, [loadStaffingAdvice]);

  const submitAdvice = useCallback(async () => {
    if (!advice) return;
    try {
      const values = await adviceForm.validateFields();
      setAdviceSubmitting(true);
      await apiClient.post(`/api/v1/workforce/stores/${STORE_ID}/staffing-advice/confirm`, {
        advice_date: advice.date,
        meal_period: advice.meal_period,
        action: values.action,
        modified_headcount: values.action === 'modified' ? values.modified_headcount : undefined,
        rejection_reason: values.action === 'rejected' ? values.rejection_reason : undefined,
      });
      showSuccess(values.action === 'rejected' ? '已拒绝建议' : '人力建议已确认');
      setAdviceModal(false);
      adviceForm.resetFields();
      loadStaffingAdvice();
    } catch (err) {
      handleApiError(err, '提交人力建议失败');
    } finally {
      setAdviceSubmitting(false);
    }
  }, [advice, adviceForm, loadStaffingAdvice]);

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

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <div className={styles.greeting}>{greeting()}，{data?.role_name || '店长'}</div>
          <div className={styles.date}>{today} · {STORE_ID}</div>
        </div>
        <ZButton variant="ghost" size="sm" onClick={load}>↺ 刷新</ZButton>
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

          <ZCard title="明日人力建议" subtitle={advice ? `${advice.meal_period} 时段` : '暂无建议数据'}>
            {adviceLoading ? (
              <ZSkeleton rows={3} />
            ) : !advice ? (
              <ZEmpty title="暂无建议数据" />
            ) : (
              <div className={styles.staffingCard}>
                <div className={styles.staffingMetaRow}>
                  <span>建议排班人数</span>
                  <strong>{advice.recommended_headcount} 人</strong>
                </div>
                <div className={styles.staffingMetaRow}>
                  <span>预测置信度</span>
                  <strong>{Math.round((advice.confidence_score || 0) * 100)}%</strong>
                </div>
                <div className={styles.staffingMetaRow}>
                  <span>预估成本</span>
                  <strong>¥{Math.round(advice.estimated_labor_cost_yuan || 0).toLocaleString()}</strong>
                </div>
                <div className={styles.positionChips}>
                  {Object.entries(advice.position_requirements || {}).map(([k, v]) => (
                    <span key={k} className={styles.positionChip}>{k} {v}人</span>
                  ))}
                </div>
                <div className={styles.staffingActions}>
                  <ZButton size="sm" variant="primary" onClick={() => {
                    adviceForm.setFieldsValue({ action: 'confirmed' });
                    setAdviceModal(true);
                  }}>✅ 一键确认</ZButton>
                  <ZButton size="sm" variant="ghost" onClick={() => {
                    adviceForm.setFieldsValue({ action: 'modified', modified_headcount: advice.recommended_headcount });
                    setAdviceModal(true);
                  }}>✏️ 修改人数</ZButton>
                  <ZButton size="sm" variant="ghost" onClick={() => {
                    adviceForm.setFieldsValue({ action: 'rejected' });
                    setAdviceModal(true);
                  }}>❌ 拒绝</ZButton>
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
            </div>
          </ZCard>
        </div>
      )}

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
                  <Form.Item label="修改后人数" name="modified_headcount" rules={[{ required: true, message: '请输入人数' }]}>
                    <InputNumber min={1} style={{ width: '100%' }} />
                  </Form.Item>
                ) : null}
                {getFieldValue('action') === 'rejected' ? (
                  <Form.Item label="拒绝原因" name="rejection_reason" rules={[{ required: true, message: '请输入拒绝原因' }]}>
                    <Input placeholder="请输入原因" />
                  </Form.Item>
                ) : null}
              </>
            )}
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
