/**
 * 班次模板管理页面
 * 路由: /shift-templates
 * 功能: 班次模板的查看/创建/管理
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Card, Table, Tag, Button, Modal, Form, Input, InputNumber,
  Select, Space, message, Typography, Switch, TimePicker,
} from 'antd';
import {
  PlusOutlined, ClockCircleOutlined, ScheduleOutlined,
} from '@ant-design/icons';
import { hrService } from '../../services/hrService';
import type { ShiftTemplateItem } from '../../services/hrService';
import dayjs from 'dayjs';

const { Title, Text } = Typography;

const BRAND_ID = localStorage.getItem('brand_id') || 'BRAND_001';

const ShiftTemplatePage: React.FC = () => {
  const [items, setItems] = useState<ShiftTemplateItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await hrService.getShiftTemplates(BRAND_ID);
      setItems(res.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      await hrService.createShiftTemplate({
        brand_id: BRAND_ID,
        store_id: values.store_id || null,
        name: values.name,
        code: values.code,
        start_time: values.start_time.format('HH:mm'),
        end_time: values.end_time.format('HH:mm'),
        is_cross_day: values.is_cross_day || false,
        break_minutes: values.break_minutes || 60,
        min_work_hours: values.min_work_hours || null,
        late_threshold_minutes: values.late_threshold_minutes || 5,
        early_leave_threshold_minutes: values.early_leave_threshold_minutes || 5,
        applicable_positions: values.applicable_positions || [],
        is_active: values.is_active !== false,
        sort_order: values.sort_order || 0,
      });
      message.success('班次模板创建成功');
      setModalOpen(false);
      form.resetFields();
      load();
    } catch {
      message.error('创建失败');
    }
    setSubmitting(false);
  };

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name', width: 120 },
    { title: '编码', dataIndex: 'code', key: 'code', width: 100 },
    {
      title: '时间', key: 'time', width: 150,
      render: (_: unknown, r: ShiftTemplateItem) => (
        <span>
          {r.start_time || '-'} ~ {r.end_time || '-'}
          {r.is_cross_day && <Tag color="orange" style={{ marginLeft: 4 }}>跨天</Tag>}
        </span>
      ),
    },
    {
      title: '休息(分钟)', dataIndex: 'break_minutes', key: 'break_minutes', width: 100,
    },
    {
      title: '迟到阈值', dataIndex: 'late_threshold_minutes', key: 'late_threshold', width: 100,
      render: (v: number) => `${v}分钟`,
    },
    {
      title: '早退阈值', dataIndex: 'early_leave_threshold_minutes', key: 'early_leave', width: 100,
      render: (v: number) => `${v}分钟`,
    },
    {
      title: '适用范围', key: 'scope', width: 150,
      render: (_: unknown, r: ShiftTemplateItem) => (
        <span>
          {r.store_id ? <Tag>{r.store_id}</Tag> : <Tag color="blue">品牌级</Tag>}
        </span>
      ),
    },
    {
      title: '适用岗位', dataIndex: 'applicable_positions', key: 'positions', width: 150,
      render: (v: string[]) => v && v.length > 0 ? v.join(', ') : '全部',
    },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80,
      render: (v: boolean) => v ? <Tag color="success">启用</Tag> : <Tag color="default">禁用</Tag>,
    },
    {
      title: '排序', dataIndex: 'sort_order', key: 'sort_order', width: 70,
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>
        <ScheduleOutlined style={{ marginRight: 8 }} />
        班次模板管理
      </Title>

      <Card bordered={false}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <Text type="secondary">管理各门店的班次时间模板，支持品牌级和门店级配置。</Text>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setModalOpen(true); }}>
            新建班次
          </Button>
        </div>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={items}
          loading={loading}
          pagination={false}
          locale={{ emptyText: '暂无班次模板' }}
          scroll={{ x: 1200 }}
        />
      </Card>

      <Modal
        title="新建班次模板"
        open={modalOpen}
        onOk={handleCreate}
        onCancel={() => setModalOpen(false)}
        confirmLoading={submitting}
        okText="创建"
        width={560}
      >
        <Form form={form} layout="vertical" initialValues={{ break_minutes: 60, late_threshold_minutes: 5, early_leave_threshold_minutes: 5, is_active: true, sort_order: 0 }}>
          <Form.Item name="name" label="班次名称" rules={[{ required: true, message: '请输入班次名称' }]}>
            <Input placeholder="如：早班" />
          </Form.Item>
          <Form.Item name="code" label="班次编码" rules={[{ required: true, message: '请输入班次编码' }]}>
            <Input placeholder="如：morning" />
          </Form.Item>
          <Space size={16} style={{ width: '100%' }}>
            <Form.Item name="start_time" label="开始时间" rules={[{ required: true, message: '请选择' }]}>
              <TimePicker format="HH:mm" />
            </Form.Item>
            <Form.Item name="end_time" label="结束时间" rules={[{ required: true, message: '请选择' }]}>
              <TimePicker format="HH:mm" />
            </Form.Item>
            <Form.Item name="is_cross_day" label="跨天" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Space>
          <Space size={16} style={{ width: '100%' }}>
            <Form.Item name="break_minutes" label="休息时间(分钟)">
              <InputNumber min={0} max={180} style={{ width: 120 }} />
            </Form.Item>
            <Form.Item name="min_work_hours" label="最低工时(小时)">
              <InputNumber min={0} max={24} precision={1} style={{ width: 120 }} />
            </Form.Item>
          </Space>
          <Space size={16} style={{ width: '100%' }}>
            <Form.Item name="late_threshold_minutes" label="迟到阈值(分钟)">
              <InputNumber min={0} max={60} style={{ width: 120 }} />
            </Form.Item>
            <Form.Item name="early_leave_threshold_minutes" label="早退阈值(分钟)">
              <InputNumber min={0} max={60} style={{ width: 120 }} />
            </Form.Item>
          </Space>
          <Form.Item name="store_id" label="门店ID（留空为品牌级）">
            <Input placeholder="留空=品牌级默认" />
          </Form.Item>
          <Form.Item name="applicable_positions" label="适用岗位">
            <Select mode="tags" placeholder="输入岗位名称后回车，留空为全部岗位" />
          </Form.Item>
          <Space size={16}>
            <Form.Item name="is_active" label="启用" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="sort_order" label="排序">
              <InputNumber min={0} style={{ width: 80 }} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
};

export default ShiftTemplatePage;
