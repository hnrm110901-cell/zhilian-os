/**
 * 业务规则配置页面
 * 路由: /business-rules
 * 功能: 管理考勤扣款/工龄补贴/加班倍数等可配置规则
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Card, Table, Tag, Button, Tabs, Modal, Form, Input, InputNumber,
  Select, Space, message, Typography, Popconfirm, Tooltip, Switch,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ThunderboltOutlined,
  SettingOutlined, EyeOutlined,
} from '@ant-design/icons';
import { hrService } from '../../services/hrService';
import type { BusinessRuleItem } from '../../services/hrService';

const { Title, Text } = Typography;
const { TextArea } = Input;

const BRAND_ID = localStorage.getItem('brand_id') || '';

const CATEGORY_LABELS: Record<string, string> = {
  attendance_penalty: '迟到扣款',
  absence_penalty: '缺勤扣款',
  seniority_subsidy: '工龄补贴',
  overtime_multiplier: '加班倍数',
  full_attendance: '全勤奖',
  meal_subsidy: '餐补',
  position_allowance: '岗位津贴',
};

const CATEGORY_KEYS = Object.keys(CATEGORY_LABELS);

const BusinessRulesPage: React.FC = () => {
  const [activeCategory, setActiveCategory] = useState(CATEGORY_KEYS[0]);
  const [items, setItems] = useState<BusinessRuleItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [editModal, setEditModal] = useState(false);
  const [editItem, setEditItem] = useState<BusinessRuleItem | null>(null);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [previewModal, setPreviewModal] = useState(false);
  const [previewData, setPreviewData] = useState<Record<string, unknown> | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await hrService.getBusinessRules(BRAND_ID, activeCategory);
      setItems(res.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, [activeCategory]);

  useEffect(() => { load(); }, [load]);

  const openEdit = (item?: BusinessRuleItem) => {
    setEditItem(item || null);
    if (item) {
      form.setFieldsValue({
        rule_name: item.rule_name,
        rules_json: JSON.stringify(item.rules_json, null, 2),
        priority: item.priority,
        is_active: item.is_active,
        description: item.description,
        store_id: item.store_id || '',
        position: item.position || '',
        employment_type: item.employment_type || '',
      });
    } else {
      form.resetFields();
      form.setFieldsValue({ priority: 0, is_active: true });
    }
    setEditModal(true);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      let rulesJson: Record<string, unknown>;
      try {
        rulesJson = JSON.parse(values.rules_json);
      } catch {
        message.error('规则JSON格式错误');
        return;
      }

      setSubmitting(true);
      const payload = {
        brand_id: BRAND_ID,
        category: activeCategory,
        rule_name: values.rule_name,
        rules_json: rulesJson,
        priority: values.priority || 0,
        is_active: values.is_active,
        description: values.description || '',
        store_id: values.store_id || null,
        position: values.position || null,
        employment_type: values.employment_type || null,
      };

      if (editItem) {
        await hrService.updateBusinessRule(editItem.id, {
          rule_name: values.rule_name,
          rules_json: rulesJson,
          priority: values.priority,
          is_active: values.is_active,
          description: values.description,
        });
        message.success('规则已更新');
      } else {
        await hrService.createBusinessRule(payload);
        message.success('规则已创建');
      }
      setEditModal(false);
      load();
    } catch {
      message.error('保存失败');
    }
    setSubmitting(false);
  };

  const handleDelete = async (id: string) => {
    try {
      await hrService.deleteBusinessRule(id);
      message.success('规则已删除');
      load();
    } catch {
      message.error('删除失败');
    }
  };

  const handlePreview = async (item: BusinessRuleItem) => {
    try {
      const res = await hrService.previewPayrollImpact(
        BRAND_ID,
        item.store_id || '',
        item.category,
        item.rules_json,
      );
      setPreviewData(res);
      setPreviewModal(true);
    } catch {
      message.error('预览失败');
    }
  };

  const handleSeedDefaults = async () => {
    try {
      const res = await hrService.seedDefaultRules(BRAND_ID);
      message.success(`已初始化 ${res.seeded_count} 条默认规则`);
      load();
    } catch {
      message.error('初始化失败');
    }
  };

  const getScopeText = (item: BusinessRuleItem) => {
    const parts: string[] = [];
    if (item.store_id) parts.push(`门店:${item.store_id}`);
    else parts.push('品牌级');
    if (item.position) parts.push(`岗位:${item.position}`);
    if (item.employment_type) parts.push(`用工:${item.employment_type}`);
    return parts.join(' | ');
  };

  const columns = [
    { title: '规则名称', dataIndex: 'rule_name', key: 'rule_name', width: 160 },
    {
      title: '适用范围', key: 'scope', width: 200,
      render: (_: unknown, record: BusinessRuleItem) => (
        <Text type={record.store_id ? undefined : 'secondary'}>{getScopeText(record)}</Text>
      ),
    },
    {
      title: '规则预览', dataIndex: 'rules_json', key: 'rules_json', ellipsis: true,
      render: (v: Record<string, unknown>) => (
        <Tooltip title={JSON.stringify(v, null, 2)}>
          <Text code style={{ maxWidth: 200, display: 'inline-block' }}>
            {JSON.stringify(v).slice(0, 60)}{JSON.stringify(v).length > 60 ? '...' : ''}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: '优先级', dataIndex: 'priority', key: 'priority', width: 80,
      sorter: (a: BusinessRuleItem, b: BusinessRuleItem) => b.priority - a.priority,
    },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80,
      render: (v: boolean) => v ? <Tag color="success">启用</Tag> : <Tag color="default">禁用</Tag>,
    },
    {
      title: '操作', key: 'actions', width: 220,
      render: (_: unknown, record: BusinessRuleItem) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
          <Button size="small" icon={<EyeOutlined />} onClick={() => handlePreview(record)}>影响预览</Button>
          <Popconfirm title="确认删除此规则？" onConfirm={() => handleDelete(record.id)} okText="确认" cancelText="取消">
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>
          <SettingOutlined style={{ marginRight: 8 }} />
          业务规则配置
        </Title>
        <Space>
          <Button onClick={handleSeedDefaults}>初始化默认规则</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit()}>
            新建规则
          </Button>
        </Space>
      </div>

      <Card bordered={false}>
        <Tabs
          activeKey={activeCategory}
          onChange={setActiveCategory}
          items={CATEGORY_KEYS.map(k => ({
            key: k,
            label: CATEGORY_LABELS[k],
          }))}
        />

        <div style={{ marginBottom: 12 }}>
          <Text type="secondary">
            规则继承逻辑：门店级覆盖品牌级，岗位级覆盖通用级，优先级越高越优先生效。
          </Text>
        </div>

        <Table
          rowKey="id"
          columns={columns}
          dataSource={items}
          loading={loading}
          pagination={false}
          locale={{ emptyText: `暂无${CATEGORY_LABELS[activeCategory]}规则` }}
        />
      </Card>

      {/* 编辑/创建 Modal */}
      <Modal
        title={editItem ? '编辑规则' : '新建规则'}
        open={editModal}
        onOk={handleSave}
        onCancel={() => setEditModal(false)}
        confirmLoading={submitting}
        okText="保存"
        width={600}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="rule_name" label="规则名称" rules={[{ required: true, message: '请输入规则名称' }]}>
            <Input placeholder="如：迟到扣款-标准" />
          </Form.Item>
          <Form.Item name="store_id" label="门店ID（留空为品牌级）">
            <Input placeholder="留空=品牌级默认" />
          </Form.Item>
          <Form.Item name="position" label="岗位（留空为通用）">
            <Input placeholder="如：服务员" />
          </Form.Item>
          <Form.Item name="employment_type" label="用工类型（留空为通用）">
            <Select allowClear placeholder="选择用工类型" options={[
              { label: '全职', value: 'full_time' },
              { label: '兼职', value: 'part_time' },
              { label: '小时工', value: 'hourly' },
              { label: '实习', value: 'intern' },
            ]} />
          </Form.Item>
          <Form.Item name="rules_json" label="规则JSON" rules={[{ required: true, message: '请输入规则配置' }]}>
            <TextArea rows={6} placeholder='{"late_per_time_fen": 5000, "max_monthly_fen": 50000}' />
          </Form.Item>
          <Form.Item name="priority" label="优先级">
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input placeholder="规则用途说明" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 影响预览 Modal */}
      <Modal
        title="薪酬影响预览"
        open={previewModal}
        onCancel={() => setPreviewModal(false)}
        footer={<Button onClick={() => setPreviewModal(false)}>关闭</Button>}
        width={500}
      >
        {previewData && (
          <div>
            <p><strong>类别：</strong>{CATEGORY_LABELS[(previewData as Record<string, unknown>).category as string] || (previewData as Record<string, unknown>).category as string}</p>
            <p><strong>影响说明：</strong>{(previewData as Record<string, unknown>).impact_description as string}</p>
            <p>
              <strong>预估月度差异：</strong>
              <Text type={((previewData as Record<string, unknown>).estimated_monthly_diff_fen as number) > 0 ? 'danger' : 'success'}>
                {((previewData as Record<string, unknown>).estimated_monthly_diff_fen as number) > 0 ? '+' : ''}
                ¥{(((previewData as Record<string, unknown>).estimated_monthly_diff_fen as number) / 100).toFixed(2)}
              </Text>
            </p>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default BusinessRulesPage;
