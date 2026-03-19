import React, { useState, useEffect, useCallback } from 'react';
import { message } from 'antd';
import { useAuth } from '../../contexts/AuthContext';
import { dailyMetricsService, warningService } from '../../services/dailyOpsService';
import type { StoreDailyMetric, WarningRecord } from '../../types/dailyOps';
import styles from './DailyDashboard.module.css';

// 读取 ZCard, ZKpi, ZBadge, ZEmpty, ZSkeleton 后根据实际接口使用

export default function DailyDashboard() {
  const { user } = useAuth();
  const storeId = user?.store_id ?? '';
  const today = new Date().toISOString().split('T')[0]; // yyyy-MM-dd

  const [metric, setMetric] = useState<StoreDailyMetric | null>(null);
  const [warnings, setWarnings] = useState<WarningRecord[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const [m, w] = await Promise.allSettled([
        dailyMetricsService.getByDate(storeId, today),
        warningService.listByDate(storeId, today),
      ]);
      if (m.status === 'fulfilled') setMetric(m.value);
      if (w.status === 'fulfilled') setWarnings(w.value);
      const failCount = [m, w].filter(r => r.status === 'rejected').length;
      if (failCount > 0) message.warning('部分数据加载失败，已显示缓存');
    } finally {
      setLoading(false);
    }
  }, [storeId, today]);

  useEffect(() => { load(); }, [load]);

  const warningColorMap = { green: '#52c41a', yellow: '#faad14', red: '#ff4d4f' } as const;
  const warningLabelMap = { green: '正常', yellow: '黄灯', red: '红灯' } as const;

  // 格式化金额
  const yuan = (v?: number) => v != null ? `¥${v.toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}` : '--';
  // 格式化率
  const pct = (v?: number) => v != null ? `${(v * 100).toFixed(1)}%` : '--';

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.header}><span className={styles.title}>今日经营总览</span></div>
        <div className={styles.skeletonGrid}>
          {[1,2,3,4,5,6].map(i => <div key={i} className={styles.skeletonCard} />)}
        </div>
      </div>
    );
  }

  const level = metric?.warningLevel || 'green';

  return (
    <div className={styles.page}>
      {/* 顶部：日期 + 预警等级 */}
      <div className={styles.header}>
        <div>
          <span className={styles.title}>今日经营总览</span>
          <span className={styles.date}>{today}</span>
        </div>
        <span
          className={styles.warningBadge}
          style={{ background: level === 'green' ? '#f6ffed' : level === 'yellow' ? '#fffbe6' : '#fff2f0',
                   color: warningColorMap[level], border: `1px solid ${warningColorMap[level]}` }}
        >
          {warningLabelMap[level]}
        </span>
      </div>

      {/* 核心指标卡片网格 */}
      {metric ? (
        <>
          <div className={styles.kpiGrid}>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>总销售额</div>
              <div className={styles.kpiValue}>{yuan(metric.totalSalesAmount)}</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>实收</div>
              <div className={styles.kpiValue}>{yuan(metric.actualReceiptsAmount)}</div>
            </div>
            <div className={`${styles.kpiCard} ${metric.foodCostRate && metric.foodCostRate > 0.35 ? styles.danger : metric.foodCostRate && metric.foodCostRate > 0.33 ? styles.warning : ''}`}>
              <div className={styles.kpiLabel}>菜品成本率</div>
              <div className={styles.kpiValue}>{pct(metric.foodCostRate)}</div>
              <div className={styles.kpiThreshold}>目标 &lt;33%</div>
            </div>
            <div className={`${styles.kpiCard} ${metric.discountRate && metric.discountRate > 0.12 ? styles.danger : metric.discountRate && metric.discountRate > 0.10 ? styles.warning : ''}`}>
              <div className={styles.kpiLabel}>折扣率</div>
              <div className={styles.kpiValue}>{pct(metric.discountRate)}</div>
              <div className={styles.kpiThreshold}>目标 &lt;10%</div>
            </div>
            <div className={`${styles.kpiCard} ${metric.laborCostRate && metric.laborCostRate > 0.20 ? styles.danger : metric.laborCostRate && metric.laborCostRate > 0.18 ? styles.warning : ''}`}>
              <div className={styles.kpiLabel}>人工率</div>
              <div className={styles.kpiValue}>{pct(metric.laborCostRate)}</div>
              <div className={styles.kpiThreshold}>目标 &lt;18%</div>
            </div>
            <div className={`${styles.kpiCard} ${metric.netProfitRate != null && metric.netProfitRate < 0 ? styles.danger : metric.netProfitRate != null && metric.netProfitRate < 0.08 ? styles.warning : ''}`}>
              <div className={styles.kpiLabel}>净利率</div>
              <div className={`${styles.kpiValue} ${metric.netProfitRate != null && metric.netProfitRate < 0 ? styles.negative : ''}`}>{pct(metric.netProfitRate)}</div>
              <div className={styles.kpiThreshold}>目标 &gt;8%</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>净利润</div>
              <div className={`${styles.kpiValue} ${metric.netProfitAmount != null && metric.netProfitAmount < 0 ? styles.negative : styles.positive}`}>{yuan(metric.netProfitAmount)}</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>堂食占比</div>
              <div className={styles.kpiValue}>{pct(metric.dineInSalesRate)}</div>
            </div>
          </div>

          {/* 渠道分布 */}
          <div className={styles.section}>
            <div className={styles.sectionTitle}>渠道分布</div>
            <div className={styles.channelRow}>
              <div className={styles.channelItem}>
                <span className={styles.channelDot} style={{background:'#FF6B2C'}} />
                <span>堂食 {yuan(metric.dineInSalesAmount)}</span>
              </div>
              <div className={styles.channelItem}>
                <span className={styles.channelDot} style={{background:'#1890ff'}} />
                <span>外卖 {yuan(metric.deliverySalesAmount)}</span>
              </div>
            </div>
          </div>

          {/* 预警列表 */}
          {warnings.length > 0 && (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>今日预警 ({warnings.length})</div>
              <div className={styles.warningList}>
                {warnings.map(w => (
                  <div key={w.id} className={`${styles.warningItem} ${w.warningLevel === 'red' ? styles.warningRed : styles.warningYellow}`}>
                    <span className={styles.warningIcon}>{w.warningLevel === 'red' ? '🔴' : '🟡'}</span>
                    <span className={styles.warningName}>{w.ruleName}</span>
                    <span className={styles.warningValue}>实际 {w.actualValue != null ? `${(w.actualValue * 100).toFixed(1)}%` : '--'}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      ) : (
        <div className={styles.empty}>
          <div className={styles.emptyIcon}>📊</div>
          <div className={styles.emptyText}>今日数据同步中，请稍后刷新</div>
          <button className={styles.refreshBtn} onClick={load}>刷新</button>
        </div>
      )}

      {/* 底部操作 */}
      <div className={styles.actions}>
        <a href="/sm/daily-settlement" className={styles.actionBtn} style={{background:'var(--accent,#FF6B2C)',color:'#fff'}}>
          进入日结提交
        </a>
        <a href="/sm/tasks" className={styles.actionBtnOutline}>
          查看异常任务
        </a>
      </div>
    </div>
  );
}
