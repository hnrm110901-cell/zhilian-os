import React, { useState, useEffect, useCallback, useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty } from '../design-system/components';
import { apiClient, handleApiError } from '../services/api';
import styles from './FinanceHealthPage.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

interface HealthScore {
  store_id: string;
  period: string;
  total_score: number;
  grade: string;
  profit_score: number;
  cash_score: number;
  tax_score: number;
  settlement_score: number;
  budget_score: number;
  profit_margin_pct: number | null;
  net_revenue_yuan: number | null;
  cash_gap_days: number | null;
  avg_tax_deviation_pct: number | null;
  high_risk_settlement: number | null;
  budget_achievement_pct: number | null;
  computed_at: string | null;
}

interface HealthTrend {
  period: string;
  total_score: number;
  grade: string;
  profit_score: number;
  cash_score: number;
  tax_score: number;
  settlement_score: number;
  budget_score: number;
}

interface ProfitTrend {
  period: string;
  net_revenue_yuan: number;
  gross_profit_yuan: number;
  profit_margin_pct: number;
  food_cost_yuan: number;
  total_cost_yuan: number;
}

interface Insight {
  id: string;
  insight_type: string;
  priority: string;
  content: string;
}

interface Dashboard {
  store_id: string;
  period: string;
  score: HealthScore | null;
  insights: Insight[];
  profit_trend: ProfitTrend[];
  health_trend: HealthTrend[];
}

// ── Constants ─────────────────────────────────────────────────────────────────

const STORE_ID = localStorage.getItem('store_id') || 'store-demo-001';
const today    = new Date().toISOString().slice(0, 10);
const period   = today.slice(0, 7);

const GRADE_COLOR: Record<string, string> = {
  A: '#52c41a', B: '#faad14', C: '#fa8c16', D: '#f5222d',
};
const PRIORITY_BADGE: Record<string, 'error' | 'warning' | 'neutral'> = {
  high: 'error', medium: 'warning', low: 'neutral',
};
const PRIORITY_LABEL: Record<string, string> = {
  high: '高', medium: '中', low: '低',
};
const TYPE_ICON: Record<string, string> = {
  profit: '💰', cash: '💧', tax: '📋', settlement: '🏦', budget: '📊', overall: '⭐',
};

// ── Component ─────────────────────────────────────────────────────────────────

const FinanceHealthPage: React.FC = () => {
  const [dashboard,  setDashboard]  = useState<Dashboard | null>(null);
  const [loading,    setLoading]    = useState(false);
  const [computing,  setComputing]  = useState(false);
  const [activeTab,  setActiveTab]  = useState<'score' | 'trend' | 'insights'>('score');

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/finance-health/dashboard/${STORE_ID}`, {
        params: { period },
      });
      setDashboard(res.data);
    } catch (e) { handleApiError(e); }
    finally { setLoading(false); }
  }, []);

  const handleCompute = async () => {
    setComputing(true);
    try {
      await apiClient.post(`/api/v1/finance-health/compute/${STORE_ID}`, null, {
        params: { period },
      });
      await loadDashboard();
    } catch (e) { handleApiError(e); }
    finally { setComputing(false); }
  };

  useEffect(() => { loadDashboard(); }, [loadDashboard]);

  const sc = dashboard?.score;

  // ── Gauge chart ─────────────────────────────────────────────────────────────

  const gaugeOption = useMemo(() => {
    if (!sc) return {};
    const gradeColor = GRADE_COLOR[sc.grade] || '#faad14';
    return {
      series: [{
        type:       'gauge',
        radius:     '85%',
        startAngle: 180,
        endAngle:   0,
        min: 0, max: 100,
        splitNumber: 4,
        axisLine: {
          lineStyle: {
            width: 18,
            color: [
              [0.40, '#f5222d'],
              [0.60, '#fa8c16'],
              [0.80, '#faad14'],
              [1.00, '#52c41a'],
            ],
          },
        },
        pointer: { length: '65%', width: 6, itemStyle: { color: gradeColor } },
        axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false },
        detail: {
          valueAnimation: true,
          formatter: `{value}\n${sc.grade}`,
          fontSize: 28,
          fontWeight: 700,
          color: gradeColor,
          offsetCenter: ['0%', '20%'],
          lineHeight: 36,
        },
        data: [{ value: Number(sc.total_score.toFixed(1)) }],
      }],
    };
  }, [sc]);

  // ── Dimension bar ───────────────────────────────────────────────────────────

  const dimBarOption = useMemo(() => {
    if (!sc) return {};
    const dims  = ['利润(30)', '现金(20)', '税务(20)', '结算(15)', '预算(15)'];
    const vals  = [sc.profit_score, sc.cash_score, sc.tax_score, sc.settlement_score, sc.budget_score];
    const maxes = [30, 20, 20, 15, 15];
    return {
      tooltip: { trigger: 'axis' },
      grid: { top: 8, bottom: 40, left: 70, right: 20 },
      xAxis: { type: 'category', data: dims, axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value', max: 30, axisLabel: { fontSize: 10 } },
      series: [{
        type: 'bar',
        data: vals.map((v, i) => ({
          value: Number(v),
          itemStyle: {
            color: Number(v) >= maxes[i] * 0.8 ? '#52c41a'
                 : Number(v) >= maxes[i] * 0.5 ? '#faad14' : '#f5222d',
          },
        })),
        barMaxWidth: 36,
        label: { show: true, position: 'top', fontSize: 11 },
      }],
    };
  }, [sc]);

  // ── Health trend line ────────────────────────────────────────────────────────

  const healthTrendOption = useMemo(() => {
    const ht = dashboard?.health_trend;
    if (!ht?.length) return {};
    return {
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0, itemHeight: 10, textStyle: { fontSize: 11 } },
      grid:   { top: 12, bottom: 50, left: 40, right: 16 },
      xAxis:  { type: 'category', data: ht.map(r => r.period), axisLabel: { fontSize: 10 } },
      yAxis:  { type: 'value', min: 0, max: 100, axisLabel: { fontSize: 10 } },
      series: [
        {
          name: '总评分',
          type: 'line',
          data: ht.map(r => Number(r.total_score)),
          lineStyle: { width: 3, color: '#FF6B2C' },
          symbol: 'circle', symbolSize: 6,
          itemStyle: { color: '#FF6B2C' },
          markLine: {
            data: [
              { yAxis: 80, lineStyle: { color: '#52c41a', type: 'dashed' }, label: { formatter: 'A', fontSize: 10 } },
              { yAxis: 60, lineStyle: { color: '#faad14', type: 'dashed' }, label: { formatter: 'B', fontSize: 10 } },
              { yAxis: 40, lineStyle: { color: '#f5222d', type: 'dashed' }, label: { formatter: 'C', fontSize: 10 } },
            ],
          },
        },
      ],
    };
  }, [dashboard]);

  // ── Profit trend dual-axis ───────────────────────────────────────────────────

  const profitTrendOption = useMemo(() => {
    const pt = dashboard?.profit_trend;
    if (!pt?.length) return {};
    return {
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0, itemHeight: 10, textStyle: { fontSize: 11 } },
      grid:   { top: 12, bottom: 50, left: 60, right: 60 },
      xAxis:  { type: 'category', data: pt.map(r => r.period), axisLabel: { fontSize: 10 } },
      yAxis: [
        {
          type: 'value', name: '利润率(%)', position: 'left',
          axisLabel: { fontSize: 10, formatter: '{value}%' },
        },
        {
          type: 'value', name: '收入(元)', position: 'right',
          axisLabel: { fontSize: 10, formatter: (v: number) => `¥${(v / 1000).toFixed(0)}k` },
        },
      ],
      series: [
        {
          name: '利润率',
          type: 'line',
          yAxisIndex: 0,
          data: pt.map(r => Number(r.profit_margin_pct.toFixed(1))),
          lineStyle: { color: '#52c41a', width: 2 },
          itemStyle: { color: '#52c41a' },
          symbol: 'circle', symbolSize: 5,
        },
        {
          name: '净收入',
          type: 'bar',
          yAxisIndex: 1,
          data: pt.map(r => r.net_revenue_yuan),
          itemStyle: { color: 'rgba(255,107,44,0.35)' },
          barMaxWidth: 28,
        },
      ],
    };
  }, [dashboard]);

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>财务健康评分</h1>
          <p className={styles.pageSub}>
            5维度综合评分 · 利润/现金/税务/结算/预算 · {period}
          </p>
        </div>
        <div className={styles.headerActions}>
          <ZButton onClick={handleCompute} disabled={computing}>
            {computing ? '计算中…' : '重新计算'}
          </ZButton>
          <ZButton onClick={loadDashboard}>刷新</ZButton>
        </div>
      </div>

      {/* KPI summary row */}
      <div className={styles.kpiGrid}>
        {loading && !sc ? (
          [...Array(5)].map((_, i) => <ZSkeleton key={i} height={88} />)
        ) : sc ? (
          <>
            <ZCard>
              <ZKpi label="综合评分" value={Number(sc.total_score.toFixed(1))} unit="分" />
              <div className={styles.kpiSub} style={{ color: GRADE_COLOR[sc.grade] }}>
                等级 {sc.grade}
              </div>
            </ZCard>
            <ZCard>
              <ZKpi label="利润率" value={`${(sc.profit_margin_pct ?? 0).toFixed(1)}%`} />
              <div className={styles.kpiSub}>利润评分 {Number(sc.profit_score).toFixed(1)}/30</div>
            </ZCard>
            <ZCard>
              <ZKpi label="现金缺口天数" value={sc.cash_gap_days ?? 0} unit="天" />
              <div className={(sc.cash_gap_days ?? 0) > 3 ? styles.kpiSubWarn : styles.kpiSub}>
                现金评分 {Number(sc.cash_score).toFixed(1)}/20
              </div>
            </ZCard>
            <ZCard>
              <ZKpi label="税务偏差率" value={`${(sc.avg_tax_deviation_pct ?? 0).toFixed(1)}%`} />
              <div className={(sc.avg_tax_deviation_pct ?? 0) > 10 ? styles.kpiSubWarn : styles.kpiSub}>
                税务评分 {Number(sc.tax_score).toFixed(1)}/20
              </div>
            </ZCard>
            <ZCard>
              <ZKpi label="高风险结算" value={sc.high_risk_settlement ?? 0} unit="笔" />
              <div className={(sc.high_risk_settlement ?? 0) > 0 ? styles.kpiSubWarn : styles.kpiSub}>
                结算评分 {Number(sc.settlement_score).toFixed(1)}/15
              </div>
            </ZCard>
          </>
        ) : (
          <div className={styles.noScore}>
            暂无评分数据，请点击「重新计算」生成本期健康评分
          </div>
        )}
      </div>

      {/* Main tabs */}
      <ZCard>
        <div className={styles.tabBar}>
          {(['score', 'trend', 'insights'] as const).map(tab => (
            <button
              key={tab}
              className={`${styles.tab} ${activeTab === tab ? styles.tabActive : ''}`}
              onClick={() => setActiveTab(tab)}
            >
              {{ score: '评分详情', trend: '历史趋势', insights: `洞察报告 (${dashboard?.insights.length ?? 0})` }[tab]}
            </button>
          ))}
        </div>

        {/* Score detail */}
        {activeTab === 'score' && (
          loading ? <ZSkeleton height={300} /> :
          sc ? (
            <div className={styles.scoreLayout}>
              <div className={styles.gaugeWrap}>
                <ReactECharts option={gaugeOption} style={{ height: '100%' }} />
                <div className={styles.gaugeLabel}>财务健康综合评分</div>
              </div>
              <div className={styles.dimChart}>
                <ReactECharts option={dimBarOption} style={{ height: '100%' }} />
              </div>
            </div>
          ) : <ZEmpty text="暂无评分，请点击「重新计算」" />
        )}

        {/* Trend */}
        {activeTab === 'trend' && (
          loading ? <ZSkeleton height={300} /> : (
            <div>
              {(dashboard?.health_trend.length ?? 0) > 0 ? (
                <>
                  <div className={styles.chartTitle}>健康评分趋势（近6期）</div>
                  <div className={styles.chart}>
                    <ReactECharts option={healthTrendOption} style={{ height: '100%' }} />
                  </div>
                </>
              ) : <ZEmpty text="暂无历史评分数据" />}

              {(dashboard?.profit_trend.length ?? 0) > 0 && (
                <>
                  <div className={styles.chartTitle} style={{ marginTop: 20 }}>利润率 + 净收入趋势</div>
                  <div className={styles.chart}>
                    <ReactECharts option={profitTrendOption} style={{ height: '100%' }} />
                  </div>
                </>
              )}
            </div>
          )
        )}

        {/* Insights */}
        {activeTab === 'insights' && (
          loading ? <ZSkeleton height={200} /> :
          (dashboard?.insights.length ?? 0) > 0 ? (
            <div className={styles.insightList}>
              {dashboard!.insights.map((ins, i) => (
                <div key={i} className={`${styles.insightCard} ${ins.priority === 'high' ? styles.insightHigh : ins.priority === 'medium' ? styles.insightMedium : ''}`}>
                  <div className={styles.insightHeader}>
                    <span className={styles.insightIcon}>{TYPE_ICON[ins.insight_type] || '📌'}</span>
                    <ZBadge type={PRIORITY_BADGE[ins.priority] || 'neutral'} text={PRIORITY_LABEL[ins.priority] || ins.priority} />
                    <span className={styles.insightType}>{ins.insight_type}</span>
                  </div>
                  <div className={styles.insightContent}>{ins.content}</div>
                </div>
              ))}
            </div>
          ) : <ZEmpty text="暂无洞察（请先计算评分）" />
        )}
      </ZCard>
    </div>
  );
};

export default FinanceHealthPage;
