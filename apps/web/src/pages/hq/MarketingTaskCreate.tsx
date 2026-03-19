import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Select, message } from 'antd';
import { ZButton, ZCard } from '../../design-system/components';
import { apiClient } from '../../services/api';
import styles from './MarketingTaskCreate.module.css';

const PRESET_OPTIONS = [
  { value: 'birthday_week', label: '近一周生日' },
  { value: 'inactive_30d', label: '30天未消费' },
  { value: 'high_value_vip', label: '高价值VIP' },
  { value: 'new_customer', label: '首单新客' },
  { value: 'declining', label: '消费下降' },
  { value: 'dormant', label: '沉睡会员' },
];

export default function MarketingTaskCreate() {
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [previewCount, setPreviewCount] = useState<number | null>(null);

  const handlePreview = useCallback(async () => {
    const values = form.getFieldsValue();
    try {
      const data = await apiClient.post<{ total_count: number }>(
        '/api/v1/hq/marketing-tasks/audience-preview',
        {
          audience_type: 'preset',
          audience_config: { preset_id: values.preset_id },
          store_ids: [],
        },
      );
      setPreviewCount(data.total_count);
    } catch {
      message.error('预览失败');
    }
  }, [form]);

  const handleSubmit = useCallback(async () => {
    const values = await form.validateFields();
    setSubmitting(true);
    try {
      await apiClient.post('/api/v1/hq/marketing-tasks', {
        title: values.title,
        audience_type: 'preset',
        audience_config: { preset_id: values.preset_id },
        script_template: values.script_template || '',
        description: values.description || '',
      });
      message.success('任务创建成功');
      navigate('/hq/marketing-tasks');
    } catch {
      message.error('创建失败');
    } finally {
      setSubmitting(false);
    }
  }, [form, navigate]);

  return (
    <div className={styles.page}>
      <h2>创建营销任务</h2>
      <ZCard>
        <Form form={form} layout="vertical" style={{ maxWidth: 600 }}>
          <Form.Item name="title" label="任务名称" rules={[{ required: true }]}>
            <Input placeholder="例：本周生日关怀" />
          </Form.Item>
          <Form.Item name="preset_id" label="目标人群" rules={[{ required: true }]}>
            <Select options={PRESET_OPTIONS} placeholder="选择预设人群包" />
          </Form.Item>
          {previewCount !== null && (
            <div className={styles.preview}>匹配人数: <strong>{previewCount}</strong></div>
          )}
          <ZButton variant="secondary" onClick={handlePreview}>预览人群</ZButton>
          <Form.Item name="script_template" label="话术模板" style={{ marginTop: 16 }}>
            <Input.TextArea rows={3} placeholder="可选，发送给员工的话术参考" />
          </Form.Item>
          <Form.Item name="description" label="任务说明">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item>
            <ZButton variant="primary" onClick={handleSubmit} disabled={submitting}>
              创建任务
            </ZButton>
          </Form.Item>
        </Form>
      </ZCard>
    </div>
  );
}
