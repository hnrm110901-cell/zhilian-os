import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './HRPerson.module.css';

interface Assignment {
  id: string;
  employment_type: string;
  start_date: string | null;
  end_date: string | null;
  status: string;
  store_name: string | null;
  store_id: string | null;
  job_title: string | null;
}

interface Achievement {
  id: string;
  skill_name: string;
  category: string | null;
  achieved_at: string | null;
  evidence: string | null;
  estimated_revenue_lift: number | null;
}

interface RiskSignal {
  risk_score: number;
  risk_factors: Record<string, unknown>;
  intervention_status: string | null;
  computed_at: string | null;
}

interface Capture {
  id: string;
  trigger_type: string | null;
  context: string | null;
  quality_score: number | null;
  created_at: string | null;
}

interface PersonDetail {
  id: string;
  name: string;
  phone: string | null;
  email: string | null;
  photo_url: string | null;
  created_at: string | null;
  assignments: Assignment[];
  achievements: Achievement[];
  latest_risk: RiskSignal | null;
  recent_captures: Capture[];
}

const EMP_TYPE_LABELS: Record<string, string> = {
  full_time: '全职', hourly: '小时工', outsourced: '外包',
  dispatched: '派遣', partner: '合伙人',
};

const TRIGGER_LABELS: Record<string, string> = {
  exit: '离职采集', monthly_review: '月度复盘', incident: '事件记录',
  onboarding: '入职引导', growth_review: '成长评议',
  talent_assessment: '人才评估', legacy_import: '历史导入',
};

function riskLevel(score: number): 'critical' | 'warning' | 'success' {
  if (score >= 0.7) return 'critical';
  if (score >= 0.4) return 'warning';
  return 'success';
}

export default function SMHRPerson() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<PersonDetail | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/hr/persons/${id}`);
      setData(resp as PersonDetail);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.header}>
          <ZButton variant="ghost" size="sm" onClick={() => navigate(-1)}>← 返回</ZButton>
        </div>
        <div className={styles.body}><ZSkeleton rows={6} /></div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className={styles.page}>
        <div className={styles.header}>
          <ZButton variant="ghost" size="sm" onClick={() => navigate(-1)}>← 返回</ZButton>
        </div>
        <div className={styles.body}>
          <ZEmpty title="员工不存在" description="该员工信息加载失败" />
        </div>
      </div>
    );
  }

  const activeAssignment = data.assignments.find((a) => a.status === 'active');
  const totalRevenueLift = data.achievements.reduce(
    (s, a) => s + (a.estimated_revenue_lift ?? 0), 0,
  );

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <ZButton variant="ghost" size="sm" onClick={() => navigate(-1)}>← 返回</ZButton>
        <ZButton variant="ghost" size="sm" onClick={load}>刷新</ZButton>
      </div>

      <div className={styles.body}>
        {/* 头像 + 基本信息 */}
        <ZCard>
          <div className={styles.profileRow}>
            <div className={styles.avatar}>
              {data.name.slice(0, 1)}
            </div>
            <div className={styles.profileInfo}>
              <div className={styles.personName}>{data.name}</div>
              {activeAssignment && (
                <div className={styles.personMeta}>
                  {activeAssignment.job_title || '—'}
                  &ensp;·&ensp;
                  {EMP_TYPE_LABELS[activeAssignment.employment_type] || activeAssignment.employment_type}
                  &ensp;·&ensp;
                  {activeAssignment.store_name || '—'}
                </div>
              )}
              {data.phone && (
                <div className={styles.personMeta}>{data.phone}</div>
              )}
            </div>
            {data.latest_risk && (
              <ZBadge
                type={riskLevel(data.latest_risk.risk_score)}
                text={`风险 ${Math.round(data.latest_risk.risk_score * 100)}%`}
              />
            )}
          </div>
        </ZCard>

        {/* KPI 行 */}
        <div className={styles.kpiRow}>
          <ZCard>
            <ZKpi
              value={data.achievements.length}
              label="技能认证"
              unit="项"
            />
          </ZCard>
          <ZCard>
            <ZKpi
              value={data.latest_risk ? `${Math.round(data.latest_risk.risk_score * 100)}%` : '—'}
              label="离职风险"
            />
          </ZCard>
          <ZCard>
            <ZKpi
              value={totalRevenueLift > 0 ? `¥${totalRevenueLift.toFixed(0)}` : '—'}
              label="技能潜在增收/月"
            />
          </ZCard>
        </div>

        {/* 技能认证 */}
        <ZCard
          title="技能认证"
          extra={<ZBadge type="info" text={`${data.achievements.length}项`} />}
        >
          {data.achievements.length === 0 ? (
            <ZEmpty title="暂无技能认证" description="尚未完成技能认证" />
          ) : (
            <div className={styles.achievementList}>
              {data.achievements.map((a) => (
                <div key={a.id} className={styles.achievementItem}>
                  <div className={styles.achievementTop}>
                    <span className={styles.skillName}>{a.skill_name}</span>
                    {a.category && <ZBadge type="info" text={a.category} />}
                    {a.estimated_revenue_lift && (
                      <span className={styles.liftAmount}>
                        +¥{a.estimated_revenue_lift.toFixed(0)}/月
                      </span>
                    )}
                  </div>
                  <div className={styles.achievementMeta}>
                    {a.achieved_at
                      ? new Date(a.achieved_at).toLocaleDateString('zh-CN')
                      : '—'}
                    {a.evidence && <span className={styles.evidence}>{a.evidence}</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </ZCard>

        {/* 离职风险详情 */}
        {data.latest_risk && (
          <ZCard
            title="留任风险详情"
            extra={
              <ZBadge
                type={riskLevel(data.latest_risk.risk_score)}
                text={data.latest_risk.intervention_status === 'resolved' ? '已干预' : '待处理'}
              />
            }
          >
            <div className={styles.riskDetails}>
              {Object.entries(data.latest_risk.risk_factors).map(([k, v]) => (
                <div key={k} className={styles.riskFactor}>
                  <span className={styles.riskKey}>{k}</span>
                  <span className={styles.riskVal}>{String(v)}</span>
                </div>
              ))}
              {data.latest_risk.computed_at && (
                <div className={styles.riskMeta}>
                  评估时间：{new Date(data.latest_risk.computed_at).toLocaleDateString('zh-CN')}
                </div>
              )}
            </div>
          </ZCard>
        )}

        {/* 近期知识采集 */}
        <ZCard title="近期知识采集">
          {data.recent_captures.length === 0 ? (
            <ZEmpty title="暂无采集记录" description="尚未进行知识采集" />
          ) : (
            <div className={styles.captureList}>
              {data.recent_captures.map((c) => (
                <div key={c.id} className={styles.captureItem}>
                  <div className={styles.captureTop}>
                    <ZBadge
                      type="info"
                      text={TRIGGER_LABELS[c.trigger_type ?? ''] || c.trigger_type || '—'}
                    />
                    {c.quality_score != null && (
                      <ZBadge
                        type={c.quality_score >= 0.8 ? 'success' : c.quality_score >= 0.5 ? 'warning' : 'critical'}
                        text={`${Math.round(c.quality_score * 100)}分`}
                      />
                    )}
                    <span className={styles.captureDate}>
                      {c.created_at
                        ? new Date(c.created_at).toLocaleDateString('zh-CN')
                        : '—'}
                    </span>
                  </div>
                  {c.context && (
                    <div className={styles.captureContext}>{c.context}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </ZCard>

        {/* 在岗历史 */}
        <ZCard title="在岗历史">
          {data.assignments.length === 0 ? (
            <ZEmpty title="暂无记录" />
          ) : (
            <div className={styles.assignmentList}>
              {data.assignments.map((a) => (
                <div key={a.id} className={styles.assignmentItem}>
                  <div className={styles.assignmentTop}>
                    <span className={styles.assignmentStore}>{a.store_name || '—'}</span>
                    <ZBadge
                      type={a.status === 'active' ? 'success' : 'info'}
                      text={a.status === 'active' ? '在职' : '已离职'}
                    />
                  </div>
                  <div className={styles.assignmentMeta}>
                    {a.job_title || '—'}
                    &ensp;·&ensp;
                    {EMP_TYPE_LABELS[a.employment_type] || a.employment_type}
                    &ensp;·&ensp;
                    {a.start_date ? new Date(a.start_date).toLocaleDateString('zh-CN') : '—'}
                    {a.end_date && ` — ${new Date(a.end_date).toLocaleDateString('zh-CN')}`}
                  </div>
                </div>
              ))}
            </div>
          )}
        </ZCard>
      </div>
    </div>
  );
}
