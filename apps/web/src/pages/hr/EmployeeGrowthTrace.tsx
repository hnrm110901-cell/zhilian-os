import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import styles from './EmployeeGrowthTrace.module.css';
import {
  ZCard,
  ZBadge,
  ZButton,
  ZEmpty,
  ZSkeleton,
  ZModal,
} from '../../design-system/components';
import type { GrowthTrace, GrowthTraceType, KPIGapAnalysis, KPIGapItem } from '../../types/jobStandard';
import { jobStandardService } from '../../services/jobStandardService';
import { useAuth } from '../../contexts/AuthContext';

// --- 辅助映射 ---

const TRACE_TYPE_LABEL: Record<GrowthTraceType, string> = {
  hire: '入职',
  transfer: '调店',
  promote: '晋升',
  train_complete: '完成培训',
  assess: '绩效考核',
  reward: '奖励',
  penalty: '处罚',
  resign: '离职',
  job_change: '岗位变更',
};

const TRACE_TYPE_COLOR: Record<GrowthTraceType, string> = {
  hire: '#3b82f6',
  transfer: '#6366f1',
  promote: '#f59e0b',
  train_complete: '#3b82f6',
  assess: '#6b7280',
  reward: '#22c55e',
  penalty: '#ef4444',
  resign: '#9ca3af',
  job_change: '#8b5cf6',
};

const TRACE_TYPE_ICON: Record<GrowthTraceType, string> = {
  hire: '🚀',
  transfer: '🏪',
  promote: '⭐',
  train_complete: '📚',
  assess: '📊',
  reward: '🏆',
  penalty: '⚠️',
  resign: '👋',
  job_change: '🔄',
};

const GAP_LEVEL_ICON: Record<string, string> = {
  good: '✅',
  warning: '⚠️',
  danger: '🔴',
  unknown: '—',
};

const GAP_LEVEL_TEXT: Record<string, string> = {
  good: '达标',
  warning: '偏低/偏高',
  danger: '超标',
  unknown: '暂无数据',
};

const GAP_LEVEL_CLASS: Record<string, string> = {
  good: 'good',
  warning: 'warning',
  danger: 'danger',
  unknown: 'unknown',
};

const TRACE_TYPES: { value: GrowthTraceType; label: string }[] = [
  { value: 'hire', label: '入职' },
  { value: 'transfer', label: '调店' },
  { value: 'promote', label: '晋升' },
  { value: 'train_complete', label: '完成培训' },
  { value: 'assess', label: '绩效考核' },
  { value: 'reward', label: '奖励' },
  { value: 'penalty', label: '处罚' },
  { value: 'resign', label: '离职' },
  { value: 'job_change', label: '岗位变更' },
];

// --- 子组件 ---

interface TimelineNodeProps {
  trace: GrowthTrace;
  isLast: boolean;
}

function TimelineNode({ trace, isLast }: TimelineNodeProps) {
  const color = TRACE_TYPE_COLOR[trace.trace_type];
  const icon = TRACE_TYPE_ICON[trace.trace_type];
  const isMilestone = trace.is_milestone;

  return (
    <div className={styles.timelineNode}>
      {/* 竖线 */}
      {!isLast && <div className={styles.timelineConnector} />}

      {/* 节点图标 */}
      <div
        className={`${styles.timelineDot} ${isMilestone ? styles.timelineDotMilestone : ''}`}
        style={{ borderColor: color, backgroundColor: isMilestone ? color : '#fff' }}
      >
        <span className={styles.timelineDotIcon} style={{ color: isMilestone ? '#fff' : color }}>
          {isMilestone ? '★' : icon}
        </span>
      </div>

      {/* 内容 */}
      <div className={`${styles.timelineContent} ${isMilestone ? styles.timelineContentMilestone : ''}`}>
        <div className={styles.timelineContentHeader}>
          <span
            className={`${styles.timelineTitle} ${isMilestone ? styles.timelineTitleMilestone : ''}`}
          >
            {isMilestone && <span className={styles.milestoneStarLabel}>里程碑 · </span>}
            {trace.event_title}
          </span>
          <span className={styles.timelineDate}>{trace.trace_date}</span>
        </div>

        {/* 岗位变更标记 */}
        {(trace.from_job_name || trace.to_job_name) && (
          <div className={styles.jobChangeRow}>
            {trace.from_job_name && (
              <span className={styles.jobChangeFrom}>{trace.from_job_name}</span>
            )}
            {trace.from_job_name && trace.to_job_name && (
              <span className={styles.jobChangeArrow}>→</span>
            )}
            {trace.to_job_name && (
              <span className={styles.jobChangeTo}>{trace.to_job_name}</span>
            )}
          </div>
        )}

        {/* 详情 */}
        {trace.event_detail && (
          <p className={styles.timelineDetail}>{trace.event_detail}</p>
        )}

        {/* 考核分数 */}
        {trace.assessment_score !== undefined && (
          <div className={styles.scoreTag}>
            考核得分：<strong>{trace.assessment_score}分</strong>
          </div>
        )}

        {/* 类型 Badge */}
        <div className={styles.timelineTypeBadge}>
          <ZBadge
            type="default"
            text={TRACE_TYPE_LABEL[trace.trace_type]}
          />
        </div>
      </div>
    </div>
  );
}

interface KPIGapCardProps {
  analysis: KPIGapAnalysis;
}

function KPIGapCard({ analysis }: KPIGapCardProps) {
  return (
    <div className={styles.kpiGapCard}>
      <div className={styles.kpiGapHeader}>
        <span className={styles.kpiGapTitle}>KPI差距分析</span>
        <ZBadge type="info" text={analysis.job_name} />
      </div>

      <div className={styles.kpiList}>
        {analysis.kpi_targets.map((item: KPIGapItem, idx: number) => (
          <div key={idx} className={`${styles.kpiRow} ${styles[GAP_LEVEL_CLASS[item.gap_level]]}`}>
            <span className={styles.kpiName}>{item.name}</span>
            <div className={styles.kpiStatus}>
              <span className={styles.kpiStatusIcon}>{GAP_LEVEL_ICON[item.gap_level]}</span>
              <span className={`${styles.kpiStatusText} ${styles[`kpiStatus_${item.gap_level}`]}`}>
                {GAP_LEVEL_TEXT[item.gap_level]}
              </span>
            </div>
          </div>
        ))}
      </div>

      {analysis.ai_suggestion && (
        <div className={styles.aiSuggestion}>
          <div className={styles.aiSuggestionLabel}>
            <span className={styles.aiSuggestionIcon}>💡</span>AI建议
          </div>
          <p className={styles.aiSuggestionText}>{analysis.ai_suggestion}</p>
        </div>
      )}
    </div>
  );
}

// --- 添加记录 Modal ---

interface AddTraceModalProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (payload: {
    trace_type: GrowthTraceType;
    event_title: string;
    event_detail: string;
    is_milestone: boolean;
  }) => Promise<void>;
  loading: boolean;
}

function AddTraceModal({ open, onClose, onSubmit, loading }: AddTraceModalProps) {
  const [traceType, setTraceType] = useState<GrowthTraceType>('assess');
  const [eventTitle, setEventTitle] = useState('');
  const [eventDetail, setEventDetail] = useState('');
  const [isMilestone, setIsMilestone] = useState(false);
  const [submitErr, setSubmitErr] = useState('');

  const handleSubmit = async () => {
    if (!eventTitle.trim()) {
      setSubmitErr('请填写事件标题');
      return;
    }
    setSubmitErr('');
    await onSubmit({ trace_type: traceType, event_title: eventTitle, event_detail: eventDetail, is_milestone: isMilestone });
    setEventTitle('');
    setEventDetail('');
    setIsMilestone(false);
    setTraceType('assess');
  };

  return (
    <ZModal
      open={open}
      title="添加成长记录"
      onClose={onClose}
      footer={
        <div className={styles.modalFooter}>
          <ZButton variant="ghost" onClick={onClose} disabled={loading}>取消</ZButton>
          <ZButton variant="primary" onClick={handleSubmit} loading={loading}>保存</ZButton>
        </div>
      }
      width={480}
    >
      <div className={styles.modalForm}>
        <div className={styles.formRow}>
          <label className={styles.formLabel}>事件类型</label>
          <select
            className={styles.formSelect}
            value={traceType}
            onChange={e => setTraceType(e.target.value as GrowthTraceType)}
          >
            {TRACE_TYPES.map(t => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>

        <div className={styles.formRow}>
          <label className={styles.formLabel}>事件标题 <span className={styles.required}>*</span></label>
          <input
            className={styles.formInput}
            placeholder="如：完成2025年Q2绩效考核"
            value={eventTitle}
            onChange={e => setEventTitle(e.target.value)}
          />
          {submitErr && <p className={styles.formError}>{submitErr}</p>}
        </div>

        <div className={styles.formRow}>
          <label className={styles.formLabel}>详细说明</label>
          <textarea
            className={styles.formTextarea}
            placeholder="可选，描述事件详情"
            value={eventDetail}
            onChange={e => setEventDetail(e.target.value)}
            rows={3}
          />
        </div>

        <div className={styles.formRowInline}>
          <label className={styles.formLabel}>是否里程碑</label>
          <label className={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={isMilestone}
              onChange={e => setIsMilestone(e.target.checked)}
            />
            <span>标记为里程碑事件（金色高亮显示）</span>
          </label>
        </div>
      </div>
    </ZModal>
  );
}

// --- 主页面 ---

export default function EmployeeGrowthTrace() {
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const employeeId = searchParams.get('employeeId') ?? 'EMP001';
  const storeId = user?.store_id ?? 'S001';

  const [timeline, setTimeline] = useState<GrowthTrace[]>([]);
  const [kpiGap, setKpiGap] = useState<KPIGapAnalysis | null>(null);
  const [loadingTimeline, setLoadingTimeline] = useState(true);
  const [loadingKpi, setLoadingKpi] = useState(true);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [addLoading, setAddLoading] = useState(false);

  const employeeName = timeline.length > 0 ? timeline[0].employee_name : employeeId;
  const currentJobName = kpiGap?.job_name ?? '—';

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoadingTimeline(true);
      setLoadingKpi(true);
      try {
        const [tl, kpi] = await Promise.all([
          jobStandardService.getGrowthTimeline(employeeId),
          jobStandardService.getKPIGap(employeeId, storeId),
        ]);
        if (!cancelled) {
          setTimeline(tl);
          setKpiGap(kpi);
        }
      } finally {
        if (!cancelled) {
          setLoadingTimeline(false);
          setLoadingKpi(false);
        }
      }
    };

    load();
    return () => { cancelled = true; };
  }, [employeeId, storeId]);

  const handleAddTrace = async (payload: {
    trace_type: GrowthTraceType;
    event_title: string;
    event_detail: string;
    is_milestone: boolean;
  }) => {
    setAddLoading(true);
    try {
      const newTrace = await jobStandardService.addGrowthTrace({
        employee_id: employeeId,
        employee_name: employeeName,
        store_id: storeId,
        trace_type: payload.trace_type,
        event_title: payload.event_title,
        event_detail: payload.event_detail,
        is_milestone: payload.is_milestone,
      });
      setTimeline(prev => [...prev, newTrace]);
      setAddModalOpen(false);
    } finally {
      setAddLoading(false);
    }
  };

  const handleBack = () => {
    window.history.back();
  };

  return (
    <div className={styles.page}>
      {/* 顶部栏 */}
      <div className={styles.pageHeader}>
        <div className={styles.headerLeft}>
          <ZButton variant="ghost" size="sm" onClick={handleBack}>← 返回</ZButton>
          <div className={styles.headerTitle}>
            <span className={styles.headerTitleMain}>员工成长档案</span>
            {!loadingTimeline && (
              <span className={styles.headerTitleSub}>— {employeeName}</span>
            )}
          </div>
        </div>
        <div className={styles.headerRight}>
          <span className={styles.currentJobLabel}>当前岗位：</span>
          <ZBadge type="accent" text={currentJobName} />
        </div>
      </div>

      {/* 主内容 */}
      <div className={styles.pageBody}>
        {/* 左列：KPI差距分析 */}
        <div className={styles.leftCol}>
          {loadingKpi ? (
            <ZSkeleton lines={5} />
          ) : kpiGap ? (
            <KPIGapCard analysis={kpiGap} />
          ) : (
            <ZEmpty title="暂无KPI数据" />
          )}
          <div className={styles.leftColAction}>
            <ZButton
              variant="primary"
              size="md"
              onClick={() => setAddModalOpen(true)}
            >
              + 添加记录
            </ZButton>
          </div>
        </div>

        {/* 右列：成长时间轴 */}
        <div className={styles.rightCol}>
          <ZCard title="成长时间轴" extra={`共 ${timeline.length} 条记录`}>
            {loadingTimeline ? (
              <ZSkeleton avatar rows={4} />
            ) : timeline.length === 0 ? (
              <ZEmpty title="暂无成长记录" />
            ) : (
              <div className={styles.timeline}>
                {timeline.map((trace, idx) => (
                  <TimelineNode
                    key={trace.id}
                    trace={trace}
                    isLast={idx === timeline.length - 1}
                  />
                ))}
              </div>
            )}

            {!loadingTimeline && (
              <div className={styles.timelineAddBtn}>
                <ZButton
                  variant="ghost"
                  size="sm"
                  onClick={() => setAddModalOpen(true)}
                >
                  + 添加成长记录
                </ZButton>
              </div>
            )}
          </ZCard>
        </div>
      </div>

      {/* 添加记录 Modal */}
      <AddTraceModal
        open={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        onSubmit={handleAddTrace}
        loading={addLoading}
      />
    </div>
  );
}
