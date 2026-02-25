import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Statistic, Space, Button, Form, Select,
  Spin, Typography, Descriptions, Tag, InputNumber, Table
} from 'antd';
import { GlobalOutlined, DollarOutlined, TranslationOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Title, Text } = Typography;
const { Option } = Select;

interface Language { code: string; name: string; native_name: string; enabled: boolean; }
interface Currency { code: string; name: string; symbol: string; rate_to_cny: number; }
interface ConvertResult {
  original_amount: number;
  original_currency: string;
  converted_amount: number;
  converted_currency: string;
}

const I18nPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [languages, setLanguages] = useState<Language[]>([]);
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  const [convertResult, setConvertResult] = useState<ConvertResult | null>(null);
  const [convertForm] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [langRes, currRes] = await Promise.allSettled([
        apiClient.get('/api/v1/i18n/languages'),
        apiClient.get('/api/v1/i18n/currencies'),
      ]);
      if (langRes.status === 'fulfilled') setLanguages(langRes.value.data.languages || []);
      if (currRes.status === 'fulfilled') setCurrencies(currRes.value.data.currencies || []);
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleConvert = async (values: Record<string, unknown>) => {
    setLoading(true);
    try {
      const res = await apiClient.post('/api/v1/i18n/currency/convert', values);
      setConvertResult(res.data);
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  };

  const langColumns = [
    { title: '语言代码', dataIndex: 'code', key: 'code', width: 100 },
    { title: '英文名', dataIndex: 'name', key: 'name' },
    { title: '本地名称', dataIndex: 'native_name', key: 'native_name' },
    {
      title: '状态', dataIndex: 'enabled', key: 'enabled',
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '已启用' : '未启用'}</Tag>,
    },
  ];

  const currColumns = [
    { title: '货币代码', dataIndex: 'code', key: 'code', width: 100 },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '符号', dataIndex: 'symbol', key: 'symbol', width: 80 },
    {
      title: '对人民币汇率', dataIndex: 'rate_to_cny', key: 'rate_to_cny',
      render: (v: number) => v?.toFixed(4),
    },
  ];

  const currencyCodes = currencies.map(c => c.code);

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0 }}>国际化</Title>
          <Button icon={<GlobalOutlined />} onClick={loadData}>刷新</Button>
        </div>

        <Row gutter={16}>
          <Col span={8}>
            <Card><Statistic title="支持语言数" value={languages.length} prefix={<TranslationOutlined />} /></Card>
          </Col>
          <Col span={8}>
            <Card><Statistic title="支持货币数" value={currencies.length} prefix={<DollarOutlined />} /></Card>
          </Col>
          <Col span={8}>
            <Card><Statistic title="已启用语言" value={languages.filter(l => l.enabled).length} valueStyle={{ color: '#52c41a' }} /></Card>
          </Col>
        </Row>

        <Row gutter={16}>
          <Col span={14}>
            <Card title="支持语言" size="small" tabList={[{ key: 'lang', tab: '语言列表' }, { key: 'curr', tab: '货币列表' }]}
              onTabChange={(key) => {
                if (key === 'curr') {
                  // already loaded
                }
              }}
            >
              <Table dataSource={languages} columns={langColumns} rowKey="code" size="small" pagination={{ pageSize: 8 }} />
            </Card>
          </Col>
          <Col span={10}>
            <Card title="货币换算" size="small">
              <Form form={convertForm} layout="vertical" onFinish={handleConvert}>
                <Form.Item name="amount" label="金额" initialValue={100} rules={[{ required: true }]}>
                  <InputNumber min={0} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="from_currency" label="源货币" initialValue="USD" rules={[{ required: true }]}>
                  <Select showSearch>
                    {currencyCodes.map(c => <Option key={c} value={c}>{c}</Option>)}
                    {currencyCodes.length === 0 && <Option value="USD">USD</Option>}
                  </Select>
                </Form.Item>
                <Form.Item name="to_currency" label="目标货币" initialValue="CNY" rules={[{ required: true }]}>
                  <Select showSearch>
                    {currencyCodes.map(c => <Option key={c} value={c}>{c}</Option>)}
                    {currencyCodes.length === 0 && <Option value="CNY">CNY</Option>}
                  </Select>
                </Form.Item>
                <Button type="primary" htmlType="submit" icon={<DollarOutlined />} block>换算</Button>
              </Form>
              {convertResult && (
                <Descriptions column={1} size="small" style={{ marginTop: 16 }}>
                  <Descriptions.Item label="原始金额">
                    {convertResult.original_amount} {convertResult.original_currency}
                  </Descriptions.Item>
                  <Descriptions.Item label="换算结果">
                    <Text strong style={{ color: '#1890ff', fontSize: 18 }}>
                      {convertResult.converted_amount?.toFixed(2)} {convertResult.converted_currency}
                    </Text>
                  </Descriptions.Item>
                </Descriptions>
              )}
            </Card>
          </Col>
        </Row>

        <Card title="货币列表" size="small">
          <Table dataSource={currencies} columns={currColumns} rowKey="code" size="small" pagination={{ pageSize: 10 }} />
        </Card>
      </Space>
    </Spin>
  );
};

export default I18nPage;
