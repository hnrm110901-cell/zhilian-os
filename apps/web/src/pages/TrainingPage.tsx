import React, { useState, useEffect, useCallback } from 'react';
import { Card, Table, Button, Modal, Form, Input, Select, DatePicker, Tabs, Statistic, Row, Col, Progress, Tag, Space } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined, EditOutlined, DeleteOutlined, CheckCircleOutlined, ClockCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import apiClient from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { TextArea } = Input;
const { Option } = Select;
const { TabPane } = Tabs;

interface TrainingCourse {
  id: string;
  name: string;
  category: string;
  duration: number;
  instructor: string;
  capacity: number;
  enrolled: number;
  status: 'active' | 'completed' | 'cancelled';
  startDate: string;
  description: string;
}

interface TrainingRecord {
  id: string;
  employeeId: string;
  employeeName: string;
  courseName: string;
  startDate: string;
  endDate: string;
  status: 'in_progress' | 'completed' | 'failed';
  score: number;
  attendance: number;
  feedback: string;
}

interface PerformanceMetric {
  employeeId: string;
  employeeName: string;
  department: string;
  beforeScore: number;
  afterScore: number;
  improvement: number;
  trainingCount: number;
}

const TrainingPage: React.FC = () => {
  const [courses, setCourses] = useState<TrainingCourse[]>([]);
  const [records, setRecords] = useState<TrainingRecord[]>([]);
  const [metrics, setMetrics] = useState<PerformanceMetric[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [modalType, setModalType] = useState<'course' | 'record'>('course');
  const [editingItem, setEditingItem] = useState<TrainingCourse | TrainingRecord | null>(null);
  const [form] = Form.useForm();

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [coursesRes, recordsRes, metricsRes] = await Promise.allSettled([
        apiClient.callAgent('training', { action: 'list_courses' }),
        apiClient.callAgent('training', { action: 'list_records' }),
        apiClient.callAgent('training', { action: 'get_metrics' }),
      ]);
      if (coursesRes.status === 'fulfilled') {
        setCourses(coursesRes.value.output_data?.courses || []);
      }
      if (recordsRes.status === 'fulfilled') {
        setRecords(recordsRes.value.output_data?.records || []);
      }
      if (metricsRes.status === 'fulfilled') {
        setMetrics(metricsRes.value.output_data?.metrics || []);
      }
    } catch (error: any) {
      handleApiError(error, '加载培训数据失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const showModal = (type: 'course' | 'record', item?: TrainingCourse | TrainingRecord) => {
    setModalType(type);
    setEditingItem(item || null);
    if (item) {
      if (type === 'course') {
        const course = item as TrainingCourse;
        form.setFieldsValue({ ...course, startDate: dayjs(course.startDate) });
      } else {
        const record = item as TrainingRecord;
        form.setFieldsValue({ ...record, startDate: dayjs(record.startDate), endDate: dayjs(record.endDate) });
      }
    } else {
      form.resetFields();
    }
    setIsModalVisible(true);
  };

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);

      if (modalType === 'course') {
        const courseData = { ...values, startDate: values.startDate.format('YYYY-MM-DD') };
        if (editingItem) {
          await apiClient.callAgent('training', { action: 'update_course', id: editingItem.id, ...courseData });
          showSuccess('课程更新成功');
        } else {
          await apiClient.callAgent('training', { action: 'create_course', ...courseData });
          showSuccess('课程创建成功');
        }
      } else {
        const recordData = {
          ...values,
          startDate: values.startDate.format('YYYY-MM-DD'),
          endDate: values.endDate.format('YYYY-MM-DD'),
        };
        if (editingItem) {
          await apiClient.callAgent('training', { action: 'update_record', id: editingItem.id, ...recordData });
          showSuccess('培训记录更新成功');
        } else {
          await apiClient.callAgent('training', { action: 'create_record', ...recordData });
          showSuccess('培训记录创建成功');
        }
      }

      setIsModalVisible(false);
      form.resetFields();
      loadData();
    } catch (error: any) {
      if (error.errorFields) return;
      handleApiError(error, '操作失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = (type: 'course' | 'record', id: string) => {
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除这条${type === 'course' ? '课程' : '培训记录'}吗？`,
      onOk: async () => {
        try {
          await apiClient.callAgent('training', {
            action: type === 'course' ? 'delete_course' : 'delete_record',
            id,
          });
          showSuccess(`${type === 'course' ? '课程' : '培训记录'}删除成功`);
          loadData();
        } catch (error: any) {
          handleApiError(error, '删除失败');
        }
      },
    });
  };

  const courseColumns: ColumnsType<TrainingCourse> = [
    { title: '课程名称', dataIndex: 'name', key: 'name' },
    { title: '类别', dataIndex: 'category', key: 'category', render: (c: string) => <Tag color="blue">{c}</Tag> },
    { title: '时长(小时)', dataIndex: 'duration', key: 'duration' },
    { title: '讲师', dataIndex: 'instructor', key: 'instructor' },
    {
      title: '报名情况',
      key: 'enrollment',
      render: (_, record) => (
        <div>
          <Progress percent={Math.round((record.enrolled / record.capacity) * 100)} size="small" status={record.enrolled >= record.capacity ? 'success' : 'active'} />
          <span style={{ fontSize: 12, color: '#666' }}>{record.enrolled}/{record.capacity}人</span>
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const statusMap = { active: { text: '进行中', color: 'green' }, completed: { text: '已完成', color: 'default' }, cancelled: { text: '已取消', color: 'red' } };
        return <Tag color={statusMap[status as keyof typeof statusMap]?.color}>{statusMap[status as keyof typeof statusMap]?.text || status}</Tag>;
      },
    },
    { title: '开始日期', dataIndex: 'startDate', key: 'startDate' },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => showModal('course', record)}>编辑</Button>
          <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleDelete('course', record.id)}>删除</Button>
        </Space>
      ),
    },
  ];

  const recordColumns: ColumnsType<TrainingRecord> = [
    { title: '员工ID', dataIndex: 'employeeId', key: 'employeeId' },
    { title: '员工姓名', dataIndex: 'employeeName', key: 'employeeName' },
    { title: '课程名称', dataIndex: 'courseName', key: 'courseName' },
    { title: '培训周期', key: 'period', render: (_, record) => `${record.startDate} ~ ${record.endDate}` },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const statusMap = {
          in_progress: { text: '进行中', color: 'processing', icon: <ClockCircleOutlined /> },
          completed: { text: '已完成', color: 'success', icon: <CheckCircleOutlined /> },
          failed: { text: '未通过', color: 'error', icon: <DeleteOutlined /> },
        };
        const s = statusMap[status as keyof typeof statusMap];
        return <Tag color={s?.color} icon={s?.icon}>{s?.text || status}</Tag>;
      },
    },
    { title: '考试成绩', dataIndex: 'score', key: 'score', render: (score: number) => score > 0 ? `${score}分` : '-' },
    {
      title: '出勤率',
      dataIndex: 'attendance',
      key: 'attendance',
      render: (attendance: number) => <Progress percent={attendance} size="small" status={attendance >= 80 ? 'success' : 'exception'} />,
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => showModal('record', record)}>编辑</Button>
          <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleDelete('record', record.id)}>删除</Button>
        </Space>
      ),
    },
  ];

  const metricColumns: ColumnsType<PerformanceMetric> = [
    { title: '员工ID', dataIndex: 'employeeId', key: 'employeeId' },
    { title: '员工姓名', dataIndex: 'employeeName', key: 'employeeName' },
    { title: '部门', dataIndex: 'department', key: 'department' },
    { title: '培训前', dataIndex: 'beforeScore', key: 'beforeScore', render: (s: number) => `${s}分` },
    { title: '培训后', dataIndex: 'afterScore', key: 'afterScore', render: (s: number) => `${s}分` },
    {
      title: '提升幅度',
      dataIndex: 'improvement',
      key: 'improvement',
      render: (improvement: number) => (
        <Tag color={improvement >= 15 ? 'green' : improvement >= 10 ? 'blue' : 'orange'}>+{improvement}分</Tag>
      ),
    },
    { title: '培训次数', dataIndex: 'trainingCount', key: 'trainingCount', render: (c: number) => `${c}次` },
  ];

  const totalCourses = courses.length;
  const activeCourses = courses.filter(c => c.status === 'active').length;
  const totalRecords = records.length;
  const completedRecords = records.filter(r => r.status === 'completed').length;
  const avgImprovement = metrics.length > 0
    ? Math.round(metrics.reduce((sum, m) => sum + m.improvement, 0) / metrics.length)
    : 0;
  const completionRate = totalRecords > 0 ? Math.round((completedRecords / totalRecords) * 100) : 0;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>培训辅导Agent</h1>
        <Button icon={<ReloadOutlined />} onClick={loadData} loading={loading}>刷新</Button>
      </div>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card><Statistic title="培训课程总数" value={totalCourses} suffix="门" /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="进行中课程" value={activeCourses} suffix="门" valueStyle={{ color: '#3f8600' }} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="培训完成率" value={completionRate} suffix="%" valueStyle={{ color: completionRate >= 80 ? '#3f8600' : '#cf1322' }} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="平均提升幅度" value={avgImprovement} suffix="分" valueStyle={{ color: '#1890ff' }} /></Card>
        </Col>
      </Row>

      <Card>
        <Tabs defaultActiveKey="1">
          <TabPane tab="课程管理" key="1">
            <Button type="primary" icon={<PlusOutlined />} onClick={() => showModal('course')} style={{ marginBottom: 16 }}>
              新建课程
            </Button>
            <Table columns={courseColumns} dataSource={courses} rowKey="id" pagination={{ pageSize: 10 }} loading={loading} />
          </TabPane>

          <TabPane tab="培训记录" key="2">
            <Button type="primary" icon={<PlusOutlined />} onClick={() => showModal('record')} style={{ marginBottom: 16 }}>
              新建记录
            </Button>
            <Table columns={recordColumns} dataSource={records} rowKey="id" pagination={{ pageSize: 10 }} loading={loading} />
          </TabPane>

          <TabPane tab="效果评估" key="3">
            <Table columns={metricColumns} dataSource={metrics} rowKey="employeeId" pagination={{ pageSize: 10 }} loading={loading} />
          </TabPane>
        </Tabs>
      </Card>

      <Modal
        title={editingItem ? (modalType === 'course' ? '编辑课程' : '编辑培训记录') : (modalType === 'course' ? '新建课程' : '新建培训记录')}
        open={isModalVisible}
        onOk={handleOk}
        confirmLoading={submitting}
        onCancel={() => { setIsModalVisible(false); form.resetFields(); }}
        width={600}
      >
        <Form form={form} layout="vertical">
          {modalType === 'course' ? (
            <>
              <Form.Item name="name" label="课程名称" rules={[{ required: true, message: '请输入课程名称' }]}>
                <Input placeholder="请输入课程名称" />
              </Form.Item>
              <Form.Item name="category" label="课程类别" rules={[{ required: true, message: '请选择课程类别' }]}>
                <Select placeholder="请选择课程类别">
                  <Option value="服务技能">服务技能</Option>
                  <Option value="销售技能">销售技能</Option>
                  <Option value="产品知识">产品知识</Option>
                  <Option value="管理能力">管理能力</Option>
                  <Option value="沟通技巧">沟通技巧</Option>
                </Select>
              </Form.Item>
              <Form.Item name="duration" label="课程时长(小时)" rules={[{ required: true, message: '请输入课程时长' }]}>
                <Input type="number" placeholder="请输入课程时长" />
              </Form.Item>
              <Form.Item name="instructor" label="讲师" rules={[{ required: true, message: '请输入讲师姓名' }]}>
                <Input placeholder="请输入讲师姓名" />
              </Form.Item>
              <Form.Item name="capacity" label="课程容量" rules={[{ required: true, message: '请输入课程容量' }]}>
                <Input type="number" placeholder="请输入课程容量" />
              </Form.Item>
              <Form.Item name="status" label="课程状态" rules={[{ required: true, message: '请选择课程状态' }]}>
                <Select placeholder="请选择课程状态">
                  <Option value="active">进行中</Option>
                  <Option value="completed">已完成</Option>
                  <Option value="cancelled">已取消</Option>
                </Select>
              </Form.Item>
              <Form.Item name="startDate" label="开始日期" rules={[{ required: true, message: '请选择开始日期' }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="description" label="课程描述" rules={[{ required: true, message: '请输入课程描述' }]}>
                <TextArea rows={3} placeholder="请输入课程描述" />
              </Form.Item>
            </>
          ) : (
            <>
              <Form.Item name="employeeId" label="员工ID" rules={[{ required: true, message: '请输入员工ID' }]}>
                <Input placeholder="请输入员工ID" />
              </Form.Item>
              <Form.Item name="employeeName" label="员工姓名" rules={[{ required: true, message: '请输入员工姓名' }]}>
                <Input placeholder="请输入员工姓名" />
              </Form.Item>
              <Form.Item name="courseName" label="课程名称" rules={[{ required: true, message: '请输入课程名称' }]}>
                <Input placeholder="请输入课程名称" />
              </Form.Item>
              <Form.Item name="startDate" label="开始日期" rules={[{ required: true, message: '请选择开始日期' }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="endDate" label="结束日期" rules={[{ required: true, message: '请选择结束日期' }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="status" label="培训状态" rules={[{ required: true, message: '请选择培训状态' }]}>
                <Select placeholder="请选择培训状态">
                  <Option value="in_progress">进行中</Option>
                  <Option value="completed">已完成</Option>
                  <Option value="failed">未通过</Option>
                </Select>
              </Form.Item>
              <Form.Item name="score" label="考试成绩" rules={[{ required: true, message: '请输入考试成绩' }]}>
                <Input type="number" placeholder="请输入考试成绩(0-100)" />
              </Form.Item>
              <Form.Item name="attendance" label="出勤率(%)" rules={[{ required: true, message: '请输入出勤率' }]}>
                <Input type="number" placeholder="请输入出勤率(0-100)" />
              </Form.Item>
              <Form.Item name="feedback" label="培训反馈">
                <TextArea rows={3} placeholder="请输入培训反馈" />
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>
    </div>
  );
};

export default TrainingPage;
