/**
 * SM 任务看板页（移动端）
 * 路由：/sm/banquet-tasks
 * 数据：GET /api/v1/banquet-agent/stores/{id}/tasks
 *      PATCH /api/v1/banquet-agent/stores/{id}/tasks/{task_id}/complete
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import {
  ZCard, ZBadge, ZButton, ZSkeleton, ZEmpty,
} from '../../design-system/components';
import apiClient from '../../services/api';
import { handleApiError } from '../../utils/message';
import styles from './BanquetTasks.module.css';

const STORE_ID = localStorage.getItem('store_id') || '';

const ROLE_CHIPS = [
  { value: '',         label: '全部' },
  { value: 'kitchen',  label: '厨房' },
  { value: 'service',  label: '服务' },
  { value: 'decor',    label: '布置' },
  { value: 'purchase', label: '采购' },
  { value: 'manager',  label: '店长' },
];

const TASK_STATUS_BADGE: Record<string, { text: string; type: 'success' | 'info' | 'warning' | 'default' }> = {
  pending:     { text: '待处理', type: 'warning' },
  in_progress: { text: '进行中', type: 'info'    },
  done:        { text: '已完成', type: 'success' },
  verified:    { text: '已核验', type: 'success' },
  overdue:     { text: '已逾期', type: 'default' },
  closed:      { text: '已关闭', type: 'default' },
};

const BANQUET_TYPE_LABELS: Record<string, string> = {
  wedding:    '婚宴',
  birthday:   '寿宴',
  business:   '商务宴',
  full_moon:  '满月酒',
  graduation: '升学宴',
  other:      '其他',
};

const WEEK_NAMES = ['日', '一', '二', '三', '四', '五', '六'];

interface TaskItem {
  task_id:      string;
  task_name:    string;
  owner_role:   string;
  order_id:     string;
  banquet_type: string | null;
  banquet_date: string;
  due_time:     string | null;
  status:       string;
  is_overdue:   boolean;
}

interface DayGroup {
  date:  string;
  tasks: TaskItem[];
}

export default function SmBanquetTasks() {
  const navigate = useNavigate();
  const [role,       setRole]       = useState('');
  const [days,       setDays]       = useState<DayGroup[]>([]);
  const [summary,    setSummary]    = useState({ total_pending: 0, total_done: 0 });
  const [loading,    setLoading]    = useState(true);
  const [completing, setCompleting] = useState<string | null>(null);
  const [showDone,   setShowDone]   = useState(false);

  const load = useCallback(async (r: string) => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = { days_ahead: 7 };
      if (r) params.owner_role = r;
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/tasks`,
        { params },
      );
      // Flatten task list into day groups
      const tasks: TaskItem[] = resp.data?.tasks ?? [];
      const groupMap: Record<string, TaskItem[]> = {};
      for (const t of tasks) {
        const key = t.banquet_date ?? 'unknown';
        if (!groupMap[key]) groupMap[key] = [];
        groupMap[key].push(t);
      }
      const grouped = Object.entries(groupMap)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([date, dayTasks]) => ({ date, tasks: dayTasks }));
      setDays(grouped);
      setSummary({
        total_pending: resp.data?.pending_count ?? 0,
        total_done:    tasks.filter(t => t.status === 'done' || t.status === 'verified').length,
      });
    } catch {
      setDays([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(role); }, [load, role]);

  const toggleTask = async (task: TaskItem) => {
    const isDone = task.status === 'done' || task.status === 'verified';
    if (isDone) return;   // Phase 20 complete endpoint is one-way
    setCompleting(task.task_id);
    try {
      await apiClient.patch(
        `/api/v1/banquet-agent/stores/${STORE_ID}/tasks/${task.task_id}/complete`,
        { remark: '' },
      );
      await load(role);
    } catch (e) {
      handleApiError(e, '更新任务失败');
    } finally {
      setCompleting(null);
    }
  };

  const totalTasks = summary.total_pending + summary.total_done;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <button className={styles.back} onClick={() => navigate('/sm/banquet')}>← 返回</button>
        <div className={styles.title}>任务看板（未来7天）</div>
      </div>

      {/* 角色筛选 */}
      <div className={styles.chipBar}>
        {ROLE_CHIPS.map(c => (
          <button
            key={c.value}
            className={`${styles.chip} ${role === c.value ? styles.chipActive : ''}`}
            onClick={() => setRole(c.value)}
          >
            {c.label}
          </button>
        ))}
      </div>

      {/* 摘要栏 */}
      {!loading && totalTasks > 0 && (
        <div className={styles.summary}>
          <span className={styles.sumPending}>{summary.total_pending} 待处理</span>
          <span className={styles.sumDone}>{summary.total_done} 已完成</span>
          <button className={styles.toggleDone} onClick={() => setShowDone(v => !v)}>
            {showDone ? '隐藏已完成' : '显示已完成'}
          </button>
        </div>
      )}

      <div className={styles.body}>
        {loading ? (
          <ZSkeleton rows={6} />
        ) : days.length === 0 ? (
          <ZEmpty title="未来 7 天暂无执行任务" description="确认订单后自动生成" />
        ) : (
          days.map(day => {
            const visibleTasks = showDone
              ? day.tasks
              : day.tasks.filter(t => t.status !== 'done' && t.status !== 'verified');
            if (visibleTasks.length === 0) return null;
            const pendingCount = day.tasks.filter(
              t => t.status !== 'done' && t.status !== 'verified'
            ).length;
            return (
              <ZCard key={day.date}>
                <div className={styles.dayHeader}>
                  <span className={styles.dayDate}>
                    {dayjs(day.date).format('MM月DD日')}
                    <span className={styles.dayWeek}>
                      （{WEEK_NAMES[dayjs(day.date).day()]}）
                    </span>
                  </span>
                  {pendingCount > 0 && (
                    <ZBadge type="warning" text={`${pendingCount} 待处理`} />
                  )}
                </div>
                <div className={styles.list}>
                  {visibleTasks.map(task => {
                    const isDone = task.status === 'done' || task.status === 'verified';
                    const tb = TASK_STATUS_BADGE[task.status] ?? { text: task.status, type: 'default' as const };
                    return (
                      <div
                        key={task.task_id}
                        className={`${styles.row} ${isDone ? styles.rowDone : ''}`}
                      >
                        <div className={styles.info}>
                          <div className={styles.taskName}>{task.task_name}</div>
                          <div className={styles.meta}>
                            {task.banquet_type
                              ? (BANQUET_TYPE_LABELS[task.banquet_type] ?? task.banquet_type)
                              : ''}
                            {task.due_time
                              ? ` · ${dayjs(task.due_time).format('HH:mm')}`
                              : ''}
                          </div>
                        </div>
                        <div className={styles.right}>
                          <ZBadge type={tb.type} text={tb.text} />
                          <ZButton
                            variant="ghost"
                            size="sm"
                            onClick={() => toggleTask(task)}
                            disabled={completing === task.task_id}
                          >
                            {completing === task.task_id ? '…' : isDone ? '撤销' : '完成'}
                          </ZButton>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </ZCard>
            );
          })
        )}
      </div>
    </div>
  );
}
