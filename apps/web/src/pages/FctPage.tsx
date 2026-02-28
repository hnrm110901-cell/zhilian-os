/**
 * FctPage
 * 业财税资金一体化（FCT）— 仪表盘 / 税务测算 / 资金流预测 / 预算执行
 */
import React, { useState, useCallback } from 'react';
import {
  Tabs, Card, Statistic, Row, Col, Button, Select, InputNumber,
  Descriptions, Table, Tag, Alert, Space, Progress, Spin,
  message, Form, DatePicker,
} from 'antd';
import {
  DashboardOutlined, CalculatorOutlined, FundOutlined,
  BarChartOutlined, SaveOutlined, ReloadOutlined,
} from '@ant-design/icons';
import axios from 'axios';
import dayjs from 'dayjs';

const { TabPane } = Tabs;
const { Option } = Select;

// ── Constants ────────────────────────────────────────────────────────────────

const STORE_ID = localStorage.getItem('store_id') || '';

const now = dayjs();
const DEFAULT_YEAR  = now.month() === 0 ? now.year() - 1 : now.year();
const DEFAULT_MONTH = now.month() === 0 ? 12 : now.month(); // previous month (1-based)

// ── Dashboard Tab ─────────────────────────────────────────────────────────────

const DashboardTab: React.FC = () => {
  const [data, setData]     = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const { data: d } = await axios.get(`/api/v1/fct/${STORE_ID}/dashboard`);
      setData(d);
    } catch {
      message.error('加载 FCT 仪表盘失败');
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => { fetch(); }, [fetch]);

  if (loading) return <Spin />;
  if (!data) return <Button icon={<ReloadOutlined />} onClick={fetch}>重新加载</Button>;

  const healthColor = (score: number) =>
    score >= 80 ? '#3f8600' : score >= 60 ? '#faad14' : '#cf1322';

  return (
    <div>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={6}>
          <Card>
            <Statistic
              title="FCT 健康分"
              value={data.health_score ?? 0}
              suffix="/ 100"
              valueStyle={{ color: healthColor(data.health_score ?? 0) }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={6}>
          <Card>
            <Statistic
              title="7 日净流"
              value={((data.cash_flow?.net_7d ?? 0) / 100).toFixed(0)}
              prefix="¥"
              valueStyle={{ color: (data.cash_flow?.net_7d ?? 0) >= 0 ? '#3f8600' : '#cf1322' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={6}>
          <Card>
            <Statistic
              title="当月估算税额"
              value={((data.tax?.total_tax ?? 0) / 100).toFixed(0)}
              prefix="¥"
            />
          </Card>
        </Col>
        <Col xs={24} sm={6}>
          <Card>
            <Statistic
              title="当月利润率"
              value={(data.budget?.profit_margin_pct ?? 0).toFixed(1)}
              suffix="%"
              valueStyle={{ color: (data.budget?.profit_margin_pct ?? 0) >= 15 ? '#3f8600' : '#faad14' }}
            />
          </Card>
        </Col>
      </Row>

      {data.cash_flow?.alerts?.length > 0 && (
        <Alert
          type="warning"
          message={`资金预警：${data.cash_flow.alerts.length} 个风险日`}
          description={data.cash_flow.alerts.slice(0, 3).join('、')}
          style={{ marginTop: 16 }}
          showIcon
        />
      )}
      {data.budget?.alerts?.length > 0 && (
        <Alert
          type="error"
          message={`超预算科目：${data.budget.alerts.length} 项`}
          description={data.budget.alerts.slice(0, 3).join('、')}
          style={{ marginTop: 8 }}
          showIcon
        />
      )}
    </div>
  );
};

// ── Tax Estimation Tab ────────────────────────────────────────────────────────

const TaxTab: React.FC = () => {
  const [year,  setYear]  = useState(DEFAULT_YEAR);
  const [month, setMonth] = useState(DEFAULT_MONTH);
  const [type,  setType]  = useState('general');
  const [data,  setData]  = useState<any>(null);
  const [loading, setLoading]  = useState(false);
  const [saving,  setSaving]   = useState(false);

  const estimate = async () => {
    setLoading(true);
    try {
      const { data: d } = await axios.get(
        `/api/v1/fct/${STORE_ID}/tax/${year}/${month}`,
        { params: { taxpayer_type: type } },
      );
      setData(d);
    } catch {
      message.error('税务测算失败');
    } finally {
      setLoading(false);
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      await axios.post(
        `/api/v1/fct/${STORE_ID}/tax/${year}/${month}/save`,
        null,
        { params: { taxpayer_type: type } },
      );
      message.success('税务记录已保存');
    } catch {
      message.error('保存失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <Space style={{ marginBottom: 16 }} wrap>
        <InputNumber
          min={2020} max={2099} value={year} onChange={v => setYear(v || DEFAULT_YEAR)}
          addonBefore="年份"
        />
        <InputNumber
          min={1} max={12} value={month} onChange={v => setMonth(v || DEFAULT_MONTH)}
          addonBefore="月份"
        />
        <Select value={type} onChange={setType} style={{ width: 160 }}>
          <Option value="general">一般纳税人</Option>
          <Option value="small">小规模纳税人</Option>
          <Option value="micro">微型企业</Option>
        </Select>
        <Button type="primary" icon={<CalculatorOutlined />} onClick={estimate} loading={loading}>
          开始测算
        </Button>
        {data && (
          <Button icon={<SaveOutlined />} onClick={save} loading={saving}>
            保存记录
          </Button>
        )}
      </Space>

      {data && (
        <Row gutter={[16, 16]}>
          <Col xs={24} md={12}>
            <Card title="汇总" size="small">
              <Descriptions column={1} size="small">
                <Descriptions.Item label="期间">{data.period}</Descriptions.Item>
                <Descriptions.Item label="纳税人类型">{data.taxpayer_type}</Descriptions.Item>
                <Descriptions.Item label="合计税额">
                  <span style={{ color: '#cf1322', fontWeight: 600 }}>
                    ¥{((data.total_tax || 0) / 100).toLocaleString()}
                  </span>
                </Descriptions.Item>
                <Descriptions.Item label="综合税负率">
                  {(data.effective_rate || 0).toFixed(2)}%
                </Descriptions.Item>
              </Descriptions>
            </Card>
          </Col>
          <Col xs={24} md={12}>
            <Card title="增值税" size="small">
              <Descriptions column={1} size="small">
                <Descriptions.Item label="销项税">¥{((data.vat?.output_vat || 0) / 100).toLocaleString()}</Descriptions.Item>
                <Descriptions.Item label="进项税">¥{((data.vat?.input_vat || 0) / 100).toLocaleString()}</Descriptions.Item>
                <Descriptions.Item label="应纳增值税">¥{((data.vat?.net_vat || 0) / 100).toLocaleString()}</Descriptions.Item>
                <Descriptions.Item label="附加税">¥{((data.vat?.surcharge || 0) / 100).toLocaleString()}</Descriptions.Item>
              </Descriptions>
            </Card>
          </Col>
          <Col xs={24} md={12}>
            <Card title="企业所得税" size="small">
              <Descriptions column={1} size="small">
                <Descriptions.Item label="应税收入">¥{((data.cit?.taxable_income || 0) / 100).toLocaleString()}</Descriptions.Item>
                <Descriptions.Item label="假定利润率">{(data.cit?.assumed_margin || 0).toFixed(0)}%</Descriptions.Item>
                <Descriptions.Item label="税率">{(data.cit?.cit_rate || 0).toFixed(0)}%</Descriptions.Item>
                <Descriptions.Item label="应缴所得税">¥{((data.cit?.cit_amount || 0) / 100).toLocaleString()}</Descriptions.Item>
              </Descriptions>
            </Card>
          </Col>
          <Col xs={24} md={12}>
            <Card title="收入基础" size="small">
              <Descriptions column={1} size="small">
                <Descriptions.Item label="POS 总收入">¥{((data.revenue?.pos_total || 0) / 100).toLocaleString()}</Descriptions.Item>
                <Descriptions.Item label="订单数">{data.revenue?.order_count || 0}</Descriptions.Item>
                <Descriptions.Item label="均单价">¥{((data.revenue?.avg_order || 0) / 100).toFixed(0)}</Descriptions.Item>
              </Descriptions>
            </Card>
          </Col>
          <Col xs={24}>
            <Alert type="info" message={data.disclaimer} showIcon />
          </Col>
        </Row>
      )}
    </div>
  );
};

// ── Cash Flow Tab ─────────────────────────────────────────────────────────────

const CashFlowTab: React.FC = () => {
  const [days,    setDays]    = useState(30);
  const [balance, setBalance] = useState(0);
  const [data,    setData]    = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const forecast = async () => {
    setLoading(true);
    try {
      const { data: d } = await axios.get(`/api/v1/fct/${STORE_ID}/cash-flow`, {
        params: { days, starting_balance: Math.round(balance * 100) },
      });
      setData(d);
    } catch {
      message.error('资金流预测失败');
    } finally {
      setLoading(false);
    }
  };

  const columns = [
    { title: '日期', dataIndex: 'date', key: 'date' },
    {
      title: '进流 (¥)',
      dataIndex: 'inflow',
      key: 'inflow',
      render: (v: number) => <span style={{ color: '#3f8600' }}>+{(v / 100).toLocaleString()}</span>,
    },
    {
      title: '出流 (¥)',
      dataIndex: 'outflow',
      key: 'outflow',
      render: (v: number) => <span style={{ color: '#cf1322' }}>-{(v / 100).toLocaleString()}</span>,
    },
    {
      title: '累计余额 (¥)',
      dataIndex: 'cumulative_balance',
      key: 'balance',
      render: (v: number) => (
        <span style={{ fontWeight: 600, color: v >= 0 ? '#3f8600' : '#cf1322' }}>
          {(v / 100).toLocaleString()}
        </span>
      ),
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      render: (v: number) => <Progress percent={Math.round(v * 100)} size="small" style={{ width: 80 }} />,
    },
    {
      title: '预警',
      dataIndex: 'is_alert',
      key: 'alert',
      render: (v: boolean) => v ? <Tag color="error">预警</Tag> : <Tag color="success">正常</Tag>,
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }} wrap>
        <InputNumber
          min={7} max={90} value={days} onChange={v => setDays(v || 30)}
          addonBefore="预测天数" addonAfter="天"
        />
        <InputNumber
          min={0} value={balance} onChange={v => setBalance(v || 0)}
          addonBefore="当前余额 ¥"
          formatter={v => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
        />
        <Button type="primary" icon={<FundOutlined />} onClick={forecast} loading={loading}>
          生成预测
        </Button>
      </Space>

      {data?.alerts?.length > 0 && (
        <Alert
          type="warning"
          message={`${data.alerts.length} 个资金预警日`}
          description={`预警日期：${data.alerts.join('、')}`}
          style={{ marginBottom: 16 }}
          showIcon
        />
      )}

      {data?.daily_forecast && (
        <Table
          dataSource={data.daily_forecast}
          columns={columns}
          rowKey="date"
          size="small"
          pagination={{ pageSize: 14 }}
          rowClassName={r => r.is_alert ? 'ant-table-row-warning' : ''}
        />
      )}
    </div>
  );
};

// ── Budget Execution Tab ──────────────────────────────────────────────────────

const BudgetTab: React.FC = () => {
  const [year,  setYear]  = useState(DEFAULT_YEAR);
  const [month, setMonth] = useState(DEFAULT_MONTH);
  const [data,  setData]  = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data: d } = await axios.get(`/api/v1/fct/${STORE_ID}/budget-execution/${year}/${month}`);
      setData(d);
    } catch {
      message.error('加载预算执行数据失败');
    } finally {
      setLoading(false);
    }
  };

  const statusColor: Record<string, string> = {
    over:      'error',
    normal:    'success',
    under:     'warning',
    no_budget: 'default',
  };
  const statusLabel: Record<string, string> = {
    over:      '超预算',
    normal:    '正常',
    under:     '欠执行',
    no_budget: '无预算',
  };

  const columns = [
    { title: '科目', dataIndex: 'category', key: 'category' },
    {
      title: '实际 (¥)',
      dataIndex: 'actual',
      key: 'actual',
      render: (v: number) => (v / 100).toLocaleString(),
    },
    {
      title: '预算 (¥)',
      dataIndex: 'budget',
      key: 'budget',
      render: (v: number) => v > 0 ? (v / 100).toLocaleString() : '—',
    },
    {
      title: '执行率',
      dataIndex: 'exec_rate',
      key: 'exec_rate',
      render: (v: number) => (
        <Progress
          percent={Math.min(150, Math.round(v))}
          size="small"
          style={{ width: 100 }}
          status={v > 110 ? 'exception' : 'normal'}
          format={() => `${v.toFixed(0)}%`}
        />
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => <Tag color={statusColor[s] || 'default'}>{statusLabel[s] || s}</Tag>,
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }} wrap>
        <InputNumber
          min={2020} max={2099} value={year} onChange={v => setYear(v || DEFAULT_YEAR)}
          addonBefore="年份"
        />
        <InputNumber
          min={1} max={12} value={month} onChange={v => setMonth(v || DEFAULT_MONTH)}
          addonBefore="月份"
        />
        <Button type="primary" icon={<BarChartOutlined />} onClick={load} loading={loading}>
          查询执行率
        </Button>
      </Space>

      {data && (
        <>
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={24} sm={8}>
              <Card size="small">
                <Statistic
                  title="收入达成率"
                  value={(data.revenue?.exec_rate || 0).toFixed(1)}
                  suffix="%"
                  valueStyle={{ color: (data.revenue?.exec_rate || 0) >= 90 ? '#3f8600' : '#faad14' }}
                />
              </Card>
            </Col>
            <Col xs={24} sm={8}>
              <Card size="small">
                <Statistic
                  title="本月利润率"
                  value={(data.overall?.profit_margin_pct || 0).toFixed(1)}
                  suffix="%"
                  valueStyle={{ color: (data.overall?.profit_margin_pct || 0) >= 15 ? '#3f8600' : '#faad14' }}
                />
              </Card>
            </Col>
            <Col xs={24} sm={8}>
              <Card size="small">
                <Statistic
                  title="超预算科目"
                  value={data.alerts?.length || 0}
                  suffix="项"
                  valueStyle={{ color: (data.alerts?.length || 0) > 0 ? '#cf1322' : '#3f8600' }}
                />
              </Card>
            </Col>
          </Row>

          {data.alerts?.length > 0 && (
            <Alert
              type="error"
              message={`超预算预警：${data.alerts.join('、')}`}
              style={{ marginBottom: 16 }}
              showIcon
            />
          )}

          <Table
            dataSource={data.categories || []}
            columns={columns}
            rowKey="category"
            size="small"
            pagination={false}
          />
        </>
      )}
    </div>
  );
};

// ── Main Page ─────────────────────────────────────────────────────────────────

const FctPage: React.FC = () => (
  <div style={{ padding: 24 }}>
    <div style={{ marginBottom: 24 }}>
      <h2 style={{ margin: 0 }}>业财税资金一体化（FCT）</h2>
      <p style={{ color: '#888', marginTop: 4 }}>
        税务估算 · 资金流预测 · 预算执行率 · 月度业财对账
      </p>
    </div>

    <Tabs defaultActiveKey="dashboard">
      <TabPane tab={<><DashboardOutlined />仪表盘</>} key="dashboard">
        <DashboardTab />
      </TabPane>
      <TabPane tab={<><CalculatorOutlined />税务测算</>} key="tax">
        <TaxTab />
      </TabPane>
      <TabPane tab={<><FundOutlined />资金流预测</>} key="cashflow">
        <CashFlowTab />
      </TabPane>
      <TabPane tab={<><BarChartOutlined />预算执行</>} key="budget">
        <BudgetTab />
      </TabPane>
    </Tabs>
  </div>
);

export default FctPage;
