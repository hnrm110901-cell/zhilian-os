import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Tag, Space, Form, Select, Statistic, Row, Col, Descriptions, Modal } from 'antd';
import { PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;

const SchedulerPage: React.FC = () => {
  const [schedule, setSchedule] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [taskStatus, setTaskStatus] = useState<any>(null);
  const [statusVisible, setStatusVisible] = useState(false);
  const [triggerForm] = Form.useForm();

  const loadSchedule = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/scheduler/schedule');
      setSchedule(res.data?.tasks || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载调度计划失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadSchedule(); }, [loadSchedule]);

  const triggerTask = async (values: any) => {
    setTriggering(true);
    try {
      const res = await apiClient.post(`/scheduler/trigger/${values.task_name}`);
      showSuccess(`任务 ${values.task_name} 已触发`);
      setTaskStatus(res.data);
      setStatusVisible(true);
      triggerForm.resetFields();
    } catch (err: any) {
      handleApiError(err, '触发任务失败');
    } finally {
      setTriggering(false);
    }
  };

  const checkStatus = async (taskId: string) => {
    try {
      const res = await apiClient.get(`/scheduler/status/${taskId}`);
      setTaskStatus(res.data);
      setStatusVisible(true);
    } catch (err: any) {
      handleApiError(err, '获取任务状态失败');
    }
  };

  const runningCount = schedule.filter(t => t.status === 'running').length;
  const pendingCount = schedule.filter(t => t.status === 'pending' || t.enabled).length;

  const columns: ColumnsType<any> = [
    { title: '任务名称', dataIndex: 'name', key: 'name' },
    { title: 'Cron表达式', dataIndex: 'cron', key: 'cron', render: (v: string) => <code>{v || '-'}</code> },
    { title: '描述', dataIndex: 'description', key: 'desc', ellipsis: true },
    {
      title: '状态', dataIndex: 'enabled', key: 'enabled',
      render: (v: boolean, r: any) => <Tag color={v || r.status === 'running' ? 'green' : 'default'}>{v || r.status === 'running' ? '启用' : '禁用'}</Tag>,
    },
    { title: '上次执行', dataIndex: 'last_run', key: 'last_run', render: (v: string) => v || '-' },
    { title: '下次执行', dataIndex: 'next_run', key: 'next_run', render: (v: string) => v || '-' },
    {
      title: '操作', key: 'action',
      render: (_: any, record: any) => (
        <Space>
          {record.task_id && (
            <Button size="small" icon={<ReloadOutlined />} onClick={() => checkStatus(record.task_id)}>状态</Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}><Card><Statistic title="计划任务总数" value={schedule.length} /></Card></Col>
        <Col span={8}><Card><Statistic title="运行中" value={runningCount} valueStyle={{ color: '#1890ff' }} /></Card></Col>
        <Col span={8}><Card><Statistic title="已启用" value={pendingCount} valueStyle={{ color: '#52c41a' }} /></Card></Col>
      </Row>

      <Card title="手动触发任务" style={{ marginBottom: 16 }}>
        <Form form={triggerForm} layout="inline" onFinish={triggerTask}>
          <Form.Item name="task_name" label="任务名称" rules={[{ required: true }]}>
            <Select style={{ width: 200 }} placeholder="选择或输入任务名">
              <Option value="forecast_update">预测更新</Option>
              <Option value="inventory_check">库存检查</Option>
              <Option value="report_generate">报表生成</Option>
              <Option value="data_backup">数据备份</Option>
              <Option value="model_retrain">模型重训</Option>
            </Select>
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" icon={<PlayCircleOutlined />} loading={triggering}>立即触发</Button>
          </Form.Item>
        </Form>
      </Card>

      <Card title="调度计划">
        <Table columns={columns} dataSource={schedule} rowKey={(r, i) => r.name || r.task_id || String(i)} loading={loading} />
      </Card>

      <Modal title="任务状态" open={statusVisible} onCancel={() => setStatusVisible(false)} footer={null}>
        {taskStatus && (
          <Descriptions bordered column={1}>
            <Descriptions.Item label="任务ID">{taskStatus.task_id || '-'}</Descriptions.Item>
            <Descriptions.Item label="状态"><Tag color={taskStatus.status === 'completed' ? 'green' : taskStatus.status === 'running' ? 'blue' : 'orange'}>{taskStatus.status || '-'}</Tag></Descriptions.Item>
            <Descriptions.Item label="开始时间">{taskStatus.started_at || '-'}</Descriptions.Item>
            <Descriptions.Item label="完成时间">{taskStatus.completed_at || '-'}</Descriptions.Item>
            <Descriptions.Item label="结果">{taskStatus.result ? JSON.stringify(taskStatus.result) : '-'}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default SchedulerPage;
