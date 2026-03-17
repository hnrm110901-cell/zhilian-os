import React, { useState, useEffect, useCallback } from 'react';
import styles from './JobStandardLibrary.module.css';
import {
  ZCard,
  ZBadge,
  ZButton,
  ZEmpty,
  ZSkeleton,
  ZDrawer,
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

const LEVEL_ORDER: JobLevel[] = ['hq', 'region', 'store', 'kitchen', 'support'];

const LEVEL_SECTION_TITLE: Record<JobLevel, string> = {
  hq: '总部层',
  region: '区域层',
  store: '门店层',
  kitchen: '后厨层',
  support: '支持部门',
};

const SOP_TYPE_LABEL: Record<string, string> = {
  pre_shift: '开市前',
  during_service: '营业中',
  peak_hour: '高峰期',
  post_shift: '收市后',
  handover: '交接班',
  emergency: '紧急处理',
};

// --- 子组件 ---

interface JobCardProps {
  job: JobStandard;
  onView: (job: JobStandard) => void;
}

function JobCard({ job, onView }: JobCardProps) {
  return (
    <div className={styles.jobCard} onClick={() => onView(job)}>
      <div className={styles.jobCardName}>{job.job_name}</div>
      <div className={styles.jobCardBadges}>
        <ZBadge type={LEVEL_BADGE_TYPE[job.job_level]} text={LEVEL_LABEL[job.job_level]} />
        <ZBadge type={CATEGORY_BADGE_TYPE[job.job_category]} text={CATEGORY_LABEL[job.job_category]} />
      </div>
      <div className={styles.jobCardMeta}>
        <span className={styles.jobCardMetaItem}>
          经验要求：{job.experience_years_min > 0 ? `${job.experience_years_min}年+` : '不限'}
        </span>
        <span className={styles.jobCardMetaItem}>
          核心KPI：{job.kpi_targets.length}项
        </span>
      </div>
      <ZButton variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); onView(job); }}>
        查看详情
      </ZButton>
    </div>
  );
}

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

interface DrawerContentProps {
  job: JobStandard;
  detail: JobStandard | null;
  loadingDetail: boolean;
}

function DrawerContent({ job, detail, loadingDetail }: DrawerContentProps) {
  const shown = detail ?? job;

  const kpiColumns: ZTableColumn<{ name: string; description: string; unit: string }>[] = [
    { key: 'name', dataIndex: 'name', title: 'KPI名称', width: '30%' },
    { key: 'description', dataIndex: 'description', title: '说明' },
    { key: 'unit', dataIndex: 'unit', title: '单位', width: 80, align: 'center' },
  ];

  const taskTabItems = [
    {
      key: 'daily',
      label: '每日',
      children: (
        <ul className={styles.taskList}>
          {shown.daily_tasks.map((t, i) => <li key={i}>{t}</li>)}
        </ul>
      ),
    },
    {
      key: 'weekly',
      label: '每周',
      children: (
        <ul className={styles.taskList}>
          {shown.weekly_tasks.map((t, i) => <li key={i}>{t}</li>)}
        </ul>
      ),
    },
    {
      key: 'monthly',
      label: '每月',
      children: (
        <ul className={styles.taskList}>
          {shown.monthly_tasks.map((t, i) => <li key={i}>{t}</li>)}
        </ul>
      ),
    },
  ];

  return (
    <div className={styles.drawerContent}>
      {/* 顶部 Badge 组合 */}
      <div className={styles.drawerBadges}>
        <ZBadge type={LEVEL_BADGE_TYPE[shown.job_level]} text={LEVEL_LABEL[shown.job_level]} />
        <ZBadge type={CATEGORY_BADGE_TYPE[shown.job_category]} text={CATEGORY_LABEL[shown.job_category]} />
        <span className={styles.drawerJobCode}>{shown.job_code}</span>
      </div>

      {/* 岗位目标 */}
      <div className={styles.objectiveBox}>
        <div className={styles.sectionLabel}>岗位目标</div>
        <p className={styles.objectiveText}>{shown.job_objective}</p>
      </div>

      {/* 汇报关系 */}
      <div className={styles.reportRow}>
        <div className={styles.reportItem}>
          <span className={styles.reportLabel}>汇报上级</span>
          <span className={styles.reportValue}>{shown.report_to_role}</span>
        </div>
        <div className={styles.reportItem}>
          <span className={styles.reportLabel}>管理下属</span>
          <span className={styles.reportValue}>{shown.manages_roles || '无'}</span>
        </div>
      </div>

      {/* 核心职责 */}
      <div className={styles.section}>
        <div className={styles.sectionLabel}>核心职责</div>
        <ul className={styles.checkList}>
          {shown.responsibilities.map((r, i) => (
            <li key={i}><span className={styles.checkMark}>✓</span>{r}</li>
          ))}
        </ul>
      </div>

      {/* 重点工作 */}
      <div className={styles.section}>
        <div className={styles.sectionLabel}>重点工作</div>
        <ZTabs items={taskTabItems} defaultKey="daily" />
      </div>

      {/* 核心KPI */}
      <div className={styles.section}>
        <div className={styles.sectionLabel}>核心KPI（{shown.kpi_targets.length}项）</div>
        <ZTable
          columns={kpiColumns}
          dataSource={shown.kpi_targets}
          rowKey="name"
          size="sm"
        />
      </div>

      {/* SOP */}
      {loadingDetail && <ZSkeleton lines={3} rows={2} />}
      {!loadingDetail && shown.sops && shown.sops.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionLabel}>标准操作规程（SOP）</div>
          <SOPCollapse sops={shown.sops} />
        </div>
      )}
      {!loadingDetail && (!shown.sops || shown.sops.length === 0) && detail && (
        <div className={styles.section}>
          <div className={styles.sectionLabel}>标准操作规程（SOP）</div>
          <ZEmpty title="该岗位暂无SOP" />
        </div>
      )}

      {/* 任职要求 */}
      <div className={styles.section}>
        <div className={styles.sectionLabel}>任职要求</div>
        <div className={styles.requireRow}>
          <span className={styles.requireLabel}>工作经验</span>
          <span>{shown.experience_years_min > 0 ? `${shown.experience_years_min}年以上` : '不限'}</span>
        </div>
        <div className={styles.requireRow}>
          <span className={styles.requireLabel}>学历要求</span>
          <span>{shown.education_requirement}</span>
        </div>
        <div className={styles.requireRow}>
          <span className={styles.requireLabel}>技能要求</span>
          <span>{shown.skill_requirements.join('、')}</span>
        </div>
      </div>

      {/* 常见问题 */}
      {shown.common_issues.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionLabel}>常见问题</div>
          <div className={styles.warningBox}>
            {shown.common_issues.map((issue, i) => (
              <div key={i} className={styles.warningItem}>
                <span className={styles.warningIcon}>⚠</span>{issue}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// --- 主页面 ---

export default function JobStandardLibrary() {
  const [jobs, setJobs] = useState<JobStandard[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [filterLevel, setFilterLevel] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [selectedJob, setSelectedJob] = useState<JobStandard | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerDetail, setDrawerDetail] = useState<JobStandard | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    try {
      const params: { level?: string; category?: string } = {};
      if (filterLevel) params.level = filterLevel;
      if (filterCategory) params.category = filterCategory;
      const list = await jobStandardService.listStandards(params);
      setJobs(list);
    } finally {
      setLoading(false);
    }
  }, [filterLevel, filterCategory]);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  const handleView = async (job: JobStandard) => {
    setSelectedJob(job);
    setDrawerOpen(true);
    setDrawerDetail(null);
    setLoadingDetail(true);
    try {
      const detail = await jobStandardService.getStandardDetail(job.job_code);
      setDrawerDetail(detail);
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleCloseDrawer = () => {
    setDrawerOpen(false);
    setSelectedJob(null);
    setDrawerDetail(null);
  };

  // 搜索过滤
  const displayedJobs = searchKeyword
    ? jobs.filter(
        j =>
          j.job_name.includes(searchKeyword) ||
          j.job_code.toLowerCase().includes(searchKeyword.toLowerCase()) ||
          j.job_objective.includes(searchKeyword),
      )
    : jobs;

  // 按层级分组
  const grouped: Partial<Record<JobLevel, JobStandard[]>> = {};
  for (const job of displayedJobs) {
    if (!grouped[job.job_level]) grouped[job.job_level] = [];
    grouped[job.job_level]!.push(job);
  }
  // 组内按sort_order排序
  for (const level of LEVEL_ORDER) {
    if (grouped[level]) {
      grouped[level]!.sort((a, b) => a.sort_order - b.sort_order);
    }
  }

  const totalCount = displayedJobs.length;

  return (
    <div className={styles.page}>
      {/* 顶部标题栏 */}
      <div className={styles.pageHeader}>
        <div className={styles.pageTitle}>
          <h1>连锁餐饮岗位标准库</h1>
          <span className={styles.pageTitleSub}>共 {totalCount} 个岗位</span>
        </div>
        <div className={styles.pageFilters}>
          <input
            className={styles.searchInput}
            placeholder="搜索岗位名称/关键词"
            value={searchKeyword}
            onChange={e => setSearchKeyword(e.target.value)}
          />
          <select
            className={styles.filterSelect}
            value={filterLevel}
            onChange={e => setFilterLevel(e.target.value)}
          >
            <option value="">全部层级</option>
            {LEVEL_ORDER.map(lv => (
              <option key={lv} value={lv}>{LEVEL_LABEL[lv]}</option>
            ))}
          </select>
          <select
            className={styles.filterSelect}
            value={filterCategory}
            onChange={e => setFilterCategory(e.target.value)}
          >
            <option value="">全部类别</option>
            <option value="management">管理</option>
            <option value="front_of_house">前厅</option>
            <option value="back_of_house">后厨</option>
            <option value="support_dept">支持</option>
          </select>
        </div>
      </div>

      {/* 内容区 */}
      <div className={styles.pageBody}>
        {loading ? (
          <ZSkeleton block rows={3} />
        ) : totalCount === 0 ? (
          <ZEmpty title="未找到匹配岗位" description="请尝试调整搜索条件" />
        ) : (
          LEVEL_ORDER.map(level => {
            const levelJobs = grouped[level];
            if (!levelJobs || levelJobs.length === 0) return null;
            return (
              <div key={level} className={styles.levelSection}>
                <div className={styles.levelSectionTitle}>
                  <ZBadge type={LEVEL_BADGE_TYPE[level]} text={LEVEL_LABEL[level]} />
                  <span className={styles.levelSectionName}>{LEVEL_SECTION_TITLE[level]}</span>
                  <span className={styles.levelSectionCount}>{levelJobs.length} 个岗位</span>
                </div>
                <div className={styles.jobGrid}>
                  {levelJobs.map(job => (
                    <JobCard key={job.id} job={job} onView={handleView} />
                  ))}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* 侧边抽屉 */}
      <ZDrawer
        open={drawerOpen}
        onClose={handleCloseDrawer}
        title={selectedJob ? selectedJob.job_name : ''}
        width={680}
      >
        {selectedJob && (
          <DrawerContent
            job={selectedJob}
            detail={drawerDetail}
            loadingDetail={loadingDetail}
          />
        )}
      </ZDrawer>
    </div>
  );
}
