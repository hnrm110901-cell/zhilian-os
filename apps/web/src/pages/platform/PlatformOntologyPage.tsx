/**
 * PlatformOntologyPage — /platform/ontology
 *
 * 本体知识图谱管理：按品牌/门店查看数据覆盖率、健康评分、质量问题
 *
 * 后端 API:
 *   GET /api/v1/merchants
 *   GET /api/v1/merchants/{brand_id}          → stores 列表
 *   GET /api/v1/cdp/platform/ontology/dashboard?store_id=X
 *   GET /api/v1/cdp/platform/ontology/entities?store_id=X
 *   GET /api/v1/cdp/platform/ontology/issues?store_id=X
 *   GET /api/v1/cdp/platform/tenant/onboarding/all
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  ZCard, ZBadge, ZButton, ZEmpty, ZSkeleton, ZAlert,
} from '../../design-system/components';
import { apiClient } from '../../services/api';
import styles from './PlatformOntologyPage.module.css';

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface BrandOption { brand_id: string; name: string; }
interface StoreOption  { id: string; name: string; city?: string; status?: string; }

interface OntologyDashboard {
  store_id: string;
  health_score: number;
  data_quality: 'excellent' | 'good' | 'warning' | 'critical';
  entity_counts: {
    dishes: number;
    inventory_items: number;
    bom_templates: number;
    bom_items: number;
  };
  coverage: {
    dish:      { rate: number; complete: number; total: number };
    bom:       { rate: number; with_bom: number; total_dishes: number };
    inventory: { rate: number; complete: number; total: number };
  };
  relationship_density: number;
}

interface EntityStats {
  dish_by_category: Record<string, number>;
  inventory_by_category: Record<string, number>;
  orphan_dishes_no_bom: number;
}

interface DataIssue {
  entity_type: string;
  entity_id: string;
  entity_name: string;
  issue: string;
  severity: 'high' | 'medium' | 'low';
}

interface OnboardingItem {
  store_id: string;
  counts: { dishes: number; bom_templates: number; inventory_items: number; employees: number };
  progress: { overall_progress: number; dish_progress: number; bom_progress: number; inventory_progress: number; employee_progress: number };
  status: 'completed' | 'almost_ready' | 'in_progress' | 'just_started';
  estimated_remaining_days: number;
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────

const QUALITY_BADGE: Record<string, 'success' | 'info' | 'warning' | 'error'> = {
  excellent: 'success', good: 'info', warning: 'warning', critical: 'error',
};
const QUALITY_LABEL: Record<string, string> = {
  excellent: '优秀', good: '良好', warning: '待改进', critical: '告急',
};
const STATUS_BADGE: Record<string, 'success' | 'info' | 'warning' | 'default'> = {
  completed: 'success', almost_ready: 'info', in_progress: 'warning', just_started: 'default',
};
const STATUS_LABEL: Record<string, string> = {
  completed: '已完成', almost_ready: '接近完成', in_progress: '进行中', just_started: '刚起步',
};
const SEVERITY_BADGE: Record<string, 'error' | 'warning' | 'info'> = {
  high: 'error', medium: 'warning', low: 'info',
};
const SEVERITY_LABEL: Record<string, string> = { high: '高', medium: '中', low: '低' };
const ISSUE_LABEL: Record<string, string> = {
  missing_price: '缺少价格',
  missing_unit_cost: '缺少成本单价',
  empty_bom_no_items: 'BOM 无明细',
};

function pct(rate: number) { return Math.round(rate * 100); }

// ── 进度条子组件 ───────────────────────────────────────────────────────────────

function CoverageBar({ label, rate, complete, total }: { label: string; rate: number; complete: number; total: number }) {
  const p = pct(rate);
  const color = p >= 85 ? '#22c55e' : p >= 60 ? '#f59e0b' : '#ef4444';
  return (
    <div className={styles.coverageItem}>
      <div className={styles.coverageHeader}>
        <span className={styles.coverageLabel}>{label}</span>
        <span className={styles.coverageValue}>{complete} / {total}</span>
        <span className={styles.coveragePct} style={{ color }}>{p}%</span>
      </div>
      <div className={styles.progressTrack}>
        <div className={styles.progressBar} style={{ width: `${p}%`, background: color }} />
      </div>
    </div>
  );
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

export default function PlatformOntologyPage() {
  const [brands, setBrands] = useState<BrandOption[]>([]);
  const [selectedBrand, setSelectedBrand] = useState<string>('');
  const [stores, setStores] = useState<StoreOption[]>([]);
  const [selectedStore, setSelectedStore] = useState<string>('');

  const [loadingBrands, setLoadingBrands] = useState(true);
  const [loadingStores, setLoadingStores] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const [dashboard, setDashboard] = useState<OntologyDashboard | null>(null);
  const [entityStats, setEntityStats] = useState<EntityStats | null>(null);
  const [issues, setIssues] = useState<DataIssue[]>([]);
  const [onboarding, setOnboarding] = useState<OnboardingItem[]>([]);
  const [loadingOnboarding, setLoadingOnboarding] = useState(false);

  const [activeTab, setActiveTab] = useState<'overview' | 'detail'>('overview');

  // 加载品牌列表
  useEffect(() => {
    (async () => {
      setLoadingBrands(true);
      try {
        const res = await apiClient.get('/api/v1/merchants?page=1&page_size=50');
        const list: any[] = res?.merchants ?? res?.items ?? (Array.isArray(res) ? res : []);
        setBrands(list.map((m: any) => ({ brand_id: m.brand_id ?? m.id, name: m.name })));
      } catch { setBrands([]); }
      finally { setLoadingBrands(false); }
    })();
  }, []);

  // 加载全量入驻总览
  useEffect(() => {
    if (activeTab !== 'overview') return;
    (async () => {
      setLoadingOnboarding(true);
      try {
        const res = await apiClient.get('/api/v1/cdp/platform/tenant/onboarding/all');
        setOnboarding(Array.isArray(res) ? res : (res?.results ?? []));
      } catch { setOnboarding([]); }
      finally { setLoadingOnboarding(false); }
    })();
  }, [activeTab]);

  // 选品牌后加载门店
  useEffect(() => {
    if (!selectedBrand) { setStores([]); setSelectedStore(''); return; }
    (async () => {
      setLoadingStores(true);
      setSelectedStore('');
      setDashboard(null); setEntityStats(null); setIssues([]);
      try {
        const res = await apiClient.get(`/api/v1/merchants/${selectedBrand}`);
        const storeList: any[] = res?.stores ?? [];
        setStores(storeList.map((s: any) => ({ id: s.id, name: s.name, city: s.city, status: s.status })));
        if (storeList.length > 0) setSelectedStore(storeList[0].id);
      } catch { setStores([]); }
      finally { setLoadingStores(false); }
    })();
  }, [selectedBrand]);

  // 选门店后加载详情
  const loadStoreDetail = useCallback(async (storeId: string) => {
    if (!storeId) return;
    setLoadingDetail(true);
    setDashboard(null); setEntityStats(null); setIssues([]);
    try {
      const [dash, ent, iss] = await Promise.allSettled([
        apiClient.get(`/api/v1/cdp/platform/ontology/dashboard?store_id=${storeId}`),
        apiClient.get(`/api/v1/cdp/platform/ontology/entities?store_id=${storeId}`),
        apiClient.get(`/api/v1/cdp/platform/ontology/issues?store_id=${storeId}`),
      ]);
      if (dash.status === 'fulfilled') setDashboard(dash.value as OntologyDashboard);
      if (ent.status === 'fulfilled')  setEntityStats(ent.value as EntityStats);
      if (iss.status === 'fulfilled')  setIssues(Array.isArray(iss.value) ? iss.value as DataIssue[] : []);
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    if (selectedStore && activeTab === 'detail') loadStoreDetail(selectedStore);
  }, [selectedStore, activeTab, loadStoreDetail]);

  useEffect(() => {
    if (selectedStore && activeTab === 'detail') loadStoreDetail(selectedStore);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStore]);

  const brandName = brands.find(b => b.brand_id === selectedBrand)?.name ?? selectedBrand;
  const storeName = stores.find(s => s.id === selectedStore)?.name ?? selectedStore;

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>本体知识图谱管理</h1>
          <p className={styles.pageSubtitle}>
            查看各品牌/门店的数据覆盖率、知识完整性健康评分与数据质量问题
          </p>
        </div>
      </div>

      {/* Tab */}
      <div className={styles.tabBar}>
        <button
          className={`${styles.tab} ${activeTab === 'overview' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('overview')}
        >🗺 全量入驻总览</button>
        <button
          className={`${styles.tab} ${activeTab === 'detail' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('detail')}
        >🔍 门店本体详情</button>
      </div>

      {/* ── 全量入驻总览 ── */}
      {activeTab === 'overview' && (
        <div className={styles.overviewSection}>
          {loadingOnboarding ? (
            <div className={styles.skeletonGrid}>
              {[...Array(4)].map((_, i) => <ZSkeleton key={i} height={100} />)}
            </div>
          ) : onboarding.length === 0 ? (
            <ZCard><ZEmpty text="暂无门店入驻数据" /></ZCard>
          ) : (
            <div className={styles.onboardingGrid}>
              {onboarding.map(item => {
                const p = Math.round(item.progress.overall_progress * 100);
                return (
                  <ZCard key={item.store_id} className={styles.onboardCard}>
                    <div className={styles.onboardHeader}>
                      <span className={styles.onboardStoreId}>{item.store_id.slice(0, 8)}…</span>
                      <ZBadge type={STATUS_BADGE[item.status]} text={STATUS_LABEL[item.status]} />
                    </div>
                    <div className={styles.onboardProgress}>
                      <div className={styles.onboardPct}>{p}%</div>
                      <div className={styles.progressTrack}>
                        <div className={styles.progressBar} style={{ width: `${p}%`, background: p >= 80 ? '#22c55e' : p >= 40 ? '#f59e0b' : '#ef4444' }} />
                      </div>
                    </div>
                    <div className={styles.onboardCounts}>
                      <span>菜品 {item.counts.dishes}</span>
                      <span>BOM {item.counts.bom_templates}</span>
                      <span>库存 {item.counts.inventory_items}</span>
                      <span>员工 {item.counts.employees}</span>
                    </div>
                    {item.estimated_remaining_days > 0 && (
                      <div className={styles.onboardEst}>预计还需 {item.estimated_remaining_days} 天完成入驻</div>
                    )}
                  </ZCard>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── 门店本体详情 ── */}
      {activeTab === 'detail' && (
        <>
          {/* 品牌选择 */}
          <div className={styles.brandBar}>
            <span className={styles.brandBarLabel}>品牌：</span>
            {loadingBrands ? <ZSkeleton height={32} /> : brands.length === 0 ? (
              <span className={styles.noData}>暂无商户数据</span>
            ) : (
              <div className={styles.brandTabs}>
                {brands.map(b => (
                  <button
                    key={b.brand_id}
                    className={`${styles.brandTab} ${selectedBrand === b.brand_id ? styles.brandTabActive : ''}`}
                    onClick={() => setSelectedBrand(b.brand_id)}
                  >{b.name}</button>
                ))}
              </div>
            )}
          </div>

          {/* 门店选择 */}
          {selectedBrand && (
            <div className={styles.storeBar}>
              <span className={styles.brandBarLabel}>门店：</span>
              {loadingStores ? <ZSkeleton height={32} /> : stores.length === 0 ? (
                <span className={styles.noData}>该品牌暂无门店</span>
              ) : (
                <div className={styles.brandTabs}>
                  {stores.map(s => (
                    <button
                      key={s.id}
                      className={`${styles.brandTab} ${selectedStore === s.id ? styles.brandTabActive : ''}`}
                      onClick={() => { setSelectedStore(s.id); loadStoreDetail(s.id); }}
                    >{s.name}{s.city ? ` · ${s.city}` : ''}</button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* 门店详情内容 */}
          {!selectedBrand ? (
            <ZCard><ZEmpty text="请先选择品牌" /></ZCard>
          ) : !selectedStore ? (
            <ZCard><ZEmpty text="请选择门店" /></ZCard>
          ) : loadingDetail ? (
            <div className={styles.detailGrid}>
              {[...Array(3)].map((_, i) => <ZSkeleton key={i} height={200} />)}
            </div>
          ) : !dashboard ? (
            <ZCard>
              <ZAlert variant="warning" title={`${brandName} · ${storeName} 暂无本体数据，请先完成基础数据录入`} />
            </ZCard>
          ) : (
            <div className={styles.detailGrid}>
              {/* ── 健康评分卡 ── */}
              <ZCard className={styles.healthCard}>
                <div className={styles.healthHeader}>
                  <h3 className={styles.cardTitle}>本体健康评分</h3>
                  <ZBadge type={QUALITY_BADGE[dashboard.data_quality]} text={QUALITY_LABEL[dashboard.data_quality]} />
                </div>
                <div className={styles.scoreRing}>
                  <svg viewBox="0 0 80 80" className={styles.ringsvg}>
                    <circle cx="40" cy="40" r="34" fill="none" stroke="var(--border,#e5e7eb)" strokeWidth="8" />
                    <circle
                      cx="40" cy="40" r="34" fill="none"
                      stroke={dashboard.health_score >= 85 ? '#22c55e' : dashboard.health_score >= 65 ? '#f59e0b' : '#ef4444'}
                      strokeWidth="8"
                      strokeDasharray={`${(dashboard.health_score / 100) * 213.6} 213.6`}
                      strokeLinecap="round"
                      transform="rotate(-90 40 40)"
                    />
                  </svg>
                  <div className={styles.scoreText}>
                    <span className={styles.scoreNum}>{Math.round(dashboard.health_score)}</span>
                    <span className={styles.scoreUnit}>分</span>
                  </div>
                </div>
                <div className={styles.entityGrid}>
                  <div className={styles.entityItem}>
                    <span className={styles.entityCount}>{dashboard.entity_counts.dishes}</span>
                    <span className={styles.entityLabel}>菜品</span>
                  </div>
                  <div className={styles.entityItem}>
                    <span className={styles.entityCount}>{dashboard.entity_counts.inventory_items}</span>
                    <span className={styles.entityLabel}>食材</span>
                  </div>
                  <div className={styles.entityItem}>
                    <span className={styles.entityCount}>{dashboard.entity_counts.bom_templates}</span>
                    <span className={styles.entityLabel}>BOM模板</span>
                  </div>
                  <div className={styles.entityItem}>
                    <span className={styles.entityCount}>{dashboard.entity_counts.bom_items}</span>
                    <span className={styles.entityLabel}>BOM明细</span>
                  </div>
                </div>
                <div className={styles.densityRow}>
                  <span className={styles.densityLabel}>关系密度（BOM项/实体）</span>
                  <span className={styles.densityValue}>{dashboard.relationship_density.toFixed(2)}</span>
                </div>
              </ZCard>

              {/* ── 覆盖率卡 ── */}
              <ZCard className={styles.coverageCard}>
                <h3 className={styles.cardTitle}>数据覆盖率</h3>
                <CoverageBar
                  label="菜品完整度（有价格+有分类）"
                  rate={dashboard.coverage.dish.rate}
                  complete={dashboard.coverage.dish.complete}
                  total={dashboard.coverage.dish.total}
                />
                <CoverageBar
                  label="BOM 覆盖率（有物料清单的菜品）"
                  rate={dashboard.coverage.bom.rate}
                  complete={dashboard.coverage.bom.with_bom}
                  total={dashboard.coverage.bom.total_dishes}
                />
                <CoverageBar
                  label="食材成本覆盖（有单位成本的食材）"
                  rate={dashboard.coverage.inventory.rate}
                  complete={dashboard.coverage.inventory.complete}
                  total={dashboard.coverage.inventory.total}
                />

                {entityStats && (
                  <>
                    <div className={styles.subTitle}>菜品品类分布</div>
                    <div className={styles.categoryCloud}>
                      {Object.entries(entityStats.dish_by_category).slice(0, 8).map(([cat, cnt]) => (
                        <span key={cat} className={styles.categoryChip}>{cat} <strong>{cnt}</strong></span>
                      ))}
                    </div>
                    {entityStats.orphan_dishes_no_bom > 0 && (
                      <div className={styles.orphanWarning}>
                        ⚠ {entityStats.orphan_dishes_no_bom} 道菜品缺少 BOM 物料清单
                      </div>
                    )}
                  </>
                )}
              </ZCard>

              {/* ── 数据质量问题卡 ── */}
              <ZCard className={styles.issuesCard}>
                <div className={styles.issuesHeader}>
                  <h3 className={styles.cardTitle}>数据质量问题</h3>
                  {issues.length > 0 && (
                    <ZBadge
                      type={issues.some(i => i.severity === 'high') ? 'error' : 'warning'}
                      text={`${issues.length} 个问题`}
                    />
                  )}
                </div>
                {issues.length === 0 ? (
                  <ZEmpty text="🎉 暂无数据质量问题" />
                ) : (
                  <div className={styles.issueList}>
                    {issues.map(issue => (
                      <div key={`${issue.entity_type}-${issue.entity_id}`} className={styles.issueItem}>
                        <div className={styles.issueLeft}>
                          <ZBadge type={SEVERITY_BADGE[issue.severity]} text={SEVERITY_LABEL[issue.severity]} />
                        </div>
                        <div className={styles.issueBody}>
                          <div className={styles.issueName}>{issue.entity_name}</div>
                          <div className={styles.issueDesc}>{ISSUE_LABEL[issue.issue] ?? issue.issue}</div>
                        </div>
                        <div className={styles.issueType}>
                          {issue.entity_type === 'dish' ? '菜品' : issue.entity_type === 'inventory_item' ? '食材' : 'BOM'}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {issues.length > 0 && (
                  <div className={styles.issueFooter}>
                    <ZButton size="sm" variant="ghost" onClick={() => loadStoreDetail(selectedStore)}>
                      刷新检测
                    </ZButton>
                  </div>
                )}
              </ZCard>
            </div>
          )}
        </>
      )}
    </div>
  );
}
