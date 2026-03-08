import React, { useCallback, useEffect, useMemo, useState } from 'react';
import dayjs from 'dayjs';
import { ClockCircleOutlined } from '@ant-design/icons';
import { ZBadge, ZButton, ZCard, ZEmpty, ZSkeleton } from '../../design-system/components';
import { startTask, submitTask } from '../../services/mobile.mutation.service';
import { queryTaskSummary } from '../../services/mobile.query.service';
import type { MobileTask, TaskSummaryResponse } from '../../services/mobile.types';
import { showSuccess, handleApiError } from '../../utils/message';
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
    const ok = await startTask(item.task_id);
    setActionLoadingId(null);
    if (ok) {
      showSuccess('任务已开始');
      load();
    }
  };

  const doSubmit = async (item: MobileTask) => {
    setActionLoadingId(item.task_id);
    const ok = await submitTask(item.task_id);
    setActionLoadingId(null);
    if (ok) {
      showSuccess('任务已提交');
      load();
    }
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
              <div className={styles.rowFooter}>
                <span className={styles.status}>{STATUS_TEXT[item.task_status] || item.task_status}</span>
                <div className={styles.actions}>
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
    </div>
  );
}
