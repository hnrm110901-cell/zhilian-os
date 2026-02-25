import React, { useEffect, useState, useCallback } from 'react';
import { Card, Col, Row, Statistic, Spin, Tag } from 'antd';
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
  ShopOutlined,
  UserOutlined,
  DollarOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const DataVisualizationScreen: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [overviewStats, setOverviewStats] = useState<any>(null);
  const [salesTrend, setSalesTrend] = useState<any>(null);
  const [memberStats, setMemberStats] = useState<any>(null);
  const [realtimeMetrics, setRealtimeMetrics] = useState<any>(null);

  const loadDashboardData = useCallback(async () => {
    try {
      setLoading(true);

      const [overview, trend, members, realtime] = await Promise.all([
        apiClient.get('/dashboard/overview'),
        apiClient.get('/dashboard/sales-trend?days=7'),
        apiClient.get('/dashboard/member-stats'),
        apiClient.get('/dashboard/realtime-metrics'),
      ]);

      setOverviewStats(overview.data);
      setSalesTrend(trend.data);
      setMemberStats(members.data);
      setRealtimeMetrics(realtime.data);
    } catch (err: any) {
      handleApiError(err, '加载数据大屏失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboardData();

    // 自动刷新（每30秒）
    const intervalId = window.setInterval(() => {
      loadDashboardData();
    }, 30000);

    return () => {
      clearInterval(intervalId);
    };
  }, [loadDashboardData]);

  // 销售趋势图表配置
  const salesTrendOption = {
    title: {
      text: '销售趋势（近7天）',
      left: 'center',
      textStyle: {
        fontSize: 18,
        fontWeight: 'bold',
      },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
      },
    },
    legend: {
      data: ['订单数', '营收（元）'],
      bottom: 10,
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: salesTrend?.dates || [],
      boundaryGap: false,
    },
    yAxis: [
      {
        type: 'value',
        name: '订单数',
        position: 'left',
      },
      {
        type: 'value',
        name: '营收（元）',
        position: 'right',
        axisLabel: {
          formatter: (value: number) => (value / 100).toFixed(0),
        },
      },
    ],
    series: [
      {
        name: '订单数',
        type: 'line',
        data: salesTrend?.orders_count || [],
        smooth: true,
        itemStyle: {
          color: '#1890ff',
        },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(24, 144, 255, 0.3)' },
              { offset: 1, color: 'rgba(24, 144, 255, 0.05)' },
            ],
          },
        },
      },
      {
        name: '营收（元）',
        type: 'line',
        yAxisIndex: 1,
        data: salesTrend?.revenue?.map((v: number) => v / 100) || [],
        smooth: true,
        itemStyle: {
          color: '#52c41a',
        },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(82, 196, 26, 0.3)' },
              { offset: 1, color: 'rgba(82, 196, 26, 0.05)' },
            ],
          },
        },
      },
    ],
  };

  // 会员等级分布图表配置
  const memberLevelOption = {
    title: {
      text: '会员等级分布',
      left: 'center',
      textStyle: {
        fontSize: 18,
        fontWeight: 'bold',
      },
    },
    tooltip: {
      trigger: 'item',
      formatter: '{a} <br/>{b}: {c} ({d}%)',
    },
    legend: {
      orient: 'vertical',
      left: 'left',
      top: 'middle',
    },
    series: [
      {
        name: '会员数量',
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#fff',
          borderWidth: 2,
        },
        label: {
          show: false,
          position: 'center',
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 20,
            fontWeight: 'bold',
          },
        },
        labelLine: {
          show: false,
        },
        data: memberStats?.member_levels?.map((level: any) => ({
          value: level.count,
          name: level.level,
        })) || [],
      },
    ],
  };

  // 实时指标仪表盘
  const tableOccupancyOption = {
    title: {
      text: '桌台占用率',
      left: 'center',
      textStyle: {
        fontSize: 16,
      },
    },
    series: [
      {
        type: 'gauge',
        startAngle: 180,
        endAngle: 0,
        min: 0,
        max: 100,
        splitNumber: 10,
        itemStyle: {
          color: '#1890ff',
        },
        progress: {
          show: true,
          width: 18,
        },
        pointer: {
          show: false,
        },
        axisLine: {
          lineStyle: {
            width: 18,
          },
        },
        axisTick: {
          show: false,
        },
        splitLine: {
          show: false,
        },
        axisLabel: {
          show: false,
        },
        detail: {
          valueAnimation: true,
          formatter: '{value}%',
          fontSize: 30,
          offsetCenter: [0, '0%'],
        },
        data: [
          {
            value: realtimeMetrics?.table_occupancy_rate || 0,
          },
        ],
      },
    ],
  };

  if (loading && !overviewStats) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <Spin size="large" />
        <p style={{ marginTop: 16 }}>正在加载数据...</p>
      </div>
    );
  }

  return (
    <div style={{ padding: '24px', background: '#f0f2f5', minHeight: '100vh' }}>
      {/* 标题栏 */}
      <div style={{ marginBottom: 24, textAlign: 'center' }}>
        <h1 style={{ fontSize: 32, fontWeight: 'bold', margin: 0 }}>
          智链OS 数据可视化大屏
        </h1>
        <p style={{ color: '#666', marginTop: 8 }}>
          实时更新 | 最后更新: {new Date().toLocaleTimeString('zh-CN')}
        </p>
      </div>

      {/* 核心指标卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="今日订单"
              value={overviewStats?.orders?.today || 0}
              prefix={<ShopOutlined />}
              suffix={
                <span style={{ fontSize: 14 }}>
                  {overviewStats?.orders?.growth_rate > 0 ? (
                    <Tag color="success" icon={<ArrowUpOutlined />}>
                      {overviewStats?.orders?.growth_rate.toFixed(1)}%
                    </Tag>
                  ) : (
                    <Tag color="error" icon={<ArrowDownOutlined />}>
                      {Math.abs(overviewStats?.orders?.growth_rate || 0).toFixed(1)}%
                    </Tag>
                  )}
                </span>
              }
              valueStyle={{ color: '#1890ff', fontSize: 32 }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="今日营收"
              value={(overviewStats?.revenue?.today || 0) / 100}
              prefix={<DollarOutlined />}
              suffix={
                <span style={{ fontSize: 14 }}>
                  {overviewStats?.revenue?.growth_rate > 0 ? (
                    <Tag color="success" icon={<ArrowUpOutlined />}>
                      {overviewStats?.revenue?.growth_rate.toFixed(1)}%
                    </Tag>
                  ) : (
                    <Tag color="error" icon={<ArrowDownOutlined />}>
                      {Math.abs(overviewStats?.revenue?.growth_rate || 0).toFixed(1)}%
                    </Tag>
                  )}
                </span>
              }
              precision={2}
              valueStyle={{ color: '#52c41a', fontSize: 32 }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="会员总数"
              value={memberStats?.total_members || 0}
              prefix={<UserOutlined />}
              suffix={
                <span style={{ fontSize: 14 }}>
                  <Tag color="blue">今日新增 {memberStats?.new_members_today || 0}</Tag>
                </span>
              }
              valueStyle={{ color: '#faad14', fontSize: 32 }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="活跃门店"
              value={overviewStats?.stores?.active || 0}
              prefix={<TeamOutlined />}
              suffix={`/ ${overviewStats?.stores?.total || 0}`}
              valueStyle={{ color: '#722ed1', fontSize: 32 }}
            />
          </Card>
        </Col>
      </Row>

      {/* 图表区域 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={16}>
          <Card>
            <ReactECharts option={salesTrendOption} style={{ height: 400 }} />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <ReactECharts option={memberLevelOption} style={{ height: 400 }} />
          </Card>
        </Col>
      </Row>

      {/* 实时指标 */}
      <Row gutter={16}>
        <Col span={8}>
          <Card>
            <ReactECharts option={tableOccupancyOption} style={{ height: 300 }} />
          </Card>
        </Col>
        <Col span={8}>
          <Card title="实时运营指标" bordered={false}>
            <div style={{ padding: '20px 0' }}>
              <Row gutter={16}>
                <Col span={12}>
                  <Statistic
                    title="当前订单"
                    value={realtimeMetrics?.current_orders || 0}
                    valueStyle={{ fontSize: 28 }}
                  />
                </Col>
                <Col span={12}>
                  <Statistic
                    title="在店顾客"
                    value={realtimeMetrics?.current_customers || 0}
                    valueStyle={{ fontSize: 28 }}
                  />
                </Col>
              </Row>
              <Row gutter={16} style={{ marginTop: 24 }}>
                <Col span={12}>
                  <Statistic
                    title="平均等待"
                    value={realtimeMetrics?.average_wait_time || 0}
                    suffix="分钟"
                    valueStyle={{ fontSize: 28 }}
                  />
                </Col>
                <Col span={12}>
                  <Statistic
                    title="厨房队列"
                    value={realtimeMetrics?.kitchen_queue || 0}
                    valueStyle={{ fontSize: 28 }}
                  />
                </Col>
              </Row>
            </div>
          </Card>
        </Col>
        <Col span={8}>
          <Card title="系统状态" bordered={false}>
            <div style={{ padding: '20px 0' }}>
              <p style={{ fontSize: 16, marginBottom: 16 }}>
                <Tag color="success">系统运行正常</Tag>
              </p>
              <p style={{ fontSize: 14, color: '#666' }}>
                • Agent数量: {overviewStats?.agents?.total || 7}
              </p>
              <p style={{ fontSize: 14, color: '#666' }}>
                • 活跃Agent: {overviewStats?.agents?.active || 7}
              </p>
              <p style={{ fontSize: 14, color: '#666' }}>
                • 数据更新: 实时
              </p>
              <p style={{ fontSize: 14, color: '#666' }}>
                • 刷新间隔: 30秒
              </p>
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default DataVisualizationScreen;
