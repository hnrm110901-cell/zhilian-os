import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import styles from './JobStandardDetail.module.css';
import {
  ZBadge,
  ZButton,
  ZEmpty,
  ZSkeleton,
  ZTabs,
  ZTable,
} from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import type { JobStandard, JobLevel, JobCategory, SOPStep, JobSOP } from '../../types/jobStandard';
import { jobStandardService } from '../../services/jobStandardService';

// --- 辅助映射 ---

const LEVEL_LABEL: Record<JobLevel, string> = {
  hq: '总部',
  region: '区域',
  store: '门店',
  kitchen: '后厨',
  support: '支持',
};

const LEVEL_BADGE_TYPE: Record<JobLevel, 'info' | 'success' | 'accent' | 'error' | 'neutral'> = {
  hq: 'info',
  region: 'success',
  store: 'accent',
  kitchen: 'error',
  support: 'neutral',
};

const CATEGORY_LABEL: Record<JobCategory, string> = {
  management: '管理',
  front_of_house: '前厅',
  back_of_house: '后厨',
  support_dept: '支持',
};

const CATEGORY_BADGE_TYPE: Record<JobCategory, 'info' | 'success' | 'warning' | 'default'> = {
  management: 'info',
  front_of_house: 'success',
  back_of_house: 'warning',
  support_dept: 'default',
};

const SOP_TYPE_LABEL: Record<string, string> = {
  pre_shift: '开市前',
  during_service: '营业中',
  peak_hour: '高峰期',
  post_shift: '收市后',
  handover: '交接班',
  emergency: '紧急处理',
};

// --- SOP Collapse ---

interface SOPCollapseProps {
  sops: JobSOP[];
}

function SOPCollapse({ sops }: SOPCollapseProps) {
  const [openKeys, setOpenKeys] = useState<Set<string>>(new Set());

  const toggle = (id: string) => {
    setOpenKeys(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const stepColumns: ZTableColumn<SOPStep>[] = [
    { key: 'step_no', dataIndex: 'step_no', title: '步骤', width: 60, align: 'center' },
    { key: 'action', dataIndex: 'action', title: '动作', width: '25%' },
    { key: 'standard', dataIndex: 'standard', title: '标准', width: '40%' },
    { key: 'check_point', dataIndex: 'check_point', title: '检查点' },
  ];

  return (
    <div className={styles.sopList}>
      {sops.map(sop => (
        <div key={sop.id} className={styles.sopItem}>
          <button className={styles.sopHeader} onClick={() => toggle(sop.id)}>
            <span className={styles.sopTitle}>
              <span className={styles.sopTypeTag}>{SOP_TYPE_LABEL[sop.sop_type] ?? sop.sop_type}</span>
              {sop.sop_name}
            </span>
            <span className={styles.sopMeta}>
              {sop.duration_minutes}分钟 · {sop.steps.length}步骤
              <span className={styles.sopToggleIcon}>{openKeys.has(sop.id) ? '▲' : '▼'}</span>
            </span>
          </button>
          {openKeys.has(sop.id) && (
            <div className={styles.sopBody}>
              <ZTable<SOPStep>
                columns={stepColumns}
                dataSource={sop.steps}
                rowKey="step_no"
                size="sm"
              />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// --- 主页面 ---

export default function JobStandardDetail() {
  const { jobCode } = useParams<{ jobCode: string }>();
  const [job, setJob] = useState<JobStandard | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!jobCode) {
      setNotFound(true);
      setLoading(false);
      return;
    }
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const detail = await jobStandardService.getStandardDetail(jobCode);
        if (!cancelled) {
          if (!detail) setNotFound(true);
          else setJob(detail);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [jobCode]);

  const handleBack = () => window.history.back();

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.pageHeader}>
          <ZButton variant="ghost" size="sm" onClick={handleBack}>← 返回</ZButton>
        </div>
        <div className={styles.pageBody}>
          <ZSkeleton lines={4} rows={3} />
        </div>
      </div>
    );
  }

  if (notFound || !job) {
    return (
      <div className={styles.page}>
        <div className={styles.pageHeader}>
          <ZButton variant="ghost" size="sm" onClick={handleBack}>← 返回</ZButton>
        </div>
        <div className={styles.pageBody}>
          <ZEmpty title="岗位不存在" description={`未找到岗位代码：${jobCode}`} />
        </div>
      </div>
    );
  }

  const kpiColumns: ZTableColumn<{ name: string; description: string; unit: string }>[] = [
    { key: 'name', dataIndex: 'name', title: 'KPI名称', width: '30%' },
    { key: 'description', dataIndex: 'description', title: '说明' },
    { key: 'unit', dataIndex: 'unit', title: '单位', width: 80, align: 'center' },
  ];

  const taskTabItems = [
    {
      key: 'daily',
      label: '每日重点',
      children: (
        <ul className={styles.taskList}>
          {job.daily_tasks.map((t, i) => <li key={i}>{t}</li>)}
        </ul>
      ),
    },
    {
      key: 'weekly',
      label: '每周重点',
      children: (
        <ul className={styles.taskList}>
          {job.weekly_tasks.map((t, i) => <li key={i}>{t}</li>)}
        </ul>
      ),
    },
    {
      key: 'monthly',
      label: '每月重点',
      children: (
        <ul className={styles.taskList}>
          {job.monthly_tasks.map((t, i) => <li key={i}>{t}</li>)}
        </ul>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.pageHeader}>
        <ZButton variant="ghost" size="sm" onClick={handleBack}>← 返回</ZButton>
        <div className={styles.headerBreadcrumb}>
          <span className={styles.breadcrumbLink} onClick={handleBack}>岗位标准库</span>
          <span className={styles.breadcrumbSep}>/</span>
          <span className={styles.breadcrumbCurrent}>{job.job_name}</span>
        </div>
      </div>

      {/* Page Body */}
      <div className={styles.pageBody}>
        {/* 顶部名称区 */}
        <div className={styles.heroSection}>
          <h1 className={styles.jobName}>{job.job_name}</h1>
          <div className={styles.heroBadges}>
            <ZBadge type={LEVEL_BADGE_TYPE[job.job_level]} text={LEVEL_LABEL[job.job_level]} />
            <ZBadge type={CATEGORY_BADGE_TYPE[job.job_category]} text={CATEGORY_LABEL[job.job_category]} />
            <span className={styles.jobCode}>{job.job_code}</span>
          </div>
        </div>

        {/* 岗位目标 */}
        <div className={styles.objectiveBox}>
          <div className={styles.objectiveLabel}>岗位目标</div>
          <p className={styles.objectiveText}>{job.job_objective}</p>
        </div>

        {/* 两列布局 */}
        <div className={styles.contentGrid}>
          {/* 左列 */}
          <div className={styles.leftCol}>
            {/* 汇报关系 */}
            <div className={styles.section}>
              <div className={styles.sectionTitle}>汇报关系</div>
              <div className={styles.reportRow}>
                <span className={styles.reportLabel}>汇报上级</span>
                <span>{job.report_to_role}</span>
              </div>
              <div className={styles.reportRow}>
                <span className={styles.reportLabel}>管理下属</span>
                <span>{job.manages_roles || '无'}</span>
              </div>
            </div>

            {/* 任职要求 */}
            <div className={styles.section}>
              <div className={styles.sectionTitle}>任职要求</div>
              <div className={styles.requireItem}>
                <span className={styles.requireLabel}>工作经验</span>
                <span>{job.experience_years_min > 0 ? `${job.experience_years_min}年以上` : '不限'}</span>
              </div>
              <div className={styles.requireItem}>
                <span className={styles.requireLabel}>学历要求</span>
                <span>{job.education_requirement}</span>
              </div>
              <div className={styles.requireItem}>
                <span className={styles.requireLabel}>技能要求</span>
                <span>{job.skill_requirements.join('、')}</span>
              </div>
            </div>

            {/* 常见问题 */}
            {job.common_issues.length > 0 && (
              <div className={styles.section}>
                <div className={styles.sectionTitle}>常见问题</div>
                <div className={styles.warningBox}>
                  {job.common_issues.map((issue, i) => (
                    <div key={i} className={styles.warningItem}>
                      <span className={styles.warningIcon}>⚠</span>{issue}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* 右列 */}
          <div className={styles.rightCol}>
            {/* 核心职责 */}
            <div className={styles.section}>
              <div className={styles.sectionTitle}>核心职责</div>
              <ul className={styles.checkList}>
                {job.responsibilities.map((r, i) => (
                  <li key={i}><span className={styles.checkMark}>✓</span>{r}</li>
                ))}
              </ul>
            </div>

            {/* 重点工作 */}
            <div className={styles.section}>
              <div className={styles.sectionTitle}>重点工作</div>
              <ZTabs items={taskTabItems} defaultKey="daily" />
            </div>

            {/* 核心KPI */}
            <div className={styles.section}>
              <div className={styles.sectionTitle}>核心KPI（{job.kpi_targets.length}项）</div>
              <ZTable
                columns={kpiColumns}
                dataSource={job.kpi_targets}
                rowKey="name"
                size="sm"
              />
            </div>
          </div>
        </div>

        {/* SOP — 全宽 */}
        {job.sops && job.sops.length > 0 && (
          <div className={styles.section}>
            <div className={styles.sectionTitle}>
              标准操作规程（SOP）— {job.sops.length} 个流程
            </div>
            <SOPCollapse sops={job.sops} />
          </div>
        )}
      </div>
    </div>
  );
}
