/**
 * 培训看板 — 完成率/认证率/学分排行
 */
import React, { useEffect, useState } from 'react';
import { Card, Row, Col, Statistic, Progress, Typography, Spin } from 'antd';
import { BookOutlined, TrophyOutlined, TeamOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { hrService } from '../../services/hrService';
import type { TrainingDashboardData } from '../../services/hrService';

const { Title } = Typography;

const TrainingDashboard: React.FC = () => {
  const [data, setData] = useState<TrainingDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const brandId = 'default_brand';

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const res = await hrService.getTrainingDashboard(brandId);
      setData(res);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  };

  if (loading) return <Spin style={{ display: 'block', margin: '100px auto' }} />;
  if (!data) return null;

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}><BookOutlined /> 培训看板</Title>
      <Row gutter={[16, 16]}>
        <Col span={6}>
          <Card><Statistic title="课程总数" value={data.total_courses} prefix={<BookOutlined />} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="总报名人次" value={data.total_enrollments} /></Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="完成率" value={data.completion_rate_pct} suffix="%" prefix={<CheckCircleOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="已获学分" value={data.total_credits_earned} prefix={<TrophyOutlined />} /></Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card title="学习状态分布">
            {Object.entries(data.enrollment_by_status).map(([status, count]) => (
              <div key={status} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span>{status === 'enrolled' ? '待学习' : status === 'in_progress' ? '学习中' : status === 'completed' ? '已完成' : status === 'failed' ? '未通过' : status}</span>
                <Progress percent={Math.round(count / Math.max(data.total_enrollments, 1) * 100)} style={{ width: 200 }} size="small" />
                <span>{count}人</span>
              </div>
            ))}
          </Card>
        </Col>
        <Col span={12}>
          <Card title={<><TeamOutlined /> 师徒制</>}>
            <Row gutter={16}>
              <Col span={12}>
                <Statistic title="进行中" value={data.active_mentorships} suffix="对" />
              </Col>
              <Col span={12}>
                <Statistic title="已完成" value={data.completed_mentorships} suffix="对" valueStyle={{ color: '#52c41a' }} />
              </Col>
            </Row>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default TrainingDashboard;
