/**
 * PlatformFeatureFlagsPage — /platform/feature-flags
 *
 * 灰度发布 & 特性开关管理：按品牌/商户控制 AI 功能 / 接入 / 实验功能的启停与覆盖范围
 *
 * 注：特性开关状态存储于前端 localStorage（key: tunxiang-feature-flags）；
 *     后端 API ready 后替换为 /api/v1/feature-flags CRUD。
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  ZCard, ZBadge, ZButton, ZEmpty, ZDrawer, ZSkeleton, ZAlert,
} from '../../design-system/components';
import { apiClient } from '../../services/api';
import styles from './PlatformFeatureFlagsPage.module.css';

// ── 特性开关元数据 ──────────────────────────────────────────────────────────────

type FlagCategory = 'ai' | 'integration' | 'experimental' | 'platform';

interface FlagMeta {
  key: string;
  name: string;
  description: string;
  category: FlagCategory;
  icon: string;
  defaultEnabled: boolean;
  risk: 'low' | 'medium' | 'high';
}

const FLAG_DEFS: FlagMeta[] = [
  {
    key: 'agent_daily_report',
    name: '日报推送 Agent',
    description: '每日自动生成营收/客流/成本摘要，推送至企业微信。启用前需确认推送频道已配置。',
    category: 'ai',
    icon: '📊',
    defaultEnabled: true,
    risk: 'low',
  },
  {
    key: 'agent_inventory_alert',
    name: '库存预警 Agent',
    description: '临期/低库存食材自动告警，防止备货断货与过期损耗。',
    category: 'ai',
    icon: '🔔',
    defaultEnabled: true,
    risk: 'low',
  },
  {
    key: 'agent_revenue_anomaly',
    name: '营收异常监测 Agent',
    description: '实时监控营业额偏差超过阈值时立即告警，适用于多店汇总对比场景。',
    category: 'ai',
    icon: '⚡',
    defaultEnabled: false,
    risk: 'low',
  },
  {
    key: 'agent_member_lifecycle',
    name: '会员生命周期 Agent',
    description: 'RFM 分层分析，自动触发流失预警 + 生日关怀推送。需接入会员 CRM。',
    category: 'ai',
    icon: '👥',
    defaultEnabled: false,
    risk: 'medium',
  },
  {
    key: 'agent_reconciliation',
    name: '对账核查 Agent',
    description: '每日自动比对 POS 收入与库存消耗，检测异常差异。高准确率需 BOM 覆盖 ≥ 80%。',
    category: 'ai',
    icon: '🔍',
    defaultEnabled: false,
    risk: 'medium',
  },
  {
    key: 'agent_prep_suggestion',
    name: '智能备料建议 Agent',
    description: '基于历史销售数据预测备料量，自动生成备料建议单。需至少 30 天历史订单。',
    category: 'ai',
    icon: '🥡',
    defaultEnabled: false,
    risk: 'low',
  },
  {
    key: 'integration_pinzhi_pos',
    name: '品智收银接入',
    description: '品智 POS 数据同步（品智Tech API v2），支持订单/客流/退款数据。',
    category: 'integration',
    icon: '🏪',
    defaultEnabled: false,
    risk: 'medium',
  },
  {
    key: 'integration_aoqiwei_crm',
    name: '奥琦玮会员接入',
    description: '奥琦玮微生活会员系统（welcrm.com）双向同步，会员积分/消费记录。',
    category: 'integration',
    icon: '🎫',
    defaultEnabled: false,
    risk: 'medium',
  },
  {
    key: 'integration_tiancai_supply',
    name: '天财云供应链接入',
    description: '天财商龙云供应链（fxscm.net）采购单/验收单同步。',
    category: 'integration',
    icon: '🚚',
    defaultEnabled: false,
    risk: 'medium',
  },
  {
    key: 'feature_rag_search',
    name: 'RAG 语义搜索',
    description: '向量化门店运营记忆，支持自然语言查询历史决策与经验。需 Qdrant 可用。',
    category: 'experimental',
    icon: '🧠',
    defaultEnabled: false,
    risk: 'high',
  },
  {
    key: 'feature_voice_chef',
    name: '厨师长语音助手',
    description: 'Shokz 骨传导耳机语音交互，厨房场景免手操作查询备料/排班。需边缘节点支持。',
    category: 'experimental',
    icon: '🎤',
    defaultEnabled: false,
    risk: 'high',
  },
  {
    key: 'feature_hq_floor_tablet',
    name: '楼面平板视图',
    description: '楼面经理专属平板端 UI：桌台状态实时看板 + 排队叫号 + 菜品推荐。',
    category: 'experimental',
    icon: '📱',
    defaultEnabled: false,
    risk: 'medium',
  },
  {
    key: 'platform_ontology_neo4j',
    name: 'Neo4j 本体图加速',
    description: '将知识图谱从 PostgreSQL 迁移至 Neo4j，提升图关系查询性能（迁移中）。',
    category: 'platform',
    icon: '🕸️',
    defaultEnabled: false,
    risk: 'high',
  },
  {
    key: 'platform_pi5_edge',
    name: 'Pi5 边缘节点离线推理',
    description: 'Raspberry Pi 5 本地 AI 推理，无网络时保持 Agent 运行（需 Pi5 已部署）。',
    category: 'platform',
    icon: '🖥️',
    defaultEnabled: false,
    risk: 'medium',
  },
];

const LS_KEY = 'tunxiang-feature-flags';

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface FlagState {
  enabled: boolean;           // 是否全局启用
  brandIds: string[];         // 启用的品牌 ID 列表（空 = 全量）
  rolloutPct: number;         // 0-100 灰度覆盖百分比（仅展示）
  note: string;               // 备注
}

interface FlagStore {
  [key: string]: FlagState;
}

interface BrandOption {
  brand_id: string;
  name: string;
}

const CATEGORY_LABEL: Record<FlagCategory, string> = {
  ai: 'AI 功能',
  integration: '接入集成',
  experimental: '实验功能',
  platform: '平台底座',
};

const CATEGORY_BADGE: Record<FlagCategory, 'info' | 'success' | 'warning' | 'default'> = {
  ai: 'info',
  integration: 'success',
  experimental: 'warning',
  platform: 'default',
};

const RISK_BADGE: Record<string, 'success' | 'warning' | 'error'> = {
  low: 'success',
  medium: 'warning',
  high: 'error',
};

const RISK_LABEL: Record<string, string> = { low: '低风险', medium: '中风险', high: '高风险' };

// ── 本地持久化工具 ─────────────────────────────────────────────────────────────

function loadFlagStore(): FlagStore {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  // 初始化默认值
  const defaults: FlagStore = {};
  FLAG_DEFS.forEach(f => {
    defaults[f.key] = { enabled: f.defaultEnabled, brandIds: [], rolloutPct: f.defaultEnabled ? 100 : 0, note: '' };
  });
  return defaults;
}

function saveFlagStore(store: FlagStore) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(store)); } catch { /* ignore */ }
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

export default function PlatformFeatureFlagsPage() {
  const [flagStore, setFlagStore] = useState<FlagStore>(() => loadFlagStore());
  const [brands, setBrands] = useState<BrandOption[]>([]);
  const [loadingBrands, setLoadingBrands] = useState(true);
  const [activeTab, setActiveTab] = useState<FlagCategory | 'all'>('all');

  // Drawer 状态
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editState, setEditState] = useState<FlagState>({ enabled: false, brandIds: [], rolloutPct: 0, note: '' });

  // 加载品牌列表
  useEffect(() => {
    (async () => {
      setLoadingBrands(true);
      try {
        const res = await apiClient.get('/api/v1/merchants?page=1&page_size=50');
        const list: any[] = res?.merchants ?? res?.items ?? (Array.isArray(res) ? res : []);
        setBrands(list.map((m: any) => ({ brand_id: m.brand_id ?? m.id, name: m.name })));
      } catch {
        setBrands([]);
      } finally {
        setLoadingBrands(false);
      }
    })();
  }, []);

  // 持久化
  const updateFlag = useCallback((key: string, patch: Partial<FlagState>) => {
    setFlagStore(prev => {
      const next = { ...prev, [key]: { ...prev[key], ...patch } };
      saveFlagStore(next);
      return next;
    });
  }, []);

  // 快速启停
  const handleToggle = (key: string) => {
    const cur = flagStore[key];
    updateFlag(key, { enabled: !cur?.enabled, rolloutPct: cur?.enabled ? 0 : 100 });
  };

  // 打开配置 Drawer
  const openEdit = (key: string) => {
    setEditingKey(key);
    setEditState({ ...flagStore[key] });
    setDrawerOpen(true);
  };

  const handleSaveEdit = () => {
    if (!editingKey) return;
    updateFlag(editingKey, editState);
    setDrawerOpen(false);
  };

  // 过滤
  const filtered = FLAG_DEFS.filter(f => activeTab === 'all' || f.category === activeTab);

  // 统计
  const totalFlags = FLAG_DEFS.length;
  const enabledFlags = FLAG_DEFS.filter(f => flagStore[f.key]?.enabled).length;
  const rolloutFlags = FLAG_DEFS.filter(f => {
    const s = flagStore[f.key];
    return s?.enabled && s.brandIds.length > 0;
  }).length;
  const disabledFlags = totalFlags - enabledFlags;

  const editingMeta = FLAG_DEFS.find(f => f.key === editingKey);

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>灰度发布 & 特性开关</h1>
          <p className={styles.pageSubtitle}>
            控制 AI 功能 / 接入集成 / 实验特性的启停范围，支持按品牌灰度发布
          </p>
        </div>
        <ZBadge type="warning" text="演示模式 — 开关状态本地存储" />
      </div>

      {/* 统计概览 */}
      <div className={styles.statsRow}>
        <ZCard className={styles.statCard}>
          <div className={styles.statNum}>{totalFlags}</div>
          <div className={styles.statLabel}>特性开关总数</div>
        </ZCard>
        <ZCard className={styles.statCard}>
          <div className={`${styles.statNum} ${styles.statNumGreen}`}>{enabledFlags}</div>
          <div className={styles.statLabel}>已开启</div>
        </ZCard>
        <ZCard className={styles.statCard}>
          <div className={`${styles.statNum} ${styles.statNumOrange}`}>{rolloutFlags}</div>
          <div className={styles.statLabel}>灰度中（按品牌）</div>
        </ZCard>
        <ZCard className={styles.statCard}>
          <div className={`${styles.statNum} ${styles.statNumGray}`}>{disabledFlags}</div>
          <div className={styles.statLabel}>已停用</div>
        </ZCard>
      </div>

      {/* Tab 过滤 */}
      <div className={styles.tabBar}>
        {(['all', 'ai', 'integration', 'experimental', 'platform'] as const).map(tab => {
          const count = tab === 'all' ? totalFlags : FLAG_DEFS.filter(f => f.category === tab).length;
          return (
            <button
              key={tab}
              className={`${styles.tab} ${activeTab === tab ? styles.tabActive : ''}`}
              onClick={() => setActiveTab(tab)}
            >
              {tab === 'all' ? '全部' : CATEGORY_LABEL[tab as FlagCategory]}
              <span className={styles.tabCount}>{count}</span>
            </button>
          );
        })}
      </div>

      {/* 特性开关网格 */}
      <div className={styles.flagGrid}>
        {filtered.map(flag => {
          const state = flagStore[flag.key] ?? { enabled: false, brandIds: [], rolloutPct: 0, note: '' };
          const isGrayMode = state.enabled && state.brandIds.length > 0;
          return (
            <ZCard
              key={flag.key}
              className={`${styles.flagCard} ${state.enabled ? styles.flagCardOn : styles.flagCardOff}`}
            >
              {/* 卡头 */}
              <div className={styles.flagCardHeader}>
                <span className={styles.flagIcon}>{flag.icon}</span>
                <div className={styles.flagInfo}>
                  <div className={styles.flagName}>{flag.name}</div>
                  <div className={styles.flagBadges}>
                    <ZBadge type={CATEGORY_BADGE[flag.category]} text={CATEGORY_LABEL[flag.category]} />
                    <ZBadge type={RISK_BADGE[flag.risk]} text={RISK_LABEL[flag.risk]} />
                  </div>
                </div>
                <div className={`${styles.statusPill} ${state.enabled ? (isGrayMode ? styles.statusPillGray : styles.statusPillOn) : styles.statusPillOff}`}>
                  {state.enabled ? (isGrayMode ? '灰度中' : '全量') : '停用'}
                </div>
              </div>

              {/* 描述 */}
              <p className={styles.flagDesc}>{flag.description}</p>

              {/* 覆盖信息 */}
              {state.enabled && (
                <div className={styles.coverageRow}>
                  <span className={styles.coverageLabel}>覆盖范围：</span>
                  {state.brandIds.length === 0 ? (
                    <span className={styles.coverageAll}>全部品牌</span>
                  ) : (
                    <span className={styles.coverageBrands}>
                      {state.brandIds.length} 个品牌
                      {loadingBrands ? '' : ` / ${brands.length} 个品牌`}
                    </span>
                  )}
                </div>
              )}

              {/* 操作 */}
              <div className={styles.flagActions}>
                <ZButton
                  size="sm"
                  variant={state.enabled ? 'ghost' : 'primary'}
                  onClick={() => handleToggle(flag.key)}
                >
                  {state.enabled ? '停用' : '启用'}
                </ZButton>
                <ZButton size="sm" variant="ghost" onClick={() => openEdit(flag.key)}>
                  配置覆盖
                </ZButton>
              </div>
            </ZCard>
          );
        })}
      </div>

      {/* 配置覆盖 Drawer */}
      <ZDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={`配置覆盖 — ${editingMeta?.name ?? ''}`}
        width={480}
        footer={
          <div className={styles.drawerFooter}>
            <ZButton variant="ghost" onClick={() => setDrawerOpen(false)}>取消</ZButton>
            <ZButton variant="primary" onClick={handleSaveEdit}>保存配置</ZButton>
          </div>
        }
      >
        <div className={styles.drawerBody}>
          {editingMeta && (
            <>
              {/* 风险提示 */}
              {editingMeta.risk === 'high' && (
                <div className={styles.alertRow}>
                  <ZAlert
                    variant="warning"
                    title="高风险特性 — 请仅在测试品牌开启，确认稳定后再全量"
                  />
                </div>
              )}

              {/* 基本信息 */}
              <div className={styles.flagInfoCard}>
                <span className={styles.drawerIcon}>{editingMeta.icon}</span>
                <div>
                  <div className={styles.drawerFlagName}>{editingMeta.name}</div>
                  <div className={styles.drawerFlagDesc}>{editingMeta.description}</div>
                </div>
              </div>

              {/* 全局开关 */}
              <div className={styles.sectionDivider}>全局开关</div>
              <div className={styles.switchRow}>
                <span className={styles.switchLabel}>启用此特性</span>
                <label className={styles.toggle}>
                  <input
                    type="checkbox"
                    checked={editState.enabled}
                    onChange={e => setEditState(s => ({ ...s, enabled: e.target.checked, rolloutPct: e.target.checked ? 100 : 0 }))}
                  />
                  <span className={styles.toggleTrack} />
                </label>
              </div>

              {/* 品牌目标 */}
              {editState.enabled && (
                <>
                  <div className={styles.sectionDivider}>目标品牌（留空 = 全量）</div>
                  {loadingBrands ? (
                    <ZSkeleton lines={3} />
                  ) : brands.length === 0 ? (
                    <ZEmpty text="暂无品牌数据" />
                  ) : (
                    <div className={styles.brandChecklist}>
                      <label className={styles.brandCheckItem}>
                        <input
                          type="checkbox"
                          checked={editState.brandIds.length === 0}
                          onChange={() => setEditState(s => ({ ...s, brandIds: [] }))}
                        />
                        <span className={styles.brandCheckLabel}>
                          <strong>全部品牌</strong>（{brands.length} 个）
                        </span>
                      </label>
                      {brands.map(b => (
                        <label key={b.brand_id} className={styles.brandCheckItem}>
                          <input
                            type="checkbox"
                            checked={editState.brandIds.includes(b.brand_id)}
                            onChange={e => {
                              setEditState(s => ({
                                ...s,
                                brandIds: e.target.checked
                                  ? [...s.brandIds, b.brand_id]
                                  : s.brandIds.filter(id => id !== b.brand_id),
                              }));
                            }}
                          />
                          <span className={styles.brandCheckLabel}>{b.name}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </>
              )}

              {/* 备注 */}
              <div className={styles.sectionDivider}>变更备注</div>
              <textarea
                className={styles.noteInput}
                rows={3}
                placeholder="记录本次开关变更的原因，便于审计追踪…"
                value={editState.note}
                onChange={e => setEditState(s => ({ ...s, note: e.target.value }))}
              />
            </>
          )}
        </div>
      </ZDrawer>
    </div>
  );
}
