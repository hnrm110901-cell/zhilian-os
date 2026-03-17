import React, { useState, useEffect, useCallback } from 'react';
import { message } from 'antd';
import { useAuth } from '../../contexts/AuthContext';
import { weeklyReviewService } from '../../services/dailyOpsService';
import type { WeeklyReview as WeeklyReviewType } from '../../types/dailyOps';
import styles from './WeeklyReview.module.css';

// 获取本周一和周日
function getCurrentWeekRange(): { start: string; end: string } {
  const today = new Date();
  const dayOfWeek = today.getDay() || 7; // 0=周日→7
  const monday = new Date(today);
  monday.setDate(today.getDate() - dayOfWeek + 1);
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  const fmt = (d: Date) => d.toISOString().split('T')[0];
  return { start: fmt(monday), end: fmt(sunday) };
}

export default function WeeklyReview() {
  const { user } = useAuth();
  const storeId = user?.store_id ?? '';
  const { start: weekStart, end: weekEnd } = getCurrentWeekRange();

  const [review, setReview] = useState<WeeklyReviewType | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [managerSummary, setManagerSummary] = useState('');
  const [nextWeekPlan, setNextWeekPlan] = useState('');

  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const r = await weeklyReviewService.getStoreReview(storeId, weekStart, weekEnd);
      setReview(r);
      if (r.managerSummary) setManagerSummary(r.managerSummary);
      if (r.nextWeekPlan) setNextWeekPlan(r.nextWeekPlan);
    } catch {
      message.error('周复盘数据加载失败');
    } finally {
      setLoading(false);
    }
  }, [storeId, weekStart, weekEnd]);

  useEffect(() => { load(); }, [load]);

  const handleSubmit = async () => {
    if (!storeId || !review) return;
    if (!managerSummary.trim()) { message.error('请填写本周总结'); return; }
    if (!nextWeekPlan.trim()) { message.error('请填写下周计划'); return; }
    setSubmitting(true);
    try {
      const result = await weeklyReviewService.submitStoreReview(storeId, {
        weekStartDate: weekStart,
        weekEndDate: weekEnd,
        managerSummary,
        nextWeekPlan,
        nextWeekFocusTargets: review.nextWeekFocusTargets,
      });
      if (result.success) {
        message.success('周复盘已提交');
        load();
      }
    } catch {
      message.error('提交失败，请重试');
    } finally {
      setSubmitting(false);
    }
  };

  const pct = (v?: number) => v != null ? `${(v * 100).toFixed(1)}%` : '--';
  const yuan = (v?: number) => v != null ? `¥${v.toLocaleString('zh-CN', { minimumFractionDigits: 0 })}` : '--';

  const isSubmitted = review?.status === 'submitted' || review?.status === 'pending_review' || review?.status === 'approved';

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.title}>周复盘</div>
        <div className={styles.skeleton} />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <span className={styles.title}>周复盘</span>
        <span className={styles.weekRange}>{weekStart} ~ {weekEnd}</span>
      </div>

      {/* 系统摘要 */}
      {review?.systemSummary && (
        <div className={styles.systemSummary}>
          <span className={styles.summaryIcon}>🤖</span>
          <span>{review.systemSummary}</span>
        </div>
      )}

      {/* 核心周指标 */}
      {review && (
        <>
          <div className={styles.statsGrid}>
            <div className={styles.statCard}>
              <div className={styles.statLabel}>本周销售</div>
              <div className={styles.statValue}>{yuan(review.actualSalesAmount)}</div>
              {review.salesTargetAmount && (
                <div className={styles.statSub}>目标 {yuan(review.salesTargetAmount)}</div>
              )}
            </div>
            <div className={styles.statCard}>
              <div className={styles.statLabel}>目标达成</div>
              <div className={`${styles.statValue} ${(review.targetAchievementRate || 0) < 0.9 ? styles.statDanger : ''}`}>
                {pct(review.targetAchievementRate)}
              </div>
            </div>
            <div className={styles.statCard}>
              <div className={styles.statLabel}>周净利率</div>
              <div className={`${styles.statValue} ${(review.netProfitRate || 0) < 0.08 ? styles.statDanger : ''}`}>
                {pct(review.netProfitRate)}
              </div>
            </div>
            <div className={styles.statCard}>
              <div className={styles.statLabel}>异常天数</div>
              <div className={`${styles.statValue} ${(review.abnormalDayCount || 0) > 2 ? styles.statDanger : ''}`}>
                {review.abnormalDayCount ?? '--'}天
              </div>
            </div>
          </div>

          {/* 异常分布 */}
          <div className={styles.section}>
            <div className={styles.sectionTitle}>本周异常分布</div>
            <div className={styles.anomalyRow}>
              <div className={styles.anomalyItem}>
                <span className={styles.anomalyCount}>{review.costAbnormalDayCount ?? 0}</span>
                <span className={styles.anomalyLabel}>成本异常</span>
              </div>
              <div className={styles.anomalyItem}>
                <span className={styles.anomalyCount}>{review.discountAbnormalDayCount ?? 0}</span>
                <span className={styles.anomalyLabel}>折扣异常</span>
              </div>
              <div className={styles.anomalyItem}>
                <span className={styles.anomalyCount}>{review.laborAbnormalDayCount ?? 0}</span>
                <span className={styles.anomalyLabel}>人工异常</span>
              </div>
              <div className={styles.anomalyItem}>
                <span className={styles.anomalyCount}>{review.repeatedIssueCount ?? 0}</span>
                <span className={styles.anomalyLabel}>复发问题</span>
              </div>
            </div>
          </div>

          {/* 任务闭环 */}
          <div className={styles.section}>
            <div className={styles.sectionTitle}>任务闭环</div>
            <div className={styles.taskRow}>
              <div className={styles.taskItem} style={{color:'#52c41a'}}>
                <span className={styles.taskCount}>{review.closedTaskCount ?? 0}</span>
                <span className={styles.taskLabel}>已关闭</span>
              </div>
              <div className={styles.taskItem} style={{color:'#ff4d4f'}}>
                <span className={styles.taskCount}>{review.pendingTaskCount ?? 0}</span>
                <span className={styles.taskLabel}>未关闭</span>
              </div>
              <div className={styles.taskItem} style={{color:'#1890ff'}}>
                <span className={styles.taskCount}>{review.submittedTaskCount ?? 0}</span>
                <span className={styles.taskLabel}>总任务</span>
              </div>
            </div>
          </div>

          {/* 下周目标 */}
          {review.nextWeekFocusTargets && (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>下周重点目标</div>
              <div className={styles.targetRow}>
                {review.nextWeekFocusTargets.foodCostRateTarget != null && (
                  <div className={styles.targetItem}>
                    <span className={styles.targetLabel}>成本率</span>
                    <span className={styles.targetValue}>&lt;{pct(review.nextWeekFocusTargets.foodCostRateTarget)}</span>
                  </div>
                )}
                {review.nextWeekFocusTargets.discountRateTarget != null && (
                  <div className={styles.targetItem}>
                    <span className={styles.targetLabel}>折扣率</span>
                    <span className={styles.targetValue}>&lt;{pct(review.nextWeekFocusTargets.discountRateTarget)}</span>
                  </div>
                )}
                {review.nextWeekFocusTargets.laborCostRateTarget != null && (
                  <div className={styles.targetItem}>
                    <span className={styles.targetLabel}>人工率</span>
                    <span className={styles.targetValue}>&lt;{pct(review.nextWeekFocusTargets.laborCostRateTarget)}</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {/* 填写区域 */}
      {!isSubmitted ? (
        <div className={styles.form}>
          <div className={styles.field}>
            <label className={styles.label}>本周总结 <span className={styles.required}>*</span></label>
            <textarea
              className={styles.textarea}
              rows={4}
              placeholder="本周主要问题是什么？做了哪些改善？效果如何？"
              value={managerSummary}
              onChange={e => setManagerSummary(e.target.value)}
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>下周重点计划 <span className={styles.required}>*</span></label>
            <textarea
              className={styles.textarea}
              rows={3}
              placeholder="下周具体要做什么？谁来负责？何时完成？"
              value={nextWeekPlan}
              onChange={e => setNextWeekPlan(e.target.value)}
            />
          </div>
          <button
            className={styles.submitBtn}
            onClick={handleSubmit}
            disabled={submitting}
          >
            {submitting ? '提交中...' : '提交周复盘'}
          </button>
        </div>
      ) : (
        <div className={styles.submittedBlock}>
          <div>✅ 周复盘已提交</div>
          {review?.managerSummary && (
            <div className={styles.submittedContent}>
              <div className={styles.submittedLabel}>本周总结</div>
              <div>{review.managerSummary}</div>
              <div className={styles.submittedLabel} style={{marginTop:8}}>下周计划</div>
              <div>{review.nextWeekPlan}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
