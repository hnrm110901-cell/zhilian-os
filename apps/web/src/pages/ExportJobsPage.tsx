import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Tag, Space, Statistic, Row, Col, Modal, Form, Select, DatePicker, Progress } from 'antd';
import { PlusOutlined, DownloadOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;
const { RangePicker } = DatePicker;

const statusColor: Record<string, string> = { pending: 'orange', running: 'blue', completed: 'green', failed: 'red' };
const statusLabel: Record<string, string> = { pending: '等待中', running: '进行中', completed: '已完成', failed: '失败' };

const ExportJobsPage: React.FC = () => {
  const [jobs, setJobs] = useState<any[]>([]);
  const [exportTypes, setExportTypes] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});
  const [createVisible, setCreateVisible] = useState(false);
  const [form] = Form.useForm();

  const loadJobs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/export-jobs');
      setJobs(res.data?.jobs || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载导出任务失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadTypes = useCallback(async () => {
    try {
      const res = await apiClient.get('/export-jobs/types');
      setExportTypes(res.data?.types || res.data || []);
    } catch {
      setExportTypes(['transactions', 'audit_logs', 'orders']);
    }
  }, []);

  useEffect(() => {
    loadJobs();
    loadTypes();
  }, [loadJobs, loadTypes]);

  const createJob = async (values: any) => {
    try {
      const payload: any = { export_type: values.export_type };
      if (values.date_range) {
        payload.start_date = values.date_range[0].format('YYYY-MM-DD');
        payload.end_date = values.date_range[1].format('YYYY-MM-DD');
      }
      await apiClient.post('/export-jobs', payload);
      showSuccess('导出任务已提交');
      setCreateVisible(false);
      form.resetFields();
      loadJobs();
    } catch (err: any) {
      handleApiError(err, '提交失败');
    }
  };

  const downloadJob = async (record: any) => {
    const key = `dl-${record.job_id || record.id}`;
    setActionLoading(prev => ({ ...prev, [key]: true }));
    try {
      const res = await apiClient.get(`/export-jobs/${record.job_id || record.id}/download`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `export_${record.job_id || record.id}.csv`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      handleApiError(err, '下载失败');
    } finally {
      setActionLoading(prev => ({ ...prev, [key]: false }));
    }
  };

  const deleteJob = async (record: any) => {
    const key = `del-${record.job_id || record.id}`;
    setActionLoading(prev => ({ ...prev, [key]: true }));
    try {
      await apiClient.delete(`/export-jobs/${record.job_id || record.id}`);
      showSuccess('已删除');
      loadJobs();
    } catch (err: any) {
      handleApiError(err, '删除失败');
    } finally {
      setActionLoading(prev => ({ ...prev, [key]: false }));
    }
  };

  const columns: ColumnsType<any> = [
    { title: '任务ID', dataIndex: 'job_id', key: 'job_id', ellipsis: true },
    { title: '导出类型', dataIndex: 'export_type', key: 'export_type' },
    { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={statusColor[v] || 'default'}>{statusLabel[v] || v}</Tag> },
    { title: '进度', dataIndex: 'progress', key: 'progress', render: (v: number) => <Progress percent={Math.round((v || 0) * 100)} size="small" style={{ width: 100 }} /> },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', ellipsis: true },
    {
      title: '操作', key: 'actions',
      render: (_: any, record: any) => (
        <Space>
          {record.status === 'completed' && (
            <Button size="small" type="primary" icon={<DownloadOutlined />} loading={actionLoading[`dl-${record.job_id || record.id}`]} onClick={() => downloadJob(record)}>下载</Button>
          )}
          <Button size="small" danger icon={<DeleteOutlined />} loading={actionLoading[`del-${record.job_id || record.id}`]} onClick={() => deleteJob(record)}>删除</Button>
        </Space>
      ),
    },
  ];

  const completed = jobs.filter((j: any) => j.status === 'completed').length;
  const running = jobs.filter((j: any) => j.status === 'running' || j.status === 'pending').length;

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="总任务数" value={jobs.length} /></Card></Col>
        <Col span={6}><Card><Statistic title="进行中" value={running} /></Card></Col>
        <Col span={6}><Card><Statistic title="已完成" value={completed} /></Card></Col>
        <Col span={6}><Card><Statistic title="失败" value={jobs.filter((j: any) => j.status === 'failed').length} /></Card></Col>
      </Row>

      <Card
        title="导出任务列表"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadJobs}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateVisible(true)}>新建导出</Button>
          </Space>
        }
      >
        <Table columns={columns} dataSource={jobs} rowKey={(r) => r.job_id || r.id} loading={loading} />
      </Card>

      <Modal title="新建导出任务" open={createVisible} onCancel={() => setCreateVisible(false)} onOk={() => form.submit()} okText="提交">
        <Form form={form} layout="vertical" onFinish={createJob}>
          <Form.Item name="export_type" label="导出类型" rules={[{ required: true }]}>
            <Select>
              {exportTypes.map(t => <Option key={t} value={t}>{t}</Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="date_range" label="日期范围">
            <RangePicker style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ExportJobsPage;
