import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Tag, Space, Tabs, Form, Input, Select, Statistic, Row, Col, Alert } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Option } = Select;

const NeuralSystemPage: React.FC = () => {
  const [status, setStatus] = useState<any>(null);
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [searchType, setSearchType] = useState<'orders' | 'dishes' | 'events'>('dishes');
  const [searchForm] = Form.useForm();

  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/neural/status');
      setStatus(res.data);
    } catch (err: any) {
      handleApiError(err, '加载神经系统状态失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  const semanticSearch = async (values: any) => {
    setSearching(true);
    setSearchResults([]);
    try {
      const res = await apiClient.post(`/neural/search/${searchType}`, {
        query: values.query,
        top_k: values.top_k || 5,
      });
      setSearchResults(res.data?.results || res.data || []);
    } catch (err: any) {
      handleApiError(err, '语义搜索失败');
    } finally {
      setSearching(false);
    }
  };

  const resultColumns: ColumnsType<any> = [
    { title: '内容', dataIndex: 'content', key: 'content', ellipsis: true, render: (v: any) => typeof v === 'object' ? JSON.stringify(v) : String(v || '-') },
    { title: '相似度', dataIndex: 'score', key: 'score', render: (v: number) => v != null ? `${(v * 100).toFixed(1)}%` : '-' },
    { title: 'ID', dataIndex: 'id', key: 'id', render: (v: string) => v || '-' },
  ];

  const tabItems = [
    {
      key: 'status',
      label: '系统状态',
      children: (
        <Card loading={loading}>
          {status ? (
            <div>
              <Row gutter={16} style={{ marginBottom: 16 }}>
                <Col span={6}><Statistic title="向量索引数量" value={status.vector_index_count || 0} /></Col>
                <Col span={6}><Statistic title="事件总数" value={status.event_count || 0} /></Col>
                <Col span={6}><Statistic title="联邦学习参与方" value={status.federated_participants || 0} /></Col>
                <Col span={6}>
                  <Statistic title="系统状态" valueRender={() => (
                    <Tag color={status.healthy ? 'green' : 'red'}>{status.healthy ? '健康' : '异常'}</Tag>
                  )} value="" />
                </Col>
              </Row>
              {status.components && (
                <Card title="组件状态" size="small">
                  {Object.entries(status.components).map(([key, val]: [string, any]) => (
                    <Space key={key} style={{ marginRight: 16 }}>
                      <Tag color={val?.healthy || val === 'ok' ? 'green' : 'red'}>{key}</Tag>
                    </Space>
                  ))}
                </Card>
              )}
            </div>
          ) : <Alert message="暂无状态数据" type="warning" />}
        </Card>
      ),
    },
    {
      key: 'search',
      label: '语义搜索',
      children: (
        <Card>
          <Form form={searchForm} layout="inline" onFinish={semanticSearch} style={{ marginBottom: 16 }}>
            <Form.Item name="query" rules={[{ required: true }]}>
              <Input placeholder="输入搜索内容..." style={{ width: 300 }} />
            </Form.Item>
            <Form.Item>
              <Select value={searchType} onChange={setSearchType} style={{ width: 120 }}>
                <Option value="dishes">菜品</Option>
                <Option value="orders">订单</Option>
                <Option value="events">事件</Option>
              </Select>
            </Form.Item>
            <Form.Item name="top_k" initialValue={5}>
              <Input type="number" min={1} max={20} style={{ width: 80 }} placeholder="Top K" />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" icon={<SearchOutlined />} loading={searching}>搜索</Button>
            </Form.Item>
          </Form>
          <Table columns={resultColumns} dataSource={searchResults} rowKey={(r, i) => r.id || String(i)} />
        </Card>
      ),
    },
  ];

  return <Tabs items={tabItems} />;
};

export default NeuralSystemPage;
