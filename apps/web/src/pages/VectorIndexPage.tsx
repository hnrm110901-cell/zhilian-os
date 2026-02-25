import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Tag, Space, Form, Input, Select, InputNumber, Tabs, Alert } from 'antd';
import { SearchOutlined, PlusOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;
const { TextArea } = Input;

const DOMAINS = ['revenue', 'inventory', 'menu', 'events'];

const VectorIndexPage: React.FC = () => {
  const [selectedStore, setSelectedStore] = useState('STORE001');
  const [collections, setCollections] = useState<any[]>([]);
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [multiResults, setMultiResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [indexLoading, setIndexLoading] = useState(false);
  const [searchForm] = Form.useForm();
  const [multiSearchForm] = Form.useForm();
  const [indexForm] = Form.useForm();

  const loadCollections = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get(`/vector/collections/${selectedStore}`);
      setCollections(res.data?.collections || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载集合失败');
    } finally {
      setLoading(false);
    }
  }, [selectedStore]);

  useEffect(() => { loadCollections(); }, [loadCollections]);

  const singleSearch = async (values: any) => {
    setSearchLoading(true);
    try {
      const res = await apiClient.get(`/vector/search/${selectedStore}`, {
        params: { query: values.query, domain: values.domain, top_k: values.top_k || 5, score_threshold: values.score_threshold || 0 },
      });
      setSearchResults(res.data?.results || res.data || []);
    } catch (err: any) {
      handleApiError(err, '搜索失败');
    } finally {
      setSearchLoading(false);
    }
  };

  const multiSearch = async (values: any) => {
    setSearchLoading(true);
    try {
      const res = await apiClient.get(`/vector/search-multi/${selectedStore}`, {
        params: { query: values.query, domains: values.domains?.join(',') || DOMAINS.join(','), top_k_per_domain: values.top_k_per_domain || 3 },
      });
      const flat: any[] = [];
      const data = res.data?.results || res.data || {};
      Object.entries(data).forEach(([domain, items]: [string, any]) => {
        (items || []).forEach((item: any) => flat.push({ ...item, domain }));
      });
      setMultiResults(flat);
    } catch (err: any) {
      handleApiError(err, '多域搜索失败');
    } finally {
      setSearchLoading(false);
    }
  };

  const indexDocument = async (values: any) => {
    setIndexLoading(true);
    try {
      await apiClient.post('/vector/index', { ...values, store_id: selectedStore, payload: {} });
      showSuccess('文档已索引');
      indexForm.resetFields();
      loadCollections();
    } catch (err: any) {
      handleApiError(err, '索引失败');
    } finally {
      setIndexLoading(false);
    }
  };

  const resultColumns = [
    { title: '文档ID', dataIndex: 'doc_id', key: 'doc_id', ellipsis: true },
    { title: '内容', dataIndex: 'text', key: 'text', ellipsis: true },
    { title: '相似度', dataIndex: 'score', key: 'score', width: 90, render: (v: number) => v != null ? v.toFixed(3) : '-' },
  ];

  const multiResultColumns = [
    { title: '域', dataIndex: 'domain', key: 'domain', width: 100, render: (v: string) => <Tag>{v}</Tag> },
    ...resultColumns,
  ];

  const tabItems = [
    {
      key: 'search', label: '单域搜索',
      children: (
        <div>
          <Form form={searchForm} layout="inline" onFinish={singleSearch} style={{ marginBottom: 16 }}>
            <Form.Item name="query" rules={[{ required: true }]}><Input placeholder="搜索内容" style={{ width: 240 }} /></Form.Item>
            <Form.Item name="domain" initialValue="events">
              <Select style={{ width: 120 }}>
                {DOMAINS.map(d => <Option key={d} value={d}>{d}</Option>)}
              </Select>
            </Form.Item>
            <Form.Item name="top_k" initialValue={5}><InputNumber min={1} max={20} addonBefore="Top" style={{ width: 100 }} /></Form.Item>
            <Form.Item><Button type="primary" htmlType="submit" icon={<SearchOutlined />} loading={searchLoading}>搜索</Button></Form.Item>
          </Form>
          <Table columns={resultColumns} dataSource={searchResults} rowKey={(r, i) => r.doc_id || String(i)} pagination={false} />
        </div>
      ),
    },
    {
      key: 'multi', label: '多域搜索',
      children: (
        <div>
          <Form form={multiSearchForm} layout="inline" onFinish={multiSearch} style={{ marginBottom: 16 }}>
            <Form.Item name="query" rules={[{ required: true }]}><Input placeholder="搜索内容" style={{ width: 240 }} /></Form.Item>
            <Form.Item name="domains" initialValue={DOMAINS}>
              <Select mode="multiple" style={{ width: 280 }} placeholder="选择域">
                {DOMAINS.map(d => <Option key={d} value={d}>{d}</Option>)}
              </Select>
            </Form.Item>
            <Form.Item><Button type="primary" htmlType="submit" icon={<SearchOutlined />} loading={searchLoading}>搜索</Button></Form.Item>
          </Form>
          <Table columns={multiResultColumns} dataSource={multiResults} rowKey={(r, i) => `${r.domain}-${r.doc_id || i}`} pagination={false} />
        </div>
      ),
    },
    {
      key: 'index', label: '索引文档',
      children: (
        <Form form={indexForm} layout="vertical" onFinish={indexDocument} style={{ maxWidth: 600 }}>
          <Alert message="手动将文档索引到向量知识库，供语义搜索使用" type="info" style={{ marginBottom: 16 }} />
          <Form.Item name="domain" label="域" rules={[{ required: true }]}>
            <Select>{DOMAINS.map(d => <Option key={d} value={d}>{d}</Option>)}</Select>
          </Form.Item>
          <Form.Item name="doc_id" label="文档ID" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="text" label="文档内容" rules={[{ required: true }]}><TextArea rows={4} /></Form.Item>
          <Form.Item><Button type="primary" htmlType="submit" icon={<PlusOutlined />} loading={indexLoading}>索引</Button></Form.Item>
        </Form>
      ),
    },
    {
      key: 'collections', label: '集合列表',
      children: (
        <Table
          columns={[
            { title: '域', dataIndex: 'domain', key: 'domain', render: (v: string) => <Tag>{v}</Tag> },
            { title: '文档数', dataIndex: 'count', key: 'count' },
            { title: '最后更新', dataIndex: 'updated_at', key: 'updated_at', ellipsis: true },
          ]}
          dataSource={collections}
          rowKey={(r, i) => r.domain || String(i)}
          loading={loading}
          pagination={false}
        />
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Space>
          <span>门店：</span>
          <Select value={selectedStore} onChange={setSelectedStore} style={{ width: 160 }}>
            <Option value="STORE001">STORE001</Option>
          </Select>
        </Space>
      </div>
      <Card><Tabs items={tabItems} /></Card>
    </div>
  );
};

export default VectorIndexPage;
