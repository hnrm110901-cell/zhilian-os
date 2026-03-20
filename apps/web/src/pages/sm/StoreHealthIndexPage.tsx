/**
 * 门店健康指数页（三支柱聚合）
 * 路由：/sm/health-index
 * 数据：GET /api/v1/stores/{store_id}/health-index
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  ZCard, ZBadge, ZButton, ZSkeleton, ZEmpty, HealthRing,
} from '../../design-system/components';
import { apiClient } from '../../services/api';
import { handleApiError } from '../../utils/message';
import ReactECharts from 'echarts-for-react';
import styles from './StoreHealthIndexPage.module.css';

// ── 常量 ───────────────────────────────────────────────────────────────────────

const STORE_ID = 'store_001';

const PILLAR_LABELS: Record<string, string> = {
  operational:    '运营支柱',
  private_domain: '私域支柱',
  ai_diagnosis:   'AI 诊断',
};

const PILLAR_DESCS: Record<string, string> = {
  operational:    '收入 / 成本率 / 损耗 / 人效',
  private_domain: '会员 / 复购 / 裂变 / 满意度',
  ai_diagnosis:   '决策采纳率 / 节省¥ / 预测准确率',
};

// ── 类型 ───────────────────────────────────────────────────────────────────────

interface PillarData {
  score:  number | null;
  weight: number;
}

interface TrendPoint {
  date:  string;
  score: number;
}

interface HealthIndexData {
  store_id:    string;
  score:       number;
  level:       string;
  level_label: string;
  level_color: string;
  pillars:     Record<string, PillarData>;
  computed_at: string;
  trend:       TrendPoint[];
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────

function levelBadgeType(color: string): string {
  const map: Record<string, string> = {
    green:  'success',
    blue:   'info',
    orange: 'warning',
    red:    'danger',
  };
  return map[color] ?? 'default';
}

function pillarBarColor(score: number): string {
  if (score >= 85) return 'var(--green)';
  if (score >= 70) return '#007AFF';
  if (score >= 50) return 'var(--accent)';
  return 'var(--red)';
}

function trendOption(trend: TrendPoint[]) {
  return {
    grid: { top: 8, bottom: 22, left: 38, right: 12 },
    xAxis: {
      type: 'category',
      data: trend.map(p => p.date.slice(5)),
      axisLabel: { fontSize: 11, color: 'var(--text-tertiary)' },
      axisLine: { lineStyle: { color: 'var(--border-subtle, #f0f0f0)' } },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      splitLine: { lineStyle: { color: 'var(--border-subtle, #f0f0f0)' } },
      axisLabel: { fontSize: 11, color: 'var(--text-tertiary)' },
    },
    tooltip: {
      trigger: 'axis',
      formatter: (params: any[]) => `${params[0].name}: <b>${params[0].value.toFixed(1)}</b> 分`,
    },
    series: [{
      type: 'line',
      data: trend.map(p => p.score),
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { color: '#FF6B2C', width: 2 },
      itemStyle: { color: '#FF6B2C' },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(255,107,44,0.22)' },
            { offset: 1, color: 'rgba(255,107,44,0.00)' },
          ],
        },
      },
    }],
  };
}

// ── 子组件 ────────────────────────────────────────────────────────────────────

function PillarRow({ pillarKey, pillar }: { pillarKey: string; pillar: PillarData }) {
  const score = pillar.score ?? 0;
  const color = pillar.score != null ? pillarBarColor(score) : 'var(--text-tertiary)';
  return (
    <div className={styles.pillarRow}>
      <div className={styles.pillarHeader}>
        <div>
          <span className={styles.pillarLabel}>{PILLAR_LABELS[pillarKey] ?? pillarKey}</span>
          <span className={styles.pillarDesc}>{PILLAR_DESCS[pillarKey]}</span>
        </div>
        <div className={styles.pillarRight}>
          <span className={styles.pillarWeight}>权重 {Math.round(pillar.weight * 100)}%</span>
          <span className={styles.pillarScore} style={{ color }}>
            {pillar.score != null ? score.toFixed(1) : '—'}
          </span>
        </div>
      </div>
      <div className={styles.barTrack}>
        <div
          className={styles.barFill}
          style={{ width: `${score}%`, background: color }}
        />
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// StoreHealthIndexPage
// ════════════════════════════════════════════════════════════════════════════

const StoreHealthIndexPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [data,    setData]    = useState<HealthIndexData | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/stores/${STORE_ID}/health-index`);
      setData(res.data);
    } catch (err: any) {
      handleApiError(err, '加载健康指数失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const computedAt = data
    ? new Date(data.computed_at).toLocaleString('zh-CN', { hour12: false })
    : '';

  return (
    <div className={styles.page}>

      {/* ── 页头 ── */}
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>门店健康指数</h2>
          {computedAt && <span className={styles.asOf}>计算于 {computedAt}</span>}
        </div>
        <ZButton size="sm" onClick={load} loading={loading}>刷新</ZButton>
      </div>

      {loading && !data ? (
        <ZSkeleton rows={6} />
      ) : !data ? (
        <ZEmpty description="暂无数据" />
      ) : (
        <div className={styles.body}>

          {/* ── 综合评分卡 ── */}
          <ZCard className={styles.scoreCard}>
            <div className={styles.scoreInner}>
              <HealthRing score={data.score} size={120} strokeWidth={10} />
              <div className={styles.scoreInfo}>
                <ZBadge
                  type={levelBadgeType(data.level_color)}
                  className={styles.levelBadge}
                >
                  {data.level_label}
                </ZBadge>
                <div className={styles.scoreNum}>
                  综合健康分 <strong>{data.score.toFixed(1)}</strong> / 100
                </div>
                <p className={styles.scoreHint}>
                  运营 40% · 私域 35% · AI诊断 25%
                </p>
              </div>
            </div>
          </ZCard>

          {/* ── 三支柱明细 ── */}
          <ZCard title="三支柱得分">
            {Object.entries(data.pillars).map(([key, pillar]) => (
              <PillarRow key={key} pillarKey={key} pillar={pillar} />
            ))}
          </ZCard>

          {/* ── 7 日趋势 ── */}
          {data.trend.length > 1 && (
            <ZCard title="健康分趋势（近7日）">
              <ReactECharts
                option={trendOption(data.trend)}
                style={{ height: 160 }}
                opts={{ renderer: 'canvas' }}
              />
            </ZCard>
          )}

        </div>
      )}
    </div>
  );
};

export default StoreHealthIndexPage;
