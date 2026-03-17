/**
 * SupplierIntelPage — /platform/supplier-intel
 *
 * 供应商智能评分面板：评级分布、排名表、风险预警、价格趋势
 * 后端 API:
 *   POST   /api/v1/supplier-intel/compute       — 计算评分卡
 *   GET    /api/v1/supplier-intel/scorecards     — 评分卡列表
 *   GET    /api/v1/supplier-intel/scorecards/:id — 评分卡详情
 *   GET    /api/v1/supplier-intel/ranking        — 供应商排名
 *   GET    /api/v1/supplier-intel/price-trends   — 价格趋势
 *   GET    /api/v1/supplier-intel/risk-alerts    — 风险预警
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  ZCard, ZBadge, ZButton, ZEmpty, ZSkeleton,
} from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import { apiClient } from '../../services/api';
import styles from './SupplierIntelPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface Scorecard {
  id: string;
  brand_id: string;
  supplier_id: string;
  supplier_name: string;
  score_period: string;
  delivery_score: number;
  quality_score: number;
  price_score: number;
  service_score: number;
  overall_score: number;
  tier: string;
  order_count: number;
  total_amount_fen: number;
  total_amount_yuan: number;
  defect_count: number;
  late_delivery_count: number;
  price_trend: string;
  recommendations: string[];
  created_at?: string;
  updated_at?: string;
}

interface RankedScorecard extends Scorecard {
  rank: number;
}

interface TierDistribution {
  A: number;
  B: number;
  C: number;
  D: number;
}

interface RankingData {
  period: string;
  total_suppliers: number;
  tier_distribution: TierDistribution;
  ranking: RankedScorecard[];
}

interface RiskAlert {
  scorecard_id: string;
  supplier_id: string;
  supplier_name: string;
  tier: string;
  overall_score: number;
  reasons: string[];
  recommended_action: string;
  total_amount_yuan: number;
  period: string;
}

interface PriceTrendItem {
  period: string;
  ingredient_name: string;
  avg_price_yuan: number;
  total_yuan: number;
}

// ── 工具函数 ─────────────────────────────────────────────────────────────────

function fmtYuan(fen: number): string {
  return `\u00A5${(fen / 100).toFixed(2)}`;
}

function getCurrentPeriod(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function getPeriodOptions(): string[] {
  const periods: string[] = [];
  const now = new Date();
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    periods.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
  }
  return periods;
}

function scoreColor(score: number): string {
  if (score >= 85) return styles.fillGreen;
  if (score >= 70) return styles.fillBlue;
  if (score >= 50) return styles.fillOrange;
  return styles.fillRed;
}

function tierVariant(tier: string): 'success' | 'info' | 'warning' | 'error' {
  if (tier === 'A') return 'success';
  if (tier === 'B') return 'info';
  if (tier === 'C') return 'warning';
  return 'error';
}

// ── 组件 ─────────────────────────────────────────────────────────────────────

const SupplierIntelPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [computing, setComputing] = useState(false);
  const [period, setPeriod] = useState(getCurrentPeriod());
  const [tierFilter, setTierFilter] = useState('');
  const [searchText, setSearchText] = useState('');

  // 数据
  const [rankingData, setRankingData] = useState<RankingData | null>(null);
  const [riskAlerts, setRiskAlerts] = useState<RiskAlert[]>([]);
  const [priceTrends, setPriceTrends] = useState<PriceTrendItem[]>([]);
  const [trendSupplierId, setTrendSupplierId] = useState('');

  const brandId = 'default';

  // ── 数据加载 ────────────────────────────────────────────────────────────

  const fetchRanking = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get<{ data: RankingData }>('/api/v1/supplier-intel/ranking', {
        params: { brand_id: brandId, period },
      });
      const data = (res as any).data || res;
      setRankingData(data);
    } catch (err) {
      console.error('加载排名数据失败', err);
    } finally {
      setLoading(false);
    }
  }, [brandId, period]);

  const fetchRiskAlerts = useCallback(async () => {
    try {
      const res = await apiClient.get<{ data: RiskAlert[] }>('/api/v1/supplier-intel/risk-alerts', {
        params: { brand_id: brandId },
      });
      const data = (res as any).data || res;
      setRiskAlerts(data || []);
    } catch (err) {
      console.error('加载风险预警失败', err);
    }
  }, [brandId]);

  const fetchPriceTrends = useCallback(async (supplierId: string) => {
    if (!supplierId) {
      setPriceTrends([]);
      return;
    }
    try {
      const res = await apiClient.get<{ data: PriceTrendItem[] }>('/api/v1/supplier-intel/price-trends', {
        params: { brand_id: brandId, supplier_id: supplierId, months: 6 },
      });
      const data = (res as any).data || res;
      setPriceTrends(data || []);
    } catch (err) {
      console.error('加载价格趋势失败', err);
    }
  }, [brandId]);

  useEffect(() => {
    fetchRanking();
    fetchRiskAlerts();
  }, [fetchRanking, fetchRiskAlerts]);

  useEffect(() => {
    fetchPriceTrends(trendSupplierId);
  }, [trendSupplierId, fetchPriceTrends]);

  // ── 重新计算 ──────────────────────────────────────────────────────────

  const handleCompute = async () => {
    setComputing(true);
    try {
      await apiClient.post('/api/v1/supplier-intel/compute', {
        brand_id: brandId,
        period,
      });
      await fetchRanking();
      await fetchRiskAlerts();
    } catch (err) {
      console.error('计算评分卡失败', err);
    } finally {
      setComputing(false);
    }
  };

  // ── 筛选 ──────────────────────────────────────────────────────────────

  const filteredRanking = (rankingData?.ranking || []).filter((card) => {
    if (tierFilter && card.tier !== tierFilter) return false;
    if (searchText && !card.supplier_name.toLowerCase().includes(searchText.toLowerCase())) return false;
    return true;
  });

  // ── 评级分布 ──────────────────────────────────────────────────────────

  const tierDist = rankingData?.tier_distribution || { A: 0, B: 0, C: 0, D: 0 };

  const tierCards: Array<{ key: string; label: string; cardCls: string; numCls: string }> = [
    { key: 'A', label: 'A级 (优秀)', cardCls: styles.tierCardA, numCls: styles.tierNumA },
    { key: 'B', label: 'B级 (良好)', cardCls: styles.tierCardB, numCls: styles.tierNumB },
    { key: 'C', label: 'C级 (待改善)', cardCls: styles.tierCardC, numCls: styles.tierNumC },
    { key: 'D', label: 'D级 (高风险)', cardCls: styles.tierCardD, numCls: styles.tierNumD },
  ];

  // ── 排名表列定义 ──────────────────────────────────────────────────────

  const columns: ZTableColumn<RankedScorecard>[] = [
    {
      key: 'rank',
      title: '排名',
      width: 60,
      render: (row) => (
        <span className={`${styles.rankCell} ${row.rank <= 3 ? styles.rankTop : ''}`}>
          {row.rank}
        </span>
      ),
    },
    {
      key: 'supplier_name',
      title: '供应商',
      render: (row) => <span className={styles.supplierName}>{row.supplier_name}</span>,
    },
    {
      key: 'overall_score',
      title: '综合评分',
      width: 160,
      render: (row) => (
        <div className={styles.scoreBar}>
          <div className={styles.scoreBarTrack}>
            <div
              className={`${styles.scoreBarFill} ${scoreColor(row.overall_score)}`}
              style={{ width: `${row.overall_score}%` }}
            />
          </div>
          <span className={styles.scoreBarValue}>{row.overall_score}</span>
        </div>
      ),
    },
    {
      key: 'delivery_score',
      title: '交付',
      width: 60,
      render: (row) => <span className={styles.scoreCell}>{row.delivery_score}</span>,
    },
    {
      key: 'quality_score',
      title: '质量',
      width: 60,
      render: (row) => <span className={styles.scoreCell}>{row.quality_score}</span>,
    },
    {
      key: 'price_score',
      title: '价格',
      width: 60,
      render: (row) => <span className={styles.scoreCell}>{row.price_score}</span>,
    },
    {
      key: 'service_score',
      title: '服务',
      width: 60,
      render: (row) => <span className={styles.scoreCell}>{row.service_score}</span>,
    },
    {
      key: 'tier',
      title: '评级',
      width: 70,
      render: (row) => <ZBadge type={tierVariant(row.tier)} text={`${row.tier}级`} />,
    },
    {
      key: 'price_trend',
      title: '价格趋势',
      width: 80,
      render: (row) => {
        if (row.price_trend === 'up') return <span className={styles.trendUp}>↑ 上涨</span>;
        if (row.price_trend === 'down') return <span className={styles.trendDown}>↓ 下降</span>;
        return <span className={styles.trendFlat}>- 稳定</span>;
      },
    },
    {
      key: 'total_amount_yuan',
      title: '采购额',
      width: 100,
      render: (row) => <span className={styles.amountCell}>{`\u00A5${row.total_amount_yuan.toFixed(2)}`}</span>,
    },
    {
      key: 'actions',
      title: '',
      width: 80,
      render: (row) => (
        <ZButton
          size="sm"
          variant="ghost"
          onClick={() => {
            setTrendSupplierId(row.supplier_id);
          }}
        >
          趋势
        </ZButton>
      ),
    },
  ];

  // ── 渲染 ──────────────────────────────────────────────────────────────

  if (loading && !rankingData) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingWrap}>
          <ZSkeleton rows={8} />
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>供应商智能评分</h1>
          <p className={styles.pageSubtitle}>
            跨系统融合B2B采购、食品安全溯源、价格趋势，四维度综合评估供应商表现
          </p>
        </div>
        <div className={styles.headerActions}>
          <ZButton
            variant="primary"
            onClick={handleCompute}
            disabled={computing}
          >
            {computing ? '计算中...' : '重新计算'}
          </ZButton>
        </div>
      </div>

      {/* 评级分布 */}
      <div className={styles.tierRow}>
        {tierCards.map(({ key, label, cardCls, numCls }) => (
          <ZCard
            key={key}
            className={`${styles.tierCard} ${cardCls}`}
            onClick={() => setTierFilter(tierFilter === key ? '' : key)}
          >
            <div className={`${styles.tierNum} ${numCls}`}>
              {tierDist[key as keyof TierDistribution]}
            </div>
            <div className={styles.tierLabel}>{label}</div>
          </ZCard>
        ))}
      </div>

      {/* 筛选工具栏 */}
      <div className={styles.toolbar}>
        <select
          className={styles.filterSelect}
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
        >
          {getPeriodOptions().map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
        <select
          className={styles.filterSelect}
          value={tierFilter}
          onChange={(e) => setTierFilter(e.target.value)}
        >
          <option value="">全部评级</option>
          <option value="A">A级</option>
          <option value="B">B级</option>
          <option value="C">C级</option>
          <option value="D">D级</option>
        </select>
        <input
          className={styles.searchInput}
          placeholder="搜索供应商..."
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
        />
        <div className={styles.toolbarSpacer} />
        <span className={styles.tierLabel}>
          共 {rankingData?.total_suppliers || 0} 家供应商
        </span>
      </div>

      {/* 排名表 */}
      <ZCard className={styles.tableCard}>
        {filteredRanking.length > 0 ? (
          <ZTable<RankedScorecard>
            columns={columns}
            data={filteredRanking}
            rowKey="id"
          />
        ) : (
          <ZEmpty description={loading ? '加载中...' : '暂无评分数据，请点击"重新计算"生成评分卡'} />
        )}
      </ZCard>

      {/* 风险预警 */}
      {riskAlerts.length > 0 && (
        <div className={styles.riskSection}>
          <h2 className={styles.riskSectionTitle}>
            风险预警 ({riskAlerts.length})
          </h2>
          <div className={styles.riskGrid}>
            {riskAlerts.map((alert) => (
              <ZCard key={alert.scorecard_id} className={styles.riskCard}>
                <div className={styles.riskCardHeader}>
                  <span className={styles.riskSupplier}>{alert.supplier_name}</span>
                  <ZBadge type="error" text={`${alert.tier}级 ${alert.overall_score}分`} />
                </div>
                <ul className={styles.riskReasons}>
                  {alert.reasons.map((reason, idx) => (
                    <li key={idx} className={styles.riskReason}>{reason}</li>
                  ))}
                </ul>
                <div className={styles.riskAction}>{alert.recommended_action}</div>
              </ZCard>
            ))}
          </div>
        </div>
      )}

      {/* 价格趋势 */}
      <div className={styles.trendSection}>
        <h2 className={styles.trendSectionTitle}>价格趋势</h2>
        <div className={styles.trendControls}>
          <select
            className={styles.filterSelect}
            value={trendSupplierId}
            onChange={(e) => setTrendSupplierId(e.target.value)}
          >
            <option value="">选择供应商...</option>
            {(rankingData?.ranking || []).map((card) => (
              <option key={card.supplier_id} value={card.supplier_id}>
                {card.supplier_name}
              </option>
            ))}
          </select>
        </div>
        {trendSupplierId && priceTrends.length > 0 ? (
          <ZCard>
            <table className={styles.trendTable}>
              <thead>
                <tr>
                  <th>月份</th>
                  <th>食材</th>
                  <th>均价 (元)</th>
                  <th>采购总额 (元)</th>
                </tr>
              </thead>
              <tbody>
                {priceTrends.map((item, idx) => (
                  <tr key={idx}>
                    <td>{item.period}</td>
                    <td>{item.ingredient_name}</td>
                    <td className={styles.priceValue}>{`\u00A5${item.avg_price_yuan.toFixed(2)}`}</td>
                    <td className={styles.priceValue}>{`\u00A5${item.total_yuan.toFixed(2)}`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ZCard>
        ) : trendSupplierId ? (
          <ZCard>
            <ZEmpty description="该供应商暂无价格数据" />
          </ZCard>
        ) : (
          <ZCard>
            <ZEmpty description="请选择供应商查看价格趋势" />
          </ZCard>
        )}
      </div>
    </div>
  );
};

export default SupplierIntelPage;
