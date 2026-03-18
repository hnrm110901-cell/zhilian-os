import React, { useState, useCallback, useEffect } from 'react';
import { apiClient } from '../../services/api';
import styles from './HRPages.module.css';

interface JobItem {
  id: string;
  title: string;
  position: string;
  headcount: number;
  hired_count: number;
  candidate_count: number;
  status: string;
  salary_range_yuan: string;
  urgent: boolean;
  created_at: string;
}

interface Funnel {
  new: number;
  screening: number;
  interview: number;
  offer: number;
  hired: number;
  rejected: number;
}

const RecruitmentPage: React.FC = () => {
  const [storeId] = useState(localStorage.getItem('store_id') || '');
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [activeJobs, setActiveJobs] = useState(0);
  const [conversionRate, setConversionRate] = useState(0);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [jobsRes, funnelRes] = await Promise.all([
        apiClient.get(`/api/v1/hr/jobs?store_id=${storeId}`),
        apiClient.get(`/api/v1/hr/recruitment/funnel?store_id=${storeId}`),
      ]);
      setJobs(jobsRes.items || []);
      setFunnel(funnelRes.funnel || null);
      setActiveJobs(funnelRes.active_jobs || 0);
      setConversionRate(funnelRes.conversion_rate || 0);
    } catch { /* silent */ }
    setLoading(false);
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  const funnelStages = funnel ? [
    { key: 'new', label: '新候选人', count: funnel.new, color: '#2D9CDB' },
    { key: 'screening', label: '简历筛选', count: funnel.screening, color: '#9B51E0' },
    { key: 'interview', label: '面试中', count: funnel.interview, color: '#F2994A' },
    { key: 'offer', label: 'Offer', count: funnel.offer, color: '#0AAF9A' },
    { key: 'hired', label: '已入职', count: funnel.hired, color: '#27AE60' },
  ] : [];

  const maxCount = Math.max(...funnelStages.map(s => s.count), 1);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>招聘管理</h1>
          <p className={styles.pageDesc}>职位发布、候选人管理与招聘漏斗</p>
        </div>
      </div>

      {/* 招聘漏斗 */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.sectionTitle}>招聘漏斗</span>
          <span className={styles.sectionTag}>{activeJobs} 个活跃职位 · 转化率 {conversionRate}%</span>
        </div>
        <div className={styles.funnelWrap}>
          {funnelStages.map(stage => (
            <div key={stage.key} className={styles.funnelRow}>
              <div className={styles.funnelLabel}>{stage.label}</div>
              <div className={styles.funnelBarBg}>
                <div
                  className={styles.funnelBar}
                  style={{
                    width: `${(stage.count / maxCount) * 100}%`,
                    backgroundColor: stage.color,
                  }}
                />
              </div>
              <div className={styles.funnelCount}>{stage.count}</div>
            </div>
          ))}
        </div>
      </div>

      {/* 职位列表 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>职位列表</div>
        {loading ? (
          <div className={styles.loadingWrap}>加载中...</div>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>职位</th>
                  <th>岗位</th>
                  <th>薪资范围</th>
                  <th>需求/已招</th>
                  <th>候选人</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map(job => (
                  <tr key={job.id}>
                    <td className={styles.cellName}>
                      {job.title}
                      {job.urgent && <span className={styles.urgentTag}>急</span>}
                    </td>
                    <td>{job.position}</td>
                    <td>¥{job.salary_range_yuan}</td>
                    <td>{job.hired_count}/{job.headcount}</td>
                    <td>{job.candidate_count}</td>
                    <td>
                      <span className={styles.badge} style={{
                        color: job.status === 'open' ? '#27AE60' : 'rgba(255,255,255,0.38)',
                        borderColor: job.status === 'open' ? '#27AE60' : 'rgba(255,255,255,0.12)',
                      }}>
                        {job.status === 'open' ? '招聘中' : '已关闭'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default RecruitmentPage;
