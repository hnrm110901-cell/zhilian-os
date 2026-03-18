import React, { useCallback, useEffect, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty, ZTable } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './HR.module.css';

interface RiskDistribution {
  high: number;
  medium: number;
  low: number;
  total: number;
}

interface KnowledgeStats {
  total_30d: number;
  by_type: Record<string, number>;
}

interface SkillHealthRow {
  store_id: string;
  store_name: string;
  total_skills: number;
  achieved_skills: number;
  coverage_pct: number;
}

interface QuickStats {
  total_employees: number;
  monthly_payroll_yuan: number;
  attendance_rate_pct: number;
  pending_approvals: number;
}

interface BffData {
  org_node_id: string;
  risk_distribution: RiskDistribution | null;
  knowledge_stats: KnowledgeStats | null;
  skill_health_ranking: SkillHealthRow[] | null;
  quick_stats?: QuickStats | null;
}

const TRIGGER_TYPE_LABELS: Record<string, string> = {
  exit: '离职采集',
  monthly_review: '月度复盘',
  incident: '事件记录',
  onboarding: '入职引导',
  growth_review: '成长评议',
  talent_assessment: '人才评估',
  legacy_import: '历史导入',
};

export default function HQHr() {
  const [data, setData] = useState<BffData | null>(null);
  const [loading, setLoading] = useState(true);
  const orgNodeId = localStorage.getItem('org_node_id') || 'ROOT';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/hr/bff/hq/${orgNodeId}`);
      setData(resp as BffData);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [orgNodeId]);

  useEffect(() => { load(); }, [load]);

  // ECharts 留任风险饼图配置
  const riskPieOption = data?.risk_distribution
    ? {
        tooltip: { trigger: 'item' },
        legend: { bottom: 0, itemGap: 16 },
        series: [
          {
            type: 'pie',
            radius: ['40%', '70%'],
            center: ['50%', '45%'],
            label: { show: false },
            data: [
              { value: data.risk_distribution.high, name: '高风险', itemStyle: { color: '#f5222d' } },
              { value: data.risk_distribution.medium, name: '中风险', itemStyle: { color: '#fa8c16' } },
              { value: data.risk_distribution.low, name: '低风险', itemStyle: { color: '#52c41a' } },
            ],
          },
        ],
      }
    : null;

  // 知识采集柱图
  const knowledgeBarOption = data?.knowledge_stats?.by_type
    ? (() => {
        const entries = Object.entries(data.knowledge_stats.by_type);
        return {
          tooltip: { trigger: 'axis' },
          xAxis: {
            type: 'category',
            data: entries.map(([k]) => TRIGGER_TYPE_LABELS[k] || k),
            axisLabel: { fontSize: 11 },
          },
          yAxis: { type: 'value', minInterval: 1 },
          series: [
            {
              type: 'bar',
              data: entries.map(([, v]) => v),
              itemStyle: { color: '#ff6b2c', borderRadius: [4, 4, 0, 0] },
            },
          ],
        };
      })()
    : null;

  const skillRanking = data?.skill_health_ranking ?? [];
  const riskDist = data?.risk_distribution;
  const kStats = data?.knowledge_stats;
  const qStats = data?.quick_stats;

  const skillColumns: ZTableColumn<SkillHealthRow>[] = [
    { key: 'store_name', title: '门店', render: (r) => r.store_name },
    {
      key: 'coverage_pct',
      title: '技能覆盖率',
      render: (r) => (
        <div className={styles.coverageBar}>
          <div
            className={styles.coverageFill}
            style={{ width: `${r.coverage_pct}%` }}
          />
          <span className={styles.coverageText}>{r.coverage_pct}%</span>
        </div>
      ),
    },
    {
      key: 'achieved_skills',
      title: '已达标',
      render: (r) => `${r.achieved_skills}/${r.total_skills}`,
    },
    {
      key: 'status',
      title: '状态',
      render: (r) => (
        <ZBadge
          type={r.coverage_pct >= 80 ? 'success' : r.coverage_pct >= 50 ? 'warning' : 'critical'}
          text={r.coverage_pct >= 80 ? '良好' : r.coverage_pct >= 50 ? '待提升' : '需关注'}
        />
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2 className={styles.title}>人力智能大盘</h2>
        <ZButton variant="ghost" size="sm" onClick={load}>刷新</ZButton>
      </div>

      {loading ? (
        <div className={styles.body}><ZSkeleton rows={6} /></div>
      ) : (
        <div className={styles.body}>
          {/* 快速统计 */}
          <div className={styles.kpiRow}>
            <ZCard>
              <ZKpi
                value={qStats?.total_employees ?? '-'}
                label="总员工数"
                unit="人"
              />
            </ZCard>
            <ZCard>
              <ZKpi
                value={qStats ? `¥${qStats.monthly_payroll_yuan.toFixed(2)}` : '-'}
                label="本月薪资总额"
              />
            </ZCard>
            <ZCard>
              <ZKpi
                value={qStats ? `${qStats.attendance_rate_pct}%` : '-'}
                label="本月出勤率"
              />
            </ZCard>
            <ZCard>
              <ZKpi
                value={qStats?.pending_approvals ?? '-'}
                label="待审批数"
                unit="条"
              />
            </ZCard>
          </div>

          {/* 风险 KPI 行 */}
          <div className={styles.kpiRow}>
            <ZCard>
              <ZKpi
                value={riskDist?.high ?? '-'}
                label="高风险员工"
                unit="人"
              />
            </ZCard>
            <ZCard>
              <ZKpi
                value={riskDist?.total ?? '-'}
                label="扫描员工总数"
                unit="人"
              />
            </ZCard>
            <ZCard>
              <ZKpi
                value={kStats?.total_30d ?? '-'}
                label="知识采集（近30天）"
                unit="条"
              />
            </ZCard>
            <ZCard>
              <ZKpi
                value={skillRanking.length > 0
                  ? `${Math.round(skillRanking.reduce((s, r) => s + r.coverage_pct, 0) / skillRanking.length)}%`
                  : '-'}
                label="平均技能覆盖率"
              />
            </ZCard>
          </div>

          {/* 主内容两列网格 */}
          <div className={styles.mainGrid}>
            {/* 留任风险分布饼图 */}
            <ZCard
              title="留任风险分布"
              extra={
                riskDist && riskDist.high > 0
                  ? <ZBadge type="critical" text={`${riskDist.high}人高风险`} />
                  : <ZBadge type="success" text="无高风险" />
              }
            >
              {riskPieOption ? (
                <ReactECharts option={riskPieOption} style={{ height: 220 }} />
              ) : (
                <ZEmpty title="暂无数据" description="留任风险数据加载失败" />
              )}
            </ZCard>

            {/* 知识采集分布柱图 */}
            <ZCard
              title="知识采集动态（近30天）"
              extra={kStats ? <ZBadge type="info" text={`共${kStats.total_30d}条`} /> : undefined}
            >
              {knowledgeBarOption ? (
                <ReactECharts option={knowledgeBarOption} style={{ height: 220 }} />
              ) : (
                <ZEmpty title="暂无采集记录" description="近30天无知识采集数据" />
              )}
            </ZCard>
          </div>

          {/* 门店技能健康度排名 */}
          <ZCard
            title="门店技能健康度排名"
            extra={<ZBadge type="info" text="按覆盖率升序" />}
          >
            {skillRanking.length === 0 ? (
              <ZEmpty title="暂无数据" description="技能健康度数据加载失败" />
            ) : (
              <ZTable data={skillRanking} columns={skillColumns} rowKey="store_id" />
            )}
          </ZCard>
        </div>
      )}
    </div>
  );
}
