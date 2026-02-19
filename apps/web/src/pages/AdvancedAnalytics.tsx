import React, { useEffect, useState, useCallback } from 'react';
import { Card, Col, Row, Table, Select, Spin, Tag, Tabs, Alert } from 'antd';
import {
  LineChartOutlined,
  WarningOutlined,
  LinkOutlined,
  ClockCircleOutlined,
  RiseOutlined,
  FallOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Option } = Select;
const { TabPane } = Tabs;

const AdvancedAnalytics: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [selectedStore, setSelectedStore] = useState('STORE001');
  const [salesPrediction, setSalesPrediction] = useState<any>(null);
  const [anomalies, setAnomalies] = useState<any>(null);
  const [associations, setAssociations] = useState<any>(null);
  const [timePatterns, setTimePatterns] = useState<any>(null);

  const loadSalesPrediction = useCallback(async () => {
    try {
      const response = await apiClient.get('/analytics/predict/sales', {
        params: {
          store_id: selectedStore,
          days_ahead: 7,
        },
      });
      setSalesPrediction(response.data);
    } catch (err: any) {
      handleApiError(err, '加载销售预测失败');
    }
  }, [selectedStore]);

  const loadAnomalies = useCallback(async () => {
    try {
      const response = await apiClient.get('/analytics/anomalies', {
        params: {
          store_id: selectedStore,
          metric: 'revenue',
          days: 30,
        },
      });
      setAnomalies(response.data);
    } catch (err: any) {
      handleApiError(err, '加载异常检测失败');
    }
  }, [selectedStore]);

  const loadAssociations = useCallback(async () => {
    try {
      const response = await apiClient.get('/analytics/associations', {
        params: {
          store_id: selectedStore,
          min_support: 0.1,
        },
      });
      setAssociations(response.data);
    } catch (err: any) {
      handleApiError(err, '加载关联分析失败');
    }
  }, [selectedStore]);

  const loadTimePatterns = useCallback(async () => {
    try {
      const response = await apiClient.get('/analytics/time-patterns', {
        params: {
          store_id: selectedStore,
          days: 30,
        },
      });
      setTimePatterns(response.data);
    } catch (err: any) {
      handleApiError(err, '加载时段分析失败');
    }
  }, [selectedStore]);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([
        loadSalesPrediction(),
        loadAnomalies(),
        loadAssociations(),
        loadTimePatterns(),
      ]);
      setLoading(false);
    };
    loadData();
  }, [loadSalesPrediction, loadAnomalies, loadAssociations, loadTimePatterns]);

  // 销售预测图表
  const predictionChartOption = salesPrediction ? {
    title: {
      text: '销售预测（未来7天）',
      left: 'center',
    },
    tooltip: {
      trigger: 'axis',
    },
    legend: {
      data: ['预测营收', '预测订单数'],
      bottom: 10,
    },
    xAxis: {
      type: 'category',
      data: salesPrediction.predictions.map((p: any) => p.date),
    },
    yAxis: [
      {
        type: 'value',
        name: '营收（元）',
        axisLabel: {
          formatter: (value: number) => `¥${(value / 100).toFixed(0)}`,
        },
      },
      {
        type: 'value',
        name: '订单数',
      },
    ],
    series: [
      {
        name: '预测营收',
        type: 'line',
        yAxisIndex: 0,
        data: salesPrediction.predictions.map((p: any) => p.predicted_revenue / 100),
        itemStyle: { color: '#1890ff' },
        areaStyle: { opacity: 0.3 },
      },
      {
        name: '预测订单数',
        type: 'line',
        yAxisIndex: 1,
        data: salesPrediction.predictions.map((p: any) => p.predicted_transactions),
        itemStyle: { color: '#52c41a' },
      },
    ],
  } : null;

  // 时段分析图表
  const timePatternChartOption = timePatterns ? {
    title: {
      text: '时段营收分析',
      left: 'center',
    },
    tooltip: {
      trigger: 'axis',
    },
    xAxis: {
      type: 'category',
      data: timePatterns.hourly_analysis.map((h: any) => `${h.hour}:00`),
    },
    yAxis: {
      type: 'value',
      name: '平均营收（元）',
      axisLabel: {
        formatter: (value: number) => `¥${(value / 100).toFixed(0)}`,
      },
    },
    series: [
      {
        name: '平均营收',
        type: 'bar',
        data: timePatterns.hourly_analysis.map((h: any) => h.avg_revenue / 100),
        itemStyle: {
          color: (params: any) => {
            const hour = timePatterns.hourly_analysis[params.dataIndex].hour;
            if (hour >= 11 && hour < 14) return '#ff7875'; // 午餐
            if (hour >= 17 && hour < 21) return '#ffa940'; // 晚餐
            return '#1890ff';
          },
        },
      },
    ],
  } : null;

  // 异常检测表格列
  const anomalyColumns = [
    {
      title: '日期',
      dataIndex: 'date',
      key: 'date',
    },
    {
      title: '实际值',
      dataIndex: 'value',
      key: 'value',
      render: (value: number) => `¥${(value / 100).toFixed(2)}`,
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      render: (type: string) => (
        <Tag color={type === 'high' ? 'red' : 'orange'} icon={type === 'high' ? <RiseOutlined /> : <FallOutlined />}>
          {type === 'high' ? '异常高' : '异常低'}
        </Tag>
      ),
    },
    {
      title: '偏离度',
      dataIndex: 'deviation',
      key: 'deviation',
      render: (deviation: number) => `${deviation.toFixed(2)}σ`,
    },
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      render: (severity: string) => (
        <Tag color={severity === 'high' ? 'red' : 'orange'}>
          {severity === 'high' ? '高' : '中'}
        </Tag>
      ),
    },
  ];

  // 关联分析表格列
  const associationColumns = [
    {
      title: '商品1',
      dataIndex: 'item1',
      key: 'item1',
    },
    {
      title: '商品2',
      dataIndex: 'item2',
      key: 'item2',
    },
    {
      title: '支持度',
      dataIndex: 'support',
      key: 'support',
      render: (support: number) => `${(support * 100).toFixed(1)}%`,
    },
    {
      title: '置信度',
      dataIndex: 'confidence_1_to_2',
      key: 'confidence',
      render: (conf: number) => `${(conf * 100).toFixed(1)}%`,
    },
    {
      title: '提升度',
      dataIndex: 'lift',
      key: 'lift',
      render: (lift: number) => lift.toFixed(2),
    },
    {
      title: '关联强度',
      dataIndex: 'strength',
      key: 'strength',
      render: (strength: string) => {
        const colorMap: any = {
          strong: 'green',
          moderate: 'blue',
          weak: 'default',
        };
        const textMap: any = {
          strong: '强',
          moderate: '中',
          weak: '弱',
        };
        return <Tag color={colorMap[strength]}>{textMap[strength]}</Tag>;
      },
    },
  ];

  return (
    <div style={{ padding: '24px', background: '#f0f2f5', minHeight: '100vh' }}>
      <h1 style={{ marginBottom: '24px' }}>
        <LineChartOutlined /> 高级分析
      </h1>

      <Card style={{ marginBottom: '24px' }}>
        <span style={{ marginRight: '8px' }}>选择门店:</span>
        <Select
          value={selectedStore}
          onChange={setSelectedStore}
          style={{ width: 200 }}
        >
          <Option value="STORE001">智链餐厅-朝阳店</Option>
          <Option value="STORE002">智链餐厅-海淀店</Option>
          <Option value="STORE003">智链餐厅-浦东店</Option>
        </Select>
      </Card>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '100px 0' }}>
          <Spin size="large" tip="加载中..." />
        </div>
      ) : (
        <Tabs defaultActiveKey="prediction">
          <TabPane tab="销售预测" key="prediction" icon={<LineChartOutlined />}>
            {salesPrediction && (
              <>
                <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
                  <Col span={8}>
                    <Card>
                      <div>平均日营收</div>
                      <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#1890ff' }}>
                        ¥{(salesPrediction.average_daily_revenue / 100).toFixed(2)}
                      </div>
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card>
                      <div>趋势</div>
                      <div style={{ fontSize: '24px', fontWeight: 'bold', color: salesPrediction.trend >= 0 ? '#52c41a' : '#ff4d4f' }}>
                        {salesPrediction.trend >= 0 ? '+' : ''}{salesPrediction.trend.toFixed(2)}%
                      </div>
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card>
                      <div>历史数据天数</div>
                      <div style={{ fontSize: '24px', fontWeight: 'bold' }}>
                        {salesPrediction.historical_period.days} 天
                      </div>
                    </Card>
                  </Col>
                </Row>

                {predictionChartOption && (
                  <Card>
                    <ReactECharts option={predictionChartOption} style={{ height: '400px' }} />
                  </Card>
                )}
              </>
            )}
          </TabPane>

          <TabPane tab="异常检测" key="anomalies" icon={<WarningOutlined />}>
            {anomalies && (
              <>
                {anomalies.anomaly_count > 0 && (
                  <Alert
                    message={`检测到 ${anomalies.anomaly_count} 个异常数据点（异常率: ${anomalies.anomaly_rate}%）`}
                    type="warning"
                    showIcon
                    style={{ marginBottom: '16px' }}
                  />
                )}

                <Card style={{ marginBottom: '16px' }}>
                  <Row gutter={16}>
                    <Col span={6}>
                      <div>平均值</div>
                      <div style={{ fontSize: '20px', fontWeight: 'bold' }}>
                        ¥{(anomalies.statistics.mean / 100).toFixed(2)}
                      </div>
                    </Col>
                    <Col span={6}>
                      <div>标准差</div>
                      <div style={{ fontSize: '20px', fontWeight: 'bold' }}>
                        ¥{(anomalies.statistics.std_dev / 100).toFixed(2)}
                      </div>
                    </Col>
                    <Col span={6}>
                      <div>上限阈值</div>
                      <div style={{ fontSize: '20px', fontWeight: 'bold', color: '#ff4d4f' }}>
                        ¥{(anomalies.statistics.threshold_upper / 100).toFixed(2)}
                      </div>
                    </Col>
                    <Col span={6}>
                      <div>下限阈值</div>
                      <div style={{ fontSize: '20px', fontWeight: 'bold', color: '#faad14' }}>
                        ¥{(anomalies.statistics.threshold_lower / 100).toFixed(2)}
                      </div>
                    </Col>
                  </Row>
                </Card>

                <Card>
                  <Table
                    columns={anomalyColumns}
                    dataSource={anomalies.anomalies}
                    rowKey="date"
                    pagination={{ pageSize: 10 }}
                  />
                </Card>
              </>
            )}
          </TabPane>

          <TabPane tab="关联分析" key="associations" icon={<LinkOutlined />}>
            {associations && (
              <>
                <Alert
                  message={`分析了 ${associations.total_orders} 个订单，发现 ${associations.associations.length} 个商品关联`}
                  type="info"
                  showIcon
                  style={{ marginBottom: '16px' }}
                />

                <Card>
                  <Table
                    columns={associationColumns}
                    dataSource={associations.associations}
                    rowKey={(record: any) => `${record.item1}-${record.item2}`}
                    pagination={{ pageSize: 10 }}
                  />
                </Card>
              </>
            )}
          </TabPane>

          <TabPane tab="时段分析" key="time-patterns" icon={<ClockCircleOutlined />}>
            {timePatterns && (
              <>
                {timePatterns.insights && timePatterns.insights.length > 0 && (
                  <Alert
                    message="分析洞察"
                    description={
                      <ul style={{ marginBottom: 0 }}>
                        {timePatterns.insights.map((insight: string, index: number) => (
                          <li key={index}>{insight}</li>
                        ))}
                      </ul>
                    }
                    type="info"
                    showIcon
                    style={{ marginBottom: '16px' }}
                  />
                )}

                <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
                  {timePatterns.peak_hours.map((peak: any, index: number) => (
                    <Col span={8} key={index}>
                      <Card>
                        <div>高峰时段 #{index + 1}</div>
                        <div style={{ fontSize: '20px', fontWeight: 'bold', color: '#1890ff' }}>
                          {peak.hour}:00 ({peak.period})
                        </div>
                        <div style={{ color: '#666' }}>
                          平均营收: ¥{(peak.avg_revenue / 100).toFixed(2)}
                        </div>
                      </Card>
                    </Col>
                  ))}
                </Row>

                {timePatternChartOption && (
                  <Card>
                    <ReactECharts option={timePatternChartOption} style={{ height: '400px' }} />
                  </Card>
                )}
              </>
            )}
          </TabPane>
        </Tabs>
      )}
    </div>
  );
};

export default AdvancedAnalytics;
