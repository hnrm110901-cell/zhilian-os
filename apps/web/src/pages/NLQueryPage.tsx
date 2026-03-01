import React, { useState } from 'react';
import {
  Card, Input, Button, Space, Typography, Table, Tag, Divider, Alert
} from 'antd';
import { SearchOutlined, BulbOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { TextArea } = Input;
const { Title, Text, Paragraph } = Typography;

const EXAMPLE_QUESTIONS = [
  '哪个门店的废料率最高？根因是什么？',
  '最近发生了哪些损耗事件？涉及哪些员工？',
  '哪些食材的库存快照异常？',
  '哪些员工需要培训？培训模块是什么？',
  '某菜品的 BOM 食材用量是多少？',
];

// 实际 API 响应结构 { question, answer, trace: {intent, cypher, params, ...}, data, data_count }
interface TraceInfo {
  intent?: string;
  cypher?: string;
  query?: string;
  service?: string;
  params?: Record<string, any>;
}

interface QueryResult {
  question?: string;
  answer?: string;
  trace?: TraceInfo;
  data?: any[];
  data_count?: number;
  error?: string;
}

const NLQueryPage: React.FC = () => {
  const [question, setQuestion] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [storeId, setStoreId] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<QueryResult | null>(null);

  const handleQuery = async () => {
    if (!question.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await apiClient.post('/api/v1/ontology/query', {
        question: question.trim(),
        tenant_id: tenantId || '',
        store_id: storeId || undefined,
      });
      setResult(res.data);
    } catch (err: any) {
      handleApiError(err, '查询失败');
    } finally {
      setLoading(false);
    }
  };

  const renderDataTable = (data: any[]) => {
    if (!data || data.length === 0) return null;
    const cols = Object.keys(data[0]).map((key) => ({
      title: key,
      dataIndex: key,
      key,
      render: (val: any) => {
        if (val === null || val === undefined) return <Text type="secondary">—</Text>;
        if (typeof val === 'object') return <Text code>{JSON.stringify(val)}</Text>;
        return String(val);
      },
    }));
    return (
      <Table
        dataSource={data.map((row, i) => ({ ...row, _key: i }))}
        columns={cols}
        rowKey="_key"
        size="small"
        scroll={{ x: true }}
        pagination={{ pageSize: 10 }}
        style={{ marginTop: 12 }}
      />
    );
  };

  const intent = result?.trace?.intent;
  const cypher = result?.trace?.cypher;

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: '24px 0' }}>
      <Title level={3}>
        <BulbOutlined style={{ marginRight: 8 }} />
        智链OS 自然语言图谱查询
      </Title>
      <Paragraph type="secondary">
        用自然语言提问，系统自动翻译为 Cypher 查询本体图谱，返回带溯源的结构化答案。
      </Paragraph>

      <Card title="提问" bordered={false}>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Space wrap>
            <div>
              <Text type="secondary" style={{ marginRight: 4 }}>租户 ID：</Text>
              <Input
                placeholder="tenant_id（可选）"
                value={tenantId}
                onChange={(e) => setTenantId(e.target.value)}
                style={{ width: 160 }}
                allowClear
              />
            </div>
            <div>
              <Text type="secondary" style={{ marginRight: 4 }}>门店 ID：</Text>
              <Input
                placeholder="store_id（可选）"
                value={storeId}
                onChange={(e) => setStoreId(e.target.value)}
                style={{ width: 160 }}
                allowClear
              />
            </div>
          </Space>

          <TextArea
            rows={4}
            placeholder="请输入问题，例如：哪个门店的废料率最高？（Ctrl+Enter 提交）"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') handleQuery();
            }}
          />

          <Space wrap>
            <Button
              type="primary"
              icon={<SearchOutlined />}
              onClick={handleQuery}
              loading={loading}
              disabled={!question.trim()}
            >
              查询（Ctrl+Enter）
            </Button>
            <Text type="secondary">示例：</Text>
            {EXAMPLE_QUESTIONS.map((q, i) => (
              <Tag
                key={i}
                style={{ cursor: 'pointer' }}
                onClick={() => setQuestion(q)}
              >
                {q}
              </Tag>
            ))}
          </Space>
        </Space>
      </Card>

      {result && (
        <Card title="查询结果" bordered={false} style={{ marginTop: 16 }}>
          {result.error ? (
            <Alert type="error" message={result.error} showIcon />
          ) : (
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              {intent && (
                <div>
                  <Text type="secondary">识别意图：</Text>
                  <Tag color="blue">{intent}</Tag>
                  {result.trace?.query && (
                    <Tag color="geekblue">{result.trace.query}</Tag>
                  )}
                </div>
              )}

              {result.answer && (
                <div>
                  <Text strong>答案：</Text>
                  <Paragraph style={{ marginTop: 4, background: '#f6ffed', padding: '12px 16px', borderRadius: 4 }}>
                    {result.answer}
                  </Paragraph>
                </div>
              )}

              {result.data && result.data.length > 0 && (
                <div>
                  <Text strong>
                    数据明细（{result.data_count ?? result.data.length} 条，展示前 {result.data.length} 条）：
                  </Text>
                  {renderDataTable(result.data)}
                </div>
              )}

              {cypher && (
                <div>
                  <Divider plain>生成的 Cypher 查询</Divider>
                  <pre style={{
                    background: '#1e1e1e', color: '#d4d4d4',
                    padding: 12, borderRadius: 4,
                    fontSize: 12, overflowX: 'auto',
                  }}>
                    {cypher}
                  </pre>
                </div>
              )}

              {result.trace?.params && Object.keys(result.trace.params).length > 0 && (
                <div>
                  <Text type="secondary">解析参数：</Text>
                  <Space wrap style={{ marginTop: 4 }}>
                    {Object.entries(result.trace.params)
                      .filter(([, v]) => v)
                      .map(([k, v]) => (
                        <Tag key={k} color="geekblue">{k}: {String(v)}</Tag>
                      ))}
                  </Space>
                </div>
              )}
            </Space>
          )}
        </Card>
      )}
    </div>
  );
};

export default NLQueryPage;
