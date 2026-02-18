import React, { useEffect, useState, useCallback } from 'react';
import { Card, Row, Col, Statistic, Table, Tag, Alert, Spin, Button, Select, Space } from 'antd';
import {
  WarningOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ReloadOutlined,
  BugOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';

const { Option } = Select;

interface ErrorSummary {
  time_window_minutes: number;
  total_errors: number;
  severity_distribution: Record<string, number>;
  category_distribution: Record<string, number>;
  recent_errors: Array<{
    error_id: string;
    timestamp: string;
    severity: string;
    category: string;
    message: string;
    endpoint: string;
  }>;
}

interface PerformanceSummary {
  time_window_minutes: number;
  total_requests: number;
  avg_duration_ms: number;
  max_duration_ms: number;
  min_duration_ms: number;
  slowest_endpoints: Array<{
    endpoint: string;
    count: number;
    avg_duration_ms: number;
  }>;
}

const MonitoringPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [errorSummary, setErrorSummary] = useState<ErrorSummary | null>(null);
  const [performanceSummary, setPerformanceSummary] = useState<PerformanceSummary | null>(null);
  const [timeWindow, setTimeWindow] = useState(60);
  const [error, setError] = useState<string | null>(null);

  const loadMonitoringData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [errors, performance] = await Promise.all([
        apiClient.get(`/monitoring/errors/summary?time_window=${timeWindow}`),
        apiClient.get(`/monitoring/performance/summary?time_window=${timeWindow}`),
      ]);

      setErrorSummary(errors);
      setPerformanceSummary(performance);
    } catch (err: any) {
      console.error('Failed to load monitoring data:', err);
      setError(err.message || '加载监控数据失败');
    } finally {
      setLoading(false);
    }
  }, [timeWindow]);

  useEffect(() => {
    loadMonitoringData();

    // 自动刷新
    const interval = setInterval(loadMonitoringData, 30000); // 30秒刷新一次

    return () => clearInterval(interval);
  }, [loadMonitoringData]);

  const getSeverityColor = (severity: string) => {
    const colors: Record<string, string> = {
      critical: 'red',
      error: 'orange',
      warning: 'gold',
      info: 'blue',
      debug: 'default',
    };
    return colors[severity] || 'default';
  };

  const errorColumns = [
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      render: (text: string) => new Date(text).toLocaleString('zh-CN'),
      width: 180,
    },
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      render: (severity: string) => (
        <Tag color={getSeverityColor(severity)}>{severity.toUpperCase()}</Tag>
      ),
      width: 100,
    },
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
      width: 120,
    },
    {
      title: '消息',
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
    },
    {
      title: '端点',
      dataIndex: 'endpoint',
      key: 'endpoint',
      width: 200,
      ellipsis: true,
    },
  ];

  const performanceColumns = [
    {
      title: '端点',
      dataIndex: 'endpoint',
      key: 'endpoint',
      ellipsis: true,
    },
    {
      title: '请求数',
      dataIndex: 'count',
      key: 'count',
      width: 100,
    },
    {
      title: '平均响应时间',
      dataIndex: 'avg_duration_ms',
      key: 'avg_duration_ms',
      render: (ms: number) => `${ms.toFixed(2)} ms`,
      width: 150,
    },
  ];

  const errorDistributionOption = {
    title: {
      text: '错误严重程度分布',
      left: 'center',
    },
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)',
    },
    legend: {
      orient: 'vertical',
      left: 'left',
    },
    series: [
      {
        name: '错误数量',
        type: 'pie',
        radius: '50%',
        data: errorSummary
          ? Object.entries(errorSummary.severity_distribution).map(([name, value]) => ({
              name: name.toUpperCase(),
              value,
            }))
          : [],
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.5)',
          },
        },
      },
    ],
  };

  if (loading && !errorSummary) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <Spin size="large" />
        <p style={{ marginTop: 16 }}>正在加载监控数据...</p>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>系统监控</h1>
        <Space>
          <Select value={timeWindow} onChange={setTimeWindow} style={{ width: 150 }}>
            <Option value={15}>最近15分钟</Option>
            <Option value={60}>最近1小时</Option>
            <Option value={360}>最近6小时</Option>
            <Option value={1440}>最近24小时</Option>
          </Select>
          <Button icon={<ReloadOutlined />} onClick={loadMonitoringData} loading={loading}>
            刷新
          </Button>
        </Space>
      </div>

      {error && (
        <Alert
          message="加载失败"
          description={error}
          type="error"
          showIcon
          closable
          onClose={() => setError(null)}
          style={{ marginBottom: 24 }}
        />
      )}

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="总错误数"
              value={errorSummary?.total_errors || 0}
              prefix={<BugOutlined />}
              valueStyle={{ color: errorSummary && errorSummary.total_errors > 0 ? '#cf1322' : '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="总请求数"
              value={performanceSummary?.total_requests || 0}
              prefix={<ThunderboltOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="平均响应时间"
              value={performanceSummary?.avg_duration_ms.toFixed(2) || 0}
              suffix="ms"
              prefix={<ClockCircleOutlined />}
              valueStyle={{
                color: performanceSummary && performanceSummary.avg_duration_ms > 500 ? '#faad14' : '#52c41a',
              }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="最慢请求"
              value={performanceSummary?.max_duration_ms.toFixed(2) || 0}
              suffix="ms"
              prefix={<WarningOutlined />}
              valueStyle={{
                color: performanceSummary && performanceSummary.max_duration_ms > 1000 ? '#cf1322' : '#faad14',
              }}
            />
          </Card>
        </Col>
      </Row>

      {/* 错误分布图表 */}
      {errorSummary && errorSummary.total_errors > 0 && (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={12}>
            <Card title="错误严重程度分布">
              <ReactECharts option={errorDistributionOption} style={{ height: 300 }} />
            </Card>
          </Col>
          <Col span={12}>
            <Card title="错误类别统计">
              <div style={{ padding: '20px 0' }}>
                {Object.entries(errorSummary.category_distribution).map(([category, count]) => (
                  <div
                    key={category}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      padding: '8px 0',
                      borderBottom: '1px solid #f0f0f0',
                    }}
                  >
                    <span>{category}</span>
                    <Tag color="blue">{count}</Tag>
                  </div>
                ))}
              </div>
            </Card>
          </Col>
        </Row>
      )}

      {/* 最近错误列表 */}
      {errorSummary && errorSummary.recent_errors.length > 0 && (
        <Card title="最近错误" style={{ marginBottom: 16 }}>
          <Table
            dataSource={errorSummary.recent_errors}
            columns={errorColumns}
            rowKey="error_id"
            pagination={false}
            size="small"
          />
        </Card>
      )}

      {/* 性能最慢端点 */}
      {performanceSummary && performanceSummary.slowest_endpoints.length > 0 && (
        <Card title="响应最慢的端点">
          <Table
            dataSource={performanceSummary.slowest_endpoints}
            columns={performanceColumns}
            rowKey="endpoint"
            pagination={false}
            size="small"
          />
        </Card>
      )}

      {errorSummary && errorSummary.total_errors === 0 && (
        <Card>
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <CheckCircleOutlined style={{ fontSize: 48, color: '#52c41a', marginBottom: 16 }} />
            <h3>系统运行正常</h3>
            <p style={{ color: '#999' }}>在过去{timeWindow}分钟内没有错误记录</p>
          </div>
        </Card>
      )}
    </div>
  );
};

export default MonitoringPage;
