/**
 * 师徒管理页面 — 配对/培养周期/验收
 */
import React, { useEffect, useState } from 'react';
import { Card, Table, Tag, Typography, Spin } from 'antd';
import { TeamOutlined } from '@ant-design/icons';
import { hrService } from '../../services/hrService';
import type { MentorshipItem } from '../../services/hrService';
import { useAuthStore } from '../../stores/authStore';

const { Title } = Typography;

const MentorshipPage: React.FC = () => {
  const [data, setData] = useState<MentorshipItem[]>([]);
  const [loading, setLoading] = useState(true);
  const user = useAuthStore((s) => s.user);
  const storeId = user?.store_id || '';

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const res = await hrService.getMentorships(storeId);
      setData(res.items);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  };

  const columns = [
    { title: '培养岗位', dataIndex: 'target_position', key: 'position' },
    { title: '师傅', dataIndex: 'mentor_name', key: 'mentor' },
    { title: '徒弟', dataIndex: 'apprentice_name', key: 'apprentice' },
    { title: '开始日期', dataIndex: 'training_start', key: 'start' },
    { title: '结束日期', dataIndex: 'training_end', key: 'end' },
    { title: '预计验收', dataIndex: 'expected_review_date', key: 'review' },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (s: string) => (
        <Tag color={s === 'completed' ? 'green' : s === 'active' ? 'blue' : 'default'}>
          {s === 'active' ? '培养中' : s === 'completed' ? '已完成' : '已取消'}
        </Tag>
      ),
    },
    {
      title: '验收结果', dataIndex: 'review_result', key: 'result',
      render: (r: string | null) => r ? (
        <Tag color={r === 'passed' ? 'green' : 'red'}>{r === 'passed' ? '通过' : '未通过'}</Tag>
      ) : '-',
    },
    {
      title: '奖励', dataIndex: 'reward_yuan', key: 'reward',
      render: (v: number) => v > 0 ? `¥${v.toFixed(2)}` : '-',
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}><TeamOutlined /> 师徒管理</Title>
      <Card>
        {loading ? <Spin /> : (
          <Table
            dataSource={data.map((d, i) => ({ ...d, key: i }))}
            columns={columns}
            pagination={{ pageSize: 20 }}
          />
        )}
      </Card>
    </div>
  );
};

export default MentorshipPage;
