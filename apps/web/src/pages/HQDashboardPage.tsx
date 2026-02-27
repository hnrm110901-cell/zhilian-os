import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Statistic, Table, Tag, Badge, Button, DatePicker,
  Typography, Space, Alert, Spin, Progress,
} from 'antd';
import {
  ShopOutlined, ReloadOutlined, WarningOutlined,
  RiseOutlined, FallOutlined, CheckCircleOutlined,
} from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Title, Text } = Typography;

const HQDashboardPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [targetDate, setTargetDate] = useState<Dayjs>(dayjs().subtract(1, 'day'));
  const [data, setData] = useState<any>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/api/v1/hq/dashboard', {
        params: { target_date: targetDate.format('YYYY-MM-DD') },
      });
      setData(res.data);
    } catch (err: any) {
      handleApiError(err, '加载总部看板失败');
    } finally {
      setLoading(false);
    }
  }, [targetDate]);

  useEffect(() => { load(); }, [load]);

  const summary = data?.summary || {};
  const storeMetrics: any[] = data?.store_metrics || [];
  const alertStores: any[] = data?.alert_stores || [];

  // 营收排名柱状图
  const top10 = storeMetrics.slice(0, 10);
  const barOption = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: top10.map((s: any) => s.store_name), axisLabel: { rotate: 30 } },
    yAxis: { type: 'value', name: '营收（分）' },
    series: [{
      type: 'bar',
      data: top10.map((s: any) => s.revenue),
      itemStyle: { color: '#1890ff' },
      label: { show: false },
    }],
  };

  const columns = [
    { title: '排名', render: (_: any, __: any, idx: number) => idx + 1, width: 60 },
    { title: '门店', dataIndex: 'store_name' },
    {
      title: '昨日营收',
      dataIndex: 'revenue',
      render: (v: number) => `¥${(v / 100).toFixed(0)}`,
      sorter: (a: any, b: any) => a.revenue - b.revenue,
    },
    { title: '订单数', dataIndex: 'orders' },
    {
      title: '健康分',
      dataIndex: 'health_score',
      render: (v: number) => (
        <Progress percent={v} size="small" status={v >= 80 ? 'success' : v >= 60 ? 'normal' : 'exception'} />
      ),
    },
    {
      title: '待审批',
      dataIndex: 'pending_approvals',
      render: (v: number) => v > 0 ? <Badge count={v} /> : <CheckCircleOutlined style={{ color: '#52c41a' }} />,
    },
    {
      title: '状态',
      dataIndex: 'has_alert',
      render: (v: boolean) => v
        ? <Tag color="red" icon={<WarningOutlined />}>需关注</Tag>
        : <Tag color="green">正常</Tag>,
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}><ShopOutlined /> 总部跨店看板</Title>
        <Space>
          <DatePicker
            value={targetDate}
            onChange={(v) => v && setTargetDate(v)}
            allowClear={false}
            disabledDate={(d) => d.isAfter(dayjs())}
          />
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        </Space>
      </div>

      <Spin spinning={loading}>
        {alertStores.length > 0 && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
            message={`${alertStores.length} 家门店需要关注`}
            description={alertStores.map((s: any) => `${s.store_name}（待审批 ${s.pending_approvals} 项）`).join('、')}
          />
        )}

        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card>
              <Statistic title="门店总数" value={summary.total_stores || 0} suffix="家" />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="昨日总营收"
                value={((summary.total_revenue || 0) / 100).toFixed(0)}
                prefix="¥"
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic title="昨日总订单" value={summary.total_orders || 0} suffix="单" />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="待审批决策"
                value={summary.total_pending_approvals || 0}
                valueStyle={{ color: summary.total_pending_approvals > 0 ? '#faad14' : '#52c41a' }}
                suffix="项"
              />
            </Card>
          </Col>
        </Row>

        <Row gutter={16}>
          <Col span={14}>
            <Card title="营收排名 TOP10">
              <ReactECharts option={barOption} style={{ height: 280 }} />
            </Card>
          </Col>
          <Col span={10}>
            <Card title="门店列表" extra={<Text type="secondary">{storeMetrics.length} 家</Text>}>
              <Table
                dataSource={storeMetrics}
                columns={columns}
                rowKey="store_id"
                size="small"
                pagination={{ pageSize: 8, size: 'small' }}
                scroll={{ y: 280 }}
              />
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  );
};

export default HQDashboardPage;
