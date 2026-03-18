import React, { useState } from 'react';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty, ZTable } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './HRTalentPipeline.module.css';

interface Candidate {
  person_id: string;
  name: string;
  job_title: string | null;
  skill_count: number;
  risk_score: number | null;
  current_store: string | null;
  transfer_eligible: boolean;
}

interface SkillGap {
  skill_name: string;
  category: string | null;
  holder_count: number;
  estimated_revenue_lift: number | null;
  urgency: 'high' | 'medium';
}

interface RecruitItem {
  position: string;
  required: number;
  internal_available: number;
  shortage: number;
  recruit_cost_yuan: number;
}

interface TimelineItem {
  week: number;
  milestone: string;
  target_date: string;
  urgent: boolean;
}

interface PipelineResult {
  new_store_org_node_id: string;
  open_date: string | null;
  total_required: number;
  eligible_candidates_count: number;
  readiness_score: number;
  readiness_pct: number;
  candidates: Candidate[];
  skill_gaps: SkillGap[];
  recruit_plan: RecruitItem[];
  total_recruit_cost_yuan: number;
  training_timeline: TimelineItem[];
}

const POSITION_LABELS: Record<string, string> = {
  kitchen: '厨房', service: '前厅', cashier: '收银',
  supervisor: '督导', manager: '店长',
};

export default function HQHrTalentPipeline() {
  const [orgNodeId, setOrgNodeId] = useState('');
  const [openDate, setOpenDate] = useState('');
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const analyze = async () => {
    if (!orgNodeId.trim()) {
      setError('请输入新店组织节点ID');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const resp = await apiClient.post('/api/v1/hr/talent-pipeline/analyze', {
        new_store_org_node_id: orgNodeId.trim(),
        open_date: openDate || null,
      });
      setResult(resp as PipelineResult);
    } catch {
      setError('分析失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  const candidateColumns: ZTableColumn<Candidate>[] = [
    { key: 'name', title: '姓名', render: (r) => r.name },
    { key: 'job_title', title: '岗位', render: (r) => r.job_title || '—' },
    { key: 'current_store', title: '当前门店', render: (r) => r.current_store || '—' },
    {
      key: 'skill_count',
      title: '技能认证',
      render: (r) => `${r.skill_count} 项`,
    },
    {
      key: 'risk_score',
      title: '离职风险',
      render: (r) =>
        r.risk_score != null
          ? <ZBadge
              type={r.risk_score >= 0.7 ? 'critical' : r.risk_score >= 0.4 ? 'warning' : 'success'}
              text={`${Math.round(r.risk_score * 100)}%`}
            />
          : <ZBadge type="info" text="未评估" />,
    },
    {
      key: 'transfer_eligible',
      title: '可调配',
      render: (r) => (
        <ZBadge type={r.transfer_eligible ? 'success' : 'warning'}
          text={r.transfer_eligible ? '可调' : '风险较高'} />
      ),
    },
  ];

  const skillGapColumns: ZTableColumn<SkillGap>[] = [
    { key: 'skill_name', title: '技能', render: (r) => r.skill_name },
    {
      key: 'category',
      title: '类别',
      render: (r) => r.category ? <ZBadge type="info" text={r.category} /> : <span>—</span>,
    },
    {
      key: 'holder_count',
      title: '已掌握人数',
      render: (r) => `${r.holder_count} 人`,
    },
    {
      key: 'urgency',
      title: '紧急程度',
      render: (r) => (
        <ZBadge type={r.urgency === 'high' ? 'critical' : 'warning'}
          text={r.urgency === 'high' ? '紧急' : '待培训'} />
      ),
    },
    {
      key: 'estimated_revenue_lift',
      title: '预期增收/月',
      render: (r) =>
        r.estimated_revenue_lift
          ? <span className={styles.liftAmount}>¥{r.estimated_revenue_lift.toFixed(0)}</span>
          : <span>—</span>,
    },
  ];

  const recruitColumns: ZTableColumn<RecruitItem>[] = [
    {
      key: 'position',
      title: '岗位',
      render: (r) => POSITION_LABELS[r.position] || r.position,
    },
    { key: 'required', title: '需求', render: (r) => `${r.required} 人` },
    { key: 'internal_available', title: '内部调配', render: (r) => `${r.internal_available} 人` },
    {
      key: 'shortage',
      title: '缺口',
      render: (r) => (
        <ZBadge type={r.shortage > 0 ? 'critical' : 'success'}
          text={r.shortage > 0 ? `缺 ${r.shortage} 人` : '充足'} />
      ),
    },
    {
      key: 'recruit_cost_yuan',
      title: '补招成本估算',
      render: (r) =>
        r.shortage > 0
          ? <span className={styles.costAmount}>¥{r.recruit_cost_yuan.toFixed(0)}</span>
          : <span>—</span>,
    },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2 className={styles.title}>新店人才梯队 (WF-5)</h2>
      </div>

      <div className={styles.body}>
        {/* 输入区 */}
        <ZCard title="分析参数">
          <div className={styles.inputGroup}>
            <div className={styles.inputItem}>
              <label className={styles.label}>新店组织节点 ID *</label>
              <input
                className={styles.input}
                value={orgNodeId}
                onChange={(e) => setOrgNodeId(e.target.value)}
                placeholder="例：ORG-NEWSTORE-001"
              />
            </div>
            <div className={styles.inputItem}>
              <label className={styles.label}>预计开业日期</label>
              <input
                className={styles.input}
                type="date"
                value={openDate}
                onChange={(e) => setOpenDate(e.target.value)}
              />
            </div>
            <ZButton variant="primary" size="sm" onClick={analyze} disabled={loading}>
              {loading ? '分析中…' : '开始分析'}
            </ZButton>
          </div>
          {error && <div className={styles.error}>{error}</div>}
        </ZCard>

        {loading && <ZSkeleton rows={6} />}

        {result && !loading && (
          <>
            {/* KPI 汇总 */}
            <div className={styles.kpiRow}>
              <ZCard>
                <ZKpi
                  value={`${result.readiness_pct}%`}
                  label="人才就绪率"
                />
              </ZCard>
              <ZCard>
                <ZKpi
                  value={result.eligible_candidates_count}
                  label="可调配人员"
                  unit="人"
                />
              </ZCard>
              <ZCard>
                <ZKpi
                  value={result.total_required}
                  label="岗位总需求"
                  unit="人"
                />
              </ZCard>
              <ZCard>
                <ZKpi
                  value={`¥${result.total_recruit_cost_yuan.toFixed(0)}`}
                  label="补招总成本估算"
                />
              </ZCard>
            </div>

            {/* 就绪率进度条 */}
            <ZCard
              title="人才就绪状态"
              extra={
                <ZBadge
                  type={result.readiness_pct >= 80 ? 'success' : result.readiness_pct >= 50 ? 'warning' : 'critical'}
                  text={result.readiness_pct >= 80 ? '准备就绪' : result.readiness_pct >= 50 ? '基本就绪' : '需补招'}
                />
              }
            >
              <div className={styles.readinessBar}>
                <div
                  className={styles.readinessFill}
                  style={{ width: `${result.readiness_pct}%` }}
                  data-level={
                    result.readiness_pct >= 80 ? 'success'
                      : result.readiness_pct >= 50 ? 'warning' : 'critical'
                  }
                />
              </div>
              <div className={styles.readinessLabel}>
                {result.eligible_candidates_count} / {result.total_required} 人
              </div>
            </ZCard>

            <div className={styles.mainGrid}>
              {/* 内部候选人 */}
              <ZCard
                title="内部储备候选人"
                extra={<ZBadge type="info" text={`共${result.candidates.length}人`} />}
              >
                {result.candidates.length === 0 ? (
                  <ZEmpty title="暂无候选人" description="集团内暂无符合条件的储备人员" />
                ) : (
                  <ZTable data={result.candidates} columns={candidateColumns} rowKey="person_id" />
                )}
              </ZCard>

              {/* 技能缺口 */}
              <ZCard
                title="技能缺口清单"
                extra={<ZBadge type={result.skill_gaps.length > 0 ? 'warning' : 'success'}
                  text={`${result.skill_gaps.length}个缺口`} />}
              >
                {result.skill_gaps.length === 0 ? (
                  <ZEmpty title="无技能缺口" description="候选人技能覆盖充分" />
                ) : (
                  <ZTable data={result.skill_gaps} columns={skillGapColumns} rowKey="skill_name" />
                )}
              </ZCard>
            </div>

            {/* 岗位补招计划 */}
            {result.recruit_plan.length > 0 && (
              <ZCard
                title="岗位补招计划"
                extra={<ZBadge type="critical" text={`总成本 ¥${result.total_recruit_cost_yuan.toFixed(0)}`} />}
              >
                <ZTable data={result.recruit_plan} columns={recruitColumns} rowKey="position" />
              </ZCard>
            )}

            {/* 培训时间线 */}
            {result.training_timeline.length > 0 && (
              <ZCard title="培训时间线">
                <div className={styles.timeline}>
                  {result.training_timeline.map((t) => (
                    <div key={t.week} className={styles.timelineItem}>
                      <div className={`${styles.timelineDot} ${t.urgent ? styles.dotUrgent : ''}`} />
                      <div className={styles.timelineContent}>
                        <div className={styles.timelineMilestone}>
                          {t.milestone}
                          {t.urgent && <ZBadge type="critical" text="紧急" />}
                        </div>
                        <div className={styles.timelineDate}>{t.target_date}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </ZCard>
            )}
          </>
        )}
      </div>
    </div>
  );
}
