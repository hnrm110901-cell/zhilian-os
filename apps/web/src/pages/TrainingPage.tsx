import React, { useState, useEffect } from 'react';
import { Card, Table, Button, Modal, Form, Input, Select, DatePicker, message, Tabs, Statistic, Row, Col, Progress, Tag, Space } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined, EditOutlined, DeleteOutlined, CheckCircleOutlined, ClockCircleOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';

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
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [modalType, setModalType] = useState<'course' | 'record'>('course');
  const [editingItem, setEditingItem] = useState<TrainingCourse | TrainingRecord | null>(null);
  const [form] = Form.useForm();

  useEffect(() => {
    loadMockData();
  }, []);

  const loadMockData = () => {
    const mockCourses: TrainingCourse[] = [
      {
        id: '1',
        name: '客户服务技巧培训',
        category: '服务技能',
        duration: 8,
        instructor: '张老师',
        capacity: 30,
        enrolled: 25,
        status: 'active',
        startDate: '2024-03-15',
        description: '提升客户服务质量和沟通技巧'
      },
      {
        id: '2',
        name: '销售话术进阶',
        category: '销售技能',
        duration: 12,
        instructor: '李老师',
        capacity: 25,
        enrolled: 25,
        status: 'active',
        startDate: '2024-03-20',
        description: '掌握高效销售话术和成交技巧'
      },
      {
        id: '3',
        name: '产品知识培训',
        category: '产品知识',
        duration: 6,
        instructor: '王老师',
        capacity: 40,
        enrolled: 38,
        status: 'completed',
        startDate: '2024-02-10',
        description: '全面了解公司产品特性和优势'
      }
    ];

    const mockRecords: TrainingRecord[] = [
      {
        id: '1',
        employeeId: 'E001',
        employeeName: '张三',
        courseName: '客户服务技巧培训',
        startDate: '2024-03-15',
        endDate: '2024-03-22',
        status: 'in_progress',
        score: 0,
        attendance: 75,
        feedback: ''
      },
      {
        id: '2',
        employeeId: 'E002',
        employeeName: '李四',
        courseName: '产品知识培训',
        startDate: '2024-02-10',
        endDate: '2024-02-16',
        status: 'completed',
        score: 92,
        attendance: 100,
        feedback: '课程内容丰富，讲解清晰'
      },
      {
        id: '3',
        employeeId: 'E003',
        employeeName: '王五',
        courseName: '销售话术进阶',
        startDate: '2024-03-20',
        endDate: '2024-04-01',
        status: 'in_progress',
        score: 0,
        attendance: 83,
        feedback: ''
      }
    ];

    const mockMetrics: PerformanceMetric[] = [
      {
        employeeId: 'E002',
        employeeName: '李四',
        department: '销售部',
        beforeScore: 75,
        afterScore: 92,
        improvement: 17,
        trainingCount: 3
      },
      {
        employeeId: 'E004',
        employeeName: '赵六',
        department: '客服部',
        beforeScore: 68,
        afterScore: 85,
        improvement: 17,
        trainingCount: 2
      },
      {
        employeeId: 'E005',
        employeeName: '孙七',
        department: '销售部',
        beforeScore: 80,
        afterScore: 88,
        improvement: 8,
        trainingCount: 1
      }
    ];

    setCourses(mockCourses);
    setRecords(mockRecords);
    setMetrics(mockMetrics);
  };

  const showModal = (type: 'course' | 'record', item?: TrainingCourse | TrainingRecord) => {
    setModalType(type);
    setEditingItem(item || null);
    if (item) {
      if (type === 'course') {
        const course = item as TrainingCourse;
        form.setFieldsValue({
          ...course,
          startDate: dayjs(course.startDate)
        });
      } else {
        const record = item as TrainingRecord;
        form.setFieldsValue({
          ...record,
          startDate: dayjs(record.startDate),
          endDate: dayjs(record.endDate)
        });
      }
    } else {
      form.resetFields();
    }
    setIsModalVisible(true);
  };

  const handleOk = () => {
    form.validateFields().then(values => {
      if (modalType === 'course') {
        const courseData = {
          ...values,
          startDate: values.startDate.format('YYYY-MM-DD'),
          id: editingItem?.id || Date.now().toString(),
          enrolled: editingItem ? (editingItem as TrainingCourse).enrolled : 0
        };

        if (editingItem) {
          setCourses(courses.map(c => c.id === editingItem.id ? courseData : c));
          message.success('课程更新成功');
        } else {
          setCourses([...courses, courseData]);
          message.success('课程创建成功');
        }
      } else {
        const recordData = {
          ...values,
          startDate: values.startDate.format('YYYY-MM-DD'),
          endDate: values.endDate.format('YYYY-MM-DD'),
          id: editingItem?.id || Date.now().toString()
        };

        if (editingItem) {
          setRecords(records.map(r => r.id === editingItem.id ? recordData : r));
          message.success('培训记录更新成功');
        } else {
          setRecords([...records, recordData]);
          message.success('培训记录创建成功');
        }
      }

      setIsModalVisible(false);
      form.resetFields();
    });
  };

  const handleDelete = (type: 'course' | 'record', id: string) => {
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除这条${type === 'course' ? '课程' : '培训记录'}吗？`,
      onOk: () => {
        if (type === 'course') {
          setCourses(courses.filter(c => c.id !== id));
          message.success('课程删除成功');
        } else {
          setRecords(records.filter(r => r.id !== id));
          message.success('培训记录删除成功');
        }
      }
    });
  };

  const courseColumns: ColumnsType<TrainingCourse> = [
    {
      title: '课程名称',
      dataIndex: 'name',
      key: 'name'
    },
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
      render: (category: string) => <Tag color="blue">{category}</Tag>
    },
    {
      title: '时长(小时)',
      dataIndex: 'duration',
      key: 'duration'
    },
    {
      title: '讲师',
      dataIndex: 'instructor',
      key: 'instructor'
    },
    {
      title: '报名情况',
      key: 'enrollment',
      render: (_, record) => (
        <div>
          <Progress
            percent={Math.round((record.enrolled / record.capacity) * 100)}
            size="small"
            status={record.enrolled >= record.capacity ? 'success' : 'active'}
          />
          <span style={{ fontSize: 12, color: '#666' }}>
            {record.enrolled}/{record.capacity}人
          </span>
        </div>
      )
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const statusMap = {
          active: { text: '进行中', color: 'green' },
          completed: { text: '已完成', color: 'default' },
          cancelled: { text: '已取消', color: 'red' }
        };
        return <Tag color={statusMap[status as keyof typeof statusMap].color}>
          {statusMap[status as keyof typeof statusMap].text}
        </Tag>;
      }
    },
    {
      title: '开始日期',
      dataIndex: 'startDate',
      key: 'startDate'
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => showModal('course', record)}
          >
            编辑
          </Button>
          <Button
            type="link"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete('course', record.id)}
          >
            删除
          </Button>
        </Space>
      )
    }
  ];

  const recordColumns: ColumnsType<TrainingRecord> = [
    {
      title: '员工ID',
      dataIndex: 'employeeId',
      key: 'employeeId'
    },
    {
      title: '员工姓名',
      dataIndex: 'employeeName',
      key: 'employeeName'
    },
    {
      title: '课程名称',
      dataIndex: 'courseName',
      key: 'courseName'
    },
    {
      title: '培训周期',
      key: 'period',
      render: (_, record) => `${record.startDate} ~ ${record.endDate}`
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const statusMap = {
          in_progress: { text: '进行中', color: 'processing', icon: <ClockCircleOutlined /> },
          completed: { text: '已完成', color: 'success', icon: <CheckCircleOutlined /> },
          failed: { text: '未通过', color: 'error', icon: <DeleteOutlined /> }
        };
        return <Tag color={statusMap[status as keyof typeof statusMap].color} icon={statusMap[status as keyof typeof statusMap].icon}>
          {statusMap[status as keyof typeof statusMap].text}
        </Tag>;
      }
    },
    {
      title: '考试成绩',
      dataIndex: 'score',
      key: 'score',
      render: (score: number) => score > 0 ? `${score}分` : '-'
    },
    {
      title: '出勤率',
      dataIndex: 'attendance',
      key: 'attendance',
      render: (attendance: number) => (
        <Progress
          percent={attendance}
          size="small"
          status={attendance >= 80 ? 'success' : 'exception'}
        />
      )
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => showModal('record', record)}
          >
            编辑
          </Button>
          <Button
            type="link"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete('record', record.id)}
          >
            删除
          </Button>
        </Space>
      )
    }
  ];

  const metricColumns: ColumnsType<PerformanceMetric> = [
    {
      title: '员工ID',
      dataIndex: 'employeeId',
      key: 'employeeId'
    },
    {
      title: '员工姓名',
      dataIndex: 'employeeName',
      key: 'employeeName'
    },
    {
      title: '部门',
      dataIndex: 'department',
      key: 'department'
    },
    {
      title: '培训前',
      dataIndex: 'beforeScore',
      key: 'beforeScore',
      render: (score: number) => `${score}分`
    },
    {
      title: '培训后',
      dataIndex: 'afterScore',
      key: 'afterScore',
      render: (score: number) => `${score}分`
    },
    {
      title: '提升幅度',
      dataIndex: 'improvement',
      key: 'improvement',
      render: (improvement: number) => (
        <Tag color={improvement >= 15 ? 'green' : improvement >= 10 ? 'blue' : 'orange'}>
          +{improvement}分
        </Tag>
      )
    },
    {
      title: '培训次数',
      dataIndex: 'trainingCount',
      key: 'trainingCount',
      render: (count: number) => `${count}次`
    }
  ];

  const totalCourses = courses.length;
  const activeCourses = courses.filter(c => c.status === 'active').length;
  const totalRecords = records.length;
  const completedRecords = records.filter(r => r.status === 'completed').length;
  const avgImprovement = metrics.length > 0
    ? Math.round(metrics.reduce((sum, m) => sum + m.improvement, 0) / metrics.length)
    : 0;
  const completionRate = totalRecords > 0
    ? Math.round((completedRecords / totalRecords) * 100)
    : 0;

  return (
    <div>
      <h1 style={{ marginBottom: 24 }}>培训辅导Agent</h1>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="培训课程总数"
              value={totalCourses}
              suffix="门"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="进行中课程"
              value={activeCourses}
              suffix="门"
              valueStyle={{ color: '#3f8600' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="培训完成率"
              value={completionRate}
              suffix="%"
              valueStyle={{ color: completionRate >= 80 ? '#3f8600' : '#cf1322' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="平均提升幅度"
              value={avgImprovement}
              suffix="分"
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
      </Row>

      <Card>
        <Tabs defaultActiveKey="1">
          <TabPane tab="课程管理" key="1">
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => showModal('course')}
              style={{ marginBottom: 16 }}
            >
              新建课程
            </Button>
            <Table
              columns={courseColumns}
              dataSource={courses}
              rowKey="id"
              pagination={{ pageSize: 10 }}
            />
          </TabPane>

          <TabPane tab="培训记录" key="2">
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => showModal('record')}
              style={{ marginBottom: 16 }}
            >
              新建记录
            </Button>
            <Table
              columns={recordColumns}
              dataSource={records}
              rowKey="id"
              pagination={{ pageSize: 10 }}
            />
          </TabPane>

          <TabPane tab="效果评估" key="3">
            <Table
              columns={metricColumns}
              dataSource={metrics}
              rowKey="employeeId"
              pagination={{ pageSize: 10 }}
            />
          </TabPane>
        </Tabs>
      </Card>

      <Modal
        title={editingItem ? (modalType === 'course' ? '编辑课程' : '编辑培训记录') : (modalType === 'course' ? '新建课程' : '新建培训记录')}
        open={isModalVisible}
        onOk={handleOk}
        onCancel={() => {
          setIsModalVisible(false);
          form.resetFields();
        }}
        width={600}
      >
        <Form form={form} layout="vertical">
          {modalType === 'course' ? (
            <>
              <Form.Item
                name="name"
                label="课程名称"
                rules={[{ required: true, message: '请输入课程名称' }]}
              >
                <Input placeholder="请输入课程名称" />
              </Form.Item>
              <Form.Item
                name="category"
                label="课程类别"
                rules={[{ required: true, message: '请选择课程类别' }]}
              >
                <Select placeholder="请选择课程类别">
                  <Option value="服务技能">服务技能</Option>
                  <Option value="销售技能">销售技能</Option>
                  <Option value="产品知识">产品知识</Option>
                  <Option value="管理能力">管理能力</Option>
                  <Option value="沟通技巧">沟通技巧</Option>
                </Select>
              </Form.Item>
              <Form.Item
                name="duration"
                label="课程时长(小时)"
                rules={[{ required: true, message: '请输入课程时长' }]}
              >
                <Input type="number" placeholder="请输入课程时长" />
              </Form.Item>
              <Form.Item
                name="instructor"
                label="讲师"
                rules={[{ required: true, message: '请输入讲师姓名' }]}
              >
                <Input placeholder="请输入讲师姓名" />
              </Form.Item>
              <Form.Item
                name="capacity"
                label="课程容量"
                rules={[{ required: true, message: '请输入课程容量' }]}
              >
                <Input type="number" placeholder="请输入课程容量" />
              </Form.Item>
              <Form.Item
                name="status"
                label="课程状态"
                rules={[{ required: true, message: '请选择课程状态' }]}
              >
                <Select placeholder="请选择课程状态">
                  <Option value="active">进行中</Option>
                  <Option value="completed">已完成</Option>
                  <Option value="cancelled">已取消</Option>
                </Select>
              </Form.Item>
              <Form.Item
                name="startDate"
                label="开始日期"
                rules={[{ required: true, message: '请选择开始日期' }]}
              >
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item
                name="description"
                label="课程描述"
                rules={[{ required: true, message: '请输入课程描述' }]}
              >
                <TextArea rows={3} placeholder="请输入课程描述" />
              </Form.Item>
            </>
          ) : (
            <>
              <Form.Item
                name="employeeId"
                label="员工ID"
                rules={[{ required: true, message: '请输入员工ID' }]}
              >
                <Input placeholder="请输入员工ID" />
              </Form.Item>
              <Form.Item
                name="employeeName"
                label="员工姓名"
                rules={[{ required: true, message: '请输入员工姓名' }]}
              >
                <Input placeholder="请输入员工姓名" />
              </Form.Item>
              <Form.Item
                name="courseName"
                label="课程名称"
                rules={[{ required: true, message: '请输入课程名称' }]}
              >
                <Input placeholder="请输入课程名称" />
              </Form.Item>
              <Form.Item
                name="startDate"
                label="开始日期"
                rules={[{ required: true, message: '请选择开始日期' }]}
              >
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item
                name="endDate"
                label="结束日期"
                rules={[{ required: true, message: '请选择结束日期' }]}
              >
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item
                name="status"
                label="培训状态"
                rules={[{ required: true, message: '请选择培训状态' }]}
              >
                <Select placeholder="请选择培训状态">
                  <Option value="in_progress">进行中</Option>
                  <Option value="completed">已完成</Option>
                  <Option value="failed">未通过</Option>
                </Select>
              </Form.Item>
              <Form.Item
                name="score"
                label="考试成绩"
                rules={[{ required: true, message: '请输入考试成绩' }]}
              >
                <Input type="number" placeholder="请输入考试成绩(0-100)" />
              </Form.Item>
              <Form.Item
                name="attendance"
                label="出勤率(%)"
                rules={[{ required: true, message: '请输入出勤率' }]}
              >
                <Input type="number" placeholder="请输入出勤率(0-100)" />
              </Form.Item>
              <Form.Item
                name="feedback"
                label="培训反馈"
              >
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
