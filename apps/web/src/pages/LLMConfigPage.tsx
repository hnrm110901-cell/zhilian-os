import React, { useState, useCallback, useEffect } from 'react';
import { Card, Form, Input, Select, Button, Descriptions, Tag, Alert, Space, Divider } from 'antd';
import { SaveOutlined, ExperimentOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;
const { TextArea } = Input;

const LLMConfigPage: React.FC = () => {
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  const [form] = Form.useForm();
  const [testForm] = Form.useForm();

  const loadConfig = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/llm/config');
      setConfig(res.data);
      form.setFieldsValue(res.data);
    } catch (err: any) {
      handleApiError(err, '加载LLM配置失败');
    } finally {
      setLoading(false);
    }
  }, [form]);

  useEffect(() => { loadConfig(); }, [loadConfig]);

  const saveConfig = async (values: any) => {
    setSaving(true);
    try {
      await apiClient.put('/llm/config', values);
      showSuccess('配置保存成功');
      loadConfig();
    } catch (err: any) {
      handleApiError(err, '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const testLLM = async (values: any) => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await apiClient.post('/llm/test', values);
      setTestResult(res.data);
    } catch (err: any) {
      handleApiError(err, '测试失败');
    } finally {
      setTesting(false);
    }
  };

  return (
    <div>
      <Card title="LLM 配置" loading={loading} style={{ marginBottom: 16 }}>
        <Form form={form} layout="vertical" onFinish={saveConfig}>
          <Form.Item name="provider" label="模型提供商" rules={[{ required: true }]}>
            <Select>
              <Option value="openai">OpenAI</Option>
              <Option value="anthropic">Anthropic</Option>
              <Option value="azure">Azure OpenAI</Option>
              <Option value="local">本地模型</Option>
            </Select>
          </Form.Item>
          <Form.Item name="model" label="模型名称" rules={[{ required: true }]}>
            <Input placeholder="如 gpt-4, claude-3-sonnet" />
          </Form.Item>
          <Form.Item name="api_key" label="API Key">
            <Input.Password placeholder="输入API Key（留空保持不变）" />
          </Form.Item>
          <Form.Item name="base_url" label="Base URL">
            <Input placeholder="自定义API地址（可选）" />
          </Form.Item>
          <Form.Item name="max_tokens" label="最大Token数">
            <Input type="number" min={1} max={32000} />
          </Form.Item>
          <Form.Item name="temperature" label="Temperature">
            <Input type="number" min={0} max={2} step={0.1} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saving}>保存配置</Button>
          </Form.Item>
        </Form>

        {config && (
          <>
            <Divider />
            <Descriptions title="当前配置" bordered column={2} size="small">
              <Descriptions.Item label="提供商"><Tag>{config.provider || '-'}</Tag></Descriptions.Item>
              <Descriptions.Item label="模型">{config.model || '-'}</Descriptions.Item>
              <Descriptions.Item label="最大Token">{config.max_tokens || '-'}</Descriptions.Item>
              <Descriptions.Item label="Temperature">{config.temperature ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={config.enabled ? 'green' : 'red'}>{config.enabled ? '已启用' : '已禁用'}</Tag></Descriptions.Item>
            </Descriptions>
          </>
        )}
      </Card>

      <Card title="LLM 测试">
        <Form form={testForm} layout="vertical" onFinish={testLLM}>
          <Form.Item name="prompt" label="测试提示词" rules={[{ required: true }]}>
            <TextArea rows={3} placeholder="输入测试提示词..." />
          </Form.Item>
          <Form.Item>
            <Button type="default" htmlType="submit" icon={<ExperimentOutlined />} loading={testing}>发送测试</Button>
          </Form.Item>
        </Form>

        {testResult && (
          <Alert
            message="测试结果"
            description={
              <Space direction="vertical" style={{ width: '100%' }}>
                <div><strong>响应：</strong>{testResult.response || testResult.content || JSON.stringify(testResult)}</div>
                {testResult.latency_ms && <div><strong>延迟：</strong>{testResult.latency_ms}ms</div>}
                {testResult.tokens_used && <div><strong>Token用量：</strong>{testResult.tokens_used}</div>}
              </Space>
            }
            type="success"
          />
        )}
      </Card>
    </div>
  );
};

export default LLMConfigPage;
