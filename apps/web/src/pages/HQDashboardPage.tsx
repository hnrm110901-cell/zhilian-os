import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Statistic, Table, Tag, Badge, Button, DatePicker,
  Typography, Space, Alert, Spin, Progress, Tooltip,
} from 'antd';
import {
  ShopOutlined, ReloadOutlined, WarningOutlined,
  RiseOutlined, FallOutlined, CheckCircleOutlined, HeartOutlined,
} from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Title, Text } = Typography;

const DIM_LABEL: Record<string, string> = {
  revenue_completion: '营收完成率',
  table_turnover:     '翻台率',
  cost_rate:          '成本率',
  complaint_rate:     '客诉率',
  staff_efficiency:   '人效',
};

const HQDashboardPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [healthLoading, setHealthLoading] = useState(false);
  const [targetDate, setTargetDate] = useState<Dayjs>(dayjs().subtract(1, 'day'));
  const [data, setData] = useState<any>(null);
  const [healthData, setHealthData] = useState<any>(null);

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

  const loadHealth = useCallback(async () => {
    setHealthLoading(true);
    try {
      const res = await apiClient.get('/api/v1/stores/health', {
        params: { target_date: targetDate.format('YYYY-MM-DD') },
      });
      setHealthData(res.data);
    } catch (err: any) {
      // 健康评分非核心，静默降级
    } finally {
      setHealthLoading(false);
    }
  }, [targetDate]);

  useEffect(() => {
    load();
    loadHealth();
  }, [load, loadHealth]);

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

  // 健康评分表格列
  const healthStores: any[] = healthData?.stores || [];
  const healthSummary = healthData?.summary || {};

  const healthColumns = [
    {
      title: '排名',
      dataIndex: 'rank',
      width: 50,
      render: (v: number) => (
        <span style={{
          fontWeight: 'bold',
          color: v === 1 ? '#f5a623' : v === 2 ? '#9b9b9b' : v === 3 ? '#cd7f32' : '#666',
        }}>{v}</span>
      ),
    },
    { title: '门店', dataIndex: 'store_name' },
    {
      title: '综合健康分',
      dataIndex: 'score',
      render: (v: number, row: any) => (
        <Space>
          <Progress
            percent={v}
            size="small"
            strokeColor={
              row.level === 'excellent' ? '#52c41a'
              : row.level === 'good' ? '#1890ff'
              : row.level === 'warning' ? '#faad14'
              : '#ff4d4f'
            }
            style={{ width: 80 }}
          />
          <span style={{ fontWeight: 600 }}>{v}</span>
        </Space>
      ),
      sorter: (a: any, b: any) => a.score - b.score,
    },
    {
      title: '状态',
      dataIndex: 'level_label',
      render: (v: string, row: any) => (
        <Tag color={row.level_color}>{v}</Tag>
      ),
    },
    {
      title: '最弱维度',
      dataIndex: 'weakest_label',
      render: (v: string | null) => v
        ? <Tag color="orange">{v}</Tag>
        : <CheckCircleOutlined style={{ color: '#52c41a' }} />,
    },
    {
      title: '营收',
      dataIndex: 'revenue_yuan',
      render: (v: number) => `¥${(v || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}`,
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
          <Button icon={<ReloadOutlined />} onClick={() => { load(); loadHealth(); }}>刷新</Button>
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

        <Row gutter={16} style={{ marginBottom: 16 }}>
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

        {/* 门店健康度排名卡片（v2.1 StoreHealthScore） */}
        <Spin spinning={healthLoading}>
          <Card
            title={<span><HeartOutlined style={{ color: '#52c41a', marginRight: 6 }} />门店健康度排名</span>}
            extra={
              <Space>
                {healthSummary.critical > 0 && (
                  <Tag color="red">🔴 危险 {healthSummary.critical} 家</Tag>
                )}
                {healthSummary.warning > 0 && (
                  <Tag color="orange">⚠️ 需关注 {healthSummary.warning} 家</Tag>
                )}
                {healthSummary.good > 0 && (
                  <Tag color="blue">良好 {healthSummary.good} 家</Tag>
                )}
                {healthSummary.excellent > 0 && (
                  <Tag color="green">优秀 {healthSummary.excellent} 家</Tag>
                )}
              </Space>
            }
          >
            <Table
              dataSource={healthStores}
              columns={healthColumns}
              rowKey="store_id"
              size="small"
              pagination={false}
              rowClassName={(row: any) =>
                row.level === 'critical' ? 'ant-table-row-danger' : ''
              }
            />
            {healthStores.length === 0 && !healthLoading && (
              <Text type="secondary" style={{ display: 'block', textAlign: 'center', padding: 16 }}>
                暂无健康评分数据
              </Text>
            )}
          </Card>
        </Spin>
      </Spin>
    </div>
  );
};

export default HQDashboardPage;
