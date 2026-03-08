import React, { useCallback, useEffect, useMemo, useState } from 'react';
import dayjs from 'dayjs';
import { ClockCircleOutlined } from '@ant-design/icons';
import { ZBadge, ZButton, ZCard, ZEmpty, ZModal, ZSkeleton } from '../../design-system/components';
import { startTask, submitTask } from '../../services/mobile.mutation.service';
import { queryTaskSummary } from '../../services/mobile.query.service';
import type { MobileTask, TaskSummaryResponse } from '../../services/mobile.types';
import { showError, showSuccess, handleApiError } from '../../utils/message';
import styles from './Tasks.module.css';

const PRIORITY_MAP: Record<string, { text: string; type: 'critical' | 'warning' | 'info' | 'success' | 'default' }> = {
  p0_urgent: { text: 'P0 紧急', type: 'critical' },
  p1_high: { text: 'P1 高', type: 'warning' },
  p2_medium: { text: 'P2 中', type: 'info' },
  p3_low: { text: 'P3 低', type: 'default' },
};

const STATUS_TEXT: Record<string, string> = {
  pending: '待执行',
  in_progress: '进行中',
  submitted: '待审核',
  approved: '已通过',
  rejected: '已驳回',
  expired: '已逾期',
  completed: '已完成',
};

type TaskFilter = 'all' | 'todo' | 'in_progress' | 'risk';

export default function SmTasks() {
  const [data, setData] = useState<TaskSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<TaskFilter>('todo');
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [selectedTask, setSelectedTask] = useState<MobileTask | null>(null);
  const [evidenceNote, setEvidenceNote] = useState('');
  const [evidenceFileName, setEvidenceFileName] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await queryTaskSummary();
      setData(resp);
    } catch (err) {
      handleApiError(err, '加载任务失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const tasks = useMemo(() => {
    const all = data?.tasks || [];
    if (filter === 'all') return all;
    if (filter === 'todo') return all.filter((t) => t.task_status === 'pending' || t.task_status === 'rejected');
    if (filter === 'in_progress') return all.filter((t) => t.task_status === 'in_progress');
    return all.filter((t) => t.task_status === 'expired' || t.priority === 'p0_urgent' || t.priority === 'p1_high');
  }, [data?.tasks, filter]);

  const doStart = async (item: MobileTask) => {
    setActionLoadingId(item.task_id);
    const result = await startTask(item.task_id);
    setActionLoadingId(null);
    if (!result.ok) return showError(result.message);
    showSuccess(result.message);
    load();
  };

  const doSubmit = async (item: MobileTask) => {
    if (item.need_evidence && !evidenceNote.trim() && !evidenceFileName) {
      return showError('该任务要求证据，请填写说明或上传图片');
    }
    setActionLoadingId(item.task_id);
    const result = await submitTask(item.task_id);
    setActionLoadingId(null);
    if (!result.ok) return showError(result.message);
    showSuccess(result.message);
    setSelectedTask(null);
    setEvidenceNote('');
    setEvidenceFileName('');
    load();
  };

  const openDetail = (item: MobileTask) => {
    setSelectedTask(item);
    setEvidenceNote('');
    setEvidenceFileName('');
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>任务页</div>
        <div className={styles.summary}>
          待办 {data?.pending_count ?? 0} · 逾期 {data?.expired_count ?? 0}
        </div>
        <div className={styles.filters}>
          <button className={`${styles.filterBtn} ${filter === 'todo' ? styles.active : ''}`} onClick={() => setFilter('todo')}>待办</button>
          <button className={`${styles.filterBtn} ${filter === 'in_progress' ? styles.active : ''}`} onClick={() => setFilter('in_progress')}>进行中</button>
          <button className={`${styles.filterBtn} ${filter === 'risk' ? styles.active : ''}`} onClick={() => setFilter('risk')}>风险</button>
          <button className={`${styles.filterBtn} ${filter === 'all' ? styles.active : ''}`} onClick={() => setFilter('all')}>全部</button>
        </div>
      </div>

      <div className={styles.body}>
        {loading ? (
          <ZSkeleton rows={4} />
        ) : tasks.length === 0 ? (
          <ZEmpty title="暂无任务" description="当前筛选下没有可执行任务" />
        ) : (
          tasks.map((item) => (
            <ZCard key={item.task_id}>
              <div className={styles.rowTop}>
                <div className={styles.taskTitle}>{item.task_title}</div>
                <ZBadge type={PRIORITY_MAP[item.priority]?.type || 'default'} text={PRIORITY_MAP[item.priority]?.text || item.priority} />
              </div>
              <div className={styles.meta}><ClockCircleOutlined /> 截止：{dayjs(item.deadline_at).format('MM-DD HH:mm')}</div>
              <div className={styles.meta}>类型：{item.task_type} · 指派：{item.assignee_name}</div>
              <div className={styles.meta}>
                证据：{item.need_evidence ? '需要上传' : '可选'} · 审核：{item.need_review ? '需要' : '无需'}
              </div>
              <div className={styles.rowFooter}>
                <span className={styles.status}>{STATUS_TEXT[item.task_status] || item.task_status}</span>
                <div className={styles.actions}>
                  <ZButton size="sm" variant="ghost" onClick={() => openDetail(item)}>详情</ZButton>
                  {item.task_status === 'pending' && (
                    <ZButton size="sm" loading={actionLoadingId === item.task_id} onClick={() => doStart(item)}>开始执行</ZButton>
                  )}
                  {item.task_status === 'in_progress' && (
                    <ZButton size="sm" loading={actionLoadingId === item.task_id} onClick={() => doSubmit(item)}>提交结果</ZButton>
                  )}
                  {item.task_status === 'rejected' && (
                    <ZButton size="sm" variant="ghost" loading={actionLoadingId === item.task_id} onClick={() => doSubmit(item)}>重新提交</ZButton>
                  )}
                </div>
              </div>
            </ZCard>
          ))
        )}
      </div>

      <ZModal
        open={!!selectedTask}
        title="任务详情"
        onClose={() => setSelectedTask(null)}
        footer={
          selectedTask ? (
            <div className={styles.modalActions}>
              {selectedTask.task_status === 'pending' && (
                <ZButton size="sm" loading={actionLoadingId === selectedTask.task_id} onClick={() => doStart(selectedTask)}>开始执行</ZButton>
              )}
              {(selectedTask.task_status === 'in_progress' || selectedTask.task_status === 'rejected') && (
                <ZButton size="sm" loading={actionLoadingId === selectedTask.task_id} onClick={() => doSubmit(selectedTask)}>提交结果</ZButton>
              )}
            </div>
          ) : null
        }
      >
        {selectedTask && (
          <div className={styles.modalBody}>
            <div className={styles.detailRow}><span>任务</span><b>{selectedTask.task_title}</b></div>
            <div className={styles.detailRow}><span>状态</span><b>{STATUS_TEXT[selectedTask.task_status] || selectedTask.task_status}</b></div>
            <div className={styles.detailRow}><span>截止</span><b>{dayjs(selectedTask.deadline_at).format('MM-DD HH:mm')}</b></div>
            <div className={styles.detailRow}><span>类型</span><b>{selectedTask.task_type}</b></div>
            <div className={styles.detailRow}><span>证据要求</span><b>{selectedTask.need_evidence ? '必须' : '可选'}</b></div>
            <div className={styles.evidenceBlock}>
              <div className={styles.evidenceTitle}>证据上传占位</div>
              <textarea
                className={styles.evidenceInput}
                rows={3}
                placeholder="填写执行说明（示例：已完成开市前巡检，冷链温度正常）"
                value={evidenceNote}
                onChange={(e) => setEvidenceNote(e.target.value)}
              />
              <input
                className={styles.fileInput}
                type="file"
                accept="image/*"
                onChange={(e) => setEvidenceFileName(e.target.files?.[0]?.name || '')}
              />
              {evidenceFileName && <div className={styles.fileName}>已选择：{evidenceFileName}</div>}
            </div>
          </div>
        )}
      </ZModal>
    </div>
  );
}
