import React, { useEffect, useState } from 'react';
import { Card, Col, Row, Statistic, Alert, Spin, Tag, Button, Switch, Space } from 'antd';
import {
  InboxOutlined,
  CheckCircleOutlined,
  RiseOutlined,
  DashboardOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { decisionAgentService, type DecisionReport } from '../services/decisionAgent';

const Dashboard: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [healthStatus, setHealthStatus] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [decisionReport, setDecisionReport] = useState<DecisionReport | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval] = useState(30000); // 30秒
  const [lastRefreshTime, setLastRefreshTime] = useState<Date>(new Date());

  useEffect(() => {
    loadDashboardData();

    // 设置自动刷新
    let intervalId: number | undefined;
    if (autoRefresh) {
      intervalId = window.setInterval(() => {
        loadDashboardData();
      }, refreshInterval);
    }

    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [autoRefresh, refreshInterval]);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      setError(null);

      // 并发加载健康检查和决策报告
      const [health, report] = await Promise.all([
        apiClient.healthCheck(),
        decisionAgentService.getDecisionReport(),
      ]);

      setHealthStatus(health);
      setDecisionReport(report);
      setLastRefreshTime(new Date());
    } catch (err: any) {
      console.error('Dashboard data loading error:', err);
      setError(err.message || '无法加载数据');
    } finally {
      setLoading(false);
    }
  };

  // 手动刷新
  const handleManualRefresh = () => {
    loadDashboardData();
  };

  // 从决策报告中提取KPI数据用于图表
  const getKPIChartData = () => {
    if (!decisionReport) return null;

    const kpis = decisionReport.kpi_summary.key_kpis;

    // 营收类KPI趋势
    const revenueKPIs = kpis.filter(k => k.category === 'revenue');

    return {
      categories: revenueKPIs.map(k => k.metric_name),
      currentValues: revenueKPIs.map(k => k.current_value),
      targetValues: revenueKPIs.map(k => k.target_value),
      achievementRates: revenueKPIs.map(k => k.achievement_rate * 100),
    };
  };

  // KPI达成率图表配置
  const kpiAchievementOption = () => {
    const chartData = getKPIChartData();
    if (!chartData) return {};

    return {
      title: {
        text: 'KPI达成率',
        left: 'center',
      },
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          let result = params[0].name + '<br/>';
          params.forEach((item: any) => {
            result += `${item.marker}${item.seriesName}: ${item.value.toFixed(1)}%<br/>`;
          });
          return result;
        },
      },
      legend: {
        data: ['达成率', '目标线'],
        bottom: 10,
      },
      xAxis: {
        type: 'category',
        data: chartData.categories,
        axisLabel: {
          interval: 0,
          rotate: 30,
        },
      },
      yAxis: {
        type: 'value',
        name: '达成率(%)',
        max: 120,
      },
      series: [
        {
          name: '达成率',
          data: chartData.achievementRates,
          type: 'bar',
          itemStyle: {
            color: (params: any) => {
              const value = params.value;
              if (value >= 95) return '#52c41a';
              if (value >= 85) return '#faad14';
              return '#f5222d';
            },
          },
        },
        {
          name: '目标线',
          data: chartData.categories.map(() => 100),
          type: 'line',
          itemStyle: {
            color: '#1890ff',
          },
          lineStyle: {
            type: 'dashed',
          },
        },
      ],
    };
  };

  // KPI状态分布饼图
  const kpiStatusOption = () => {
    if (!decisionReport) return {};

    const statusDist = decisionReport.kpi_summary.status_distribution;

    return {
      title: {
        text: 'KPI状态分布',
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
          name: 'KPI数量',
          type: 'pie',
          radius: '50%',
          data: [
            { value: statusDist.on_track || 0, name: '正常', itemStyle: { color: '#52c41a' } },
            { value: statusDist.at_risk || 0, name: '风险', itemStyle: { color: '#faad14' } },
            { value: statusDist.off_track || 0, name: '异常', itemStyle: { color: '#f5222d' } },
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>控制台</h1>
        <Space>
          <span style={{ fontSize: 12, color: '#999' }}>
            最后更新: {lastRefreshTime.toLocaleTimeString('zh-CN')}
          </span>
          <Button
            icon={<ReloadOutlined spin={loading} />}
            onClick={handleManualRefresh}
            loading={loading}
          >
            刷新
          </Button>
          <span style={{ fontSize: 14 }}>自动刷新:</span>
          <Switch
            checked={autoRefresh}
            onChange={setAutoRefresh}
            checkedChildren="开"
            unCheckedChildren="关"
          />
        </Space>
      </div>

      {error && (
        <Alert
          message="数据加载失败"
          description={
            <div>
              <p>{error}</p>
              <Button size="small" onClick={handleManualRefresh}>
                重试
              </Button>
            </div>
          }
          type="error"
          showIcon
          closable
          onClose={() => setError(null)}
          style={{ marginBottom: 24 }}
        />
      )}

      {healthStatus && !error && (
        <Alert
          message="系统状态"
          description={`后端服务运行正常 - ${healthStatus.status}`}
          type="success"
          showIcon
          style={{ marginBottom: 24 }}
        />
      )}

      {/* 健康分数卡片 */}
      {decisionReport && (
        <Card style={{ marginBottom: 16, background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}>
          <Row align="middle">
            <Col span={18}>
              <div style={{ color: 'white' }}>
                <h2 style={{ color: 'white', marginBottom: 8 }}>
                  <DashboardOutlined /> 系统健康分数
                </h2>
                <p style={{ fontSize: 48, fontWeight: 'bold', margin: 0 }}>
                  {decisionReport.overall_health_score.toFixed(1)}
                </p>
                <p style={{ opacity: 0.9, marginTop: 8 }}>
                  {decisionReport.kpi_summary.total_kpis} 个KPI指标 |
                  {' '}{decisionReport.action_required} 项需要关注
                </p>
              </div>
            </Col>
            <Col span={6} style={{ textAlign: 'right' }}>
              <div style={{ color: 'white', fontSize: 14 }}>
                <div style={{ marginBottom: 8 }}>
                  <Tag color="success">{decisionReport.kpi_summary.status_distribution.on_track || 0} 正常</Tag>
                </div>
                <div style={{ marginBottom: 8 }}>
                  <Tag color="warning">{decisionReport.kpi_summary.status_distribution.at_risk || 0} 风险</Tag>
                </div>
                <div>
                  <Tag color="error">{decisionReport.kpi_summary.status_distribution.off_track || 0} 异常</Tag>
                </div>
              </div>
            </Col>
          </Row>
        </Card>
      )}

      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic
              title="KPI总数"
              value={decisionReport?.kpi_summary.total_kpis || 0}
              prefix={<DashboardOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="业务洞察"
              value={decisionReport?.insights_summary.total_insights || 0}
              suffix={`/ ${decisionReport?.insights_summary.high_impact || 0} 高影响`}
              prefix={<RiseOutlined />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="待处理建议"
              value={decisionReport?.action_required || 0}
              prefix={<InboxOutlined />}
              valueStyle={{ color: '#cf1322' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="KPI达标率"
              value={decisionReport ? (decisionReport.kpi_summary.on_track_rate * 100).toFixed(1) : 0}
              suffix="%"
              prefix={<CheckCircleOutlined />}
              valueStyle={{
                color: decisionReport && decisionReport.kpi_summary.on_track_rate >= 0.8 ? '#52c41a' : '#faad14'
              }}
            />
          </Card>
        </Col>
      </Row>

      {/* 数据可视化图表 */}
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card>
            {decisionReport ? (
              <ReactECharts option={kpiAchievementOption()} style={{ height: 300 }} />
            ) : (
              <div style={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Spin />
              </div>
            )}
          </Card>
        </Col>
        <Col span={12}>
          <Card>
            {decisionReport ? (
              <ReactECharts option={kpiStatusOption()} style={{ height: 300 }} />
            ) : (
              <div style={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Spin />
              </div>
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card title="关键业务洞察" bordered={false}>
            {decisionReport?.insights_summary.key_insights.slice(0, 3).map((insight, index) => (
              <div key={insight.insight_id} style={{ marginBottom: 16, paddingBottom: 16, borderBottom: index < 2 ? '1px solid #f0f0f0' : 'none' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <strong>{insight.title}</strong>
                  <Tag color={insight.impact_level === 'high' ? 'red' : insight.impact_level === 'medium' ? 'orange' : 'blue'}>
                    {insight.impact_level === 'high' ? '高影响' : insight.impact_level === 'medium' ? '中影响' : '低影响'}
                  </Tag>
                </div>
                <p style={{ color: '#666', fontSize: 13, margin: 0 }}>{insight.description}</p>
              </div>
            )) || <p style={{ color: '#999' }}>暂无洞察数据</p>}
          </Card>
        </Col>
        <Col span={12}>
          <Card title="系统信息" bordered={false}>
            <p>• 版本: 0.1.0</p>
            <p>• Agent数量: 7个</p>
            <p>• API状态: {healthStatus ? '正常' : '异常'}</p>
            <p>• 最后更新: {new Date().toLocaleString('zh-CN')}</p>
            {decisionReport && (
              <>
                <p style={{ marginTop: 16 }}>• 报告时间: {new Date(decisionReport.report_date).toLocaleString('zh-CN')}</p>
                <p>• 门店ID: {decisionReport.store_id}</p>
                <p>• 健康分数: {decisionReport.overall_health_score.toFixed(1)}/100</p>
              </>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default Dashboard;
