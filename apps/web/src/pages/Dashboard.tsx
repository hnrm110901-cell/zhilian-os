import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { Card, Col, Row, Alert, Tag, Button, Switch, Space } from 'antd';
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
import { PageHeader, DataCard, LoadingSkeleton } from '../components';

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
  }, [autoRefresh, refreshInterval, loadDashboardData]);

  const loadDashboardData = useCallback(async () => {
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
  }, []);

  // 手动刷新
  const handleManualRefresh = useCallback(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  // 从决策报告中提取KPI数据用于图表 - 使用 useMemo 缓存计算结果
  const kpiChartData = useMemo(() => {
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
  }, [decisionReport]);

  // KPI达成率图表配置 - 使用 useMemo 缓存配置对象
  const kpiAchievementOption = useMemo(() => {
    if (!kpiChartData) return {};

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
        data: kpiChartData.categories,
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
          data: kpiChartData.achievementRates,
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
          data: kpiChartData.categories.map(() => 100),
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
  }, [kpiChartData]);

  // KPI状态分布饼图 - 使用 useMemo 缓存配置对象
  const kpiStatusOption = useMemo(() => {
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
  }, [decisionReport]);

  if (loading) {
    return <LoadingSkeleton type="card" rows={4} />;
  }

  return (
    <div>
      <PageHeader
        title="控制台"
        subtitle={`最后更新: ${lastRefreshTime.toLocaleTimeString('zh-CN')}`}
        extra={
          <Space>
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
        }
      />

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
        <Card
          style={{
            marginBottom: 16,
            background: 'var(--primary-gradient)',
            border: 'none',
          }}
          bodyStyle={{ padding: '32px' }}
        >
          <Row align="middle" gutter={24}>
            <Col xs={24} sm={18}>
              <div style={{ color: 'white' }}>
                <h2 style={{ color: 'white', marginBottom: 8, fontSize: 20 }}>
                  <DashboardOutlined /> 系统健康分数
                </h2>
                <p style={{ fontSize: 56, fontWeight: 'bold', margin: '16px 0', lineHeight: 1 }}>
                  {decisionReport.overall_health_score.toFixed(1)}
                </p>
                <p style={{ opacity: 0.9, marginTop: 8, fontSize: 15 }}>
                  {decisionReport.kpi_summary.total_kpis} 个KPI指标 |{' '}
                  {decisionReport.action_required} 项需要关注
                </p>
              </div>
            </Col>
            <Col xs={24} sm={6} style={{ textAlign: 'right' }}>
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                <Tag color="success" style={{ fontSize: 14, padding: '4px 12px' }}>
                  {decisionReport.kpi_summary.status_distribution.on_track || 0} 正常
                </Tag>
                <Tag color="warning" style={{ fontSize: 14, padding: '4px 12px' }}>
                  {decisionReport.kpi_summary.status_distribution.at_risk || 0} 风险
                </Tag>
                <Tag color="error" style={{ fontSize: 14, padding: '4px 12px' }}>
                  {decisionReport.kpi_summary.status_distribution.off_track || 0} 异常
                </Tag>
              </Space>
            </Col>
          </Row>
        </Card>
      )}

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <DataCard
            title="KPI总数"
            value={decisionReport?.kpi_summary.total_kpis || 0}
            prefix={<DashboardOutlined />}
            style={{ height: '100%' }}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <DataCard
            title="业务洞察"
            value={decisionReport?.insights_summary.total_insights || 0}
            suffix={`/ ${decisionReport?.insights_summary.high_impact || 0} 高影响`}
            prefix={<RiseOutlined />}
            style={{ height: '100%' }}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <DataCard
            title="待处理建议"
            value={decisionReport?.action_required || 0}
            prefix={<InboxOutlined />}
            style={{ height: '100%' }}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <DataCard
            title="KPI达标率"
            value={
              decisionReport
                ? (decisionReport.kpi_summary.on_track_rate * 100).toFixed(1)
                : 0
            }
            suffix="%"
            prefix={<CheckCircleOutlined />}
            trend={{
              value: 5.2,
              isPositive: decisionReport ? decisionReport.kpi_summary.on_track_rate >= 0.8 : false,
            }}
            style={{ height: '100%' }}
          />
        </Col>
      </Row>

      {/* 数据可视化图表 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card>
            {decisionReport ? (
              <ReactECharts option={kpiAchievementOption} style={{ height: 320 }} />
            ) : (
              <LoadingSkeleton type="card" rows={1} />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card>
            {decisionReport ? (
              <ReactECharts option={kpiStatusOption} style={{ height: 320 }} />
            ) : (
              <LoadingSkeleton type="card" rows={1} />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card title="关键业务洞察" bordered={false}>
            {decisionReport?.insights_summary.key_insights.slice(0, 3).map((insight, index) => (
              <div
                key={insight.insight_id}
                style={{
                  marginBottom: 16,
                  paddingBottom: 16,
                  borderBottom: index < 2 ? '1px solid var(--divider-color)' : 'none',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 8,
                  }}
                >
                  <strong style={{ fontSize: 15 }}>{insight.title}</strong>
                  <Tag
                    color={
                      insight.impact_level === 'high'
                        ? 'red'
                        : insight.impact_level === 'medium'
                        ? 'orange'
                        : 'blue'
                    }
                  >
                    {insight.impact_level === 'high'
                      ? '高影响'
                      : insight.impact_level === 'medium'
                      ? '中影响'
                      : '低影响'}
                  </Tag>
                </div>
                <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: 0 }}>
                  {insight.description}
                </p>
              </div>
            )) || (
              <p style={{ color: 'var(--text-tertiary)', textAlign: 'center', padding: '32px 0' }}>
                暂无洞察数据
              </p>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="系统信息" bordered={false}>
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>版本</span>
                <span style={{ fontWeight: 500 }}>0.1.0</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Agent数量</span>
                <span style={{ fontWeight: 500 }}>7个</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>API状态</span>
                <Tag color={healthStatus ? 'success' : 'error'}>
                  {healthStatus ? '正常' : '异常'}
                </Tag>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>最后更新</span>
                <span style={{ fontWeight: 500 }}>
                  {new Date().toLocaleString('zh-CN')}
                </span>
              </div>
              {decisionReport && (
                <>
                  <div
                    style={{
                      height: 1,
                      background: 'var(--divider-color)',
                      margin: '12px 0',
                    }}
                  />
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>报告时间</span>
                    <span style={{ fontWeight: 500 }}>
                      {new Date(decisionReport.report_date).toLocaleString('zh-CN')}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>门店ID</span>
                    <span style={{ fontWeight: 500 }}>{decisionReport.store_id}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>健康分数</span>
                    <span style={{ fontWeight: 500, fontSize: 16, color: 'var(--primary-color)' }}>
                      {decisionReport.overall_health_score.toFixed(1)}/100
                    </span>
                  </div>
                </>
              )}
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default Dashboard;
