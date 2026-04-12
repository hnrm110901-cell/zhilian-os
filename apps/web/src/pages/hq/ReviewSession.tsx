/**
 * 五步闭环经营复盘
 * 路由：/hq/review
 *
 * Step 1: 拆细账 — 维度拆解（渠道×品类×时段）+ 菜品四象限矩阵
 * Step 2: 找真因 — 核查清单（必须逐项打勾才能进入下一步）
 * Step 3: 定措施 — 四字段措施（责任人 + 时限 + 动作 + 量化结果）
 * Step 4: 追执行 — KPI 偏离阈值自动预警 + 进度追踪
 * Step 5: 看结果 — 周/月复盘闭环验证
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty,
} from '../../design-system/components';
import { message } from 'antd';
import apiClient from '../../services/api';
import styles from './ReviewSession.module.css';

// ── 类型定义 ─────────────────────────────────────────────────────

interface ChannelBreakdown {
  channel: string;
  order_count: number;
  revenue_yuan: number;
  revenue_pct: number;
}

interface DishMatrix {
  dish_name: string;
  sold_qty: number;
  revenue_yuan: number;
  avg_price_yuan: number;
  quadrant: 'star' | 'cash_cow' | 'question' | 'dog';
}

interface BreakdownData {
  period: string;
  total_revenue_yuan: number;
  channel_breakdown: ChannelBreakdown[];
  dish_matrix: DishMatrix[];
  avg_dish_qty_threshold: number;
  avg_dish_revenue_threshold_yuan: number;
}

interface ChecklistItem {
  id: string;
  dimension: string;
  description: string;
  verified: boolean;
  verified_by: string | null;
  verified_at: string | null;
  verification_note: string;
}

interface ActionItem {
  id: string;
  owner: string;
  deadline: string;
  action_desc: string;
  target_kpi: string;
  progress_status: string;
  progress_pct: number;
  current_kpi_value: string;
  alert_level: string | null;
  is_achieved: boolean | null;
  actual_impact_yuan: number;
  progress_notes: Array<{ date: string; note: string; updated_by: string }>;
}

interface SessionDetail {
  id: string;
  store_id: string;
  review_type: string;
  period_label: string;
  period_start: string;
  period_end: string;
  current_step: number;
  status: string;
  created_by: string;
  created_at: string | null;
  completed_at: string | null;
  breakdown_snapshot: BreakdownData | null;
  result_summary: ResultSummary | null;
  checklists: ChecklistItem[];
  actions: ActionItem[];
}

interface SessionListItem {
  id: string;
  store_id: string;
  review_type: string;
  period_label: string;
  current_step: number;
  status: string;
  created_at: string | null;
}

interface ResultSummary {
  total_actions: number;
  completed_actions: number;
  achieved_actions: number;
  overdue_actions: number;
  completion_rate_pct: number;
  achievement_rate_pct: number;
  total_impact_yuan: number;
  actions_detail: Array<{
    id: string;
    owner: string;
    action_desc: string;
    target_kpi: string;
    current_kpi_value: string;
    is_achieved: boolean | null;
    actual_impact_yuan: number;
    progress_status: string;
  }>;
}

// ── 常量 ──────────────────────────────────────────────────────────

const STEPS = [
  { num: 1, label: '拆细账', desc: '多维度拆解，找增长抓手' },
  { num: 2, label: '找真因', desc: '一线核查清单，逐项验证' },
  { num: 3, label: '定措施', desc: '责任人+时限+动作+量化' },
  { num: 4, label: '追执行', desc: 'KPI 偏离预警，自动监控' },
  { num: 5, label: '看结果', desc: '闭环验证，经验沉淀' },
];

const QUADRANT_LABELS: Record<string, { label: string; cls: string }> = {
  star:     { label: '明星（高销高利）', cls: styles.quadrantStar },
  cash_cow: { label: '现金牛（高销低利）', cls: styles.quadrantCashCow },
  question: { label: '问题（低销高利）', cls: styles.quadrantQuestion },
  dog:      { label: '瘦狗（双低→考虑下架）', cls: styles.quadrantDog },
};

const DIMENSION_LABELS: Record<string, string> = {
  revenue_channel: '渠道营收',
  table_turnover: '翻台率',
  cost_rate: '食材成本率',
  dish_structure: '菜品结构',
  labor_efficiency: '人效',
  waste: '损耗',
  member_lifecycle: '会员生命周期',
  competitive: '竞对环境',
  supplier_price: '供应商价格',
  staff_turnover: '人员流动',
};

// ── 辅助函数 ──────────────────────────────────────────────────────

function getCurrentWeekLabel(): string {
  const now = new Date();
  const jan1 = new Date(now.getFullYear(), 0, 1);
  const days = Math.floor((now.getTime() - jan1.getTime()) / 86400000);
  const week = Math.ceil((days + jan1.getDay() + 1) / 7);
  return `${now.getFullYear()}-W${String(week).padStart(2, '0')}`;
}

function getCurrentMonthLabel(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

// ── 主组件 ────────────────────────────────────────────────────────

export default function ReviewSession() {
  // 门店 ID（实际使用时从路由参数或全局状态获取）
  const [storeId] = useState(() => localStorage.getItem('current_store_id') || 'S001');
  const [reviewType, setReviewType] = useState<'weekly' | 'monthly'>('weekly');
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [activeStep, setActiveStep] = useState(1);
  const [loading, setLoading] = useState(true);

  // Step 3 表单状态
  const [actionForm, setActionForm] = useState({
    owner: '', deadline: '', action_desc: '', target_kpi: '',
  });

  // Step 2 备注输入
  const [noteInputs, setNoteInputs] = useState<Record<string, string>>({});

  // Step 4 进度更新
  const [progressForm, setProgressForm] = useState<Record<string, { pct: number; note: string }>>({});

  // ── 数据加载 ────────────────────────────────────────────────────

  const loadSessions = useCallback(async () => {
    try {
      const resp = await apiClient.get<SessionListItem[]>(
        `/api/v1/review/sessions?store_id=${storeId}&review_type=${reviewType}`
      );
      setSessions(resp);
    } catch {
      setSessions([]);
    }
  }, [storeId, reviewType]);

  const loadDetail = useCallback(async (sessionId: string) => {
    try {
      const resp = await apiClient.get<SessionDetail>(`/api/v1/review/sessions/${sessionId}`);
      setDetail(resp);
      setActiveStep(resp.current_step);
    } catch (e: any) {
      message.error('加载复盘详情失败');
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    loadSessions().finally(() => setLoading(false));
  }, [loadSessions]);

  // ── 操作 ─────────────────────────────────────────────────────────

  const handleCreate = async () => {
    try {
      const period = reviewType === 'weekly' ? getCurrentWeekLabel() : getCurrentMonthLabel();
      const resp = await apiClient.post<SessionDetail>('/api/v1/review/sessions', {
        store_id: storeId,
        review_type: reviewType,
        period_label: period,
      });
      setDetail(resp);
      setActiveStep(1);
      message.success('复盘会已创建');
      loadSessions();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '创建失败');
    }
  };

  const handleGenerateBreakdown = async () => {
    if (!detail) return;
    try {
      const breakdown = await apiClient.post<BreakdownData>(
        `/api/v1/review/sessions/${detail.id}/breakdown`
      );
      setDetail(prev => prev ? { ...prev, breakdown_snapshot: breakdown } : prev);
      message.success('拆细账数据已生成');
    } catch (e: any) {
      message.error('生成拆细账失败');
    }
  };

  const handleVerify = async (checkId: string, verified: boolean) => {
    if (!detail) return;
    try {
      await apiClient.patch(`/api/v1/review/checklists/${checkId}`, {
        verified,
        verification_note: noteInputs[checkId] || '',
      });
      loadDetail(detail.id);
    } catch (e: any) {
      message.error('更新核查项失败');
    }
  };

  const handleAdvance = async (targetStep: number) => {
    if (!detail) return;
    try {
      await apiClient.post(`/api/v1/review/sessions/${detail.id}/advance`, {
        target_step: targetStep,
      });
      setActiveStep(targetStep);
      loadDetail(detail.id);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '推进失败');
    }
  };

  const handleCreateAction = async () => {
    if (!detail) return;
    const { owner, deadline, action_desc, target_kpi } = actionForm;
    if (!owner || !deadline || !action_desc || !target_kpi) {
      message.warning('四个字段缺一不可');
      return;
    }
    try {
      await apiClient.post(`/api/v1/review/sessions/${detail.id}/actions`, {
        owner, deadline, action_desc, target_kpi,
      });
      setActionForm({ owner: '', deadline: '', action_desc: '', target_kpi: '' });
      loadDetail(detail.id);
      message.success('措施已添加');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '创建措施失败');
    }
  };

  const handleUpdateProgress = async (actionId: string) => {
    const form = progressForm[actionId];
    if (!form) return;
    try {
      await apiClient.patch(`/api/v1/review/actions/${actionId}/progress`, {
        progress_pct: form.pct,
        note: form.note,
      });
      loadDetail(detail!.id);
      message.success('进度已更新');
    } catch (e: any) {
      message.error('更新进度失败');
    }
  };

  const handleCloseAction = async (actionId: string, isAchieved: boolean) => {
    try {
      await apiClient.post(`/api/v1/review/actions/${actionId}/close`, {
        is_achieved: isAchieved,
        actual_impact_fen: 0,
      });
      loadDetail(detail!.id);
    } catch (e: any) {
      message.error('关闭措施失败');
    }
  };

  const handleGenerateSummary = async () => {
    if (!detail) return;
    try {
      const summary = await apiClient.get<ResultSummary>(
        `/api/v1/review/sessions/${detail.id}/summary`
      );
      setDetail(prev => prev ? { ...prev, result_summary: summary } : prev);
    } catch (e: any) {
      message.error('生成结果摘要失败');
    }
  };

  // ── 渲染：加载态 ────────────────────────────────────────────────

  if (loading) return <div className={styles.container}><ZSkeleton rows={8} /></div>;

  // ── 渲染：无会话 → 创建入口 ──────────────────────────────────────

  if (!detail) {
    return (
      <div className={styles.container}>
        <div className={styles.header}>
          <h1 className={styles.title}>经营复盘会</h1>
          <div className={styles.controls}>
            <ZButton
              variant={reviewType === 'weekly' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => setReviewType('weekly')}
            >周复盘</ZButton>
            <ZButton
              variant={reviewType === 'monthly' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => setReviewType('monthly')}
            >月复盘</ZButton>
          </div>
        </div>

        {sessions.length > 0 && (
          <ZCard title="历史复盘" style={{ marginBottom: 24 }}>
            <table className={styles.channelTable}>
              <thead>
                <tr>
                  <th>周期</th>
                  <th>类型</th>
                  <th>当前步骤</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map(s => (
                  <tr key={s.id}>
                    <td>{s.period_label}</td>
                    <td>{s.review_type === 'weekly' ? '周复盘' : '月复盘'}</td>
                    <td>Step {s.current_step} / {STEPS[s.current_step - 1]?.label}</td>
                    <td>
                      <ZBadge
                        text={s.status === 'completed' ? '已完成' : s.status === 'in_progress' ? '进行中' : '草稿'}
                        type={s.status === 'completed' ? 'success' : s.status === 'in_progress' ? 'warning' : 'default'}
                      />
                    </td>
                    <td>
                      <ZButton size="sm" variant="ghost" onClick={() => loadDetail(s.id)}>
                        查看
                      </ZButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ZCard>
        )}

        <div className={styles.emptyState}>
          <div className={styles.emptyTitle}>
            开启本{reviewType === 'weekly' ? '周' : '月'}经营复盘
          </div>
          <div className={styles.emptyDesc}>
            五步闭环：拆细账 → 找真因 → 定措施 → 追执行 → 看结果<br />
            大多数餐饮品牌的经营分析会停在第三步。<br />
            让闭环的摩擦系数低到"没有理由不完成"。
          </div>
          <ZButton variant="primary" onClick={handleCreate}>
            创建{reviewType === 'weekly' ? '周' : '月'}复盘会
          </ZButton>
        </div>
      </div>
    );
  }

  // ── 渲染：五步闭环主界面 ────────────────────────────────────────

  const checkedCount = detail.checklists.filter(c => c.verified).length;
  const totalChecks = detail.checklists.length;

  return (
    <div className={styles.container}>
      {/* 标题栏 */}
      <div className={styles.header}>
        <h1 className={styles.title}>
          {detail.review_type === 'weekly' ? '周复盘' : '月复盘'} · {detail.period_label}
        </h1>
        <div className={styles.controls}>
          <ZBadge
            text={detail.status === 'completed' ? '已完成' : `Step ${detail.current_step}`}
            type={detail.status === 'completed' ? 'success' : 'info'}
          />
          <ZButton size="sm" variant="ghost" onClick={() => { setDetail(null); loadSessions(); }}>
            返回列表
          </ZButton>
        </div>
      </div>

      {/* 步骤导航 */}
      <div className={styles.stepper}>
        {STEPS.map(s => {
          const isActive = s.num === activeStep;
          const isCompleted = s.num < detail.current_step;
          const isLocked = s.num > detail.current_step + 1;
          return (
            <div
              key={s.num}
              className={`${styles.step} ${isActive ? styles.stepActive : ''} ${isCompleted ? styles.stepCompleted : ''} ${isLocked ? styles.stepLocked : ''}`}
              onClick={() => !isLocked && setActiveStep(s.num)}
            >
              <div className={styles.stepNumber}>
                {isCompleted ? '✓' : `Step ${s.num}`}
              </div>
              <div className={styles.stepLabel}>{s.label}</div>
              <div className={styles.stepDesc}>{s.desc}</div>
            </div>
          );
        })}
      </div>

      {/* 内容区 */}
      <div className={styles.content}>
        {/* ── Step 1: 拆细账 ── */}
        {activeStep === 1 && (
          <>
            {!detail.breakdown_snapshot ? (
              <div className={styles.emptyState}>
                <div className={styles.emptyTitle}>生成拆细账数据</div>
                <div className={styles.emptyDesc}>
                  维度优先于总量。总营收涨了3%不重要，<br />
                  重要的是：哪个渠道客单价最高却占比最低——这才是增长抓手。
                </div>
                <ZButton variant="primary" onClick={handleGenerateBreakdown}>
                  生成拆细账
                </ZButton>
              </div>
            ) : (
              <>
                <div className={styles.kpiRow}>
                  <ZKpi
                    label="周期营收"
                    value={`¥${detail.breakdown_snapshot.total_revenue_yuan.toLocaleString()}`}
                  />
                  <ZKpi
                    label="渠道数"
                    value={String(detail.breakdown_snapshot.channel_breakdown.length)}
                  />
                  <ZKpi
                    label="分析菜品数"
                    value={String(detail.breakdown_snapshot.dish_matrix.length)}
                  />
                </div>

                <div className={styles.breakdownGrid}>
                  {/* 渠道拆解 */}
                  <ZCard title="渠道拆解">
                    <table className={styles.channelTable}>
                      <thead>
                        <tr>
                          <th>渠道</th>
                          <th>订单数</th>
                          <th>营收</th>
                          <th>占比</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.breakdown_snapshot.channel_breakdown.map(ch => (
                          <tr key={ch.channel}>
                            <td>{ch.channel}</td>
                            <td>{ch.order_count}</td>
                            <td>¥{ch.revenue_yuan.toLocaleString()}</td>
                            <td>{ch.revenue_pct}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </ZCard>

                  {/* 菜品四象限矩阵 */}
                  <ZCard title="菜品四象限矩阵">
                    <div className={styles.quadrantGrid}>
                      {(['star', 'cash_cow', 'question', 'dog'] as const).map(q => {
                        const items = detail.breakdown_snapshot!.dish_matrix.filter(d => d.quadrant === q);
                        const info = QUADRANT_LABELS[q];
                        return (
                          <div key={q} className={`${styles.quadrant} ${info.cls}`}>
                            <div className={styles.quadrantTitle}>{info.label}</div>
                            {items.length === 0 && (
                              <div className={styles.quadrantItem}>暂无</div>
                            )}
                            {items.map(d => (
                              <div key={d.dish_name} className={styles.quadrantItem}>
                                {d.dish_name} · {d.sold_qty}份 · ¥{d.revenue_yuan}
                              </div>
                            ))}
                          </div>
                        );
                      })}
                    </div>
                  </ZCard>
                </div>

                <div className={styles.footer}>
                  <div />
                  <ZButton variant="primary" onClick={() => handleAdvance(2)}>
                    进入「找真因」→
                  </ZButton>
                </div>
              </>
            )}
          </>
        )}

        {/* ── Step 2: 找真因 ── */}
        {activeStep === 2 && (
          <>
            <div className={styles.checkProgress}>
              已验证 {checkedCount} / {totalChecks} 项
              {checkedCount < totalChecks && (
                <span>（还有 {totalChecks - checkedCount} 项需要一线核查）</span>
              )}
              <div className={styles.checkProgressBar}>
                <div
                  className={styles.checkProgressFill}
                  style={{ width: `${totalChecks ? (checkedCount / totalChecks) * 100 : 0}%` }}
                />
              </div>
            </div>

            <div className={styles.checklistWrap}>
              {detail.checklists.map(item => (
                <div
                  key={item.id}
                  className={`${styles.checkItem} ${item.verified ? styles.checkItemVerified : ''}`}
                >
                  <div
                    className={`${styles.checkBox} ${item.verified ? styles.checkBoxChecked : ''}`}
                    onClick={() => handleVerify(item.id, !item.verified)}
                  >
                    {item.verified && '✓'}
                  </div>
                  <div className={styles.checkContent}>
                    <div className={styles.checkDimension}>
                      {DIMENSION_LABELS[item.dimension] || item.dimension}
                    </div>
                    <div className={styles.checkDesc}>{item.description}</div>
                    <div className={styles.checkNote}>
                      <textarea
                        className={styles.checkNoteInput}
                        placeholder="一线验证备注…"
                        value={noteInputs[item.id] ?? item.verification_note ?? ''}
                        onChange={e => setNoteInputs(prev => ({ ...prev, [item.id]: e.target.value }))}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className={styles.footer}>
              <ZButton variant="ghost" onClick={() => setActiveStep(1)}>
                ← 拆细账
              </ZButton>
              <ZButton
                variant="primary"
                disabled={checkedCount < totalChecks}
                onClick={() => handleAdvance(3)}
              >
                {checkedCount < totalChecks
                  ? `还有 ${totalChecks - checkedCount} 项未验证`
                  : '全部验证 → 进入「定措施」'}
              </ZButton>
            </div>
          </>
        )}

        {/* ── Step 3: 定措施 ── */}
        {activeStep === 3 && (
          <>
            <ZCard title="新增措施（四字段缺一不可）" style={{ marginBottom: 24 }}>
              <div className={styles.actionForm}>
                <div>
                  <div className={styles.actionLabel}>责任人 *</div>
                  <input
                    className={styles.actionInput}
                    placeholder="如：厨师长 张三"
                    value={actionForm.owner}
                    onChange={e => setActionForm(p => ({ ...p, owner: e.target.value }))}
                  />
                </div>
                <div>
                  <div className={styles.actionLabel}>完成时限 *</div>
                  <input
                    className={styles.actionInput}
                    type="date"
                    value={actionForm.deadline}
                    onChange={e => setActionForm(p => ({ ...p, deadline: e.target.value }))}
                  />
                </div>
                <div className={styles.actionFormFull}>
                  <div className={styles.actionLabel}>具体动作 *（不是"加强培训"，而是具体频次+方法）</div>
                  <input
                    className={styles.actionInput}
                    placeholder="如：每日早会5分钟话术演练持续2周"
                    value={actionForm.action_desc}
                    onChange={e => setActionForm(p => ({ ...p, action_desc: e.target.value }))}
                  />
                </div>
                <div className={styles.actionFormFull}>
                  <div className={styles.actionLabel}>可量化结果 *</div>
                  <input
                    className={styles.actionInput}
                    placeholder="如：饮品搭售率从 39% 提升至 52%"
                    value={actionForm.target_kpi}
                    onChange={e => setActionForm(p => ({ ...p, target_kpi: e.target.value }))}
                  />
                </div>
                <div className={styles.actionFormFull} style={{ textAlign: 'right' }}>
                  <ZButton variant="primary" onClick={handleCreateAction}>
                    添加措施
                  </ZButton>
                </div>
              </div>
            </ZCard>

            <div className={styles.actionList}>
              {detail.actions.map(a => (
                <div key={a.id} className={styles.actionCard}>
                  <div className={styles.actionHeader}>
                    <span className={styles.actionOwner}>{a.owner}</span>
                    <span className={styles.actionDeadline}>截止 {a.deadline}</span>
                  </div>
                  <div className={styles.actionBody}>{a.action_desc}</div>
                  <div className={styles.actionTarget}>{a.target_kpi}</div>
                </div>
              ))}
              {detail.actions.length === 0 && (
                <ZEmpty title="暂无措施" description="请在上方添加至少一条可执行措施" />
              )}
            </div>

            <div className={styles.footer}>
              <ZButton variant="ghost" onClick={() => setActiveStep(2)}>
                ← 找真因
              </ZButton>
              <ZButton
                variant="primary"
                disabled={detail.actions.length === 0}
                onClick={() => handleAdvance(4)}
              >
                进入「追执行」→
              </ZButton>
            </div>
          </>
        )}

        {/* ── Step 4: 追执行 ── */}
        {activeStep === 4 && (
          <>
            {detail.actions.map(a => {
              const pf = progressForm[a.id] || { pct: a.progress_pct, note: '' };
              const fillCls = a.alert_level === 'critical' ? styles.progressRed
                : a.progress_status === 'overdue' ? styles.progressRed
                : a.progress_pct >= 60 ? styles.progressGreen
                : styles.progressYellow;

              return (
                <div key={a.id} className={styles.progressCard}>
                  <div className={styles.actionHeader}>
                    <span className={styles.actionOwner}>
                      {a.owner} · {a.action_desc.slice(0, 40)}{a.action_desc.length > 40 ? '...' : ''}
                    </span>
                    <span>
                      {a.alert_level === 'critical' && (
                        <span className={`${styles.alertBadge} ${styles.alertCritical}`}>逾期预警</span>
                      )}
                      {a.alert_level === 'warning' && (
                        <span className={`${styles.alertBadge} ${styles.alertWarning}`}>关注</span>
                      )}
                      <ZBadge
                        text={a.progress_status === 'completed' ? '已完成' : a.progress_status === 'overdue' ? '逾期' : `${a.progress_pct}%`}
                        type={a.progress_status === 'completed' ? 'success' : a.progress_status === 'overdue' ? 'error' : 'info'}
                      />
                    </span>
                  </div>

                  <div className={styles.progressBar}>
                    <div className={`${styles.progressFill} ${fillCls}`} style={{ width: `${a.progress_pct}%` }} />
                  </div>

                  <div className={styles.progressMeta}>
                    <span>目标: {a.target_kpi}</span>
                    <span>截止 {a.deadline}</span>
                  </div>

                  {a.progress_status !== 'completed' && (
                    <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'center' }}>
                      <input
                        type="range"
                        min={0} max={100} step={5}
                        value={pf.pct}
                        onChange={e => setProgressForm(prev => ({
                          ...prev,
                          [a.id]: { ...pf, pct: Number(e.target.value) },
                        }))}
                        style={{ flex: 1 }}
                      />
                      <span style={{ fontSize: 13, width: 36 }}>{pf.pct}%</span>
                      <input
                        className={styles.actionInput}
                        placeholder="进度备注"
                        value={pf.note}
                        onChange={e => setProgressForm(prev => ({
                          ...prev,
                          [a.id]: { ...pf, note: e.target.value },
                        }))}
                        style={{ width: 200 }}
                      />
                      <ZButton size="sm" onClick={() => handleUpdateProgress(a.id)}>
                        更新
                      </ZButton>
                    </div>
                  )}
                </div>
              );
            })}

            <div className={styles.footer}>
              <ZButton variant="ghost" onClick={() => setActiveStep(3)}>
                ← 定措施
              </ZButton>
              <ZButton variant="primary" onClick={() => handleAdvance(5)}>
                进入「看结果」→
              </ZButton>
            </div>
          </>
        )}

        {/* ── Step 5: 看结果 ── */}
        {activeStep === 5 && (
          <>
            {!detail.result_summary ? (
              <div className={styles.emptyState}>
                <div className={styles.emptyTitle}>生成闭环结果摘要</div>
                <div className={styles.emptyDesc}>
                  五步缺一步，就是断掉的环。<br />
                  点击下方按钮，汇总所有措施的执行结果。
                </div>
                <ZButton variant="primary" onClick={handleGenerateSummary}>
                  生成结果摘要
                </ZButton>
              </div>
            ) : (
              <>
                <div className={styles.summaryGrid}>
                  <div className={styles.summaryCard}>
                    <div className={styles.summaryValue}>{detail.result_summary.total_actions}</div>
                    <div className={styles.summaryLabel}>总措施数</div>
                  </div>
                  <div className={styles.summaryCard}>
                    <div className={styles.summaryValue} style={{ color: 'var(--success)' }}>
                      {detail.result_summary.completion_rate_pct}%
                    </div>
                    <div className={styles.summaryLabel}>完成率</div>
                  </div>
                  <div className={styles.summaryCard}>
                    <div className={styles.summaryValue} style={{ color: 'var(--accent)' }}>
                      {detail.result_summary.achievement_rate_pct}%
                    </div>
                    <div className={styles.summaryLabel}>达标率</div>
                  </div>
                  <div className={styles.summaryCard}>
                    <div className={styles.summaryValue}>
                      ¥{detail.result_summary.total_impact_yuan.toLocaleString()}
                    </div>
                    <div className={styles.summaryLabel}>总 ¥ 影响</div>
                  </div>
                </div>

                <ZCard title="措施达成明细">
                  <div className={styles.resultList}>
                    {detail.result_summary.actions_detail.map(a => (
                      <div key={a.id} className={styles.resultItem}>
                        <div className={`${styles.resultIcon} ${a.is_achieved ? styles.resultSuccess : styles.resultFail}`}>
                          {a.is_achieved ? '✓' : '✗'}
                        </div>
                        <div className={styles.resultBody}>
                          <div className={styles.resultAction}>{a.owner}: {a.action_desc}</div>
                          <div className={styles.resultKpi}>
                            目标: {a.target_kpi}
                            {a.current_kpi_value && ` → 实际: ${a.current_kpi_value}`}
                          </div>
                        </div>
                        <div className={styles.resultImpact} style={{ color: a.is_achieved ? 'var(--success)' : 'var(--danger)' }}>
                          {a.is_achieved === null ? (
                            <div style={{ display: 'flex', gap: 4 }}>
                              <ZButton size="sm" variant="primary" onClick={() => handleCloseAction(a.id, true)}>达标</ZButton>
                              <ZButton size="sm" variant="ghost" onClick={() => handleCloseAction(a.id, false)}>未达标</ZButton>
                            </div>
                          ) : (
                            a.is_achieved ? '达标' : '未达标'
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </ZCard>

                {detail.result_summary.overdue_actions > 0 && (
                  <div style={{ marginTop: 16, padding: 16, background: 'rgba(239,68,68,0.06)', borderRadius: 'var(--radius-md)' }}>
                    <strong style={{ color: 'var(--danger)' }}>
                      {detail.result_summary.overdue_actions} 项逾期措施
                    </strong>
                    <span style={{ color: 'var(--text-secondary)', marginLeft: 8 }}>
                      建议在下次复盘会中优先跟进
                    </span>
                  </div>
                )}

                <div className={styles.footer}>
                  <ZButton variant="ghost" onClick={() => setActiveStep(4)}>
                    ← 追执行
                  </ZButton>
                  <ZButton variant="ghost" onClick={() => { setDetail(null); loadSessions(); }}>
                    返回列表
                  </ZButton>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
