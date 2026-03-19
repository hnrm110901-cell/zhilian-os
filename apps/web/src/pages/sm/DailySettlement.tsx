import React, { useState, useEffect, useCallback } from 'react';
import { message } from 'antd';
import { useAuth } from '../../contexts/AuthContext';
import { dailySettlementService, dailyMetricsService, warningService } from '../../services/dailyOpsService';
import type { StoreDailySettlement, StoreDailyMetric, WarningRecord } from '../../types/dailyOps';
import styles from './DailySettlement.module.css';

export default function DailySettlement() {
  const { user } = useAuth();
  const storeId = user?.store_id ?? '';
  const today = new Date().toISOString().split('T')[0];

  const [settlement, setSettlement] = useState<StoreDailySettlement | null>(null);
  const [metric, setMetric] = useState<StoreDailyMetric | null>(null);
  const [warnings, setWarnings] = useState<WarningRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // 表单
  const [managerComment, setManagerComment] = useState('');
  const [chefComment, setChefComment] = useState('');
  const [actionPlan, setActionPlan] = useState('');

  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const [s, m, w] = await Promise.allSettled([
        dailySettlementService.getDetail(storeId, today),
        dailyMetricsService.getByDate(storeId, today),
        warningService.listByDate(storeId, today),
      ]);
      if (s.status === 'fulfilled') {
        setSettlement(s.value);
        // 预填已有说明
        if (s.value.managerComment) setManagerComment(s.value.managerComment);
        if (s.value.chefComment) setChefComment(s.value.chefComment);
        if (s.value.nextDayActionPlan) setActionPlan(s.value.nextDayActionPlan);
      }
      if (m.status === 'fulfilled') setMetric(m.value);
      if (w.status === 'fulfilled') setWarnings(w.value);
    } finally {
      setLoading(false);
    }
  }, [storeId, today]);

  useEffect(() => { load(); }, [load]);

  const handleSubmit = async () => {
    if (!storeId) return;
    // 有红黄灯时必须填写说明
    if (settlement?.warningLevel !== 'green' && !managerComment.trim()) {
      message.error('有异常预警时，店长说明不能为空');
      return;
    }
    if (!actionPlan.trim()) {
      message.error('明日动作计划不能为空');
      return;
    }
    setSubmitting(true);
    try {
      const result = await dailySettlementService.submit({
        storeId,
        bizDate: today,
        managerComment,
        chefComment,
        nextDayActionPlan: actionPlan,
      });
      if (result.success) {
        message.success('日结提交成功，等待区域经理审核');
        load();
      }
    } catch {
      message.error('提交失败，请重试');
    } finally {
      setSubmitting(false);
    }
  };

  const yuan = (v?: number) => v != null ? `¥${v.toLocaleString('zh-CN', { minimumFractionDigits: 0 })}` : '--';
  const pct = (v?: number) => v != null ? `${(v * 100).toFixed(1)}%` : '--';

  const statusMap: Record<string, { label: string; color: string }> = {
    pending_collect: { label: '待取数', color: '#888' },
    pending_validate: { label: '待校验', color: '#888' },
    pending_confirm: { label: '待确认', color: '#1890ff' },
    abnormal_wait_comment: { label: '异常待说明', color: '#faad14' },
    submitted: { label: '已提交', color: '#52c41a' },
    pending_review: { label: '待审核', color: '#1890ff' },
    approved: { label: '已通过', color: '#52c41a' },
    returned: { label: '已退回', color: '#ff4d4f' },
    closed: { label: '已关闭', color: '#888' },
  };

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.header}><span className={styles.title}>日结提交</span></div>
        <div className={styles.skeleton} />
      </div>
    );
  }

  const isSubmitted = settlement?.status === 'submitted' || settlement?.status === 'pending_review' || settlement?.status === 'approved' || settlement?.status === 'closed';
  const statusInfo = statusMap[settlement?.status || 'pending_confirm'];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <span className={styles.title}>日结提交</span>
        <span className={styles.date}>{today}</span>
        <span className={styles.statusBadge} style={{ color: statusInfo?.color, borderColor: statusInfo?.color }}>
          {statusInfo?.label}
        </span>
      </div>

      {/* 自动摘要 */}
      {settlement?.autoSummary && (
        <div className={`${styles.summary} ${settlement.warningLevel === 'red' ? styles.summaryRed : settlement.warningLevel === 'yellow' ? styles.summaryYellow : styles.summaryGreen}`}>
          <span className={styles.summaryIcon}>{settlement.warningLevel === 'red' ? '🚨' : settlement.warningLevel === 'yellow' ? '⚠️' : '✅'}</span>
          <span>{settlement.autoSummary}</span>
        </div>
      )}

      {/* 核心指标摘要 */}
      {metric && (
        <div className={styles.metricsRow}>
          <div className={styles.metricItem}><span className={styles.metricLabel}>销售</span><span className={styles.metricValue}>{yuan(metric.totalSalesAmount)}</span></div>
          <div className={styles.metricItem}><span className={styles.metricLabel}>成本率</span><span className={`${styles.metricValue} ${metric.foodCostRate && metric.foodCostRate > 0.35 ? styles.danger : ''}`}>{pct(metric.foodCostRate)}</span></div>
          <div className={styles.metricItem}><span className={styles.metricLabel}>折扣率</span><span className={`${styles.metricValue} ${metric.discountRate && metric.discountRate > 0.12 ? styles.danger : ''}`}>{pct(metric.discountRate)}</span></div>
          <div className={styles.metricItem}><span className={styles.metricLabel}>净利润</span><span className={`${styles.metricValue} ${metric.netProfitAmount != null && metric.netProfitAmount < 0 ? styles.danger : styles.profit}`}>{yuan(metric.netProfitAmount)}</span></div>
        </div>
      )}

      {/* 预警列表 */}
      {warnings.length > 0 && (
        <div className={styles.warningSection}>
          <div className={styles.sectionTitle}>今日预警</div>
          {warnings.map(w => (
            <div key={w.id} className={`${styles.warningItem} ${w.warningLevel === 'red' ? styles.warningRed : styles.warningYellow}`}>
              <span>{w.warningLevel === 'red' ? '🔴' : '🟡'} {w.ruleName}</span>
              <span className={styles.warningVal}>实际 {w.actualValue != null ? `${(w.actualValue*100).toFixed(1)}%` : '--'} / 红线 {w.redThresholdValue ? `${(parseFloat(w.redThresholdValue)*100).toFixed(0)}%` : '--'}</span>
            </div>
          ))}
        </div>
      )}

      {/* 日结表单 */}
      {!isSubmitted ? (
        <div className={styles.form}>
          <div className={styles.field}>
            <label className={styles.label}>
              店长说明{settlement?.warningLevel !== 'green' && <span className={styles.required}> *必填</span>}
            </label>
            <textarea
              className={styles.textarea}
              rows={3}
              placeholder="请说明今日异常原因（如：晚市折扣活动导致折扣率偏高）"
              value={managerComment}
              onChange={e => setManagerComment(e.target.value)}
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>厨师长说明</label>
            <textarea
              className={styles.textarea}
              rows={2}
              placeholder="（可选）厨房成本、报损相关说明"
              value={chefComment}
              onChange={e => setChefComment(e.target.value)}
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>明日动作计划 <span className={styles.required}>*必填</span></label>
            <textarea
              className={styles.textarea}
              rows={3}
              placeholder="明天具体要做什么改善？（如：控制折扣审批，调整海鲜备货量）"
              value={actionPlan}
              onChange={e => setActionPlan(e.target.value)}
            />
          </div>
          <button
            className={styles.submitBtn}
            onClick={handleSubmit}
            disabled={submitting}
          >
            {submitting ? '提交中...' : '提交日结'}
          </button>
        </div>
      ) : (
        <div className={styles.submitted}>
          <div className={styles.submittedIcon}>✅</div>
          <div className={styles.submittedText}>
            {settlement?.status === 'approved' ? '日结已通过审核' : '日结已提交，等待审核'}
          </div>
          {settlement?.managerComment && (
            <div className={styles.commentBlock}>
              <div className={styles.commentLabel}>店长说明</div>
              <div className={styles.commentText}>{settlement.managerComment}</div>
            </div>
          )}
          {settlement?.nextDayActionPlan && (
            <div className={styles.commentBlock}>
              <div className={styles.commentLabel}>明日计划</div>
              <div className={styles.commentText}>{settlement.nextDayActionPlan}</div>
            </div>
          )}
          {settlement?.reviewComment && (
            <div className={styles.commentBlock}>
              <div className={styles.commentLabel}>审核意见</div>
              <div className={styles.commentText}>{settlement.reviewComment}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
