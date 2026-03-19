import React, { useState, useEffect, useCallback } from 'react';
import { message } from 'antd';
import { useAuth } from '../../contexts/AuthContext';
import { actionTaskService } from '../../services/dailyOpsService';
import type { ActionTask } from '../../types/dailyOps';
import styles from './AbnormalTasks.module.css';

const STATUS_MAP: Record<string, { label: string; color: string; bg: string }> = {
  generated:      { label: '已生成', color: '#1890ff', bg: '#e6f4ff' },
  pending_handle: { label: '待处理', color: '#d46b08', bg: '#fff7e6' },
  submitted:      { label: '已提交', color: '#389e0d', bg: '#f6ffed' },
  pending_review: { label: '待复核', color: '#1890ff', bg: '#e6f4ff' },
  rectifying:     { label: '整改中', color: '#722ed1', bg: '#f9f0ff' },
  closed:         { label: '已关闭', color: '#595959', bg: '#f5f5f5' },
  returned:       { label: '已退回', color: '#cf1322', bg: '#fff2f0' },
  repeated:       { label: '复发', color: '#cf1322', bg: '#fff2f0' },
  canceled:       { label: '已取消', color: '#888', bg: '#f5f5f5' },
};

export default function AbnormalTasks() {
  const { user } = useAuth();
  const storeId = user?.store_id ?? '';

  const [tasks, setTasks] = useState<ActionTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeFilter, setActiveFilter] = useState<string>('all');
  const [expandedTaskId, setExpandedTaskId] = useState<string | number | null>(null);
  const [submitComment, setSubmitComment] = useState<Record<string | number, string>>({});
  const [submitting, setSubmitting] = useState<string | number | null>(null);

  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const list = await actionTaskService.list({ storeId });
      setTasks(list);
    } catch {
      message.error('任务加载失败');
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  const filteredTasks = activeFilter === 'all'
    ? tasks
    : activeFilter === 'pending'
      ? tasks.filter(t => ['generated', 'pending_handle', 'returned'].includes(t.status))
      : activeFilter === 'red'
        ? tasks.filter(t => t.severityLevel === 'red')
        : tasks;

  const handleSubmit = async (taskId: string | number) => {
    const comment = submitComment[taskId] || '';
    if (!comment.trim()) { message.error('说明不能为空'); return; }
    setSubmitting(taskId);
    try {
      await actionTaskService.submit(taskId, { submitComment: comment });
      message.success('说明已提交，等待审核');
      load();
      setExpandedTaskId(null);
    } catch {
      message.error('提交失败');
    } finally {
      setSubmitting(null);
    }
  };

  const filterBtns = [
    { key: 'all', label: `全部 (${tasks.length})` },
    { key: 'pending', label: `待处理 (${tasks.filter(t => ['generated','pending_handle','returned'].includes(t.status)).length})` },
    { key: 'red', label: `红灯 (${tasks.filter(t => t.severityLevel === 'red').length})` },
  ];

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.title}>异常任务</div>
        {[1,2,3].map(i => <div key={i} className={styles.skeletonCard} />)}
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <span className={styles.title}>异常任务</span>
      </div>

      {/* 筛选 */}
      <div className={styles.filterRow}>
        {filterBtns.map(f => (
          <button
            key={f.key}
            className={`${styles.filterBtn} ${activeFilter === f.key ? styles.filterActive : ''}`}
            onClick={() => setActiveFilter(f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {filteredTasks.length === 0 ? (
        <div className={styles.empty}>
          <div className={styles.emptyIcon}>✅</div>
          <div>暂无任务</div>
        </div>
      ) : (
        <div className={styles.list}>
          {filteredTasks.map(task => {
            const s = STATUS_MAP[task.status] || { label: task.status, color: '#888', bg: '#f5f5f5' };
            const expanded = expandedTaskId === task.id;
            const canSubmit = ['generated', 'pending_handle', 'returned'].includes(task.status);
            return (
              <div key={task.id} className={styles.card}>
                <div className={styles.cardHeader} onClick={() => setExpandedTaskId(expanded ? null : task.id)}>
                  <div className={styles.cardLeft}>
                    <span className={`${styles.severity} ${task.severityLevel === 'red' ? styles.red : styles.yellow}`}>
                      {task.severityLevel === 'red' ? '🔴' : '🟡'}
                    </span>
                    <div>
                      <div className={styles.cardTitle}>{task.taskTitle}</div>
                      <div className={styles.cardMeta}>{task.bizDate} · {task.assigneeRole === 'chef' ? '厨师长' : '店长'}</div>
                    </div>
                  </div>
                  <div className={styles.cardRight}>
                    <span className={styles.statusTag} style={{ color: s.color, background: s.bg }}>{s.label}</span>
                    {task.isRepeatedIssue && <span className={styles.repeatTag}>复发×{task.repeatCount}</span>}
                    <span className={styles.expandIcon}>{expanded ? '▲' : '▼'}</span>
                  </div>
                </div>

                {expanded && (
                  <div className={styles.cardBody}>
                    {task.taskDescription && (
                      <div className={styles.desc}>{task.taskDescription}</div>
                    )}
                    {task.dueAt && (
                      <div className={styles.meta}>截止：{task.dueAt.slice(0, 16)}</div>
                    )}
                    {task.submitComment && (
                      <div className={styles.comment}>
                        <span className={styles.commentLabel}>已提交说明：</span>
                        <span>{task.submitComment}</span>
                      </div>
                    )}
                    {task.reviewComment && (
                      <div className={styles.comment}>
                        <span className={styles.commentLabel}>审核意见：</span>
                        <span>{task.reviewComment}</span>
                      </div>
                    )}
                    {canSubmit && (
                      <div className={styles.submitArea}>
                        <textarea
                          className={styles.textarea}
                          rows={2}
                          placeholder="请说明原因及整改措施"
                          value={submitComment[task.id] || ''}
                          onChange={e => setSubmitComment(prev => ({ ...prev, [task.id]: e.target.value }))}
                        />
                        <button
                          className={styles.submitBtn}
                          disabled={submitting === task.id}
                          onClick={() => handleSubmit(task.id)}
                        >
                          {submitting === task.id ? '提交中...' : '提交说明'}
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
