import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Tag, Space, message } from 'antd';
import { ZButton, ZCard } from '../../design-system/components';
import { apiClient } from '../../services/api';
import styles from './MarketingTasks.module.css';

interface Task {
  id: string;
  title: string;
  status: string;
  audience_type: string;
  created_at: string;
  deadline: string | null;
}

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  published: { color: 'blue', label: '已下发' },
  in_progress: { color: 'orange', label: '执行中' },
  completed: { color: 'green', label: '已完成' },
  cancelled: { color: 'red', label: '已取消' },
};

export default function MarketingTasks() {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.get<Task[]>('/api/v1/hq/marketing-tasks');
      setTasks(data || []);
    } catch {
      message.error('加载任务列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadTasks(); }, [loadTasks]);

  const columns = [
    { title: '任务名称', dataIndex: 'title', key: 'title' },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (s: string) => {
        const m = STATUS_MAP[s] || { color: 'default', label: s };
        return <Tag color={m.color}>{m.label}</Tag>;
      },
    },
    {
      title: '人群类型', dataIndex: 'audience_type', key: 'audience_type',
      render: (t: string) => t === 'preset' ? '预设人群包' : 'AI筛选',
    },
    { title: '截止时间', dataIndex: 'deadline', key: 'deadline' },
    {
      title: '操作', key: 'action',
      render: (_: unknown, record: Task) => (
        <Space>
          <a onClick={() => navigate(`/hq/marketing-tasks/${record.id}`)}>详情</a>
        </Space>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.toolbar}>
        <h2>营销任务</h2>
        <ZButton variant="primary" onClick={() => navigate('/hq/marketing-tasks/create')}>
          创建任务
        </ZButton>
      </div>
      <ZCard>
        <Table dataSource={tasks} columns={columns} loading={loading} rowKey="id" />
      </ZCard>
    </div>
  );
}
