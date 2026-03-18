import React, { useCallback, useEffect, useState } from 'react';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './HRQuick.module.css';

interface RiskPerson {
  person_id: string;
  person_name?: string;
  risk_score: number;
  intervention?: { action: string };
}

interface SkillRec {
  skill_name: string;
  category?: string;
  expected_yuan?: number;
}

interface BffData {
  store_id: string;
  retention: {
    high_risk_count: number;
    persons: RiskPerson[];
    recommendations: { action: string; expected_yuan?: number }[];
  } | null;
  skill_gaps: {
    total_potential_yuan: number;
    top_recommendations: SkillRec[];
  } | null;
}

function riskBadgeType(score: number): 'critical' | 'warning' | 'info' {
  if (score >= 0.7) return 'critical';
  if (score >= 0.4) return 'warning';
  return 'info';
}

function riskLabel(score: number): string {
  if (score >= 0.7) return '高风险';
  if (score >= 0.4) return '中风险';
  return '低风险';
}

export default function HRQuick() {
  const [data, setData] = useState<BffData | null>(null);
  const [loading, setLoading] = useState(true);
  const storeId = localStorage.getItem('store_id') || 'STORE001';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/hr/bff/sm/${storeId}`);
      setData(resp as BffData);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  const highRiskCount = data?.retention?.high_risk_count ?? 0;
  const gapCount = data?.skill_gaps?.top_recommendations?.length ?? 0;
  const potentialYuan = data?.skill_gaps?.total_potential_yuan ?? 0;
  const persons = data?.retention?.persons ?? [];
  const recs = data?.skill_gaps?.top_recommendations ?? [];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <span className={styles.title}>人力智能</span>
        <ZButton variant="ghost" size="sm" onClick={load}>刷新</ZButton>
      </div>

      {loading ? (
        <div className={styles.body}><ZSkeleton rows={4} /></div>
      ) : (
        <div className={styles.body}>
          {/* KPI 行 */}
          <div className={styles.kpiRow}>
            <ZCard>
              <ZKpi value={highRiskCount} label="留任风险" unit="人" />
            </ZCard>
            <ZCard>
              <ZKpi value={gapCount} label="技能缺口" unit="项" />
            </ZCard>
            <ZCard>
              <ZKpi value={`¥${potentialYuan.toFixed(0)}`} label="提升潜力" unit="/月" />
            </ZCard>
          </div>

          {/* 留人预警卡 */}
          <ZCard
            title="留任风险预警"
            extra={
              highRiskCount > 0
                ? <ZBadge type="critical" text={`${highRiskCount}人需关注`} />
                : <ZBadge type="success" text="暂无高风险" />
            }
          >
            {persons.length === 0 ? (
              <ZEmpty title="暂无风险员工" description="本店员工留任状态良好" />
            ) : (
              <div className={styles.riskList}>
                {persons.slice(0, 3).map((p) => (
                  <div key={p.person_id} className={styles.riskItem}>
                    <div className={styles.riskTop}>
                      <span className={styles.personName}>
                        {p.person_name || '员工'}
                      </span>
                      <ZBadge
                        type={riskBadgeType(p.risk_score)}
                        text={riskLabel(p.risk_score)}
                      />
                    </div>
                    <div className={styles.scoreBar}>
                      <div
                        className={styles.scoreFill}
                        data-level={riskBadgeType(p.risk_score)}
                        style={{ width: `${Math.round(p.risk_score * 100)}%` }}
                      />
                    </div>
                    {p.intervention && (
                      <div className={styles.intervention}>
                        建议：{p.intervention.action}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </ZCard>

          {/* 技能提升建议卡 */}
          <ZCard
            title="技能提升建议"
            extra={
              potentialYuan > 0
                ? <ZBadge type="info" text={`潜力¥${potentialYuan.toFixed(0)}/月`} />
                : undefined
            }
          >
            {recs.length === 0 ? (
              <ZEmpty title="暂无技能建议" description="当前技能匹配情况良好" />
            ) : (
              <div className={styles.skillList}>
                {recs.slice(0, 5).map((r, idx) => (
                  <div key={idx} className={styles.skillItem}>
                    <span className={styles.skillRank}>{idx + 1}</span>
                    <span className={styles.skillName}>{r.skill_name}</span>
                    {r.category && <ZBadge type="info" text={r.category} />}
                    {r.expected_yuan != null && (
                      <span className={styles.skillYuan}>
                        +¥{r.expected_yuan.toFixed(0)}/月
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </ZCard>
        </div>
      )}
    </div>
  );
}
