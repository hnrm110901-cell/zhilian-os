/**
 * 员工成长旅程页面
 * 路由: /employee-growth
 * 功能: 成长计划 · 技能矩阵 · 里程碑墙 · 幸福指数 · 全旅程视图
 */
import React, { useCallback, useEffect, useState } from 'react';
import { hrService } from '../../services/hrService';
import type {
  GrowthPlanItem,
  MilestoneItem,
  WellbeingInsights,
  SkillDefinitionItem,
  EmployeeJourney,
} from '../../services/hrService';
import styles from './EmployeeGrowthPage.module.css';

const STORE_ID = localStorage.getItem('store_id') || 'STORE_001';

type TabKey = 'plans' | 'skills' | 'milestones' | 'wellbeing' | 'journey';

const TAB_LABELS: Record<TabKey, string> = {
  plans: '成长计划',
  skills: '技能矩阵',
  milestones: '里程碑墙',
  wellbeing: '幸福指数',
  journey: '全旅程视图',
};

const MILESTONE_ICONS: Record<string, string> = {
  onboard: '🎉', trial_pass: '✅', probation_pass: '🏅',
  first_praise: '⭐', skill_up: '📈', zero_waste_month: '♻️',
  sales_champion: '🏆', anniversary: '🎂', promotion: '🚀',
  mentor_first: '🤝', culture_star: '💫', training_complete: '📚',
  perfect_attendance: '💯', custom: '🎯',
};

const LEVEL_LABELS: Record<string, string> = {
  novice: '学徒', apprentice: '熟手', journeyman: '能手',
  expert: '高手', master: '匠人',
};

const STATUS_LABELS: Record<string, string> = {
  active: '进行中', completed: '已完成', paused: '已暂停', cancelled: '已取消',
};

const DIM_LABELS: Record<string, string> = {
  achievement: '成就感', belonging: '归属感', growth: '成长感',
  balance: '平衡感', culture: '文化感',
};

const EmployeeGrowthPage: React.FC = () => {
  const [tab, setTab] = useState<TabKey>('plans');
  const [loading, setLoading] = useState(true);

  // 成长计划
  const [plans, setPlans] = useState<GrowthPlanItem[]>([]);
  const [planFilter, setPlanFilter] = useState<string>('');

  // 技能矩阵
  const [skills, setSkills] = useState<SkillDefinitionItem[]>([]);

  // 里程碑
  const [milestones, setMilestones] = useState<MilestoneItem[]>([]);

  // 幸福指数
  const [wellbeing, setWellbeing] = useState<WellbeingInsights | null>(null);

  // 全旅程
  const [journeyId, setJourneyId] = useState('');
  const [journey, setJourney] = useState<EmployeeJourney | null>(null);

  const loadPlans = useCallback(async () => {
    setLoading(true);
    try {
      const data = await hrService.getGrowthPlans(STORE_ID, undefined, planFilter || undefined);
      setPlans(data.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, [planFilter]);

  const loadSkills = useCallback(async () => {
    setLoading(true);
    try {
      const data = await hrService.getSkillDefinitions(STORE_ID);
      setSkills(data.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  const loadMilestones = useCallback(async () => {
    setLoading(true);
    try {
      const data = await hrService.getMilestones(STORE_ID, undefined, 100);
      setMilestones(data.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  const loadWellbeing = useCallback(async () => {
    setLoading(true);
    try {
      const data = await hrService.getWellbeingInsights(STORE_ID);
      setWellbeing(data);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  const loadJourney = useCallback(async (empId: string) => {
    if (!empId) return;
    setLoading(true);
    try {
      const data = await hrService.getEmployeeJourney(empId);
      setJourney(data);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (tab === 'plans') loadPlans();
    else if (tab === 'skills') loadSkills();
    else if (tab === 'milestones') loadMilestones();
    else if (tab === 'wellbeing') loadWellbeing();
  }, [tab, loadPlans, loadSkills, loadMilestones, loadWellbeing]);

  const handleScanMilestones = async () => {
    try {
      const result = await hrService.scanMilestones(STORE_ID);
      alert(`扫描完成，触发 ${result.triggered_count} 个新里程碑`);
      loadMilestones();
    } catch { /* silent */ }
  };

  // ── 成长计划 Tab ──
  const renderPlans = () => (
    <>
      <div className={styles.filterRow}>
        <select className={styles.select} value={planFilter} onChange={e => setPlanFilter(e.target.value)}>
          <option value="">全部状态</option>
          <option value="active">进行中</option>
          <option value="completed">已完成</option>
          <option value="paused">已暂停</option>
        </select>
      </div>
      {plans.length === 0 ? (
        <div className={styles.empty}>暂无成长计划</div>
      ) : (
        plans.map(p => (
          <div key={p.id} className={styles.planCard}>
            <div className={styles.planHeader}>
              <div>
                <h3 className={styles.planName}>{p.plan_name}</h3>
                <span className={styles.cardSub}>
                  {p.employee_name} · {p.target_position ? `目标: ${p.target_position}` : ''}
                  {p.mentor_name ? ` · 导师: ${p.mentor_name}` : ''}
                </span>
              </div>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                {p.ai_generated && <span className={`${styles.badge} ${styles.badgeAI}`}>AI生成</span>}
                <span className={`${styles.badge} ${
                  p.status === 'active' ? styles.badgeActive :
                  p.status === 'completed' ? styles.badgeCompleted : styles.badgePaused
                }`}>{STATUS_LABELS[p.status] || p.status}</span>
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'rgba(255,255,255,0.5)', marginBottom: 4 }}>
              <span>进度 {p.completed_tasks}/{p.total_tasks} 项</span>
              <span>{p.progress_pct}%</span>
            </div>
            <div className={styles.progressBar}>
              <div className={styles.progressFill} style={{ width: `${p.progress_pct}%` }} />
            </div>
            {p.target_date && (
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.38)', marginTop: 6 }}>
                目标日期: {p.target_date}
              </div>
            )}
          </div>
        ))
      )}
    </>
  );

  // ── 技能矩阵 Tab ──
  const renderSkills = () => {
    const categories = [...new Set(skills.map(s => s.skill_category))];
    return (
      <>
        {skills.length === 0 ? (
          <div className={styles.empty}>暂无技能定义</div>
        ) : (
          <div className={styles.grid}>
            {categories.map(cat => (
              <div key={cat} className={styles.card}>
                <h3 className={styles.cardTitle}>{cat}</h3>
                <div className={styles.skillList}>
                  {skills.filter(s => s.skill_category === cat).map(s => (
                    <div key={s.id} className={styles.skillRow}>
                      <span className={styles.skillName}>{s.skill_name}</span>
                      <div className={styles.skillBarWrap}>
                        <div
                          className={styles.skillBarFill}
                          style={{
                            width: `${
                              s.required_level === 'master' ? 100 :
                              s.required_level === 'expert' ? 80 :
                              s.required_level === 'journeyman' ? 60 :
                              s.required_level === 'apprentice' ? 40 : 20
                            }%`,
                          }}
                        />
                      </div>
                      <span className={styles.skillScore}>
                        {LEVEL_LABELS[s.required_level] || s.required_level}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </>
    );
  };

  // ── 里程碑墙 Tab ──
  const renderMilestones = () => (
    <>
      <div className={styles.filterRow}>
        <button className={styles.btn} onClick={handleScanMilestones}>
          扫描新里程碑
        </button>
      </div>
      {milestones.length === 0 ? (
        <div className={styles.empty}>暂无里程碑记录</div>
      ) : (
        <div className={styles.milestoneWall}>
          {milestones.map(m => (
            <div key={m.id} className={styles.milestone}>
              <span className={styles.milestoneBadge}>
                {MILESTONE_ICONS[m.milestone_type] || '🎯'}
              </span>
              <div className={styles.milestoneInfo}>
                <div className={styles.milestoneTitle}>{m.title}</div>
                <div className={styles.milestoneMeta}>
                  {m.employee_name} · {m.achieved_at}
                  {m.reward_yuan > 0 ? ` · ¥${m.reward_yuan}` : ''}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );

  // ── 幸福指数 Tab ──
  const renderWellbeing = () => {
    if (!wellbeing) return <div className={styles.empty}>暂无幸福指数数据</div>;
    return (
      <>
        <div className={styles.statsRow}>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>本月提交数</div>
            <div className={styles.statValue}>{wellbeing.total_submissions}</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>综合均分</div>
            <div className={`${styles.statValue} ${styles.statMint}`}>
              {wellbeing.avg_overall}
            </div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>需关怀人数</div>
            <div className={styles.statValue} style={{ color: wellbeing.care_warnings?.length > 0 ? '#FF6B6B' : undefined }}>
              {wellbeing.care_warnings?.length || 0}
            </div>
          </div>
        </div>

        <div className={styles.card} style={{ marginBottom: 16 }}>
          <h3 className={styles.cardTitle}>五维幸福指数</h3>
          <div className={styles.wellbeingGrid}>
            {Object.entries(wellbeing.dimensions || {}).map(([key, val]) => (
              <div key={key} className={styles.dimCard}>
                <div className={`${styles.dimScore} ${val < 5 ? styles.dimLow : ''}`}>
                  {val}
                </div>
                <div className={styles.dimLabel}>{DIM_LABELS[key] || key}</div>
              </div>
            ))}
          </div>
        </div>

        {wellbeing.trend && wellbeing.trend.length > 0 && (
          <div className={styles.card} style={{ marginBottom: 16 }}>
            <h3 className={styles.cardTitle}>趋势（近3月）</h3>
            <div style={{ display: 'flex', gap: 16, fontSize: 13 }}>
              {wellbeing.trend.map(t => (
                <div key={t.period} style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 18, fontWeight: 700, color: '#0AAF9A' }}>{t.avg}</div>
                  <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 11 }}>{t.period}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {wellbeing.care_warnings && wellbeing.care_warnings.length > 0 && (
          <div className={styles.card}>
            <h3 className={styles.cardTitle} style={{ color: '#FF6B6B' }}>需关怀员工</h3>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr><th>员工</th><th>综合分</th><th>建议</th></tr>
                </thead>
                <tbody>
                  {wellbeing.care_warnings.map(w => (
                    <tr key={w.employee_id} className={styles.warnRow}>
                      <td>{w.employee_name}</td>
                      <td>{w.score}</td>
                      <td>建议一对一沟通</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </>
    );
  };

  // ── 全旅程视图 Tab ──
  const renderJourney = () => (
    <>
      <div className={styles.filterRow}>
        <input
          className={styles.select}
          placeholder="输入员工ID"
          value={journeyId}
          onChange={e => setJourneyId(e.target.value)}
        />
        <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={() => loadJourney(journeyId)}>
          查看旅程
        </button>
      </div>
      {!journey ? (
        <div className={styles.empty}>输入员工ID查看完整成长旅程</div>
      ) : (
        <>
          {/* 员工基本信息 */}
          <div className={styles.statsRow}>
            <div className={styles.statCard}>
              <div className={styles.statLabel}>姓名</div>
              <div className={styles.statValue} style={{ fontSize: 16 }}>{journey.employee.name}</div>
            </div>
            <div className={styles.statCard}>
              <div className={styles.statLabel}>岗位</div>
              <div className={styles.statValue} style={{ fontSize: 16 }}>{journey.employee.position}</div>
            </div>
            <div className={styles.statCard}>
              <div className={styles.statLabel}>入职日期</div>
              <div className={styles.statValue} style={{ fontSize: 16 }}>{journey.employee.hire_date}</div>
            </div>
            <div className={styles.statCard}>
              <div className={styles.statLabel}>在职天数</div>
              <div className={`${styles.statValue} ${styles.statMint}`}>{journey.employee.tenure_days}</div>
            </div>
          </div>

          <div className={styles.grid}>
            {/* 技能雷达 */}
            <div className={styles.card}>
              <h3 className={styles.cardTitle}>技能水平</h3>
              {journey.skill_radar.length === 0 ? (
                <div className={styles.empty}>暂无技能评估</div>
              ) : (
                <div className={styles.skillList}>
                  {journey.skill_radar.map((s, i) => (
                    <div key={i} className={styles.skillRow}>
                      <span className={styles.skillName}>{s.skill_name}</span>
                      <div className={styles.skillBarWrap}>
                        <div className={styles.skillBarFill} style={{ width: `${s.score}%` }} />
                      </div>
                      <span className={styles.skillScore}>{s.score}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 幸福指数 */}
            <div className={styles.card}>
              <h3 className={styles.cardTitle}>幸福指数</h3>
              {!journey.wellbeing ? (
                <div className={styles.empty}>暂无数据</div>
              ) : (
                <>
                  <div style={{ textAlign: 'center', marginBottom: 12 }}>
                    <div style={{ fontSize: 32, fontWeight: 700, color: '#0AAF9A' }}>
                      {journey.wellbeing.overall_score}
                    </div>
                    <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)' }}>
                      {journey.wellbeing.latest_period} 综合分
                    </div>
                  </div>
                  <div className={styles.wellbeingGrid}>
                    {Object.entries(journey.wellbeing.dimensions || {}).map(([k, v]) => (
                      <div key={k} className={styles.dimCard}>
                        <div className={`${styles.dimScore} ${v < 5 ? styles.dimLow : ''}`} style={{ fontSize: 16 }}>{v}</div>
                        <div className={styles.dimLabel}>{DIM_LABELS[k] || k}</div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* 里程碑 */}
          {journey.milestones.length > 0 && (
            <div className={styles.card} style={{ marginBottom: 16 }}>
              <h3 className={styles.cardTitle}>里程碑</h3>
              <div className={styles.milestoneWall}>
                {journey.milestones.map(m => (
                  <div key={m.id} className={styles.milestone}>
                    <span className={styles.milestoneBadge}>
                      {MILESTONE_ICONS[m.milestone_type] || '🎯'}
                    </span>
                    <div className={styles.milestoneInfo}>
                      <div className={styles.milestoneTitle}>{m.title}</div>
                      <div className={styles.milestoneMeta}>{m.achieved_at}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 成长计划 */}
          {journey.growth_plans.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <h3 className={styles.cardTitle}>成长计划</h3>
              {journey.growth_plans.map(p => (
                <div key={p.id} className={styles.planCard}>
                  <div className={styles.planHeader}>
                    <h3 className={styles.planName}>{p.plan_name}</h3>
                    <span className={`${styles.badge} ${
                      p.status === 'active' ? styles.badgeActive : styles.badgeCompleted
                    }`}>{STATUS_LABELS[p.status] || p.status}</span>
                  </div>
                  <div className={styles.progressBar}>
                    <div className={styles.progressFill} style={{ width: `${p.progress_pct}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 时间线 */}
          {journey.timeline.length > 0 && (
            <div className={styles.card}>
              <h3 className={styles.cardTitle}>成长时间线</h3>
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr><th>日期</th><th>类型</th><th>事件</th></tr>
                  </thead>
                  <tbody>
                    {journey.timeline.map((t, i) => (
                      <tr key={i}>
                        <td>{t.date}</td>
                        <td>{t.type}</td>
                        <td>{t.title}{t.description ? ` — ${t.description}` : ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </>
  );

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>员工成长旅程</h1>
        <div className={styles.tabs}>
          {(Object.keys(TAB_LABELS) as TabKey[]).map(k => (
            <button
              key={k}
              className={`${styles.tab} ${tab === k ? styles.tabActive : ''}`}
              onClick={() => setTab(k)}
            >
              {TAB_LABELS[k]}
            </button>
          ))}
        </div>
      </div>

      {loading && tab !== 'journey' ? (
        <div className={styles.loading}>加载中...</div>
      ) : (
        <>
          {tab === 'plans' && renderPlans()}
          {tab === 'skills' && renderSkills()}
          {tab === 'milestones' && renderMilestones()}
          {tab === 'wellbeing' && renderWellbeing()}
          {tab === 'journey' && renderJourney()}
        </>
      )}
    </div>
  );
};

export default EmployeeGrowthPage;
