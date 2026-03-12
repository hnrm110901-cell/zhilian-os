import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { Switch } from 'antd';
import {
  InboxOutlined,
  CheckCircleOutlined,
  RiseOutlined,
  DashboardOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';
import { decisionAgentService, type DecisionReport } from '../services/decisionAgent';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton } from '../design-system/components';
import styles from './Dashboard.module.css';

const Dashboard: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [healthStatus, setHealthStatus] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [decisionReport, setDecisionReport] = useState<DecisionReport | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval] = useState(30000); // 30秒
  const [lastRefreshTime, setLastRefreshTime] = useState<Date>(new Date());

  const loadDashboardData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [health, report] = await Promise.all([
        apiClient.healthCheck(),
        decisionAgentService.getDecisionReport(),
      ]);

      setHealthStatus(health);
      setDecisionReport(report);
      setLastRefreshTime(new Date());
    } catch (err: any) {
      handleApiError(err, '加载仪表盘数据失败');
      setError(err.message || '无法加载数据');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboardData();

    let intervalId: number | undefined;
    if (autoRefresh) {
      intervalId = window.setInterval(() => {
        loadDashboardData();
      }, refreshInterval);
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [autoRefresh, refreshInterval, loadDashboardData]);

  const handleManualRefresh = useCallback(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  const kpiChartData = useMemo(() => {
    if (!decisionReport) return null;
    const kpis = decisionReport.kpi_summary.key_kpis;
    const revenueKPIs = kpis.filter((k: any) => k.category === 'revenue');
    return {
      categories: revenueKPIs.map((k: any) => k.metric_name),
      achievementRates: revenueKPIs.map((k: any) => k.achievement_rate * 100),
    };
  }, [decisionReport]);

  const kpiAchievementOption = useMemo(() => {
    if (!kpiChartData) return {};
    return {
      title: { text: 'KPI达成率', left: 'center' },
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          let r = params[0].name + '<br/>';
          params.forEach((p: any) => { r += `${p.marker}${p.seriesName}: ${p.value.toFixed(1)}%<br/>`; });
          return r;
        },
      },
      legend: { data: ['达成率', '目标线'], bottom: 10 },
      xAxis: { type: 'category', data: kpiChartData.categories, axisLabel: { interval: 0, rotate: 30 } },
      yAxis: { type: 'value', name: '达成率(%)', max: 120 },
      series: [
        {
          name: '达成率',
          data: kpiChartData.achievementRates,
          type: 'bar',
          itemStyle: {
            color: (params: any) => {
              const v = params.value;
              if (v >= 95) return '#1A7A52';
              if (v >= 85) return '#faad14';
              return '#C53030';
            },
          },
        },
        {
          name: '目标线',
          data: kpiChartData.categories.map(() => 100),
          type: 'line',
          itemStyle: { color: '#0AAF9A' },
          lineStyle: { type: 'dashed' },
        },
      ],
    };
  }, [kpiChartData]);

  const kpiStatusOption = useMemo(() => {
    if (!decisionReport) return {};
    const dist = decisionReport.kpi_summary.status_distribution;
    return {
      title: { text: 'KPI状态分布', left: 'center' },
      tooltip: { trigger: 'item', formatter: '{a} <br/>{b}: {c} ({d}%)' },
      legend: { orient: 'vertical', left: 'left', top: 'middle' },
      series: [{
        name: 'KPI数量',
        type: 'pie',
        radius: '50%',
        data: [
          { value: dist.on_track  || 0, name: '正常', itemStyle: { color: '#1A7A52' } },
          { value: dist.at_risk   || 0, name: '风险', itemStyle: { color: '#faad14' } },
          { value: dist.off_track || 0, name: '异常', itemStyle: { color: '#C53030' } },
        ],
        emphasis: { itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.5)' } },
      }],
    };
  }, [decisionReport]);

  if (loading) return <ZSkeleton rows={4} block />;

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <div>
          <h2 className={styles.pageTitle}>控制台</h2>
          <p className={styles.pageSub}>最后更新：{lastRefreshTime.toLocaleTimeString('zh-CN')}</p>
        </div>
        <div className={styles.headerActions}>
          <ZButton icon={<ReloadOutlined />} onClick={handleManualRefresh} disabled={loading}>
            刷新
          </ZButton>
          <span className={styles.toggleLabel}>自动刷新</span>
          <Switch
            checked={autoRefresh}
            onChange={setAutoRefresh}
            checkedChildren="开"
            unCheckedChildren="关"
          />
        </div>
      </div>

      {/* 错误 / 成功 Banner */}
      {error && (
        <div className={`${styles.alertBar} ${styles.alertError}`} style={{ marginBottom: 16 }}>
          <strong>数据加载失败：</strong>{error}
          <ZButton
            style={{ marginLeft: 12 }}
            onClick={() => { setError(null); handleManualRefresh(); }}
          >
            重试
          </ZButton>
        </div>
      )}
      {healthStatus && !error && (
        <div className={`${styles.alertBar} ${styles.alertSuccess}`} style={{ marginBottom: 16 }}>
          系统状态正常 — {healthStatus.status}
        </div>
      )}

      {/* 健康分数大卡 */}
      {decisionReport && (
        <ZCard style={{ marginBottom: 14, background: 'var(--primary-gradient)', border: 'none' }}>
          <div className={styles.heroRow}>
            <div className={styles.heroLeft}>
              <div className={styles.heroTitle}>
                <DashboardOutlined /> 系统健康分数
              </div>
              <div className={styles.heroScore}>
                {decisionReport.overall_health_score.toFixed(1)}
              </div>
              <div className={styles.heroSub}>
                {decisionReport.kpi_summary.total_kpis} 个KPI指标 &nbsp;|&nbsp;
                {decisionReport.action_required} 项需要关注
              </div>
            </div>
            <div className={styles.heroBadges}>
              <ZBadge type="success" text={`${decisionReport.kpi_summary.status_distribution.on_track  || 0} 正常`} />
              <ZBadge type="warning" text={`${decisionReport.kpi_summary.status_distribution.at_risk   || 0} 风险`} />
              <ZBadge type="critical" text={`${decisionReport.kpi_summary.status_distribution.off_track || 0} 异常`} />
            </div>
          </div>
        </ZCard>
      )}

      {/* KPI 概览 */}
      <div className={styles.kpiGrid}>
        <ZCard>
          <ZKpi
            value={decisionReport?.kpi_summary.total_kpis || 0}
            label="KPI总数"
          />
        </ZCard>
        <ZCard>
          <ZKpi
            value={decisionReport?.insights_summary.total_insights || 0}
            unit={`/ ${decisionReport?.insights_summary.high_impact || 0} 高影响`}
            label="业务洞察"
          />
        </ZCard>
        <ZCard>
          <ZKpi
            value={decisionReport?.action_required || 0}
            label="待处理建议"
          />
        </ZCard>
        <ZCard>
          <ZKpi
            value={decisionReport ? (decisionReport.kpi_summary.on_track_rate * 100).toFixed(1) : '0.0'}
            unit="%"
            label="KPI达标率"
            change={decisionReport ? (decisionReport.kpi_summary.on_track_rate >= 0.8 ? 5.2 : -5.2) : undefined}
            changeLabel="较上期"
          />
        </ZCard>
      </div>

      {/* 图表行 */}
      <div className={styles.twoColGrid} style={{ marginBottom: 14 }}>
        <ZCard>
          {decisionReport
            ? <ReactECharts option={kpiAchievementOption} style={{ height: 320 }} />
            : <ZSkeleton rows={3} block />}
        </ZCard>
        <ZCard>
          {decisionReport
            ? <ReactECharts option={kpiStatusOption} style={{ height: 320 }} />
            : <ZSkeleton rows={3} block />}
        </ZCard>
      </div>

      {/* 洞察 + 系统信息 */}
      <div className={styles.twoColGrid}>
        <ZCard title="关键业务洞察">
          {decisionReport?.insights_summary.key_insights.slice(0, 3).map((insight: any, index: number) => (
            <div
              key={insight.insight_id}
              style={{
                marginBottom: 16,
                paddingBottom: 16,
                borderBottom: index < 2 ? '1px solid var(--border)' : 'none',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <strong style={{ fontSize: 15 }}>{insight.title}</strong>
                <ZBadge
                  type={insight.impact_level === 'high' ? 'critical' : insight.impact_level === 'medium' ? 'warning' : 'info'}
                  text={insight.impact_level === 'high' ? '高影响' : insight.impact_level === 'medium' ? '中影响' : '低影响'}
                />
              </div>
              <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: 0 }}>
                {insight.description}
              </p>
            </div>
          )) || (
            <p style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '32px 0' }}>
              暂无洞察数据
            </p>
          )}
        </ZCard>

        <ZCard title="系统信息">
          <div className={styles.infoList}>
            <div className={styles.infoRow}>
              <span className={styles.infoLabel}>版本</span>
              <span className={styles.infoValue}>0.1.0</span>
            </div>
            <div className={styles.infoRow}>
              <span className={styles.infoLabel}>Agent数量</span>
              <span className={styles.infoValue}>7个</span>
            </div>
            <div className={styles.infoRow}>
              <span className={styles.infoLabel}>API状态</span>
              <ZBadge type={healthStatus ? 'success' : 'critical'} text={healthStatus ? '正常' : '异常'} />
            </div>
            <div className={styles.infoRow}>
              <span className={styles.infoLabel}>最后更新</span>
              <span className={styles.infoValue}>{new Date().toLocaleString('zh-CN')}</span>
            </div>
            {decisionReport && (
              <>
                <div className={styles.infoDivider} />
                <div className={styles.infoRow}>
                  <span className={styles.infoLabel}>报告时间</span>
                  <span className={styles.infoValue}>{new Date(decisionReport.report_date).toLocaleString('zh-CN')}</span>
                </div>
                <div className={styles.infoRow}>
                  <span className={styles.infoLabel}>门店ID</span>
                  <span className={styles.infoValue}>{decisionReport.store_id}</span>
                </div>
                <div className={styles.infoRow}>
                  <span className={styles.infoLabel}>健康分数</span>
                  <span style={{ fontWeight: 600, fontSize: 16, color: 'var(--accent)' }}>
                    {decisionReport.overall_health_score.toFixed(1)}/100
                  </span>
                </div>
              </>
            )}
          </div>
        </ZCard>
      </div>
    </div>
  );
};

export default Dashboard;
