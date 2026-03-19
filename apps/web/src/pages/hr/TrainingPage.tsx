/**
 * 培训课程页面 — 课程列表(卡片式) + 学习进度
 */
import React, { useEffect, useState } from 'react';
import { Card, Row, Col, Tag, Progress, Tabs, Empty, Spin, Typography } from 'antd';
import { BookOutlined, TrophyOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { hrService } from '../../services/hrService';
import type { TrainingCourseItem, TrainingEnrollmentItem } from '../../services/hrService';
import { useAuthStore } from '../../stores/authStore';

const { Title, Text } = Typography;

const categoryColors: Record<string, string> = {
  safety: 'red', service: 'blue', cooking: 'orange', management: 'purple', culture: 'green',
};
const categoryLabels: Record<string, string> = {
  safety: '食品安全', service: '服务规范', cooking: '烹饪技能', management: '管理培训', culture: '企业文化',
};

const TrainingPage: React.FC = () => {
  const [courses, setCourses] = useState<TrainingCourseItem[]>([]);
  const [enrollments, setEnrollments] = useState<TrainingEnrollmentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const user = useAuthStore((s) => s.user);
  const brandId = user?.brand_id || '';
  const employeeId = user?.id || '';

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [courseRes, enrollRes] = await Promise.all([
        hrService.getTrainingCourses(brandId),
        hrService.getMyCourses(employeeId),
      ]);
      setCourses(courseRes.items);
      setEnrollments(enrollRes.items);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  };

  if (loading) return <Spin style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}><BookOutlined /> 培训中心</Title>
      <Tabs defaultActiveKey="courses" items={[
        {
          key: 'courses',
          label: '课程列表',
          children: (
            <Row gutter={[16, 16]}>
              {courses.length === 0 ? <Col span={24}><Empty description="暂无课程" /></Col> : courses.map(c => (
                <Col key={c.id} xs={24} sm={12} md={8} lg={6}>
                  <Card hoverable>
                    <div style={{ marginBottom: 8 }}>
                      <Tag color={categoryColors[c.category]}>{categoryLabels[c.category] || c.category}</Tag>
                      {c.is_mandatory && <Tag color="red">必修</Tag>}
                      <Tag>{c.course_type === 'online' ? '线上' : c.course_type === 'offline' ? '线下' : '实操'}</Tag>
                    </div>
                    <Title level={5} style={{ marginBottom: 4 }}>{c.title}</Title>
                    <Text type="secondary">{c.description || '暂无描述'}</Text>
                    <div style={{ marginTop: 12, display: 'flex', justifyContent: 'space-between' }}>
                      <span><ClockCircleOutlined /> {c.duration_minutes}分钟</span>
                      <span><TrophyOutlined /> {c.credits}学分</span>
                    </div>
                  </Card>
                </Col>
              ))}
            </Row>
          ),
        },
        {
          key: 'my',
          label: `我的学习 (${enrollments.length})`,
          children: (
            <Row gutter={[16, 16]}>
              {enrollments.map(e => (
                <Col key={e.enrollment_id} xs={24} sm={12} md={8}>
                  <Card>
                    <Title level={5}>{e.course_title}</Title>
                    <Tag color={categoryColors[e.category]}>{categoryLabels[e.category] || e.category}</Tag>
                    <Progress percent={e.progress_pct} style={{ marginTop: 12 }} />
                    <div style={{ marginTop: 8 }}>
                      <Tag color={e.status === 'completed' ? 'green' : e.status === 'in_progress' ? 'blue' : 'default'}>
                        {e.status === 'completed' ? '已完成' : e.status === 'in_progress' ? '学习中' : e.status === 'failed' ? '未通过' : '待学习'}
                      </Tag>
                      {e.score !== null && <span style={{ marginLeft: 8 }}>成绩：{e.score}分</span>}
                      {e.certificate_no && <Tag color="gold" style={{ marginLeft: 8 }}>已认证</Tag>}
                    </div>
                  </Card>
                </Col>
              ))}
            </Row>
          ),
        },
      ]} />
    </div>
  );
};

export default TrainingPage;
