import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Modal, Form, Input, Select, Tag, Space, Statistic, Row, Col } from 'antd';
import { PlusOutlined, CheckOutlined, UserAddOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;
const { TextArea } = Input;

const statusColor: Record<string, string> = { pending: 'orange', in_progress: 'blue', completed: 'green', cancelled: 'red' };
const statusLabel: Record<string, string> = { pending: '待处理', in_progress: '进行中', completed: '已完成', cancelled: '已取消' };
const priorityColor: Record<string, string> = { high: 'red', medium: 'orange', low: 'green' };

const TaskManagementPage: React.FC = () => {
  const [tasks, setTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [createVisible, setCreateVisible] = useState(false);
  const [assignVisible, setAssignVisible] = useState(false);
  const [currentTask, setCurrentTask] = useState<any>(null);
  const [assignee, setAssignee] = useState('');
  const [form] = Form.useForm();

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/tasks');
      setTasks(res.data?.tasks || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载任务列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadTasks(); }, [loadTasks]);

  const createTask = async (values: any) => {
    try {
      await apiClient.post('/tasks', values);
      showSuccess('任务创建成功');
      setCreateVisible(false);
      form.resetFields();
      loadTasks();
    } catch (err: any) {
      handleApiError(err, '创建任务失败');
    }
  };

  const assignTask = async () => {
    try {
      await apiClient.put(`/tasks/${currentTask.task_id || currentTask.id}/assign`, { assignee });
      showSuccess('任务分配成功');
      setAssignVisible(false);
      loadTasks();
    } catch (err: any) {
      handleApiError(err, '分配任务失败');
    }
  };

  const completeTask = async (task: any) => {
    try {
      await apiClient.put(`/tasks/${task.task_id || task.id}/complete`);
      showSuccess('任务已完成');
      loadTasks();
    } catch (err: any) {
      handleApiError(err, '操作失败');
    }
  };

  const deleteTask = async (task: any) => {
    try {
      await apiClient.delete(`/tasks/${task.task_id || task.id}`);
      showSuccess('任务已删除');
      loadTasks();
    } catch (err: any) {
      handleApiError(err, '删除失败');
    }
  };

  const pending = tasks.filter(t => t.status === 'pending').length;
  const inProgress = tasks.filter(t => t.status === 'in_progress').length;
  const completed = tasks.filter(t => t.status === 'completed').length;

  const columns: ColumnsType<any> = [
    { title: '任务标题', dataIndex: 'title', key: 'title', ellipsis: true },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    {
      title: '优先级', dataIndex: 'priority', key: 'priority',
      render: (v: string) => <Tag color={priorityColor[v] || 'default'}>{v || '-'}</Tag>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (v: string) => <Tag color={statusColor[v] || 'default'}>{statusLabel[v] || v}</Tag>,
    },
    { title: '负责人', dataIndex: 'assignee', key: 'assignee', render: (v: string) => v || '-' },
    { title: '截止日期', dataIndex: 'due_date', key: 'due_date', render: (v: string) => v || '-' },
    {
      title: '操作', key: 'action',
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" icon={<UserAddOutlined />} onClick={() => { setCurrentTask(record); setAssignee(''); setAssignVisible(true); }}>分配</Button>
          {record.status !== 'completed' && (
            <Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => completeTask(record)}>完成</Button>
          )}
          <Button size="small" danger onClick={() => deleteTask(record)}>删除</Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}><Card><Statistic title="待处理" value={pending} valueStyle={{ color: '#fa8c16' }} /></Card></Col>
        <Col span={8}><Card><Statistic title="进行中" value={inProgress} valueStyle={{ color: '#1890ff' }} /></Card></Col>
        <Col span={8}><Card><Statistic title="已完成" value={completed} valueStyle={{ color: '#52c41a' }} /></Card></Col>
      </Row>

      <Card
        title="任务列表"
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateVisible(true)}>新建任务</Button>}
      >
        <Table columns={columns} dataSource={tasks} rowKey={(r, i) => r.task_id || r.id || String(i)} loading={loading} />
      </Card>

      <Modal title="新建任务" open={createVisible} onCancel={() => { setCreateVisible(false); form.resetFields(); }} onOk={() => form.submit()} okText="创建">
        <Form form={form} layout="vertical" onFinish={createTask}>
          <Form.Item name="title" label="任务标题" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="描述"><TextArea rows={3} /></Form.Item>
          <Form.Item name="priority" label="优先级" initialValue="medium">
            <Select>
              <Option value="high">高</Option>
              <Option value="medium">中</Option>
              <Option value="low">低</Option>
            </Select>
          </Form.Item>
          <Form.Item name="due_date" label="截止日期"><Input type="date" /></Form.Item>
        </Form>
      </Modal>

      <Modal title="分配任务" open={assignVisible} onCancel={() => setAssignVisible(false)} onOk={assignTask} okText="确认分配">
        <p>任务：{currentTask?.title}</p>
        <Input placeholder="输入负责人" value={assignee} onChange={e => setAssignee(e.target.value)} />
      </Modal>
    </div>
  );
};

export default TaskManagementPage;
