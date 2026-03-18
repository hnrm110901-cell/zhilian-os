import React, { useState } from 'react';
import { Alert, Button, Card, Col, Form, Input, InputNumber, Row, Space, Typography } from 'antd';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Title, Paragraph } = Typography;
const { TextArea } = Input;

const OntologyGraphPage: React.FC = () => {
  const [storeId, setStoreId] = useState(localStorage.getItem('store_id') || '');
  const [dishId, setDishId] = useState('D001');
  const [question, setQuestion] = useState('本周损耗最高的菜品是什么？');
  const [limit, setLimit] = useState(20);
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
      <Title level={4}>本体图谱查询台</Title>
      <Paragraph type="secondary">
        提供门店图谱摘要、菜品 BOM 查询、自然语言到 Cypher 查询能力。
      </Paragraph>

      {error && <Alert style={{ marginBottom: 16 }} type="error" message={error} showIcon />}

      <Row gutter={16}>
        <Col span={8}>
          <Card title="门店图谱摘要">
            <Form layout="vertical">
              <Form.Item label="门店ID">
                <Input value={storeId} onChange={(e) => setStoreId(e.target.value)} />
              </Form.Item>
              <Button
                type="primary"
                loading={loading}
                onClick={() => run(() => apiClient.get(`/api/v1/ontology/store/${storeId}/summary`))}
              >
                查询摘要
              </Button>
            </Form>
          </Card>
        </Col>
        <Col span={8}>
          <Card title="菜品 BOM">
            <Form layout="vertical">
              <Form.Item label="菜品ID">
                <Input value={dishId} onChange={(e) => setDishId(e.target.value)} />
              </Form.Item>
              <Space>
                <Button
                  type="primary"
                  loading={loading}
                  onClick={() => run(() => apiClient.get(`/api/v1/ontology/dish/${dishId}/bom`))}
                >
                  查询 BOM
                </Button>
                <Button
                  loading={loading}
                  onClick={() => run(() => apiClient.get(`/api/v1/ontology/dish/${dishId}/waste?limit=20`))}
                >
                  查询损耗
                </Button>
              </Space>
            </Form>
          </Card>
        </Col>
        <Col span={8}>
          <Card title="自然语言查询">
            <Form layout="vertical">
              <Form.Item label="问题">
                <TextArea rows={3} value={question} onChange={(e) => setQuestion(e.target.value)} />
              </Form.Item>
              <Form.Item label="返回条数">
                <InputNumber min={1} max={100} value={limit} onChange={(v) => setLimit(v || 20)} style={{ width: '100%' }} />
              </Form.Item>
              <Button
                type="primary"
                loading={loading}
                onClick={() =>
                  run(() =>
                    apiClient.post('/api/v1/ontology/query/natural', {
                      question,
                      store_id: storeId,
                      limit,
                    })
                  )
                }
              >
                执行查询
              </Button>
            </Form>
          </Card>
        </Col>
      </Row>

      <Card title="返回结果" style={{ marginTop: 16 }}>
        <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
          {JSON.stringify(result, null, 2)}
        </pre>
      </Card>
    </div>
  );
};

export default OntologyGraphPage;
