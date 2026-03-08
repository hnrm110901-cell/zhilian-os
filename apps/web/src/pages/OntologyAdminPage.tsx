import React, { useState } from 'react';
import { Alert, Button, Card, Form, Input, Space, Typography } from 'antd';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Title, Paragraph } = Typography;

const OntologyAdminPage: React.FC = () => {
  const [eventId, setEventId] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');

  const run = async (fn: () => Promise<any>) => {
    setLoading(true);
    setError('');
    try {
      const res = await fn();
      setResult(res);
    } catch (err: any) {
      handleApiError(err, '请求失败');
      setError(err?.response?.data?.detail || err?.response?.data?.message || err?.message || '请求失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Title level={4}>本体管理台</Title>
      <Paragraph type="secondary">
        管理员可在此触发损耗推理、查看证据链，验证本体层闭环状态。
      </Paragraph>

      {error && <Alert style={{ marginBottom: 16 }} type="error" message={error} showIcon />}

      <Card title="损耗事件推理">
        <Form layout="vertical">
          <Form.Item label="损耗事件ID">
            <Input value={eventId} onChange={(e) => setEventId(e.target.value)} placeholder="如 WASTE_EVENT_001" />
          </Form.Item>
          <Space>
            <Button
              type="primary"
              loading={loading}
              disabled={!eventId}
              onClick={() => run(() => apiClient.post(`/api/v1/ontology/waste/${eventId}/infer`))}
            >
              触发推理
            </Button>
            <Button
              loading={loading}
              disabled={!eventId}
              onClick={() => run(() => apiClient.get(`/api/v1/ontology/waste/${eventId}/explain`))}
            >
              查看证据链
            </Button>
          </Space>
        </Form>
      </Card>

      <Card title="返回结果" style={{ marginTop: 16 }}>
        <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
          {JSON.stringify(result, null, 2)}
        </pre>
      </Card>
    </div>
  );
};

export default OntologyAdminPage;
