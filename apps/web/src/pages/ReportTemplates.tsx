import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Tabs, Table, Button, Modal, Form, Input, Select,
  Space, Popconfirm, Switch, Tag,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
  DownloadOutlined, PlayCircleOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { showSuccess, handleApiError, showLoading } from '../utils/message';

interface ReportTemplate {
  id: number;
  name: string;
  type: string;
  description?: string;
  format: string;
  created_at?: string;
}

interface ScheduledReport {
  id: number;
  template_id: number;
  template_name?: string;
  cron_expression: string;
  recipients: string;
  is_active: boolean;
  created_at?: string;
}

const ReportTemplates: React.FC = () => {
  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  const [scheduled, setScheduled] = useState<ScheduledReport[]>([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [loadingScheduled, setLoadingScheduled] = useState(false);
  const [templateModalVisible, setTemplateModalVisible] = useState(false);
  const [scheduleModalVisible, setScheduleModalVisible] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<ReportTemplate | null>(null);
  const [templateForm] = Form.useForm();
  const [scheduleForm] = Form.useForm();

  const loadTemplates = useCallback(async () => {
    try {
      setLoadingTemplates(true);
      const res = await apiClient.get('/api/v1/report-templates/');
      setTemplates(res.data?.data || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载模板列表失败');
    } finally {
      setLoadingTemplates(false);
    }
  }, []);

  const loadScheduled = useCallback(async () => {
    try {
      setLoadingScheduled(true);
      const res = await apiClient.get('/api/v1/report-templates/scheduled-reports');
      setScheduled(res.data?.data || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载订阅列表失败');
    } finally {
      setLoadingScheduled(false);
    }
  }, []);

  useEffect(() => {
    loadTemplates();
    loadScheduled();
  }, [loadTemplates, loadScheduled]);

  const handleGenerate = async (id: number, name: string) => {
    const hide = showLoading('生成报表中...');
    try {
      const res = await apiClient.get(`/api/v1/report-templates/${id}/generate`, { responseType: 'blob' });
      hide();
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${name}_report.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      showSuccess('报表生成成功');
    } catch (err: any) {
      hide();
      handleApiError(err, '生成报表失败');
    }
  };

  const handleDeleteTemplate = async (id: number) => {
    const hide = showLoading('删除中...');
    try {
      await apiClient.delete(`/api/v1/report-templates/${id}`);
      hide();
      showSuccess('删除成功');
      loadTemplates();
    } catch (err: any) {
      hide();
      handleApiError(err, '删除失败');
    }
  };

  const handleTemplateModalOk = async () => {
    try {
      const values = await templateForm.validateFields();
      const hide = showLoading(editingTemplate ? '更新中...' : '新增中...');
      try {
        if (editingTemplate) {
          await apiClient.put(`/api/v1/report-templates/${editingTemplate.id}`, values);
        } else {
          await apiClient.post('/api/v1/report-templates/', values);
        }
        hide();
        showSuccess(editingTemplate ? '更新成功' : '新增成功');
        setTemplateModalVisible(false);
        loadTemplates();
      } catch (err: any) {
        hide();
        handleApiError(err, '操作失败');
      }
    } catch (_) {}
  };

  const handleToggleSchedule = async (record: ScheduledReport) => {
    const hide = showLoading('更新中...');
    try {
      await apiClient.put(`/api/v1/report-templates/scheduled-reports/${record.id}`, {
        is_active: !record.is_active,
      });
      hide();
      showSuccess('更新成功');
      loadScheduled();
    } catch (err: any) {
      hide();
      handleApiError(err, '更新失败');
    }
  };

  const handleDeleteSchedule = async (id: number) => {
    const hide = showLoading('删除中...');
    try {
      await apiClient.delete(`/api/v1/report-templates/scheduled-reports/${id}`);
      hide();
      showSuccess('删除成功');
      loadScheduled();
    } catch (err: any) {
      hide();
      handleApiError(err, '删除失败');
    }
  };

  const handleScheduleModalOk = async () => {
    try {
      const values = await scheduleForm.validateFields();
      const hide = showLoading('新增订阅中...');
      try {
        await apiClient.post('/api/v1/report-templates/scheduled-reports', values);
        hide();
        showSuccess('订阅创建成功');
        setScheduleModalVisible(false);
        loadScheduled();
      } catch (err: any) {
        hide();
        handleApiError(err, '创建订阅失败');
      }
    } catch (_) {}
  };

  const templateColumns: ColumnsType<ReportTemplate> = [
    { title: '模板名称', dataIndex: 'name', key: 'name' },
    { title: '类型', dataIndex: 'type', key: 'type' },
    { title: '格式', dataIndex: 'format', key: 'format', render: (v) => <Tag>{v?.toUpperCase()}</Tag> },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    {
      title: '操作', key: 'action',
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<PlayCircleOutlined />} type="primary"
            onClick={() => handleGenerate(record.id, record.name)}>生成报表</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => {
            setEditingTemplate(record);
            templateForm.setFieldsValue(record);
            setTemplateModalVisible(true);
          }}>编辑</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDeleteTemplate(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const scheduleColumns: ColumnsType<ScheduledReport> = [
    { title: '模板', dataIndex: 'template_name', key: 'template_name' },
    { title: 'Cron 表达式', dataIndex: 'cron_expression', key: 'cron_expression' },
    { title: '收件人', dataIndex: 'recipients', key: 'recipients', ellipsis: true },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active',
      render: (v, record) => (
        <Switch checked={v} onChange={() => handleToggleSchedule(record)} checkedChildren="启用" unCheckedChildren="禁用" />
      ),
    },
    {
      title: '操作', key: 'action',
      render: (_, record) => (
        <Popconfirm title="确认删除？" onConfirm={() => handleDeleteSchedule(record.id)}>
          <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
        </Popconfirm>
      ),
    },
  ];

  const tabItems = [
    {
      key: 'templates',
      label: '模板管理',
      children: (
        <>
          <div style={{ marginBottom: 16 }}>
            <Space>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => {
                setEditingTemplate(null);
                templateForm.resetFields();
                setTemplateModalVisible(true);
              }}>新增模板</Button>
              <Button icon={<ReloadOutlined />} onClick={loadTemplates}>刷新</Button>
            </Space>
          </div>
          <Table columns={templateColumns} dataSource={templates} rowKey="id" loading={loadingTemplates} />
        </>
      ),
    },
    {
      key: 'scheduled',
      label: '定时订阅',
      children: (
        <>
          <div style={{ marginBottom: 16 }}>
            <Space>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => {
                scheduleForm.resetFields();
                setScheduleModalVisible(true);
              }}>新增订阅</Button>
              <Button icon={<ReloadOutlined />} onClick={loadScheduled}>刷新</Button>
            </Space>
          </div>
          <Table columns={scheduleColumns} dataSource={scheduled} rowKey="id" loading={loadingScheduled} />
        </>
      ),
    },
  ];

  return (
    <div>
      <Card>
        <Tabs items={tabItems} />
      </Card>

      <Modal
        title={editingTemplate ? '编辑模板' : '新增模板'}
        open={templateModalVisible}
        onOk={handleTemplateModalOk}
        onCancel={() => setTemplateModalVisible(false)}
        destroyOnClose
      >
        <Form form={templateForm} layout="vertical">
          <Form.Item name="name" label="模板名称" rules={[{ required: true, message: '请输入模板名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="type" label="类型" rules={[{ required: true, message: '请选择类型' }]}>
            <Select options={[
              { label: '销售报表', value: 'sales' },
              { label: '库存报表', value: 'inventory' },
              { label: '财务报表', value: 'finance' },
              { label: '用户报表', value: 'users' },
            ]} />
          </Form.Item>
          <Form.Item name="format" label="格式" rules={[{ required: true, message: '请选择格式' }]}>
            <Select options={[
              { label: 'Excel (xlsx)', value: 'xlsx' },
              { label: 'CSV', value: 'csv' },
              { label: 'PDF', value: 'pdf' },
            ]} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="新增定时订阅"
        open={scheduleModalVisible}
        onOk={handleScheduleModalOk}
        onCancel={() => setScheduleModalVisible(false)}
        destroyOnClose
      >
        <Form form={scheduleForm} layout="vertical">
          <Form.Item name="template_id" label="报表模板" rules={[{ required: true, message: '请选择模板' }]}>
            <Select options={templates.map(t => ({ label: t.name, value: t.id }))} />
          </Form.Item>
          <Form.Item name="cron_expression" label="Cron 表达式" rules={[{ required: true, message: '请输入 Cron 表达式' }]}
            extra="例：0 9 * * 1 表示每周一早上9点">
            <Input placeholder="0 9 * * 1" />
          </Form.Item>
          <Form.Item name="recipients" label="收件人邮箱" rules={[{ required: true, message: '请输入收件人' }]}
            extra="多个邮箱用逗号分隔">
            <Input placeholder="a@example.com,b@example.com" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ReportTemplates;
