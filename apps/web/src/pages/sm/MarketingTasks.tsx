import React, { useState, useEffect, useCallback } from 'react';
import { Tag } from 'antd';
import { ZCard, ZEmpty } from '../../design-system/components';
import { apiClient } from '../../services/api';
import styles from './MarketingTasks.module.css';

interface Assignment {
  id: string;
  task_title: string;
  status: string;
  target_count: number;
  completed_count: number;
  deadline: string | null;
}

export default function SmMarketingTasks() {
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [loading, setLoading] = useState(false);

  const loadAssignments = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.get<Assignment[]>('/api/v1/sm/marketing-tasks');
      setAssignments(data || []);
    } catch {
      setAssignments([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAssignments(); }, [loadAssignments]);

  if (!loading && assignments.length === 0) {
    return <ZEmpty title="暂无营销任务" description="总部下发的任务会在这里显示" />;
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>营销任务</div>
      </div>
      <div className={styles.list}>
        {assignments.map((a) => (
          <ZCard key={a.id} style={{ marginBottom: 12 }}>
            <div className={styles.taskRow}>
              <div>
                <div className={styles.taskTitle}>{a.task_title}</div>
                <Tag>{a.status === 'assigned' ? '待执行' : '进行中'}</Tag>
              </div>
              <div className={styles.progress}>
                {a.completed_count}/{a.target_count}
              </div>
            </div>
          </ZCard>
        ))}
      </div>
    </div>
  );
}
