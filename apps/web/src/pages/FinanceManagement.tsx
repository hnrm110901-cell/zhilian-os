import React, { useEffect, useState, useCallback } from 'react';
import { Card, Col, Row, Table, Button, Modal, Form, Input, Select, InputNumber, DatePicker, Tag, Space, Tabs, Statistic, message } from 'antd';
import {
  DollarOutlined,
  PlusOutlined,
  RiseOutlined,
  FallOutlined,
  FileTextOutlined,
  BarChartOutlined,
  DownloadOutlined,
  FilePdfOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { showSuccess, showError, handleApiError } from '../utils/message';
import dayjs from 'dayjs';

const { TabPane } = Tabs;
const { TextArea } = Input;
const { RangePicker } = DatePicker;

const FinanceManagement: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [transactions, setTransactions] = useState<any[]>([]);
  const [incomeStatement, setIncomeStatement] = useState<any>(null);
  const [cashFlow, setCashFlow] = useState<any>(null);
  const [budgetAnalysis, setBudgetAnalysis] = useState<any>(null);
  const [financialMetrics, setFinancialMetrics] = useState<any>(null);
  const [transactionModalVisible, setTransactionModalVisible] = useState(false);
  const [budgetModalVisible, setBudgetModalVisible] = useState(false);
  const [form] = Form.useForm();
  const [budgetForm] = Form.useForm();
  const [dateRange, setDateRange] = useState<any>([
    dayjs().startOf('month'),
    dayjs().endOf('month'),
  ]);

  const loadTransactions = useCallback(async () => {
    try {
      const response = await apiClient.get('/finance/transactions', {
        params: {
          start_date: dateRange[0].format('YYYY-MM-DD'),
          end_date: dateRange[1].format('YYYY-MM-DD'),
        },
      });
      setTransactions(response.data.transactions || []);
    } catch (err: any) {
      handleApiError(err, '加载交易记录失败');
    }
  }, [dateRange]);

  const loadIncomeStatement = useCallback(async () => {
    try {
      const response = await apiClient.get('/finance/reports/income-statement', {
        params: {
          store_id: 'STORE001',
          start_date: dateRange[0].format('YYYY-MM-DD'),
          end_date: dateRange[1].format('YYYY-MM-DD'),
        },
      });
      setIncomeStatement(response.data);
    } catch (err: any) {
      handleApiError(err, '加载损益表失败');
    }
  }, [dateRange]);

  const loadCashFlow = useCallback(async () => {
    try {
      const response = await apiClient.get('/finance/reports/cash-flow', {
        params: {
          store_id: 'STORE001',
          start_date: dateRange[0].format('YYYY-MM-DD'),
          end_date: dateRange[1].format('YYYY-MM-DD'),
        },
      });
      setCashFlow(response.data);
    } catch (err: any) {
      handleApiError(err, '加载现金流量表失败');
    }
  }, [dateRange]);

  const loadBudgetAnalysis = useCallback(async () => {
    try {
      const now = dayjs();
      const response = await apiClient.get('/finance/budgets/analysis', {
        params: {
          store_id: 'STORE001',
          year: now.year(),
          month: now.month() + 1,
        },
      });
      setBudgetAnalysis(response.data);
    } catch (err: any) {
      handleApiError(err, '加载预算分析失败');
    }
  }, []);

  const loadFinancialMetrics = useCallback(async () => {
    try {
      const response = await apiClient.get('/finance/metrics', {
        params: {
          store_id: 'STORE001',
          start_date: dateRange[0].format('YYYY-MM-DD'),
          end_date: dateRange[1].format('YYYY-MM-DD'),
        },
      });
      setFinancialMetrics(response.data);
    } catch (err: any) {
      handleApiError(err, '加载财务指标失败');
    }
  }, [dateRange]);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([
        loadTransactions(),
        loadIncomeStatement(),
        loadCashFlow(),
        loadBudgetAnalysis(),
        loadFinancialMetrics(),
      ]);
      setLoading(false);
    };
    loadData();
  }, [loadTransactions, loadIncomeStatement, loadCashFlow, loadBudgetAnalysis, loadFinancialMetrics]);

  const handleCreateTransaction = async (values: any) => {
    try {
      await apiClient.post('/finance/transactions', {
        ...values,
        amount: values.amount * 100, // 转换为分
      });
      showSuccess('交易记录创建成功');
      setTransactionModalVisible(false);
      form.resetFields();
      loadTransactions();
      loadIncomeStatement();
      loadCashFlow();
      loadFinancialMetrics();
    } catch (err: any) {
      handleApiError(err, '创建交易记录失败');
    }
  };

  const handleCreateBudget = async (values: any) => {
    try {
      await apiClient.post('/finance/budgets', {
        ...values,
        budgeted_amount: values.budgeted_amount * 100, // 转换为分
      });
      showSuccess('预算创建成功');
      setBudgetModalVisible(false);
      budgetForm.resetFields();
      loadBudgetAnalysis();
    } catch (err: any) {
      handleApiError(err, '创建预算失败');
    }
  };

  const handleExportReport = async (reportType: string, format: string = 'csv') => {
    try {
      message.loading({ content: '正在导出报表...', key: 'export' });

      const params = new URLSearchParams({
        report_type: reportType,
        format: format,
        start_date: dateRange[0].format('YYYY-MM-DD'),
        end_date: dateRange[1].format('YYYY-MM-DD'),
      });

      const response = await apiClient.get(`/finance/reports/export?${params.toString()}`, {
        responseType: 'blob',
      });

      // 创建下载链接
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      const extension = format === 'pdf' ? 'pdf' : 'csv';
      link.setAttribute('download', `${reportType}_${dateRange[0].format('YYYY-MM-DD')}_${dateRange[1].format('YYYY-MM-DD')}.${extension}`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

      message.success({ content: '报表导出成功', key: 'export' });
    } catch (err: any) {
      message.error({ content: '报表导出失败', key: 'export' });
      handleApiError(err, '报表导出失败');
    }
  };

  // 交易记录表格列
  const transactionColumns = [
    {
      title: '日期',
      dataIndex: 'transaction_date',
      key: 'transaction_date',
    },
    {
      title: '类型',
      dataIndex: 'transaction_type',
      key: 'transaction_type',
      render: (type: string) => (
        <Tag color={type === 'income' ? 'green' : 'red'}>
          {type === 'income' ? '收入' : '支出'}
        </Tag>
      ),
    },
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
    },
    {
      title: '金额',
      dataIndex: 'amount',
      key: 'amount',
      render: (amount: number) => `¥${(amount / 100).toFixed(2)}`,
    },
    {
      title: '支付方式',
      dataIndex: 'payment_method',
      key: 'payment_method',
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
    },
  ];

  // 预算分析表格列
  const budgetColumns = [
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
    },
    {
      title: '预算金额',
      dataIndex: 'budgeted_amount',
      key: 'budgeted_amount',
      render: (amount: number) => `¥${(amount / 100).toFixed(2)}`,
    },
    {
      title: '实际金额',
      dataIndex: 'actual_amount',
      key: 'actual_amount',
      render: (amount: number) => `¥${(amount / 100).toFixed(2)}`,
    },
    {
      title: '差异',
      dataIndex: 'variance',
      key: 'variance',
      render: (variance: number) => {
        const isPositive = variance > 0;
        return (
          <span style={{ color: isPositive ? '#ff4d4f' : '#52c41a' }}>
            {isPositive ? '+' : ''}¥{(variance / 100).toFixed(2)}
          </span>
        );
      },
    },
    {
      title: '差异率',
      dataIndex: 'variance_percentage',
      key: 'variance_percentage',
      render: (percentage: number) => {
        const isPositive = percentage > 0;
        return (
          <Tag color={isPositive ? 'red' : 'green'} icon={isPositive ? <RiseOutlined /> : <FallOutlined />}>
            {isPositive ? '+' : ''}{percentage.toFixed(1)}%
          </Tag>
        );
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const statusMap: any = {
          over: { color: 'red', text: '超支' },
          under: { color: 'green', text: '节约' },
          on_track: { color: 'blue', text: '正常' },
        };
        const s = statusMap[status] || { color: 'default', text: status };
        return <Tag color={s.color}>{s.text}</Tag>;
      },
    },
  ];

  // 现金流图表配置
  const cashFlowChartOption = cashFlow ? {
    title: {
      text: '现金流量趋势',
      left: 'center',
    },
    tooltip: {
      trigger: 'axis',
    },
    legend: {
      data: ['流入', '流出', '净额'],
      bottom: 10,
    },
    xAxis: {
      type: 'category',
      data: Object.keys(cashFlow.cash_flow || {}),
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        formatter: (value: number) => `¥${(value / 100).toFixed(0)}`,
      },
    },
    series: [
      {
        name: '流入',
        type: 'line',
        data: Object.values(cashFlow.cash_flow || {}).map((d: any) => d.inflow / 100),
        itemStyle: { color: '#52c41a' },
      },
      {
        name: '流出',
        type: 'line',
        data: Object.values(cashFlow.cash_flow || {}).map((d: any) => d.outflow / 100),
        itemStyle: { color: '#ff4d4f' },
      },
      {
        name: '净额',
        type: 'line',
        data: Object.values(cashFlow.cash_flow || {}).map((d: any) => d.net / 100),
        itemStyle: { color: '#1890ff' },
      },
    ],
  } : null;

  return (
    <div style={{ padding: '24px', background: '#f0f2f5', minHeight: '100vh' }}>
      <h1 style={{ marginBottom: '24px' }}>
        <DollarOutlined /> 财务管理
      </h1>

      {/* 日期选择 */}
      <Card style={{ marginBottom: '24px' }}>
        <Space>
          <span>选择日期范围:</span>
          <RangePicker
            value={dateRange}
            onChange={(dates) => setDateRange(dates)}
          />
        </Space>
      </Card>

      {/* 财务指标卡片 */}
      {financialMetrics && (
        <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="总营收"
                value={financialMetrics.metrics.total_revenue / 100}
                precision={2}
                prefix="¥"
                valueStyle={{ color: '#3f8600' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="净利润"
                value={financialMetrics.metrics.net_profit / 100}
                precision={2}
                prefix="¥"
                valueStyle={{ color: financialMetrics.metrics.net_profit >= 0 ? '#3f8600' : '#cf1322' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="毛利率"
                value={financialMetrics.metrics.gross_margin}
                precision={2}
                suffix="%"
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="净利率"
                value={financialMetrics.metrics.net_margin}
                precision={2}
                suffix="%"
              />
            </Card>
          </Col>
        </Row>
      )}

      {/* 主要内容 */}
      <Card>
        <Tabs defaultActiveKey="transactions">
          <TabPane tab="交易记录" key="transactions">
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setTransactionModalVisible(true)}
              style={{ marginBottom: '16px' }}
            >
              添加交易记录
            </Button>
            <Table
              columns={transactionColumns}
              dataSource={transactions}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </TabPane>

          <TabPane tab="损益表" key="income-statement">
            <Space style={{ marginBottom: '16px' }}>
              <Button
                type="primary"
                icon={<DownloadOutlined />}
                onClick={() => handleExportReport('income_statement', 'csv')}
              >
                导出CSV
              </Button>
              <Button
                icon={<FilePdfOutlined />}
                onClick={() => handleExportReport('income_statement', 'pdf')}
              >
                导出PDF
              </Button>
            </Space>
            {incomeStatement && (
              <div>
                <h3>收入</h3>
                <p>总营收: ¥{(incomeStatement.revenue.total / 100).toFixed(2)}</p>

                <h3>支出</h3>
                <ul>
                  {Object.entries(incomeStatement.expenses).map(([key, value]: [string, any]) => (
                    <li key={key}>{key}: ¥{(value / 100).toFixed(2)}</li>
                  ))}
                </ul>
                <p>总支出: ¥{(incomeStatement.total_expenses / 100).toFixed(2)}</p>

                <h3>利润</h3>
                <p>毛利润: ¥{(incomeStatement.profit.gross_profit / 100).toFixed(2)}</p>
                <p>营业利润: ¥{(incomeStatement.profit.operating_profit / 100).toFixed(2)}</p>
                <p>净利润: ¥{(incomeStatement.profit.net_profit / 100).toFixed(2)}</p>

                <h3>利润率</h3>
                <p>毛利率: {incomeStatement.margins.gross_margin}%</p>
                <p>营业利润率: {incomeStatement.margins.operating_margin}%</p>
                <p>净利率: {incomeStatement.margins.net_margin}%</p>
              </div>
            )}
          </TabPane>

          <TabPane tab="现金流量" key="cash-flow">
            <Space style={{ marginBottom: '16px' }}>
              <Button
                type="primary"
                icon={<DownloadOutlined />}
                onClick={() => handleExportReport('cash_flow', 'csv')}
              >
                导出CSV
              </Button>
              <Button
                icon={<FilePdfOutlined />}
                onClick={() => handleExportReport('cash_flow', 'pdf')}
              >
                导出PDF
              </Button>
            </Space>
            {cashFlowChartOption && (
              <ReactECharts option={cashFlowChartOption} style={{ height: '400px' }} />
            )}
          </TabPane>

          <TabPane tab="交易明细" key="transactions-detail">
            <Space style={{ marginBottom: '16px' }}>
              <Button
                type="primary"
                icon={<DownloadOutlined />}
                onClick={() => handleExportReport('transactions', 'csv')}
              >
                导出CSV
              </Button>
            </Space>
            <Table
              columns={transactionColumns}
              dataSource={transactions}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </TabPane>

          <TabPane tab="预算分析" key="budget">
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setBudgetModalVisible(true)}
              style={{ marginBottom: '16px' }}
            >
              创建预算
            </Button>
            {budgetAnalysis && (
              <Table
                columns={budgetColumns}
                dataSource={budgetAnalysis.analysis}
                rowKey="category"
                loading={loading}
                pagination={false}
              />
            )}
          </TabPane>
        </Tabs>
      </Card>

      {/* 添加交易记录模态框 */}
      <Modal
        title="添加交易记录"
        open={transactionModalVisible}
        onCancel={() => setTransactionModalVisible(false)}
        onOk={() => form.submit()}
      >
        <Form form={form} layout="vertical" onFinish={handleCreateTransaction}>
          <Form.Item name="store_id" label="门店ID" initialValue="STORE001" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="transaction_date" label="交易日期" rules={[{ required: true }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="transaction_type" label="交易类型" rules={[{ required: true }]}>
            <Select>
              <Select.Option value="income">收入</Select.Option>
              <Select.Option value="expense">支出</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="category" label="类别" rules={[{ required: true }]}>
            <Select>
              <Select.Option value="sales">销售收入</Select.Option>
              <Select.Option value="food_cost">食材成本</Select.Option>
              <Select.Option value="labor_cost">人力成本</Select.Option>
              <Select.Option value="rent">租金</Select.Option>
              <Select.Option value="utilities">水电费</Select.Option>
              <Select.Option value="marketing">营销费用</Select.Option>
              <Select.Option value="other_expense">其他支出</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="amount" label="金额（元）" rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="payment_method" label="支付方式">
            <Select>
              <Select.Option value="cash">现金</Select.Option>
              <Select.Option value="card">银行卡</Select.Option>
              <Select.Option value="wechat">微信</Select.Option>
              <Select.Option value="alipay">支付宝</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 创建预算模态框 */}
      <Modal
        title="创建预算"
        open={budgetModalVisible}
        onCancel={() => setBudgetModalVisible(false)}
        onOk={() => budgetForm.submit()}
      >
        <Form form={budgetForm} layout="vertical" onFinish={handleCreateBudget}>
          <Form.Item name="store_id" label="门店ID" initialValue="STORE001" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="year" label="年份" initialValue={dayjs().year()} rules={[{ required: true }]}>
            <InputNumber min={2020} max={2030} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="month" label="月份" initialValue={dayjs().month() + 1} rules={[{ required: true }]}>
            <InputNumber min={1} max={12} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="category" label="类别" rules={[{ required: true }]}>
            <Select>
              <Select.Option value="food_cost">食材成本</Select.Option>
              <Select.Option value="labor_cost">人力成本</Select.Option>
              <Select.Option value="rent">租金</Select.Option>
              <Select.Option value="utilities">水电费</Select.Option>
              <Select.Option value="marketing">营销费用</Select.Option>
              <Select.Option value="other_expense">其他支出</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="budgeted_amount" label="预算金额（元）" rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default FinanceManagement;
