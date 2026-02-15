import React, { useEffect, useState } from 'react';
import { Card, Col, Row, Statistic, Alert, Spin } from 'antd';
import {
  UserOutlined,
  ShoppingOutlined,
  InboxOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';

const Dashboard: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [healthStatus, setHealthStatus] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    checkHealth();
  }, []);

  const checkHealth = async () => {
    try {
      setLoading(true);
      const response = await apiClient.healthCheck();
      setHealthStatus(response);
      setError(null);
    } catch (err: any) {
      setError(err.message || '无法连接到后端服务');
    } finally {
      setLoading(false);
    }
  };

  // 订单趋势图配置
  const orderTrendOption = {
    title: {
      text: '近7天订单趋势',
      left: 'center',
    },
    tooltip: {
      trigger: 'axis',
    },
    xAxis: {
      type: 'category',
      data: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
    },
    yAxis: {
      type: 'value',
    },
    series: [
      {
        name: '订单数',
        data: [280, 310, 295, 340, 380, 420, 328],
        type: 'line',
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
    ],
  };

  // Agent使用情况饼图
  const agentUsageOption = {
    title: {
      text: 'Agent使用分布',
      left: 'center',
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
        name: '调用次数',
        type: 'pie',
        radius: '50%',
        data: [
          { value: 235, name: '智能排班' },
          { value: 189, name: '订单协同' },
          { value: 156, name: '库存预警' },
          { value: 142, name: '服务质量' },
          { value: 98, name: '培训辅导' },
          { value: 87, name: '决策支持' },
          { value: 76, name: '预定宴会' },
        ],
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

  // 门店营业额柱状图
  const revenueOption = {
    title: {
      text: '门店营业额TOP5',
      left: 'center',
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow',
      },
    },
    xAxis: {
      type: 'category',
      data: ['朝阳店', '海淀店', '西城店', '东城店', '丰台店'],
    },
    yAxis: {
      type: 'value',
      name: '营业额(万元)',
    },
    series: [
      {
        name: '营业额',
        data: [45.2, 38.6, 35.8, 32.4, 28.9],
        type: 'bar',
        itemStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: '#52c41a' },
              { offset: 1, color: '#95de64' },
            ],
          },
        },
      },
    ],
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <Spin size="large" />
        <p style={{ marginTop: 16 }}>正在加载...</p>
      </div>
    );
  }

  return (
    <div>
      <h1 style={{ marginBottom: 24 }}>控制台</h1>

      {error && (
        <Alert
          message="连接错误"
          description={error}
          type="error"
          showIcon
          closable
          style={{ marginBottom: 24 }}
        />
      )}

      {healthStatus && (
        <Alert
          message="系统状态"
          description={`后端服务运行正常 - ${healthStatus.status}`}
          type="success"
          showIcon
          style={{ marginBottom: 24 }}
        />
      )}

      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic
              title="活跃门店"
              value={12}
              prefix={<UserOutlined />}
              valueStyle={{ color: '#3f8600' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="今日订单"
              value={328}
              prefix={<ShoppingOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="库存预警"
              value={5}
              prefix={<InboxOutlined />}
              valueStyle={{ color: '#cf1322' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Agent运行"
              value={7}
              suffix="/ 7"
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 数据可视化图表 */}
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card>
            <ReactECharts option={orderTrendOption} style={{ height: 300 }} />
          </Card>
        </Col>
        <Col span={12}>
          <Card>
            <ReactECharts option={agentUsageOption} style={{ height: 300 }} />
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card>
            <ReactECharts option={revenueOption} style={{ height: 300 }} />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="系统信息" bordered={false}>
            <p>• 版本: 0.1.0</p>
            <p>• Agent数量: 7个</p>
            <p>• API状态: {healthStatus ? '正常' : '异常'}</p>
            <p>• 最后更新: {new Date().toLocaleString('zh-CN')}</p>
            <p style={{ marginTop: 16, color: '#999' }}>
              • 智能排班 - 基于客流预测的自动排班
            </p>
            <p style={{ color: '#999' }}>• 订单协同 - 全流程订单管理</p>
            <p style={{ color: '#999' }}>• 库存预警 - 实时库存监控</p>
            <p style={{ color: '#999' }}>• 服务质量 - 评价分析与监控</p>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default Dashboard;
