import React, { useState, useEffect, useCallback } from 'react';
import { Card, Select, Button, Tag, Table, Progress, Empty, Spin, Alert, Tooltip, Statistic } from 'antd';
import {
  ReloadOutlined,
  ThunderboltOutlined,
  RiseOutlined,
  FallOutlined,
  MinusOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { apiClient, handleApiError } from '../services/api';
import styles from './FinancialForecastPage.module.css';

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface ForecastItem {
  forecast_type: string;
  predicted_value: number | null;
  lower_bound: number | null;
  upper_bound: number | null;
  confidence_pct: number | null;
  method: string;
  based_on_periods: number | null;
  actual_value: number | null;
  accuracy_pct: number | null;
  label: string;
}

interface StoredForecast {
  store_id: string;
  target_period: string;
  forecasts: ForecastItem[];
}

interface ComputedForecast {
  store_id: string;
  target_period: string;
  revenue:        ComputedItem | null;
  food_cost_rate: ComputedItem | null;
  profit_margin:  ComputedItem | null;
  health_score:   ComputedItem | null;
}

interface ComputedItem {
  forecast_type: string;
  target_period: string;
  predicted_value: number;
  lower_bound: number;
  upper_bound: number;
  confidence_pct: number;
  trend_direction: 'up' | 'down' | 'flat';
  history: { period: string; value: number }[];
  label: string;
  based_on_periods: number;
}

interface AccuracyRecord {
  forecast_type: string;
  target_period: string;
  predicted_value: number;
  actual_value: number;
  accuracy_pct: number;
  label: string;
}

// ── 常量 ──────────────────────────────────────────────────────────────────────

const TYPE_COLORS: Record<string, string> = {
  revenue:        '#0AAF9A',
  food_cost_rate: '#C53030',
  profit_margin:  '#1A7A52',
  health_score:   '#722ed1',
};

const FORECAST_TYPES = ['revenue', 'food_cost_rate', 'profit_margin', 'health_score'] as const;

const TYPE_UNITS: Record<string, string> = {
  revenue:        '¥',
  food_cost_rate: '%',
  profit_margin:  '%',
  health_score:   '分',
};

// cost rate: lower is better; others: higher is better
const LOWER_IS_BETTER = new Set(['food_cost_rate']);

// ── 工具 ──────────────────────────────────────────────────────────────────────

const fmt = (v: number | null, unit: string) =>
  v == null ? '—' : unit === '¥'
    ? `¥${v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}`
    : `${v.toFixed(1)}${unit}`;

const trendIcon = (dir: 'up' | 'down' | 'flat', type: string) => {
  const good = LOWER_IS_BETTER.has(type) ? 'down' : 'up';
  if (dir === 'up') return <RiseOutlined style={{ color: dir === good ? '#1A7A52' : '#C53030' }} />;
  if (dir === 'down') return <FallOutlined style={{ color: dir === good ? '#1A7A52' : '#C53030' }} />;
  return <MinusOutlined style={{ color: '#8c8c8c' }} />;
};

// ── ECharts 工厂 ──────────────────────────────────────────────────────────────

const buildForecastChart = (
  item: ComputedItem,
  color: string,
) => {
  const hist  = item.history;
  const allPeriods = [...hist.map(h => h.period), item.target_period];
  const histLen = hist.length;

  // historical values
  const histValues: (number | null)[] = [...hist.map(h => h.value), null];
  // forecast point (last position)
  const fcastValues: (number | null)[] = [...Array(histLen).fill(null), item.predicted_value];
  // CI band: upper
  const upperValues: (number | null)[] = [...Array(histLen).fill(null), item.upper_bound];
  // CI lower (used as stack base)
  const lowerValues: (number | null)[] = [...Array(histLen).fill(null), item.lower_bound];
  const ciWidth: (number | null)[] = upperValues.map((u, i) =>
    u != null && lowerValues[i] != null ? u - lowerValues[i]! : null,
  );

  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any[]) => {
        const p = params[0];
        return `${p.axisValue}<br/>${p.seriesName}: ${p.value?.toFixed(2) ?? '—'}`;
      },
    },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: allPeriods, axisLabel: { fontSize: 10, rotate: 30 } },
    yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
    series: [
      {
        name: '历史',
        type: 'line',
        data: histValues,
        lineStyle: { color, width: 2 },
        symbol: 'circle', symbolSize: 4,
        itemStyle: { color },
        connectNulls: false,
      },
      {
        name: 'CI下沿',
        type: 'bar',
        stack: 'ci',
        data: lowerValues,
        itemStyle: { opacity: 0 },
        silent: true,
      },
      {
        name: 'CI区间',
        type: 'bar',
        stack: 'ci',
        data: ciWidth,
        itemStyle: { color, opacity: 0.15 },
        silent: true,
      },
      {
        name: '预测',
        type: 'scatter',
        data: fcastValues,
        symbol: 'diamond',
        symbolSize: 12,
        itemStyle: { color },
        label: {
          show: true,
          position: 'top',
          formatter: (p: any) => p.value?.toFixed(1) ?? '',
          fontSize: 11,
          fontWeight: 700,
        },
      },
    ],
  };
};

// ── 组件 ──────────────────────────────────────────────────────────────────────

const FinancialForecastPage: React.FC = () => {
  const [storeId, setStoreId]   = useState(localStorage.getItem('store_id') || '');
  const [targetPeriod, setTP]   = useState<string>(() => {
    const now = dayjs();
    const next = now.add(1, 'month');
    return next.format('YYYY-MM');
  });
  const [tab, setTab]           = useState<'detail' | 'accuracy'>('detail');
  const [computed, setComputed] = useState<ComputedForecast | null>(null);
  const [accuracy, setAccuracy] = useState<AccuracyRecord[]>([]);
  const [loading, setLoading]   = useState(false);
  const [computing, setComp]    = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [stores, setStores]     = useState<any[]>([]);

  useEffect(() => {
    apiClient.get('/api/v1/stores').then((res: any) => {
      setStores(res.stores || res || []);
    }).catch(() => {});
  }, []);

  const loadAccuracy = useCallback(async () => {
    try {
      const resp = await apiClient.get(`/api/v1/fin-forecast/accuracy/${storeId}`);
      setAccuracy(resp.data);
    } catch (_) {}
  }, [storeId]);

  const loadExisting = useCallback(async () => {
    try {
      const resp = await apiClient.get(`/api/v1/fin-forecast/${storeId}`, {
        params: { target_period: targetPeriod },
      });
      // Convert stored format to computed format for display
      const stored: StoredForecast = resp.data;
      const byType: Record<string, any> = {};
      for (const f of stored.forecasts) {
        byType[f.forecast_type] = {
          forecast_type:    f.forecast_type,
          target_period:    stored.target_period,
          predicted_value:  f.predicted_value ?? 0,
          lower_bound:      f.lower_bound ?? 0,
          upper_bound:      f.upper_bound ?? 0,
          confidence_pct:   f.confidence_pct ?? 95,
          trend_direction:  'flat' as const,
          history:          [],
          label:            f.label,
          based_on_periods: f.based_on_periods ?? 0,
        };
      }
      setComputed({ store_id: storeId, target_period: targetPeriod, ...byType as any });
    } catch (_) {}
  }, [storeId, targetPeriod]);

  useEffect(() => {
    loadExisting();
    loadAccuracy();
  }, [loadExisting, loadAccuracy]);

  const handleCompute = async () => {
    setComp(true);
    setError(null);
    try {
      const resp = await apiClient.post(`/api/v1/fin-forecast/compute/${storeId}`, null, {
        params: { target_period: targetPeriod },
      });
      setComputed(resp.data);
      await loadAccuracy();
    } catch (e) {
      setError(handleApiError(e));
    } finally {
      setComp(false);
    }
  };

  // ── 摘要 KPI 卡 ─────────────────────────────────────────────────────────────

  const kpiCards = FORECAST_TYPES.map(ft => {
    const item = computed?.[ft] as ComputedItem | null | undefined;
    const unit  = TYPE_UNITS[ft];
    const color = TYPE_COLORS[ft];
    return {
      ft, unit, color,
      label:     item?.label ?? ft,
      predicted: item?.predicted_value ?? null,
      lower:     item?.lower_bound ?? null,
      upper:     item?.upper_bound ?? null,
      trend:     item?.trend_direction ?? 'flat',
      nPeriods:  item?.based_on_periods ?? 0,
    };
  });

  // ── 精度表格 ────────────────────────────────────────────────────────────────

  const accuracyColumns = [
    { title: '类型',   dataIndex: 'label',           key: 'label',   width: 130 },
    { title: '期间',   dataIndex: 'target_period',   key: 'period',  width: 90 },
    {
      title: '预测值', dataIndex: 'predicted_value', key: 'predicted',
      render: (v: number, r: AccuracyRecord) => fmt(v, TYPE_UNITS[r.forecast_type]),
    },
    {
      title: '实际值', dataIndex: 'actual_value', key: 'actual',
      render: (v: number, r: AccuracyRecord) => fmt(v, TYPE_UNITS[r.forecast_type]),
    },
    {
      title: '精度',   dataIndex: 'accuracy_pct', key: 'acc',
      render: (v: number | null) => v == null ? '—' : (
        <Progress percent={Math.round(v)} size="small"
          strokeColor={v >= 90 ? '#1A7A52' : v >= 70 ? '#C8923A' : '#C53030'}
          format={p => `${v.toFixed(1)}%`}
        />
      ),
    },
  ];

  // ── render ────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.pageHeader}>
        <div>
          <h2 className={styles.pageTitle}>智能财务预测</h2>
          <p className={styles.pageSub}>4维预测 · 加权移动均值 · 95% 置信区间</p>
        </div>
        <div className={styles.headerActions}>
          <Select
            value={storeId}
            onChange={setStoreId}
            style={{ width: 140 }}
            options={stores.map((s: any) => ({ value: s.store_id || s.id, label: s.name || s.store_id || s.id }))}
          />
          <Select
            value={targetPeriod}
            onChange={setTP}
            style={{ width: 120 }}
            options={Array.from({ length: 6 }, (_, i) => {
              const m = dayjs().add(i + 1, 'month').format('YYYY-MM');
              return { value: m, label: m };
            })}
          />
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            onClick={handleCompute}
            loading={computing}
          >
            计算预测
          </Button>
        </div>
      </div>

      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 12 }} />}

      <Spin spinning={computing || loading}>
        {/* KPI 摘要卡 */}
        <div className={styles.kpiGrid}>
          {kpiCards.map(k => (
            <Card key={k.ft} size="small" className={styles.kpiCard}>
              <div className={styles.kpiLabel} style={{ color: k.color }}>{k.label}</div>
              <div className={styles.kpiValue}>
                {k.predicted == null ? '—' : fmt(k.predicted, k.unit)}
                <span className={styles.trendIcon}>{trendIcon(k.trend, k.ft)}</span>
              </div>
              {k.lower != null && k.upper != null && (
                <div className={styles.kpiCI}>
                  区间 [{fmt(k.lower, k.unit)}, {fmt(k.upper, k.unit)}]
                </div>
              )}
              {k.nPeriods > 0 && (
                <div className={styles.kpiSub}>基于 {k.nPeriods} 期历史</div>
              )}
            </Card>
          ))}
        </div>

        {/* Tabs */}
        <div className={styles.tabBar}>
          {[
            { key: 'detail',   label: '预测详情' },
            { key: 'accuracy', label: `精度追踪 (${accuracy.length})` },
          ].map(t => (
            <button
              key={t.key}
              className={`${styles.tab} ${tab === t.key ? styles.tabActive : ''}`}
              onClick={() => setTab(t.key as any)}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* 预测详情 Tab */}
        {tab === 'detail' && (
          computed == null ? (
            <Empty
              description={
                <span>
                  暂无预测数据。点击「计算预测」生成 {targetPeriod} 期的财务预测。
                  <br />
                  <small>需要至少 {2} 期历史数据（profit_attribution_results / finance_health_scores）。</small>
                </span>
              }
            />
          ) : (
            <div className={styles.chartsGrid}>
              {FORECAST_TYPES.map(ft => {
                const item = (computed as any)[ft] as ComputedItem | null;
                const color = TYPE_COLORS[ft];
                if (!item) {
                  return (
                    <Card key={ft} size="small" title={ft} className={styles.chartCard}>
                      <Empty description="历史数据不足（需≥2期）" />
                    </Card>
                  );
                }
                return (
                  <Card
                    key={ft}
                    size="small"
                    title={
                      <span>
                        <span style={{ color }}>{item.label}</span>
                        <span className={styles.chartMeta}>
                          {' '}· 目标期 {item.target_period}
                          {' '}· {trendIcon(item.trend_direction, ft)} {
                            item.trend_direction === 'up' ? '上升趋势' :
                            item.trend_direction === 'down' ? '下降趋势' : '平稳'
                          }
                        </span>
                      </span>
                    }
                    className={styles.chartCard}
                  >
                    {item.history.length > 0 ? (
                      <ReactECharts
                        option={buildForecastChart(item, color)}
                        style={{ height: 200 }}
                      />
                    ) : (
                      <div className={styles.noHistoryNote}>
                        <p className={styles.predictedBig} style={{ color }}>
                          {fmt(item.predicted_value, TYPE_UNITS[ft])}
                        </p>
                        <p className={styles.ciBand}>
                          95% CI：[{fmt(item.lower_bound, TYPE_UNITS[ft])}, {fmt(item.upper_bound, TYPE_UNITS[ft])}]
                        </p>
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>
          )
        )}

        {/* 精度追踪 Tab */}
        {tab === 'accuracy' && (
          accuracy.length === 0 ? (
            <Empty description="暂无已验证的预测记录（需先有实际数据回填）" />
          ) : (
            <div>
              {/* 精度汇总 */}
              <div className={styles.accSummaryGrid}>
                {FORECAST_TYPES.map(ft => {
                  const records = accuracy.filter(r => r.forecast_type === ft);
                  if (!records.length) return null;
                  const avg = records.reduce((s, r) => s + (r.accuracy_pct ?? 0), 0) / records.length;
                  return (
                    <Card key={ft} size="small" className={styles.accCard}>
                      <div style={{ color: TYPE_COLORS[ft], fontSize: 12, marginBottom: 4 }}>
                        {records[0].label}
                      </div>
                      <Progress
                        type="circle"
                        percent={Math.round(avg)}
                        size={64}
                        strokeColor={avg >= 90 ? '#1A7A52' : avg >= 70 ? '#C8923A' : '#C53030'}
                      />
                      <div className={styles.accSub}>{records.length} 期均值</div>
                    </Card>
                  );
                })}
              </div>

              <Table
                dataSource={accuracy}
                columns={accuracyColumns}
                rowKey={(r, i) => `${r.forecast_type}-${r.target_period}-${i}`}
                size="small"
                pagination={false}
                style={{ marginTop: 12 }}
              />
            </div>
          )
        )}
      </Spin>
    </div>
  );
};

export default FinancialForecastPage;
